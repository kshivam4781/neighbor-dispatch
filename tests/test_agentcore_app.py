"""
Offline, no-network verification that deploy/agentcore_app.py's Bedrock AgentCore
Runtime wrapper is wired up correctly: the /invocations and /ping routes respond,
and the entrypoint correctly refuses to run the Match Advisor in mock mode with a
clear error rather than crashing (since there is no live model to reason with).

This does NOT touch AWS -- BedrockAgentCoreApp is a local Starlette ASGI app, and
Starlette's TestClient drives it in-process. It proves the deployment wrapper's
HTTP contract works; it does not (and cannot, from this offline suite) prove a
live AWS-hosted AgentCore endpoint, which requires `agentcore launch` and real
AWS credentials -- see deploy/agentcore_app.py's module docstring.
"""
import os

import pytest

pytest.importorskip(
    "bedrock_agentcore",
    reason="optional dependency -- pip install -r requirements-agentcore.txt to exercise this test",
)
starlette_testclient = pytest.importorskip("starlette.testclient")

os.environ.setdefault("MODEL_PROVIDER", "mock")

from deploy.agentcore_app import app  # noqa: E402


@pytest.fixture
def client():
    return starlette_testclient.TestClient(app)


def test_ping_route_responds(client):
    response = client.get("/ping")
    assert response.status_code == 200


def test_invocations_requires_prompt(client):
    response = client.post("/invocations", json={})
    assert response.status_code == 200
    assert "error" in response.json()


def test_invocations_refuses_mock_mode_with_clear_error(client):
    response = client.post("/invocations", json={"prompt": "Why hasn't Maria's need been matched?"})
    assert response.status_code == 200
    body = response.json()
    assert "error" in body
    assert "MODEL_PROVIDER" in body["error"]
