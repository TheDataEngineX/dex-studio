import re

from dex_studio.cli import main


def _write_project(tmp_path, extra=""):
    (tmp_path / "orders.csv").write_text("order_id\n" "o1\n" "o2\n")
    (tmp_path / "project.py").write_text(
        "from dataenginex import Column, Contract, Pipeline, Project, Source, Structure\n"
        "project = Project(\n"
        "    name='demo',\n"
        "    structures=[Structure(name='orders', columns=[Column(name='order_id', dtype='string')])],\n"
        "    contracts=[Contract(structure='orders', unique=['order_id'])],\n"
        "    pipelines=[Pipeline(name='p', sources=[Source(name='orders', path='orders.csv')])],\n"
        + extra
        + ")\n"
    )
    return tmp_path


def test_check_valid_project(tmp_path, capsys):
    _write_project(tmp_path)
    assert main(["check", str(tmp_path / "project.py")]) == 0
    assert "valid: demo" in capsys.readouterr().out


def test_check_invalid_project_reports_problems(tmp_path, capsys):
    project_file = tmp_path / "project.py"
    project_file.write_text(
        "from dataenginex import Contract, Project\n"
        "project = Project(name='demo', contracts=[Contract(structure='ghost')])\n"
    )
    assert main(["check", str(project_file)]) == 1
    assert "ghost" in capsys.readouterr().out


def test_run_and_receipt_round_trip(tmp_path, capsys):
    _write_project(tmp_path)
    assert main(["run", str(tmp_path / "project.py")]) == 0
    out = capsys.readouterr().out
    run_id = re.search(r"([0-9a-f]{32}) p succeeded", out).group(1)

    assert main(["receipt", run_id, "--workspace", str(tmp_path / ".dex")]) == 0
    receipt = capsys.readouterr().out
    assert '"status": "succeeded"' in receipt
    assert '"orders": 2' in receipt


def test_run_refuses_rerun_without_force(tmp_path, capsys):
    _write_project(tmp_path)
    assert main(["run", str(tmp_path / "project.py")]) == 0
    assert main(["run", str(tmp_path / "project.py")]) == 1
    assert "already ran" in capsys.readouterr().out
    assert main(["run", str(tmp_path / "project.py"), "--force"]) == 0
    assert "succeeded" in capsys.readouterr().out


def test_run_unknown_pipeline_is_an_error(tmp_path, capsys):
    _write_project(tmp_path)
    assert main(["run", str(tmp_path / "project.py"), "--pipeline", "nope"]) == 1
    assert "unknown pipeline" in capsys.readouterr().out


def test_no_args_prints_help(capsys):
    assert main([]) == 0
    assert "check" in capsys.readouterr().out
