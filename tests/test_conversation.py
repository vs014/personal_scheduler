import io
import json
import time
import uuid
from urllib.parse import urlsplit, parse_qs
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from fastapi.testclient import TestClient
from backend.app import create_app
from backend.ai import Proposal, API, AUTH

@pytest.fixture
def setup(tmp_path):
 app=create_app(tmp_path/'data.sqlite3')
 c=TestClient(app,base_url='http://127.0.0.1:8000',headers={'X-Scheduler-Client':'web'})
 assert c.post('/api/setup',json={'password':'test-conversation-password'}).status_code==200
 return c,app.state.chatgpt


def request(content,revision):return {'content':content,'revision':revision,'request_id':str(uuid.uuid4())}


def test_questions_preview_approval_retry_and_restart(setup,monkeypatch):
 c,engine=setup
 responses=iter([
  Proposal(reply='어느 날인가요?',questions=[{'prompt':'주말 중 언제인가요?','options':['토요일','일요일','미정으로 두기']}]),
  Proposal(reply='시간은 미정으로 두었습니다.',items=[{'title':'친구와 저녁 식사','kind':'일정','planned_date':'2026-10-31'}]),
 ])
 monkeypatch.setattr(engine,'propose',lambda history:next(responses))
 chat=c.post('/api/conversations',json={}).json();id=chat['id']
 t=request('이번 주말 친구와 저녁 먹기로 했어',1)
 r=c.post(f'/api/conversations/{id}/turn',json=t);assert r.status_code==200
 assert c.get('/api/items').json()==[]
 assert c.post(f'/api/conversations/{id}/confirm',json={'revision':2}).status_code==400
 t=request('토요일, 시간은 미정으로 두기',2)
 r=c.post(f'/api/conversations/{id}/turn',json=t);assert r.status_code==200
 assert c.post(f'/api/conversations/{id}/turn',json=t).json()['revision']==3
 assert c.get('/api/items').json()==[]
 assert c.post(f'/api/conversations/{id}/confirm',json={'revision':2}).status_code==409
 for _ in range(2):assert c.post(f'/api/conversations/{id}/confirm',json={'revision':3}).status_code==200
 items=c.get('/api/items').json();assert len(items)==1
 assert items[0]['start_time'] is None and items[0]['deadline'] is None
 assert c.get('/api/conversations').json()[0]['status']=='저장 완료'


def test_multiple_dateless_items_cancel_and_provider_failure(setup,monkeypatch):
 c,engine=setup
 monkeypatch.setattr(engine,'propose',lambda history:Proposal(reply='두 가지를 확인해 주세요.',items=[{'title':'섬유유연제 사기'},{'title':'침대 구매하기'}]))
 id=c.post('/api/conversations',json={}).json()['id']
 c.post(f'/api/conversations/{id}/turn',json=request('두 구매할 일',1))
 c.post(f'/api/conversations/{id}/cancel',json={'revision':2})
 assert c.post(f'/api/conversations/{id}/confirm',json={'revision':3}).status_code==409
 assert c.get('/api/items').json()==[]
 id=c.post('/api/conversations',json={}).json()['id']
 def failed(_):raise HTTPException(503,'연결 실패')
 monkeypatch.setattr(engine,'propose',failed)
 assert c.post(f'/api/conversations/{id}/turn',json=request('할 일',1)).status_code==503
 assert c.get('/api/conversations').json()[0]['revision']==1
 assert c.get('/api/items').json()==[]


def test_ai_routes_require_session(setup):
 c,engine=setup
 c.post('/api/logout',json={})
 for p in ('/api/ai/status','/api/ai/models','/api/conversations'):assert c.get(p).status_code==401
 assert c.post('/api/ai/connect',json={}).status_code==401


def test_oauth_signed_identity_pkce_nonce_scopes_and_no_secret_exposure(setup,monkeypatch):
 c,engine=setup
 key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
 jwk=json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()));jwk['kid']='test-key'
 start=c.post('/api/ai/connect',json={}).json()['url'];params={k:v[0] for k,v in parse_qs(urlsplit(start).query).items()}
 assert params['client_id']=='dynamic_agent_client' and params['code_challenge_method']=='S256'
 assert params['redirect_uri']=='http://127.0.0.1:8000/auth/callback'
 host=params['ext_agent_host_id']
 token=jwt.encode({'sub':'example-account','iss':AUTH,'aud':'oaiapp_test','iat':time.time(),'exp':time.time()+3600,'nonce':params['nonce'],'email':'demo@example.invalid'},key,algorithm='RS256',headers={'kid':'test-key'})
 def fake(url,data=None,**kwargs):
  if url.endswith('openid-configuration'):return {'issuer':AUTH,'jwks_uri':AUTH+'/keys','revocation_endpoint':AUTH+'/revoke'}
  if url.endswith('/keys'):return {'keys':[jwk]}
  assert data['client_id']=='oaiapp_test' and data['code_verifier']
  return {'id_token':token,'access_token':'only-a-test-access-token','refresh_token':'only-a-test-refresh-token','scope':'chatgpt.tokens.use.direct','expires_in':3600,'token_type':'Bearer'}
 monkeypatch.setattr(engine,'json_request',fake)
 engine.callback(params['state'],'fake-code','oaiapp_test','')
 result=c.get('/api/ai/status');assert result.json()['accounts'][0]['connected']
 assert 'only-a-test' not in result.text and 'id_token' not in result.text
 with pytest.raises(HTTPException):engine.callback(params['state'],'fake-code','oaiapp_test','')
 with pytest.raises(HTTPException):engine.validate(token,'oaiapp_test','wrong-nonce')
 with pytest.raises(HTTPException):engine.validate(token,'wrong-audience',params['nonce'])
 again=c.post('/api/ai/connect',json={'client_id':'oaiapp_test'}).json()['url']
 q=parse_qs(urlsplit(again).query)
 assert q['ext_agent_host_id']==[host] and q['client_id']==['oaiapp_test']
 assert 'agent_name_hint' not in q


def test_sse_requires_completion_and_validates_payload(setup,monkeypatch):
 _,engine=setup
 monkeypatch.setattr(engine,'credentials',lambda:{'model':'account-model','access_token':'fake'})
 proposal=Proposal(reply='확인해 주세요',items=[{'title':'침대 구매하기'}]).model_dump_json()
 def response(url,data,token):
  assert url==API+'/responses' and data['store'] is False and data['stream'] is True
  assert 'max_output_tokens' not in data and 'tools' not in data
  events=[{'type':'response.output_text.delta','delta':proposal},{'type':'response.completed'}]
  return io.BytesIO(b''.join(b'data: '+json.dumps(e).encode()+b'\n\n' for e in events))
 monkeypatch.setattr(engine,'request',response)
 assert engine.propose([{'role':'user','content':'침대 구매하기'}]).items[0].planned_date is None
 monkeypatch.setattr(engine,'request',lambda *a,**k:io.BytesIO(b'data: {"type":"response.output_text.delta","delta":"{}"}\n'))
 with pytest.raises(HTTPException,match='끊겼습니다'):engine.propose([])
 monkeypatch.setattr(engine,'request',lambda *a,**k:io.BytesIO(b'data: {"type":"response.failed"}\n'))
 with pytest.raises(HTTPException):engine.propose([])


@pytest.mark.parametrize('kind,expected',[
 ('cert','TLS-CERT'),('wrapped-cert','TLS-CERT'),('dns','DNS'),
 ('timeout','TIMEOUT'),('proxy','PROXY-CONNECT'),('refused','CONNECTION-REFUSED'),
 ('tls','TLS'),('network','NETWORK'),('http401','HTTP-401'),
 ('http403','HTTP-403'),('http429','HTTP-429'),('http500','HTTP-500'),
])
def test_transport_failures_are_actionable_without_leaking_secrets(setup,monkeypatch,kind,expected):
 import socket
 import ssl
 from urllib.error import HTTPError, URLError
 _,engine=setup
 secret='private-token-must-not-appear'
 failures={
  'cert':ssl.SSLCertVerificationError(1,secret),
  'wrapped-cert':URLError(ssl.SSLCertVerificationError(1,secret)),
  'dns':URLError(socket.gaierror(-2,secret)),
  'timeout':TimeoutError(secret),
  'proxy':URLError(OSError('Tunnel connection failed: 403 Forbidden '+secret)),
  'refused':URLError(ConnectionRefusedError(secret)),
  'tls':URLError(ssl.SSLError(secret)),
  'network':URLError(OSError(secret)),
 }
 if kind.startswith('http'):
  failure=HTTPError(AUTH+'/api/accounts/oauth/token',int(kind[4:]),secret,{},io.BytesIO(secret.encode()))
 else:failure=failures[kind]
 def fail(*args,**kwargs):raise failure
 monkeypatch.setattr('backend.ai.urlopen',fail)
 with pytest.raises(HTTPException) as caught:
  engine.request(AUTH+'/api/accounts/oauth/token',{'code':secret},token=secret)
 assert f'[{expected}]' in caught.value.detail
 assert '로그인 정보 교환' in caught.value.detail
 assert secret not in caught.value.detail


def test_public_connection_check_never_sends_credentials_or_changes_data(setup,monkeypatch):
 c,engine=setup
 from urllib.error import URLError
 seen=[]
 def blocked(req,**kwargs):
  seen.append(req)
  raise URLError(OSError('Tunnel connection failed: 403 Forbidden'))
 monkeypatch.setattr('backend.ai.urlopen',blocked)
 response=c.post('/api/ai/diagnose',json={})
 assert response.status_code==200 and response.json()['ok'] is False
 assert '[PROXY-CONNECT]' in response.json()['message']
 assert '인증 서버 정보 확인' in response.json()['message']
 assert len(seen)==1 and seen[0].full_url==AUTH+'/.well-known/openid-configuration'
 assert seen[0].data is None and seen[0].get_header('Authorization') is None
 assert c.get('/api/ai/status').json()['accounts']==[]
 assert c.get('/api/items').json()==[]
 monkeypatch.setattr('backend.ai.urlopen',lambda *a,**k:io.BytesIO(json.dumps({'issuer':AUTH,'jwks_uri':AUTH+'/keys','revocation_endpoint':AUTH+'/revoke'}).encode()))
 result=c.post('/api/ai/diagnose',json={}).json()
 assert result['ok'] and '성공을 의미하지는 않습니다' in result['message']
 c.post('/api/logout',json={})
 assert c.post('/api/ai/diagnose',json={}).status_code==401


def test_callback_network_failure_redirects_with_safe_stage_and_allows_new_login(setup,monkeypatch):
 from urllib.error import URLError
 c,engine=setup
 params=parse_qs(urlsplit(c.post('/api/ai/connect',json={}).json()['url']).query)
 def blocked(*a,**k):raise URLError(TimeoutError('do-not-display-provider-secret'))
 monkeypatch.setattr('backend.ai.urlopen',blocked)
 r=c.get('/auth/callback',params={'state':params['state'][0],'code':'private-code','client_id':'test-client'},follow_redirects=False)
 assert r.status_code==303
 q=parse_qs(urlsplit(r.headers['location']).query)
 assert q['chatgpt']==['error'] and '[TIMEOUT]' in q['reason'][0]
 assert '로그인 정보 교환' in q['reason'][0]
 assert 'private-code' not in r.headers['location'] and 'provider-secret' not in r.headers['location']
 assert c.get('/api/ai/status').json()['accounts']==[]
 assert c.post('/api/ai/connect',json={}).status_code==200
