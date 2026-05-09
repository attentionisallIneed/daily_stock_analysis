# compatibility shim: legacy module kept for existing imports and scripts.
from __future__ import annotations

import runpy
import sys
import types

_ALIAS = __name__
_MODULE = "daily_analysis.prompts.theme_discovery"

if __name__ == "__main__":
    globals().update(runpy.run_module(_MODULE, run_name="__main__"))
else:
    _impl = __import__(_MODULE, fromlist=["*"])

    class _CompatModule(types.ModuleType):
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

        def __delattr__(self, name):
            if hasattr(_impl, name):
                delattr(_impl, name)
            if name in self.__dict__:
                types.ModuleType.__delattr__(self, name)

    sys.modules[_ALIAS].__class__ = _CompatModule
    for _name, _value in _impl.__dict__.items():
        if not (_name.startswith("__") and _name.endswith("__")):
            globals()[_name] = _value
