"""Build the labelled dispute set v2, judged under policies/fbp-v2.json.

    python datasets/disputes/build_v2.py      # writes datasets/disputes/v2/

v1 plus the fixes its studionet run exposed (results in docs/eval-disputes.md):
  * loop_tail labels follow the v2 partial rule: the bucket nearest the wasted share of
    the billed output, +-1 (v1 labelled every one 1-3 although ~90% of each was loop).
  * New loop_tail_short cases: a usable answer with a short loop, so the wasted share is
    genuinely partial. v1 never tested a partial refund.
  * Language-neutral answers (formulas, equations) answered with a Spanish fragment are
    not wrong-language under v2; they are labelled none 0-1.
Labels are still the author's and need human review.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_v1 import TASKS, build, case, first_words, loop, none, refund, write  # noqa: E402

OUT = Path(__file__).resolve().parent / "v2"
BUCKETS = [0, 25, 50, 75, 100]
LANGUAGE_NEUTRAL = {"fahrenheit", "equation"}


def wasted_label(good: str, output: str):
    share = 100 * (len(output.encode()) - len(good.encode())) / len(output.encode())
    nearest = min(range(len(BUCKETS)), key=lambda i: abs(BUCKETS[i] - share))
    return refund("degenerate", max(1, nearest - 1), min(4, nearest + 1)), round(share)


def build_v2() -> list[dict]:
    tasks = {t[0]: t for t in TASKS}
    cases = []
    for c in build():
        good = tasks[c["task"]][2]
        if c["variant"] == "loop_tail":
            c["expect"], _ = wasted_label(good, c["output"])
        elif c["variant"] == "wrong_language" and c["task"] in LANGUAGE_NEUTRAL:
            c["expect"] = none(0, 1)
        cases.append(c)
    for t in TASKS:
        good = t[2]
        out = good + "\n" + loop(first_words(good, 4) + ".", 3)
        expect, _ = wasted_label(good, out)
        cases.append(case(f"{t[0]}-looptail-short", t, "loop_tail_short", out, expect))
    return cases


if __name__ == "__main__":
    write(OUT, build_v2())
