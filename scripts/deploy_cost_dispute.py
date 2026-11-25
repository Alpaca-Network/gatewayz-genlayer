"""Deploy contracts/genlayer/cost_dispute.py to a GenLayer network and approve policies.

    python scripts/deploy_cost_dispute.py --network studionet [--policy policies/fbp-v4.json ...]

With no --policy, every policies/fbp-*.json is approved (testnets only; on a real
deployment approve exactly the version the escrow commits to).
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from gzgl.billing import policy_hash  # noqa: E402
from gzgl.net import DEPLOYMENTS, genlayer_client, gl_contract_address, gl_deploy, gl_wait, gl_write  # noqa: E402

CONTRACT = ROOT / "contracts/genlayer/cost_dispute.py"

ap = argparse.ArgumentParser()
ap.add_argument("--network", default="studionet")
ap.add_argument("--policy", action="append", default=[])
a = ap.parse_args()
policies = [Path(p) for p in a.policy] or sorted((ROOT / "policies").glob("fbp-*.json"))

client = genlayer_client(a.network)
print(f"deploying CostDispute to {a.network} from {client.local_account.address}")
tx = gl_deploy(client, CONTRACT.read_text(), [])
print("tx", tx)
addr = gl_contract_address(gl_wait(client, tx))
print("CostDispute at", addr)
approved = {}
for p in policies:
    h = policy_hash(json.loads(p.read_text()))
    gl_wait(client, gl_write(client, addr, "set_policy", [h, True]))
    approved[p.stem] = h
    print("approved", p.stem, h)
out = DEPLOYMENTS / f"{a.network}.json"
d = json.loads(out.read_text()) if out.exists() else {}
d.update({"cost_dispute": addr, "cost_dispute_deploy_tx": tx, "cost_dispute_operator": client.local_account.address,
          "cost_dispute_policies": approved})
out.write_text(json.dumps(d, indent=2) + "\n")
print("wrote", out)
