import asyncio
import httpx
import pytest
from app.heartbeat import AgentHeartbeat

@pytest.mark.asyncio
async def test_heartbeat_repeats_and_authenticates(httpx_mock):
    url = "http://agent:8765/activity/llm"
    httpx_mock.add_callback(lambda request: httpx.Response(202), method="POST", url=url, is_reusable=True)
    async with httpx.AsyncClient(timeout=1) as client:
        heartbeat = AgentHeartbeat(client, url, "secret", 0.01)
        await heartbeat.start()
        await asyncio.sleep(0.025)
        await heartbeat.stop()
    requests = httpx_mock.get_requests()
    assert len(requests) >= 2
    assert all(request.headers["authorization"] == "Bearer secret" for request in requests)

@pytest.mark.asyncio
async def test_heartbeat_disabled_without_configuration():
    async with httpx.AsyncClient(timeout=1) as client:
        heartbeat = AgentHeartbeat(client, "", "", 60)
        await heartbeat.start()
        assert heartbeat.task is None

@pytest.mark.asyncio
async def test_heartbeat_failure_is_fail_open(httpx_mock):
    url = "http://agent:8765/activity/llm"
    httpx_mock.add_response(method="POST", url=url, status_code=503)
    async with httpx.AsyncClient(timeout=1) as client:
        heartbeat = AgentHeartbeat(client, url, "secret", 60)
        await heartbeat.start()
        await asyncio.sleep(0.01)
        await heartbeat.stop()
