"""
AgentOrchestrationConstruct — CDK construct for AgentCore Runtime, Gateway
(registering the 6 tool Lambdas), and the EventBridge trigger rule.

Per infrastructure-design.md's Service Mapping, agent/runtime/agent_config.py,
agent/gateway/tool_registration.py.

Note: Bedrock Guardrails for ReprocessOrder (agent/guardrails/
reprocess_order_guardrail.py) are configured via aws_cdk.aws_bedrock's
CfnGuardrail (a separate service module from aws_bedrockagentcore) — included
here for completeness of Unit 2's infrastructure footprint.

API signatures below were verified directly against the installed
aws-cdk-lib==2.261.0 package (via `inspect.signature`) before writing this
construct — not assumed from documentation alone.
"""

from __future__ import annotations

from typing import Any

from aws_cdk import aws_bedrock as bedrock
from aws_cdk import aws_bedrockagentcore as agentcore
from aws_cdk import aws_events as events
from aws_cdk import aws_iam as iam
from constructs import Construct

from agent.gateway.tool_registration import GATEWAY_CONFIG
from agent.guardrails.reprocess_order_guardrail import GUARDRAIL_CONFIG
from agent.runtime.agent_config import RUNTIME_CONFIG
from infrastructure.cdk_constructs.agent_tools import AgentToolsConstruct
from infrastructure.cdk_constructs.tagging import apply_standard_tags

_JSON_TYPE_MAP = {
    "string": agentcore.SchemaDefinitionType.STRING,
    "integer": agentcore.SchemaDefinitionType.INTEGER,
    "number": agentcore.SchemaDefinitionType.NUMBER,
    "boolean": agentcore.SchemaDefinitionType.BOOLEAN,
    "array": agentcore.SchemaDefinitionType.ARRAY,
    "object": agentcore.SchemaDefinitionType.OBJECT,
}


def _to_schema_definition(json_schema: dict[str, Any]) -> agentcore.SchemaDefinition:
    """Converts a plain JSON-Schema dict (as used in agent/gateway/tool_registration.py's
    TOOL_DEFINITIONS) into the CDK's SchemaDefinition builder shape."""
    schema_type = _JSON_TYPE_MAP[json_schema["type"]]

    properties = None
    if "properties" in json_schema:
        properties = {
            key: _to_schema_definition(value) for key, value in json_schema["properties"].items()
        }

    items = None
    if "items" in json_schema:
        items = _to_schema_definition(json_schema["items"])

    return agentcore.SchemaDefinition(
        type=schema_type,
        properties=properties,
        items=items,
        required=json_schema.get("required"),
    )


class AgentOrchestrationConstruct(Construct):
    """Owns: AgentCore Runtime, AgentCore Gateway (+ 6 GatewayTargets registering
    the tool Lambdas), Bedrock Guardrail (scoped to ReprocessOrder), and the
    EventBridge rule that triggers the Runtime on OrderStatusChanged events."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        agent_tools: AgentToolsConstruct,
        environment: str = "Demo",
    ) -> None:
        super().__init__(scope, construct_id)

        apply_standard_tags(self, component="agent", environment=environment)

        # --- AgentCore Gateway ---
        # NOTE: Gateway is created BEFORE Runtime (reordered from the original
        # construct order) because Runtime's real agent loop (agent.py, added
        # when the placeholder agent loop was replaced with a real Strands SDK
        # implementation) needs the Gateway's MCP endpoint URL injected as an
        # environment variable at Runtime creation time — this was a genuine
        # ordering gap that only became apparent once the Runtime's
        # environment_variables needed to reference gateway.gateway_url.
        self.gateway = agentcore.Gateway(
            self, "AgentGateway",
            gateway_name=GATEWAY_CONFIG["gateway_name"],
            authorizer_configuration=agentcore.IamAuthorizer(),
        )

        # --- AgentCore Runtime ---
        # Runs the real Strands Agents SDK agent loop (src/agent/runtime/agent.py),
        # connected to the Gateway above via SigV4-signed MCP over HTTP
        # (src/agent/runtime/gateway_client.py + sigv4_auth.py).
        self.runtime = agentcore.Runtime(
            self, "OrderReprocessingRuntime",
            runtime_name=RUNTIME_CONFIG["agent_name"].replace("-", "_"),
            agent_runtime_artifact=agentcore.AgentRuntimeArtifact.from_asset(
                directory="src/agent/runtime",
            ),
            description="Order Reprocessing Agent — detects, diagnoses, and resolves stuck telco orders",
            environment_variables={
                "MODEL_ID": RUNTIME_CONFIG["model_id"],
                "GATEWAY_URL": self.gateway.gateway_url,
            },
            # NOTE: tracing_enabled=True was originally set here, but disabled
            # after a real deployment failure: Runtime's tracing feature
            # auto-creates a Logs::Delivery targeting X-Ray, which requires the
            # ACCOUNT-LEVEL X-Ray trace segment destination to already be set
            # to CloudWatchLogs (via xray:UpdateTraceSegmentDestination) AND a
            # CloudWatch Logs resource policy granting xray.amazonaws.com
            # logs:PutLogEvents on the /aws/spans log group. Attempted both
            # fixes live; the resource policy was created successfully but
            # UpdateTraceSegmentDestination continued to reject it as
            # insufficient even after a propagation wait — a genuine, not-yet-
            # resolved account-level X-Ray configuration gap, tracked as a
            # known follow-up rather than blocking the rest of this
            # deployment. Observability/tracing is valuable but not required
            # for the agent's core function.
            tracing_enabled=False,
        )

        # --- Runtime execution role permissions: invoke the Gateway (real
        # agent loop's MCPClient connection, per gateway_client.py) and
        # invoke the Bedrock model (Claude Sonnet 4.6 via Global cross-region
        # inference, per agent_config.py's MODEL_ID). Verified action names
        # against real-world CDK examples (bedrock-agentcore:InvokeGateway,
        # ListTools, CallTool scoped to the gateway ARN) before writing this —
        # not guessed.
        self.runtime.add_to_role_policy(
            iam.PolicyStatement(
                actions=[
                    "bedrock-agentcore:InvokeGateway",
                    "bedrock-agentcore:ListTools",
                    "bedrock-agentcore:CallTool",
                ],
                resources=[self.gateway.gateway_arn],
            )
        )
        self.runtime.add_to_role_policy(
            iam.PolicyStatement(
                actions=["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
                resources=["*"],  # Global cross-region inference profile has no single-region ARN to scope to
            )
        )

        # --- Gateway Targets: register each of the 6 tool Lambdas as an MCP tool ---
        # NOTE: real bug found during first live deployment (not catchable via
        # cdk synth/moto — only surfaces against the real BedrockAgentCoreControl
        # service): the Gateway construct does NOT automatically grant its own
        # execution role permission to invoke the target Lambda functions.
        # Deployment failed with "Gateway execution role lacks permission to
        # invoke Lambda function ...". Fixed by explicitly granting invoke
        # permission on each tool Lambda to the Gateway's execution role
        # (self.gateway.role) before creating each GatewayTarget.
        self.gateway_targets = []
        for tool_def in GATEWAY_CONFIG["tools"]:
            lambda_fn = agent_tools.tool_functions[tool_def["lambda_construct_id"]]
            lambda_fn.grant_invoke(self.gateway.role)

            tool_definition = agentcore.ToolDefinition(
                name=tool_def["name"],
                description=tool_def["description"],
                input_schema=_to_schema_definition(tool_def["input_schema"]),
            )
            tool_schema = agentcore.ToolSchema.from_inline(schema=[tool_definition])

            target_config = agentcore.LambdaTargetConfiguration(
                lambda_function=lambda_fn,
                tool_schema=tool_schema,
            )

            gateway_target = agentcore.GatewayTarget(
                self, f"GatewayTarget{tool_def['lambda_construct_id']}",
                gateway=self.gateway,
                target_configuration=target_config,
                gateway_target_name=tool_def["name"],
                description=tool_def["description"],
            )
            self.gateway_targets.append(gateway_target)

        # --- Bedrock Guardrail (scoped to ReprocessOrder, per BR-20) ---
        self.guardrail = bedrock.CfnGuardrail(
            self, "ReprocessOrderGuardrail",
            name=GUARDRAIL_CONFIG["name"],
            description=GUARDRAIL_CONFIG["description"],
            blocked_input_messaging="This value could not be validated and was blocked before submission.",
            blocked_outputs_messaging="This value could not be validated and was blocked before submission.",
            word_policy_config=bedrock.CfnGuardrail.WordPolicyConfigProperty(
                words_config=[
                    bedrock.CfnGuardrail.WordConfigProperty(text=word)
                    for word in GUARDRAIL_CONFIG["word_policy"]["denied_words"]
                ]
            ),
        )

        # --- EventBridge Rule: triggers the Runtime on OrderStatusChanged (status=FAILED) ---
        self.trigger_rule = events.Rule(
            self, "OrderStatusChangedRule",
            rule_name="ora-order-status-changed-rule",
            event_pattern=events.EventPattern(
                source=["crm.orders"],
                detail_type=["OrderStatusChanged"],
                detail={"status": ["FAILED"]},
            ),
        )
        # NOTE: The rule's TARGET (invoking the AgentCore Runtime) is wired in
        # Unit 3's construct, which owns the EventBridge-to-Runtime hand-off
        # per services.md's Service 2 boundary (Order Placement Service fires
        # the event; this rule matches it; Unit 3 attaches the actual target
        # once the Runtime reference is available across both constructs).
