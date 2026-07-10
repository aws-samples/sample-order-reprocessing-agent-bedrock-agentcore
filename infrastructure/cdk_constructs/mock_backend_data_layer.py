"""
MockBackendDataLayerConstruct — CDK construct for Unit 1 (Mock Backend Data
Layer), nested within the single overall solution deployment (per the
corrected deployment model in unit-of-work-dependency.md — NOT a standalone
stack).

Per infrastructure-design.md and deployment-architecture.md.
"""

from __future__ import annotations

from pathlib import Path

from aws_cdk import Duration, RemovalPolicy
from aws_cdk import aws_dynamodb as dynamodb
from aws_cdk import aws_lambda as _lambda
from constructs import Construct

from infrastructure.cdk_constructs.tagging import apply_standard_tags

SRC_ROOT = Path(__file__).parent.parent.parent / "src" / "mock_backends"

# Adapter Lambda definitions: (construct_id, module_path, description)
_DATA_SOURCE_ADAPTERS = [
    ("EsimProvisioningAdapter", "adapters.esim_provisioning", "Mock eSIM Provisioning Adapter"),
    ("ProductCatalogAdapter", "adapters.product_catalog", "Mock Product Catalog Adapter"),
    ("SimInventoryAdapter", "adapters.sim_inventory", "Mock SIM Inventory Adapter"),
    ("NumberPortabilityAdapter", "adapters.number_portability", "Mock Number Portability Adapter"),
    ("ImeiRegistryAdapter", "adapters.imei_registry", "Mock IMEI Registry Adapter"),
    ("DeviceInventoryAdapter", "adapters.device_inventory", "Mock Device Inventory/Stock Adapter"),
    ("BillingProfileAdapter", "adapters.billing_profile", "Mock Billing Profile Adapter"),
]

_PARTNER_ADAPTERS = [
    ("GvpmAdapter", "adapters.gvpm", "Mock GVPM Adapter"),
    ("NetflixAdapter", "adapters.netflix", "Mock Netflix Partner Adapter"),
    ("SpotifyAdapter", "adapters.spotify", "Mock Spotify Partner Adapter"),
    ("DisneyPlusAdapter", "adapters.disneyplus", "Mock Disney+ Partner Adapter"),
]

_SUPPORT_ADAPTERS = [
    ("TicketingAdapter", "adapters.ticketing", "Mock Ticketing Adapter (ServiceNow/Jira)"),
]


class MockBackendDataLayerConstruct(Construct):
    """Owns: 4 DynamoDB tables, 12 mock backend adapter Lambdas, the Failure
    Injection Engine Lambda. Exposes table/Lambda references for other units'
    constructs to be granted permissions against (per component-dependency.md)."""

    def __init__(self, scope: Construct, construct_id: str, *, environment: str = "Demo") -> None:
        super().__init__(scope, construct_id)

        apply_standard_tags(self, component="mock-backend", environment=environment)

        # --- DynamoDB Tables (infrastructure-design.md, NFR-6: RETAIN policy) ---

        self.crm_orders_table = dynamodb.Table(
            self, "CrmOrdersTable",
            table_name="ora-crm-orders",
            partition_key=dynamodb.Attribute(name="order_id", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.RETAIN,
        )
        self.crm_orders_table.add_global_secondary_index(
            index_name="status-updated_at-index",
            partition_key=dynamodb.Attribute(name="status", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="updated_at", type=dynamodb.AttributeType.STRING),
        )

        self.crm_order_subscriptions_table = dynamodb.Table(
            self, "CrmOrderSubscriptionsTable",
            table_name="ora-crm-order-subscriptions",
            partition_key=dynamodb.Attribute(name="order_id", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="subscription_id", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.RETAIN,
        )

        self.order_processing_history_table = dynamodb.Table(
            self, "OrderProcessingHistoryTable",
            table_name="ora-order-processing-history",
            partition_key=dynamodb.Attribute(name="order_id", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="event_timestamp", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.RETAIN,
        )

        self.device_inventory_table = dynamodb.Table(
            self, "DeviceInventoryTable",
            table_name="ora-device-inventory",
            partition_key=dynamodb.Attribute(name="device_model", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.RETAIN,
        )

        # --- Lambda Layer: shared PartnerAdapter contract + domain models ---

        self.shared_layer = _lambda.LayerVersion(
            self, "SharedContractsLayer",
            layer_version_name="ora-partner-adapter-contract",
            code=_lambda.Code.from_asset(str(SRC_ROOT.parent)),  # packages the whole src/ tree
            compatible_runtimes=[_lambda.Runtime.PYTHON_3_13],
            description="Shared domain models, PartnerAdapter/DataSourceAdapter contracts",
        )

        # --- Adapter Lambdas ---

        self.adapter_functions: dict[str, _lambda.Function] = {}

        for construct_id, module_path, description in (
            _DATA_SOURCE_ADAPTERS + _PARTNER_ADAPTERS + _SUPPORT_ADAPTERS
        ):
            module_name = module_path.rsplit(".", 1)[1]
            fn = _lambda.Function(
                self, construct_id,
                function_name=f"ora-adapter-{module_name.replace('_', '-')}",
                runtime=_lambda.Runtime.PYTHON_3_13,
                handler=f"mock_backends.{module_path}.handler",
                code=_lambda.Code.from_asset(str(SRC_ROOT.parent)),
                layers=[self.shared_layer],
                timeout=Duration.seconds(10),
                description=description,
                environment={
                    "DEVICE_INVENTORY_TABLE": self.device_inventory_table.table_name,
                } if construct_id == "DeviceInventoryAdapter" else {},
            )
            # Least-privilege grants (per NFR pattern): only the tables each
            # adapter actually needs. Data-source/partner adapters here are
            # mostly stateless/in-memory in v1 (per business-logic-summary.md);
            # Device Inventory Adapter is the exception — it's backed by the
            # real ora-device-inventory DynamoDB table (post-Unit-1-review fix,
            # see device_inventory_repository.py) so it needs both the IAM
            # grant AND the table name passed via environment variable.
            if construct_id == "DeviceInventoryAdapter":
                self.device_inventory_table.grant_read_write_data(fn)

            self.adapter_functions[construct_id] = fn

        # --- Failure Injection Engine ---

        self.failure_injection_engine = _lambda.Function(
            self, "FailureInjectionEngine",
            function_name="ora-failure-injection-engine",
            runtime=_lambda.Runtime.PYTHON_3_13,
            handler="mock_backends.failure_injection_engine.engine.determine_outcome",
            code=_lambda.Code.from_asset(str(SRC_ROOT.parent)),
            layers=[self.shared_layer],
            timeout=Duration.seconds(10),
            description="Determines Realistic/Demo Mode failure outcomes for placed orders",
        )
        self.crm_orders_table.grant_read_data(self.failure_injection_engine)
        self.crm_order_subscriptions_table.grant_read_write_data(self.failure_injection_engine)
