"""Tests for kluris list command."""

import json

from click.testing import CliRunner

import kluris.cli as cli_module
from kluris.cli import cli
from conftest import create_test_brain
from kluris.core.config import read_global_config, write_global_config


def test_list_shows_brains(tmp_path, monkeypatch):
    monkeypatch.setenv("KLURIS_CONFIG", str(tmp_path / "config.yml"))
    monkeypatch.setenv("HOME", str(tmp_path))
    runner = CliRunner()
    create_test_brain(runner, "my-brain", tmp_path)
    result = runner.invoke(cli, ["list"])
    assert "my-brain" in result.output


def test_list_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("KLURIS_CONFIG", str(tmp_path / "config.yml"))
    runner = CliRunner()
    result = runner.invoke(cli, ["list"])
    assert "No brains" in result.output


def test_list_json(tmp_path, monkeypatch):
    monkeypatch.setenv("KLURIS_CONFIG", str(tmp_path / "config.yml"))
    monkeypatch.setenv("HOME", str(tmp_path))
    runner = CliRunner()
    create_test_brain(runner, "my-brain", tmp_path)
    result = runner.invoke(cli, ["list", "--json"])
    data = json.loads(result.output)
    assert data["ok"] is True
    assert len(data["brains"]) == 1


def test_use_sets_default_brain(tmp_path, monkeypatch):
    monkeypatch.setenv("KLURIS_CONFIG", str(tmp_path / "config.yml"))
    monkeypatch.setenv("HOME", str(tmp_path))
    runner = CliRunner()
    create_test_brain(runner, "brain-a", tmp_path)
    create_test_brain(runner, "brain-b", tmp_path)
    result = runner.invoke(cli, ["use", "brain-b", "--json"])
    data = json.loads(result.output)
    assert result.exit_code == 0
    assert data["default_brain"] == "brain-b"

    listed = runner.invoke(cli, ["list", "--json"])
    listed_data = json.loads(listed.output)
    assert listed_data["default_brain"] == "brain-b"


def test_use_reinstalls_skills(tmp_path, monkeypatch):
    """Switching default brain must regenerate agent skill files."""
    monkeypatch.setenv("KLURIS_CONFIG", str(tmp_path / "config.yml"))
    monkeypatch.setenv("HOME", str(tmp_path))
    runner = CliRunner()
    create_test_brain(runner, "brain-a", tmp_path)
    create_test_brain(runner, "brain-b", tmp_path)

    result = runner.invoke(cli, ["use", "brain-b"])
    assert result.exit_code == 0

    skill_file = tmp_path / ".claude" / "skills" / "kluris" / "SKILL.md"
    assert skill_file.exists()
    content = skill_file.read_text(encoding="utf-8")
    assert "brain-b" in content
    assert "(default)" in content


def test_use_warns_on_partial_install_failure(tmp_path, monkeypatch):
    """use always switches default, warns if some agent installs fail."""
    monkeypatch.setenv("KLURIS_CONFIG", str(tmp_path / "config.yml"))
    monkeypatch.setenv("HOME", str(tmp_path))
    runner = CliRunner()
    create_test_brain(runner, "brain-a", tmp_path)
    create_test_brain(runner, "brain-b", tmp_path)

    def partial_fail(*args, **kwargs):
        return {"agents": 6, "commands_per_agent": 1, "total_files": 6,
                "failed_agents": [("windsurf", "permission denied")]}

    monkeypatch.setattr(cli_module, "_do_install", partial_fail)

    result = runner.invoke(cli, ["use", "brain-b"])

    assert result.exit_code == 0
    assert read_global_config().default_brain == "brain-b"
    assert "Warning" in result.output
    assert "windsurf" in result.output
