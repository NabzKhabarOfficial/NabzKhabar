"""Install safety hooks before the production launcher imports its modules.

This keeps the guard active in the existing free GitHub Actions entrypoint
without duplicating the large news engine or weakening its handoff contract.
"""
from __future__ import annotations

import builtins

_installed = False
_original_import = builtins.__import__


def _hook(name, globals=None, locals=None, fromlist=(), level=0):
    global _installed
    module = _original_import(name, globals, locals, fromlist, level)
    root = name.split(".", 1)[0]
    try:
        import quarantine_guard
        if root == "v13_standalone":
            quarantine_guard.install_main(module)
        elif root == "v13_editor_gate":
            quarantine_guard.install_editor_gate(module)
        _installed = True
    except Exception as exc:
        # Safety hooks fail closed when the manifest is malformed. Do not hide
        # ordinary imports in tests that do not load the news engine.
        if root in {"v13_standalone", "v13_editor_gate"}:
            raise
    return module


if not _installed:
    builtins.__import__ = _hook
