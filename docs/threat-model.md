# Threat Model — Autonomous Order Processing Failure Detection and Correction for BSS Telco

**System**: Order Reprocessing Agent (Amazon Bedrock AgentCore + Claude Sonnet 4.6)
**Scope**: `OrderReprocessingAgentStack` deployed to eu-west-2, ~80 AWS resources
**Last updated**: 2026-07-13
**Repository**: `gitlab.aws.dev/telco-buddy/autonomous-order-failure-detection-and-correction-for-bss-telco`

## 1. System Overview

The Order Reprocessing Agent autonomously diagnoses and resolves failed telco BSS orders. An EventBridge event triggers a Strands Agent (Claude Sonnet 4.6) running on Amazon Bedrock AgentCore Runtime, which calls 6 tools via AgentCore Gateway to fetch missing data, resubmit orders, or escalate to a human.

**Important scoping note**: this is a fully-mocked v1 reference implementation. There is no real Amdocs/telco backend, no real customer PII, and no real financial transaction. All "customer data" is synthetically generated. This threat model assesses the architecture pattern as if backends were real, since that is the intended production evolution path (see README's Roadmap Preview), while explicitly flagging where v1's mocked nature changes the actual current risk.

## 2. Architecture & Trust Boundaries

```
[Boundary 1: Order Placement]          [Boundary 2: Agent Reasoning]           [Boundary 3: Backend Systems]
                                                                                          
Operator UI/API  →  Order Placement  →  EventBridge  →  Runtime Invoker  →  AgentCore Runtime  →  AgentCore Gateway  →  6 Tool Lambdas  →  Mock/Real Backends
  (untrusted            Lambda                              Lambda          (Claude Sonnet 4.6)      (MCP, IAM-      (DynamoDB, mock       (would be real
   input)                                                                    -- LLM reasoning          authorized)     partner APIs)          CRM/GVPM/etc.
                                                                               over tool outputs)                                               in production)
                                                                                          │
                                                                                          ▼
                                                                              [Boundary 4: Escalation]
                                                                              EscalateToHuman → Ticketing (mock) + SNS (stubbed, not wired)
```

**Boundary 1 — Order Placement**: The entry point where external order data enters the system. Currently exercised via direct Lambda invoke / local Streamlit UI using the operator's own AWS credentials — there is no public-facing API Gateway in this v1.

**Boundary 2 — Agent Reasoning**: The highest-privilege boundary. Claude Sonnet 4.6, via the Strands Agent loop, decides which tools to call and with what arguments. This is the only component in the system that makes autonomous, non-deterministic decisions.

**Boundary 3 — Backend Systems**: Where tool calls resolve to actual data reads/writes. In v1, entirely mocked Lambdas with in-memory/DynamoDB-backed fake data. In a production evolution, this boundary would cross into real Amdocs CRM/GVPM systems — the highest-impact boundary if reached with excessive privilege.

**Boundary 4 — Escalation**: Where the agent hands off to a human when it can't safely proceed.

## 3. Assets

| Asset | Sensitivity | Current State (v1) |
|---|---|---|
| Customer order/subscription data | High (would be PII/PCI-adjacent in production) | Synthetic/fake in v1 — no real customer data |
| Agent reasoning/decision logic (system prompt) | Medium — a target for prompt injection | Real, deployed |
| AgentCore Runtime execution role credentials | High | Real IAM role, scoped (see §5) |
| Bedrock model access | Medium (cost/abuse vector) | Real |
| Escalation tickets (may contain reasoning about real customer issues) | Medium | Mocked ticketing system |

## 4. STRIDE Threat Analysis

### 4.1 Spoofing

| Threat | Component | Assessment | Mitigation |
|---|---|---|---|
| Unauthorized invocation of AgentCore Runtime | Runtime Invoker Lambda → AgentCore Runtime | AgentCore Runtime is invoked via `InvokeAgentRuntime`, authorized by IAM (SigV4), not a public endpoint. Only the Runtime Invoker Lambda's execution role can call it. | IAM policy scoped to the specific runtime + runtime-endpoint ARN (confirmed in `order_placement_service.py`) — not a wildcard |
| Spoofed EventBridge events triggering false agent invocations | EventBridge rule matching `OrderStatusChanged` | The rule matches on event `source`/`detail-type`/`detail.status` but does not currently verify the *origin* of the PutEvents call beyond IAM permission on `events:PutEvents`. Any principal with that permission in the account could inject a fabricated failure event. | **Gap**: `events:PutEvents` is granted with `resources=["*"]` (see `order_placement_service.py`) rather than scoped to the specific event bus. Recommend scoping to the account's default event bus ARN explicitly, and consider a custom event bus for this system rather than the default bus shared by other account activity. |

### 4.2 Tampering

| Threat | Component | Assessment | Mitigation |
|---|---|---|---|
| Agent submits fabricated/hallucinated data via ReprocessOrder | AgentCore Runtime → ReprocessOrder tool | This is the single highest-value tampering risk in the system — an LLM autonomously writing to a system of record. | Two independent layers: (1) system prompt explicitly instructs "never fabricate a field value," (2) a Bedrock Guardrail scoped specifically to `ReprocessOrder`'s input, blocking empty/placeholder/obviously-fabricated values via pattern and word-policy rules (see `reprocess_order_guardrail.py`). **Residual risk**: prompt-based instructions are not a hard guarantee; the Guardrail's denied-word list (`"fabricated"`, `"guessed"`, etc.) would only catch a model that explicitly states it's guessing, not a confidently-wrong hallucination that doesn't self-report. |
| Duplicate/replayed order resubmission | ReprocessOrder tool | A duplicate EventBridge delivery or Lambda retry could cause a duplicate downstream resubmission. | Verified fix: `ReprocessOrder` uses DynamoDB conditional writes (`ConditionExpression`), confirmed idempotent against real duplicate-event testing this session. |
| Tampering with the failure-injection probability config | `failure_probabilities.json` | Low real-world risk in v1 (this file only controls demo/simulation behavior), but in a production system this pattern (externalized business-rule config read at Lambda cold start) would need integrity protection if it controlled real order-routing logic. | Not currently signed/validated; acceptable for v1's simulation purpose, flagged for production evolution. |

### 4.3 Repudiation

| Threat | Component | Assessment | Mitigation |
|---|---|---|---|
| No record of why the agent took an action | Agent tool calls | Every tool writes a structured event to `OrderProcessingHistory` (DynamoDB) at the moment it acts — order_id, subscription_id, event_type, tool_name, summary, resulting_status, and (for escalations) the full agent reasoning text. This is a genuine, real-time audit trail, not reconstructed from logs. | Confirmed working end-to-end this session across all 6 tools. |
| History table itself could be tampered with post-hoc | `OrderProcessingHistory` DynamoDB table | The table has no write-time integrity control (e.g., no append-only/immutability enforcement beyond IAM permissions on who can call `PutItem`). | **Gap**: consider DynamoDB Streams + a separate immutable audit sink (e.g., S3 with Object Lock) if this history needs to be tamper-evident for real compliance/audit purposes in production. |

### 4.4 Information Disclosure

| Threat | Component | Assessment | Mitigation |
|---|---|---|---|
| Agent reasoning text in escalation tickets could leak sensitive customer data | EscalateToHuman → Ticketing | The agent's `agent_reasoning` field is written verbatim into the ticket and into `OrderProcessingHistory`. In production, this reasoning could include real customer PII (device IMEI, billing details) as plain text. | No current redaction/masking of PII within reasoning text. **Gap for production**: consider a PII-scanning step before persisting agent-generated free text, or tokenizing sensitive fields before they ever reach the LLM's context. |
| Bedrock model invocation with `resources=["*"]` | Runtime execution role → `bedrock:InvokeModel` | Necessarily broad because Claude Sonnet 4.6 is accessed via a global cross-region inference profile with no single-region ARN to scope to (documented in `agent_orchestration.py`). This is a known AWS/Bedrock limitation, not a design oversight. | Accepted risk — scoping is not currently possible for this inference profile type. Monitor for future Bedrock IAM condition-key support. |
| Order data readable by any principal with DynamoDB read access | `CRMOrders`/`CRMOrderSubscriptions` tables | Tables use RETAIN removal policy and standard IAM grants (`grant_read_write_data` scoped per-Lambda) — no table-level encryption-at-rest customization beyond DynamoDB's default AWS-managed encryption. | Acceptable for v1 mock data; production evolution should evaluate customer-managed KMS keys if real customer data is stored. |

### 4.5 Denial of Service

| Threat | Component | Assessment | Mitigation |
|---|---|---|---|
| Ambient Activity Generator or a compromised caller floods the system with orders | `ora-ambient-activity-generator` (EventBridge Scheduler, 1-minute default interval) | Currently unthrottled beyond Lambda's own concurrency limits; a misconfigured or malicious interval change could generate excessive agent invocations (real Bedrock inference cost + Lambda invocations). | Recommend a Lambda reserved-concurrency limit on `ora-order-placement-service` and `ora-runtime-invoker`, and a CloudWatch alarm on invocation rate. Not currently configured. |
| Runaway agent tool-calling loop | AgentCore Runtime ↔ Gateway ↔ tools | The system prompt bounds the decision sequence (validate → check eligibility → fetch → reprocess/escalate), but there's no hard iteration cap enforced outside the prompt itself. | **Gap**: no programmatic max-tool-calls circuit breaker independent of the LLM's own prompt-following behavior. A model that ignores instructions could loop indefinitely, incurring cost. Recommend adding an explicit step-count limit in the agent loop (`agent.py`) as a hard backstop. |

### 4.6 Elevation of Privilege

| Threat | Component | Assessment | Mitigation |
|---|---|---|---|
| Gateway execution role over-privileged to invoke tool Lambdas | AgentCore Gateway → 6 tool Lambdas | Each tool Lambda's invoke permission is granted individually and explicitly (`lambda_fn.grant_invoke(self.gateway.role)`) per tool — not a blanket wildcard grant. | Correctly scoped; confirmed via code review. |
| Prompt injection via order data causing the agent to call tools outside its intended sequence | Order data → agent's initial prompt | Order/subscription field values (device model, VAS type, etc.) are interpolated into the agent's initial prompt (`_build_initial_prompt` in `agent.py`). If backend data were ever attacker-controlled (e.g., a compromised upstream CRM in production), it could theoretically attempt prompt injection to alter agent behavior. | The agent's tool set is narrow and each tool has its own IAM-authorized, schema-validated inputs — a successful injection could still only call the same 6 pre-registered tools, bounding the blast radius. The Guardrail on `ReprocessOrder` is the critical backstop even under injection. **Gap**: no explicit input sanitization/injection-pattern detection on order field values before they reach the prompt. |
| Docker container running as root | AgentCore Runtime container | **Fixed this session**: Dockerfile now creates and runs as a non-root `appuser` (previously ran as root, the image default). | Resolved — see `src/agent/runtime/Dockerfile`. |
| Container binds to 0.0.0.0 | AgentCore Runtime container | Initially flagged by static analysis (bandit B104, semgrep `avoid_app_run_with_bad_host`). Verified this is required by the AgentCore Runtime contract — the container is invoked over AgentCore's internal network, not directly internet-exposed. AgentCore's own network boundary controls external access. | Documented with inline suppression + rationale comment; not a real exposure given AgentCore's actual invocation model. |

## 5. IAM Privilege Summary (Verified Against Real Code)

| Role | Key Permissions | Scoping Quality |
|---|---|---|
| AgentCore Runtime execution role | `bedrock-agentcore:InvokeGateway/ListTools/CallTool` (scoped to gateway ARN); `bedrock:InvokeModel*` (`resources=["*"]`, unavoidable per Bedrock cross-region inference profile limitation) | Good, with one accepted/unavoidable exception |
| AgentCore Gateway execution role | `lambda:InvokeFunction` per tool Lambda (explicitly granted per-function) | Good — no wildcard |
| Runtime Invoker Lambda role | `bedrock-agentcore:InvokeAgentRuntime` scoped to the specific runtime ARN + `/runtime-endpoint/*` | Good — correctly scoped to the actual authorization sub-resource (a real bug found and fixed this session) |
| Order Placement / Ambient Activity Lambda roles | DynamoDB `grant_read_write_data` (table-scoped); `events:PutEvents` (`resources=["*"]`) | **Gap**: `events:PutEvents` should be scoped to the specific event bus ARN, not `"*"` |
| EventBridge Scheduler role | `lambda:InvokeFunction` scoped to the ambient activity function only | Good |

## 6. Known Gaps & Accepted Risks (Honest Summary)

1. **`events:PutEvents` scoped to `"*"`** — should be narrowed to the specific event bus ARN. Not yet fixed.
2. **No hard circuit-breaker on agent tool-call iterations** — relies entirely on prompt-following. Not yet fixed.
3. **No PII redaction in agent reasoning text** — acceptable for v1 (no real PII exists), but a real gap for production evolution.
4. **`OrderProcessingHistory` is not tamper-evident** — DynamoDB table with standard IAM-gated writes, no immutability/Object Lock equivalent.
5. **SNS notification on escalation is a documented no-op stub** (`escalate_to_human.py`'s `notified = True` is hardcoded, not a real SNS publish) — tracked as a known v1 limitation, not a security gap per se, but relevant to incident-response completeness.
6. **AgentCore Runtime tracing is disabled** (`tracing_enabled=False`) due to an unresolved account-level X-Ray trace destination configuration gap — reduces observability into agent decision-making at the infrastructure level (Order History table remains the reliable audit source).
7. **`bedrock:InvokeModel` cannot be resource-scoped** — accepted, current AWS/Bedrock limitation for global cross-region inference profiles.

## 7. Recommendations Prioritized

| Priority | Recommendation | Effort |
|---|---|---|
| High | Scope `events:PutEvents` to the specific event bus ARN | Low |
| High | Add a hard max-tool-calls circuit breaker in `agent.py`, independent of prompt instructions | Medium |
| Medium | Add PII-pattern detection/redaction before persisting agent reasoning text (relevant before any real customer data is introduced) | Medium |
| Medium | Add CloudWatch alarms + reserved concurrency limits on order-placement and runtime-invoker Lambdas to bound cost/DoS exposure | Low |
| Low | Evaluate DynamoDB Streams + immutable audit sink for `OrderProcessingHistory` if compliance requirements demand tamper-evidence | Medium |
| Low | Wire the SNS escalation notification for real (currently a stub) | Low |

## 8. Out of Scope for This Assessment

- Real Amdocs/telco backend integrations (do not exist in v1)
- Network-layer threats (system uses AWS-managed services with no VPC/network path currently defined for most components)
- Physical security, insider threat at AWS infrastructure level (covered by AWS's own compliance posture)
- Multi-tenant isolation (this is a single-account reference deployment, not a multi-tenant SaaS)
