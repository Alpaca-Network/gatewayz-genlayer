"""CostDispute v0.6.1: a leader's model judgment must have the exact honest shape.

A negative bucket used to pass the one-step tolerance (|-1 - 0| = 1) and then index
buckets[-1], the largest refund; extra fields used to be stored as returned."""

import copy

import pytest

from gzgl.shim import load_contract

C = load_contract("contracts/genlayer/cost_dispute.py")
POLICY = {"refund_buckets_bps": [0, 2500, 5000, 7500, 10000], "bucket_tolerance": 1}
LINE = {"line": 0, "content_ok": True, "det_bps": 0, "det_reason": "none",
        "category": "degenerate", "bucket": 2, "reason": "loops"}
MINE = {"error": "", "lines": [LINE]}


def _leader(**over):
    lead = copy.deepcopy(MINE)
    lead["lines"][0].update(over)
    return lead


def test_honest_leader_agrees():
    assert C.results_agree(POLICY, _leader(), MINE)
    assert C.results_agree(POLICY, _leader(bucket=3), MINE)  # within tolerance


@pytest.mark.parametrize("over", [
    {"bucket": -1},           # buckets[-1] = full refund
    {"bucket": 1.0},          # not an int
    {"bucket": True},         # bool is an int in Python
    {"bucket": "2"},          # string
    {"bucket": 5},            # past the last bucket
    {"bucket": 4},            # outside tolerance (2 -> 4)
    {"category": "free_money"},
    {"category": "none", "bucket": 1},
    {"reason": "x" * 281},
    {"reason": None},
    {"extra": "smuggled"},
])
def test_malformed_or_out_of_range_judgment_disagrees(over):
    assert not C.results_agree(POLICY, _leader(**over), MINE)


def test_missing_field_disagrees():
    lead = _leader()
    del lead["lines"][0]["reason"]
    assert not C.results_agree(POLICY, lead, MINE)
