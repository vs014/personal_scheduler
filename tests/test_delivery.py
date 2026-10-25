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
