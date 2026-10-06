# Inference escrow on GenLayer

Org A funds an agent job. Org B's agent runs it through [Gatewayz](https://gatewayz.ai).
A GenLayer Intelligent Contract rules on the deliverable, and the verdict releases or refunds the money.

```
Org A ──openJob──▶ InferenceEscrow (Avalanche Fuji)  ◀──settle── relayer ◀── FINALIZED verdict
                                                                                  │
Org B ──inference──▶ Gatewayz ──usage lines──▶ Merkle root ──┐                   │
Org B ──deliverable──────────────────────────────────────────┴─▶ VerifyJob (GenLayer)
```

GenLayer is never on the inference hot path. It is called once per **job**, never per request.
Only the verdict crosses chains, and the money stays on the chain the buyer uses.

## What's here

| Path | What it is |
|---|---|
| `contracts/genlayer/verify_job.py` | **VerifyJob** Intelligent Contract. It fetches the spec and the deliverable, checks both against the committed sha256, and grades the deliverable against a rubric. Validators re-run the grading with their own models. |
| `contracts/evm/src/InferenceEscrow.sol` | **InferenceEscrow**. Funds are locked per job and move only on a verdict from one specific VerifyJob deployment. There are two delivery paths (bridge or relayer), a deadline refund, pull payouts, and an on-chain usage-proof check. |
| `gzgl/usage.py` | Sealed usage record: a Merkle tree over billing metadata (`ts, model, provider, tokens_in, tokens_out, cost_usd, commit`). It never holds a prompt or a completion. |
| `gzgl/relayer.py` | Fallback verdict delivery. It waits for GenLayer FINALIZED, reads finalized state only, then calls `settle()`. |
| `gzgl/rubric.py` | Rubric canonicalisation. It must hash identically to the contract's, because the escrow rejects a verdict judged against a different rubric. |
| `rubrics/` | Three templates: `written.json`, `code.json` and `data_extraction.json`. |
| `scripts/demo.py` | The end-to-end run: `new → fund → work → verify → settle → audit`. |
| `scripts/verify_usage.py` | Public audit. Anyone can check a usage record against the on-chain root without a key. |

## How a verdict is reached

- **What the leader does.** The leader fetches `spec_uri` and `deliverable_uri`. If either sha256 differs from the committed hash, the case fails with no LLM call. Otherwise it prompts its LLM with the spec, the rubric and the fenced, untrusted deliverable.
- **Pass is computed, never read from the model's prose.** A case passes when every must-have is met, no hard rejection applies, and `score >= pass_threshold`.
- **Validators re-run the grading.** They agree with the leader when both reach the same pass/fail and their scores are within the rubric's `score_tolerance` (default 15).
- **Who can open a case.** Only allowlisted submitters (the Gatewayz Verify service in the pilot) may open one, and only one case per job. This stops a third party front-running a job with a bogus deliverable.

## Trust model and known limits (pilot)

- **The verdict is GenLayer's.** The relayer forwards only what VerifyJob stored in finalized state. Anyone can compare a `JobSettled` event with `get_verdict(job_id)` on GenLayer, using `verdictRef` (the GenLayer tx hash).
- **Relayer key.** On the relayer path, the escrow trusts a single relayer address for *delivery*. A compromised relayer key could settle jobs wrongly. That is why the bridge path exists, and why the production key must live in a managed signer.
- **Bridge path.** The escrow authenticates the *originating* GenLayer contract and the source chain id, not just the BridgeReceiver. GenLayer's reference `BridgeSender.send_message` is unauthenticated ([internetcourt#11](https://github.com/genlayer-foundation/internetcourt/issues/11)), so checking only the receiver would let anyone write verdicts. `test_bridge_rejects_message_from_untrusted_genlayer_sender` covers this.
- **Spec and rubric binding.** The buyer commits `specHash` and `rubricHash` at `openJob`. A verdict for any other spec or rubric reverts with `VerdictMismatch`.
- **Deadlines.** `openJob` requires a deadline at least `minDuration` away, so GenLayer finality plus appeals fits inside it. A verdict that arrives after the deadline loses to `expire()`, which refunds the buyer.
- **The submitter chooses the deliverable.** In the pilot that is the Gatewayz Verify service, acting on the seller's authenticated submission.
- **Validators see whatever the URIs serve.** Private work must be submitted as a redacted copy.
- **Testnets only.** There is no mainnet deployment and no token. Real funds wait for GenLayer mainnet and an external audit.

## Run it

You need Python 3.12+, [uv](https://docs.astral.sh/uv/), [Foundry](https://getfoundry.sh) and the `gh` CLI (for publishing spec and deliverable as gists).

```bash
uv venv -p 3.12 .venv && uv pip install -p .venv -e '.[dev]'
git submodule update --init
(cd contracts/evm && forge build && forge test)
.venv/bin/pytest -q                       # contract (direct mode), usage, relayer-on-anvil tests
```

Keys live outside the repo, in `~/.gatewayz-genlayer-testnet.env` (override the path with `GZGL_ENV`):

```
OPERATOR_PRIVATE_KEY=0x...   # deploys, submits cases, relays (needs GEN on Bradbury + AVAX on Fuji)
BUYER_PRIVATE_KEY=0x...      # Org A, funds the escrow (needs AVAX on Fuji)
SELLER_PRIVATE_KEY=0x...     # Org B, receives payment
SELLER_GATEWAYZ_API_KEY=gw_...   # Org B's Gatewayz key
```

Faucets: Fuji from <https://core.app/tools/testnet-faucet/?subnet=c&token=c>, and GEN from <https://testnet-faucet.genlayer.foundation>. Studionet needs no funding.

```bash
python scripts/deploy_verify_job.py --network studionet         # or bradbury
python scripts/deploy_escrow.py --genlayer-network studionet
python scripts/demo.py all --genlayer-network studionet
python scripts/verify_usage.py --escrow <escrow> --job-id <job> --usage runs/<job>/usage.json
```

## Deployments

Deployments are recorded in `deployments/<genlayer-network>.json`. The Slither report is in `docs/slither-2026-10-05.txt`; it has no high or medium findings.

## License

MIT
