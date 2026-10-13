"""Verification precedes dispatch; webhook claims never approve/capture an order."""
import json
import httpx
from .evidence import ClosedError, ID

EVENTS={'CHECKOUT.ORDER.APPROVED','PAYMENT.CAPTURE.COMPLETED'}
HEADERS={'transmission_id':'paypal-transmission-id','transmission_time':'paypal-transmission-time',
         'cert_url':'paypal-cert-url','auth_algo':'paypal-auth-algo','transmission_sig':'paypal-transmission-sig'}


class Webhooks:
    def __init__(self, webhook_id, transport):
        if not isinstance(transport,httpx.MockTransport): raise ClosedError('real_provider_disabled')
        self.webhook_id,self.transport=webhook_id,transport;self.seen=set()

    async def accept(self, headers, body):
        if len(body)>65536: raise ClosedError('invalid_webhook')
        try:
            event=json.loads(body)
            payload={key:headers[value] for key,value in HEADERS.items()}
            if any(not isinstance(v,str) or not 1<=len(v)<=2048 for v in payload.values()): raise ValueError()
            # Never fetch the untrusted certificate URL ourselves.
            payload.update(webhook_id=self.webhook_id,webhook_event=event)
            async with httpx.AsyncClient(transport=self.transport,timeout=10,trust_env=False,follow_redirects=False) as client:
                result=await client.post('https://api-m.sandbox.paypal.com/v1/notifications/verify-webhook-signature',json=payload)
            if result.status_code!=200 or result.json().get('verification_status')!='SUCCESS': raise ValueError()
            event_id=event['id'];kind=event['event_type']
            if not isinstance(event_id,str) or not ID.fullmatch(event_id): raise ValueError()
        except Exception: raise ClosedError('webhook_not_verified') from None
        if kind not in EVENTS: return {'status':'ignored'}
        if event_id in self.seen: return {'status':'duplicate'}
        if len(self.seen)>=1024: raise ClosedError('server_busy')
        self.seen.add(event_id)
        # Advisory notification only. Capture still requires owned binding and GET checks.
        return {'status':'accepted','event_type':kind}


def webhook_app(verifier):
    from starlette.applications import Starlette
    from starlette.routing import Route
    from starlette.responses import JSONResponse
    async def receive(request):
        try:
            body=bytearray()
            async for chunk in request.stream():
                body.extend(chunk)
                if len(body)>65536: raise ClosedError('invalid_webhook')
            return JSONResponse(await verifier.accept(request.headers,bytes(body)))
        except Exception:
            return JSONResponse({'status':'error','error_code':'webhook_not_verified'},status_code=400)
    return Starlette(routes=[Route('/paypal/webhook',receive,methods=['POST'])])
