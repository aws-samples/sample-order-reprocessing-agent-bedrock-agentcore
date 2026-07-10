"""
Order Reprocessing Agent — canonical CDK deployment app.

Composes Units 1-3's constructs into ONE stack, per the corrected
single-deployment model (unit-of-work-dependency.md's Deployment Checkpoint
Sequencing section): the entire solution's infrastructure is provisioned in
ONE `cdk deploy`, not incremental per-unit stacks.

Unit 4 (Operator UI) has no construct here — it's a local client application
per NFR-11, launched independently via `streamlit run src/ui/app.py`.

Usage:
    cdk deploy --app "python infrastructure/app.py" \\
        -c environment=Demo -c owner=<your-alias> -c costCenter=<your-cost-center>

Region/account: per NFR-1/NFR-2, deploys to eu-west-2 using the deploying
credentials' default account (no hardcoded account ID — standard CDK practice
for a samples repo other people will deploy from their own accounts).
"""

from __future__ import annotations

import aws_cdk as cdk
from aws_cdk import Tags

from infrastructure.cdk_constructs.agent_orchestration import AgentOrchestrationConstruct
from infrastructure.cdk_constructs.agent_tools import AgentToolsConstruct
from infrastructure.cdk_constructs.mock_backend_data_layer import MockBackendDataLayerConstruct
from infrastructure.cdk_constructs.order_placement_service import OrderPlacementServiceConstruct

app = cdk.App()

# --- Configurable tagging parameters (Step 2) ---
environment = app.node.try_get_context("environment") or "Demo"
owner = app.node.try_get_context("owner") or "unspecified"
cost_center = app.node.try_get_context("costCenter") or "unspecified"
workshop_attendee_id = app.node.try_get_context("workshopAttendeeId")  # optional, per NFR-3
operating_mode = app.node.try_get_context("operatingMode") or "REALISTIC"  # "REALISTIC" | "DEMO"
ambient_activity_interval = int(app.node.try_get_context("ambientActivityIntervalMinutes") or 1)

stack = cdk.Stack(
    app, "OrderReprocessingAgentStack",
    env=cdk.Environment(region="eu-west-2"),  # NFR-1; account resolves from deploying credentials
    description="Order Reprocessing Agent — AWS Samples reference implementation on Amazon Bedrock AgentCore",
)

# Apply Owner/CostCenter/Workshop-Attendee-ID at the STACK level so they
# cascade to every nested construct via CDK's tag inheritance — simpler than
# threading these three params through all 4 constructs' constructors
# individually. Environment/Project/Component/CreatedDate/ManagedBy remain
# applied per-construct (via each construct's own apply_standard_tags() call)
# since Component varies by construct; Tags.of(stack) here supplements those
# with the stack-wide values that don't vary by construct.
Tags.of(stack).add("Owner", owner)
Tags.of(stack).add("CostCenter", cost_center)
if workshop_attendee_id:
    Tags.of(stack).add("Workshop-Attendee-ID", workshop_attendee_id)

mock_backends = MockBackendDataLayerConstruct(
    stack, "MockBackendDataLayer", environment=environment,
)

agent_tools = AgentToolsConstruct(
    stack, "AgentTools", mock_backend_layer=mock_backends, environment=environment,
)

agent_orchestration = AgentOrchestrationConstruct(
    stack, "AgentOrchestration", agent_tools=agent_tools, environment=environment,
)

order_placement = OrderPlacementServiceConstruct(
    stack, "OrderPlacementService",
    mock_backend_layer=mock_backends,
    agent_orchestration=agent_orchestration,
    operating_mode=operating_mode,
    ambient_activity_interval_minutes=ambient_activity_interval,
    environment=environment,
)

app.synth()
