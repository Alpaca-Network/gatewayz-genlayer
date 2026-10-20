"""Deploy contracts/genlayer/cost_dispute.py to a GenLayer network.

    python scripts/deploy_cost_dispute.py --network studionet
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gzgl.net import DEPLOYMENTS, genlayer_client  # noqa: E402

from genlayer_py.types import TransactionStatus  # noqa: E402

CONTRACT = Path(__file__).resolve().parents[1] / "contracts/genlayer/cost_dispute.py"

ap = argparse.ArgumentParser()
ap.add_argument("--network", default="studionet")
a = ap.parse_args()

client = genlayer_client(a.network)
print(f"deploying CostDispute to {a.network} from {client.local_account.address}")
tx = client.deploy_contract(code=CONTRACT.read_text(), args=[])
print("tx", tx)
r = client.wait_for_transaction_receipt(transaction_hash=tx, status=TransactionStatus.ACCEPTED, retries=200)
addr = (r.get("tx_data_decoded") or {}).get("contract_address") or (r.get("data") or {}).get("contract_address")
print("CostDispute at", addr)
out = DEPLOYMENTS / f"{a.network}.json"
d = json.loads(out.read_text()) if out.exists() else {}
d.update({"cost_dispute": addr, "cost_dispute_deploy_tx": tx, "cost_dispute_operator": client.local_account.address})
out.write_text(json.dumps(d, indent=2) + "\n")
print("wrote", out)
