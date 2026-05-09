# compatibility shim: legacy package kept for existing imports.
from __future__ import annotations

import sys
import types

_ALIAS = __name__
_MODULE = "daily_analysis.data_provider"
_impl = __import__(_MODULE, fromlist=["*"])

class _CompatPackage(types.ModuleType):
    def __getattr__(self, name):
        return getattr(_impl, name)

    def __setattr__(self, name, value):
        if name == "__file__":
            setattr(_impl, name, value)
            types.ModuleType.__setattr__(self, name, value)
            return
        if name.startswith("__") or name in {"_ALIAS", "_MODULE", "_impl"}:
            types.ModuleType.__setattr__(self, name, value)
            return
        setattr(_impl, name, value)
        types.ModuleType.__setattr__(self, name, value)

sys.modules[_ALIAS].__class__ = _CompatPackage
for _name, _value in _impl.__dict__.items():
    if not (_name.startswith("__") and _name.endswith("__")):
        globals()[_name] = _value
