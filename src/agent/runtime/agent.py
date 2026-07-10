"""
Order Reprocessing Agent — real Strands SDK agent loop.

Replaces the previous placeholder (a Dockerfile with no agent logic, only
present to satisfy CDK's `AgentRuntimeArtifact.from_asset()` requirement —
see agent_orchestration.py's comment and every unit's code-summary.md
"known gaps" section since Unit 2).

Entrypoint payload shape: matches exactly what
order_placement_service/runtime_invoker.py's invoke_runtime() sends as the
InvokeAgentRuntime `payload` — the EventBridge event's `detail` field:
    {"order_id": "...", "status": "FAILED",
     "failed_subscriptions": [{"subscription_id": "...", "scenario": "...",
                                "is_non_fetchable": bool}, ...]}

Per agent_config.py's SYSTEM_PROMPT, the agent itself is responsible for
calling GetOrderDetails to fetch full order context — this entrypoint's job
is only to construct the initial user-turn prompt describing what changed,
not to pre-fetch data on the agent's behalf (that would duplicate
GetOrderDetails' purpose and violate the system prompt's step 1).
"""

from __future__ import annotations

import json
import os
from typing import Any

from bedrock_agentcore import BedrockAgentCoreApp
from strands import Agent
from strands.models import BedrockModel

from agent_config import RUNTIME_CONFIG, SYSTEM_PROMPT
from gateway_client import get_gateway_client

app = BedrockAgentCoreApp()


def _build_initial_prompt(payload: dict[str, Any]) -> str:
    """Constructs the user-turn prompt from the OrderStatusChanged event
    detail, per BR-24-BR-30's event shape (domain-entities.md)."""
    order_id = payload["order_id"]
    failed_subscriptions = payload.get("failed_subscriptions", [])

    lines = [
        f"Order {order_id} has changed status to FAILED.",
        "The following subscription item(s) reported a failure:",
    ]
    for fs in failed_subscriptions:
        lines.append(
            f"- subscription_id={fs.get('subscription_id')}, "
            f"scenario={fs.get('scenario')}, "
            f"is_non_fetchable={fs.get('is_non_fetchable')}"
        )
    lines.append(
        f"\nBegin by calling GetOrderDetails with order_id={order_id!r} to get "
        f"the full current state of the order and all its subscription items, "
        f"then follow your standard decision sequence."
    )
    return "\n".join(lines)


@app.entrypoint
def invoke(payload: dict[str, Any], context: Any = None) -> dict[str, Any]:
    """AgentCore Runtime entrypoint. `payload` is the EventBridge event
    `detail` dict forwarded by runtime_invoker.py's invoke_agent_runtime()
    call. Returns a summary dict (not streamed — this agent's flow is a
    bounded, deterministic tool-chaining sequence per the system prompt,
    not an open-ended conversational session, so a single synchronous
    response is the right shape rather than streaming)."""
    model = BedrockModel(model_id=os.environ.get("MODEL_ID", RUNTIME_CONFIG["model_id"]))

    with get_gateway_client() as gateway_client:
        tools = gateway_client.list_tools_sync()

        agent = Agent(
            model=model,
            system_prompt=SYSTEM_PROMPT,
            tools=tools,
        )

        prompt = _build_initial_prompt(payload)
        result = agent(prompt)

    return {
        "order_id": payload.get("order_id"),
        "agent_response": str(result),
    }


def main() -> None:
    app.run(host="0.0.0.0", port=8080)


if __name__ == "__main__":
    main()
