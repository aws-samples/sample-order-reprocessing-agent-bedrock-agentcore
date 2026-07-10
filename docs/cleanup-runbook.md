# Cleanup Runbook — Order Reprocessing Agent

## ⚠️ Important: `cdk destroy` Does NOT Fully Clean Up This Stack

Per NFR-6, all stateful resources in this project use a **`RETAIN`** removal policy — meaning DynamoDB tables and their data survive `cdk destroy`. This is intentional (protects against accidental data loss during iterative development/demos), but it means **you must manually delete these resources** when you're truly done, or they will continue to incur (small) ongoing costs indefinitely.

## Step 1: Run `cdk destroy`

```bash
cd order-reprocessing-agent
cdk destroy --app "python infrastructure/app.py"
```

This removes: all Lambda functions, the AgentCore Runtime/Gateway/GatewayTargets, the Bedrock Guardrail, the EventBridge Rule and Scheduler, IAM roles/policies, and the Lambda Layer.

**This does NOT remove**: the 4 DynamoDB tables (`ora-crm-orders`, `ora-crm-order-subscriptions`, `ora-order-processing-history`, `ora-device-inventory`) and their CloudWatch Log Groups.

## Step 2: Manually Delete the Retained DynamoDB Tables

```bash
aws dynamodb delete-table --table-name ora-crm-orders --region eu-west-2
aws dynamodb delete-table --table-name ora-crm-order-subscriptions --region eu-west-2
aws dynamodb delete-table --table-name ora-order-processing-history --region eu-west-2
aws dynamodb delete-table --table-name ora-device-inventory --region eu-west-2
```

**⚠️ This permanently deletes all seeded/demo order data. There is no undo.** If you want to preserve the data (e.g., for later reference or to re-seed from an export), export it first:

```bash
# Optional: export each table's contents before deleting, for reference
aws dynamodb scan --table-name ora-crm-orders --region eu-west-2 > ora-crm-orders-backup.json
aws dynamodb scan --table-name ora-crm-order-subscriptions --region eu-west-2 > ora-crm-order-subscriptions-backup.json
aws dynamodb scan --table-name ora-order-processing-history --region eu-west-2 > ora-order-processing-history-backup.json
aws dynamodb scan --table-name ora-device-inventory --region eu-west-2 > ora-device-inventory-backup.json
```

## Step 3: Manually Delete Retained CloudWatch Log Groups

CDK's default Lambda log group behavior also uses RETAIN unless explicitly overridden. List and delete them:

```bash
aws logs describe-log-groups --log-group-name-prefix "/aws/lambda/ora-" --region eu-west-2 \
  --query "logGroups[].logGroupName" --output text | \
  tr '\t' '\n' | \
  xargs -I{} aws logs delete-log-group --log-group-name {} --region eu-west-2
```

Also check for the AgentCore Runtime's dedicated log group:

```bash
aws logs describe-log-groups --log-group-name-prefix "/aws/bedrock-agentcore/ora-" --region eu-west-2 \
  --query "logGroups[].logGroupName" --output text | \
  tr '\t' '\n' | \
  xargs -I{} aws logs delete-log-group --log-group-name {} --region eu-west-2
```

## Step 4: Verify Nothing Remains

```bash
# Should return an empty list once cleanup is complete
aws resourcegroupstaggingapi get-resources \
  --tag-filters Key=Project,Values=OrderReprocessingAgent \
  --region eu-west-2
```

If this returns any resources, investigate and delete them individually — they may be resources this runbook didn't anticipate (e.g., manually-created test resources, or a future construct added without RETAIN-awareness).

## Step 5: Region Note

eu-west-2 (London) is a standard, always-enabled AWS region — there is no opt-in to disable, unlike the originally-planned ap-south-2. No action needed here.

## Cost Reminder

Per requirements.md's cost estimates, this project's ongoing cost if left running is roughly **$0.60-1.00/day** at demo scale (informational only, no fixed ceiling per NFR-8) — small, but not zero. If you're pausing rather than permanently done, at minimum consider whether the EventBridge Scheduler (`ora-ambient-activity-schedule`) should be disabled to stop generating ambient orders while you're not actively using the environment (this alone doesn't require a full teardown — you can disable just the schedule via `aws scheduler update-schedule --state DISABLED ...`).
