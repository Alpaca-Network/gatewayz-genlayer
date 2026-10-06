"""Rubric canonicalisation. MUST stay byte-identical to canonical_rubric() in
contracts/genlayer/verify_job.py: the buyer commits rubric_hash on the escrow chain
at openJob, and the escrow rejects a verdict whose rubric hash differs."""

import hashlib
import json

DEFAULT_TOLERANCE = 15
_FIELDS = {"must_have", "nice_to_have", "hard_reject", "pass_threshold", "score_tolerance", "template"}


def canonical_rubric(rubric: dict) -> str:
    extra = set(rubric) - _FIELDS
    if extra:
        raise ValueError(f"rubric_invalid: unknown field {sorted(extra)[0]}")
    r = dict(rubric)
    for key in ("must_have", "nice_to_have", "hard_reject"):
        r[key] = list(r.get(key, []))
    r["score_tolerance"] = r.get("score_tolerance", DEFAULT_TOLERANCE)
    return json.dumps(r, sort_keys=True, separators=(",", ":"))


def rubric_hash(rubric: dict) -> str:
    return "0x" + hashlib.sha256(canonical_rubric(rubric).encode()).hexdigest()
