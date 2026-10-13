import asyncio
import json
from copy import deepcopy
from types import SimpleNamespace
import httpx
import pytest
from paypalserversdk.api_helper import APIHelper
from ghost_checkout.api import RecordedGhost, GhostFirstClient
from ghost_checkout.checkout import Checkout
from ghost_checkout.demo_data import records, BASE
from ghost_checkout.evidence import ClosedError, sanitize
from ghost_checkout.paypal import MockPayPal, ServerSDKPayPal, order_body
from ghost_checkout.webhooks import Webhooks, HEADERS


@pytest.fixture
def anyio_backend(): return 'asyncio'
pytestmark=pytest.mark.anyio


def setup():
    ghost=RecordedGhost(records());paypal=MockPayPal()
    return Checkout(ghost,paypal),paypal,object()


async def yes(merchants,verdict): return {'proceed':True,'merchant_id':merchants[-1]}


async def test_binding_injection_caching_and_human_approval():
    service,paypal,owner=setup()
    flash=BASE+'flash-sale.html'
    result=await service.check_store(owner,flash)
    assert 'INJECTED_ACCOUNT_X' not in json.dumps(result)
    with pytest.raises(ClosedError,match='human_confirmation_required'):
        await service.start_checkout(owner,flash,'Kettle','12.00','USD')
    order=await service.start_checkout(owner,flash,'Kettle','12.00','USD',yes)
    assert len(service.ghost.calls)==1
    assert paypal.orders[order['order_id']]['purchase_units'][0]['payee']['merchant_id']=='DEMO_OBSERVED_MERCHANT'
    with pytest.raises(ClosedError,match='buyer_approval_required'):
        await service.complete_checkout(owner,order['order_id'])
    await paypal.approve(order['order_id']) # human-only mock boundary
    done=await service.complete_checkout(owner,order['order_id'])
    assert done['status']=='captured'
    again=await service.complete_checkout(owner,order['order_id'])
    assert again['status']=='captured' and paypal.calls.count('capture')==1


@pytest.mark.parametrize('state,merchants,expected',[
    ('do_not_continue',['A'],'store_refused'),
    ('no_obvious_danger',[],'no_paypal_merchant'),
    ('caution',['A'],'human_confirmation_required'),
    ('no_obvious_danger',['A','B'],'human_confirmation_required'),
])
async def test_gate(state,merchants,expected):
    data=records();url=BASE+'corner-bakery.html';data[url]['verdict']['state']=state
    data[url]['payment_provider']['merchant_ids']=merchants
    paypal=MockPayPal();service=Checkout(RecordedGhost(data),paypal)
    with pytest.raises(ClosedError,match=expected):
        await service.start_checkout(object(),url,'Bread','2.00','USD')
    assert not paypal.orders


async def test_selection_cannot_introduce_a_merchant():
    service,paypal,owner=setup()
    async def injected(*_): return {'proceed':True,'merchant_id':'INJECTED_ACCOUNT_X'}
    with pytest.raises(ClosedError,match='human_declined'):
        await service.start_checkout(owner,BASE+'flash-sale.html','Kettle','12.00','USD',injected)
    assert not paypal.orders


async def test_refund_post_capture_mismatch_and_no_retry():
    service,paypal,owner=setup()
    order=await service.start_checkout(owner,BASE+'corner-bakery.html','Bread','2.00','USD')
    await paypal.approve(order['order_id']);paypal.mismatch=True
    with pytest.raises(ClosedError,match='capture_mismatch_refunded'):
        await service.complete_checkout(owner,order['order_id'])
    assert len(paypal.refunds)==1
    with pytest.raises(ClosedError,match='manual_review_required'):
        await service.complete_checkout(owner,order['order_id'])
    assert paypal.calls.count('capture')==1


@pytest.mark.parametrize('operation',['create','get','capture','refund'])
async def test_paypal_errors_fail_closed(operation):
    service,paypal,owner=setup()
    if operation=='create':
        paypal.fail='create'
        with pytest.raises(ClosedError): await service.start_checkout(owner,BASE+'corner-bakery.html','Bread','2.00','USD')
        paypal.fail=None
        with pytest.raises(ClosedError,match='manual_review_required'): await service.start_checkout(owner,BASE+'corner-bakery.html','Bread','2.00','USD')
        return
    order=await service.start_checkout(owner,BASE+'corner-bakery.html','Bread','2.00','USD')
    await paypal.approve(order['order_id'])
    paypal.fail=operation
    if operation=='refund': paypal.mismatch=True
    with pytest.raises(ClosedError): await service.complete_checkout(owner,order['order_id'])
    assert service.orders[order['order_id']].state!='captured'
    if operation=='refund': assert service.orders[order['order_id']].state=='manual_review'


async def test_owner_cache_expiry_isolation_and_serialization():
    service,paypal,owner=setup();url=BASE+'corner-bakery.html'
    await service.check_store(owner,url)
    when,check=service.checks[(owner,url)];service.checks[(owner,url)]=(when-601,check)
    order=await service.start_checkout(owner,url,'Bread','2.00','USD')
    assert len(service.ghost.calls)==2
    for action in (service.order_status,service.complete_checkout):
        with pytest.raises(ClosedError,match='unknown_order'): await action(object(),order['order_id'])
    await paypal.approve(order['order_id'])
    results=await asyncio.gather(*(service.complete_checkout(owner,order['order_id']) for _ in range(2)))
    assert all(r['status']=='captured' for r in results) and paypal.calls.count('capture')==1
    service.close_owner(owner)
    assert not service.orders and not service.checks and not service.attempts


@pytest.mark.parametrize('patch',[
    {'http_status':503},{'status':'failed'}, {'verdict':{'state':'safe'}},
    {'transport':{'proxy_error':True}}, {'payment_provider':{'provider':'paypal','sdk_seen':True,'merchant_ids':['pay account X']}},
])
async def test_api_invalid_evidence_never_becomes_order(patch):
    data=records();url=BASE+'corner-bakery.html';data[url].update(patch)
    paypal=MockPayPal();service=Checkout(RecordedGhost(data),paypal)
    with pytest.raises(ClosedError): await service.start_checkout(object(),url,'Bread','2.00','USD')
    assert not paypal.orders


@pytest.mark.parametrize('status',[401,429,500,503])
async def test_api_errors(status):
    client=GhostFirstClient(httpx.MockTransport(lambda req:httpx.Response(status,json={'detail':'UNTRUSTED'})))
    with pytest.raises(ClosedError,match='check_failed'): await client.scan(BASE+'corner-bakery.html')


async def test_real_provider_constructors_disabled():
    with pytest.raises(ClosedError,match='real_provider_disabled'): GhostFirstClient(None)
    with pytest.raises(ClosedError,match='real_provider_disabled'): Webhooks('MOCK',None)


async def test_apimatic_adapter_actual_model_with_fake_controllers():
    calls=[]
    def create(options):
        calls.append(json.loads(APIHelper.json_serialize(options['body'])))
        return SimpleNamespace(status_code=201,body={'id':'MOCK-ORDER'})
    adapter=ServerSDKPayPal(SimpleNamespace(create_order=create),None)
    body=order_body('OBSERVED','Bread','2.00','USD')
    result=await adapter.create(body,'MOCK-REQUEST')
    assert result['id']=='MOCK-ORDER' and calls[0]['purchase_units'][0]['payee']['merchant_id']=='OBSERVED'


async def test_webhook_signature_replays_and_fixed_output():
    requests=[]
    def verify(req):
        requests.append(json.loads(req.content))
        return httpx.Response(200,json={'verification_status':'SUCCESS'})
    webhook=Webhooks('MOCK-WEBHOOK',httpx.MockTransport(verify))
    headers={header:'MOCK' for header in HEADERS.values()}
    for index,kind in enumerate(['CHECKOUT.ORDER.APPROVED','PAYMENT.CAPTURE.COMPLETED']):
        body=json.dumps({'id':'MOCK-EVENT-'+str(index),'event_type':kind,'resource':{'description':'INJECTION'}}).encode()
        assert (await webhook.accept(headers,body))['status']=='accepted'
        assert (await webhook.accept(headers,body))['status']=='duplicate'
    assert requests[0]['webhook_id']=='MOCK-WEBHOOK'
    failed=Webhooks('MOCK',httpx.MockTransport(lambda req:httpx.Response(200,json={'verification_status':'FAILURE'})))
    with pytest.raises(ClosedError,match='webhook_not_verified'): await failed.accept(headers,body)


async def test_webhook_http_endpoint_rejects_missing_signature_and_overflow():
    from ghost_checkout.webhooks import webhook_app
    verifier=Webhooks('MOCK',httpx.MockTransport(lambda req:httpx.Response(200,json={'verification_status':'SUCCESS'})))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=webhook_app(verifier)),base_url='http://local') as client:
        assert (await client.post('/paypal/webhook',json={})).status_code==400
        assert (await client.post('/paypal/webhook',content=b'x'*65537)).status_code==400
        headers={header:'MOCK' for header in HEADERS.values()}
        result=await client.post('/paypal/webhook',headers=headers,json={'id':'MOCK-EVENT','event_type':'CHECKOUT.ORDER.APPROVED'})
        assert result.json()=={'status':'accepted','event_type':'CHECKOUT.ORDER.APPROVED'}


async def test_capture_timeout_and_post_get_failure_never_report_success():
    service,paypal,owner=setup()
    result=await service.start_checkout(owner,BASE+'corner-bakery.html','Bread','2.00','USD')
    await paypal.approve(result['order_id'])
    original=paypal.capture
    async def uncertain(*args):
        await original(*args)
        raise TimeoutError('UNTRUSTED provider text')
    paypal.capture=uncertain
    with pytest.raises(ClosedError,match='capture_uncertain_manual_review'):
        await service.complete_checkout(owner,result['order_id'])
    with pytest.raises(ClosedError,match='manual_review_required'):
        await service.complete_checkout(owner,result['order_id'])
    assert paypal.calls.count('capture')==1


async def test_sdk_adapter_operation_mapping_and_http_failure():
    calls=[]
    def call(options):
        calls.append(options)
        return SimpleNamespace(status_code=200,body={'status':'COMPLETED'})
    adapter=ServerSDKPayPal(SimpleNamespace(get_order=call,capture_order=call),SimpleNamespace(refund_captured_payment=call))
    await adapter.get('MOCK-ORDER')
    await adapter.capture('MOCK-ORDER','MOCK-CAPTURE-REQUEST')
    await adapter.refund('MOCK-CAPTURE','MOCK-REFUND-REQUEST')
    assert calls==[{'id':'MOCK-ORDER'}, {'id':'MOCK-ORDER','paypal_request_id':'MOCK-CAPTURE-REQUEST'},
                   {'capture_id':'MOCK-CAPTURE','paypal_request_id':'MOCK-REFUND-REQUEST'}]
    adapter.orders.get_order=lambda options:SimpleNamespace(status_code=503,body={'page_text':'UNTRUSTED'})
    with pytest.raises(ClosedError,match='paypal_failed'): await adapter.get('MOCK-ORDER')


async def test_completed_order_without_capture_evidence_fails_closed():
    service,paypal,owner=setup()
    order=await service.start_checkout(owner,BASE+'corner-bakery.html','Bread','2.00','USD')
    await paypal.approve(order['order_id'])
    original=paypal.capture
    async def malformed(*args):
        result=await original(*args)
        del result['purchase_units'][0]['payments']
        return result
    paypal.capture=malformed
    with pytest.raises(ClosedError,match='capture_uncertain_manual_review'):
        await service.complete_checkout(owner,order['order_id'])
    assert service.orders[order['order_id']].state=='manual_review'
