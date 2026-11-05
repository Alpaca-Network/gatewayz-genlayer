"""End-to-end canary for backend v2 usage lines (cost disputes, shadow mode).

One tiny real request through a fresh job key, then every promise the backend
makes about the line is checked from the outside:

  1. X-Gatewayz-Content-Hash equals sha256 of what we sent + what came back
  2. the sealed v2 line carries that same hash, a real finish_reason, and
     tokens_out + tokens_reasoning == the billed completion tokens
  3. the line's price sheet is served and hashes to its key
  4. the v2 proof verifies against root_v2 (sha256, as the contract does)
  5. the contract's own deterministic checks do not flag the line (gzgl/replay)

Needs GATEWAYZ_CANARY_API_KEY (an ordinary account key that may open jobs) in
~/.gatewayz-genlayer-canary.env or the environment. Without it: not configured.
Cost: one request capped at 16 output tokens, job cap $0.05. Prints one JSON line.
Exit 0 pass, 1 fail, 3 not configured / v2 off.
"""

import hashlib
import json
import os
import secrets
import sys
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gzgl import billing as b  # noqa: E402
from gzgl.replay import replay  # noqa: E402

ENV_FILE = Path.home() / ".gatewayz-genlayer-canary.env"
POLICY = json.loads((Path(__file__).resolve().parents[1] / "policies/fbp-v5.json").read_text())


def _env() -> dict:
    env = dict(os.environ)
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            line = line.strip().removeprefix("export ")
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env.setdefault(k.strip(), v.strip().strip("'\""))
    return env


def _call(base, method, path, key=None, body=None):
    req = urllib.request.Request(
        base + path,
        method=method,
        data=None if body is None else json.dumps(body).encode(),
        headers={
            "User-Agent": "gatewayz-genlayer canary",
            "Content-Type": "application/json",
            **({"Authorization": f"Bearer {key}"} if key else {}),
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()


def run() -> tuple[int, dict]:
    env = _env()
    key = env.get("GATEWAYZ_CANARY_API_KEY")
    if not key:
        return 3, {"ok": False, "not_configured": True, "error": "GATEWAYZ_CANARY_API_KEY not set"}
    base = env.get("GATEWAYZ_CANARY_API_BASE", "https://api.gatewayz.ai").rstrip("/")
    model = env.get("GATEWAYZ_CANARY_MODEL", "openai/gpt-4o-mini")
    fails: list[str] = []

    deadline = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    spec = "0x" + hashlib.sha256(b"gatewayz-genlayer canary").hexdigest()
    st, _, raw = _call(base, "POST", "/v1/jobs", key, {"spec_hash": spec, "cap_usd": "0.05", "deadline": deadline})
    if st != 201:
        return 1, {"ok": False, "error": f"create job failed: {st} {raw[:200]!r}"}
    job = json.loads(raw)
    job_id, job_key = job["job_id"], job["api_key"]

    sent = {
        "model": model,
        "messages": [{"role": "user", "content": f"Reply with the single word ok. ({secrets.token_hex(4)})"}],
        "max_tokens": 16,
    }
    try:
        st, headers, raw = _call(base, "POST", "/v1/chat/completions", job_key, sent)
    finally:
        _call(base, "POST", f"/v1/jobs/{job_id}/close", key)  # always retire the key
    if st != 200:
        return 1, {"ok": False, "job_id": job_id, "error": f"inference failed: {st} {raw[:200]!r}"}
    resp = json.loads(raw)
    output = resp["choices"][0]["message"].get("content") or ""
    billed_out = int(resp.get("usage", {}).get("completion_tokens") or 0)
    local_hash = b.content_hash(sent["messages"], output)
    header = {k.lower(): v for k, v in headers.items()}.get("x-gatewayz-content-hash")

    st, _, raw = _call(base, "GET", f"/v1/jobs/{job_id}/usage?full=true", key)
    if st != 200:
        return 1, {"ok": False, "job_id": job_id, "error": f"usage read failed: {st}"}
    usage = json.loads(raw)
    lines = usage.get("entries_v2")
    if lines is None or not header:
        return 3, {"ok": False, "v2_off": True, "job_id": job_id,
                   "error": "no v2 line / header: JOB_USAGE_V2_ENABLED is off or not deployed"}

    if header != local_hash:
        fails.append("content hash header != sha256(sent messages + output)")
    if len(lines) != 1:
        fails.append(f"expected 1 v2 line, got {len(lines)}")
    e = lines[0] if lines else {}
    if e.get("content_hash") != local_hash:
        fails.append("line content_hash != local hash")
    if e.get("finish_reason") not in ("stop", "length"):
        fails.append(f"unexpected finish_reason {e.get('finish_reason')!r}")
    if e and e["tokens_out"] + e["tokens_reasoning"] != billed_out:
        fails.append(f"tokens_out+reasoning {e['tokens_out']}+{e['tokens_reasoning']} != billed {billed_out}")

    st, _, raw = _call(base, "GET", f"/v1/jobs/{job_id}/usage/proof?i=0&v=2", key)
    if st == 200:
        p = json.loads(raw)
        h = b.leaf_hash(p["entry"])
        for sib in p["proof"]:
            h = b.node_hash(h, bytes.fromhex(sib[2:]))
        if "0x" + h.hex() != usage.get("root_v2"):
            fails.append("v2 proof does not verify against root_v2")
    else:
        fails.append(f"v2 proof unavailable: {st}")

    def fetch(h):
        s, _, body = _call(base, "GET", f"/v1/price-sheets/{h}")
        if s != 200:
            raise ValueError(f"HTTP {s}")
        return body

    rep = replay(usage, POLICY, fetch)
    if not rep["ok"]:
        fails.append(f"replay: {rep.get('error') or rep['sheet_errors']}")
    for f in rep.get("flagged", []):
        fails.append(f"replay flagged line {f['seq']}: {f['det_reason']} ({f['det_bps']} bps)")

    out = {"ok": not fails, "job_id": job_id, "model": model, "finish_reason": e.get("finish_reason"),
           "tokens_out": e.get("tokens_out"), "tokens_reasoning": e.get("tokens_reasoning"), "failures": fails}
    return (0 if not fails else 1), out


if __name__ == "__main__":
    try:
        code, out = run()
    except Exception as exc:  # noqa: BLE001 -- one JSON line, always
        code, out = 1, {"ok": False, "error": f"canary crashed: {exc}"}
    print(json.dumps(out))
    sys.exit(code)
