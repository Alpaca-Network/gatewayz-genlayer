"""Direct-mode tests for contracts/genlayer/verify_job.py (no node, mocked web + LLM)."""

import hashlib
import json

import pytest
from eth_abi import decode as abi_decode

from gzgl.rubric import rubric_hash

CONTRACT = "contracts/genlayer/verify_job.py"
URL = "https://example.org/deliverables/job-1.md"
BODY = b"# Report\n\nThe three competitor prices are A=$10, B=$12, C=$9. Sources cited.\n"
BODY_HASH = "0x" + hashlib.sha256(BODY).hexdigest()
SPEC_URL = "https://example.org/specs/job-1.txt"
SPEC_BODY = b"Compare the prices of our three competitors A, B and C, with sources."
JOB = "0x" + "11" * 32
SPEC = "0x" + hashlib.sha256(SPEC_BODY).hexdigest()
ROOT = "0x" + "33" * 32
ESCROW = "0x" + "ab" * 20

RUBRIC = {
    "must_have": ["Lists prices for all three competitors", "Cites sources"],
    "nice_to_have": ["Gives a recommendation"],
    "hard_reject": ["Off-topic", "Truncated"],
    "pass_threshold": 70,
}


def llm(met=(True, True), hard=False, score=85, reasons=("complete",)):
    return json.dumps(
        {"must_have_met": list(met), "hard_reject_hit": hard, "score": score, "reasons": list(reasons)}
    )


@pytest.fixture
def setup(direct_vm, direct_deploy, direct_owner):
    direct_vm.sender = direct_owner
    c = direct_deploy(CONTRACT, "", 0, "")
    mock_sources(direct_vm)
    return c


def submit(c, job=JOB, rubric=RUBRIC, body_hash=BODY_HASH, url=URL, spec=SPEC, spec_url=SPEC_URL):
    return c.submit_case(job, spec_url, spec, url, body_hash, ROOT, json.dumps(rubric))


def mock_sources(vm, body=BODY, status=200):
    vm.mock_web(r"example\.org/specs/job-1\.txt", {"status": 200, "body": SPEC_BODY})
    vm.mock_web(r"example\.org/deliverables/job-1\.md", {"status": status, "body": body})


def test_pass_verdict(setup, direct_vm):
    direct_vm.mock_llm(r"impartial adjudicator", llm(score=88))
    v = submit(setup)
    assert v["pass"] is True
    assert v["score"] == 88
    assert v["status"] == "decided"
    assert v["usage_root"] == ROOT
    assert v["rubric_hash"] == rubric_hash(RUBRIC)
    assert setup.get_verdict(JOB)["pass"] is True
    assert setup.get_case_ids() == [JOB]


def test_pass_is_computed_not_trusted(setup, direct_vm):
    # High score but one must-have unmet => fail.
    direct_vm.mock_llm(r"impartial adjudicator", llm(met=(True, False), score=95))
    assert submit(setup)["pass"] is False


def test_hard_reject_fails(setup, direct_vm):
    direct_vm.mock_llm(r"impartial adjudicator", llm(hard=True, score=90))
    assert submit(setup)["pass"] is False


def test_below_threshold_fails(setup, direct_vm):
    direct_vm.mock_llm(r"impartial adjudicator", llm(score=69))
    assert submit(setup)["pass"] is False


def test_hash_mismatch_fails_without_llm(setup, direct_vm):
    direct_vm.mock_llm(r"impartial adjudicator", llm(score=99))
    v = submit(setup, body_hash="0x" + "00" * 32)
    assert v["pass"] is False and v["score"] == 0
    assert v["reasons"] == ["deliverable_hash_mismatch"]


def test_fetch_failure_fails(direct_vm, direct_deploy, direct_owner):
    direct_vm.sender = direct_owner
    c = direct_deploy(CONTRACT, "", 0, "")
    mock_sources(direct_vm, body=b"nope", status=404)
    v = submit(c)
    assert v["pass"] is False and v["reasons"] == ["deliverable_fetch_failed"]


def test_spec_hash_mismatch_fails_without_llm(setup, direct_vm):
    direct_vm.mock_llm(r"impartial adjudicator", llm(score=99))
    v = submit(setup, spec="0x" + "44" * 32)
    assert v["pass"] is False and v["reasons"] == ["spec_hash_mismatch"]


def test_prompt_contains_spec(setup, direct_vm):
    direct_vm.mock_llm(r"<<<SPEC_START>>>\s*Compare the prices of our three competitors[\s\S]*<<<SPEC_END>>>", llm())
    assert submit(setup)["pass"] is True


def test_prompt_fences_untrusted_deliverable(setup, direct_vm):
    direct_vm.mock_llm(r"<<<DELIVERABLE_START>>>[\s\S]*Sources cited[\s\S]*<<<DELIVERABLE_END>>>", llm())
    submit(setup)  # the mock only matches if the deliverable sits inside the fence


def test_one_case_per_job(setup, direct_vm):
    direct_vm.mock_llm(r"impartial adjudicator", llm())
    submit(setup)
    with direct_vm.expect_revert("case_exists"):
        submit(setup)
    # case ids are normalised, so upper-case hex is the same job
    with direct_vm.expect_revert("case_exists"):
        submit(setup, job=JOB.upper().replace("0X", "0x"))


def test_only_allowlisted_submitters(setup, direct_vm, direct_alice, direct_owner):
    direct_vm.mock_llm(r"impartial adjudicator", llm())
    direct_vm.sender = direct_alice
    with direct_vm.expect_revert("submitter_not_allowed"):
        submit(setup)
    with direct_vm.expect_revert("only_owner"):
        setup.set_submitter(direct_alice.as_hex, True)
    direct_vm.sender = direct_owner
    setup.set_submitter(direct_alice.as_hex, True)
    direct_vm.sender = direct_alice
    assert submit(setup)["pass"] is True


@pytest.mark.parametrize(
    "rubric,err",
    [
        ({**RUBRIC, "must_have": []}, "must_have is empty"),
        ({**RUBRIC, "pass_threshold": 101}, "pass_threshold"),
        ({**RUBRIC, "pass_threshold": True}, "pass_threshold"),
        ({**RUBRIC, "score_tolerance": 80}, "score_tolerance"),
        ({**RUBRIC, "surprise": 1}, "unknown field"),
        ({**RUBRIC, "must_have": ["x" * 301]}, "must_have item"),
    ],
)
def test_rubric_validation(setup, direct_vm, rubric, err):
    with direct_vm.expect_revert("rubric_invalid: " + err):
        submit(setup, rubric=rubric)


@pytest.mark.parametrize("field", ["job", "body_hash", "spec"])
def test_rejects_malformed_hashes(setup, direct_vm, field):
    with direct_vm.expect_revert("invalid_"):
        submit(setup, **{field: "0x1234"})


def test_rejects_non_https_uri(setup, direct_vm):
    with direct_vm.expect_revert("invalid_deliverable_uri"):
        submit(setup, url="http://example.org/deliverables/job-1.md")
    with direct_vm.expect_revert("invalid_spec_uri"):
        submit(setup, spec_url="http://example.org/specs/job-1.txt")


# ------------------------------------------------------------- consensus


def test_validator_agrees_within_tolerance(setup, direct_vm):
    direct_vm.mock_llm(r"impartial adjudicator", llm(score=80))
    submit(setup)
    direct_vm.clear_mocks()
    mock_sources(direct_vm)
    direct_vm.mock_llm(r"impartial adjudicator", llm(score=94))  # 14 apart, default tolerance 15
    assert direct_vm.run_validator() is True


def test_validator_disagrees_outside_tolerance(setup, direct_vm):
    direct_vm.mock_llm(r"impartial adjudicator", llm(score=75))
    submit(setup)
    direct_vm.clear_mocks()
    mock_sources(direct_vm)
    direct_vm.mock_llm(r"impartial adjudicator", llm(score=95))
    assert direct_vm.run_validator() is False


def test_validator_disagrees_on_pass_even_with_close_scores(setup, direct_vm):
    direct_vm.mock_llm(r"impartial adjudicator", llm(score=71))  # pass
    submit(setup)
    direct_vm.clear_mocks()
    mock_sources(direct_vm)
    direct_vm.mock_llm(r"impartial adjudicator", llm(score=68))  # fail, 3 apart
    assert direct_vm.run_validator() is False


def test_validator_rejects_forged_leader_result(setup, direct_vm):
    direct_vm.mock_llm(r"impartial adjudicator", llm(score=30, met=(False, False)))
    submit(setup)
    assert direct_vm.run_validator(leader_result={"passed": True, "score": 30, "reasons": []}) is False


def test_validator_rejects_leader_error(setup, direct_vm):
    direct_vm.mock_llm(r"impartial adjudicator", llm())
    submit(setup)
    assert direct_vm.run_validator(leader_error=Exception("boom")) is False


def test_custom_tolerance_is_honoured(setup, direct_vm):
    direct_vm.mock_llm(r"impartial adjudicator", llm(score=80))
    submit(setup, rubric={**RUBRIC, "score_tolerance": 5})
    direct_vm.clear_mocks()
    mock_sources(direct_vm)
    direct_vm.mock_llm(r"impartial adjudicator", llm(score=86))
    assert direct_vm.run_validator() is False


# ------------------------------------------------------------- bridge payload


def test_verdict_payload_matches_escrow_abi(setup, direct_vm):
    direct_vm.mock_llm(r"impartial adjudicator", llm(score=88))
    submit(setup)
    payload = setup.verdict_payload(JOB)
    job, passed, score, root, spec, rh = abi_decode(
        ["bytes32", "bool", "uint8", "bytes32", "bytes32", "bytes32"], bytes(payload)
    )
    assert "0x" + job.hex() == JOB
    assert passed is True and score == 88
    assert "0x" + root.hex() == ROOT
    assert "0x" + spec.hex() == SPEC
    assert "0x" + rh.hex() == rubric_hash(RUBRIC)


def test_relay_requires_route(setup, direct_vm):
    direct_vm.mock_llm(r"impartial adjudicator", llm())
    submit(setup)
    with direct_vm.expect_revert("bridge_not_configured"):
        setup.relay_verdict(JOB)
    with direct_vm.expect_revert("case_not_found"):
        setup.relay_verdict("0x" + "99" * 32)


def test_route_is_owner_only(setup, direct_vm, direct_alice):
    direct_vm.sender = direct_alice
    with direct_vm.expect_revert("only_owner"):
        setup.set_route("0x" + "cd" * 20, 40106, ESCROW)
