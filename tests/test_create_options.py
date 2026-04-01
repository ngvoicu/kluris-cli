"""Tests for create command options: --no-git, --remote, --branch, wizard guards."""

import json
import subprocess

from click.testing import CliRunner

from kluris.cli import cli
from kluris.core.config import read_global_config


def test_create_no_git(tmp_path, monkeypatch):
    monkeypatch.setenv("KLURIS_CONFIG", str(tmp_path / "config.yml"))
    monkeypatch.setenv("HOME", str(tmp_path))
    runner = CliRunner()
    result = runner.invoke(cli, ["create", "my-brain", "--path", str(tmp_path), "--no-git"])
    assert result.exit_code == 0
    assert (tmp_path / "my-brain" / "kluris.yml").exists()
    assert not (tmp_path / "my-brain" / ".git").exists()


def test_create_with_remote(tmp_path, monkeypatch):
    monkeypatch.setenv("KLURIS_CONFIG", str(tmp_path / "config.yml"))
    monkeypatch.setenv("HOME", str(tmp_path))
    runner = CliRunner()
    # Create a bare remote
    bare = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", str(bare)], capture_output=True)
    subprocess.run(["git", "symbolic-ref", "HEAD", "refs/heads/main"], cwd=str(bare), capture_output=True)

    result = runner.invoke(cli, ["create", "my-brain", "--path", str(tmp_path),
                                  "--remote", str(bare)])
    assert result.exit_code == 0
    # Check remote was set
    r = subprocess.run(["git", "remote", "-v"], cwd=tmp_path / "my-brain",
                       capture_output=True, text=True)
    assert "origin" in r.stdout
    assert str(bare) in r.stdout


def test_create_with_branch(tmp_path, monkeypatch):
    monkeypatch.setenv("KLURIS_CONFIG", str(tmp_path / "config.yml"))
    monkeypatch.setenv("HOME", str(tmp_path))
    runner = CliRunner()
    result = runner.invoke(cli, ["create", "my-brain", "--path", str(tmp_path),
                                  "--branch", "develop"])
    assert result.exit_code == 0
    r = subprocess.run(["git", "branch", "--show-current"],
                       cwd=tmp_path / "my-brain", capture_output=True, text=True)
    assert "develop" in r.stdout


def test_create_duplicate_name(tmp_path, monkeypatch):
    monkeypatch.setenv("KLURIS_CONFIG", str(tmp_path / "config.yml"))
    monkeypatch.setenv("HOME", str(tmp_path))
    runner = CliRunner()
    runner.invoke(cli, ["create", "my-brain", "--path", str(tmp_path)])
    result = runner.invoke(cli, ["create", "my-brain", "--path", str(tmp_path / "other")])
    assert result.exit_code != 0
    assert "already registered" in result.output


def test_create_inside_existing_brain(tmp_path, monkeypatch):
    monkeypatch.setenv("KLURIS_CONFIG", str(tmp_path / "config.yml"))
    monkeypatch.setenv("HOME", str(tmp_path))
    runner = CliRunner()
    runner.invoke(cli, ["create", "outer-brain", "--path", str(tmp_path)])
    # Try creating inside the outer brain -- caught as "already a brain"
    result = runner.invoke(cli, ["create", "inner", "--path", str(tmp_path / "outer-brain")])
    assert result.exit_code != 0
    assert "already a brain" in result.output


def test_create_path_is_file(tmp_path, monkeypatch):
    monkeypatch.setenv("KLURIS_CONFIG", str(tmp_path / "config.yml"))
    monkeypatch.setenv("HOME", str(tmp_path))
    runner = CliRunner()
    (tmp_path / "afile").write_text("x", encoding="utf-8")
    result = runner.invoke(cli, ["create", "my-brain", "--path", str(tmp_path / "afile")])
    assert result.exit_code != 0
    assert "not a directory" in result.output


def test_create_path_is_brain(tmp_path, monkeypatch):
    monkeypatch.setenv("KLURIS_CONFIG", str(tmp_path / "config.yml"))
    monkeypatch.setenv("HOME", str(tmp_path))
    runner = CliRunner()
    runner.invoke(cli, ["create", "existing-brain", "--path", str(tmp_path)])
    result = runner.invoke(cli, ["create", "new-brain", "--path", str(tmp_path / "existing-brain")])
    assert result.exit_code != 0
    assert "already a brain" in result.output


def test_create_blank_type(tmp_path, monkeypatch):
    monkeypatch.setenv("KLURIS_CONFIG", str(tmp_path / "config.yml"))
    monkeypatch.setenv("HOME", str(tmp_path))
    runner = CliRunner()
    result = runner.invoke(cli, ["create", "my-brain", "--path", str(tmp_path), "--type", "blank"])
    assert result.exit_code == 0
    brain = tmp_path / "my-brain"
    dirs = [d for d in brain.iterdir() if d.is_dir() and d.name != ".git"]
    assert len(dirs) == 0


def test_create_research_type(tmp_path, monkeypatch):
    monkeypatch.setenv("KLURIS_CONFIG", str(tmp_path / "config.yml"))
    monkeypatch.setenv("HOME", str(tmp_path))
    runner = CliRunner()
    result = runner.invoke(cli, ["create", "my-brain", "--path", str(tmp_path), "--type", "research"])
    assert result.exit_code == 0
    assert (tmp_path / "my-brain" / "literature").is_dir()
    assert (tmp_path / "my-brain" / "experiments").is_dir()


def test_create_product_type(tmp_path, monkeypatch):
    monkeypatch.setenv("KLURIS_CONFIG", str(tmp_path / "config.yml"))
    monkeypatch.setenv("HOME", str(tmp_path))
    runner = CliRunner()
    result = runner.invoke(cli, ["create", "my-brain", "--path", str(tmp_path), "--type", "product"])
    assert result.exit_code == 0
    assert (tmp_path / "my-brain" / "prd").is_dir()
    assert (tmp_path / "my-brain" / "features").is_dir()
