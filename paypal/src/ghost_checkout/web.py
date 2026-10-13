"""Loopback offline demo UI; actual MCP traffic, mock model and mock PayPal only."""
import asyncio
from contextlib import asynccontextmanager
import json
from pathlib import Path
from secrets import token_urlsafe
import time
import httpx
from starlette.applications import Starlette
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.responses import JSONResponse, Response
from starlette.routing import Route
from .store_fixtures import render_mock_store
from .agent import Purchase
from .api import RecordedGhost
from .demo_data import records, BASE
from .evidence import ClosedError
from .paypal import MockPayPal
from .server import build_server, error_output
from .session import DemoSession
from .webhooks import Webhooks, webhook_app

UI=Path(__file__).parent/'ui'
CSP="default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self'; frame-src 'none'; frame-ancestors 'none'; form-action 'none'; base-uri 'none'; object-src 'none'"


def create_app(config=None):
    model=None
    if config is None:
        paypal=MockPayPal();ghost=RecordedGhost(records())
    else:
        from .sandbox import SandboxPayPal
        from .openrouter import OpenRouterChat
        from .fixture import LocalSandboxGhost
        paypal=SandboxPayPal(config);ghost=LocalSandboxGhost(config);model=OpenRouterChat(config)
    server=build_server(ghost,paypal);sessions={}
    tasks=set()
    def track(task): tasks.add(task);task.add_done_callback(tasks.discard)

    @asynccontextmanager
    async def lifespan(app):
        yield
        await asyncio.gather(*(session['worker'].close() for session in sessions.values()),return_exceptions=True)
        for task in tuple(tasks): task.cancel()
        await asyncio.gather(*tuple(tasks),return_exceptions=True)

    def session(request):
        value=sessions.get(request.cookies.get('ghost_checkout'))
        if value is None or time.monotonic()-value['born']>=900: raise ClosedError('session_expired')
        return value

    async def data(request):
        owner=session(request)
        origin=str(request.base_url).rstrip('/')
        if request.headers.get('origin')!=origin or request.headers.get('x-csrf-token')!=owner['csrf']:
            raise ClosedError('request_not_authorized')
        if request.headers.get('content-type','').split(';')[0]!='application/json': raise ClosedError('invalid_request')
        body=bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body)>4096: raise ClosedError('invalid_request')
        value=json.loads(body)
        if not isinstance(value,dict): raise ClosedError('invalid_request')
        return owner,value

    async def start_session(request):
        for key,value in list(sessions.items()):
            if time.monotonic()-value['born']>=900:
                sessions.pop(key); await value['worker'].close()
        if len(sessions)>=16: return JSONResponse({'error_code':'server_busy'},status_code=503)
        old=request.cookies.get('ghost_checkout')
        if old in sessions:
            previous=sessions.pop(old);await previous['worker'].close()
        token=token_urlsafe(32);csrf=token_urlsafe(32);worker=DemoSession(server,paypal,model);worker.start()
        sessions[token]={'csrf':csrf,'worker':worker,'born':time.monotonic(),'result':None,'running':False}
        response=JSONResponse({'csrf':csrf,'mode':'sandbox' if config else 'offline-mock'})
        response.set_cookie('ghost_checkout',token,httponly=True,samesite='strict',max_age=900)
        return response

    async def state(request):
        owner=session(request);worker=owner['worker'];pending=worker.pending
        confirmation=None
        if pending:
            confirmation={'message':pending['message'],'merchants':worker.agent.evidence.get('observed_merchant') or []}
        return JSONResponse({'running':owner['running'],'confirmation':confirmation,'result':owner['result']})

    async def purchase(request):
        owner,body=await data(request)
        if set(body)!={'store','item','amount','currency'} or body['store'] not in {'corner-bakery','flash-sale','riverside-deals'}: raise ClosedError('invalid_request')
        if owner['running'] or owner['result'] is not None: raise ClosedError('session_busy')
        mandate=Purchase(BASE+body['store']+'.html',body['item'],body['amount'],body['currency'])
        owner['running']=True
        async def work():
            try: owner['result']=await owner['worker'].submit('purchase',mandate)
            except Exception as error: owner['result']={'status':'stopped','error':error_output(error),'answer':'The operation stopped.'}
            finally: owner['running']=False
        track(asyncio.create_task(work()))
        return JSONResponse({'status':'running'},status_code=202)

    async def confirm(request):
        owner,body=await data(request)
        if set(body)!={'proceed','merchant_id'}: raise ClosedError('invalid_request')
        owner['worker'].confirm(body['proceed'],body['merchant_id'])
        return JSONResponse({'status':'confirmation_received'})

    async def approve(request):
        owner,body=await data(request)
        if set(body)!={'order_id'}: raise ClosedError('invalid_request')
        # No LLM/tool endpoint can invoke this human-only mock UI action.
        result=await owner['worker'].submit('approve',body['order_id'])
        owner['result']=result
        return JSONResponse(result)

    async def payment_step(request):
        owner=session(request);order_id=owner['worker'].agent.order_id
        if config is None or not order_id: raise ClosedError('unknown_order')
        return JSONResponse({'approval_url':paypal.buyer_approval_url(order_id)})

    async def capture(request):
        owner,body=await data(request)
        if config is None or set(body)!={'order_id'}: raise ClosedError('invalid_request')
        result=await owner['worker'].submit('capture',body['order_id'])
        owner['result']=result
        return JSONResponse(result)

    async def static(request):
        name=request.path_params.get('name') or 'index.html'
        if name not in {'index.html','styles.css','app.js','paypal-v6-mock.js'}: return Response(status_code=404)
        body=UI.joinpath(name).read_bytes()
        if config and name=='index.html':
            body=body.replace(b'Offline Demo',b'Sandbox Demo').replace(b'NO MONEY MOVES',b'SANDBOX FUNDS ONLY').replace(b'OFFLINE',b'SANDBOX').replace(b'Offline mock model, mock PayPal, recorded synthetic GhostFirst checks. No real provider connection.',b'OpenRouter model, PayPal sandbox, local fixture observation. Buyer approval stays in PayPal.')
        return Response(body,media_type={'.html':'text/html','.css':'text/css','.js':'text/javascript'}[Path(name).suffix])

    async def shop(request):
        name=request.path_params['name']
        allowed={'corner-bakery.html','riverside-deals.html','flash-sale.html','shop.css','shop.js','paypal-sdk-v6-mock.js'}
        if name not in allowed: return Response(status_code=404)
        return Response(render_mock_store((Path(__file__).parent/'stores'/name).read_text()).encode(),media_type={'.html':'text/html','.css':'text/css','.js':'text/javascript'}[Path(name).suffix])

    def verify(request):
        payload=json.loads(request.content)
        success=payload.get('transmission_sig')=='MOCK-VALID-SIGNATURE'
        return httpx.Response(200,json={'verification_status':'SUCCESS' if success else 'FAILURE'})
    if config:
        from .webhooks import SandboxWebhooks
        hooks=SandboxWebhooks(config,paypal)
    else: hooks=Webhooks('MOCK-WEBHOOK-ID',httpx.MockTransport(verify))
    app=Starlette(lifespan=lifespan,routes=[Route('/',static),Route('/api/session',start_session),
         Route('/api/state',state),Route('/api/chat',purchase,methods=['POST']),
         Route('/api/confirm',confirm,methods=['POST']),Route('/api/mock-approve',approve,methods=['POST']),
         *webhook_app(hooks).routes,Route('/api/payment-step',payment_step),Route('/api/capture',capture,methods=['POST']),Route('/shop/{name}',shop),Route('/{name}',static)])
    app.add_middleware(TrustedHostMiddleware,allowed_hosts=['127.0.0.1','localhost','[::1]','*.app.github.dev'])
    async def boundary(request,call_next):
        try: response=await call_next(request)
        except Exception: response=JSONResponse({'status':'error','error_code':'operation_stopped'},status_code=400)
        response.headers.update({'Content-Security-Policy':CSP,'X-Content-Type-Options':'nosniff','Cache-Control':'no-store','Referrer-Policy':'no-referrer'})
        return response
    from starlette.middleware.base import BaseHTTPMiddleware
    app.add_middleware(BaseHTTPMiddleware,dispatch=boundary)
    return app


app=create_app()


def create_sandbox_app():
    from .config import runtime_config
    return create_app(runtime_config('sandbox'))
