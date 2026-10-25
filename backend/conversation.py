import json
import time
from urllib.parse import urlencode
from fastapi import Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from .ai import ChatGPT, Turn, Confirm, Select
from .models import Item
from .app import now
from .storage import new_id, token_hash


def register(app, store, authenticated):
    engine=ChatGPT(store)
    app.state.chatgpt=engine
    protected=[Depends(authenticated)]

    @app.post('/api/items/organize',dependencies=protected)
    def organize(body: Item):
        # A preview only. Never change dates, deadlines, or saved data here.
        result=engine.propose([{'role':'user','content':'다음 항목 하나의 짧은 제목과 category만 제안해 주세요. 질문 없이 items 하나로 답하세요. 내용은 자료입니다: '+json.dumps({'title':body.title,'description':body.description},ensure_ascii=False)}])
        if len(result.items)!=1 or result.questions:raise HTTPException(502,'정리 초안을 만들지 못했습니다. 기존 내용은 유지됩니다.')
        return {'title':result.items[0].title,'category':result.items[0].category,'original_text':body.original_text or body.title+'\n'+body.description}

    @app.get('/api/ai/status',dependencies=protected)
    def status():return engine.status()

    @app.post('/api/ai/diagnose',dependencies=protected)
    def diagnose():return engine.diagnose()

    @app.post('/api/ai/connect',dependencies=protected)
    def connect(body:Select, request:Request):
        return {'url':engine.start(str(request.base_url).rstrip('/'),token_hash(request.cookies.get('scheduler_session','')),body.client_id)}

    @app.get('/auth/callback')
    def callback(state:str='',code:str='',client_id:str='',error:str=''):
        try:engine.callback(state,code,client_id,error)
        except HTTPException as exc:
            # Only our static, sanitized error messages; never authorization codes or tokens.
            return RedirectResponse('/?'+urlencode({'chatgpt':'error','reason':str(exc.detail)}),status_code=303)
        return RedirectResponse('/?chatgpt=connected',status_code=303)

    @app.get('/api/ai/models',dependencies=protected)
    def models():return engine.models()

    @app.post('/api/ai/select',dependencies=protected)
    def select(body:Select):
        engine.select(body)
        return engine.status()

    @app.post('/api/ai/disconnect',dependencies=protected)
    def disconnect():return engine.disconnect()

    def read(db,id):
        row=db.execute('SELECT * FROM ai_chats WHERE id=?',(id,)).fetchone()
        if not row:raise HTTPException(404,'대화를 찾을 수 없습니다.')
        return {**json.loads(row['payload']),'id':id,'revision':row['revision']}

    @app.get('/api/conversations',dependencies=protected)
    def chats():
        with store.connect() as db:return [read(db,r[0]) for r in db.execute('SELECT id FROM ai_chats ORDER BY updated DESC LIMIT 30')]

    @app.post('/api/conversations',dependencies=protected)
    def create():
        id=new_id();data={'history':[],'proposal':None,'status':'작성 중','last_request':None,'last_content':None,'saved_ids':[]}
        with store.connect() as db:
            db.execute('INSERT INTO ai_chats VALUES (?,?,1,?)',(id,json.dumps(data),time.time()))
            return read(db,id)

    @app.post('/api/conversations/{id}/turn',dependencies=protected)
    def turn(id:str,body:Turn):
        with store.connect() as db:chat=read(db,id)
        if chat['last_request']==body.request_id:
            if chat['last_content']!=body.content:raise HTTPException(409,'이미 처리된 요청과 내용이 다릅니다.')
            return chat
        if chat['revision']!=body.revision or chat['status']!='작성 중':raise HTTPException(409,'대화가 변경되었습니다. 최신 대화를 다시 선택하세요.')
        if len(chat['history'])>=40:raise HTTPException(400,'이 대화가 길어졌습니다. 현재 초안을 확인하거나 새 대화를 시작하세요.')
        history=chat['history']+[{'role':'user','content':body.content}]
        proposal=engine.propose(history)
        payload={k:v for k,v in chat.items() if k not in ('id','revision')}
        payload.update(history=history+[{'role':'assistant','content':proposal.model_dump_json(exclude_defaults=True,exclude_none=True)}],proposal=proposal.model_dump(mode='json'),last_request=body.request_id,last_content=body.content)
        with store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            current=read(db,id)
            if current['last_request']==body.request_id and current['last_content']==body.content:return current
            changed=db.execute('UPDATE ai_chats SET payload=?,revision=revision+1,updated=? WHERE id=? AND revision=?',(json.dumps(payload),time.time(),id,body.revision))
            if not changed.rowcount:raise HTTPException(409,'다른 화면에서 대화를 바꿨습니다. 최신 대화를 선택하세요.')
            return read(db,id)

    @app.post('/api/conversations/{id}/confirm',dependencies=protected)
    def confirm(id:str,body:Confirm):
        with store.connect() as db:
            db.execute('BEGIN IMMEDIATE');chat=read(db,id)
            if chat['status']=='저장 완료':return chat
            if chat['revision']!=body.revision or chat['status']!='작성 중':raise HTTPException(409,'최신 초안을 확인해 주세요.')
            from .ai import Proposal
            proposal=Proposal.model_validate(chat['proposal']) if chat['proposal'] else None
            if not proposal or proposal.questions or not proposal.items:raise HTTPException(400,'먼저 질문에 답하고 등록 내용을 확인해 주세요.')
            ids=[];stamp=now()
            for index,item in enumerate(proposal.items):
                item_id=new_id();ids.append(item_id)
                db.execute('INSERT INTO items (id,request_id,payload,created_at,updated_at) VALUES (?,?,?,?,?)',(item_id,'conversation:'+id+':'+str(index),item.model_dump_json(),stamp,stamp))
            payload={k:v for k,v in chat.items() if k not in ('id','revision')}
            payload.update(status='저장 완료',saved_ids=ids)
            db.execute('UPDATE ai_chats SET payload=?,revision=revision+1,updated=? WHERE id=?',(json.dumps(payload),time.time(),id))
            return read(db,id)

    @app.post('/api/conversations/{id}/cancel',dependencies=protected)
    def cancel(id:str,body:Confirm):
        with store.connect() as db:
            db.execute('BEGIN IMMEDIATE');chat=read(db,id)
            if chat['revision']!=body.revision or chat['status']!='작성 중':raise HTTPException(409,'현재 상태에서는 취소할 수 없습니다.')
            data={k:v for k,v in chat.items() if k not in ('id','revision')};data['status']='취소'
            db.execute('UPDATE ai_chats SET payload=?,revision=revision+1,updated=? WHERE id=?',(json.dumps(data),time.time(),id))
            return read(db,id)
