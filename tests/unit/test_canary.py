"""The v2 canary passes against a correct backend and names each broken promise."""

import importlib.util
import json
from pathlib import Path

import pytest

from gzgl import billing as b

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("canary", ROOT / "scripts/canary_usage_v2.py")
canary = importlib.util.module_from_spec(spec)
spec.loader.exec_module(canary)

SHEET = {"version": "t", "models": {"openai/gpt-4o-mini": {"in_per_mtok": "0.15", "out_per_mtok": "0.6"}}}
SHEET_BYTES = b.canonical_json(SHEET)
SHEET_HASH = b.sha256_hex(SHEET_BYTES)


def _backend(break_=None):
    state = {}

    def call(base, method, path, key=None, body=None):
        if path == "/v1/jobs":
            return 201, {}, json.dumps({"job_id": "0x" + "ab" * 32, "api_key": "gw_job"}).encode()
        if path == "/v1/chat/completions":
            state["messages"] = body["messages"]
            out = "ok"
            h = b.content_hash(body["messages"], out if break_ != "header" else "other")
            state["entry"] = {
                "request_id": "r", "ts": "2026-10-27T00:00:00Z", "model": "openai/gpt-4o-mini",
                "provider": "openai", "tokens_in": 20, "tokens_out": 1, "tokens_reasoning": 0,
                "cost_usd": "0.0000036" if break_ != "price" else "0.01", "status": 200,
                "finish_reason": "stop" if break_ != "finish" else "unknown",
                "price_sheet": SHEET_HASH, "content_hash": b.content_hash(body["messages"], out),
                "commit": "r",
            }
            resp = {"choices": [{"message": {"content": out}}], "usage": {"completion_tokens": 1}}
            return 200, {"X-Gatewayz-Content-Hash": h}, json.dumps(resp).encode()
        if path.endswith("/close"):
            return 200, {}, b"{}"
        ep = b.Epoch("x")
        ep.append(state["entry"])
        if path.endswith("/usage?full=true"):
            return 200, {}, json.dumps({"entries_v2": [state["entry"]], "root_v2": ep.seal()["root"]}).encode()
        if "/usage/proof" in path:
            return 200, {}, json.dumps({"entry": state["entry"], "proof": ep.proof(0)}).encode()
        if path.startswith("/v1/price-sheets/"):
            return 200, {}, SHEET_BYTES
        raise AssertionError(path)

    return call


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setenv("GATEWAYZ_CANARY_API_KEY", "gw_test")


def test_passes_against_a_correct_backend(monkeypatch):
    monkeypatch.setattr(canary, "_call", _backend())
    code, out = canary.run()
    assert code == 0 and out["ok"], out


@pytest.mark.parametrize(
    "break_,needle",
    [("header", "content hash header"), ("finish", "finish_reason"), ("price", "price_mismatch")],
)
def test_names_the_broken_promise(monkeypatch, break_, needle):
    monkeypatch.setattr(canary, "_call", _backend(break_))
    code, out = canary.run()
    assert code == 1 and any(needle in f for f in out["failures"]), out


def test_not_configured_without_a_key(monkeypatch):
    monkeypatch.delenv("GATEWAYZ_CANARY_API_KEY")
    monkeypatch.setattr(canary, "ENV_FILE", Path("/nonexistent"))
    code, out = canary.run()
    assert code == 3 and out["not_configured"]
