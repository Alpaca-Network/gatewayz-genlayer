# Backend spec: v2 usage lines for cost disputes

What `gatewayz-backend` must record so a CostDispute (`contracts/genlayer/cost_dispute.py`)
can judge a line. Builds on Alpaca-Network/gatewayz-backend#2382 (job-scoped keys, sealed
usage), branch `feat/genlayer-inference-escrow`. Shadow mode: job keys only, no money moves.

## Line format

One line per completed request on a job key, hashed as in `gzgl/billing.py` (sha256 leaves,
not the keccak v1 tree, which stays as-is for `InferenceEscrow`):

| Field | Source at the billing hook | Notes |
|---|---|---|
| `request_id` | `save_kwargs["request_id"]` / stream `request_id` | Joins to `chat_completion_requests` |
| `ts`, `model`, `provider`, `commit` | as in v1 | |
| `tokens_in` | `prompt_tokens` | |
| `tokens_out` | **visible** completion tokens = `completion_tokens − reasoning_tokens` | ⚠️ see below |
| `tokens_reasoning` | `usage.completion_tokens_details.reasoning_tokens` (OpenAI), `usage.reasoning_tokens` (xAI), thinking tokens (Anthropic); 0 when the provider does not report them | |
| `cost_usd` | billed cost after BYOK fee | Exactly what was charged |
| `status` | 200 for completed | Failed requests are not billed, so not lines |
| `finish_reason` | non-stream: `choice.finish_reason`; stream: last chunk's `finish_reason`; `"cancelled"` for client-cancelled streams | The legacy stream path hard-codes `"stop"`; it must pass the real one |
| `price_sheet` | sha256 of the canonical price sheet in force (model → in/out per Mtok) | New: price sheets must be versioned and served at a stable URL |
| `content_hash` | `sha256(canonical_json({"messages": <client messages>, "output": <visible text>}))` | Computed in memory. The content is never stored |

### ⚠️ Two correctness requirements

1. **Split reasoning tokens.** Today `completion_tokens` includes hidden reasoning for
   OpenAI reasoning models, and the backend never extracts `completion_tokens_details`.
   If reasoning lands in `tokens_out`, the contract's metering check (visible tokens ≤ output
   bytes + slack) refunds every reasoning-model call. Shadow mode must not start until this split is in.
2. **Hash the client's messages, not the normalised ones.** At the billing hook, `messages`
   is rebuilt from `InternalChatRequest` (and `/v1/messages` is converted from Anthropic
   format), so a user cannot reproduce it. Capture the `messages` array from the request body
   at the route, before normalisation, and hash that. `canonical_json` sorts keys, so the user's
   SDK can reproduce the bytes from what it sent.

Also return the hash to the caller as `X-Gatewayz-Content-Hash` (and the usage-line index once
known), so the client knows which bundle to keep.

### Known gaps

- **Tool calls and non-text output** are not part of `output` in v1 of the bundle. A dispute
  over a tool-call-only response can only be judged on metadata.
- **Estimated usage.** When a provider returns no usage, the backend estimates `len/4`. Flag
  such lines (`usage_estimated: true` in a v3 entry) so a metering dispute knows the count
  wasn't the provider's.

## Hook points (PR #2382 branch)

| Path | Where | What is in scope |
|---|---|---|
| Non-stream | `ChatInferenceHandler.process` → `_save_request_record` (job hook already added) | `content`, `finish_reason`, `messages`, `usage` |
| Stream (handler) | `_run_shielded_billing` / `_bill_stream` | `accumulated_content`, `messages`, last chunk's `finish_reason` |
| Stream (legacy) | `post_processing._process_stream_completion_background` | `accumulated_content`; `finish_reason` is hard-coded `"stop"` today |

`record_job_usage` gains the new fields; `append_job_usage` (SQL) gains columns
`tokens_reasoning, finish_reason, status, price_sheet, content_hash`. The v1 keccak seal is
unchanged, so the pinned cross-repo fixture keeps passing. A v2 seal (sha256) is added next to it.

## Before editing

`gatewayz-backend/CLAUDE.md` requires a GitNexus impact analysis before editing any symbol
and `gitnexus_detect_changes()` before committing. Run them on `_save_request_record`,
`_bill_stream`, `_run_shielded_billing`, `_process_stream_completion_background` and
`record_job_usage` first.

## Contract v0.5.0 changes (2026-10-27)

Found while wiring the backend (Alpaca-Network/gatewayz-backend#2410); none changes the
entry format or any hash, so `fixtures/usage-v2.json` is unchanged.

- **`finish_reason: "timeout"`** (the gateway's stream watchdog cut a provider that never
  finished) is a billed failure, like `"error"`: 100% deterministic refund.
- **Prompt-cache writes.** A sheet model may list `cache_write_per_mtok`. The price check
  then uses `max(in_per_mtok, cache_write_per_mtok)` for input tokens, because the line does
  not split cached input out. Conservative: a fair cache-write charge is never a
  `price_mismatch`; an overcharge smaller than the write premium on a cache-write request
  can go unflagged. Splitting cache tokens into the entry is a v3 format change.
- **Per-line price sheets.** `open_dispute(..., price_sheet_uri, price_sheet_hash)` with
  `price_sheet_hash = 0x00..00` and a `price_sheet_uri` ending in `/` fetches each line's
  own sheet from `price_sheet_uri + <line's price_sheet>`. One dispute can then cover lines
  of different models (the backend publishes one sheet per model and rate). The
  single-sheet call is unchanged.

Deployed 2026-10-27 to studionet at `0x661036e09B406Fc4A0AB3cBf95C0FdE2e86ECdfe` (fbp-v1..v5
approved; smoke test decided). The gatewayz.ai/escrow demo reads `cost_dispute` from this repo's
deployments file, so it moved to v0.5.0 with it. Its submitter was allowlisted there only later the same
day (tx `0x29e4aa77…d715`); until then every demo dispute was refused with `submitter_not_allowed`.
**After any redeploy, run `set_submitter` for the demo submitter** (`~/.gatewayz-escrow-demo.env`)
before the site's pinned ref picks up the new address. The orchestrator's daily end-to-end dispute
canary catches a miss. v0.4.0 at `0x23069f4C16F21E48d0E74e6E358485f1FE66B45f` is no longer used.

## Decisions (2026-10-27)

- **Failover re-pricing:** disputes judge the rate actually charged. Each line's sheet is
  the rates its charge was computed from, including the backend's loss-proof re-price to
  a pricier served provider. The contract verifies that the bill was computed honestly
  from published rates. Whether charging the served provider's rate on failover is fair
  is a Gatewayz pricing-policy question, outside the refund rules.
- **`/v1/messages` system prompt:** included. For an Anthropic-shaped body the bundle's
  `messages` is `[{"role": "system", "content": <system exactly as sent>}, *messages]`
  (system omitted when absent/empty). OpenAI bodies stay verbatim. Clients rebuild the
  same list from what they sent.
