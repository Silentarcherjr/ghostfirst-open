"""Bounded, volatile jobs owned by a verified MCP connection, never a header."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from secrets import token_urlsafe
from typing import Any, Awaitable, Callable

JOB_TTL = 900
JOB_TIMEOUT = 65
# Limits on checks *running* at once. Finished results are kept for polling
# until JOB_TTL but never block new checks; past MAX_STORED the oldest
# finished results are dropped first.
MAX_JOBS = 128
MAX_SESSION_JOBS = 8
MAX_STORED = 1024


@dataclass
class Job:
    owner: Any
    task: asyncio.Task
    expiry: asyncio.TimerHandle
    result: Any = None


class Jobs:
    def __init__(self):
        self.entries: dict[str, Job] = {}

    def start(self, owner: Any, run: Callable[[], Awaitable[Any]]) -> str | None:
        running = [j for j in self.entries.values() if not j.task.done()]
        if len(running) >= MAX_JOBS or sum(j.owner is owner for j in running) >= MAX_SESSION_JOBS:
            return None
        if len(self.entries) >= MAX_STORED:
            finished = [k for k, j in self.entries.items() if j.task.done()]
            for key in finished[: len(self.entries) - MAX_STORED + 1]:
                self.remove(key)
            if len(self.entries) >= MAX_STORED:
                return None
        job_id = token_urlsafe(24)

        async def work():
            result = await run()
            if job_id in self.entries:
                self.entries[job_id].result = result

        task = asyncio.create_task(work())
        expiry = asyncio.get_running_loop().call_later(JOB_TTL, self.remove, job_id)
        self.entries[job_id] = Job(owner, task, expiry)
        return job_id

    def get(self, owner: Any, job_id: str) -> Job | None:
        job = self.entries.get(job_id)
        return job if job and job.owner is owner else None

    def remove(self, job_id: str):
        job = self.entries.pop(job_id, None)
        if job:
            job.expiry.cancel()
            if not job.task.done():
                job.task.cancel()

    async def close_owner(self, owner: Any):
        tasks = [j.task for j in self.entries.values() if j.owner is owner]
        for key in [k for k, j in self.entries.items() if j.owner is owner]:
            self.remove(key)
        await asyncio.gather(*tasks, return_exceptions=True)
