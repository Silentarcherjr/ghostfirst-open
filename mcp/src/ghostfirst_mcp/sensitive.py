"""One-time link detection (same rules as the GhostFirst app and web demo).

Password-reset, sign-in, and invitation links often work only once. Opening
one in a remote browser could use it up, so the MCP server asks the human
before such a link is sent anywhere. The GhostFirst API applies the same rules
again and refuses without an explicit confirmation.
"""

from __future__ import annotations

import re
from urllib.parse import parse_qsl, unquote, urlsplit

PARAM_NAMES = frozenset(["accesstoken", "activate", "activation", "activationkey", "auth", "authcode", "authtoken", "code", "confirm", "confirmation", "confirmationcode", "idtoken", "invitation", "invite", "invitecode", "jwt", "logincode", "loginlink", "magic", "magiccode", "magiclink", "oobcode", "otp", "refreshtoken", "reset", "resettoken", "sig", "signature", "ticket", "token", "unsubscribe", "verification", "verificationcode", "verify"])
PATH_WORDS = frozenset(["activate", "activation", "auth", "confirm", "confirmation", "emaillogin", "forgotpassword", "invitation", "invite", "loginlink", "magic", "magiclink", "passwordreset", "reset", "resetpassword", "token", "unsubscribe", "verification", "verify"])
ALWAYS_ONE_TIME_PATHS = frozenset({"unsubscribe", "magiclink", "loginlink"})

_TOKENISH = re.compile(r"^[A-Za-z0-9_\-.~+/=%]{20,}$")
_JWT = re.compile(r"^eyJ[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{6,}(\.[A-Za-z0-9_-]*)?$")
_CLASSES = (re.compile(r"[a-z]"), re.compile(r"[A-Z]"), re.compile(r"[0-9]"), re.compile(r"[_\-.~+/=%]"))


def _normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def _looks_like_secret(value: str) -> bool:
    if _JWT.match(value):
        return True
    if not _TOKENISH.match(value):
        return False
    classes = sum(1 for pattern in _CLASSES if pattern.search(value))
    return classes >= 2 and not value.isalpha()


def one_time_link_indicators(url: str) -> list[str]:
    try:
        parts = urlsplit(url)
    except ValueError:
        return []
    found: set[str] = set()
    for name, value in parse_qsl(parts.query, keep_blank_values=True):
        label = name.lower()[:40]
        if _normalize(name) in PARAM_NAMES and len(value) >= 4:
            found.add(f"query:{label}")
        elif _looks_like_secret(value) and len(value) >= 32:
            found.add(f"query:{label}")
    segments = [unquote(part) for part in parts.path.split("/") if part]
    for index, segment in enumerate(segments):
        word = _normalize(segment)
        following = segments[index + 1] if index + 1 < len(segments) else ""
        if word in PATH_WORDS and (
            word in ALWAYS_ONE_TIME_PATHS or _looks_like_secret(following) or len(following) >= 16
        ):
            found.add(f"path:{word}")
        elif _looks_like_secret(segment) and len(segment) >= 32:
            found.add("path:opaque_token")
    return sorted(found)
