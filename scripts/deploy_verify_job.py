"""Deploy contracts/genlayer/verify_job.py to a GenLayer network.

    python scripts/deploy_verify_job.py --network studionet
    python scripts/deploy_verify_job.py --network bradbury [--bridge-sender 0x.. --target-eid N --escrow 0x..]
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gzgl.net import DEPLOYMENTS, genlayer_client  # noqa: E402

from genlayer_py.types import TransactionStatus  # noqa: E402

CONTRACT = Path(__file__).resolve().parents[1] / "contracts/genlayer/verify_job.py"

ap = argparse.ArgumentParser()
ap.add_argument("--network", default="studionet")
ap.add_argument("--bridge-sender", default="")
ap.add_argument("--target-eid", type=int, default=0)
ap.add_argument("--escrow", default="")
a = ap.parse_args()

client = genlayer_client(a.network)
print(f"deploying VerifyJob to {a.network} from {client.local_account.address}")
tx = client.deploy_contract(code=CONTRACT.read_text(), args=[a.bridge_sender, a.target_eid, a.escrow])
print("tx", tx)
r = client.wait_for_transaction_receipt(transaction_hash=tx, status=TransactionStatus.ACCEPTED, retries=200)
addr = (r.get("tx_data_decoded") or {}).get("contract_address") or (r.get("data") or {}).get("contract_address")
print("VerifyJob at", addr)
out = DEPLOYMENTS / f"{a.network}.json"
d = json.loads(out.read_text()) if out.exists() else {}
d.update({"verify_job": addr, "verify_job_deploy_tx": tx, "operator": client.local_account.address})
out.write_text(json.dumps(d, indent=2) + "\n")
print("wrote", out)
