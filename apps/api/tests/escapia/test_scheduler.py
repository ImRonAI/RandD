"""Scheduler: per-resource error isolation and interval loop."""

from __future__ import annotations

import httpx

from strqc_api.escapia.scheduler import run_forever, run_sync_cycle

from .conftest import PMC_ID, make_client, token_response


def token_only(request: httpx.Request) -> httpx.Response:
    if request.url.path.endswith("/hsapi/auth/token"):
        return token_response()
    raise AssertionError(f"unexpected path {request.url.path}")


async def test_one_failing_job_does_not_stop_the_others(db):
    calls: list[str] = []

    async def ok_job(conn, client, pmc_id):
        calls.append("ok")
        return "fine"

    async def boom_job(conn, client, pmc_id):
        calls.append("boom")
        raise RuntimeError("escapia is down")

    async def also_ok(conn, client, pmc_id):
        calls.append("also_ok")
        return 3

    jobs = {"a": ok_job, "b": boom_job, "c": also_ok}
    async with make_client(token_only) as client:
        cycle = await run_sync_cycle(db, client, PMC_ID, jobs=jobs)

    assert calls == ["ok", "boom", "also_ok"]  # c ran despite b failing
    assert cycle.results == {"a": "fine", "c": 3}
    assert "RuntimeError" in cycle.errors["b"]
    assert not cycle.ok


async def test_run_forever_cycles_with_interval_sleep(db):
    runs: list[int] = []
    sleeps: list[float] = []

    async def counting_job(conn, client, pmc_id):
        runs.append(1)
        return len(runs)

    async def record_sleep(delay: float) -> None:
        sleeps.append(delay)

    async with make_client(token_only) as client:
        history = await run_forever(
            db, client, PMC_ID,
            jobs={"count": counting_job},
            interval_seconds=60.0,
            max_cycles=3,
            sleep=record_sleep,
        )

    assert len(history) == 3
    assert len(runs) == 3
    assert sleeps == [60.0, 60.0]  # sleeps between cycles, not after the last
    assert all(cycle.ok for cycle in history)
