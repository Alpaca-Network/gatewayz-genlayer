"""Measure CostDispute agreement with the labelled dispute set.

    python scripts/eval_disputes.py --offline                    # deterministic layer only, no network
    python scripts/eval_disputes.py --network studionet [--ref <git sha>] [--limit N]

Network mode builds one epoch from datasets/disputes/v1/cases.jsonl (salted per run so
lines are never "already disputed"), shuffles the cases into disputes of up to
`max_lines`, and serves content and prices from raw.githubusercontent.com at --ref
(which must be pushed). Results go to runs/eval-<network>-<ts>.json, then a report.

Scoring, per line:
  det_ok      deterministic reason and bps equal the label exactly
  bucket_ok   the judged refund bucket is inside the labelled range
  category_ok the judged category equals the label (only where a refund is expected)
  false refund   label says 0 but the judgment refunded something
  missed refund  label says >0 but the judgment refunded nothing
"""

import argparse
import json
import random
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from gzgl import billing as b  # noqa: E402
from gzgl.shim import load_contract  # noqa: E402

DATA = ROOT / "datasets/disputes/v1"
REPO_RAW = "https://raw.githubusercontent.com/Alpaca-Network/gatewayz-genlayer"
C = load_contract("contracts/genlayer/cost_dispute.py")


def load():
    cases = [json.loads(line) for line in (DATA / "cases.jsonl").read_text().splitlines() if line.strip()]
    policy_json = (ROOT / "policies/fbp-v1.json").read_text()
    sheet = json.loads((DATA / "prices.json").read_bytes())
    return cases, policy_json, sheet


def score(case, got) -> dict:
    exp = case["expect"]
    lo, hi = exp["bucket"]
    if got is None:
        return {"id": case["id"], "variant": case["variant"], "status": "no_verdict"}
    got_det = got["det_reason"] == exp["det_reason"] and int(got["det_bps"]) == exp["det_bps"]
    judged = got.get("bucket") is not None and got.get("content_ok", True) and int(got["det_bps"]) < 10_000
    bucket = int(got.get("bucket") or 0)
    r = {"id": case["id"], "variant": case["variant"], "status": "ok", "det_ok": got_det, "judged": judged,
         "category": got.get("category"), "bucket": bucket, "expect": exp}
    if judged:
        r["bucket_ok"] = lo <= bucket <= hi
        r["category_ok"] = exp["category"] == "none" or got.get("category") == exp["category"]
        r["false_refund"] = hi == 0 and bucket > 0
        r["missed_refund"] = lo > 0 and bucket == 0
    return r


def offline(cases, policy_json, sheet):
    policy, _ = C.parse_policy(policy_json)
    out = []
    for c in cases:
        content = json.loads((DATA / "content" / f"{c['id']}.json").read_bytes())
        d = C.deterministic_check(policy, sheet, c["entry"], content)
        out.append(score(c, {**d, "bucket": None, "content_ok": True}))
    return out


def network(cases, policy_json, args):
    from genlayer_py.types import TransactionStatus

    from gzgl.net import DEPLOYMENTS, genlayer_client

    ref = args.ref or subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip()
    pushed = subprocess.run(["git", "-C", str(ROOT), "branch", "-r", "--contains", ref], capture_output=True, text=True)
    if not pushed.stdout.strip():
        raise SystemExit(f"{ref} is not on any remote branch; push it first so raw URLs resolve")
    base = f"{REPO_RAW}/{ref}/datasets/disputes/v1"
    policy, _ = C.parse_policy(policy_json)
    salt = f"eval-{int(time.time())}"
    entries = [dict(c["entry"], commit=salt) for c in cases]
    ep = b.Epoch("0x" + b.sha256_hex(salt.encode())[2:])
    for e in entries:
        ep.append(e)
    root = ep.seal()["root"]
    order = list(range(len(cases)))
    random.Random(args.seed).shuffle(order)
    if args.limit:
        order = order[: args.limit]
    batches = [order[i:i + policy["max_lines"]] for i in range(0, len(order), policy["max_lines"])]

    dep = json.loads((DEPLOYMENTS / f"{args.network}.json").read_text())
    client = genlayer_client(args.network)
    results, disputes = {}, []
    for n, batch in enumerate(batches):
        lines = [{"index": i, "entry": entries[i], "proof": ep.proof(i),
                  "content_uri": f"{base}/content/{cases[i]['id']}.json", "claim": cases[i]["claim"]} for i in batch]
        dispute_id = b.sha256_hex(f"{salt}:{n}".encode())
        t0 = time.time()
        rec = {"n": n, "dispute_id": dispute_id, "lines": len(batch)}
        try:
            tx = client.write_contract(address=dep["cost_dispute"], function_name="open_dispute",
                                       args=[dispute_id, ep.epoch_id, root, policy_json, f"{base}/prices.json",
                                             entries[0]["price_sheet"], json.dumps(lines)])
            rec["tx"] = tx
            r = client.wait_for_transaction_receipt(transaction_hash=tx, status=TransactionStatus.ACCEPTED,
                                                    retries=args.retries)
            rec["status"] = r.get("status_name") or "ACCEPTED"
            v = client.read_contract(address=dep["cost_dispute"], function_name="get_dispute", args=[dispute_id])
            for line in v["lines"]:
                results[line["line"]] = line
        except Exception as e:  # a dispute that fails consensus or reverts is a result, not a crash
            rec["status"] = "failed"
            rec["error"] = str(e)[:300]
        rec["seconds"] = round(time.time() - t0, 1)
        disputes.append(rec)
        print(f"dispute {n + 1}/{len(batches)}: {rec['status']} in {rec['seconds']}s", flush=True)
    scored = [score(cases[i], results.get(i)) for i in order]
    return scored, {"ref": ref, "salt": salt, "root": root, "contract": dep["cost_dispute"], "disputes": disputes}


def report(scored, meta=None):
    by = defaultdict(list)
    for s in scored:
        by[s["variant"]].append(s)
    print(f"\n{'variant':28} {'n':>3} {'det_ok':>7} {'bucket_ok':>9} {'cat_ok':>7} {'false+':>6} {'missed':>6} {'none':>5}")
    tot = defaultdict(int)
    for v in sorted(by):
        rows = by[v]
        ok = [r for r in rows if r["status"] == "ok"]
        j = [r for r in ok if r.get("judged")]
        cells = {
            "n": len(rows),
            "det_ok": sum(r["det_ok"] for r in ok),
            "bucket_ok": sum(r["bucket_ok"] for r in j),
            "cat_ok": sum(r["category_ok"] for r in j),
            "false": sum(r["false_refund"] for r in j),
            "missed": sum(r["missed_refund"] for r in j),
            "noverdict": len(rows) - len(ok),
            "judged": len(j),
        }
        for k, x in cells.items():
            tot[k] += x
        jd = f"/{cells['judged']}" if j else ""
        print(f"{v:28} {cells['n']:3d} {cells['det_ok']:4d}/{len(ok):<2d} {cells['bucket_ok']:6d}{jd:<3} "
              f"{cells['cat_ok']:4d}{jd:<3} {cells['false']:6d} {cells['missed']:6d} {cells['noverdict']:5d}")
    print(f"{'TOTAL':28} {tot['n']:3d} {tot['det_ok']:4d}    {tot['bucket_ok']:6d}/{tot['judged']:<3d}"
          f"{tot['cat_ok']:4d}    {tot['false']:6d} {tot['missed']:6d} {tot['noverdict']:5d}")
    if meta:
        ds = meta["disputes"]
        okd = [d for d in ds if d["status"] != "failed"]
        secs = sorted(d["seconds"] for d in okd) or [0]
        print(f"\ndisputes: {len(okd)}/{len(ds)} reached a verdict; median {secs[len(secs) // 2]}s, max {secs[-1]}s")
        for d in ds:
            if d["status"] == "failed":
                print(f"  dispute {d['n']} failed: {d.get('error', '')[:160]}")
    return dict(tot)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--network", default="studionet")
    ap.add_argument("--ref", default="")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--retries", type=int, default=200)
    a = ap.parse_args()
    cases, policy_json, sheet = load()
    if a.offline:
        scored, meta, name = offline(cases, policy_json, sheet), None, "offline"
    else:
        scored, meta = network(cases, policy_json, a)
        name = a.network
    totals = report(scored, meta)
    runs = ROOT / "runs"
    runs.mkdir(exist_ok=True)
    out = runs / f"eval-{name}-{int(time.time())}.json"
    out.write_text(json.dumps({"meta": meta, "totals": totals, "lines": scored}, indent=2, default=str))
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
