"""
Standalone CDK app for synthesizing Unit 1's construct in isolation during
development/testing. The FINAL deployment uses Unit 5's single root app
composing all units' constructs together (per the corrected single-deployment
model) — this file exists only to validate Unit 1's construct synthesizes
correctly before that composition happens.
"""

from __future__ import annotations

import aws_cdk as cdk

from infrastructure.cdk_constructs.mock_backend_data_layer import MockBackendDataLayerConstruct

app = cdk.App()
stack = cdk.Stack(app, "OraMockBackendDataLayerDevStack", env=cdk.Environment(region="eu-west-2"))
MockBackendDataLayerConstruct(stack, "MockBackendDataLayer")

app.synth()
