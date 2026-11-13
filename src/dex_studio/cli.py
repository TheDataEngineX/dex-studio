"""dataenginex command line entry point.

Commands land with the foundation milestones:
- M0: check (validate a project file without running it).
- M1: run, receipt. Init templates and serve land later.
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
import types
from pathlib import Path

from dataenginex import Project, run_pipeline, validate_project


def _load_project(path: str) -> types.ModuleType:
    """Load a project file as a module. Local files are trusted code
    (decision 0011)."""
    spec = importlib.util.spec_from_file_location("dex_project", path)
    if spec is None or spec.loader is None:
        raise ValueError("cannot load project file: " + path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _project_from(args: argparse.Namespace) -> Project:
    module = _load_project(args.project)
    project = getattr(module, "project", None)
    if not isinstance(project, Project):
        raise ValueError(
            "no Project instance named 'project' in " + args.project
        )
    return project


def _cmd_check(args: argparse.Namespace) -> int:
    project = _project_from(args)
    problems = validate_project(project)
    if problems:
        for problem in problems:
            print("problem: " + problem)
        return 1
    print("valid: " + project.name)
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    project = _project_from(args)
    if args.pipeline:
        pipelines = [args.pipeline]
    else:
        pipelines = [p.name for p in project.pipelines]
    if not pipelines:
        print("no pipelines in project")
        return 0
    workspace = args.workspace
    exit_code = 0
    for name in pipelines:
        try:
            receipt = run_pipeline(
                project, name, str(Path(args.project).resolve().parent), workspace, args.force
            )
            print(
                receipt.run.run_id + " " + receipt.job.name + " " + receipt.run.status
            )
        except Exception as exc:  # keep the loop running on other pipelines
            print("error: " + str(exc))
            exit_code = 1
    return exit_code


def _cmd_receipt(args: argparse.Namespace) -> int:
    ws = Path(args.workspace) if args.workspace else Path.cwd() / ".dex"
    receipt_file = ws / "receipts" / (args.run_id + ".json")
    if not receipt_file.exists():
        print("no receipt " + args.run_id + " in " + str(ws / "receipts"))
        return 1
    print(receipt_file.read_text())
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="dataenginex")
    sub = parser.add_subparsers(dest="command")

    check = sub.add_parser("check", help="validate a project without running it")
    check.add_argument("project", help="path to project.py")

    run = sub.add_parser("run", help="run pipelines (Bronze / Silver / Gold)")
    run.add_argument("project", help="path to project.py")
    run.add_argument("--pipeline", help="run only this pipeline")
    run.add_argument("--workspace", help="workspace dir (default <project>/.dex)")
    run.add_argument("--force", action="store_true", help="re-run an unchanged pipeline")

    receipt = sub.add_parser("receipt", help="show the receipt of a run")
    receipt.add_argument("run_id", help="the run id printed by run")
    receipt.add_argument("--workspace", help="workspace dir (default ./.dex)")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command is None:
        _parser().print_help()
        return 0
    try:
        if args.command == "check":
            return _cmd_check(args)
        if args.command == "run":
            return _cmd_run(args)
        if args.command == "receipt":
            return _cmd_receipt(args)
    except Exception as exc:
        print("error: " + str(exc))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
