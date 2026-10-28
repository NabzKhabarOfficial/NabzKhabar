"""Install fail-closed guards through the full production launcher lifecycle."""
from __future__ import annotations
import builtins
_original_import = builtins.__import__
_in_hook = False


def _hook(name, globals=None, locals=None, fromlist=(), level=0):
    global _in_hook
    module = _original_import(name, globals, locals, fromlist, level)
    root = name.split(".", 1)[0]
    if _in_hook or root not in {"v13_standalone", "v13_editor_gate", "v13_final_guard", "run_bot", "v13_ai_extra"}:
        return module
    _in_hook = True
    try:
        import quarantine_guard
        if root == "run_bot":
            quarantine_guard.install_launcher(module)
        if root in {"v13_standalone", "run_bot", "v13_ai_extra"}:
            target = getattr(module, "main", None)
            if target is not None and hasattr(target, "process_news"):
                quarantine_guard.install_main(target, force=True)
        if root in {"v13_editor_gate", "run_bot", "v13_ai_extra"}:
            quarantine_guard.install_editor_gate(module if root == "v13_editor_gate" else __import__("v13_editor_gate"))
        if root == "v13_final_guard":
            quarantine_guard.install_final_guard(module)
    finally:
        _in_hook = False
    return module


builtins.__import__ = _hook
