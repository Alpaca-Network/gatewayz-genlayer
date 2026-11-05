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
from gzgl.net import DEPLOYMENTS, genlayer_client  # noqa: E402

from genlayer_py.types import TransactionStatus  # noqa: E402

CONTRACT = ROOT / "contracts/genlayer/cost_dispute.py"

ap = argparse.ArgumentParser()
ap.add_argument("--network", default="studionet")
ap.add_argument("--policy", action="append", default=[])
a = ap.parse_args()
policies = [Path(p) for p in a.policy] or sorted((ROOT / "policies").glob("fbp-*.json"))

client = genlayer_client(a.network)
print(f"deploying CostDispute to {a.network} from {client.local_account.address}")
tx = client.deploy_contract(code=CONTRACT.read_text(), args=[])
print("tx", tx)
r = client.wait_for_transaction_receipt(transaction_hash=tx, status=TransactionStatus.ACCEPTED, retries=200)
addr = (r.get("tx_data_decoded") or {}).get("contract_address") or (r.get("data") or {}).get("contract_address")
print("CostDispute at", addr)
approved = {}
for p in policies:
    h = policy_hash(json.loads(p.read_text()))
    t = client.write_contract(address=addr, function_name="set_policy", args=[h, True])
    client.wait_for_transaction_receipt(transaction_hash=t, status=TransactionStatus.ACCEPTED, retries=200)
    approved[p.stem] = h
    print("approved", p.stem, h)
out = DEPLOYMENTS / f"{a.network}.json"
d = json.loads(out.read_text()) if out.exists() else {}
d.update({"cost_dispute": addr, "cost_dispute_deploy_tx": tx, "cost_dispute_operator": client.local_account.address,
          "cost_dispute_policies": approved})
out.write_text(json.dumps(d, indent=2) + "\n")
print("wrote", out)
