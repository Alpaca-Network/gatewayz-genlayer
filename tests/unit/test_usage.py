import pytest

from gzgl.usage import UsageRecord, canonical_entry, leaf_hash, merkle_proof, merkle_root, verify_proof


def entry(i, cost="0.0012"):
    return {"ts": f"2026-10-05T12:00:{i:02d}Z", "model": "openai/gpt-5-mini", "provider": "openai",
            "tokens_in": 100 + i, "tokens_out": 50 + i, "cost_usd": cost, "commit": "480fc938"}


@pytest.mark.parametrize("n", [1, 2, 3, 4, 5, 7, 8, 13])
def test_every_leaf_proves_against_root(n):
    leaves = [leaf_hash(entry(i)) for i in range(n)]
    root = merkle_root(leaves)
    for i in range(n):
        assert verify_proof(leaves[i], merkle_proof(leaves, i), root)


def test_tampered_entry_fails():
    rec = UsageRecord("0x" + "11" * 32)
    for i in range(5):
        rec.append(entry(i))
    p = rec.proof(2)
    forged = dict(p["entry"], tokens_out=999_999)
    assert not verify_proof(leaf_hash(forged), [bytes.fromhex(x[2:]) for x in p["proof"]],
                            bytes.fromhex(p["root"][2:]))


def test_cost_formatting_does_not_change_hash():
    assert canonical_entry(entry(0, "0.0012")) == canonical_entry(entry(0, "0.00120"))
    assert canonical_entry(entry(0, "0.0012")) == canonical_entry(entry(0, 0.0012))


def test_entry_rejects_content_fields():
    with pytest.raises(ValueError):
        canonical_entry({**entry(0), "prompt": "secret"})


def test_seal_totals():
    rec = UsageRecord("0x" + "11" * 32)
    rec.append(entry(0, "0.5"))
    rec.append(entry(1, "0.25"))
    s = rec.seal()
    assert s["requests"] == 2 and s["tokens_in"] == 201 and s["tokens_out"] == 101
    assert s["cost_usd"] == "0.75"
    assert UsageRecord.from_json(rec.to_json()).seal() == s


def test_empty_record_seals_to_zero_root():
    assert UsageRecord("0x" + "11" * 32).seal()["root"] == "0x" + "00" * 32


def test_matches_gatewayz_backend_fixture():
    # Pinned identically in gatewayz-backend tests/services/test_job_usage.py.
    rec = UsageRecord("0x" + "ab" * 32)
    costs = ["0.0123", "0.5", "1", "0.00001", "2.10"]
    for i in range(5):
        rec.append({"ts": f"2026-10-05T12:00:0{i}Z", "model": "anthropic/claude-sonnet-5", "provider": "anthropic",
                    "tokens_in": 1000 + i, "tokens_out": 400 + i, "cost_usd": costs[i], "commit": f"req-{i}"})
    assert rec.seal()["root"] == "0x9a4ae32bbe8b6ea2a179eb7a2957b58bab2e56e105ccf83fecfd0c8e31fabf8a"
