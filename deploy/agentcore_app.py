#!/usr/bin/env python3
"""
Bedrock AgentCore Runtime wrapper around the Neighbor Dispatch Match Advisor agent.

This wraps `build_agent()` / `ask_match_advisor()` (src/agent.py) -- the exact same
Strands Agent and five real @tool functions used by `python demo.py --ask` -- as a
Bedrock AgentCore Runtime HTTP service (`/invocations`, `/ping`), with zero changes
to the agent or tool logic itself.

Status: implemented here and verified locally and offline (see
tests/test_agentcore_app.py, which drives it through Starlette's TestClient with
no network access). It has NOT been deployed to a live AWS-hosted AgentCore
endpoint from this development environment: that step requires `agentcore
configure` / `agentcore launch` (from the `bedrock-agentcore-starter-toolkit`
package) run with real AWS credentials and network access to Bedrock AgentCore's
control-plane APIs, and this sandbox's egress policy returns 403 on outbound AWS
API calls. A team with AWS access can deploy this file for real with zero code
changes:

    pip install bedrock-agentcore bedrock-agentcore-starter-toolkit
    agentcore configure --entrypoint deploy/agentcore_app.py
    agentcore launch

Local, fully offline check that the endpoint itself is wired up correctly (no AWS,
no API key needed -- this only proves the HTTP contract; getting a real Match
Advisor answer back additionally needs MODEL_PROVIDER set to bedrock/anthropic/
openai per the README, since there is no live reasoning loop to run under the
mock/offline provider):

    pip install bedrock-agentcore
    python deploy/agentcore_app.py          # serves http://0.0.0.0:8080
    curl -s -X POST http://localhost:8080/invocations \\
      -H 'Content-Type: application/json' \\
      -d '{"prompt": "Why hasnt the need from Maria been matched yet?"}'
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bedrock_agentcore.runtime import BedrockAgentCoreApp  # noqa: E402

from src.agent import ask_match_advisor  # noqa: E402
from src.config import build_model  # noqa: E402

app = BedrockAgentCoreApp()

# Built once per process (per AgentCore microVM), matching the usual cold-start-once /
# warm-invocation-many pattern -- identical to how demo.py calls build_model() once at startup.
_model = build_model()


@app.entrypoint
def invoke(payload: dict):
    """AgentCore Runtime entrypoint.

    Expects a JSON payload of {"prompt": "<question>"} (or {"question": "..."}) and
    returns {"result": "<Match Advisor's answer>"}. This calls the exact same
    ask_match_advisor() that `demo.py --ask` calls -- no separate code path, no
    behavior divergence between the CLI and the hosted endpoint.
    """
    prompt = payload.get("prompt") or payload.get("question")
    if not prompt:
        return {"error": "payload must include a 'prompt' (or 'question') string"}

    if _model is None:
        return {
            "error": (
                "MODEL_PROVIDER=mock (or unset) -- the Match Advisor has no live model to reason "
                "with in this mode. Set MODEL_PROVIDER=bedrock/anthropic/openai (see .env.example) "
                "in this endpoint's environment before invoking it for real."
            )
        }

    try:
        answer = ask_match_advisor(prompt, model=_model)
        return {"result": answer}
    except Exception as exc:  # surfaced to the caller instead of a bare 500 with no context
        return {"error": str(exc)}


if __name__ == "__main__":
    app.run()
