"""Write a human review sheet for the borderline cases of a labelled dispute set.

    python datasets/disputes/review_sheet.py runs/eval-studionet-<ts>.json > datasets/disputes/v2/REVIEW.md

Shows each case's request, output, label and the network's ruling, so a reviewer can mark
the label right or wrong without opening any JSON.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BORDERLINE = ("loop_tail_short", "max_tokens_truncation", "wrong_but_attempted", "reasoning_below_threshold",
              "wrong_language")
BUCKETS = ["0%", "25%", "50%", "75%", "100%"]


def cell(text: str, limit: int = 220) -> str:
    t = text.replace("|", "\\|").replace("\n", " ⏎ ")
    return t if len(t) <= limit else t[: limit - 1] + "…"


def main(run_path: str):
    run = json.loads(Path(run_path).read_text())
    data = ROOT / run["meta"]["data"]
    cases = {json.loads(l)["id"]: json.loads(l) for l in (data / "cases.jsonl").read_text().splitlines() if l}
    got = {s["id"]: s for s in run["lines"]}
    print(f"# Label review: {data.name}, borderline cases\n")
    print(f"Ruling column: run `{Path(run_path).name}` (policy `{run['meta']['policy']}`, contract "
          f"`{run['meta']['contract']}`). Mark **Your call** as ✅ (label right), ❌ (label wrong, say "
          "what it should be) or ? (unsure). Disagreements between label and ruling are marked ⚠️.\n")
    for v in BORDERLINE:
        rows = [c for c in cases.values() if c["variant"] == v]
        if not rows:
            continue
        print(f"## {v} ({len(rows)})\n")
        print("| Case | Request | Output | Tokens out / reasoning | Label | Ruling | Your call |")
        print("|---|---|---|---|---|---|---|")
        for c in sorted(rows, key=lambda r: r["id"]):
            bundle = json.loads((data / "content" / f"{c['id']}.json").read_bytes())
            e, x = c["entry"], c["expect"]
            label = f"{x['category']} {BUCKETS[x['bucket'][0]]}–{BUCKETS[x['bucket'][1]]}"
            g = got.get(c["id"], {})
            ruling = f"{g.get('category', '–')} {BUCKETS[g['bucket']] if 'bucket' in g else ''}".strip()
            flag = " ⚠️" if g.get("judged") and not g.get("bucket_ok") else ""
            print(f"| `{c['id']}` | {cell(bundle['messages'][0]['content'], 120)} | {cell(bundle['output'])} | "
                  f"{e['tokens_out']} / {e['tokens_reasoning']} | {label} | {ruling}{flag} | |")
        print()


if __name__ == "__main__":
    main(sys.argv[1])
