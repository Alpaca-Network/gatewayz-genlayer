"""Escrow + relayer + usage proofs against a real local EVM (anvil), GenLayer faked.

Proves the pieces fit: the ABI the relayer uses, the Python Merkle root vs the
Solidity verifier, and the escrow's money movement after a relayed verdict."""

import json
import shutil
import socket
import subprocess
import time
from pathlib import Path

import pytest
from web3 import Web3

from gzgl.relayer import Relayer, VerdictError
from gzgl.rubric import rubric_hash
from gzgl.usage import UsageRecord

ROOT = Path(__file__).resolve().parents[2]
ARTIFACT = ROOT / "contracts/evm/out/InferenceEscrow.sol/InferenceEscrow.json"
# anvil's well-known dev keys (public test mnemonic — never funded anywhere real)
KEYS = [
    "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80",
    "0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d",
    "0x5de4111afa1a4b94908f83103eb1f1706367c2e68ca870fc3fb9a804cdab365a",
    "0x7c852118294e51e653712a81e05800f419141751be58f605c371e15141b007a6",
]
RUBRIC = {"must_have": ["Answers the question"], "pass_threshold": 70}
SPEC = "0x" + "22" * 32
GL_TX = "0x" + "ee" * 32

pytestmark = pytest.mark.skipif(not shutil.which("anvil") or not ARTIFACT.exists(), reason="needs anvil + forge build")


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


@pytest.fixture
def chain():
    port = _free_port()
    proc = subprocess.Popen(["anvil", "--port", str(port), "--silent"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    w3 = Web3(Web3.HTTPProvider(f"http://127.0.0.1:{port}"))
    for _ in range(50):
        if w3.is_connected():
            break
        time.sleep(0.1)
    yield w3
    proc.terminate()
    proc.wait()


def send(w3, key, fn, value=0):
    acct = w3.eth.account.from_key(key)
    tx = fn.build_transaction({"from": acct.address, "value": value, "nonce": w3.eth.get_transaction_count(acct.address)})
    h = w3.eth.send_raw_transaction(acct.sign_transaction(tx).raw_transaction)
    r = w3.eth.wait_for_transaction_receipt(h)
    assert r["status"] == 1
    return r


class FakeGenLayer:
    def __init__(self):
        self.verdicts = {}

    def finalized_verdict(self, job_id, gl_tx):
        v = self.verdicts.get(job_id)
        if isinstance(v, Exception):
            raise v
        return v


@pytest.fixture
def world(chain, tmp_path):
    w3 = chain
    deployer, relayer_key, buyer_key, seller_key = KEYS
    art = json.loads(ARTIFACT.read_text())
    treasury = w3.eth.account.create().address
    relayer_addr = w3.eth.account.from_key(relayer_key).address
    verify_ic = "0x" + "ab" * 20
    C = w3.eth.contract(abi=art["abi"], bytecode=art["bytecode"]["object"])
    r = send(w3, deployer, C.constructor(treasury, 250, 6 * 3600, relayer_addr, "0x" + "00" * 20, 61998, Web3.to_checksum_address(verify_ic)))
    escrow = w3.eth.contract(address=r["contractAddress"], abi=art["abi"])
    gl = FakeGenLayer()
    rel = Relayer(w3, escrow.address, relayer_key, gl, tmp_path / "state.json")
    return dict(w3=w3, escrow=escrow, gl=gl, rel=rel, treasury=treasury,
                buyer=buyer_key, seller=w3.eth.account.from_key(seller_key).address)


def open_job(world, job_id, amount=Web3.to_wei(1, "ether")):
    w3, escrow = world["w3"], world["escrow"]
    deadline = w3.eth.get_block("latest")["timestamp"] + 48 * 3600
    send(w3, world["buyer"], escrow.functions.openJob(bytes.fromhex(job_id[2:]), world["seller"], deadline,
                                                     bytes.fromhex(SPEC[2:]), bytes.fromhex(rubric_hash(RUBRIC)[2:])), value=amount)


def usage(job_id, n=5):
    rec = UsageRecord(job_id)
    for i in range(n):
        rec.append({"ts": f"2026-10-05T12:00:0{i}Z", "model": "anthropic/claude-sonnet-5", "provider": "anthropic",
                    "tokens_in": 1000 + i, "tokens_out": 400, "cost_usd": "0.0123", "commit": "abc1234"})
    return rec


def verdict(job_id, passed, root, score=88):
    return {"job_id": job_id, "pass": passed, "score": score, "usage_root": root,
            "spec_hash": SPEC, "rubric_hash": rubric_hash(RUBRIC)}


def test_pass_settles_and_usage_proves_onchain(world):
    job = "0x" + "01" * 32
    open_job(world, job)
    rec = usage(job)
    sealed = rec.seal()
    rel = world["rel"]
    rel.register(job, GL_TX)

    assert rel.tick() == []  # not finalized yet -> nothing happens
    assert rel.job(job)["status"] == "Funded"

    world["gl"].verdicts[job] = verdict(job, True, sealed["root"])
    [s] = rel.tick()
    assert s.passed and s.score == 88
    j = rel.job(job)
    assert j["status"] == "Paid"
    assert "0x" + j["verdictRef"].hex() == GL_TX
    assert world["escrow"].functions.credits(world["seller"]).call() == Web3.to_wei(0.975, "ether")
    assert world["escrow"].functions.credits(world["treasury"]).call() == Web3.to_wei(0.025, "ether")

    # Every usage line verifies against the root now stored ON-CHAIN, and a forged one doesn't.
    for i in range(len(rec.entries)):
        p = rec.proof(i)
        ok = world["escrow"].functions.verifyUsageLeaf(
            bytes.fromhex(job[2:]), bytes.fromhex(p["leaf"][2:]), [bytes.fromhex(x[2:]) for x in p["proof"]]).call()
        assert ok, i
    forged = usage(job)
    forged.entries[2]["tokens_out"] = 1
    p = forged.proof(2)
    assert not world["escrow"].functions.verifyUsageLeaf(
        bytes.fromhex(job[2:]), bytes.fromhex(p["leaf"][2:]), [bytes.fromhex(x[2:]) for x in p["proof"]]).call()

    assert rel.tick() == []  # idempotent


def test_fail_refunds_buyer(world):
    job = "0x" + "02" * 32
    open_job(world, job)
    world["rel"].register(job, GL_TX)
    world["gl"].verdicts[job] = verdict(job, False, usage(job).seal()["root"], score=30)
    [s] = world["rel"].tick()
    assert not s.passed
    buyer = world["w3"].eth.account.from_key(world["buyer"]).address
    assert world["escrow"].functions.credits(buyer).call() == Web3.to_wei(1, "ether")


def test_verdict_against_other_rubric_is_not_sent(world):
    job = "0x" + "03" * 32
    open_job(world, job)
    world["rel"].register(job, GL_TX)
    v = verdict(job, True, usage(job).seal()["root"])
    v["rubric_hash"] = "0x" + "99" * 32
    world["gl"].verdicts[job] = v
    assert world["rel"].tick() == []
    state = json.loads(world["rel"].state_path.read_text())
    assert "rubric" in state[job]["error"]
    assert world["rel"].job(job)["status"] == "Funded"


def test_dead_case_is_parked_not_retried(world):
    job = "0x" + "04" * 32
    open_job(world, job)
    world["rel"].register(job, GL_TX)
    world["gl"].verdicts[job] = VerdictError("case tx ended UNDETERMINED")
    assert world["rel"].tick() == []
    assert "UNDETERMINED" in json.loads(world["rel"].state_path.read_text())[job]["error"]


def test_register_refuses_to_swap_case_tx(world):
    job = "0x" + "05" * 32
    world["rel"].register(job, GL_TX)
    with pytest.raises(ValueError):
        world["rel"].register(job, "0x" + "ff" * 32)


def test_wrong_key_refuses_to_start(world, tmp_path):
    with pytest.raises(RuntimeError, match="escrow relayer is"):
        Relayer(world["w3"], world["escrow"].address, KEYS[2], world["gl"], tmp_path / "s.json")


# ------------------------------------------------------------- GenLayer reader


class FakeClient:
    def __init__(self, tx, verdict=None):
        self.tx, self.verdict, self.reads = tx, verdict, []

    def get_transaction(self, transaction_hash):
        return self.tx

    def read_contract(self, **kw):
        self.reads.append(kw)
        return self.verdict


VJ = "0x85685b7504d0F88fCBD336170366FC5969EC3502"
JOB = "0x" + "07" * 32


def _tx(**over):
    return {"status_name": "FINALIZED", "result_name": "MAJORITY_AGREE", "to_address": VJ,
            "tx_execution_result_name": None, **over}


def test_reader_waits_until_finalized():
    from gzgl.relayer import GenLayerVerdicts
    c = FakeClient(_tx(status_name="ACCEPTED"))
    assert GenLayerVerdicts(c, VJ).finalized_verdict(JOB, GL_TX) is None
    assert c.reads == []


def test_reader_reads_final_state_only():
    from genlayer_py.types import TransactionHashVariant
    from gzgl.relayer import GenLayerVerdicts
    c = FakeClient(_tx(), {"job_id": JOB, "pass": True})
    assert GenLayerVerdicts(c, VJ).finalized_verdict(JOB, GL_TX)["pass"] is True
    assert c.reads[0]["transaction_hash_variant"] == TransactionHashVariant.LATEST_FINAL


@pytest.mark.parametrize("over,msg", [
    ({"status_name": "UNDETERMINED"}, "UNDETERMINED"),
    ({"result_name": "MAJORITY_DISAGREE"}, "without agreement"),
    ({"to_address": "0x" + "12" * 20}, "not VerifyJob"),
    ({"tx_execution_result_name": "FINISHED_WITH_ERROR"}, "with error"),
])
def test_reader_rejects_unusable_case_tx(over, msg):
    from gzgl.relayer import GenLayerVerdicts
    with pytest.raises(VerdictError, match=msg):
        GenLayerVerdicts(FakeClient(_tx(**over), {"job_id": JOB}), VJ).finalized_verdict(JOB, GL_TX)


def test_reader_rejects_verdict_for_other_job():
    from gzgl.relayer import GenLayerVerdicts
    with pytest.raises(VerdictError, match="job_id mismatch"):
        GenLayerVerdicts(FakeClient(_tx(), {"job_id": "0x" + "08" * 32}), VJ).finalized_verdict(JOB, GL_TX)
