"""End-to-end inference escrow run: fund -> work through Gatewayz -> verify on GenLayer -> settle on Fuji.

    python scripts/demo.py all --spec demo/specs/job-001-validator-guide.md
    python scripts/demo.py <step> --run runs/<job_id>.json      # resume one step

Steps (each writes its outputs into runs/<job_id>.json so any step can be re-run):
  new     create a job id, publish the spec, hash it and the rubric
  fund    Org A (BUYER) opens the job on InferenceEscrow (Fuji), locking AMOUNT
  work    Org B (SELLER) produces the deliverable through Gatewayz; every request appends
          one billing-metadata line to the usage record; the record is sealed to a Merkle root
  verify  submit the case to VerifyJob on GenLayer; register the case tx with the relayer
  settle  relayer waits for GenLayer FINALIZED and calls settle() on the escrow
  audit   check every usage line against the root stored on-chain; print the money movement

Publishing: spec and deliverable must be at an https URL whose bytes never change, because
validators fetch them and compare hashes. --host gist publishes each as a public GitHub gist
(pinned to its revision) using the `gh` CLI. Pass --spec-uri/--deliverable-uri to host elsewhere.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from gzgl.net import DEPLOYMENTS, fuji, genlayer_client, key  # noqa: E402
from gzgl.relayer import GenLayerVerdicts, Relayer, load_abi  # noqa: E402
from gzgl.rubric import rubric_hash  # noqa: E402
from gzgl.usage import UsageRecord  # noqa: E402

RUNS = ROOT / "runs"
GATEWAYZ_URL = os.environ.get("GATEWAYZ_BASE_URL", "https://api.gatewayz.ai/v1")
SNOWTRACE = "https://testnet.snowtrace.io"


def sha256_0x(b: bytes) -> str:
    return "0x" + hashlib.sha256(b).hexdigest()


def fetch(url: str) -> bytes:
    return urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "gzgl-demo"}), timeout=30).read()


def publish_gist(path: Path, description: str) -> str:
    """Public gist, returned as a raw URL pinned to the gist revision (immutable bytes)."""
    out = subprocess.run(["gh", "gist", "create", "--public", "-d", description, str(path)],
                         check=True, capture_output=True, text=True).stdout.strip()
    gist_id = out.rstrip("/").split("/")[-1]
    raw = subprocess.run(["gh", "api", f"gists/{gist_id}", "--jq", ".files[].raw_url"],
                         check=True, capture_output=True, text=True).stdout.strip().splitlines()[0]
    if fetch(raw) != path.read_bytes():
        raise SystemExit(f"gist {raw} does not serve the exact bytes of {path}")
    return raw


def load(run: Path) -> dict:
    return json.loads(run.read_text())


def save(run: Path, st: dict) -> None:
    run.write_text(json.dumps(st, indent=2) + "\n")


def deployments(st: dict) -> dict:
    return json.loads((DEPLOYMENTS / f"{st['genlayer_network']}.json").read_text())


def send(w3, role: str, fn, value: int = 0):
    acct = w3.eth.account.from_key(key(role))
    tx = fn.build_transaction({"from": acct.address, "value": value, "chainId": w3.eth.chain_id,
                               "nonce": w3.eth.get_transaction_count(acct.address, "pending")})
    h = w3.eth.send_raw_transaction(acct.sign_transaction(tx).raw_transaction)
    r = w3.eth.wait_for_transaction_receipt(h, timeout=180)
    if r["status"] != 1:
        raise SystemExit(f"{role} tx reverted: {h.hex()}")
    return "0x" + h.hex().removeprefix("0x")


# ------------------------------------------------------------------ steps


def step_new(a) -> Path:
    job_id = "0x" + secrets.token_hex(32)
    RUNS.mkdir(exist_ok=True)
    run = RUNS / f"{job_id[:18]}.json"
    spec_path = Path(a.spec)
    spec_uri = a.spec_uri or publish_gist(spec_path, f"Gatewayz x GenLayer inference escrow — job spec {job_id[:18]}")
    spec_bytes = fetch(spec_uri)
    if spec_bytes != spec_path.read_bytes():
        raise SystemExit(f"{spec_uri} does not serve {spec_path}")
    rubric = json.loads(Path(a.rubric).read_text())
    st = {
        "job_id": job_id, "created_at": datetime.now(timezone.utc).isoformat(),
        "genlayer_network": a.genlayer_network, "spec_path": str(spec_path), "spec_uri": spec_uri,
        "spec_hash": sha256_0x(spec_bytes), "rubric_path": a.rubric, "rubric_hash": rubric_hash(rubric),
        "amount_wei": int(float(a.amount) * 10**18), "model": a.model, "deadline_hours": a.deadline_hours,
    }
    save(run, st)
    print(f"[new] job {job_id}\n      spec {spec_uri}\n      run file {run}")
    return run


def step_fund(run: Path) -> None:
    st = load(run)
    if st.get("fund_tx"):
        return print(f"[fund] already funded: {SNOWTRACE}/tx/{st['fund_tx']}")
    dep = deployments(st)
    w3 = fuji()
    escrow = w3.eth.contract(address=dep["escrow"], abi=load_abi())
    seller = w3.eth.account.from_key(key("SELLER")).address
    deadline = w3.eth.get_block("latest")["timestamp"] + int(st["deadline_hours"] * 3600)
    h = send(w3, "BUYER", escrow.functions.openJob(
        bytes.fromhex(st["job_id"][2:]), seller, deadline,
        bytes.fromhex(st["spec_hash"][2:]), bytes.fromhex(st["rubric_hash"][2:])), value=st["amount_wei"])
    st.update(fund_tx=h, deadline=deadline, seller=seller)
    save(run, st)
    print(f"[fund] Org A locked {st['amount_wei'] / 1e18} AVAX  {SNOWTRACE}/tx/{h}")


def step_work(run: Path, a) -> None:
    """Org B's agent. Two calls through Gatewayz: draft, then self-review + final."""
    st = load(run)
    if st.get("deliverable_uri"):
        return print(f"[work] already delivered: {st['deliverable_uri']}")
    api_key = os.environ.get("SELLER_GATEWAYZ_API_KEY") or os.environ.get("GATEWAYZ_API_KEY")
    if not api_key:
        raise SystemExit("SELLER_GATEWAYZ_API_KEY missing (Org B's Gatewayz key)")
    spec = Path(st["spec_path"]).read_text()
    rec = UsageRecord(st["job_id"])

    def call(messages: list[dict]) -> str:
        body = json.dumps({"model": st["model"], "messages": messages, "max_tokens": 2500}).encode()
        req = urllib.request.Request(f"{GATEWAYZ_URL}/chat/completions", data=body, method="POST", headers={
            "Authorization": f"Bearer {api_key}", "Content-Type": "application/json", "User-Agent": "gzgl-demo"})
        try:
            resp = urllib.request.urlopen(req, timeout=180)
        except urllib.error.HTTPError as e:
            raise SystemExit(f"Gatewayz {e.code}: {e.read()[:300]!r}")
        d = json.loads(resp.read())
        usage = d.get("usage") or {}
        cost = usage.get("cost", usage.get("cost_usd", usage.get("total_cost")))
        model = d.get("model") or st["model"]
        rec.append({
            "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "model": model,
            "provider": model.split("/")[0] if "/" in model else "unknown",
            "tokens_in": int(usage.get("prompt_tokens", 0)),
            "tokens_out": int(usage.get("completion_tokens", 0)),
            "cost_usd": str(cost if cost is not None else 0),
            "commit": resp.headers.get("x-gatewayz-request-id", "")[:36],
        })
        return d["choices"][0]["message"]["content"]

    draft = call([{"role": "system", "content": "You are Org B's technical writing agent. Follow the job spec exactly."},
                  {"role": "user", "content": spec}])
    final = call([{"role": "system", "content": "You are Org B's reviewing agent."},
                  {"role": "user", "content": f"Job spec:\n{spec}\n\nDraft:\n{draft}\n\nCheck the draft against every requirement in the spec, fix anything missing or wrong, and return ONLY the final Markdown note."}])

    out_dir = RUNS / st["job_id"][:18]
    out_dir.mkdir(exist_ok=True)
    deliverable = out_dir / "deliverable.md"
    deliverable.write_text(final.strip() + "\n")
    (out_dir / "usage.json").write_text(rec.to_json())
    sealed = rec.seal()
    uri = a.deliverable_uri or publish_gist(deliverable, f"Gatewayz x GenLayer inference escrow — deliverable {st['job_id'][:18]}")
    st.update(deliverable_path=str(deliverable), deliverable_uri=uri, deliverable_hash=sha256_0x(fetch(uri)),
              usage_path=str(out_dir / "usage.json"), usage=sealed)
    save(run, st)
    print(f"[work] Org B delivered via Gatewayz ({sealed['requests']} requests, {sealed['tokens_in']}+{sealed['tokens_out']} tokens, ${sealed['cost_usd']})")
    print(f"       usage root {sealed['root']}\n       deliverable {uri}")


def _relayer(st: dict) -> Relayer:
    dep = deployments(st)
    return Relayer(fuji(), dep["escrow"], key("OPERATOR"),
                   GenLayerVerdicts(genlayer_client(st["genlayer_network"]), dep["verify_job"]),
                   RUNS / f"relayer-{st['genlayer_network']}.json")


def step_verify(run: Path) -> None:
    st = load(run)
    if st.get("genlayer_tx"):
        return print(f"[verify] case already submitted: {st['genlayer_tx']}")
    from genlayer_py.types import TransactionStatus

    dep = deployments(st)
    client = genlayer_client(st["genlayer_network"])
    t0 = time.time()
    tx = client.write_contract(address=dep["verify_job"], function_name="submit_case", args=[
        st["job_id"], st["spec_uri"], st["spec_hash"], st["deliverable_uri"], st["deliverable_hash"],
        st["usage"]["root"], Path(st["rubric_path"]).read_text()])
    st["genlayer_tx"] = tx
    save(run, st)
    _relayer(st).register(st["job_id"], tx)
    print(f"[verify] case tx {tx} — waiting for consensus")
    client.wait_for_transaction_receipt(transaction_hash=tx, status=TransactionStatus.ACCEPTED, retries=600, interval=5000)
    v = client.read_contract(address=dep["verify_job"], function_name="get_verdict", args=[st["job_id"]])
    st["verdict"] = json.loads(json.dumps(v, default=str))
    st["accepted_after_s"] = round(time.time() - t0)
    save(run, st)
    print(f"[verify] ACCEPTED after {st['accepted_after_s']}s: pass={v['pass']} score={v['score']}")
    for r in v["reasons"]:
        print(f"         - {r}")


def step_settle(run: Path, poll: int) -> None:
    st = load(run)
    if st.get("settle_tx"):
        return print(f"[settle] already settled: {SNOWTRACE}/tx/{st['settle_tx']}")
    rel = _relayer(st)
    print("[settle] waiting for GenLayer FINALIZED (appeal window) before touching the escrow")
    while True:
        for s in rel.tick():
            if s.job_id == st["job_id"]:
                st.update(settle_tx=s.evm_tx, settled_pass=s.passed)
                save(run, st)
                return print(f"[settle] escrow settled pass={s.passed}  {SNOWTRACE}/tx/{s.evm_tx}")
        state = json.loads(rel.state_path.read_text()).get(st["job_id"], {})
        if state.get("error"):
            raise SystemExit(f"[settle] relayer parked the job: {state['error']}")
        if state.get("settled_tx"):
            st.update(settle_tx=state["settled_tx"])
            save(run, st)
            return print(f"[settle] escrow settled  {SNOWTRACE}/tx/{state['settled_tx']}")
        time.sleep(poll)


def step_audit(run: Path) -> None:
    st = load(run)
    dep = deployments(st)
    w3 = fuji()
    escrow = w3.eth.contract(address=dep["escrow"], abi=load_abi())
    jid = bytes.fromhex(st["job_id"][2:])
    rel = _relayer(st)
    j = rel.job(st["job_id"])
    rec = UsageRecord.from_json(Path(st["usage_path"]).read_text())
    ok = all(escrow.functions.verifyUsageLeaf(jid, bytes.fromhex(p["leaf"][2:]), [bytes.fromhex(x[2:]) for x in p["proof"]]).call()
             for p in (rec.proof(i) for i in range(len(rec.entries))))
    print(f"[audit] escrow status {j['status']}  score {j['score']}  verdictRef 0x{j['verdictRef'].hex()}")
    print(f"        usage root on-chain 0x{j['usageRoot'].hex()} — {len(rec.entries)}/{len(rec.entries)} lines verify: {ok}")
    for role in ("BUYER", "SELLER"):
        addr = w3.eth.account.from_key(key(role)).address
        print(f"        credits[{role}] = {escrow.functions.credits(addr).call() / 1e18} AVAX")
    print(f"        credits[treasury] = {escrow.functions.credits(dep['treasury']).call() / 1e18} AVAX")
    st["audit"] = {"status": j["status"], "usage_lines_verified": ok, "at": datetime.now(timezone.utc).isoformat()}
    save(run, st)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("step", choices=["all", "new", "fund", "work", "verify", "settle", "audit"])
    ap.add_argument("--run", type=Path)
    ap.add_argument("--spec", default="demo/specs/job-001-validator-guide.md")
    ap.add_argument("--spec-uri")
    ap.add_argument("--deliverable-uri")
    ap.add_argument("--rubric", default="rubrics/written.json")
    ap.add_argument("--genlayer-network", default="studionet")
    ap.add_argument("--amount", default="0.01", help="AVAX the buyer locks")
    ap.add_argument("--model", default="anthropic/claude-sonnet-5")
    ap.add_argument("--deadline-hours", type=float, default=48)
    ap.add_argument("--poll", type=int, default=30)
    a = ap.parse_args()

    run = a.run
    if a.step in ("all", "new"):
        run = step_new(a)
    if run is None:
        raise SystemExit("--run is required for a single step")
    if a.step in ("all", "fund"):
        step_fund(run)
    if a.step in ("all", "work"):
        step_work(run, a)
    if a.step in ("all", "verify"):
        step_verify(run)
    if a.step in ("all", "settle"):
        step_settle(run, a.poll)
    if a.step in ("all", "audit"):
        step_audit(run)


if __name__ == "__main__":
    main()
