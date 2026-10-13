"""Own sandbox merchant request observed on a local fixture; SDK never fetched."""
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import threading
from urllib.parse import urlsplit
from .wisp_lite import ROOT,observe_fixtures
from .evidence import ClosedError


@contextmanager
def fixture_server(config):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            name=urlsplit(self.path).path.lstrip('/')
            if name not in {'corner-bakery.html','shop.css','shop.js','paypal-sdk-v6-mock.js'}:
                self.send_error(404);return
            text=ROOT.joinpath(name).read_text()
            text=text.replace('SANDBOX_CLIENT_ID',config.client_id.get_secret_value()).replace('SANDBOX_MERCHANT_ID',config.merchant_id.get_secret_value())
            if name.endswith('.html'):
                text=text.replace('paypal-sdk-v6-mock.js?','https://www.sandbox.paypal.com/sdk/js?')
                text=text.replace("script-src 'self'","script-src 'self' https://www.sandbox.paypal.com")
            self.send_response(200);self.send_header('Content-Type',{'.html':'text/html','.css':'text/css','.js':'text/javascript'}['.'+name.rsplit('.',1)[-1]])
            self.end_headers();self.wfile.write(text.encode())
        def log_message(self,*_): pass
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try: yield f'http://127.0.0.1:{server.server_port}'
    finally: server.shutdown();server.server_close();thread.join()


async def observe_corner(config):
    with fixture_server(config) as base:
        rows=await observe_fixtures(base,stores=('corner-bakery',))
    row=rows[0];provider=row['payment_provider']
    if row['http_status']!=200 or not provider or provider['merchant_ids']!=[config.merchant_id.get_secret_value()] or row['offsite_card_form']:
        raise ClosedError('sandbox_fixture_not_verified')
    # Bounded local observation only, explicitly not full hosted-engine evidence.
    return {'status':'complete','http_status':200,'payment_provider':provider,
            'verdict':{'state':'no_obvious_danger','rules':['NSB-0'],'findings':[{'code':'page.paypal_checkout_seen'}]}}


class LocalSandboxGhost:
    def __init__(self,config): self.config=config
    async def scan(self,url):
        from .demo_data import BASE
        if url!=BASE+'corner-bakery.html': raise ClosedError('sandbox_fixture_only')
        return await observe_corner(self.config)
