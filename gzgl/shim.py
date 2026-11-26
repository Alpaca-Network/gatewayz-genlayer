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


STUB_MODULES = ("genlayer", "genlayer.storage", "genlayer.types")


def load_contract(relpath: str):
    """Covers the GenVM v0.4 layout the contracts use (`import genlayer as gl`,
    `from genlayer.storage import ...`, `from genlayer.types import *`)."""
    passthrough = lambda f: f  # noqa: E731
    stub = types.ModuleType("genlayer")
    stub.__path__ = []  # a package, so its submodules import
    stub.vm = types.SimpleNamespace(UserError=UserError)
    stub.public = types.SimpleNamespace(write=passthrough, view=passthrough)
    stub.contract = types.SimpleNamespace(Contract=object)

    storage = types.ModuleType("genlayer.storage")
    storage.allow = passthrough
    storage.TreeMap = storage.DynArray = _Generic

    gtypes = types.ModuleType("genlayer.types")
    gtypes.Address = _Generic
    gtypes.u8 = gtypes.u256 = int
    gtypes.__all__ = ["Address", "u8", "u256"]

    stub.storage, stub.types = storage, gtypes
    saved = {name: sys.modules.get(name) for name in STUB_MODULES}
    sys.modules.update({"genlayer": stub, "genlayer.storage": storage, "genlayer.types": gtypes})
    try:
        spec = importlib.util.spec_from_file_location(Path(relpath).stem, ROOT / relpath)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    finally:
        for name, module in saved.items():
            if module is None:
                del sys.modules[name]
            else:
                sys.modules[name] = module
