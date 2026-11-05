"""Load an Intelligent Contract's pure helpers outside GenVM.

The contract module is executed against a stub `genlayer` module, so its canonical
forms and deterministic checks can be called from tests and offline evaluation.
Nothing that touches storage, the web or an LLM works through this shim.
"""

import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class UserError(Exception):
    pass


class _Generic:
    def __class_getitem__(cls, _):
        return cls


def load_contract(relpath: str):
    stub = types.ModuleType("genlayer")
    passthrough = lambda f: f  # noqa: E731
    stub.gl = types.SimpleNamespace(
        vm=types.SimpleNamespace(UserError=UserError),
        public=types.SimpleNamespace(write=passthrough, view=passthrough),
        Contract=object,
    )
    stub.allow_storage = lambda c: c
    stub.Address = stub.TreeMap = stub.DynArray = _Generic
    stub.__all__ = ["gl", "allow_storage", "Address", "TreeMap", "DynArray"]
    saved = sys.modules.get("genlayer")
    sys.modules["genlayer"] = stub
    try:
        spec = importlib.util.spec_from_file_location(Path(relpath).stem, ROOT / relpath)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    finally:
        if saved is None:
            del sys.modules["genlayer"]
        else:
            sys.modules["genlayer"] = saved
