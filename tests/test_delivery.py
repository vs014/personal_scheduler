import json
import subprocess
import time
from types import SimpleNamespace
import pytest
from fastapi.testclient import TestClient
from backend.app import create_app
from backend.delivery import task_id

URL='https://chatgpt.com/codex/tasks/task_test123'

@pytest.fixture
def setup(tmp_path,monkeypatch):
    app=create_app(tmp_path/'app.sqlite3')
    engine=app.state.delivery
    engine.stop.set()  # Drive the durable worker deterministically in tests.
    client=TestClient(app,headers={'X-Scheduler-Client':'web','Content-Type':'application/json'})
    client.post('/api/setup',json={'password':'delivery-test-password'})
    client.put('/api/codex/settings',json={'environment':'scheduler-test','branch':'codex/feedback-delivery'})
    thread=client.post('/api/feedback',json={'title':'화면 개선','kind':'기능 제안','content':'선택을 간단히. $(never-run) `never-run`','request_id':'delivery-feedback-request'}).json()
    calls=[]
    def run(args,text=None,timeout=30):
        calls.append((args,text))
        if args==['login','status']:return SimpleNamespace(returncode=0,stdout='',stderr='Logged in using ChatGPT')
        if args[:2]==['cloud','list']:return SimpleNamespace(returncode=0,stdout=json.dumps({'tasks':[{'id':'task_test123'}]}),stderr='')
        if args[:2]==['cloud','exec']:return SimpleNamespace(returncode=0,stdout=URL+'\n',stderr='')
        if args[:2]==['cloud','status']:return SimpleNamespace(returncode=0,stdout='[READY] review\n',stderr='')
        raise AssertionError(args)
    monkeypatch.setattr(engine,'run',run)
    return client,engine,thread,calls


def test_preview_confirm_snapshot_and_duplicate_delivery(setup):
    c,e,t,calls=setup
    c.post('/api/items',json={'title':'PRIVATE-SCHEDULE','request_id':'private-item-request-id'})
    preview=c.post('/api/codex/preview',json={'ids':[t['id']]}).json()
    assert calls==[] and preview['status']=='확인 대기'
    assert 'PRIVATE-SCHEDULE' not in json.dumps(preview)
    id=preview['id']
    for _ in range(2):assert c.post(f'/api/codex/jobs/{id}/send',json={}).status_code==200
    e.once();e.once()
    sent=[call for call in calls if call[0][:2]==['cloud','exec']]
    assert len(sent)==1 and sent[0][0][-1]=='-'
    assert '$(never-run)' in sent[0][1] and 'PRIVATE-SCHEDULE' not in sent[0][1]
    assert c.get('/api/codex/jobs').json()[0]['url']==URL
    assert c.post('/api/codex/preview',json={'ids':[t['id']]}).json()['id']==id
    c.post(f'/api/codex/jobs/{id}/refresh',json={})
    assert c.get('/api/codex/jobs').json()[0]['status']=='검토 완료'
    assert c.get('/api/feedback').json()[0]['status']=='접수'
    # Completion in Codex is not a claim that the feature was implemented.


def test_ambiguous_create_is_not_automatically_retried(setup,monkeypatch):
    c,e,t,calls=setup
    original=e.run
    def run(args,text=None,timeout=30):
        if args[:2]==['cloud','exec']:raise subprocess.TimeoutExpired('codex',timeout)
        return original(args,text,timeout)
    monkeypatch.setattr(e,'run',run)
    id=c.post('/api/codex/preview',json={'ids':[t['id']]}).json()['id']
    c.post(f'/api/codex/jobs/{id}/send',json={});e.once()
    assert c.get('/api/codex/jobs').json()[0]['status']=='접수 확인 필요'
    c.post(f'/api/codex/jobs/{id}/send',json={});e.once()
    assert c.get('/api/codex/jobs').json()[0]['status']=='접수 확인 필요'
    assert c.post(f'/api/codex/jobs/{id}/receipt',json={'url':'https://evil.invalid/task_test123'}).status_code==400
    assert c.post(f'/api/codex/jobs/{id}/receipt',json={'url':URL}).status_code==200
    assert c.get('/api/codex/jobs').json()[0]['url']==URL


def test_login_failure_safe_retry_and_restart_recovery(setup,monkeypatch):
    c,e,t,calls=setup
    monkeypatch.setattr(e,'connected',lambda:False)
    id=c.post('/api/codex/preview',json={'ids':[t['id']]}).json()['id']
    c.post(f'/api/codex/jobs/{id}/send',json={});e.once()
    assert c.get('/api/codex/jobs').json()[0]['status']=='연결 필요'
    assert not any(a[:2]==['cloud','exec'] for a,_ in calls)
    monkeypatch.setattr(e,'connected',lambda:True)
    c.post(f'/api/codex/jobs/{id}/send',json={})
    with e.store.connect() as db:db.execute("UPDATE codex_jobs SET status='전송 중',updated=? WHERE id=?",(time.time()-301,id))
    e.once()
    assert c.get('/api/codex/jobs').json()[0]['status']=='접수 확인 필요'
    c.post('/api/logout',json={})
    assert c.get('/api/codex/jobs').status_code==401
    assert c.post('/api/codex/login',json={}).status_code==401


def test_payload_is_sent_via_stdin_and_no_shell_or_api_key(setup,monkeypatch,tmp_path):
    _,e,_,_=setup
    binary=tmp_path/'codex';binary.write_text('fixture')
    monkeypatch.setenv('SCHEDULER_CODEX_BINARY',str(binary))
    monkeypatch.setenv('OPENAI_API_KEY','do-not-inherit')
    monkeypatch.setenv('CODEX_API_KEY','do-not-inherit')
    seen={}
    def process(command,**kwargs):
        seen.update(command=command,**kwargs)
        return SimpleNamespace(returncode=0,stdout='',stderr='')
    monkeypatch.setattr('backend.delivery.subprocess.run',process)
    type(e).run(e,['cloud','exec','--env','scheduler-test','-'],'$(not-a-command)')
    assert seen['shell'] is False and seen['input']=='$(not-a-command)'
    assert '$(not-a-command)' not in seen['command']
    assert 'OPENAI_API_KEY' not in seen['env'] and 'CODEX_API_KEY' not in seen['env']
    assert 'forced_login_method="chatgpt"' in seen['command']


@pytest.mark.parametrize('stderr,code',[
 ("environment 'private-name' not found; run `codex cloud`",'CODEX-ENV-NOT-FOUND'),
 ('no cloud environments are available for this workspace','CODEX-NO-ENV'),
 ("environment label 'secret' is ambiguous",'CODEX-ENV-AMBIGUOUS'),
 ('403 Forbidden private-token','CODEX-403'),
 ('401 Unauthorized private-token','CODEX-AUTH'),
 ('invalid peer certificate: UnknownIssuer private-token','CODEX-TLS'),
 ('request timed out private-token','CODEX-TIMEOUT'),
 ('DNS error private-token','CODEX-DNS'),
 ('<html>private-token</html>','CODEX-HTML'),
 ('unexpected private-token','CODEX-CLI'),
])
def test_connection_errors_preserve_stage_without_exposing_cli_output(setup,monkeypatch,stderr,code):
    c,e,_,_=setup
    original=e.run
    def run(args,text=None,timeout=30):
        if args[:2]==['cloud','list']:return SimpleNamespace(returncode=1,stdout='',stderr=stderr)
        return original(args,text,timeout)
    monkeypatch.setattr(e,'run',run)
    result=c.post('/api/codex/check',json={}).json()
    assert not result['ok'] and result['code']==code
    assert '로그인 확인됨' in result['stage']
    assert 'private-token' not in str(result) and 'private-name' not in str(result)


def test_discovery_uses_unfiltered_task_list_and_does_not_send_feedback(setup,monkeypatch):
    c,e,_,calls=setup
    original=e.run
    def run(args,text=None,timeout=30):
        if args[:2]==['cloud','list']:
            assert '--env' not in args and text is None
            return SimpleNamespace(returncode=0,stdout=json.dumps({'tasks':[
                {'environment_id':'env_real','environment_label':'personal_scheduler'},
                {'environment_id':'env_real','environment_label':'personal_scheduler'},
                {'environment_id':None,'title':'private task title'},
            ]}),stderr='')
        return original(args,text,timeout)
    monkeypatch.setattr(e,'run',run)
    before=e.settings()
    result=c.post('/api/codex/environments',json={}).json()
    assert result['ok'] and result['environments']==[{'id':'env_real','name':'personal_scheduler'}]
    assert 'private task title' not in str(result)
    assert e.settings()==before
    assert not any(args[:2]==['cloud','exec'] for args,_ in calls)
    c.post('/api/logout',json={})
    assert c.post('/api/codex/environments',json={}).status_code==401
    assert c.post('/api/codex/connection',json={}).status_code==401


@pytest.mark.parametrize('tasks,state',[
    ([], 'empty'),
    ([{'title':'PRIVATE-TITLE','environment_id':'private-other'}], 'tasks-found'),
    ([{'environment_label':'SCHEDULER-TEST','title':'PRIVATE-TITLE'}], 'target-found'),
    ([{'environment_id':'scheduler-test','title':'PRIVATE-TITLE'}], 'target-found'),
])
def test_empty_environment_catalog_runs_one_read_only_diagnostic(setup,monkeypatch,tasks,state):
    c,e,_,_=setup
    calls=[]
    def run(args,text=None,timeout=30):
        calls.append(args)
        assert text is None
        if args==['login','status']:
            return SimpleNamespace(returncode=0,stdout='',stderr='Logged in using ChatGPT')
        assert args[:2]==['cloud','list']
        if '--env' in args:
            return SimpleNamespace(returncode=1,stdout='',stderr='no cloud environments are available for this workspace')
        return SimpleNamespace(returncode=0,stdout=json.dumps({'tasks':tasks}),stderr='')
    monkeypatch.setattr(e,'run',run)
    before=e.settings()
    result=c.post('/api/codex/check',json={}).json()
    assert result['ok'] is False and result['code']=='CODEX-NO-ENV'
    assert result['task_check']=={'state':state,'count':len(tasks)}
    assert '작업 목록 조회 성공' in result['message']
    assert 'PRIVATE-TITLE' not in str(result) and 'private-other' not in str(result)
    assert len(calls)==3 and '--env' in calls[1] and '--env' not in calls[2]
    assert e.settings()==before and c.get('/api/codex/jobs').json()==[]


@pytest.mark.parametrize('failure,code',[
    ('403 Forbidden PRIVATE-TOKEN', 'CODEX-403'),
    ('not-json PRIVATE-TOKEN', 'CODEX-CLI'),
    ('timeout', 'CODEX-TIMEOUT'),
])
def test_secondary_diagnostic_failure_preserves_original_error(setup,monkeypatch,failure,code):
    c,e,_,_=setup
    original=e.run
    calls=[]
    def run(args,text=None,timeout=30):
        calls.append(args)
        if args[:2]!=['cloud','list']:return original(args,text,timeout)
        if '--env' in args:
            return SimpleNamespace(returncode=1,stdout='',stderr='no cloud environments are available for this workspace')
        if failure=='timeout':raise subprocess.TimeoutExpired('PRIVATE-TOKEN',timeout)
        return SimpleNamespace(returncode=1,stdout='',stderr=failure)
    monkeypatch.setattr(e,'run',run)
    result=c.post('/api/codex/check',json={}).json()
    assert result['ok'] is False and result['code']=='CODEX-NO-ENV'
    assert result['task_check']=={'state':'failed','code':code}
    assert 'PRIVATE-TOKEN' not in str(result)
    assert len(calls)==3
