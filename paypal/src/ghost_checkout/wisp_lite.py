"""Public fixture-only observer. No private engine imports, no live store visits."""
import asyncio
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import threading
from urllib.parse import parse_qs, urlsplit
from playwright.async_api import async_playwright
from .store_fixtures import render_mock_store

ROOT=Path(__file__).parent/'stores'
STORES=('corner-bakery','riverside-deals','flash-sale')
IDENTIFIER=re.compile(r'[A-Za-z0-9_-]{1,128}\Z')
DETECTOR="""() => {
 const inputs=[...document.querySelectorAll('input')];
 const card=inputs.some(el=>/card|credit|debit|cvv|cvc|expiry|expiration/.test([el.name,el.id,el.autocomplete].join(' ').toLowerCase()));
 const claim=document.getElementById('claimed-merchant');
 const box=claim?.getBoundingClientRect();
 return {card,claim:box?.width && box?.height ? claim.textContent.trim() : null};
}"""


def sdk_metadata(url):
    p=urlsplit(url)
    if (p.scheme!='https' or p.hostname not in {'www.paypal.com','www.sandbox.paypal.com'}
        or p.path!='/sdk/js' or p.username or p.password or p.port not in (None,443)):
        return None
    q=parse_qs(p.query,max_num_fields=30)
    merchants=[v.strip() for group in q.get('merchant-id',[]) for v in group.split(',')]
    if len(merchants)>20 or any(not IDENTIFIER.fullmatch(v) for v in merchants): merchants=[]
    clients=q.get('client-id',[])
    return {'provider':'paypal','sdk_seen':True,'client_id':clients[0] if len(clients)==1 and IDENTIFIER.fullmatch(clients[0]) else None,
            'merchant_ids':sorted(set(merchants))}


async def isolated(page):
    cdp=await page.context.new_cdp_session(page)
    try:
        frame=(await cdp.send('Page.getFrameTree'))['frameTree']['frame']['id']
        world=await cdp.send('Page.createIsolatedWorld',{'frameId':frame,'worldName':'ghost-checkout-observer'})
        response=await cdp.send('Runtime.evaluate',{'expression':'('+DETECTOR+')()',
          'contextId':world['executionContextId'],'returnByValue':True,'userGesture':False})
        if response.get('exceptionDetails'): raise ValueError('isolated_read_failed')
        return response['result']['value']
    finally: await cdp.detach()


async def observe_fixtures(base,stores=STORES):
    results=[]
    async with async_playwright() as pw:
        options={'headless':True,'args':['--disable-background-networking']}
        if os.environ.get('GHOST_CHECKOUT_CHROMIUM'): options['executable_path']=os.environ['GHOST_CHECKOUT_CHROMIUM']
        browser=await pw.chromium.launch(**options)
        try:
            for name in stores:
                context=await browser.new_context(viewport={'width':390,'height':844},accept_downloads=False,permissions=[],service_workers='block')
                page=await context.new_page();provider=None
                async def guard(route,request):
                    nonlocal provider
                    if request.frame.page is not page: await route.abort();return
                    metadata=sdk_metadata(request.url)
                    if metadata and request.resource_type=='script' and request.frame==page.main_frame:
                        provider=metadata
                        await route.fulfill(status=200,content_type='text/javascript',body=ROOT.joinpath('paypal-sdk-v6-mock.js').read_text());return
                    if request.url.startswith(base+'/'):
                        await route.continue_();return
                    await route.abort()
                await context.route('**/*',guard)
                page.on('download',lambda download:asyncio.create_task(download.cancel()))
                response=await page.goto(base+'/'+name+'.html',wait_until='domcontentloaded')
                before=await isolated(page)
                await page.wait_for_timeout(4000)
                after=await isolated(page)
                claimed=after['claim'] if isinstance(after['claim'],str) and IDENTIFIER.fullmatch(after['claim']) else None
                results.append({'fixture':name,'http_status':response.status,'payment_provider':provider,
                    'claimed_merchant_id':claimed,'offsite_card_form':bool(after['card'] and not provider),
                    'card_appeared_after_load':bool(after['card'] and not before['card']),
                    'not_full_verdict':True,'mock_sdk_fulfilled_locally':True})
                await context.close()
        finally: await browser.close()
    return results


def main():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            name=urlsplit(self.path).path.lstrip('/')
            if name not in {p.name for p in ROOT.iterdir()}: self.send_error(404);return
            text=render_mock_store(ROOT.joinpath(name).read_text())
            if name.endswith('.html'):
                text=text.replace('paypal-sdk-v6-mock.js?','https://www.paypal.com/sdk/js?')
                text=text.replace("script-src 'self'","script-src 'self' https://www.paypal.com")
            self.send_response(200);self.send_header('Content-Type',{'.html':'text/html','.css':'text/css','.js':'text/javascript'}[Path(name).suffix]);self.end_headers();self.wfile.write(text.encode())
        def log_message(self,*_): pass
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try: print(json.dumps(asyncio.run(observe_fixtures(f'http://127.0.0.1:{server.server_port}')),indent=2))
    finally: server.shutdown();server.server_close();thread.join()


if __name__ == '__main__':
    main()
