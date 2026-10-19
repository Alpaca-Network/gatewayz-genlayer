"""Billing epochs for cost disputes (Fair Billing Policy v1).

An epoch is one key's usage over a settlement period. Each request appends one v2 entry:
    {request_id, ts, model, provider, tokens_in, tokens_out, tokens_reasoning,
     cost_usd, status, finish_reason, price_sheet, content_hash, commit}
Still no content: `content_hash` is sha256 of the canonical content bundle, which only the
user keeps. A user who disputes a line reveals the bundle; validators check it against
the hash.

Hashing differs from gzgl/usage.py on purpose: sha256, not keccak, so the CostDispute
contract can verify proofs with hashlib alone (Solidity has a sha256 precompile too).
    leaf = sha256(0x00 || canonical_json(entry))
    node = sha256(0x01 || min(a, b) || max(a, b))

Everything here MUST stay byte-identical to contracts/genlayer/cost_dispute.py.
"""

from __future__ import annotations

import hashlib
import json

ENTRY_FIELDS = (
    "request_id", "ts", "model", "provider", "tokens_in", "tokens_out", "tokens_reasoning",
    "cost_usd", "status", "finish_reason", "price_sheet", "content_hash", "commit",
)
_INT_FIELDS = ("tokens_in", "tokens_out", "tokens_reasoning", "status")
_POLICY_FIELDS = {
    "version", "refund_buckets_bps", "bucket_tolerance", "price_tolerance_bps", "token_slack",
    "max_lines", "max_excerpt_chars", "runaway_reasoning_min_tokens", "runaway_reasoning_ratio",
    "refundable", "not_refundable",
}
NANO = 10**9


def canonical_json(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def sha256_hex(b: bytes) -> str:
    return "0x" + hashlib.sha256(b).hexdigest()


def to_nano(usd: str) -> int:
    """'0.0012' -> 1_200_000. Exact for up to 9 decimals; no floats, no Decimal."""
    s = str(usd).strip()
    if not s or s.startswith("-"):
        raise ValueError(f"bad amount {usd!r}")
    whole, _, frac = s.partition(".")
    if not (whole or "0").isdigit() or (frac and not frac.isdigit()) or len(frac) > 9:
        raise ValueError(f"bad amount {usd!r}")
    return int(whole or "0") * NANO + int((frac + "000000000")[:9])


def nano_to_usd(n: int) -> str:
    whole, frac = divmod(n, NANO)
    frac_s = f"{frac:09d}".rstrip("0")
    return f"{whole}.{frac_s}" if frac_s else str(whole)


def canonical_entry(entry: dict) -> bytes:
    missing = [f for f in ENTRY_FIELDS if f not in entry]
    extra = set(entry) - set(ENTRY_FIELDS)
    if missing or extra:
        raise ValueError(f"billing entry fields: missing={missing} extra={sorted(extra)}")
    e = dict(entry)
    for f in _INT_FIELDS:
        if not isinstance(e[f], int) or isinstance(e[f], bool) or e[f] < 0:
            raise ValueError(f"{f} must be a non-negative int")
    e["cost_usd"] = nano_to_usd(to_nano(e["cost_usd"]))
    return canonical_json(e)


def leaf_hash(entry: dict) -> bytes:
    return hashlib.sha256(b"\x00" + canonical_entry(entry)).digest()


def node_hash(a: bytes, b: bytes) -> bytes:
    lo, hi = (a, b) if a < b else (b, a)
    return hashlib.sha256(b"\x01" + lo + hi).digest()


def _levels(leaves: list[bytes]) -> list[list[bytes]]:
    if not leaves:
        raise ValueError("empty epoch")
    levels = [leaves]
    while len(levels[-1]) > 1:
        cur = levels[-1]
        nxt = [node_hash(cur[i], cur[i + 1]) for i in range(0, len(cur) - 1, 2)]
        if len(cur) % 2:
            nxt.append(cur[-1])
        levels.append(nxt)
    return levels


def merkle_root(leaves: list[bytes]) -> bytes:
    return _levels(leaves)[-1][0]


def merkle_proof(leaves: list[bytes], index: int) -> list[bytes]:
    if not 0 <= index < len(leaves):
        raise IndexError(index)
    proof = []
    for level in _levels(leaves)[:-1]:
        sibling = index ^ 1
        if sibling < len(level):
            proof.append(level[sibling])
        index //= 2
    return proof


def canonical_content(messages: list[dict], output: str) -> bytes:
    """The content bundle Gatewayz hashes at serve time and the user reveals on dispute.
    `messages` is the request's chat messages as sent; `output` is the visible completion."""
    return canonical_json({"messages": messages, "output": output})


def content_hash(messages: list[dict], output: str) -> str:
    return sha256_hex(canonical_content(messages, output))


def canonical_policy(policy: dict) -> bytes:
    extra = set(policy) - _POLICY_FIELDS
    missing = _POLICY_FIELDS - set(policy)
    if extra or missing:
        raise ValueError(f"policy_invalid: missing={sorted(missing)} extra={sorted(extra)}")
    return canonical_json(policy)


def policy_hash(policy: dict) -> str:
    return sha256_hex(canonical_policy(policy))


def price_sheet_hash(sheet: dict) -> str:
    """Sheet: {"version": str, "models": {"<model>": {"in_per_mtok": "3", "out_per_mtok": "15"}}}.
    Reasoning tokens are billed at the output rate."""
    return sha256_hex(canonical_json(sheet))


def expected_cost_nano(sheet: dict, model: str, tokens_in: int, tokens_out: int, tokens_reasoning: int) -> int:
    p = sheet["models"][model]
    return (tokens_in * to_nano(p["in_per_mtok"]) + (tokens_out + tokens_reasoning) * to_nano(p["out_per_mtok"])) // 10**6


class Epoch:
    """One key's billing epoch: append() while open, seal() at close, proof() on dispute."""

    def __init__(self, epoch_id: str):
        self.epoch_id = epoch_id
        self.entries: list[dict] = []

    def append(self, entry: dict) -> None:
        canonical_entry(entry)
        self.entries.append(entry)

    @property
    def leaves(self) -> list[bytes]:
        return [leaf_hash(e) for e in self.entries]

    def seal(self) -> dict:
        if not self.entries:
            return {"epoch_id": self.epoch_id, "root": "0x" + "00" * 32, "requests": 0, "cost_usd": "0"}
        return {
            "epoch_id": self.epoch_id,
            "root": "0x" + merkle_root(self.leaves).hex(),
            "requests": len(self.entries),
            "cost_usd": nano_to_usd(sum(to_nano(e["cost_usd"]) for e in self.entries)),
        }

    def proof(self, index: int) -> list[str]:
        return ["0x" + p.hex() for p in merkle_proof(self.leaves, index)]
