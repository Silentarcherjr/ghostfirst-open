import asyncio
import json
import pytest
from mcp.client import Client
from mcp_types import ElicitResult
from ghost_checkout.api import RecordedGhost
from ghost_checkout.demo_data import records, BASE
from ghost_checkout.paypal import MockPayPal
from ghost_checkout.server import build_server

pytestmark=pytest.mark.anyio
@pytest.fixture
def anyio_backend(): return 'asyncio'


async def checked(client,url):
    output=(await client.call_tool('check_store',{'store_url':url})).structured_content
    for _ in range(100):
        if output['status']!='checking': return output
        await asyncio.sleep(.005)
        output=(await client.call_tool('get_check_result',{'job_id':output['job_id']})).structured_content
    raise AssertionError('job did not complete')


async def test_mcp_binding_schema_approval_and_session_close():
    paypal=MockPayPal();server=build_server(RecordedGhost(records()),paypal)
    async with Client(server,mode='legacy') as client:
        tools=await client.list_tools()
        start=next(t for t in tools.tools if t.name=='start_checkout')
        assert set(start.input_schema['properties'])=={'store_url','item','amount','currency'}
        out=await checked(client,BASE+'corner-bakery.html')
        assert out['observed_merchant']==['DEMO_BAKERY_MERCHANT']
        args={'store_url':BASE+'corner-bakery.html','item':'Bread','amount':'2.00','currency':'USD'}
        created=(await client.call_tool('start_checkout',args)).structured_content
        assert created['status']=='buyer_approval_required'
        order_id=created['order_id']
        await paypal.approve(order_id)
        complete=(await client.call_tool('complete_checkout',{'order_id':order_id})).structured_content
        assert complete['status']=='captured'
    async with Client(server,mode='legacy') as other:
        result=(await other.call_tool('order_status',{'order_id':order_id})).structured_content
        assert result['error_code']=='unknown_order'


async def test_human_elicitation_and_injection_is_not_forwarded():
    prompts=[]
    async def human(context,params):
        prompts.append(params.message)
        return ElicitResult(action='accept',content={'proceed':True,'merchant_id':'DEMO_OBSERVED_MERCHANT'})
    paypal=MockPayPal();server=build_server(RecordedGhost(records()),paypal)
    async with Client(server,mode='legacy',elicitation_callback=human) as client:
        check=await checked(client,BASE+'flash-sale.html')
        created=(await client.call_tool('start_checkout',{'store_url':BASE+'flash-sale.html','item':'Kettle','amount':'12.00','currency':'USD'})).structured_content
        assert created['observed_merchant']==['DEMO_OBSERVED_MERCHANT']
        assert prompts and 'INJECTED_ACCOUNT_X' not in json.dumps([prompts,check,created])
        assert 'DEMO_CLAIMED_MERCHANT' not in json.dumps([check,created])


async def test_no_elicitation_no_order_and_stateless_check_fallback():
    paypal=MockPayPal();server=build_server(RecordedGhost(records()),paypal)
    async with Client(server,mode='legacy') as client:
        out=(await client.call_tool('start_checkout',{'store_url':BASE+'flash-sale.html','item':'Kettle','amount':'12.00','currency':'USD'})).structured_content
        assert out['error_code']=='human_confirmation_required' and not paypal.orders
    async with Client(server) as client:
        out=(await client.call_tool('check_store',{'store_url':BASE+'corner-bakery.html'})).structured_content
        assert out['status']=='checked' # current protocol is stateless: no orphan job.
        refused=(await client.call_tool('start_checkout',{'store_url':BASE+'corner-bakery.html','item':'Bread','amount':'2.00','currency':'USD'})).structured_content
        assert refused['error_code']=='session_required'


async def test_installed_stdio_entrypoint_uses_mocks_only():
    import sys
    from mcp import StdioServerParameters
    params=StdioServerParameters(command=sys.executable,args=['-m','ghost_checkout.server'])
    async with Client(params,mode='legacy') as client:
        output=await checked(client,BASE+'corner-bakery.html')
        assert output['status']=='checked' and output['observed_merchant']==['DEMO_BAKERY_MERCHANT']
