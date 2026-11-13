"""dataenginex command line entry point.

Commands land with the foundation milestones:
- M0: check (validate a project file without running it).
- M1: run, receipt, init templates.
- Later: serve.
"""

from __future__ import annotations

import importlib.util
import sys
import types

from dataenginex import Project, validate_project

_USAGE = "usage: dataenginex check <project.py>"


def _load_project(path: str) -> types.ModuleType:
    """Load a project file as a module. Local files are trusted code
    (decision 0011)."""
    spec = importlib.util.spec_from_file_location("dex_project", path)
    if spec is None or spec.loader is None:
        raise ValueError("cannot load project file: " + path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] not in ("check", "run", "receipt"):
        print("dataenginex: check (M0) | run, receipt (M1) | serve (later)")
        return 0
    command = args[0]
    if command == "check":
        if len(args) != 2:
            print(_USAGE)
            return 2
        module = _load_project(args[1])
        project = getattr(module, "project", None)
        if not isinstance(project, Project):
            print("no Project instance named 'project' in " + args[1])
            return 1
        problems = validate_project(project)
        if problems:
            for problem in problems:
                print("problem: " + problem)
            return 1
        print("valid: " + project.name)
        return 0
    print("dataenginex " + command + ": lands with M1")
    return 0
