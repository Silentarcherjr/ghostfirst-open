import asyncio
import httpx
import pytest
from mcp.client import Client
from mcp_types import ElicitResult
from ghostfirst_mcp.server import build_server
from ghostfirst_mcp.inbox import Inbox
from test_server import fake_api, PHISHING_SCAN

pytestmark = pytest.mark.anyio
@pytest.fixture
def anyio_backend(): return 'asyncio'

async def finish(client, ack):
    out = ack.structured_content
    while out['status'] == 'checking':
        await asyncio.sleep(.01)
        out = (await client.call_tool('get_check_result', {'job_id':out['job_id']})).structured_content
    return out

async def test_shared_link_has_no_url_argument_is_isolated_and_remembers_only_host():
    seen=[]
    server=build_server(fake_api([httpx.Response(200,json=PHISHING_SCAN)]*2, seen))
    async with Client(server,mode='legacy') as c, Client(server,mode='legacy') as other:
        tool=next(t for t in (await c.list_tools()).tools if t.name=='check_shared_link')
        assert not tool.input_schema.get('properties')
        await c.call_tool('share_link', {'url':'https://a.example/'})
        assert not seen
        assert (await other.call_tool('check_shared_link',{})).structured_content['error_code']=='no_shared_link'
        first=await finish(c, await c.call_tool('check_shared_link',{}))
        second=await finish(c, await c.call_tool('check_shared_link',{}))
        assert not first['checked_earlier_today'] and second['checked_earlier_today']
        assert second['history_note'].startswith('You checked this site earlier today.')
        assert all(v['url']=='https://a.example/' for v in seen)

async def test_shared_sensitive_link_cannot_bypass_human_and_consent_snapshots_url():
    seen=[]; holder={}
    async def human(params, context):
        assert not seen
        await holder['client'].call_tool('share_link',{'url':'https://different.example/'})
        return ElicitResult(action='accept',content={'visit_anyway':True})
    server=build_server(fake_api([httpx.Response(200,json=PHISHING_SCAN)],seen))
    async with Client(server,mode='legacy',elicitation_callback=human) as c:
        holder['client']=c
        await c.call_tool('share_link',{'url':'https://a.example/reset?token=abc123'})
        out=await finish(c, await c.call_tool('check_shared_link',{}))
        assert out['status']=='checked'
        assert seen[0]['url']=='https://a.example/reset?token=abc123' and seen[0]['confirm_sensitive_link']
    async with Client(server,mode='legacy') as c:
        await c.call_tool('share_link',{'url':'https://a.example/reset?token=abc123'})
        assert (await c.call_tool('check_shared_link',{})).structured_content['status']=='needs_human_confirmation'
        assert len(seen)==1

async def test_inbox_ttl_replaces_and_removes_memory(monkeypatch):
    import ghostfirst_mcp.inbox as mod
    monkeypatch.setattr(mod,'INBOX_TTL',.02)
    monkeypatch.setattr(mod,'HISTORY_TTL',.02)
    inbox=Inbox()
    assert not inbox.share('file:///etc/passwd')
    assert not inbox.share('https://user:secret@example.com/')
    assert inbox.share('https://a.example/') and inbox.share('https://b.example/')
    assert inbox.latest()=='https://b.example/'
    assert not inbox.remember('b.example') and inbox.remember('b.example')
    await asyncio.sleep(.05)
    assert inbox.url is None and not inbox.history
    inbox.clear()
