"""Bounded snapshot stream; reconnect for current state, not historical token deltas."""

import asyncio
import time


async def snapshots(service, job_id, token, request, duration=60, interval=1):
    deadline, previous = time.monotonic() + duration, None
    while time.monotonic() < deadline:
        if await request.is_disconnected():
            return
        try:
            job = await asyncio.to_thread(service.get, job_id, token)
            data = job.model_dump_json()
        except Exception:
            yield 'event: stream_error\ndata: {"code":"STREAM_UNAVAILABLE"}\n\n'
            return
        if data != previous:
            yield f"event: snapshot\ndata: {data}\n\n"
            previous = data
        else:
            yield ": heartbeat\n\n"
        await asyncio.sleep(interval)
