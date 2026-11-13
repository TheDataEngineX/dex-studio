from dex_studio.cli import main


def test_check_valid_project(tmp_path, capsys):
    project_file = tmp_path / "project.py"
    project_file.write_text("from dataenginex import Project\nproject = Project(name='demo')\n")
    assert main(["check", str(project_file)]) == 0
    assert "valid: demo" in capsys.readouterr().out


def test_check_invalid_project_reports_problems(tmp_path, capsys):
    project_file = tmp_path / "project.py"
    project_file.write_text(
        "from dataenginex import Contract, Project\n"
        "project = Project(name='demo', contracts=[Contract(structure='ghost')])\n"
    )
    assert main(["check", str(project_file)]) == 1
    assert "ghost" in capsys.readouterr().out


def test_check_file_without_project(tmp_path, capsys):
    project_file = tmp_path / "project.py"
    project_file.write_text("x = 1\n")
    assert main(["check", str(project_file)]) == 1
    assert "no Project" in capsys.readouterr().out


def test_no_args_prints_commands(capsys):
    assert main([]) == 0
    assert "check" in capsys.readouterr().out
