# Deployment Guide — Order Reprocessing Agent

## Prerequisites

### 1. Region: eu-west-2 (London)
This project deploys to eu-west-2, a standard, always-enabled region (no opt-in required). No action needed here — this replaces the originally-planned ap-south-2 (Hyderabad), which was an opt-in region found to be DISABLED in the target account and blocked by Isengard-managed accounts requiring console-based opt-in (see aidlc-docs/audit.md for the full investigation). eu-west-2 was selected after confirming it has no pre-existing project resources and supports both Bedrock AgentCore and the required Claude Sonnet 4.6 model.

### 2. Verify Bedrock Model Access
This project uses **Claude Sonnet 4.6** via Global cross-region inference (`global.anthropic.claude-sonnet-4-6`). Ensure model access is enabled in your account:
```bash
aws bedrock list-foundation-models --region eu-west-2 --by-provider anthropic
```
If access isn't yet granted, request it via the Bedrock console's Model Access page.

### 3. Tooling
- Python 3.13+
- AWS CDK CLI >= 2.1129.0 (`npm install -g aws-cdk@latest`)
- `pip install -e ".[dev]"` from the repo root (installs pytest, moto, aws-cdk-lib==2.261.0, constructs)

### 4. Bootstrap CDK (if not already done in your account/region)
```bash
cdk bootstrap aws://<your-account-id>/eu-west-2
```

## Deployment Steps

### 1. Deploy the full stack
```bash
cd order-reprocessing-agent
cdk deploy --app "python infrastructure/app.py" \
  -c environment=Demo \
  -c owner=<your-alias> \
  -c costCenter=<your-cost-center> \
  -c operatingMode=REALISTIC
```

For a Workshop Studio deployment, use `-c operatingMode=DEMO -c workshopAttendeeId=<attendee-id>` instead — this switches the Trigger tab's primary flow to explicit scenario-forcing (per FR-17/BR-38).

This single `cdk deploy` provisions everything: 4 DynamoDB tables, ~22 Lambda functions, the AgentCore Runtime/Gateway/GatewayTargets, the Bedrock Guardrail, EventBridge Rule + Scheduler, and all IAM roles/policies.

### 2. Seed the mock CRM
```bash
export CRM_ORDERS_TABLE=ora-crm-orders
export CRM_ORDER_SUBSCRIPTIONS_TABLE=ora-crm-order-subscriptions
export AWS_REGION=eu-west-2
python -m mock_backends.seed.seed_crm
```
This populates 100 realistic orders with a representative status mix (BR-13), so the Order Summary/History/Issues tabs have content immediately.

### 3. Launch the Operator UI (local)
```bash
streamlit run src/ui/app.py
```
Ensure your local AWS credentials have the IAM permissions documented in `aidlc-docs/construction/operator-ui/code/code-summary.md`.

## Post-Deployment Verification

**Authoritative verification: run the automated end-to-end test suite (Unit 6)**

```bash
export ORA_E2E_REGION=eu-west-2  # or your deployment's region if different
python -m pytest tests/e2e/ -m e2e -v
```

This runs all 14 scenarios from `requirements.md` Section 7 against your real deployment (requires `operatingMode=DEMO`, as configured above). Expect a runtime of a few minutes total (each scenario polls the real agent invocation chain, up to 60s per scenario). See `aidlc-docs/construction/testing/code/code-summary.md` for the full scenario list and 2 known scenarios (4, 9 in that doc's numbering — unresolvable-conflict and VAS dependency-ordering) that are marked `xfail` pending a small follow-up fix to the failure injection engine.

**Manual spot-checks** (optional, if you want to see it in the UI rather than just test output):
1. **Order Summary tab**: should show 100 seeded orders with varied statuses.
2. **Trigger tab**: place a test order; verify it appears in Order Summary shortly after.
3. **Order History tab**: select any order; verify history events appear (note: full agent reasoning traces require the AgentCore Runtime's agent loop, which is a known placeholder as of this version — see `aidlc-docs/construction/agent-tools-orchestration/code/code-summary.md`'s gap #1).
4. **Issues tab**: after some ambient activity has run (default every 1 minute), check for any ESCALATED/PARTIALLY_ACTIVATED orders appearing.

## Known Limitations (as of this version)

- **~~AgentCore Runtime's agent loop is a placeholder~~ — RESOLVED.** The Runtime now runs a real Strands Agents SDK agent loop connected to the Gateway. This has been verified locally (Docker build + run + health check) but NOT yet verified end-to-end against a real AWS deployment — that verification is exactly what running `pytest tests/e2e/ -m e2e -v` (below) after your first deployment will confirm.
- **SNS publishing in EscalateToHuman is a no-op** — escalation tickets are created (via the mock Ticketing Adapter), but no real SNS notification is sent yet.
- **This is a fully mocked v1** — no real Amdocs/TM Forum API integration; all backends (GVPM, VAS partners, etc.) are simulated.

## Cleanup

See `docs/cleanup-runbook.md` — **`cdk destroy` alone does NOT fully remove this stack** due to RETAIN removal policies on stateful resources (NFR-6).
