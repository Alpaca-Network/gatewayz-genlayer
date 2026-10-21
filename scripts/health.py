"""One-line JSON health probe for the orchestrator (read-only, no key needed).

    python scripts/health.py [--network studionet]

Reads the deployed CostDispute: reachable, newest policy approved, dispute count, and
the latest committed-or-local eval summary. Never writes to the chain.
"""

import argparse
import glob
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ap = argparse.ArgumentParser()
ap.add_argument("--network", default="studionet")
a = ap.parse_args()
out = {"ok": False, "network": a.network}
try:
    from genlayer_py import create_account, create_client
    from genlayer_py.chains import studionet, testnet_bradbury

    from gzgl.billing import policy_hash

    dep = json.loads((ROOT / "deployments" / f"{a.network}.json").read_text())
    addr = dep["cost_dispute"]
    newest = sorted((ROOT / "policies").glob("fbp-v*.json"), key=lambda p: int(p.stem.split("-v")[1]))[-1]
    # Reads need an account object but sign nothing: use a throwaway in-memory one.
    client = create_client(chain={"studionet": studionet, "bradbury": testnet_bradbury}[a.network],
                           account=create_account())
    ids = client.read_contract(address=addr, function_name="get_dispute_ids", args=[])
    allowed = client.read_contract(address=addr, function_name="is_policy_allowed",
                                   args=[policy_hash(json.loads(newest.read_text()))])
    out.update({"ok": True, "contract": addr, "disputes": len(ids), "newest_policy": newest.stem,
                "newest_policy_allowed": bool(allowed)})
    runs = sorted(glob.glob(str(ROOT / "runs" / f"eval-{a.network}-*.json")))
    if runs:
        r = json.loads(Path(runs[-1]).read_text())
        t = r.get("totals", {})
        out["last_eval"] = {"file": Path(runs[-1]).name, "policy": (r.get("meta") or {}).get("policy"),
                            "bucket_ok": t.get("bucket_ok"), "judged": t.get("judged"),
                            "false_refunds": t.get("false"), "no_verdict": t.get("noverdict")}
except Exception as e:  # report, never raise: the orchestrator reads one JSON line
    out["error"] = f"{type(e).__name__}: {str(e)[:200]}"
print(json.dumps(out))
