"""gzgl.net GenLayer helpers: status mapping across genlayer-py versions, rollback and
address extraction, and gl_wait refusing anything short of an accepted, non-rolled-back tx."""

import pytest

from gzgl.net import GenLayerTxError, gl_contract_address, gl_rollback, gl_status, gl_wait


@pytest.mark.parametrize("tx,expected", [
    ({"status_name": "FINALIZED"}, "FINALIZED"),  # genlayer-py <= 0.18
    ({"lifecycle": {"state": "processing", "phase": "uninitialized"}}, "PENDING"),
    ({"lifecycle": {"state": "processing", "phase": "committing"}}, "COMMITTING"),
    ({"lifecycle": {"state": "decided", "outcome": "accepted"}}, "ACCEPTED"),
    ({"lifecycle": {"state": "decided", "outcome": "undetermined"}}, "UNDETERMINED"),
    ({"lifecycle": {"state": "decided", "outcome": "leader_timeout"}}, "LEADER_TIMEOUT"),
    ({"lifecycle": {"state": "decided", "outcome": "something_new"}}, "UNDETERMINED"),
    ({"lifecycle": {"state": "finalized"}}, "FINALIZED"),
    ({"lifecycle": {"state": "canceled"}}, "CANCELED"),
    ({}, "PENDING"),
])
def test_gl_status(tx, expected):
    assert gl_status(tx) == expected


def _receipt(result):
    return {"consensus_data": {"leader_receipt": [{"result": result}]}}


def test_gl_rollback():
    assert gl_rollback(_receipt({"status": "rollback", "payload": "submitter_not_allowed"})) == "submitter_not_allowed"
    assert gl_rollback(_receipt({"status": "return", "payload": "ok"})) is None
    assert gl_rollback({}) is None


def test_gl_contract_address():
    assert gl_contract_address({"data": {"contract_address": "0xabc"}}) == "0xabc"
    assert gl_contract_address({"tx_data_decoded": {"contract_address": "0xdef"}, "data": {}}) == "0xdef"
    assert gl_contract_address({"to_address": "0x123"}) == "0x123"
    with pytest.raises(GenLayerTxError):
        gl_contract_address({})


class FakeClient:
    def __init__(self, tx):
        self.tx, self.calls = tx, []

    def wait_for_transaction_receipt(self, **kw):
        self.calls.append(kw)
        return self.tx


def test_gl_wait_accepts_and_passes_through():
    tx = {"lifecycle": {"state": "decided", "outcome": "accepted"}, **_receipt({"status": "return"})}
    c = FakeClient(tx)
    assert gl_wait(c, "0x01") is tx
    assert c.calls[0]["wait_until"] == "decided" and c.calls[0]["full_transaction"] is True
    gl_wait(c, "0x01", finalized=True, interval=5000)
    assert c.calls[1]["wait_until"] == "finalized" and c.calls[1]["interval"] == 5000


@pytest.mark.parametrize("tx,msg", [
    ({"lifecycle": {"state": "decided", "outcome": "undetermined"}}, "ended UNDETERMINED"),
    ({"lifecycle": {"state": "canceled"}}, "ended CANCELED"),
    ({"lifecycle": {"state": "finalized"}, "result_name": "MAJORITY_DISAGREE"}, "without agreement"),
    ({"lifecycle": {"state": "decided", "outcome": "accepted"},
      **_receipt({"status": "rollback", "payload": "policy_not_allowed"})}, "rolled back: policy_not_allowed"),
])
def test_gl_wait_rejects(tx, msg):
    with pytest.raises(GenLayerTxError, match=msg):
        gl_wait(FakeClient(tx), "0x01")
