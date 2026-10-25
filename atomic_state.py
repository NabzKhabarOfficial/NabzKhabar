"""Crash-safe JSON state persistence for NabzKhabar."""

from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path


def load_json(path, default=None):
    path = Path(path)
    fallback = {} if default is None else default

    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    except FileNotFoundError:
        return fallback

    except (OSError, ValueError, TypeError) as exc:
        if path.exists():
            stamp = time.strftime("%Y%m%d-%H%M%S")
            quarantine = path.with_name(
                path.name + f".corrupt-{stamp}"
            )

            try:
                os.replace(path, quarantine)
            except OSError:
                pass

        print(
            f"ATOMIC STATE: ignored corrupt {path}: "
            f"{type(exc).__name__}",
            flush=True,
        )
        return fallback


def save_json(path, value) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=str(path.parent),
    )

    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(
                value,
                handle,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            handle.write("
")
            handle.flush()
            os.fsync(handle.fileno())

        os.replace(tmp_name, path)

        try:
            directory_fd = os.open(path.parent, os.O_DIRECTORY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except (AttributeError, OSError):
            pass

    finally:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass
