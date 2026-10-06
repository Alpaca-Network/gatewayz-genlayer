"""Deploy InferenceEscrow to Avalanche Fuji, bound to one VerifyJob deployment.

    (cd contracts/evm && forge build) && python scripts/deploy_escrow.py --genlayer-network studionet

Relayer path only (bridge receiver = 0) until the GenLayer -> ZKsync -> Fuji
LayerZero route is confirmed. The relayer and treasury default to OPERATOR.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gzgl.net import DEPLOYMENTS, fuji, key  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
ap = argparse.ArgumentParser()
ap.add_argument("--genlayer-network", default="studionet")
ap.add_argument("--fee-bps", type=int, default=250)
ap.add_argument("--min-duration", type=int, default=2 * 3600, help="seconds; must exceed GenLayer finality + appeals")
ap.add_argument("--treasury", default=None)
ap.add_argument("--bridge-receiver", default="0x" + "00" * 20)
ap.add_argument("--genlayer-chain-id", type=int, default=61998, help="source chain id the bridge stamps (BridgeSender.py)")
a = ap.parse_args()

dep_file = DEPLOYMENTS / f"{a.genlayer_network}.json"
dep = json.loads(dep_file.read_text())
art = json.loads((ROOT / "contracts/evm/out/InferenceEscrow.sol/InferenceEscrow.json").read_text())
w3 = fuji()
op = w3.eth.account.from_key(key("OPERATOR"))
treasury = a.treasury or op.address
bal = w3.eth.get_balance(op.address)
print(f"operator {op.address} balance {w3.from_wei(bal, 'ether')} AVAX")
if bal == 0:
    raise SystemExit("operator has no Fuji AVAX — fund it at https://core.app/tools/testnet-faucet/?subnet=c&token=c")

C = w3.eth.contract(abi=art["abi"], bytecode=art["bytecode"]["object"])
ctor = C.constructor(treasury, a.fee_bps, a.min_duration, op.address, w3.to_checksum_address(a.bridge_receiver),
                     a.genlayer_chain_id, w3.to_checksum_address(dep["verify_job"]))
tx = ctor.build_transaction({"from": op.address, "nonce": w3.eth.get_transaction_count(op.address), "chainId": w3.eth.chain_id})
h = w3.eth.send_raw_transaction(op.sign_transaction(tx).raw_transaction)
r = w3.eth.wait_for_transaction_receipt(h, timeout=180)
if r["status"] != 1:
    raise SystemExit(f"deploy reverted {h.hex()}")
dep.update({"escrow": r["contractAddress"], "escrow_deploy_tx": "0x" + h.hex().removeprefix("0x"), "escrow_chain": "fuji",
            "relayer": op.address, "treasury": treasury, "fee_bps": a.fee_bps, "min_duration": a.min_duration})
dep_file.write_text(json.dumps(dep, indent=2) + "\n")
print(f"InferenceEscrow at {r['contractAddress']}  https://testnet.snowtrace.io/address/{r['contractAddress']}")
