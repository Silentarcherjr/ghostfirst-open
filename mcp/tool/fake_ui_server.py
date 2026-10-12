"""Local UI test server. MockTransport guarantees zero provider calls."""
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import httpx
import uvicorn
from ghostfirst_mcp.api import GhostFirstClient
from ghostfirst_mcp.server import build_http_app

FIXTURE = {'final_url':'https://xn--pple-43d.example/', 'forms':{'password':True},
           'next_step':{'action':'deep_check'},
           'verdict':{'state':'caution','summary_code':'credentials_requested',
                      'summary_params':{'credential':'password','domain':'xn--pple-43d.example'},
                      'reasons':[{'code':'page.password_requested','severity':'medium'}]}}
def response(request):
    if request.url.path == '/v1/deep-checks':
        return httpx.Response(200,json={'verdict':{'state':'caution'},'wisps':[],
                         'comparison':{'classification':'expected_variation'}})
    return httpx.Response(200,json=FIXTURE)
uvicorn.run(build_http_app(GhostFirstClient('https://fixture.example',transport=httpx.MockTransport(response))),
            host='127.0.0.1',port=int(os.environ.get('GHOSTFIRST_TEST_PORT','8799')),log_level='error')
