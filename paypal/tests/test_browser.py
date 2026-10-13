"""Optional real Chromium regression; all provider requests are local mocks."""
import os
import socket
import subprocess
import sys
import time
from urllib.request import urlopen
import pytest
from playwright.sync_api import sync_playwright

pytestmark=pytest.mark.skipif(os.environ.get('GHOST_CHECKOUT_BROWSER_TESTS')!='1',reason='Opt-in local Chromium test; no browser needed for offline chat.')


@pytest.fixture(scope='module')
def browser_url():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    process=subprocess.Popen([sys.executable,'-m','ghost_checkout.demo','--port',str(port)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,env={**os.environ,'GHOST_CHECKOUT_MODE':'offline'})
    base=f'http://127.0.0.1:{port}'
    try:
        for _ in range(100):
            try:
                with urlopen(base,timeout=.2) as response:
                    if response.status==200: break
            except Exception: time.sleep(.05)
        else: raise AssertionError('offline UI did not start')
        yield base
    finally:
        process.terminate()
        try: process.wait(timeout=10)
        except subprocess.TimeoutExpired: process.kill();process.wait()


@pytest.mark.parametrize('store,proceed,expected',[
    ('flash-sale',True,'captured'),('flash-sale',False,'declined'),
    ('corner-bakery',True,'captured'),('riverside-deals',False,'refused'),
])
def test_phone_browser_mock_flow(browser_url,store,proceed,expected):
    with sync_playwright() as pw:
        options={'headless':True}
        if os.environ.get('GHOST_CHECKOUT_CHROMIUM'): options['executable_path']=os.environ['GHOST_CHECKOUT_CHROMIUM']
        browser=pw.chromium.launch(**options)
        try:
            page=browser.new_page(viewport={'width':390,'height':844})
            external=[];errors=[]
            page.on('pageerror',lambda error:errors.append(str(error)))
            def guard(route):
                if route.request.url.startswith(browser_url+'/'): route.continue_()
                else: external.append('external_request');route.abort()
            page.route('**/*',guard)
            page.goto(browser_url+'/');page.locator('#store').select_option(store)
            page.get_by_role('button',name='Ask the assistant to check and buy').click()
            if store=='flash-sale':
                page.get_by_role('button',name='Continue with this observed merchant' if proceed else 'Decline',exact=True).click()
            if expected=='captured':
                page.get_by_role('button',name='Open simulated PayPal approval').click()
                page.get_by_role('button',name='Approve mock payment',exact=True).click()
                page.get_by_text('Mock capture verified. No real payment.',exact=True).wait_for()
            else:
                message='Checkout cannot proceed. Review the evidence.' if expected=='refused' else 'The operation stopped. Review the error.'
                page.get_by_text(message,exact=True).wait_for()
                assert not page.locator('#pay').is_visible()
            page.get_by_text('Developer · MCP traffic',exact=True).click()
            trace=page.locator('#traffic').inner_text()
            assert 'INJECTED_ACCOUNT_X' not in trace and 'DEMO_CLAIMED_MERCHANT' not in trace
            if expected=='refused':
                assert 'start_checkout' not in trace and 'complete_checkout' not in trace
            if expected=='captured':
                merchant='DEMO_OBSERVED_MERCHANT' if store=='flash-sale' else 'DEMO_BAKERY_MERCHANT'
                assert merchant in trace
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            assert not external and not errors
        finally: browser.close()
