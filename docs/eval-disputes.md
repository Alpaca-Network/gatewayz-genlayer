# CostDispute agreement: studionet runs, 2026-10-20

How often GenLayer consensus on `CostDispute` matches the labelled dispute sets. Shadow mode:
no money moved. Re-run with `scripts/eval_disputes.py` (raw results go to `runs/`, which is
not committed).

**Read the caveats first.** Every case is synthetic, and the same author wrote the policy, the
cases and the labels. That makes the numbers below a test of *consistency with the written
policy*, not of fairness to real users. Quote them only after a human has reviewed the labels,
and after a run on real disputed traffic.

## Runs

| | v1 | v2 |
|---|---|---|
| Dataset / policy | `datasets/disputes/v1` (196) / `fbp-v1` | `datasets/disputes/v2` (216) / `fbp-v2` |
| Contract | v0.1.0 `0xdb8889f3…4A1F` | v0.2.0 `0xC29DfA26…5C79` |
| Data ref | `a852b7e` | `29b81f0` |
| Lines per dispute | 10 | 5 |
| Deterministic layer exact | 166/166 | 206/206 |
| Judged refund bucket in label range | 130/147 (88%) | **185/188 (98.4%)** |
| Judged category matches | 146/147 | 186/188 |
| False refunds (label 0, refunded) | 0 | 1 |
| Missed refunds (label >0, refunded 0) | 1 | 1 |
| Disputes without consensus (MAJORITY_DISAGREE) | 2/20 | **0/44** |
| Disputes lost to studionet RPC errors | 2/20 | 2/44 |
| Time to ACCEPTED: p50 / p90 / max | 34 s / 123 s / 288 s | 21 s / 150 s / 1077 s |

Fees: studionet is free, so the cost per dispute is **not measured yet**. That needs a Bradbury run.

## What v1 showed, and what changed for v2

- **All 15 v1 `loop_tail` misses were label errors.** Each case had a correct answer followed by
  ~80 repetitions (~90% of the billed output), the validators refunded 100%, and the label
  said 25–75%. v1 also never tested a genuinely partial refund.
  → `fbp-v2` adds a `partial` rule (refund about the wasted share, nearest bucket). v2 labels
  `loop_tail` by wasted share and adds 20 `loop_tail_short` cases (wasted share 25–75%) that no
  validator had seen. They scored 19/20.
  *Caveat:* relabelling `loop_tail` after seeing results flatters the v2 number for that variant.
  `loop_tail_short` is the clean test.
- **Two v1 wrong-language cases were bad cases.** The answers were formulas with a Spanish
  fragment, so they were mostly language-neutral. → `fbp-v2` says code, numbers and formulas
  are language-neutral.
- **Both v1 consensus failures were 10-line batches containing partial-loop lines.** Suspected
  cause: no partial rule, so validator buckets spread wider than the tolerance, and one line
  sinks the whole batch. v2 (partial rule + 5-line batches) had none in 44 disputes. Which of
  the two changes mattered is not isolated.

## v2 misses

| Case | Judged | Label | Reading |
|---|---|---|---|
| `fahrenheit-metering` | degenerate, 25% | none | **False refund.** The prompt shows `visible_tokens_out=2000` for a one-line answer. The judge penalised overbilling that the deterministic layer had already refunded. Fix: tell the judge that tokens and price are checked separately and to rule on content only. |
| `multiply-truncated` | off_task, 100% | none 0–1 | "17 x 23 =" cut by the caller's own `max_tokens` (`finish_reason=length`). The policy never says this is not refundable. Fix: add it to `not_refundable`. |
| `zip-looptail-short` | none | degenerate 2–4 | Label error: a regex followed by the same regex three times is not really degenerate. |

## Next

1. Prompt fix (judge content only) + `max_tokens` line in the policy → fbp-v3, re-run.
2. Human review of the labels (sample at least the borderline variants: `loop_tail_short`,
   `max_tokens_truncation`, `wrong_but_attempted`, `reasoning_below_threshold`).
3. Bradbury run to measure fees per dispute, and finality and appeal times.
4. Real traffic: once the backend records v2 lines (`docs/backend-usage-v2.md`), sample real
   failed and suspicious requests (with consent) into a v4 set.
