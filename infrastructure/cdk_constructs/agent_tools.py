"""
AgentToolsConstruct — CDK construct for Unit 2's 6 Lambda tools, nested within
the single overall solution deployment (per unit-of-work-dependency.md's
corrected deployment model — NOT a standalone stack).

Per infrastructure-design.md's Service Mapping and IAM grant table.
"""

from __future__ import annotations

from pathlib import Path

from aws_cdk import Duration
from aws_cdk import aws_lambda as _lambda
from constructs import Construct

from infrastructure.cdk_constructs.mock_backend_data_layer import MockBackendDataLayerConstruct
from infrastructure.cdk_constructs.tagging import apply_standard_tags

SRC_ROOT = Path(__file__).parent.parent.parent / "src"

_TOOL_DEFINITIONS = [
    ("GetOrderDetailsTool", "get_order_details", "GetOrderDetails: fetches full order + subscriptions"),
    ("ValidateOrderTool", "validate_order", "ValidateOrder: identifies missing required fields"),
    ("FetchMissingDataTool", "fetch_missing_data", "FetchMissingData: resolves a single missing field"),
    ("CheckVASEligibilityTool", "check_vas_eligibility", "CheckVASEligibility: fixable vs. business-rule block"),
    ("ReprocessOrderTool", "reprocess_order", "ReprocessOrder: resubmits corrected subscription"),
    ("EscalateToHumanTool", "escalate_to_human", "EscalateToHuman: creates ticket + notifies ops"),
]


class AgentToolsConstruct(Construct):
    """Owns: 6 tool Lambdas. Depends on Unit 1's MockBackendDataLayerConstruct
    for table/adapter references (passed in via constructor, per
    infrastructure-design.md's deployment architecture)."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        mock_backend_layer: MockBackendDataLayerConstruct,
        environment: str = "Demo",
    ) -> None:
        super().__init__(scope, construct_id)

        apply_standard_tags(self, component="agent", environment=environment)

        self.tool_functions: dict[str, _lambda.Function] = {}

        for construct_name, module_name, description in _TOOL_DEFINITIONS:
            fn = _lambda.Function(
                self, construct_name,
                function_name=f"ora-tool-{module_name.replace('_', '-')}",
                runtime=_lambda.Runtime.PYTHON_3_13,
                handler=f"agent.tools.{module_name}.handler",
                code=_lambda.Code.from_asset(str(SRC_ROOT)),
                timeout=Duration.seconds(15),
                description=description,
            )

            # Least-privilege grants per infrastructure-design.md's table:
            if construct_name == "GetOrderDetailsTool":
                mock_backend_layer.crm_orders_table.grant_read_data(fn)
                mock_backend_layer.crm_order_subscriptions_table.grant_read_data(fn)
            elif construct_name in ("ReprocessOrderTool",):
                mock_backend_layer.crm_order_subscriptions_table.grant_read_write_data(fn)
                mock_backend_layer.crm_orders_table.grant_read_write_data(fn)
            elif construct_name == "EscalateToHumanTool":
                mock_backend_layer.crm_orders_table.grant_read_write_data(fn)

            # All 6 tools write to OrderProcessingHistory via the shared History Recorder pattern.
            mock_backend_layer.order_processing_history_table.grant_write_data(fn)

            # FetchMissingData/CheckVASEligibility/ReprocessOrder invoke Unit 1's adapter Lambdas.
            if construct_name in ("FetchMissingDataTool", "CheckVASEligibilityTool", "ReprocessOrderTool"):
                for adapter_fn in mock_backend_layer.adapter_functions.values():
                    adapter_fn.grant_invoke(fn)

            self.tool_functions[construct_name] = fn
