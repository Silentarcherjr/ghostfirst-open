"""APIMatic sandbox only, no redirects/proxies/logging/retries or disk tokens."""
import logging
from urllib.parse import urlsplit,parse_qs
import requests
from paypalserversdk.paypal_serversdk_client import PaypalServersdkClient
from paypalserversdk.configuration import Environment
from paypalserversdk.http.auth.o_auth_2 import ClientCredentialsAuthCredentials
from .config import PAYPAL_BASE
from .evidence import ClosedError, ID
from .paypal import ServerSDKPayPal


class SandboxSession(requests.Session):
    def __init__(self):
        super().__init__();self.trust_env=False

    def request(self,method,url,**kwargs):
        p=urlsplit(url)
        if (p.scheme!='https' or p.netloc!='api-m.sandbox.paypal.com' or p.fragment
            or not p.path.startswith(('/v1/oauth2/token','/v2/checkout/orders','/v2/payments/captures','/v1/notifications/verify-webhook-signature'))):
            raise ClosedError('sandbox_endpoint_required')
        kwargs.update(allow_redirects=False,verify=True)
        return super().request(method,url,**kwargs)


class SandboxPayPal(ServerSDKPayPal):
    mode='sandbox'
    def __init__(self,config):
        if config.paypal_base!=PAYPAL_BASE: raise ClosedError('sandbox_endpoint_required')
        for name in ('paypalserversdk','apimatic_core','requests','urllib3','httpx','httpcore'):
            logging.getLogger(name).setLevel(logging.CRITICAL)
        credentials=ClientCredentialsAuthCredentials(config.client_id.get_secret_value(),config.client_secret.get_secret_value(),o_auth_clock_skew=30)
        # SDK OAuth stores/refreshes its token only in this client instance's RAM.
        self.sdk=PaypalServersdkClient(environment=Environment.SANDBOX,
            client_credentials_auth_credentials=credentials,http_client_instance=SandboxSession(),
            timeout=10,max_retries=0,logging_configuration=None)
        super().__init__(self.sdk.orders,self.sdk.payments)
        self.approval_urls={}

    async def create(self,body,request_id):
        result=await super().create(body,request_id)
        order_id=result.get('id')
        if not isinstance(order_id,str) or not ID.fullmatch(order_id): raise ClosedError('create_failed')
        links=[link.get('href') for link in result.get('links',[]) if link.get('rel') in {'approve','payer-action'}]
        if len(links)!=1: raise ClosedError('sandbox_approval_link_missing')
        self.approval_urls[order_id]=approval_url(links[0],order_id)
        return result

    def buyer_approval_url(self,order_id):
        if order_id not in self.approval_urls: raise ClosedError('unknown_order')
        return self.approval_urls[order_id]


def approval_url(value,order_id):
    try:
        p=urlsplit(value);query=parse_qs(p.query,max_num_fields=5)
        if (p.scheme!='https' or p.netloc!='www.sandbox.paypal.com' or p.path not in {'/checkoutnow','/webapps/hermes'}
            or p.fragment or query!={'token':[order_id]}): raise ValueError()
        return value
    except Exception: raise ClosedError('sandbox_approval_link_invalid') from None


async def verify_signature(client,payload):
    async with client.lock:
        def send():
            if not client.sdk.oauth_2.is_valid(): raise ClosedError('paypal_failed')
            token=client.sdk.oauth_2._o_auth_token.access_token
            with SandboxSession() as session:
                response=session.post(PAYPAL_BASE+'/v1/notifications/verify-webhook-signature',
                    headers={'Authorization':'Bearer '+token},json=payload,timeout=10)
            if response.status_code!=200: raise ClosedError('webhook_not_verified')
            return response.json()
        import asyncio
        try: return await asyncio.to_thread(send)
        except Exception: raise ClosedError('webhook_not_verified') from None
