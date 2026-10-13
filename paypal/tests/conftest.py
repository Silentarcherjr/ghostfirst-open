"""The suite cannot use real provider transports, even if a key exists on the host."""
import httpx
import pytest
import requests
from ghost_checkout.evidence import ClosedError


@pytest.fixture(autouse=True)
def no_real_provider_sessions(monkeypatch):
    def blocked(*args,**kwargs): raise ClosedError('network_disabled_in_tests')
    monkeypatch.setattr(requests.Session,'request',blocked)
    original=httpx.AsyncHTTPTransport.handle_async_request
    async def local_only(transport,request):
        if request.url.host not in {'127.0.0.1','localhost','::1'}:
            raise ClosedError('network_disabled_in_tests')
        return await original(transport,request)
    monkeypatch.setattr(httpx.AsyncHTTPTransport,'handle_async_request',local_only)
    monkeypatch.setenv('GHOST_CHECKOUT_MODE','offline')
