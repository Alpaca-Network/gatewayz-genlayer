"""Approve (or revoke) Fair Billing Policy versions on the deployed CostDispute.

    python scripts/approve_policy.py --network studionet policies/fbp-v5.json [--revoke]
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from gzgl.billing import policy_hash  # noqa: E402
from gzgl.net import DEPLOYMENTS, genlayer_client, gl_wait, gl_write  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--network", default="studionet")
ap.add_argument("--revoke", action="store_true")
ap.add_argument("policy", nargs="+")
a = ap.parse_args()

out = DEPLOYMENTS / f"{a.network}.json"
dep = json.loads(out.read_text())
client = genlayer_client(a.network)
for p in map(Path, a.policy):
    h = policy_hash(json.loads(p.read_text()))
    gl_wait(client, gl_write(client, dep["cost_dispute"], "set_policy", [h, not a.revoke]))
    if a.revoke:
        dep["cost_dispute_policies"].pop(p.stem, None)
    else:
        dep["cost_dispute_policies"][p.stem] = h
    print("revoked" if a.revoke else "approved", p.stem, h)
out.write_text(json.dumps(dep, indent=2) + "\n")
