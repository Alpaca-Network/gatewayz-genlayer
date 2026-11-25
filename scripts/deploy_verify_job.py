"""Deploy contracts/genlayer/verify_job.py to a GenLayer network.

    python scripts/deploy_verify_job.py --network studionet
    python scripts/deploy_verify_job.py --network bradbury [--bridge-sender 0x.. --target-eid N --escrow 0x..]
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gzgl.net import DEPLOYMENTS, genlayer_client, gl_contract_address, gl_deploy, gl_wait  # noqa: E402

CONTRACT = Path(__file__).resolve().parents[1] / "contracts/genlayer/verify_job.py"

ap = argparse.ArgumentParser()
ap.add_argument("--network", default="studionet")
ap.add_argument("--bridge-sender", default="")
ap.add_argument("--target-eid", type=int, default=0)
ap.add_argument("--escrow", default="")
a = ap.parse_args()

client = genlayer_client(a.network)
print(f"deploying VerifyJob to {a.network} from {client.local_account.address}")
tx = gl_deploy(client, CONTRACT.read_text(), [a.bridge_sender, a.target_eid, a.escrow])
print("tx", tx)
addr = gl_contract_address(gl_wait(client, tx))
print("VerifyJob at", addr)
out = DEPLOYMENTS / f"{a.network}.json"
d = json.loads(out.read_text()) if out.exists() else {}
d.update({"verify_job": addr, "verify_job_deploy_tx": tx, "operator": client.local_account.address})
out.write_text(json.dumps(d, indent=2) + "\n")
print("wrote", out)
