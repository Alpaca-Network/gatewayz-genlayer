"""Shadow replay: run sealed v2 usage lines through the CostDispute contract's own
deterministic checks, before any user disputes them.

The checks are loaded from contracts/genlayer/cost_dispute.py through the shim, so
this is the code validators run, not a copy. Content is never revealed here, so
only the content-free checks apply: billed failure, price mismatch against the
line's price sheet, unlisted price. A hit means either a backend billing bug or a
line a user would win a refund on; both should be seen before money moves.

    report = replay(usage, policy, fetch_sheet)

`usage` is GET /v1/jobs/{id}/usage?full=true from gatewayz-backend (needs
`entries_v2` and `root_v2`); `fetch_sheet(hash) -> bytes` returns a price sheet's
exact served bytes.
"""

from __future__ import annotations

import json
from collections.abc import Callable

from gzgl import billing as b
from gzgl.shim import load_contract

_C = load_contract("contracts/genlayer/cost_dispute.py")
ZERO = "0x" + "00" * 32


def replay(usage: dict, policy: dict, fetch_sheet: Callable[[str], bytes]) -> dict:
    entries = usage.get("entries_v2")
    if entries is None:
        return {"ok": False, "error": "no v2 entries (job predates v2, or JOB_USAGE_V2_ENABLED is off)"}
    report: dict = {"ok": True, "lines": len(entries), "flagged": [], "sheet_errors": [], "root_ok": None}

    if entries:
        local_root = "0x" + b.merkle_root([b.leaf_hash(e) for e in entries]).hex()
    else:
        local_root = ZERO
    claimed = usage.get("root_v2")
    if claimed:
        report["root_ok"] = claimed == local_root
        if not report["root_ok"]:
            report["ok"] = False
            report["error"] = f"root_v2 {claimed} != recomputed {local_root}"

    sheets: dict[str, dict | None] = {}
    for seq, entry in enumerate(entries):
        h = str(entry.get("price_sheet", "")).lower()
        if h not in sheets:
            sheets[h] = None
            if h != ZERO:
                try:
                    body = fetch_sheet(h)
                    if b.sha256_hex(body) != h:
                        report["sheet_errors"].append({"sheet": h, "error": "hash_mismatch"})
                    else:
                        sheets[h] = json.loads(body)
                except Exception as e:  # noqa: BLE001 -- reported, never swallowed
                    report["sheet_errors"].append({"sheet": h, "error": str(e)[:200]})
        det = _C.deterministic_check(policy, sheets[h] or {}, entry, None)
        if det["det_bps"] > 0 or det["det_reason"] != "none" or sheets[h] is None:
            report["flagged"].append(
                {
                    "seq": seq,
                    "request_id": entry.get("request_id"),
                    "model": entry.get("model"),
                    "det_bps": det["det_bps"],
                    "det_reason": det["det_reason"] if sheets[h] is not None else "price_unlisted",
                }
            )
    if report["sheet_errors"]:
        report["ok"] = False
    return report
