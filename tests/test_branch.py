"""Tests for kluris branch command."""

import json
import subprocess

from click.testing import CliRunner

from kluris.cli import cli
from conftest import create_test_brain


def test_branch_shows_current(tmp_path, monkeypatch):
    monkeypatch.setenv("KLURIS_CONFIG", str(tmp_path / "config.yml"))
    monkeypatch.setenv("HOME", str(tmp_path))
    runner = CliRunner()
    create_test_brain(runner, "my-brain", tmp_path)

    result = runner.invoke(cli, ["branch"])
    assert result.exit_code == 0
    assert "main" in result.output


def test_branch_json_shows_current(tmp_path, monkeypatch):
    monkeypatch.setenv("KLURIS_CONFIG", str(tmp_path / "config.yml"))
    monkeypatch.setenv("HOME", str(tmp_path))
    runner = CliRunner()
    create_test_brain(runner, "my-brain", tmp_path)

    result = runner.invoke(cli, ["branch", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["ok"] is True
    assert data["current"] == "main"


def test_branch_switch_creates_new(tmp_path, monkeypatch):
    """Switching to a non-existent branch creates it."""
    monkeypatch.setenv("KLURIS_CONFIG", str(tmp_path / "config.yml"))
    monkeypatch.setenv("HOME", str(tmp_path))
    runner = CliRunner()
    create_test_brain(runner, "my-brain", tmp_path)

    result = runner.invoke(cli, ["branch", "feature/monitoring", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["switched"] is True
    assert data["current"] == "feature/monitoring"
    assert data["previous"] == "main"


def test_branch_switch_back_to_main(tmp_path, monkeypatch):
    monkeypatch.setenv("KLURIS_CONFIG", str(tmp_path / "config.yml"))
    monkeypatch.setenv("HOME", str(tmp_path))
    runner = CliRunner()
    create_test_brain(runner, "my-brain", tmp_path)
    bp = tmp_path / "my-brain"

    subprocess.run(["git", "checkout", "-b", "feature/x"], cwd=bp,
                    capture_output=True, check=True)

    result = runner.invoke(cli, ["branch", "main", "--json"])
    data = json.loads(result.output)
    assert data["switched"] is True
    assert data["current"] == "main"


def test_branch_already_on_target(tmp_path, monkeypatch):
    monkeypatch.setenv("KLURIS_CONFIG", str(tmp_path / "config.yml"))
    monkeypatch.setenv("HOME", str(tmp_path))
    runner = CliRunner()
    create_test_brain(runner, "my-brain", tmp_path)

    result = runner.invoke(cli, ["branch", "main", "--json"])
    data = json.loads(result.output)
    assert data["switched"] is False
    assert data["current"] == "main"


def test_branch_list(tmp_path, monkeypatch):
    monkeypatch.setenv("KLURIS_CONFIG", str(tmp_path / "config.yml"))
    monkeypatch.setenv("HOME", str(tmp_path))
    runner = CliRunner()
    create_test_brain(runner, "my-brain", tmp_path)
    bp = tmp_path / "my-brain"

    subprocess.run(["git", "checkout", "-b", "feature/a"], cwd=bp,
                    capture_output=True, check=True)
    subprocess.run(["git", "checkout", "main"], cwd=bp,
                    capture_output=True, check=True)

    result = runner.invoke(cli, ["branch", "--list", "--json"])
    data = json.loads(result.output)
    assert "feature/a" in data["branches"]
    assert "main" in data["branches"]
    assert data["current"] == "main"


def test_branch_refuses_with_uncommitted_changes(tmp_path, monkeypatch):
    monkeypatch.setenv("KLURIS_CONFIG", str(tmp_path / "config.yml"))
    monkeypatch.setenv("HOME", str(tmp_path))
    runner = CliRunner()
    create_test_brain(runner, "my-brain", tmp_path)
    (tmp_path / "my-brain" / "projects" / "dirty.md").write_text("# Dirty\n", encoding="utf-8")

    result = runner.invoke(cli, ["branch", "feature/x"])
    assert result.exit_code != 0
    assert "uncommitted" in result.output.lower()


def test_branch_no_git_brain(tmp_path, monkeypatch):
    monkeypatch.setenv("KLURIS_CONFIG", str(tmp_path / "config.yml"))
    monkeypatch.setenv("HOME", str(tmp_path))
    runner = CliRunner()
    runner.invoke(cli, ["create", "my-brain", "--path", str(tmp_path),
                        "--description", "test", "--no-git", "--json"])

    result = runner.invoke(cli, ["branch", "--json"])
    assert result.exit_code != 0
    data = json.loads(result.output)
    assert data["ok"] is False
