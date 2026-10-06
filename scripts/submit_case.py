"""Open and adjudicate a VerifyJob case, wait for consensus, print the verdict.

    python scripts/submit_case.py --network studionet --job-id 0x.. --spec-uri https://... \
        --deliverable-uri https://... --rubric rubrics/written.json [--usage-root 0x..] [--finalized]

The deliverable hash is computed from the bytes served at --deliverable-uri right now;
validators fetch the same URL and fail the case if the bytes change.
"""

import argparse
import hashlib
import json
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gzgl.net import DEPLOYMENTS, genlayer_client  # noqa: E402

from genlayer_py.types import TransactionStatus  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--network", default="studionet")
ap.add_argument("--job-id", required=True)
ap.add_argument("--spec-uri", required=True)
ap.add_argument("--deliverable-uri", required=True)
ap.add_argument("--rubric", required=True)
ap.add_argument("--usage-root", default="0x" + "00" * 32)
ap.add_argument("--finalized", action="store_true", help="wait for FINALIZED (appeal window closed), not just ACCEPTED")
a = ap.parse_args()

dep = json.loads((DEPLOYMENTS / f"{a.network}.json").read_text())
body = urllib.request.urlopen(urllib.request.Request(a.deliverable_uri, headers={"User-Agent": "gzgl"}), timeout=30).read()
dhash = "0x" + hashlib.sha256(body).hexdigest()
spec_hash = "0x" + hashlib.sha256(urllib.request.urlopen(urllib.request.Request(a.spec_uri, headers={"User-Agent": "gzgl"}), timeout=30).read()).hexdigest()
rubric = Path(a.rubric).read_text()
print(f"deliverable {len(body)} bytes sha256 {dhash}")

client = genlayer_client(a.network)
t0 = time.time()
tx = client.write_contract(
    address=dep["verify_job"], function_name="submit_case",
    args=[a.job_id, a.spec_uri, spec_hash, a.deliverable_uri, dhash, a.usage_root, rubric],
)
print("case tx", tx)
status = TransactionStatus.FINALIZED if a.finalized else TransactionStatus.ACCEPTED
r = client.wait_for_transaction_receipt(transaction_hash=tx, status=status, retries=600, interval=5000)
print(f"{status.value} after {time.time() - t0:.0f}s; execution: {r.get('tx_execution_result_name')}")
verdict = client.read_contract(address=dep["verify_job"], function_name="get_verdict", args=[a.job_id])
verdict = dict(verdict, genlayer_tx=tx)
print(json.dumps(verdict, indent=2, default=str))
