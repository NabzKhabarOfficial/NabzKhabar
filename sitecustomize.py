"""Install fail-closed guards and runtime observability through the launcher lifecycle."""
from __future__ import annotations
import builtins
import os
import sys
_original_import = builtins.__import__
_in_hook = False


def _engine_process():
    return os.path.basename(str(sys.argv[0] or "")) in {"v13_ai_extra.py", "run_bot.py"}


def _hook(name, globals=None, locals=None, fromlist=(), level=0):
    global _in_hook
    module = _original_import(name, globals, locals, fromlist, level)
    root = name.split(".", 1)[0]
    if _in_hook or root not in {"v13_standalone", "v13_intelligence", "v13_editor_gate", "v13_final_guard", "v13_growth", "run_bot", "v13_ai_extra"}:
        return module
    _in_hook = True
    try:
        import quarantine_guard
        import v13_hardening
        if _engine_process() and root == "v13_standalone":
            try:
                import runtime_observability
                runtime_observability.startup_heartbeat()
            except Exception as exc:
                print(f"V13 OBSERVABILITY: startup heartbeat skipped ({type(exc).__name__})", flush=True)
        if root == "run_bot":
            quarantine_guard.install_launcher(module)
            try:
                import runtime_observability
                runtime_observability.install_patch_hook(module)
            except Exception as exc:
                print(f"V13 OBSERVABILITY: patch hook skipped ({type(exc).__name__})", flush=True)
        if root in {"v13_standalone", "run_bot", "v13_ai_extra"}:
            target = getattr(module, "main", None)
            if target is not None and hasattr(target, "process_news"):
                quarantine_guard.install_main(target, force=True)
            if hasattr(module, "normalize_space"):
                v13_hardening.install_text_normalizer(module)
        if root in {"v13_editor_gate", "run_bot", "v13_ai_extra"}:
            quarantine_guard.install_editor_gate(module if root == "v13_editor_gate" else __import__("v13_editor_gate"))
        if root == "v13_final_guard":
            quarantine_guard.install_final_guard(module)
            module.install()
        if root == "v13_growth":
            try:
                import quarantine_site_sweep
                changed = quarantine_site_sweep.run()
                if changed:
                    print(f"QUARANTINE SITE SWEEP: {changed} public entries rewritten", flush=True)
            except Exception as exc:
                print(f"QUARANTINE SITE SWEEP: blocked startup ({type(exc).__name__})", flush=True)
                raise
            v13_hardening.install_growth(module)
            v13_hardening.install_digest(module)
    finally:
        _in_hook = False
    return module


builtins.__import__ = _hook
