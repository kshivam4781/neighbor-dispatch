"""A deterministic, fully offline stand-in for a Strands `Model`.

This exists for exactly one purpose: to let `examples/match_advisor_worked_example.py`
(and `python demo.py --worked-example`) drive the REAL Match Advisor `Agent` --
the same `build_agent()` from `src/agent.py`, wired to the same five real
`@tool` functions -- through a full multi-step tool-calling loop with **zero
network access and zero API key**, so the tool-calling shape of the agent is
visible to anyone running the demo, not only to someone who has configured
`MODEL_PROVIDER=bedrock/anthropic/openai`.

This is NOT a fake "pretend the agent ran" script: the Strands `Agent` event
loop that consumes this model is the actual production event loop, and every
tool it invokes (`category_match_impl`, `geo_distance_impl`, `score_match_impl`,
`duplicate_check_impl`, `sla_check_impl`) is the actual production tool
implementation running against real `Post` data -- nothing about tool
execution is mocked. What IS scripted is which tool to call next and what the
final natural-language answer says; both are computed from the *real* return
values of those tool calls (see examples/match_advisor_worked_example.py),
never hardcoded/fabricated numbers.

The live path is still `python demo.py --ask "..."` with a real
MODEL_PROVIDER configured -- that calls a real model that decides its own
tool calls. See the README's "Swapping model providers" and "Seeing the live
agent without waiting on cloud credentials" sections.
"""

import json
from typing import Any, List, Optional, Tuple

from strands.models.model import Model


ScriptStep = Tuple[str, ...]  # ("tool", tool_name, input_dict) or ("text", answer_str)


class ScriptedAdvisorModel(Model):
    """Implements the minimal Strands `Model` interface (`stream`, `get_config`,
    `update_config`, `structured_output`) with a pre-built list of turns.

    Each `stream()` call inspects how many `toolResult` blocks have accumulated
    across the conversation so far (which the real Strands event loop appends
    after each real tool call completes) to figure out which scripted turn
    comes next -- so it works correctly no matter how many times the agent's
    event loop calls it.
    """

    def __init__(self, script: List[ScriptStep]):
        if not script or script[-1][0] != "text":
            raise ValueError("script must end with a ('text', answer) turn so the agent loop terminates")
        self._script = script
        self._config: dict = {}

    def update_config(self, **model_config: Any) -> None:
        self._config.update(model_config)

    def get_config(self) -> Any:
        return self._config

    async def structured_output(self, output_model, prompt, system_prompt=None, **kwargs):
        raise NotImplementedError(
            "ScriptedAdvisorModel is a worked-example stand-in and does not implement "
            "structured_output; it only supports the tool-calling stream() path."
        )

    @staticmethod
    def _count_tool_results(messages) -> int:
        count = 0
        for message in messages:
            for block in message.get("content", []):
                if "toolResult" in block:
                    count += 1
        return count

    async def stream(self, messages, tool_specs=None, system_prompt=None, **kwargs):
        turn_index = min(self._count_tool_results(messages), len(self._script) - 1)
        step = self._script[turn_index]
        kind = step[0]

        yield {"messageStart": {"role": "assistant"}}

        if kind == "tool":
            _, tool_name, tool_input = step
            tool_use_id = f"scripted-turn-{turn_index}"
            yield {"contentBlockStart": {"start": {"toolUse": {"toolUseId": tool_use_id, "name": tool_name}}}}
            yield {"contentBlockDelta": {"delta": {"toolUse": {"input": json.dumps(tool_input)}}}}
            yield {"contentBlockStop": {}}
            yield {"messageStop": {"stopReason": "tool_use"}}
        else:
            _, answer_text = step
            yield {"contentBlockStart": {"start": {}}}
            yield {"contentBlockDelta": {"delta": {"text": answer_text}}}
            yield {"contentBlockStop": {}}
            yield {"messageStop": {"stopReason": "end_turn"}}
