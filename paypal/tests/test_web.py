import asyncio
import json
import httpx
import pytest
from ghost_checkout.web import create_app, CSP, UI

pytestmark=pytest.mark.anyio
@pytest.fixture
def anyio_backend(): return 'asyncio'


async def test_http_flow_confirm_and_human_payment_separate_from_model():
    app=create_app()
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://127.0.0.1') as client:
            token=(await client.get('/api/session')).json()['csrf']
            headers={'Origin':'http://127.0.0.1','X-CSRF-Token':token}
            r=await client.post('/api/chat',headers=headers,json={'store':'flash-sale','item':'Kettle','amount':'12.00','currency':'USD'})
            assert r.status_code==202
            for _ in range(100):
                state=(await client.get('/api/state')).json()
                if state['confirmation']: break
                await asyncio.sleep(.01)
            assert state['confirmation']['merchants']==['DEMO_OBSERVED_MERCHANT']
            await client.post('/api/confirm',headers=headers,json={'proceed':True,'merchant_id':'DEMO_OBSERVED_MERCHANT'})
            for _ in range(100):
                state=(await client.get('/api/state')).json()
                if not state['running']: break
                await asyncio.sleep(.01)
            assert state['result']['status']=='buyer_approval_required'
            order=state['result']['order']['order_id']
            assert 'INJECTED_ACCOUNT_X' not in json.dumps(state)
            result=await client.post('/api/mock-approve',headers=headers,json={'order_id':order})
            assert result.json()['status']=='captured'
            page=await client.get('/')
            assert page.headers['content-security-policy']==CSP
            assert 'frame-ancestors' in CSP and 'unsafe-inline' not in CSP
            assert 'HttpOnly' in (await client.get('/api/session')).headers['set-cookie']


async def test_cross_origin_and_unknown_payee_parameter_refused():
    app=create_app()
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://127.0.0.1') as client:
            csrf=(await client.get('/api/session')).json()['csrf']
            body={'store':'corner-bakery','item':'Bread','amount':'2.00','currency':'USD'}
            assert (await client.post('/api/chat',json=body)).status_code==400
            headers={'Origin':'http://evil.test','X-CSRF-Token':csrf}
            assert (await client.post('/api/chat',headers=headers,json=body)).status_code==400
            headers['Origin']='http://127.0.0.1'
            body['payee']='INJECTED'
            assert (await client.post('/api/chat',headers=headers,json=body)).status_code==400


async def test_ui_does_not_use_html_injection_sinks():
    code=UI.joinpath('app.js').read_text()+UI.joinpath('paypal-v6-mock.js').read_text()
    assert 'innerHTML' not in code and 'insertAdjacentHTML' not in code
    assert 'textContent' in code
    html=UI.joinpath('index.html').read_text()
    assert 'aria-live="polite"' in html and '<details' in html and '<label' in html


async def test_fixed_ui_color_pairs_have_wcag_aa_contrast():
    def linear(channel):
        value=int(channel,16)/255
        return value/12.92 if value<=.04045 else ((value+.055)/1.055)**2.4
    def lum(color):
        return sum(weight*linear(color[i:i+2]) for weight,i in zip((.2126,.7152,.0722),(0,2,4)))
    for foreground,background in [('193048','eaf0f5'),('193048','ffffff'),('ffffff','174a78'),('214d38','eaf0f5'),('344b60','eaf0f5')]:
        a,b=sorted((lum(foreground),lum(background)))
        assert (b+.05)/(a+.05)>=4.5


async def test_public_shop_pages_are_local_mock_assets_and_never_submit():
    app=create_app()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://127.0.0.1') as client:
        for store in ('corner-bakery','riverside-deals','flash-sale'):
            response=await client.get('/shop/'+store+'.html')
            assert response.status_code==200 and 'GHOSTFIRST DEMO' in response.text
            assert '<script' in response.text and '<script src="https://' not in response.text
            assert 'form-action \'none\'' in response.headers['content-security-policy']
        assert (await client.get('/shop/../../LICENSE')).status_code==404
