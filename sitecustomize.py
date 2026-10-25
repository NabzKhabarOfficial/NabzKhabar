"""Safe import hook for quarantine enforcement.

The re-entrancy guard is mandatory: importing quarantine_guard itself passes
through builtins.__import__ on Python startup.
"""
from __future__ import annotations
import builtins

_original_import = builtins.__import__
_in_hook = False
_installed_modules = set()


def _hook(name, globals=None, locals=None, fromlist=(), level=0):
    global _in_hook
    module = _original_import(name, globals, locals, fromlist, level)
    root = name.split(".", 1)[0]
    if _in_hook or root not in {"v13_standalone", "v13_editor_gate"}:
        return module
    _in_hook = True
    try:
        import quarantine_guard
        if root == "v13_standalone" and root not in _installed_modules:
            quarantine_guard.install_main(module)
            _installed_modules.add(root)
        elif root == "v13_editor_gate" and root not in _installed_modules:
            quarantine_guard.install_editor_gate(module)
            _installed_modules.add(root)
    finally:
        _in_hook = False
    return module


builtins.__import__ = _hook
