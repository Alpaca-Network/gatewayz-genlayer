"""fixtures/usage-v2.json is the contract with gatewayz-backend: it must keep matching gzgl/billing.py
and the CostDispute contract's own hashing and proof check."""

import json
from pathlib import Path

from gzgl import billing as b
from gzgl.shim import load_contract

CONTRACT = load_contract("contracts/genlayer/cost_dispute.py")
FIX = json.loads((Path(__file__).resolve().parents[2] / "fixtures/usage-v2.json").read_text())


def test_fixture_matches_reference_hashing():
    assert b.price_sheet_hash(FIX["price_sheet"]) == FIX["price_sheet_hash"]
    root = bytes.fromhex(FIX["root"][2:])
    for ln in FIX["lines"]:
        bundle = b.canonical_content(ln["messages"], ln["output"])
        assert bundle.decode() == ln["content_bundle_utf8"]
        assert b.sha256_hex(bundle) == ln["entry"]["content_hash"]
        assert b.canonical_entry(ln["entry"]).decode() == ln["canonical_entry_utf8"]
        assert "0x" + b.leaf_hash(ln["entry"]).hex() == ln["leaf"]
        assert CONTRACT.leaf_hash(ln["entry"]) == b.leaf_hash(ln["entry"])
        assert CONTRACT.verify_proof(b.leaf_hash(ln["entry"]), [bytes.fromhex(p[2:]) for p in ln["proof"]], root)
