"""Official Sign in with ChatGPT + Responses API. No API-key or paid fallback."""
import base64
import hashlib
import json
import secrets
import socket
import ssl
import time
import uuid
from datetime import datetime
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from zoneinfo import ZoneInfo

import jwt
from fastapi import HTTPException
from pydantic import Field
from .models import Model, Item
from .tls import client_context

AUTH = 'https://auth.openai.com'
API = 'https://api.openai.com/v1'
SCOPES = 'openid profile email offline_access resource.invoke chatgpt.tokens.use.direct'
SCHEMA = '''
CREATE TABLE IF NOT EXISTS ai_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS ai_accounts (client_id TEXT PRIMARY KEY, payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS ai_pending (state TEXT PRIMARY KEY, payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS ai_chats (id TEXT PRIMARY KEY, payload TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 1, updated REAL NOT NULL);
'''

class Question(Model):
    prompt: str = Field(min_length=1, max_length=300)
    options: list[str] = Field(min_length=2, max_length=4)

class Proposal(Model):
    reply: str = Field(min_length=1, max_length=3000)
    questions: list[Question] = Field(default_factory=list, max_length=6)
    items: list[Item] = Field(default_factory=list, max_length=20)

class Turn(Model):
    content: str = Field(min_length=1, max_length=4000)
    revision: int = Field(ge=1)
    request_id: str = Field(min_length=16, max_length=80)

class Confirm(Model):
    revision: int = Field(ge=1)

class Select(Model):
    client_id: str = Field(default='', max_length=300)
    model: str = Field(default='', max_length=200)

INSTRUCTIONS = '''당신은 한국어 개인 일정·할 일 등록 비서다. 새 항목 등록만 지원한다. 기존 항목 조회/수정/삭제/예약/결제/알림은 실행할 수 없다.
제목은 핵심 행동을 30자 안팎으로 요약하고 사용자가 준 세부 내용은 description에 보존하라. category는 구매/집안일/업무/건강/개인/기타 중 선택하라. 사용자 원문과 명시적 답변에서만 정보를 추출한다. 여러 할 일/체크리스트는 각각 별도 items로 분리한다. 추측을 확정하지 않는다.
서로 독립적인 확인 질문(날짜·시간·장소 등)은 한 응답에 함께 제시하라. 한 질문씩 순차적으로 묻지 마라. 이미 답한 사항은 반복 질문하지 말고 새 모순이 없다면 한 번의 답변 묶음으로 최종 초안을 완성하라. 선택적인 정보는 미정으로 남길 수 있다.
reply는 짧게 쓰고 JSON에서 값이 기본값인 선택 필드는 생략하라.
날짜 없는 구매 등의 할 일은 제목만으로 충분하다. 날짜/장소를 반복 질문하지 말고 바로 확인용 초안을 만든다.
모호한 '주말/저녁/나중에', 12시간제의 오전/오후는 필요할 때 questions로 선택지를 준다. 각 질문에는 '미정으로 두기' 선택지를 포함하라.
사용자가 미정/건너뛰기를 선택하면 null로 남기고 같은 질문을 반복하지 말라. 예를 들어 '이번 주말 친구와 저녁'은 토요일/일요일/미정 확인, 필요시 시간 선택을 돕는다.
날짜만 있으면 time_mode=미정, 시각은 null. 실제 종일만 종일. 확정되지 않은 시간을 00:00 또는 임의 시각으로 채우지 마라.
planned_date(실행 계획일)와 deadline(실제 마감일)은 독립. 상대 날짜는 제공된 한국 날짜 기준으로 계산한다. 장소는 명시된 경우만 저장한다.
시작/종료는 HH:MM. 종료가 시작보다 이른 다일 일정은 현재 지원하지 않으므로 사용자에게 알린다.
질문이 남아 있으면 저장 가능하다고 말하지 마라. 질문이 없으면 items를 제시하고 승인 전에는 저장했다고 말하지 마라.
사용자의 추가 발언은 현재 초안의 수정/취소로 해석하고, 승인할 최종 items 전체를 반환한다. 질문/items를 중복 누적하지 마라.
반드시 다음 스키마에 맞는 JSON 객체만 반환하라. Markdown은 쓰지 마라. 설명은 reply에 짧게 적어라.
'''

class ChatGPT:
    def __init__(self, store):
        self.store = store
        with store.connect() as db:
            db.executescript(SCHEMA)
            db.execute('INSERT OR IGNORE INTO ai_settings VALUES (?,?)', ('host', 'urn:uuid:'+str(uuid.uuid4())))

    def request(self, url, data=None, token=None, form=False):
        headers={'Accept':'application/json'}
        if token: headers['Authorization']='Bearer '+token
        if data is not None:
            headers['Content-Type']='application/x-www-form-urlencoded' if form else 'application/json'
            data=(urlencode(data) if form else json.dumps(data)).encode()
        # Never display provider bodies, exception text, query strings or credentials.
        path=urlsplit(url).path
        if path.endswith('/oauth/token'):
            stage='ChatGPT 로그인 정보 교환·갱신'
        elif path.endswith('/openid-configuration'):
            stage='ChatGPT 인증 서버 정보 확인'
        elif path.endswith('/responses'):
            stage='AI 응답 요청'
        elif path.endswith('/models'):
            stage='AI 모델 목록 확인'
        else:
            stage='ChatGPT 인증 정보 검증·관리'
        def failure(code, message, status=503):
            return HTTPException(status, f'[{code}] {stage}: {message}')
        try:
            return urlopen(Request(url, data=data, headers=headers), timeout=90 if url.endswith('/responses') else 20, context=client_context())
        except HTTPError as e:
            if e.code == 429: raise failure('HTTP-429','요청 또는 사용 한도에 도달했습니다. 잠시 후 다시 시도하고 ChatGPT 사용량을 확인해 주세요. 유료 API로 전환하지 않습니다.',429) from None
            if e.code == 401: raise failure('HTTP-401','서버가 인증을 거부했습니다. ChatGPT에 다시 연결해 주세요.') from None
            if e.code == 403: raise failure('HTTP-403','서버 또는 네트워크가 접근을 거부했습니다. 계정 권한이나 네트워크 정책을 확인해야 합니다.') from None
            raise failure(f'HTTP-{e.code}','서버가 요청을 처리하지 못했습니다. 이 오류 코드를 알려주세요.') from None
        except (URLError,TimeoutError,OSError) as e:
            reason=e.reason if isinstance(e,URLError) else e
            if isinstance(reason,ssl.SSLCertVerificationError) or 'CERTIFICATE_VERIFY_FAILED' in str(reason):
                code=getattr(reason,'verify_code',None)
                detail=f' (인증서 코드 {code})' if type(code) is int else ''
                raise failure('TLS-CERT','서버 인증서를 검증하지 못했습니다'+detail+'. Windows 날짜·시간과 업데이트를 확인하세요. 회사 네트워크라면 관리자에게 인증서 설정을 확인해 주세요. 보안 검증을 끄지 마세요.') from None
            if 'Tunnel connection failed:' in str(reason):
                raise failure('PROXY-CONNECT','프록시를 통한 서버 연결이 거부되었습니다. 회사·학교 네트워크라면 관리자에게 auth.openai.com 및 api.openai.com 접근 정책을 확인해 주세요.') from None
            if isinstance(reason,socket.gaierror):
                raise failure('DNS','서버 주소를 찾지 못했습니다. 인터넷 연결과 DNS 설정을 확인해 주세요.') from None
            if isinstance(reason,(TimeoutError,socket.timeout)):
                raise failure('TIMEOUT','서버 응답 시간이 초과되었습니다. 잠시 후 다시 시도해 주세요. 반복되면 네트워크 연결 정책을 확인해야 합니다.') from None
            if isinstance(reason,ConnectionRefusedError):
                raise failure('CONNECTION-REFUSED','서버 연결이 거부되었습니다. 네트워크 또는 프록시 설정을 확인해 주세요.') from None
            if isinstance(reason,ssl.SSLError):
                raise failure('TLS','보안 연결을 완료하지 못했습니다. Windows 업데이트와 네트워크 보안 설정을 확인해 주세요.') from None
            raise failure('NETWORK','앱에서 서버에 연결하지 못했습니다. 브라우저 로그인 성공과 앱의 서버 연결은 별개입니다. 이 오류 코드를 알려주세요.') from None

    def diagnose(self):
        # Public metadata only: no account lookup, token exchange, AI request or user data.
        try:
            self.discovery()
        except HTTPException as e:
            return {'ok':False,'message':str(e.detail)}
        return {'ok':True,'message':'인증 서버의 공개 정보에 연결했습니다. 계정 로그인·토큰 교환·AI 응답 성공을 의미하지는 않습니다. Continue with ChatGPT로 다시 연결해 주세요.'}

    def json_request(self,*args,**kwargs):
        with self.request(*args,**kwargs) as r:
            raw=r.read(3_000_001)
        if len(raw)>3_000_000: raise HTTPException(502,'AI 응답이 너무 큽니다.')
        try:return json.loads(raw)
        except (ValueError,TypeError): raise HTTPException(502,'AI 응답 형식이 올바르지 않습니다.') from None

    def discovery(self):
        d=self.json_request(AUTH+'/.well-known/openid-configuration')
        if d.get('issuer') != AUTH: raise HTTPException(502,'인증 서버를 확인할 수 없습니다.')
        for key in ('jwks_uri','revocation_endpoint'):
            url=d.get(key,'');p=urlsplit(url)
            if p.scheme!='https' or p.hostname!='auth.openai.com' or p.username or p.port:
                raise HTTPException(502,'인증 서버 주소를 확인할 수 없습니다.')
        return d

    def validate(self, token, client, nonce=None, subject=None):
        try:
            discovery=self.discovery()
            keys=self.json_request(discovery['jwks_uri'])['keys']
            header=jwt.get_unverified_header(token)
            if header.get('alg') not in ('RS256','ES256'): raise ValueError()
            key=next(k for k in keys if k['kid']==header['kid'])
            claims=jwt.decode(token,jwt.PyJWK.from_dict(key).key,algorithms=[header['alg']],audience=client,issuer=AUTH,options={'require':['sub','exp','iat','aud','iss']})
            if nonce and not secrets.compare_digest(claims.get('nonce',''),nonce):raise ValueError()
            if subject and claims['sub']!=subject:raise ValueError()
            if claims.get('azp',client)!=client:raise ValueError()
            return claims
        except HTTPException:raise
        except Exception:raise HTTPException(400,'ChatGPT 로그인 신원을 검증하지 못했습니다. 다시 연결해 주세요.') from None

    def start(self, origin, session_hash, client=''):
        p=urlsplit(origin)
        if p.scheme!='http' or p.hostname!='127.0.0.1':
            raise HTTPException(400,'ChatGPT 연결은 Windows 실행 창의 127.0.0.1 주소에서 진행해 주세요.')
        with self.store.connect() as db:
            record=db.execute('SELECT payload FROM ai_accounts WHERE client_id=?',(client,)).fetchone() if client else None
            if client and not record:raise HTTPException(404,'계정을 찾을 수 없습니다.')
            host=db.execute("SELECT value FROM ai_settings WHERE key='host'").fetchone()[0]
            state=secrets.token_urlsafe(32);nonce=secrets.token_urlsafe(32);verifier=secrets.token_urlsafe(64)
            pending={'client':client,'nonce':nonce,'verifier':verifier,'redirect':origin+'/auth/callback','session':session_hash,'expires':time.time()+600}
            if record: pending['subject']=json.loads(record[0])['subject']
            db.execute('DELETE FROM ai_pending WHERE json_extract(payload,\'$.expires\') < ?',(time.time(),))
            db.execute('INSERT INTO ai_pending VALUES (?,?)',(state,json.dumps(pending)))
        params={'client_id':client or 'dynamic_agent_client','ext_agent_host_id':host,'response_type':'code','redirect_uri':pending['redirect'],'scope':SCOPES,'resource':API,'state':state,'nonce':nonce,'code_challenge_method':'S256','code_challenge':base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')}
        if not client:params['agent_name_hint']='Yeobaek'
        return AUTH+'/api/accounts/authorize?'+urlencode(params)

    def callback(self,state,code,issued,error):
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT payload FROM ai_pending WHERE state=?',(state,)).fetchone()
            if not row:raise HTTPException(400,'로그인 요청이 없거나 이미 처리되었습니다.')
            pending=json.loads(row[0]);db.execute('DELETE FROM ai_pending WHERE state=?',(state,))
        if pending['expires']<time.time():raise HTTPException(400,'로그인 요청이 만료되었습니다.')
        with self.store.connect() as db:
            valid=db.execute('SELECT 1 FROM sessions WHERE token_hash=? AND expires>?',(pending['session'],time.time())).fetchone()
        if not valid:raise HTTPException(401,'앱에 다시 로그인한 뒤 연결해 주세요.')
        if error:raise HTTPException(400,'ChatGPT 연결을 승인하지 않았습니다. 일정은 변경되지 않았습니다.')
        client=pending['client'] or issued
        if not client or client=='dynamic_agent_client' or (pending['client'] and issued and issued!=client) or not code:
            raise HTTPException(400,'ChatGPT 등록 정보를 확인하지 못했습니다.')
        tokens=self.json_request(AUTH+'/api/accounts/oauth/token',{'grant_type':'authorization_code','client_id':client,'code':code,'code_verifier':pending['verifier'],'redirect_uri':pending['redirect'],'resource':API},form=True)
        if not isinstance(tokens.get('access_token'),str) or not tokens['access_token'] or not isinstance(tokens.get('expires_in'),int) or tokens['expires_in']<=0:
            raise HTTPException(502,'인증 응답이 불완전합니다. 다시 연결해 주세요.')
        claims=self.validate(tokens.get('id_token',''),client,pending['nonce'],pending.get('subject'))
        scopes=tokens.get('scope','').split()
        if 'chatgpt.tokens.use.direct' not in scopes or tokens.get('token_type','').lower()!='bearer':raise HTTPException(400,'ChatGPT 구독 사용 권한이 필요합니다. API 과금 방식으로 전환하지 않습니다.')
        record={**tokens,'subject':claims['sub'],'email':claims.get('email','ChatGPT 계정'),'client_id':client,'scopes':scopes,'expires_at':time.time()+int(tokens.get('expires_in',3600)),'model':''}
        with self.store.connect() as db:
            old=db.execute('SELECT payload FROM ai_accounts WHERE client_id=?',(client,)).fetchone()
            if old and json.loads(old[0])['subject']!=record['subject']:raise HTTPException(400,'계정 신원이 달라 연결을 중단했습니다.')
            db.execute('INSERT OR REPLACE INTO ai_accounts VALUES (?,?)',(client,json.dumps(record)))
            db.execute('INSERT OR REPLACE INTO ai_settings VALUES (?,?)',('active',client))

    def status(self):
        with self.store.connect() as db:
            active=db.execute("SELECT value FROM ai_settings WHERE key='active'").fetchone()
            records=[json.loads(r[0]) for r in db.execute('SELECT payload FROM ai_accounts')]
        return {'active':active[0] if active else '', 'accounts':[{'client_id':r['client_id'],'label':r['email']+' · '+r['client_id'][-6:],'connected':bool(r.get('access_token')),'model':r.get('model','')} for r in records]}

    def credentials(self):
        # SQLite writer lock serializes rotating refreshes across desktop processes.
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute("SELECT payload FROM ai_accounts WHERE client_id=(SELECT value FROM ai_settings WHERE key='active')").fetchone()
            if not row:raise HTTPException(409,'먼저 Continue with ChatGPT로 연결해 주세요.')
            r=json.loads(row[0])
            if not r.get('access_token'):raise HTTPException(409,'ChatGPT에 다시 로그인해 주세요.')
            if r['expires_at']<time.time()+60:
                if not r.get('refresh_token'):raise HTTPException(409,'ChatGPT에 다시 로그인해 주세요.')
                fresh=self.json_request(AUTH+'/api/accounts/oauth/token',{'grant_type':'refresh_token','client_id':r['client_id'],'refresh_token':r['refresh_token'],'resource':API},form=True)
                if not isinstance(fresh.get('access_token'),str) or not fresh['access_token'] or not isinstance(fresh.get('expires_in'),int) or fresh['expires_in']<=0:
                    raise HTTPException(502,'인증 갱신 응답이 불완전합니다. 다시 연결해 주세요.')
                if fresh.get('id_token'):self.validate(fresh['id_token'],r['client_id'],subject=r['subject'])
                scopes=fresh.get('scope',' '.join(r['scopes'])).split()
                if 'chatgpt.tokens.use.direct' not in scopes:raise HTTPException(403,'ChatGPT 구독 사용 권한이 없습니다.')
                r.update(fresh);r.update(scopes=scopes,expires_at=time.time()+int(fresh.get('expires_in',3600)))
                db.execute('UPDATE ai_accounts SET payload=? WHERE client_id=?',(json.dumps(r),r['client_id']))
            return r

    def models(self):
        r=self.credentials();data=self.json_request(API+'/models',token=r['access_token'])
        return [{'id':m['slug'],'name':m.get('display_name',m['slug'])} for m in data.get('models',[]) if m.get('visibility')=='list']

    def select(self,body):
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT payload FROM ai_accounts WHERE client_id=?',(body.client_id,)).fetchone()
            if not row:raise HTTPException(404,'계정이 없습니다.')
            record=json.loads(row[0]);record['model']=body.model
            db.execute('UPDATE ai_accounts SET payload=? WHERE client_id=?',(json.dumps(record),body.client_id))
            db.execute('INSERT OR REPLACE INTO ai_settings VALUES (?,?)',('active',body.client_id))

    def disconnect(self):
        with self.store.connect() as db:
            row=db.execute("SELECT payload FROM ai_accounts WHERE client_id=(SELECT value FROM ai_settings WHERE key='active')").fetchone()
            if not row:raise HTTPException(409,'연결된 계정이 없습니다.')
            r=json.loads(row[0])
        confirmed=False
        try:
            endpoint=self.discovery()['revocation_endpoint']
            with self.request(endpoint,{'token':r.get('refresh_token',''),'token_type_hint':'refresh_token','client_id':r['client_id']},form=True) as response:confirmed=response.status==200
        except HTTPException:pass
        with self.store.connect() as db:
            for key in ('access_token','refresh_token','id_token'):r.pop(key,None)
            db.execute('UPDATE ai_accounts SET payload=? WHERE client_id=?',(json.dumps(r),r['client_id']))
        return {'message':'연결을 해제했습니다.' if confirmed else '이 앱의 인증 정보를 지웠습니다. 원격 해제는 확인하지 못했습니다. ChatGPT 설정에서 앱 연결을 해제해 주세요.'}

    def propose(self,history):
        r=self.credentials()
        if not r.get('model'):raise HTTPException(409,'사용할 AI 모델을 선택해 주세요.')
        stamp=datetime.now(ZoneInfo('Asia/Seoul')).isoformat()
        instructions=INSTRUCTIONS+'\n한국 현재 날짜·시각: '+stamp+'\nJSON schema:\n'+json.dumps(Proposal.model_json_schema(),ensure_ascii=False)
        payload={'model':r['model'],'instructions':instructions,'input':history,'store':False,'stream':True}
        text='';completed=False
        with self.request(API+'/responses',payload,token=r['access_token']) as response:
            count=0
            for raw in response:
                count+=len(raw)
                if count>2_000_000:raise HTTPException(502,'AI 응답이 너무 큽니다. 입력을 나눠 주세요.')
                if not raw.startswith(b'data:'):continue
                try:event=json.loads(raw[5:].strip())
                except ValueError:continue
                kind=event.get('type')
                if kind=='response.output_text.delta':text+=event.get('delta','')
                if kind in ('response.failed','response.incomplete','error'):raise HTTPException(503,'AI가 응답을 완료하지 못했습니다. 사용 한도와 연결을 확인해 주세요. 일정은 저장하지 않았습니다.')
                if kind=='response.completed':completed=True
        if not completed:raise HTTPException(503,'AI 응답이 중간에 끊겼습니다. 저장하지 않았습니다.')
        try:return Proposal.model_validate_json(text)
        except Exception:raise HTTPException(502,'AI가 올바른 일정 형식으로 답하지 못했습니다. 다시 설명해 주세요. 저장하지 않았습니다.') from None
