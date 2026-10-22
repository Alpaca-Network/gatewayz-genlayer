"""Ledger escrow: money states, verdict application, conservation (gzgl/ledger.py)."""

import random

import pytest

from gzgl import billing as b
from gzgl.ledger import DAY, NANO, EscrowTerms, Ledger, LedgerError

POLICY = "0x" + "ab" * 32
EPOCH = "0x" + "e1" * 32
T0 = 1_800_000_000
TERMS = EscrowTerms(open_providers=frozenset({"gatewayz-gpu"}), underwritten_models=frozenset({"openai/gpt-5-mini"}),
                    allowed_policies=frozenset({POLICY}), refund_cap_nano=50 * NANO)


def entry(i, cost="0.40", provider="gatewayz-gpu", model="meta/llama-4"):
    return {"request_id": f"r{i}", "ts": "2026-10-22T00:00:00Z", "model": model, "provider": provider,
            "tokens_in": 10, "tokens_out": 10, "tokens_reasoning": 0, "cost_usd": cost, "status": 200,
            "finish_reason": "stop", "price_sheet": "0x" + "00" * 32, "content_hash": "0x" + "11" * 32, "commit": "x"}


def build(entries, terms=TERMS, deposit="100"):
    led, ep = Ledger(terms), b.Epoch(EPOCH)
    led.deposit("u", deposit)
    for e in entries:
        assert led.charge(EPOCH, "u", e) == len(ep.entries)
        ep.append(e)
    root = ep.seal()["root"]
    led.close_epoch(EPOCH, root, T0)
    return led, root


def verdict(root, rows, dispute="0xd1", policy=POLICY):
    """rows: [(line, billed_usd, refund_bps)], amounts computed as the contract does."""
    lines = [{"line": i, "billed_usd": usd, "refund_bps": bps,
              "refund_usd": b.nano_to_usd(b.to_nano(usd) * bps // 10_000)} for i, usd, bps in rows]
    return {"dispute_id": dispute, "epoch_id": EPOCH, "usage_root": root, "policy_hash": policy, "lines": lines}


def test_undisputed_epoch_pays_providers_after_the_window():
    led, _ = build([entry(0), entry(1, model="openai/gpt-5-mini", provider="openai")])
    with pytest.raises(LedgerError, match="window_open"):
        led.finalize_epoch(EPOCH, T0 + 3 * DAY - 1)
    assert led.finalize_epoch(EPOCH, T0 + 3 * DAY) == b.to_nano("0.80")
    bal = led.balances()
    assert bal["provider:gatewayz-gpu:payable"] == b.to_nano("0.40")
    assert bal["gatewayz:upstream"] == b.to_nano("0.40")
    # escrow fee: 1% for provider-backed, 10% for reserve-backed lines
    assert bal["gatewayz:reserve"] == b.to_nano("0.004") + b.to_nano("0.04")
    assert "user:u:pending" not in bal


def test_provider_line_refund_never_reaches_the_provider():
    led, root = build([entry(0), entry(1)])
    bond = led.open_dispute("0xd1", EPOCH, [1], T0 + DAY)
    assert bond == NANO  # max($1, 10% of 0.40)
    assert led.finalize_epoch(EPOCH, T0 + 3 * DAY) == b.to_nano("0.40")  # line 0 only; line 1 stays held
    assert led.apply_verdict(verdict(root, [(1, "0.4", 7_500)])) == b.to_nano("0.30")
    bal = led.balances()
    assert bal["provider:gatewayz-gpu:payable"] == b.to_nano("0.50")
    assert bal["user:u:available"] == b.to_nano("100") - b.to_nano("0.80") - b.to_nano("0.008") + b.to_nano("0.30")
    assert "user:u:held" not in bal and "user:u:bond" not in bal


def test_underwritten_line_refund_comes_out_of_the_reserve():
    led, root = build([entry(0, model="openai/gpt-5-mini", provider="openai")])
    led.open_dispute("0xd1", EPOCH, [0], T0)
    led.apply_verdict(verdict(root, [(0, "0.4", 10_000)]))
    bal = led.balances()
    assert bal["gatewayz:reserve"] == b.to_nano("0.04") - b.to_nano("0.40")  # negative: reserve shortfall shows
    assert bal["gatewayz:upstream"] == b.to_nano("0.40")  # the reserve made Gatewayz whole for the lab bill


def test_lost_dispute_forfeits_the_bond():
    led, root = build([entry(0)])
    led.open_dispute("0xd1", EPOCH, [0], T0)
    assert led.apply_verdict(verdict(root, [(0, "0.4", 0)])) == 0
    assert led.balances()["gatewayz:fees"] == NANO
    with pytest.raises(LedgerError, match="dispute_settled"):
        led.apply_verdict(verdict(root, [(0, "0.4", 0)]))


def test_unescrowed_lines_cannot_be_disputed():
    led, _ = build([entry(0, provider="anthropic", model="anthropic/claude")])
    assert led.balances()["gatewayz:upstream"] == b.to_nano("0.40")
    with pytest.raises(LedgerError, match="line_not_escrowed"):
        led.open_dispute("0xd1", EPOCH, [0], T0)


@pytest.mark.parametrize("when,ok", [(T0 + 3 * DAY - 1, True), (T0 + 3 * DAY, False)])
def test_challenge_window(when, ok):
    led, _ = build([entry(0)])
    if ok:
        led.open_dispute("0xd1", EPOCH, [0], when)
    else:
        with pytest.raises(LedgerError, match="dispute_window_closed"):
            led.open_dispute("0xd1", EPOCH, [0], when)


def test_lines_are_disputed_once_and_need_credit_for_the_bond():
    led, _ = build([entry(0), entry(1)], deposit="1.9")  # 0.808 billed, $1 bond leaves 0.092
    led.open_dispute("0xd1", EPOCH, [0], T0)
    with pytest.raises(LedgerError, match="line_already_disputed"):
        led.open_dispute("0xd2", EPOCH, [0], T0)
    with pytest.raises(LedgerError, match="insufficient_credit"):
        led.open_dispute("0xd2", EPOCH, [1], T0)


@pytest.mark.parametrize("mutate,err", [
    (lambda v: v.update(usage_root="0x" + "00" * 32), "epoch"),
    (lambda v: v.update(policy_hash="0x" + "cd" * 32), "policy"),
    (lambda v: v["lines"].pop(), "lines"),
    (lambda v: v["lines"][0].update(billed_usd="0.39"), "line 0"),
    (lambda v: v["lines"][0].update(refund_usd="0.4"), "line 0"),
])
def test_verdict_must_match_the_dispute(mutate, err):
    led, root = build([entry(0), entry(1)])
    led.open_dispute("0xd1", EPOCH, [0, 1], T0)
    v = verdict(root, [(0, "0.4", 5_000), (1, "0.4", 0)])
    mutate(v)
    with pytest.raises(LedgerError, match="verdict_mismatch: " + err):
        led.apply_verdict(v)
    assert led.balances()["user:u:held"] == b.to_nano("0.80")  # nothing moved


def test_refund_cap_limits_payout_but_a_winner_keeps_the_bond():
    terms = EscrowTerms(open_providers=TERMS.open_providers, allowed_policies=TERMS.allowed_policies, refund_cap_nano=b.to_nano("0.5"))
    led, root = build([entry(0), entry(1)], terms=terms)
    led.open_dispute("0xd1", EPOCH, [0, 1], T0)
    assert led.apply_verdict(verdict(root, [(0, "0.4", 10_000), (1, "0.4", 10_000)])) == b.to_nano("0.5")
    bal = led.balances()
    assert bal["provider:gatewayz-gpu:payable"] == b.to_nano("0.30")
    assert "gatewayz:fees" not in bal


def test_overdue_disputes_are_reported_not_settled():
    led, _ = build([entry(0)])
    led.open_dispute("0xd1", EPOCH, [0], T0)
    assert led.overdue_disputes(T0 + 2 * DAY - 1) == []
    assert led.overdue_disputes(T0 + 2 * DAY) == ["0xd1"]
    assert led.balances()["user:u:held"] == b.to_nano("0.40")


def test_random_flows_keep_balances_sane():
    rng = random.Random(7)
    for trial in range(200):
        n = rng.randint(1, 8)
        es = [entry(i, cost=f"0.{rng.randint(1, 99):02d}", provider=rng.choice(["gatewayz-gpu", "openai", "anthropic"]),
                    model=rng.choice(["meta/llama-4", "openai/gpt-5-mini"])) for i in range(n)]
        led, root = build(es)
        escrowed = [i for i, ln in enumerate(led.epochs[EPOCH].lines) if ln.clawback]
        picked = rng.sample(escrowed, rng.randint(0, len(escrowed))) if escrowed else []
        if picked:
            led.open_dispute("0xd1", EPOCH, picked, T0)
        led.finalize_epoch(EPOCH, T0 + 3 * DAY)
        if picked:
            led.apply_verdict(verdict(root, [(i, es[i]["cost_usd"], rng.choice([0, 2500, 5000, 7500, 10000])) for i in sorted(picked)]))
        bal = led.balances()
        assert sum(bal.values()) == 0
        assert not [k for k, v in bal.items() if v < 0 and k not in ("external:card", "gatewayz:reserve")], trial
        assert not [k for k in bal if k.endswith((":pending", ":held", ":bond"))], trial


class FakeClient:
    def __init__(self, tx, state):
        self.tx, self.state = tx, state

    def get_transaction(self, transaction_hash):
        return self.tx

    def read_contract(self, address, function_name, args, transaction_hash_variant):
        assert function_name == "get_dispute" and "FINAL" in str(transaction_hash_variant)
        return self.state


@pytest.mark.parametrize("tx,expect", [
    (None, None),
    ({"status_name": "ACCEPTED", "to_address": "0xC"}, None),
    ({"status_name": "FINALIZED", "result_name": "MAJORITY_AGREE", "to_address": "0xc"}, "verdict"),
    ({"status_name": "FINALIZED", "result_name": "MAJORITY_DISAGREE", "to_address": "0xC"}, "without agreement"),
    ({"status_name": "FINALIZED", "to_address": "0xD"}, "not CostDispute"),
])
def test_dispute_verdicts_are_read_only_once_finalized(tx, expect):
    from gzgl.relayer import CostDisputeVerdicts, VerdictError

    src = CostDisputeVerdicts(FakeClient(tx, {"dispute_id": "0xD1"}), "0xC")
    if expect is None:
        assert src.finalized_verdict("0xd1", "0xt") is None
    elif expect == "verdict":
        assert src.finalized_verdict("0xd1", "0xt") == {"dispute_id": "0xD1"}
    else:
        with pytest.raises(VerdictError, match=expect):
            src.finalized_verdict("0xd1", "0xt")
