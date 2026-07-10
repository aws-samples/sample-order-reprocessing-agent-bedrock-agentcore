"""
Standalone CDK app for synthesizing Unit 1 + Unit 2's constructs together
during development/testing. Final deployment uses Unit 5's single root app.
"""

from __future__ import annotations

import aws_cdk as cdk

from infrastructure.cdk_constructs.agent_orchestration import AgentOrchestrationConstruct
from infrastructure.cdk_constructs.agent_tools import AgentToolsConstruct
from infrastructure.cdk_constructs.mock_backend_data_layer import MockBackendDataLayerConstruct

app = cdk.App()
stack = cdk.Stack(app, "OraUnit2DevStack", env=cdk.Environment(region="eu-west-2"))

mock_backends = MockBackendDataLayerConstruct(stack, "MockBackendDataLayer")
agent_tools = AgentToolsConstruct(stack, "AgentTools", mock_backend_layer=mock_backends)
agent_orchestration = AgentOrchestrationConstruct(stack, "AgentOrchestration", agent_tools=agent_tools)

app.synth()
