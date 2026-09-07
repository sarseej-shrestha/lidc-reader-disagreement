#!/usr/bin/env python3
"""Stdlib-only test runner.

The test modules are written against the pytest API so they run unchanged under pytest once
it is a declared dependency (Milestone 2). Until then this runner injects a minimal `pytest`
shim, so the suite is runnable today **without installing anything into the project
environment**.

    python tests/run_tests.py [pattern]
"""

from __future__ import annotations

import importlib.util
import os
import sys
import traceback
import types

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


class _Approx:
    # Signature mirrors pytest.approx, including the `abs` keyword, so tests written
    # against the real API run unchanged here.
    def __init__(self, expected, rel=1e-6, abs=1e-9, abs_=None):
        self.expected, self.rel = expected, rel
        self.abs = abs_ if abs_ is not None else abs

    def __eq__(self, other):
        try:
            return abs(other - self.expected) <= max(
                self.abs, self.rel * max(abs(other), abs(self.expected)))
        except TypeError:
            return NotImplemented

    def __repr__(self):
        return f"approx({self.expected!r})"


class _Raises:
    def __init__(self, exc):
        self.exc = exc

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            raise AssertionError(f"DID NOT RAISE {self.exc}")
        return issubclass(exc_type, self.exc)


def _install_shim() -> None:
    if "pytest" in sys.modules:
        return
    shim = types.ModuleType("pytest")
    shim.approx = _Approx
    shim.raises = _Raises
    shim.fail = lambda msg="": (_ for _ in ()).throw(AssertionError(msg))

    def skip(reason=""):
        raise _Skipped(reason)
    shim.skip = skip
    sys.modules["pytest"] = shim


class _Skipped(Exception):
    pass


def load_module(path: str):
    name = "t_" + os.path.basename(path)[:-3]
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def main() -> int:
    pattern = sys.argv[1] if len(sys.argv) > 1 else ""
    sys.path.insert(0, ROOT)
    _install_shim()

    files = []
    for dirpath, _dirs, names in os.walk(os.path.join(ROOT, "tests")):
        for n in sorted(names):
            if n.startswith("test_") and n.endswith(".py"):
                files.append(os.path.join(dirpath, n))

    passed = failed = skipped = 0
    failures: list[tuple[str, str]] = []
    for path in sorted(files):
        module = load_module(path)
        rel = os.path.relpath(path, ROOT)
        names = [n for n in dir(module) if n.startswith("test_")]
        print(f"\n{rel}  ({len(names)} tests)")
        for name in names:
            if pattern and pattern not in name:
                continue
            fn = getattr(module, name)
            if not callable(fn):
                continue
            try:
                fn()
                passed += 1
                print(f"  PASS  {name}")
            except _Skipped as exc:
                skipped += 1
                print(f"  SKIP  {name}: {exc}")
            except Exception:
                failed += 1
                print(f"  FAIL  {name}")
                failures.append((f"{rel}::{name}", traceback.format_exc()))

    print(f"\n{'=' * 68}")
    print(f"passed {passed}   failed {failed}   skipped {skipped}")
    for name, tb in failures:
        print(f"\n--- {name} ---\n{tb}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
