"""Sealed usage record: a Merkle tree over a job's billing metadata.

Each inference request made with a job-scoped Gatewayz key appends one entry:
    {ts, model, provider, tokens_in, tokens_out, cost_usd, commit}
No prompt or completion content is ever part of an entry.

Hashing (mirrored by InferenceEscrow.verifyUsageLeaf):
    leaf = keccak256(0x00 || canonical_json(entry))
    node = keccak256(0x01 || min(a, b) || max(a, b))      # sorted pair
An odd node at any level is promoted unchanged. The 0x00/0x01 prefixes keep a leaf
from ever being passed off as an internal node (second-preimage hardening).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from decimal import Decimal

from eth_hash.auto import keccak

ENTRY_FIELDS = ("ts", "model", "provider", "tokens_in", "tokens_out", "cost_usd", "commit")


def canonical_entry(entry: dict) -> bytes:
    missing = [f for f in ENTRY_FIELDS if f not in entry]
    extra = set(entry) - set(ENTRY_FIELDS)
    if missing or extra:
        raise ValueError(f"usage entry fields: missing={missing} extra={sorted(extra)}")
    e = dict(entry)
    for f in ("tokens_in", "tokens_out"):
        if not isinstance(e[f], int) or isinstance(e[f], bool) or e[f] < 0:
            raise ValueError(f"{f} must be a non-negative int")
    # Money as a decimal STRING: floats would make the hash depend on formatting.
    e["cost_usd"] = format(Decimal(str(e["cost_usd"])).normalize(), "f")
    return json.dumps(e, sort_keys=True, separators=(",", ":")).encode()


def leaf_hash(entry: dict) -> bytes:
    return keccak(b"\x00" + canonical_entry(entry))


def node_hash(a: bytes, b: bytes) -> bytes:
    lo, hi = (a, b) if a < b else (b, a)
    return keccak(b"\x01" + lo + hi)


def _levels(leaves: list[bytes]) -> list[list[bytes]]:
    if not leaves:
        raise ValueError("empty usage record")
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


def verify_proof(leaf: bytes, proof: list[bytes], root: bytes) -> bool:
    h = leaf
    for p in proof:
        h = node_hash(h, p)
    return h == root


@dataclass
class UsageRecord:
    """A job's usage log. append() while running; seal() on close."""

    job_id: str
    entries: list[dict] = field(default_factory=list)

    def append(self, entry: dict) -> None:
        canonical_entry(entry)  # validate now, not at seal time
        self.entries.append(entry)

    @property
    def leaves(self) -> list[bytes]:
        return [leaf_hash(e) for e in self.entries]

    def seal(self) -> dict:
        root = merkle_root(self.leaves)
        return {
            "job_id": self.job_id,
            "root": "0x" + root.hex(),
            "requests": len(self.entries),
            "tokens_in": sum(e["tokens_in"] for e in self.entries),
            "tokens_out": sum(e["tokens_out"] for e in self.entries),
            "cost_usd": format(sum(Decimal(str(e["cost_usd"])) for e in self.entries).normalize(), "f"),
        }

    def proof(self, index: int) -> dict:
        leaves = self.leaves
        return {
            "index": index,
            "entry": self.entries[index],
            "leaf": "0x" + leaves[index].hex(),
            "proof": ["0x" + p.hex() for p in merkle_proof(leaves, index)],
            "root": "0x" + merkle_root(leaves).hex(),
        }

    def to_json(self) -> str:
        return json.dumps({"job_id": self.job_id, "entries": self.entries}, indent=2)

    @classmethod
    def from_json(cls, s: str) -> "UsageRecord":
        d = json.loads(s)
        rec = cls(d["job_id"])
        for e in d["entries"]:
            rec.append(e)
        return rec
