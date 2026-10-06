"""Relayer — the fallback verdict-delivery path (PRD Feature 3, "Fallback").

Watches jobs whose VerifyJob case was submitted on GenLayer. Once the case
transaction is FINALIZED (appeal window closed), it reads the verdict from FINALIZED
contract state and calls InferenceEscrow.settle() with the GenLayer tx hash as
verdictRef.

The relayer cannot invent a verdict: it only forwards what VerifyJob stored, and
anyone can re-check a settlement by reading get_verdict(job_id) on GenLayer and
comparing it to the JobSettled event. The escrow still checks spec and rubric hashes.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from web3 import Web3

log = logging.getLogger("gzgl.relayer")

ABI_PATH = Path(__file__).parent / "abi" / "InferenceEscrow.json"
STATUS = {0: "None", 1: "Funded", 2: "Paid", 3: "Refunded"}


class VerdictError(RuntimeError):
    """The case transaction exists but can never yield a usable verdict."""


class VerdictSource(Protocol):
    def finalized_verdict(self, job_id: str, gl_tx: str) -> dict | None: ...


class GenLayerVerdicts:
    """Reads verdicts from a deployed VerifyJob, finalized state only."""

    def __init__(self, client, verify_address: str):
        self.client = client
        self.verify_address = verify_address

    def finalized_verdict(self, job_id: str, gl_tx: str) -> dict | None:
        from genlayer_py.types import TransactionHashVariant

        tx = self.client.get_transaction(transaction_hash=gl_tx)
        if tx is None:
            return None
        status = str(tx.get("status_name") or "")
        if status in ("CANCELED", "UNDETERMINED", "VALIDATORS_TIMEOUT"):
            raise VerdictError(f"case tx {gl_tx} ended {status}")
        if status != "FINALIZED":
            return None
        result = tx.get("result_name")
        if result is not None and str(result) not in ("AGREE", "MAJORITY_AGREE"):
            raise VerdictError(f"case tx {gl_tx} finalized without agreement ({result})")
        if tx.get("tx_execution_result_name") not in (None, "FINISHED_WITH_RETURN"):
            raise VerdictError(f"case tx {gl_tx} finished with error")
        to = str(tx.get("to_address") or tx.get("recipient") or "")
        if to.lower() != self.verify_address.lower():
            raise VerdictError(f"case tx {gl_tx} was sent to {to}, not VerifyJob")
        verdict = self.client.read_contract(
            address=self.verify_address,
            function_name="get_verdict",
            args=[job_id],
            transaction_hash_variant=TransactionHashVariant.LATEST_FINAL,
        )
        if str(verdict.get("job_id", "")).lower() != job_id.lower():
            raise VerdictError("verdict job_id mismatch")
        return dict(verdict)


@dataclass
class Settlement:
    job_id: str
    passed: bool
    score: int
    evm_tx: str


class Relayer:
    def __init__(self, w3: Web3, escrow_address: str, private_key: str, verdicts: VerdictSource, state_path: Path):
        self.w3 = w3
        self.escrow = w3.eth.contract(address=Web3.to_checksum_address(escrow_address), abi=load_abi())
        self.account = w3.eth.account.from_key(private_key)
        self.verdicts = verdicts
        self.state_path = Path(state_path)
        onchain = self.escrow.functions.relayer().call()
        if onchain.lower() != self.account.address.lower():
            raise RuntimeError(f"escrow relayer is {onchain}, this key is {self.account.address}")

    # ---------------------------------------------------------------- state

    def _load(self) -> dict:
        if self.state_path.exists():
            return json.loads(self.state_path.read_text())
        return {}

    def _save(self, state: dict) -> None:
        tmp = self.state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, indent=2, sort_keys=True))
        tmp.replace(self.state_path)

    def register(self, job_id: str, gl_tx: str) -> None:
        """Record which GenLayer transaction carries the case for job_id."""
        state = self._load()
        entry = state.setdefault(job_id.lower(), {})
        if entry.get("gl_tx") and entry["gl_tx"] != gl_tx:
            raise ValueError(f"job {job_id} already registered to {entry['gl_tx']}")
        entry["gl_tx"] = gl_tx
        self._save(state)

    # ---------------------------------------------------------------- work

    def job(self, job_id: str) -> dict:
        r = self.escrow.functions.jobs(bytes.fromhex(job_id[2:])).call()
        keys = ("buyer", "seller", "amount", "deadline", "status", "score", "specHash", "rubricHash", "usageRoot", "verdictRef")
        d = dict(zip(keys, r))
        d["status"] = STATUS[d["status"]]
        return d

    def tick(self) -> list[Settlement]:
        state = self._load()
        done = []
        for job_id, entry in sorted(state.items()):
            if entry.get("settled_tx") or entry.get("error"):
                continue
            try:
                s = self._process(job_id, entry["gl_tx"])
            except VerdictError as e:
                log.error("job %s: %s", job_id, e)
                entry["error"] = str(e)
                s = None
            if s:
                entry["settled_tx"] = s.evm_tx
                done.append(s)
            self._save(state)
        return done

    def _process(self, job_id: str, gl_tx: str) -> Settlement | None:
        job = self.job(job_id)
        if job["status"] != "Funded":
            log.info("job %s is %s on escrow; nothing to do", job_id, job["status"])
            return None
        now = self.w3.eth.get_block("latest")["timestamp"]
        if now > job["deadline"]:
            log.warning("job %s passed its deadline; buyer can expire() it", job_id)
            return None
        v = self.verdicts.finalized_verdict(job_id, gl_tx)
        if v is None:
            return None
        if v["spec_hash"].lower() != "0x" + job["specHash"].hex() or v["rubric_hash"].lower() != "0x" + job["rubricHash"].hex():
            raise VerdictError("verdict spec/rubric hash differs from what the buyer committed")

        fn = self.escrow.functions.settle(
            bytes.fromhex(job_id[2:]),
            bool(v["pass"]),
            int(v["score"]),
            bytes.fromhex(v["usage_root"][2:]),
            bytes.fromhex(v["spec_hash"][2:]),
            bytes.fromhex(v["rubric_hash"][2:]),
            bytes.fromhex(gl_tx[2:].rjust(64, "0")),
        )
        tx = fn.build_transaction({
            "from": self.account.address,
            "nonce": self.w3.eth.get_transaction_count(self.account.address, "pending"),
            "chainId": self.w3.eth.chain_id,
        })
        signed = self.account.sign_transaction(tx)
        h = self.w3.eth.send_raw_transaction(signed.raw_transaction)
        rcpt = self.w3.eth.wait_for_transaction_receipt(h, timeout=180)
        if rcpt["status"] != 1:
            raise RuntimeError(f"settle reverted: {h.hex()}")
        log.info("job %s settled pass=%s score=%s tx=%s", job_id, v["pass"], v["score"], h.hex())
        return Settlement(job_id, bool(v["pass"]), int(v["score"]), "0x" + h.hex().removeprefix("0x"))


def load_abi() -> list:
    return json.loads(ABI_PATH.read_text())
