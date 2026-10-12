"""Session-only shared URL and minimal host history. No disk or account state."""
import asyncio
from collections import deque
from datetime import datetime, timezone
import time
from urllib.parse import urlsplit

INBOX_TTL = 900
HISTORY_TTL = 24 * 60 * 60

class Inbox:
    def __init__(self):
        self.url = None
        self.expires = 0
        self.history = deque(maxlen=10)
        self.timer = None
        self.history_timer = None

    def share(self, url):
        if len(url) > 4096:
            return False
        try:
            parsed = urlsplit(url)
            if parsed.scheme not in {'https', 'http'} or not parsed.hostname or parsed.username or parsed.password:
                return False
        except ValueError:
            return False
        if self.timer:
            self.timer.cancel()
        self.timer = asyncio.get_running_loop().call_later(INBOX_TTL, self.expire)
        self.url = url
        self.expires = time.monotonic() + INBOX_TTL
        return True

    def expire(self):
        self.url = None

    def prune_history(self):
        now = time.monotonic()
        while self.history and now - self.history[0][1] >= HISTORY_TTL:
            self.history.popleft()
        if self.history:
            self.history_timer = asyncio.get_running_loop().call_later(
                max(.001, HISTORY_TTL - (now - self.history[0][1])), self.prune_history)

    def latest(self):
        if time.monotonic() >= self.expires:
            self.url = None
        return self.url

    def remember(self, host):
        now = time.monotonic(); day = datetime.now(timezone.utc).date()
        while self.history and now - self.history[0][1] >= HISTORY_TTL:
            self.history.popleft()
        earlier = any(h == host and d == day for h, _, d in self.history)
        if host:
            self.history.append((host, now, day))
            if self.history_timer:
                self.history_timer.cancel()
            self.prune_history()
        return earlier

    def clear(self):
        self.url = None; self.history.clear()
        for timer in (self.timer, self.history_timer):
            if timer:
                timer.cancel()
