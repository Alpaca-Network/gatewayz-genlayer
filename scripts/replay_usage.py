"""Shadow replay of a job's sealed v2 usage lines (see gzgl/replay.py).

    python scripts/replay_usage.py --usage usage.json \
        [--sheets https://api.gatewayz.ai/v1/price-sheets/] [--policy policies/fbp-v5.json]

Prints one JSON line. Exit 0 when every line passes the contract's content-free
checks, 1 when a line is flagged or a price sheet is missing/mismatched, 2 on
bad input. Needs no key: price sheets are public.
"""

import argparse
import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gzgl.replay import replay  # noqa: E402

MAX_SHEET_BYTES = 128_000

ap = argparse.ArgumentParser()
ap.add_argument("--usage", required=True, help="GET /v1/jobs/{id}/usage?full=true output, or - for stdin")
ap.add_argument("--sheets", default="https://api.gatewayz.ai/v1/price-sheets/")
ap.add_argument("--policy", default=str(Path(__file__).resolve().parents[1] / "policies/fbp-v5.json"))
a = ap.parse_args()

try:
    usage = json.loads(sys.stdin.read() if a.usage == "-" else Path(a.usage).read_text())
    policy = json.loads(Path(a.policy).read_text())
except Exception as e:  # noqa: BLE001
    print(json.dumps({"ok": False, "error": f"bad input: {e}"}))
    sys.exit(2)


def fetch(h: str) -> bytes:
    req = urllib.request.Request(a.sheets + h, headers={"User-Agent": "gatewayz-genlayer replay"})
    with urllib.request.urlopen(req, timeout=20) as r:
        body = r.read(MAX_SHEET_BYTES + 1)
    if len(body) > MAX_SHEET_BYTES:
        raise ValueError("sheet too large")
    return body


rep = replay(usage, policy, fetch)
print(json.dumps(rep))
sys.exit(0 if rep["ok"] and not rep["flagged"] else 1)
