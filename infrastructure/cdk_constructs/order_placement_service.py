"""
OrderPlacementServiceConstruct — CDK construct for Unit 3's 2 Lambdas
(order placement, ambient activity), the EventBridge Scheduler, and completing
Unit 2's previously-unwired EventBridge rule target.

Per infrastructure-design.md's Service Mapping and "Completing Unit 2's
EventBridge Rule Target" section.
"""

from __future__ import annotations

from pathlib import Path

from aws_cdk import Duration
from aws_cdk import aws_events as events
from aws_cdk import aws_events_targets as targets
from aws_cdk import aws_lambda as _lambda
from aws_cdk import aws_scheduler as scheduler
from aws_cdk import aws_iam as iam
from constructs import Construct

from infrastructure.cdk_constructs.agent_orchestration import AgentOrchestrationConstruct
from infrastructure.cdk_constructs.mock_backend_data_layer import MockBackendDataLayerConstruct
from infrastructure.cdk_constructs.tagging import apply_standard_tags

SRC_ROOT = Path(__file__).parent.parent.parent / "src"


class OrderPlacementServiceConstruct(Construct):
    """Owns: order placement Lambda, ambient activity Lambda, EventBridge
    Scheduler. Also completes Unit 2's EventBridge rule target (per
    infrastructure-design.md), since this unit owns the Order Placement →
    EventBridge → Agent hand-off boundary (services.md's Service 2)."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        mock_backend_layer: MockBackendDataLayerConstruct,
        agent_orchestration: AgentOrchestrationConstruct,
        operating_mode: str = "REALISTIC",
        ambient_activity_interval_minutes: int = 1,
        environment: str = "Demo",
    ) -> None:
        super().__init__(scope, construct_id)

        apply_standard_tags(self, component="order-placement-service", environment=environment)

        common_env = {"OPERATING_MODE": operating_mode}

        # --- Order Placement Lambda ---
        self.order_placement_fn = _lambda.Function(
            self, "OrderPlacementFunction",
            function_name="ora-order-placement-service",
            runtime=_lambda.Runtime.PYTHON_3_13,
            handler="order_placement_service.service.handler",
            code=_lambda.Code.from_asset(str(SRC_ROOT)),
            timeout=Duration.seconds(15),
            environment=common_env,
            description="Creates orders and determines Realistic/Demo Mode outcome",
        )
        mock_backend_layer.crm_orders_table.grant_read_write_data(self.order_placement_fn)
        mock_backend_layer.crm_order_subscriptions_table.grant_read_write_data(self.order_placement_fn)
        mock_backend_layer.failure_injection_engine.grant_invoke(self.order_placement_fn)
        self.order_placement_fn.add_to_role_policy(
            iam.PolicyStatement(actions=["events:PutEvents"], resources=["*"])
        )

        # --- Ambient Activity Lambda ---
        self.ambient_activity_fn = _lambda.Function(
            self, "AmbientActivityFunction",
            function_name="ora-ambient-activity-generator",
            runtime=_lambda.Runtime.PYTHON_3_13,
            handler="order_placement_service.ambient_activity.handler",
            code=_lambda.Code.from_asset(str(SRC_ROOT)),
            timeout=Duration.seconds(15),
            environment=common_env,
            description="Simulates background customer order activity (BR-31/32/33)",
        )
        mock_backend_layer.crm_orders_table.grant_read_write_data(self.ambient_activity_fn)
        mock_backend_layer.crm_order_subscriptions_table.grant_read_write_data(self.ambient_activity_fn)
        mock_backend_layer.failure_injection_engine.grant_invoke(self.ambient_activity_fn)
        self.ambient_activity_fn.add_to_role_policy(
            iam.PolicyStatement(actions=["events:PutEvents"], resources=["*"])
        )

        # --- EventBridge Scheduler: triggers Ambient Activity every N minutes (BR-31) ---
        scheduler_role = iam.Role(
            self, "AmbientActivitySchedulerRole",
            assumed_by=iam.ServicePrincipal("scheduler.amazonaws.com"),
        )
        self.ambient_activity_fn.grant_invoke(scheduler_role)

        self.ambient_activity_schedule = scheduler.CfnSchedule(
            self, "AmbientActivitySchedule",
            name="ora-ambient-activity-schedule",
            schedule_expression=f"rate({ambient_activity_interval_minutes} minute"
                                 f"{'s' if ambient_activity_interval_minutes != 1 else ''})",
            flexible_time_window=scheduler.CfnSchedule.FlexibleTimeWindowProperty(mode="OFF"),
            target=scheduler.CfnSchedule.TargetProperty(
                arn=self.ambient_activity_fn.function_arn,
                role_arn=scheduler_role.role_arn,
            ),
        )

        # --- Complete Unit 2's EventBridge rule target ---
        # Unit 2's AgentOrchestrationConstruct.trigger_rule matches
        # OrderStatusChanged events but has no target (documented as deferred
        # to this unit in Unit 2's code-summary.md gap #3). AgentCore Runtime
        # doesn't yet have a first-class EventBridge target construct at this
        # CDK version, so we bridge via a thin Lambda invoker calling
        # boto3's bedrock-agentcore InvokeAgentRuntime operation (verified
        # present via direct botocore service-model inspection).
        self.runtime_invoker_fn = _lambda.Function(
            self, "RuntimeInvokerFunction",
            function_name="ora-runtime-invoker",
            runtime=_lambda.Runtime.PYTHON_3_13,
            handler="order_placement_service.runtime_invoker.handler",
            code=_lambda.Code.from_asset(str(SRC_ROOT)),
            timeout=Duration.seconds(15),
            environment={"AGENT_RUNTIME_ARN": agent_orchestration.runtime.agent_runtime_arn},
            description="Bridges EventBridge OrderStatusChanged events to AgentCore Runtime invocation",
        )
        self.runtime_invoker_fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=["bedrock-agentcore:InvokeAgentRuntime"],
                # NOTE: real bug found via live deployment testing — scoping
                # this resource to JUST the runtime ARN (no suffix) caused
                # AccessDeniedException at actual invocation time: "runtime_invoker.py:49
                # bedrock-agentcore:InvokeAgentRuntime on resource:
                # arn:...:runtime/<id>/runtime-endpoint/DEFAULT because no
                # identity-based policy allows the action" — the real
                # authorization check is against the runtime-endpoint
                # sub-resource, not the bare runtime ARN. cdk synth/moto could
                # never catch this since it's a real IAM authorization
                # decision made by the live AgentCore service.
                resources=[
                    agent_orchestration.runtime.agent_runtime_arn,
                    f"{agent_orchestration.runtime.agent_runtime_arn}/runtime-endpoint/*",
                ],
            )
        )

        agent_orchestration.trigger_rule.add_target(
            targets.LambdaFunction(self.runtime_invoker_fn)
        )
