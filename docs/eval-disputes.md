# CostDispute agreement: studionet runs, 2026-10-20

How often GenLayer consensus on `CostDispute` matches the labelled dispute sets. Shadow mode:
no money moved. Re-run with `scripts/eval_disputes.py` (raw results go to `runs/`, which is
not committed).

**Read the caveats first.** Every case is synthetic, and the same author wrote the policy, the
cases and the labels. That makes the numbers below a test of *consistency with the written
policy*, not of fairness to real users. Quote them only after a human has reviewed the labels,
and after a run on real disputed traffic.

## Runs

| | v1 | v2 | v3 (regression) | v4 (hardened) | v5 (worked examples) |
|---|---|---|---|---|---|
| Dataset / policy | `datasets/disputes/v1` (196) / `fbp-v1` | `datasets/disputes/v2` (216) / `fbp-v2` | v2 set / `fbp-v3` | `datasets/disputes/v3` (216) / `fbp-v4` | v3 set / `fbp-v5` |
| Contract | v0.1.0 `0xdb8889f3…4A1F` | v0.2.0 `0xC29DfA26…5C79` | v0.3.0 `0xdda926fA…55b3` | v0.4.0 `0x23069f4C…B45f` | same |
| Data ref | `a852b7e` | `29b81f0` | `a458271` | `99f4997` | `60049d4` |
| Lines per dispute | 10 | 5 | 5 | 5 | 5 |
| Deterministic layer exact | 166/166 | 206/206 | 216/216 | 211/211 | 216/216 |
| Judged refund bucket in label range | 130/147 (88%) | 185/188 (98.4%) | 194/196 (99.0%) | **186/191 (97.4%)** | **196/196 (100%)** |
| Judged category matches | 146/147 | 186/188 | 195/196 | 189/191 | 196/196 |
| False refunds (label 0, refunded) | 0 | 1 | 0 | **0** | **0** |
| Missed refunds (label >0, refunded 0) | 1 | 1 | 1 | 1 | 0 |
| Disputes without consensus (MAJORITY_DISAGREE) | 2/20 | 0/44 | 0/44 | 0/44 | 0/44 |
| Disputes lost to studionet RPC errors | 2/20 | 2/44 | 0/44 (wider retry) | 1/44 | 0/44 |
| Time to ACCEPTED: p50 / p90 / max | 34 s / 123 s / 288 s | 21 s / 150 s / 1077 s | 34 s / 1021 s / 5445 s | 27 s / 86 s / 275 s | 26 s / 72 s / 129 s |

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

## v3 (regression on the v2 set)

v3 fixed the two judgment misses v2 exposed: the prompt now says token counts and prices are
code-checked and never a reason to refund, and `fbp-v3` lists the caller's own `max_tokens`
cut-off as not refundable. Both cases now pass. This is a **regression check, not a fresh
test**, because the fixes were made after seeing those exact cases.

The two remaining misses are both `loop_tail_short`, the genuinely partial cases:
`zip-looptail-short` (judged 25%, labelled 50–100%; the label is doubtful, see v2) and
`fahrenheit-looptail-short` (judged none, labelled 25–50%). Partial refunds are where the
judges are least sure, which matches the intuition.

**Latency is the open problem.** The median was fine at 34 s, but p90 was 17 min and the worst
dispute took 91 min to ACCEPTED on studionet. If Bradbury looks similar, the challenge window has
to absorb hours, not minutes, before payouts. Measure there before fixing window lengths.

## v4 (hardened contract, useful-answer partial rule)

Decision 2026-10-21: partial refunds are judged against the useful answer, not by byte
share (`fbp-v4`). Dataset v3 relabels the 20 `loop_tail_short` cases (complete answer + a
few repeated fragments) from 25–100% to 0–25%. The contract is v0.4.0 (approved-policy
allowlist, fence defanging, size limits).

The rule moved most short-loop rulings but not all of them. 17 of 20 now get 0–25%;
`hash`, `capital` and `author` still got 50%. On a one-line answer the validators still
weigh how much junk there is relative to the answer. `palindrome-looptail` (long loop) got
25% where 75–100% was expected. `capital-spanish` ("La capital de Australia es Canberra.")
got no refund; the label is doubtful, since a one-line name reads in any language.

There were still no false refunds and every dispute reached consensus. If 50% on a short
answer with a few repeats is unacceptable, the next step is a worked example in the policy,
not more wording.

## v5 (worked examples in the partial rule)

Decision 2026-10-22 (Joaquim): add a worked example. `fbp-v5` keeps the v4 wording and adds
three examples on a question that is not in the dataset (Mount Everest): answer + a few
repeated fragments → 0–25%, never 50%, however short the answer; the same answer + ~150
repeats → 75–100%; a loop before the answer is finished → 100%. Same contract, dataset and
labels as v4.

Every judged line landed in its label range (196/196), with no false refunds, no missed
refunds and no consensus failures. 19 of 20 short-loop cases got 25%, and one got 0%.

Read it with care:
- **Not a clean test.** The examples were written after v4 showed which cases failed. The
  question differs, but the shape is the same, so this is a fit to the known misses. Only
  new cases or real traffic will show whether it generalises.
- **Run-to-run variance on doubtful cases.** `capital-spanish` got 0% in v4 and 100% in v5,
  although the only policy change was the loop examples, which say nothing about language. The label (50–100%) is doubtful, so v5 "passing" it
  proves little. One run per policy is not enough to separate a policy effect from noise.

## Next

1. ~~Prompt fix + `max_tokens` line → fbp-v3~~ done (v3 above).
2. Human review of the labels (sample at least the borderline variants: `loop_tail_short`,
   `max_tokens_truncation`, `wrong_but_attempted`, `reasoning_below_threshold`).
3. Bradbury run to measure fees per dispute, and finality and appeal times.
4. Real traffic: once the backend records v2 lines (`docs/backend-usage-v2.md`), sample real
   failed and suspicious requests (with consent) into a v4 set.
