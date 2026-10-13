import asyncio
from copy import deepcopy
import json
import os
from pathlib import Path
from types import SimpleNamespace
import httpx
from pydantic import SecretStr
import pytest
from ghost_checkout.config import SandboxConfig,runtime_config
from ghost_checkout.sandbox import SandboxSession,SandboxPayPal,approval_url
from ghost_checkout.openrouter import OpenRouterChat
from ghost_checkout.evidence import ClosedError
from ghost_checkout.webhooks import SandboxWebhooks


def config():
    return SandboxConfig(SecretStr('TEST_CLIENT'),SecretStr('TEST_SECRET'),SecretStr('TEST_MERCHANT'),
                         SecretStr('TEST_LLM_KEY'),'anthropic/claude-haiku-5.5')


def test_default_never_reads_secrets_and_live_modes_refuse(monkeypatch):
    monkeypatch.setenv('GHOST_CHECKOUT_MODE','offline')
    monkeypatch.setenv('GHOST_CHECKOUT_SECRETS','/no/such/file')
    assert runtime_config() is None
    with pytest.raises(ClosedError): runtime_config('live')
    assert 'TEST_SECRET' not in repr(config()) and 'TEST_LLM_KEY' not in repr(config())


def test_external_file_permissions_and_redacted_errors(tmp_path,monkeypatch):
    monkeypatch.delenv('GHOST_CHECKOUT_MODE',raising=False)
    path=tmp_path/'credentials.env'
    path.write_text('PAYPAL_CLIENT_ID=TEST_CLIENT\nPAYPAL_CLIENT_SECRET=TEST_SECRET\nSANDBOX_MERCHANT_ID=TEST_MERCHANT\nLLM_API_KEY=TEST_LLM_KEY\nLLM_MODEL=anthropic/claude-haiku-5.5\n')
    path.chmod(0o600)
    assert runtime_config('sandbox',path).redact('TEST_SECRET TEST_LLM_KEY')=='[REDACTED] [REDACTED]'
    path.chmod(0o644)
    with pytest.raises(ClosedError) as error: runtime_config('sandbox',path)
    assert str(error.value)=='invalid_sandbox_configuration'
    path.chmod(0o600)
    path.write_text(path.read_text()+'PAYPAL_BASE_URL=https://api-m.paypal.com\n')
    with pytest.raises(ClosedError): runtime_config('sandbox',path)


@pytest.mark.parametrize('url',['https://api-m.paypal.com/v2/checkout/orders','http://api-m.sandbox.paypal.com/v2/checkout/orders','https://api-m.sandbox.paypal.com.evil.test/v2/checkout/orders'])
def test_sandbox_http_refuses_other_endpoints(url):
    with SandboxSession() as session:
        assert session.trust_env is False
        with pytest.raises(ClosedError): session.get(url)


def test_approval_url_never_leaves_sandbox_or_changes_order():
    url='https://www.sandbox.paypal.com/checkoutnow?token=ORDER1'
    assert approval_url(url,'ORDER1')==url
    for bad in (url.replace('sandbox.',''),url+'&redirect_uri=https://evil.test',url.replace('ORDER1','ORDER2')):
        with pytest.raises(ClosedError): approval_url(bad,'ORDER1')


def test_sdk_constructs_sandbox_with_memory_oauth_without_fetching():
    client=SandboxPayPal(config())
    assert client.sdk.config.get_base_uri()=='https://api-m.sandbox.paypal.com'
    assert client.sdk.config.max_retries==0
    assert client.sdk.oauth_2._o_auth_token is None
    assert not hasattr(client,'approve')


@pytest.mark.anyio
async def test_openrouter_mock_transport_budget_and_secret_exclusion():
    requests=[]
    def handler(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200,json={'choices':[{'message':{'role':'assistant','content':'Review the evidence.'}}],
              'usage':{'prompt_tokens':100,'completion_tokens':10,'cost':.0001}})
    model=OpenRouterChat(config(),httpx.MockTransport(handler),max_calls=1)
    await model.complete([{'role':'user','content':'TEST_SECRET'}],[])
    assert requests[0]['messages'][0]['content']=='[REDACTED]'
    assert requests[0]['max_completion_tokens']==384 and requests[0]['parallel_tool_calls'] is False
    assert 'TEST_LLM_KEY' not in json.dumps(model.cassette)
    with pytest.raises(ClosedError,match='model_step_limit'): await model.complete([],[])


@pytest.mark.anyio
async def test_openrouter_errors_and_guard_do_not_leak_headers_or_body():
    for status,content in [(401,{'error':'TEST_LLM_KEY'}),(200,{'choices':[{'message':{'content':'Payment approved.','role':'assistant'}}],'usage':{'cost':0}})]:
        model=OpenRouterChat(config(),httpx.MockTransport(lambda request:httpx.Response(status,json=content)))
        with pytest.raises(ClosedError) as error: await model.complete([],[])
        assert 'TEST_LLM_KEY' not in str(error.value) and not model.cassette


@pytest.mark.anyio
async def test_empty_webhook_id_never_contacts_paypal():
    webhook=SandboxWebhooks(config(),object())
    with pytest.raises(ClosedError,match='webhook_not_configured'): await webhook.accept({},b'{}')


@pytest.fixture
def anyio_backend(): return 'asyncio'


def test_apimatic_optional_breakdown_preserves_amount_binding():
    from paypalserversdk.models.order import Order
    from paypalserversdk.api_helper import APIHelper
    from ghost_checkout.checkout import Checkout,BoundOrder
    body={'id':'TEST_ORDER','status':'CREATED','purchase_units':[{'payee':{'merchant_id':'TEST_MERCHANT'},'amount':{'currency_code':'USD','value':'1.00'}}]}
    serialized=json.loads(APIHelper.json_serialize(Order.from_dictionary(body)))
    service=Checkout(None,None);bound=BoundOrder(object(),'TEST_MERCHANT','1.00','USD')
    assert service.matches(serialized,bound)
    serialized['purchase_units'][0]['amount']['value']='1.01'
    assert not service.matches(serialized,bound)


@pytest.mark.anyio
async def test_pinned_sdk_full_flow_and_memory_oauth_with_mock_http(monkeypatch):
    import requests
    calls=[]
    unit={'payee':{'merchant_id':'TEST_MERCHANT'},'amount':{'currency_code':'USD','value':'1.00'}}
    created={'id':'TEST_ORDER','status':'CREATED','purchase_units':[unit],'links':[{'rel':'approve','href':'https://www.sandbox.paypal.com/checkoutnow?token=TEST_ORDER'}]}
    completed=deepcopy(created);completed['status']='COMPLETED'
    completed['purchase_units'][0]['payments']={'captures':[{'id':'TEST_CAPTURE','status':'COMPLETED','amount':{'currency_code':'USD','value':'1.00'}}]}
    def mock_send(session,method,url,**kwargs):
        calls.append((method,url,kwargs))
        if url.endswith('/oauth2/token'): body={'access_token':'TEST_TOKEN','token_type':'Bearer','expires_in':300}
        elif url.endswith('/capture'): body=completed
        elif url.endswith('/refund'): body={'id':'TEST_REFUND','status':'COMPLETED','amount':{'currency_code':'USD','value':'1.00'}}
        elif method=='GET': body=created
        else: body=created
        response=requests.Response();response.status_code=200;response._content=json.dumps(body).encode();response.headers['Content-Type']='application/json';response.url=url
        return response
    monkeypatch.setattr(requests.Session,'request',mock_send)
    client=SandboxPayPal(config())
    from ghost_checkout.paypal import order_body
    await client.create(order_body('TEST_MERCHANT','Bread','1.00','USD'),'TEST_CREATE_ID')
    await client.get('TEST_ORDER')
    await client.capture('TEST_ORDER','TEST_CAPTURE_ID')
    await client.refund('TEST_CAPTURE','TEST_REFUND_ID')
    assert sum(url.endswith('/oauth2/token') for _,url,_ in calls)==1
    assert all(url.startswith('https://api-m.sandbox.paypal.com/') and kwargs['allow_redirects'] is False for _,url,kwargs in calls)
    assert client.buyer_approval_url('TEST_ORDER').startswith('https://www.sandbox.paypal.com/')


@pytest.mark.anyio
async def test_recorded_real_openrouter_cassette_never_calls_provider():
    from ghost_checkout.agent import TOOL_SCHEMAS
    cassette=json.loads((Path(__file__).parent/'cassettes/openrouter_conversation.json').read_text())
    pending=list(cassette)
    def replay(request):
        expected=pending.pop(0);payload=json.loads(request.content)
        assert payload['messages']==expected['request']['messages'] and payload['tools']==expected['request']['tools']
        return httpx.Response(200,json={'choices':[{'message':expected['response']}],'usage':expected['usage']})
    model=OpenRouterChat(config(),httpx.MockTransport(replay))
    for entry in cassette:
        assert await model.complete(entry['request']['messages'],entry['request']['tools'])==entry['response']
    assert not pending and model.calls==6


@pytest.mark.anyio
async def test_sandbox_ui_cannot_use_mock_approval_or_skip_paypal_approval(monkeypatch):
    from ghost_checkout.paypal import MockPayPal
    from ghost_checkout.agent import MockModel
    from ghost_checkout.api import RecordedGhost
    from ghost_checkout.demo_data import records
    from ghost_checkout.web import create_app
    import ghost_checkout.sandbox as module
    import ghost_checkout.openrouter as models
    import ghost_checkout.fixture as fixtures
    class RealBoundaryFake:
        mode='sandbox'
        def __init__(self): self.delegate=MockPayPal()
        async def create(self,*args): return await self.delegate.create(*args)
        async def get(self,*args): return await self.delegate.get(*args)
        async def capture(self,*args): return await self.delegate.capture(*args)
        async def refund(self,*args): return await self.delegate.refund(*args)
        def buyer_approval_url(self,order): return 'https://www.sandbox.paypal.com/checkoutnow?token='+order
    paypal=RealBoundaryFake()
    monkeypatch.setattr(module,'SandboxPayPal',lambda cfg:paypal)
    monkeypatch.setattr(models,'OpenRouterChat',lambda cfg:MockModel())
    monkeypatch.setattr(fixtures,'LocalSandboxGhost',lambda cfg:RecordedGhost(records()))
    app=create_app(config())
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://127.0.0.1') as client:
            session=(await client.get('/api/session')).json();assert session['mode']=='sandbox'
            headers={'Origin':'http://127.0.0.1','X-CSRF-Token':session['csrf']}
            await client.post('/api/chat',headers=headers,json={'store':'corner-bakery','item':'Bread','amount':'1.00','currency':'USD'})
            for _ in range(100):
                state=(await client.get('/api/state')).json()
                if state['result']: break
                await asyncio.sleep(.01)
            order_id=state['result']['order']['order_id']
            step=(await client.get('/api/payment-step')).json()
            assert step['approval_url'].startswith('https://www.sandbox.paypal.com/')
            assert (await client.post('/api/mock-approve',headers=headers,json={'order_id':order_id})).status_code==400
            result=(await client.post('/api/capture',headers=headers,json={'order_id':order_id})).json()
            assert result['order']['error_code']=='buyer_approval_required'
            assert 'capture' not in paypal.delegate.calls
