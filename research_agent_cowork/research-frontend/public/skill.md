# AVA Research Agent - AI Agent Skill Guide

> **Audience**: AI agents (LLMs with tool-use capabilities).
> This skill teaches you how to autonomously register a FluxA wallet, authorize a research budget, submit a Twitter research request to the AVA Research Agent, poll for completion, and download the final report.

---

## Prerequisites

| Requirement | Details |
|---|---|
| **FluxA Agent Wallet skill** | You MUST complete agent registration first. Follow the FluxA Agent Wallet skill at: `https://github.com/FluxA-Agent-Payment/FluxA-AI-Wallet-MCP/blob/main/skills/fluxa-agent-wallet/SKILL.md` |
| **Node.js v18+** | Required for the FluxA CLI (`scripts/fluxa-cli.bundle.js`) |
| **HTTP client** | `curl` or equivalent for REST API calls |
| **AVA Research API** | Base URL: `https://web-production-1b829.up.railway.app` |

After completing FluxA registration, credentials are automatically stored in `~/.fluxa-ai-wallet-mcp/` by the CLI. To retrieve the JWT for API calls:

```bash
node scripts/fluxa-cli.bundle.js status    # also refreshes expired JWT
```

The `jwt` field in the response is your `Bearer` token for all AVA API calls.

---

## Overview of the Full Workflow

```
Step 1 ─ Register FluxA Agent Wallet (one-time)
Step 2 ─ Confirm research target with user
Step 3 ─ Create a payment mandate (budget authorization)
Step 4 ─ User signs the mandate
Step 5 ─ Submit research request to AVA
Step 6 ─ Poll for task completion
Step 7 ─ Download the research report
```

---

## Step 1: Register a FluxA Agent Wallet (One-Time)

If you do not yet have FluxA credentials (`AGENT_ID`, `AGENT_TOKEN`, `AGENT_JWT`), register now.

### 1.1 Run the init command

```bash
node scripts/fluxa-cli.bundle.js init \
  --email "your-agent@example.com" \
  --name "My Research Agent" \
  --client "AVA Research Client v1.0"
```

The CLI returns JSON:

```json
{
  "success": true,
  "data": {
    "agent_id": "ag_xxxxxxxxxxxx",
    "token": "tok_xxxxxxxxxxxx",
    "jwt": "eyJhbGciOiJ..."
  }
}
```

### 1.2 If an authorization URL is returned

Ask the user whether to open it:

> "I need to complete FluxA agent registration. May I open the authorization link in your browser?"
>
> Options: **[Yes, open the link]** / **[No, show me the URL]**

If user says yes, run:

```bash
open "<authorization_url>"
```

If no, display the URL and wait for the user to confirm completion.

### 1.3 Verify registration

```bash
node scripts/fluxa-cli.bundle.js status
```

Expected output includes `agent_id`, `jwt` status, and wallet readiness.

Credentials are automatically stored by the CLI in `~/.fluxa-ai-wallet-mcp/` and loaded on subsequent calls. No manual export is needed.

> **Note**: The JWT automatically refreshes when expired. If you get a 401 error later, run `node scripts/fluxa-cli.bundle.js status` to trigger a refresh.

---

## Step 2: Confirm Research Target with the User

Before spending any budget, **always** confirm with the human user which Twitter handle to research.

Ask the user:

> "Which Twitter account would you like me to research? Please provide the handle (e.g., @username)."

Also confirm the research parameters:

> "The default research budget is $2.00 USD. Would you like to change the budget?"

Collect:
- **handle** (required): e.g., `@elonmusk`
- **budget_usd** (optional, default `2.00`): maximum spend in USD

> **Note**: The engine is OpenAI (non-configurable). A payment mandate is **required** before submitting research.

**Do NOT proceed** until the user explicitly confirms the target handle and budget.

---

## Step 3: Create a Payment Mandate (Budget Authorization)

A mandate authorizes AVA to charge up to the budget amount from the user's FluxA wallet.

### 3.1 Create the mandate

Convert the budget to USDC atomic units (6 decimals). For example:
- $2.00 = `2000000` atomic units
- $1.50 = `1500000` atomic units
- $5.00 = `5000000` atomic units

```bash
node scripts/fluxa-cli.bundle.js mandate-create \
  --desc "AVA Research: @<handle> - budget $<budget_usd> USDC" \
  --amount <atomic_units>
```

> **Important**: Both `--desc` and `--amount` flags are REQUIRED.

Example for $2.00 budget:

```bash
node scripts/fluxa-cli.bundle.js mandate-create \
  --desc "AVA Research: @elonmusk - budget $2.00 USDC" \
  --amount 2000000
```

The response includes:

```json
{
  "success": true,
  "data": {
    "mandateId": "mand_xxxxxxxxxxxx",
    "authorizationUrl": "https://agentwallet.fluxapay.xyz/onboard/intent?oid=..."
  }
}
```

Save the `mandateId` for Step 5.

---

## Step 4: User Signs the Mandate

The user must authorize the mandate in the FluxA Wallet UI.

### 4.1 Present the authorization URL

Ask the user:

> "I need your authorization to spend up to $X.XX for this research. May I open the authorization page in your browser?"
>
> Options: **[Yes, open the link]** / **[No, show me the URL]**

If yes:

```bash
open "<authorizationUrl>"
```

If no, display the URL for manual opening.

### 4.2 Wait for user confirmation

> "Please sign the mandate in the FluxA Wallet page, then let me know when you're done."

### 4.3 Verify mandate status

```bash
node scripts/fluxa-cli.bundle.js mandate-status --id <mandateId>
```

> **Important**: Use `--id`, NOT `--mandate`.

Check that the status is `"signed"` or `"active"` before proceeding. If still pending, wait and retry.

---

## Step 5: Submit the Research Request

Now submit the research task to the AVA Research API.

### 5.1 API endpoint

```
POST <AVA_BASE_URL>/research
```

### 5.2 Request headers

```
Authorization: Bearer <AGENT_JWT>
Content-Type: application/json
```

### 5.3 Request body

```json
{
  "handle": "@<twitter_handle>",
  "mandate_id": "<mandateId_from_step_3>",
  "budget_usd": 2.00,
  "fluxa_jwt": "<AGENT_JWT>"
}
```

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `handle` | string | **Yes** | - | Twitter handle (with or without `@`) |
| `mandate_id` | string | **Yes** | - | FluxA mandate ID for payment |
| `budget_usd` | float | No | `2.00` | Maximum budget in USD |
| `fluxa_jwt` | string | No | null | Your FluxA JWT for payment processing |

### 5.4 Example curl

```bash
curl -X POST <AVA_BASE_URL>/research \
  -H "Authorization: Bearer $AGENT_JWT" \
  -H "Content-Type: application/json" \
  -d '{
    "handle": "@elonmusk",
    "mandate_id": "mand_xxxxxxxxxxxx",
    "budget_usd": 2.00,
    "fluxa_jwt": "'"$AGENT_JWT"'"
  }'
```

### 5.5 Response

```json
{
  "task_id": "20250218_120000_elonmusk_abc123",
  "handle": "@elonmusk",
  "status": "pending",
  "version": "gpt-5.2-2025-12-11",
  "engine": "openai",
  "created_at": "2025-02-18T12:00:00",
  "message_count": 0,
  "cost_usd": 0.0,
  "mandate_id": "mand_xxxxxxxxxxxx",
  "budget_usd": 2.00,
  "payment_status": "authorized",
  "payment_amount_usd": 0.0,
  "tool_calls": 0,
  "failure_stage": null,
  "failure_code": null,
  "retryable": null,
  "upstream_request_id": null
}
```

Save the `task_id` for polling.

### 5.6 Error handling

| HTTP Status | Meaning | Action |
|-------------|---------|--------|
| 200/201 | Success | Proceed to polling |
| 400 | Bad request (missing mandate_id, empty handle) | Fix input and retry |
| 401 | Invalid/expired JWT | Refresh JWT and retry |
| 422 | Validation error (missing required field) | Check request body |
| 500 | Server error | Wait and retry (up to 3 times) |

---

## Step 6: Poll for Task Completion

Research tasks run asynchronously. Poll the status endpoint until the task completes.

### 6.1 Status endpoint

```
GET <AVA_BASE_URL>/research/<task_id>
Authorization: Bearer <AGENT_JWT>
```

### 6.2 Example curl

```bash
curl <AVA_BASE_URL>/research/20250218_120000_elonmusk_abc123 \
  -H "Authorization: Bearer $AGENT_JWT"
```

### 6.3 Response

```json
{
  "task_id": "20250218_120000_elonmusk_abc123",
  "handle": "@elonmusk",
  "status": "running",
  "message_count": 25,
  "cost_usd": 0.35,
  "tool_calls": 8,
  "payment_status": "authorized",
  "payment_amount_usd": 0.0,
  "error_message": null
}
```

### 6.4 Task status values

| Status | Meaning | Action |
|--------|---------|--------|
| `pending` | Queued, not yet started | Keep polling |
| `running` | Actively researching | Keep polling |
| `completed` | Finished successfully | Proceed to download |
| `failed` | Error occurred | Check `error_message`, notify user |
| `cancelled` | User cancelled | Inform user |

### 6.5 Polling strategy

1. Poll every **2 minutes** while status is `pending` or `running`
2. Maximum polling duration: **10 minutes** (research typically completes in 2-5 minutes)
3. If polling times out, inform the user and provide the `task_id` for manual checking

---

## Step 7: Download the Research Report

Once the task status is `completed`, download the report.

### 7.1 Get report as JSON

```bash
curl <AVA_BASE_URL>/research/<task_id>/report \
  -H "Authorization: Bearer $AGENT_JWT"
```

Response:

```json
{
  "task_id": "20250218_120000_elonmusk_abc123",
  "handle": "@elonmusk",
  "status": "completed",
  "report": {
    "content": "# Research Report: @elonmusk\n\n## Executive Summary\n...",
    "filename": "elonmusk_20250218_120000_abc123_research.md",
    "size_bytes": 15234
  }
}
```

The `report.content` field contains the full Markdown research report.

### 7.2 Download report as file

```bash
curl <AVA_BASE_URL>/research/<task_id>/report?download=true \
  -H "Authorization: Bearer $AGENT_JWT" \
  -o research_report.md
```

### 7.3 Check payment details

```bash
curl <AVA_BASE_URL>/research/<task_id>/payment \
  -H "Authorization: Bearer $AGENT_JWT"
```

Response:

```json
{
  "task_id": "20250218_120000_elonmusk_abc123",
  "payment_status": "completed",
  "budget_usd": 2.00,
  "claude_cost_usd": 0.35,
  "tool_calls": 12,
  "tool_cost_usd": 0.12,
  "total_cost_usd": 0.47,
  "payment_amount_usd": 0.47,
  "payment_tx_hash": "0x1234abcd..."
}
```

### 7.4 Retry failed payment

If the report endpoint returns HTTP **402**, it means payment failed (e.g. mandate balance insufficient). Use the retry-payment endpoint to resolve:

```bash
curl -X POST <AVA_BASE_URL>/research/<task_id>/retry-payment \
  -H "Authorization: Bearer $AGENT_JWT" \
  -H "Content-Type: application/json" \
  -d '{
    "mandate_id": "<new_mandate_id>",
    "fluxa_jwt": "'"$AGENT_JWT"'"
  }'
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `mandate_id` | string | No | New mandate ID if the old one is expired or exhausted. Falls back to the original mandate if omitted |
| `fluxa_jwt` | string | No | Fresh JWT. Falls back to stored JWT if omitted |

Response:

```json
{
  "success": true,
  "payment_status": "completed",
  "payment_amount_usd": 0.47,
  "payment_tx_hash": "0x1234abcd...",
  "payment_error": null
}
```

> **Typical flow**: If mandate funds are insufficient, create a new mandate (Step 3) with a higher budget, then call retry-payment with the new `mandate_id`. Once payment succeeds, the report endpoint will return normally.

### 7.5 Present results to user

Summarize the key findings from the report to the user, and offer the full report content or download link.

---

## Additional Endpoints Reference

### List all tasks

```
GET <AVA_BASE_URL>/research_lists_magic?limit=50&offset=0&status=completed
Authorization: Bearer <AGENT_JWT>
```

### Cancel a running task

```
DELETE <AVA_BASE_URL>/research/<task_id>
Authorization: Bearer <AGENT_JWT>
```

### Download raw log

```
GET <AVA_BASE_URL>/research/<task_id>/log
Authorization: Bearer <AGENT_JWT>
```

### Health check (no auth required)

```
GET <AVA_BASE_URL>/
```

### Server configuration (no auth required)

```
GET <AVA_BASE_URL>/config
```

---

## Authentication Details

All authenticated endpoints require a JWT in the `Authorization` header:

```
Authorization: Bearer <your_AGENT_JWT>
```

The server extracts your agent identity from the JWT payload. It looks for these fields in order: `agent_id`, `agentId`, `sub`, `user_id`, `uid`, `id`, or nested `agent.agent_id`.

Your FluxA `AGENT_JWT` satisfies this requirement since it contains `agent_id` in its payload.

### JWT Refresh

If you receive a `401` response, your JWT may have expired. Refresh it:

```bash
node scripts/fluxa-cli.bundle.js status
```

Or call the FluxA refresh endpoint directly:

```bash
curl -X POST https://agentid.fluxapay.xyz/refresh \
  -H "Content-Type: application/json" \
  -d '{"agent_id": "<AGENT_ID>", "token": "<AGENT_TOKEN>"}'
```

The response contains a new `jwt` field. Update your `AGENT_JWT` and retry the failed request.

---

## Cost Model

Research tasks are billed based on actual usage:

| Component | Rate | Example |
|-----------|------|---------|
| OpenAI API usage | Actual token cost | ~$0.30-0.50 per report |
| Tool calls | $0.01 per call | 12 calls = $0.12 |
| **Total** | Sum of above | ~$0.40-0.60 typical |

Payment is automatically processed after research completes. A `mandate_id` is **required** for all research requests. The actual charge will never exceed the `budget_usd` you specified.

---

## Complete Example: End-to-End Flow

```bash
# Step 1: Register FluxA wallet (one-time)
node scripts/fluxa-cli.bundle.js init \
  --email "agent@example.com" \
  --name "Research Bot" \
  --client "AVA Client v1"

# Credentials auto-saved to ~/.fluxa-ai-wallet-mcp/
# Retrieve JWT for API calls:
AGENT_JWT=$(node scripts/fluxa-cli.bundle.js status | jq -r '.data.jwt')

# Step 2: (Confirm target with user - handled via conversation)
# User confirmed: @vaborsh, budget $1.00

# Step 3: Create mandate (REQUIRED before submitting research)
node scripts/fluxa-cli.bundle.js mandate-create \
  --desc "AVA Research: @vaborsh - budget $1.00 USDC" \
  --amount 1000000

# Save mandate_id from response
MANDATE_ID="mand_xxxxxxxxxxxx"

# Step 4: (User signs mandate at authorization URL)

# Verify mandate is signed
node scripts/fluxa-cli.bundle.js mandate-status --id $MANDATE_ID

# Step 5: Submit research request (mandate_id is required!)
TASK_ID=$(curl -s -X POST https://web-production-1b829.up.railway.app/research \
  -H "Authorization: Bearer $AGENT_JWT" \
  -H "Content-Type: application/json" \
  -d '{
    "handle": "@vaborsh",
    "mandate_id": "'"$MANDATE_ID"'",
    "budget_usd": 1.00,
    "fluxa_jwt": "'"$AGENT_JWT"'"
  }' | jq -r '.task_id')

echo "Task submitted: $TASK_ID"

# Step 6: Poll for completion
while true; do
  STATUS=$(curl -s https://web-production-1b829.up.railway.app/research/$TASK_ID \
    -H "Authorization: Bearer $AGENT_JWT" | jq -r '.status')
  echo "Status: $STATUS"
  if [ "$STATUS" = "completed" ] || [ "$STATUS" = "failed" ]; then
    break
  fi
  sleep 5
done

# Step 7: Download report
curl -s https://web-production-1b829.up.railway.app/research/$TASK_ID/report \
  -H "Authorization: Bearer $AGENT_JWT" | jq -r '.report.content'
```

---

## Preflight Checklist (Before Submitting)

Before calling `POST /research`, verify:

1. **Mandate exists and is signed** — Run `mandate-status --id <mandateId>` and confirm status is `"signed"` or `"active"`
2. **JWT is valid** — Run `node scripts/fluxa-cli.bundle.js status` to refresh if expired
3. **Budget is sufficient** — Typical research costs $0.40-0.60; set `budget_usd` >= $1.00 to be safe
4. **mandate_id is included** — The API will reject requests without a `mandate_id` (HTTP 400)

---

## Error Matrix

When a task fails, the API returns structured failure information in the task status response:

| `failure_code` | `failure_stage` | `retryable` | Meaning | Action |
|----------------|----------------|-------------|---------|--------|
| `provider_key_missing` | `provider_auth` | `false` | OpenAI API key not configured on server | Contact service operator |
| `provider_auth_failed` | `provider_auth` | `false` | API key invalid or expired | Contact service operator |
| `billing_insufficient_credit` | `provider_quota` | `false` | Provider account balance too low | Top up provider account |
| `provider_rate_limited` | `provider_runtime` | `true` | Rate limited by OpenAI | Wait 30s and retry |
| `provider_internal_error` | `provider_runtime` | `true` | OpenAI internal error | Retry; report `upstream_request_id` if persistent |
| `provider_timeout` | `provider_runtime` | `true` | Connection timeout to OpenAI | Retry |
| `provider_no_output` | `provider_runtime` | `true` | OpenAI returned empty response | Retry |
| `tool_execution_failed` | `tool_runtime` | `true` | MCP tool call failed | Check `/log` for details; retry |
| `internal_error` | `internal` | `false` | Unexpected server error | Contact service operator |

### HTTP-level errors (before task creation)

| HTTP Status | Meaning | Action |
|-------------|---------|--------|
| 400 | Missing `mandate_id` or invalid input | Create mandate first, fix request |
| 401 | JWT expired or invalid | Refresh JWT via `status` command |
| 422 | Request validation error | Check required fields |
| 500 | Server internal error | Retry up to 3 times |

---

## Observability & Troubleshooting

When a task fails, use these endpoints to diagnose the issue:

### Minimum troubleshooting steps

```bash
# 1. Check task status and failure classification
curl <AVA_BASE_URL>/research/<task_id> \
  -H "Authorization: Bearer $AGENT_JWT" | jq '{
    status, error_message, failure_stage, failure_code,
    retryable, upstream_request_id
  }'

# 2. Check detailed logs (includes provider errors, tool calls)
curl <AVA_BASE_URL>/research/<task_id>/log \
  -H "Authorization: Bearer $AGENT_JWT"

# 3. Check payment status
curl <AVA_BASE_URL>/research/<task_id>/payment \
  -H "Authorization: Bearer $AGENT_JWT"
```

### Understanding the failure fields

| Field | Description |
|-------|-------------|
| `failure_stage` | Where the failure occurred: `provider_auth`, `provider_quota`, `provider_runtime`, `tool_runtime`, or `internal` |
| `failure_code` | Machine-readable error code (see Error Matrix above) |
| `retryable` | `true` if the client should retry, `false` if a different action is needed (e.g., top up balance) |
| `upstream_request_id` | OpenAI's request ID (e.g., `req_c013...`) — include this when reporting issues |

### Decision tree for agents

```
if retryable == true:
    → wait 5-30s, create new task with same parameters
elif failure_code == "billing_insufficient_credit":
    → inform user to top up provider balance
elif failure_code == "provider_key_missing" or "provider_auth_failed":
    → inform user to contact service operator
else:
    → inform user with error_message and upstream_request_id
```

---

## Error Recovery

| Scenario | Solution |
|----------|----------|
| 401 Unauthorized | Refresh JWT using `status` command or `/refresh` endpoint |
| Task failed (retryable) | Check `failure_code` and `retryable`; retry with new task |
| Task failed (non-retryable) | Check `failure_code` for specific action (top up, contact support) |
| Mandate not signed | Re-prompt user to sign; check `mandate-status` |
| Polling timeout | Inform user, provide `task_id` for later retrieval |
| Payment failed | Check `payment_error` in status; task still completes, report still available |
| Network error | Retry up to 3 times with exponential backoff (2s, 4s, 8s) |

---

## MCP Server Access (Advanced)

AVA also exposes its Twitter and web scraping tools via MCP (Model Context Protocol) at:

```
SSE endpoint: <AVA_BASE_URL>/mcp/sse
```

Available MCP tools:
- `get_twitter_profile` - Profile data (username, bio, followers, etc.)
- `get_twitter_following` - Following list with founder detection
- `get_twitter_tweets` - Recent tweets with URL extraction
- `bulk_get_twitter_profiles` - Batch profile lookup (max 20)
- `scrape_website` - Web page content extraction (Markdown)

These can be used directly by MCP-capable agents (e.g., OpenAI with MCP support, Claude Desktop) for custom research workflows without going through the REST API.
