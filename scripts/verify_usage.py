"""Public audit script: check one job's usage record against the root stored on the escrow.

    python scripts/verify_usage.py --escrow 0x.. --job-id 0x.. --usage usage.json [--rpc URL]

Either party can run it. It needs no key: it reads the root and runs
InferenceEscrow.verifyUsageLeaf for every line, and also recomputes the root locally.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from web3 import Web3  # noqa: E402

from gzgl.relayer import load_abi  # noqa: E402
from gzgl.usage import UsageRecord  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--escrow", required=True)
ap.add_argument("--job-id", required=True)
ap.add_argument("--usage", required=True, help="usage.json as returned by GET /v1/jobs/{id}/usage?full=1 or the demo")
ap.add_argument("--rpc", default="https://api.avax-test.network/ext/bc/C/rpc")
a = ap.parse_args()

w3 = Web3(Web3.HTTPProvider(a.rpc))
escrow = w3.eth.contract(address=Web3.to_checksum_address(a.escrow), abi=load_abi())
jid = bytes.fromhex(a.job_id.removeprefix("0x"))
onchain_root = "0x" + escrow.functions.jobs(jid).call()[8].hex()
rec = UsageRecord.from_json(Path(a.usage).read_text())
local_root = rec.seal()["root"]
print(f"on-chain root {onchain_root}\nlocal root    {local_root}")
bad = []
for i in range(len(rec.entries)):
    p = rec.proof(i)
    if not escrow.functions.verifyUsageLeaf(jid, bytes.fromhex(p["leaf"][2:]), [bytes.fromhex(x[2:]) for x in p["proof"]]).call():
        bad.append(i)
print(f"{len(rec.entries) - len(bad)}/{len(rec.entries)} lines verify on-chain")
sys.exit(1 if bad or onchain_root != local_root else 0)
