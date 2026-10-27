"""Build the labelled dispute set v3, judged under policies/fbp-v4.json.

    python datasets/disputes/build_v3.py      # writes datasets/disputes/v3/

v2 with one decision applied (2026-10-21): partial refunds are judged against the useful
answer, not by byte share. A complete answer followed by a few repeated fragments
(loop_tail_short) is now labelled 0-25%; v2 labelled it by wasted bytes, 25-100%.
Long loops after a short answer (loop_tail, ~90% of the bill) keep their 75-100% labels.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_v1 import none, write  # noqa: E402
from build_v2 import build_v2  # noqa: E402

OUT = Path(__file__).resolve().parent / "v3"


def build_v3() -> list[dict]:
    cases = build_v2()
    for c in cases:
        if c["variant"] == "loop_tail_short":
            c["expect"] = none(0, 1)
    return cases


if __name__ == "__main__":
    write(OUT, build_v3())
