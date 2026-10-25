import secrets
from test_app import item_payload, client, database
from backend.ai import Proposal

def test_undo_update_delete_conflict_and_auth(client):
    item=client.post('/api/items',json={'title':'원문','request_id':secrets.token_hex(16),'deadline':'2026-12-01'}).json()
    changed=client.put('/api/items/'+item['id'],json={**item_payload(item),'planned_date':'2026-10-25'})
    key=changed.headers['X-Scheduler-Undo']
    restored=client.post('/api/item-undo/'+key,json={})
    assert restored.status_code==200
    assert restored.json()['planned_date'] is None and restored.json()['deadline']=='2026-12-01'
    assert client.post('/api/item-undo/'+key,json={}).status_code==409
    current=restored.json()
    changed=client.put('/api/items/'+item['id'],json={**item_payload(current),'status':'완료'})
    old_key=changed.headers['X-Scheduler-Undo']
    deleted=client.request('DELETE','/api/items/'+item['id']+'?revision='+str(changed.json()['revision']),json={})
    assert client.get('/api/items').json()==[]
    assert client.post('/api/item-undo/'+old_key,json={}).status_code==409
    restored=client.post('/api/item-undo/'+deleted.headers['X-Scheduler-Undo'],json={})
    assert restored.status_code==200 and restored.json()['status']=='완료'
    assert client.post('/api/item-undo/'+old_key,json={}).status_code==409
    client.post('/api/logout',json={})
    assert client.post('/api/item-undo/'+old_key,json={}).status_code==401

def test_organize_is_preview_and_keeps_original_and_dates(client, monkeypatch):
    monkeypatch.setattr(client.app.state.chatgpt,'propose',lambda _:Proposal(reply='정리',items=[{'title':'우유 사기','category':'구매','planned_date':'2027-01-01'}]))
    result=client.post('/api/items/organize',json={'title':'내일 가게에 가서 우유를 사와야 해','description':'저지방 두 통','deadline':'2026-12-01'})
    assert result.status_code==200
    data=result.json()
    assert data['category']=='구매' and '저지방 두 통' in data['original_text']
    assert 'deadline' not in data and 'planned_date' not in data
    assert client.get('/api/items').json()==[]
