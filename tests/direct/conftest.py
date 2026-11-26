"""Direct-mode shim for GenVM v0.4 contracts under genlayer-test 0.30.1.

genlayer-test's mocked LLM handler parses a JSON reply into a dict before returning it
(`gltest/direct/wasi_mock.py::_handle_llm_request`), which is what the v0.2 SDK expected.
The v0.4 SDK expects the host to return the reply as TEXT and parses it itself
(`genlayer/nondet/__init__.py::_decode_nondet_json` raises "JSON result is not text"
otherwise), so every mocked `exec_prompt(..., response_format="json")` failed.

This keeps mocked replies as text, matching the real v0.4 host. Drop it once
genlayer-test ships a direct mode that does the same.
"""

import pytest


@pytest.fixture(autouse=True)
def _llm_mock_returns_text(monkeypatch):
    from gltest.direct import wasi_mock

    original = wasi_mock._handle_llm_request

    def handler(vm, data):
        response = vm._match_llm_mock(data.get("prompt", ""))
        if isinstance(response, str):
            return {"ok": response}
        return original(vm, data)

    monkeypatch.setattr(wasi_mock, "_handle_llm_request", handler)
