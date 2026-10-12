"""Self-contained MCP Apps resource; hashes authorize only our fixed code."""
import base64
import hashlib
from pathlib import Path
from mcp.server.extension import Extension

URI = 'ui://ghostfirst/verdict'
MIME = 'text/html;profile=mcp-app'
META = {'ui': {'csp': {'connectDomains': [], 'resourceDomains': []}, 'prefersBorder': True}}
DIR = Path(__file__).parent / 'simulator'

class Apps(Extension):
    identifier = 'io.modelcontextprotocol/ui'
    def settings(self):
        return {'mimeTypes': [MIME]}

def digest(text):
    return "'sha256-" + base64.b64encode(hashlib.sha256(text.encode()).digest()).decode() + "'"

STYLE = (DIR / 'verdict.css').read_text()
SCRIPT = (DIR / 'verdict.js').read_text()
SCRIPT_HASH = digest(SCRIPT)
STYLE_HASH = digest(STYLE)
CSP = f"default-src 'none'; script-src {SCRIPT_HASH}; style-src {STYLE_HASH}; base-uri 'none'; form-action 'none'; connect-src 'none'"
HTML = (DIR / 'verdict.html').read_text().replace('__CSP__', CSP).replace('__STYLE__', STYLE).replace('__SCRIPT__', SCRIPT)
