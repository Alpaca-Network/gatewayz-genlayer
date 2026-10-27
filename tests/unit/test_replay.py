"""Shadow replay flags exactly what the contract's content-free checks would refund."""

import json
from pathlib import Path

from gzgl import billing as b
from gzgl.replay import replay

ROOT = Path(__file__).resolve().parents[2]
FIX = json.loads((ROOT / "fixtures/usage-v2.json").read_text())
POLICY = json.loads((ROOT / "policies/fbp-v5.json").read_text())
SHEET = b.canonical_json(FIX["price_sheet"])


def _usage(entries):
    ep = b.Epoch("x")
    for e in entries:
        ep.append(e)
    return {"entries_v2": entries, "root_v2": ep.seal()["root"]}


def _fetch(h):
    assert h == FIX["price_sheet_hash"]
    return SHEET


def test_fixture_lines_pass():
    rep = replay(_usage([ln["entry"] for ln in FIX["lines"]]), POLICY, _fetch)
    assert rep["ok"] and rep["root_ok"] and rep["flagged"] == [], rep


def test_overcharge_is_flagged():
    e = dict(FIX["lines"][0]["entry"], cost_usd="0.01")  # ~500x the sheet price
    rep = replay(_usage([e]), POLICY, _fetch)
    assert rep["flagged"][0]["det_reason"] == "price_mismatch" and rep["flagged"][0]["det_bps"] > 0


def test_billed_failure_is_flagged():
    e = dict(FIX["lines"][0]["entry"], finish_reason="error")
    rep = replay(_usage([e]), POLICY, _fetch)
    assert rep["flagged"][0]["det_reason"] == "billed_failure"


def test_tampered_root_is_not_ok():
    u = _usage([ln["entry"] for ln in FIX["lines"]])
    u["root_v2"] = "0x" + "11" * 32
    rep = replay(u, POLICY, _fetch)
    assert not rep["ok"] and rep["root_ok"] is False


def test_sheet_that_does_not_hash_is_an_error():
    rep = replay(_usage([FIX["lines"][0]["entry"]]), POLICY, lambda h: SHEET + b" ")
    assert not rep["ok"] and rep["sheet_errors"][0]["error"] == "hash_mismatch"


def test_zero_sheet_is_reported_as_unlisted():
    e = dict(FIX["lines"][0]["entry"], price_sheet="0x" + "00" * 32)
    rep = replay(_usage([e]), POLICY, _fetch)
    assert rep["flagged"][0]["det_reason"] == "price_unlisted"


def test_no_v2_entries_is_not_ok():
    assert not replay({"entries": []}, POLICY, _fetch)["ok"]
