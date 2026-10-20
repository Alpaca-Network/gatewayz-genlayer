"""Live smoke test of a deployed CostDispute: one synthetic epoch, three disputed lines.

    python scripts/smoke_cost_dispute.py --network studionet

Publishes the price sheet and the revealed content bundles as secret gists (synthetic
data only), checks the served bytes hash to what the epoch committed, opens a dispute,
waits for ACCEPTED and prints the verdict. Expected: line 0 fair (0), line 1 degenerate
(refund), line 2 empty output (deterministic 100%).
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from gzgl import billing as b  # noqa: E402
from gzgl.net import DEPLOYMENTS, genlayer_client  # noqa: E402

from genlayer_py.types import TransactionStatus  # noqa: E402

SHEET = {"version": "smoke", "models": {"openai/gpt-5-mini": {"in_per_mtok": "0.25", "out_per_mtok": "2"}}}
MESSAGES = [{"role": "user", "content": "Write a haiku about rain."}]
OUTPUTS = [
    "Soft rain on the roof\nthe gutters hum their one note\nstreets turn into sky",
    "rain rain rain rain rain rain rain rain rain rain rain rain rain rain rain rain rain rain " * 4,
    "",
]
COSTS = [(20, "0.00029"), (100, "0.00045"), (40, "0.00033")]


def gist(name: str, data: bytes) -> str:
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / name
        p.write_bytes(data)
        url = subprocess.check_output(["gh", "gist", "create", str(p)], text=True).strip().splitlines()[-1]
    gid = url.rstrip("/").split("/")[-1]
    meta = json.loads(subprocess.check_output(["gh", "api", f"gists/{gid}"], text=True))
    raw = meta["files"][name]["raw_url"]
    served = urllib.request.urlopen(urllib.request.Request(raw, headers={"User-Agent": "gzgl"}), timeout=30).read()
    if hashlib.sha256(served).digest() != hashlib.sha256(data).digest():
        raise SystemExit(f"{name}: served bytes differ from what was hashed")
    return raw


ap = argparse.ArgumentParser()
ap.add_argument("--network", default="studionet")
a = ap.parse_args()

dep = json.loads((DEPLOYMENTS / f"{a.network}.json").read_text())
sheet_bytes = b.canonical_json(SHEET)
sheet_hash = b.sha256_hex(sheet_bytes)
sheet_url = gist("prices.json", sheet_bytes)

epoch_id = "0x" + os.urandom(32).hex()
ep = b.Epoch(epoch_id)
bundles = [b.canonical_content(MESSAGES, o) for o in OUTPUTS]
for i, (tok_out, cost) in enumerate(COSTS):
    ep.append({
        "request_id": f"smoke_{i}", "ts": f"2026-10-20T12:00:{i:02d}Z", "model": "openai/gpt-5-mini",
        "provider": "openai", "tokens_in": 1000, "tokens_out": tok_out, "tokens_reasoning": 0, "cost_usd": cost,
        "status": 200, "finish_reason": "stop", "price_sheet": sheet_hash,
        "content_hash": b.sha256_hex(bundles[i]), "commit": "smoke",
    })
lines = [{"index": i, "entry": ep.entries[i], "proof": ep.proof(i),
          "content_uri": gist(f"content-{i}.json", bundles[i]), "claim": "Charged too much for this output."}
         for i in range(3)]

client = genlayer_client(a.network)
dispute_id = "0x" + os.urandom(32).hex()
policy_json = (ROOT / "policies/fbp-v1.json").read_text()
tx = client.write_contract(
    address=dep["cost_dispute"], function_name="open_dispute",
    args=[dispute_id, epoch_id, ep.seal()["root"], policy_json, sheet_url, sheet_hash, json.dumps(lines)],
)
print("tx", tx)
r = client.wait_for_transaction_receipt(transaction_hash=tx, status=TransactionStatus.ACCEPTED, retries=200)
print("consensus:", (r.get("consensus_data") or {}).get("final", r.get("status_name")))
v = client.read_contract(address=dep["cost_dispute"], function_name="get_dispute", args=[dispute_id])
print(json.dumps(v, indent=2, default=str))
