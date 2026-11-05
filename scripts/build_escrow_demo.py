"""Build demo/escrow/: the request catalogue and price sheet behind gatewayz.ai/escrow.

    python scripts/build_escrow_demo.py

The live demo replays recorded responses from datasets/disputes/v3 (synthetic, written for
the evaluation) and lets a visitor contest them on the real CostDispute contract. Validators
fetch the content bundles and this price sheet from raw.githubusercontent.com at a pinned
commit, so every hash below must match the served bytes exactly.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from gzgl import billing as b  # noqa: E402

DATA = ROOT / "datasets/disputes/v3"
OUT = ROOT / "demo/escrow"
OPEN_MODEL = "meta-llama/llama-3.3-70b-instruct"
SHEET = {
    "version": "escrow-demo-v1",
    "models": {
        OPEN_MODEL: {"in_per_mtok": "0.25", "out_per_mtok": "2"},
    },
}

# (case id, short title, provider, model, what a fair verdict looks like)
ITEMS = [
    ("capital-fair", "Capital of Australia", "open-provider", OPEN_MODEL, "A correct one-line answer. Not refundable."),
    ("sql-fair", "Top 5 customers in SQL", "open-provider", OPEN_MODEL, "A working query. Not refundable."),
    ("tcpudp-fair", "TCP vs UDP in 80 words", "open-provider", OPEN_MODEL, "A good explanation. Not refundable."),
    ("capital-wrong", "Capital of Australia (again)", "open-provider", OPEN_MODEL,
     "Wrong answer (Sydney), but it tried. Wrong answers are not refundable."),
    ("email-loop", "Decline-a-meeting email", "open-provider", OPEN_MODEL,
     "The model looped on one phrase. Expect 75-100% back."),
    ("hash-garbage", "Explain hash functions to a 12-year-old", "open-provider", OPEN_MODEL,
     "Garbage characters. Expect 75-100% back."),
    ("haiku-offtask", "Haiku about rain", "open-provider", OPEN_MODEL,
     "Answered a different question. Expect 75-100% back."),
    ("summary-spanish", "Two-sentence summary", "open-provider", OPEN_MODEL,
     "Answered in Spanish to an English request. Expect 50-100% back."),
    ("email-looptail-short", "Decline-a-meeting email (retry)", "open-provider", OPEN_MODEL,
     "A good email plus a few repeated fragments. Expect 0-25%."),
    ("fahrenheit-empty", "Fahrenheit to Celsius", "open-provider", OPEN_MODEL,
     "Billed for an empty reply. Code refunds 100% without asking a model."),
    ("sql-metering", "Top 5 customers in SQL (retry)", "open-provider", OPEN_MODEL,
     "Billed 2,000 tokens for a short reply. Code refunds the overbilled share."),
    ("multiply-runaway", "What is 17 x 23?", "open-provider", OPEN_MODEL,
     "24,000 hidden reasoning tokens for a one-line sum. Expect 50-100% back."),
]


def main() -> None:
    cases = {json.loads(l)["id"]: json.loads(l) for l in (DATA / "cases.jsonl").read_text().splitlines() if l}
    sheet_bytes = b.canonical_json(SHEET)
    sheet_hash = b.sha256_hex(sheet_bytes)
    items = []
    for cid, title, provider, model, expect in ITEMS:
        c, raw = cases[cid], (DATA / "content" / f"{cid}.json").read_bytes()
        content = json.loads(raw)
        e = c["entry"]
        assert b.sha256_hex(raw) == e["content_hash"], cid
        expected = b.expected_cost_nano(SHEET, model, e["tokens_in"], e["tokens_out"], e["tokens_reasoning"])
        assert b.to_nano(e["cost_usd"]) == expected, (cid, e["cost_usd"], expected)
        items.append({
            "id": cid, "title": title, "provider": provider, "model": model, "expect": expect,
            "variant": c["variant"],
            "prompt": content["messages"][-1]["content"], "output": content["output"],
            "tokens_in": e["tokens_in"], "tokens_out": e["tokens_out"], "tokens_reasoning": e["tokens_reasoning"],
            "cost_usd": e["cost_usd"], "status": e["status"], "finish_reason": e["finish_reason"],
            "content_hash": e["content_hash"], "content_path": f"datasets/disputes/v3/content/{cid}.json",
        })
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "prices.json").write_bytes(sheet_bytes)
    (OUT / "catalogue.json").write_text(json.dumps(
        {"price_sheet_path": "demo/escrow/prices.json", "price_sheet_hash": sheet_hash, "items": items},
        indent=1, ensure_ascii=False) + "\n")
    print(f"{len(items)} items, price sheet {sheet_hash}")


if __name__ == "__main__":
    main()
