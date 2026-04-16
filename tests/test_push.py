"""Tests for kluris push command."""

from click.testing import CliRunner
from kluris.cli import cli
from conftest import create_test_brain


def test_push_clean_brain(tmp_path, monkeypatch):
    monkeypatch.setenv("KLURIS_CONFIG", str(tmp_path / "config.yml"))
    monkeypatch.setenv("HOME", str(tmp_path))
    runner = CliRunner()
    create_test_brain(runner, "my-brain", tmp_path)
    result = runner.invoke(cli, ["push"])
    assert "nothing to push" in result.output.lower()


def test_push_json_reports_current_git_branch(tmp_path, monkeypatch):
    """Push JSON envelope must report the actual git branch, not the
    configured default_branch from kluris.yml."""
    import json
    monkeypatch.setenv("KLURIS_CONFIG", str(tmp_path / "config.yml"))
    monkeypatch.setenv("HOME", str(tmp_path))
    runner = CliRunner()
    create_test_brain(runner, "my-brain", tmp_path)

    result = runner.invoke(cli, ["push", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["brains"][0]["branch"] == "main"


def test_push_on_feature_branch_reports_that_branch(tmp_path, monkeypatch):
    """When working on a non-default branch, push must commit and report
    that branch, not the configured default_branch."""
    import json
    import subprocess
    monkeypatch.setenv("KLURIS_CONFIG", str(tmp_path / "config.yml"))
    monkeypatch.setenv("HOME", str(tmp_path))
    runner = CliRunner()
    create_test_brain(runner, "my-brain", tmp_path)
    bp = tmp_path / "my-brain"

    # Switch to a feature branch
    subprocess.run(["git", "checkout", "-b", "feature/monitoring"], cwd=bp,
                    capture_output=True, check=True)
    (bp / "projects" / "monitoring.md").write_text("# Monitoring\n", encoding="utf-8")

    result = runner.invoke(cli, ["push", "-m", "add monitoring", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["brains"][0]["branch"] == "feature/monitoring"
    assert data["brains"][0]["files_committed"] >= 1


def test_push_commits_changes(tmp_path, monkeypatch):
    monkeypatch.setenv("KLURIS_CONFIG", str(tmp_path / "config.yml"))
    monkeypatch.setenv("HOME", str(tmp_path))
    runner = CliRunner()
    create_test_brain(runner, "my-brain", tmp_path)
    (tmp_path / "my-brain" / "projects" / "auth.md").write_text("# Auth\n", encoding="utf-8")
    result = runner.invoke(cli, ["push", "-m", "add auth"])
    assert "committed" in result.output.lower() or result.exit_code == 0


def test_push_with_message(tmp_path, monkeypatch):
    monkeypatch.setenv("KLURIS_CONFIG", str(tmp_path / "config.yml"))
    monkeypatch.setenv("HOME", str(tmp_path))
    runner = CliRunner()
    create_test_brain(runner, "my-brain", tmp_path)
    (tmp_path / "my-brain" / "projects" / "auth.md").write_text("# Auth\n", encoding="utf-8")
    runner.invoke(cli, ["push", "-m", "brain: add auth neuron"])
    import subprocess
    log = subprocess.run(["git", "log", "--oneline", "-1"], cwd=tmp_path / "my-brain", capture_output=True, text=True)
    assert "add auth" in log.stdout


def test_push_no_remote_warning(tmp_path, monkeypatch):
    monkeypatch.setenv("KLURIS_CONFIG", str(tmp_path / "config.yml"))
    monkeypatch.setenv("HOME", str(tmp_path))
    runner = CliRunner()
    create_test_brain(runner, "my-brain", tmp_path)
    (tmp_path / "my-brain" / "projects" / "auth.md").write_text("# Auth\n", encoding="utf-8")
    result = runner.invoke(cli, ["push", "-m", "test"])
    # Should succeed (local commit) even without remote
    assert result.exit_code == 0


def test_push_prompts_for_message(tmp_path, monkeypatch):
    """kluris push without -m shows changed files and prompts for a message."""
    monkeypatch.setenv("KLURIS_CONFIG", str(tmp_path / "config.yml"))
    monkeypatch.setenv("HOME", str(tmp_path))
    runner = CliRunner()
    create_test_brain(runner, "my-brain", tmp_path)
    (tmp_path / "my-brain" / "projects" / "auth.md").write_text("# Auth\n", encoding="utf-8")
    result = runner.invoke(cli, ["push"], input="add auth neuron\n")
    assert result.exit_code == 0
    assert "files changed" in result.output
    assert "Commit message" in result.output


def test_push_no_git_brain(tmp_path, monkeypatch):
    monkeypatch.setenv("KLURIS_CONFIG", str(tmp_path / "config.yml"))
    monkeypatch.setenv("HOME", str(tmp_path))
    runner = CliRunner()
    runner.invoke(cli, ["create", "my-brain", "--path", str(tmp_path),
                        "--description", "test", "--no-git", "--json"])
    result = runner.invoke(cli, ["push", "--json"])
    import json
    data = json.loads(result.output)
    assert result.exit_code == 0
    assert data["brains"][0]["git_enabled"] is False
    assert data["brains"][0]["pushed"] is False
