"""Hosted API boundary, transport-injected only until separately authorized E6."""
from copy import deepcopy
import httpx
from .evidence import ClosedError, store_url


class GhostFirstClient:
    def __init__(self, transport, base_url='https://ghostfirst.com'):
        if not isinstance(transport,httpx.MockTransport):
            raise ClosedError('real_provider_disabled')
        self.transport,self.base_url=transport,base_url

    async def scan(self, url):
        store_url(url)
        async with httpx.AsyncClient(base_url=self.base_url,transport=self.transport,timeout=60,follow_redirects=False,trust_env=False) as client:
            try:
                response=await client.post('/v1/scans',json={'url':url,'confirm_sensitive_link':False})
                if response.status_code!=200: raise ValueError()
                return response.json()
            except Exception: raise ClosedError('check_failed') from None


class RecordedGhost:
    def __init__(self, records):
        self.records=deepcopy(records); self.calls=[]

    async def scan(self, url):
        store_url(url);self.calls.append(url)
        if url not in self.records: raise ClosedError('unknown_demo_store')
        return deepcopy(self.records[url])
