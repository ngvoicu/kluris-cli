"""Tests for create command options: --no-git, --remote, --branch, wizard guards."""

import json
import subprocess

from click.testing import CliRunner

from kluris.cli import cli
from conftest import create_test_brain
from kluris.core.config import read_global_config


def test_create_no_git(tmp_path, monkeypatch):
    monkeypatch.setenv("KLURIS_CONFIG", str(tmp_path / "config.yml"))
    monkeypatch.setenv("HOME", str(tmp_path))
    runner = CliRunner()
    result = runner.invoke(cli, ["create", "my-brain", "--path", str(tmp_path), "--description", "test", "--no-git", "--json"])
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
                                  "--description", "test", "--remote", str(bare), "--json"])
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
                                  "--description", "test", "--branch", "develop", "--json"])
    assert result.exit_code == 0
    r = subprocess.run(["git", "branch", "--show-current"],
                       cwd=tmp_path / "my-brain", capture_output=True, text=True)
    assert "develop" in r.stdout


def test_create_duplicate_name(tmp_path, monkeypatch):
    monkeypatch.setenv("KLURIS_CONFIG", str(tmp_path / "config.yml"))
    monkeypatch.setenv("HOME", str(tmp_path))
    runner = CliRunner()
    create_test_brain(runner, "my-brain", tmp_path)
    result = runner.invoke(cli, ["create", "my-brain", "--path", str(tmp_path / "other"), "--description", "test", "--json"])
    assert result.exit_code != 0
    assert "already registered" in result.output


def test_create_inside_existing_brain(tmp_path, monkeypatch):
    monkeypatch.setenv("KLURIS_CONFIG", str(tmp_path / "config.yml"))
    monkeypatch.setenv("HOME", str(tmp_path))
    runner = CliRunner()
    create_test_brain(runner, "outer-brain", tmp_path)
    # Try creating inside the outer brain -- caught as "already a brain"
    result = runner.invoke(cli, ["create", "inner", "--path", str(tmp_path / "outer-brain"), "--description", "test", "--json"])
    assert result.exit_code != 0
    assert "already a brain" in result.output


def test_create_path_is_file(tmp_path, monkeypatch):
    monkeypatch.setenv("KLURIS_CONFIG", str(tmp_path / "config.yml"))
    monkeypatch.setenv("HOME", str(tmp_path))
    runner = CliRunner()
    (tmp_path / "afile").write_text("x", encoding="utf-8")
    result = runner.invoke(cli, ["create", "my-brain", "--path", str(tmp_path / "afile"), "--description", "test", "--json"])
    assert result.exit_code != 0
    assert "not a directory" in result.output


def test_create_path_is_brain(tmp_path, monkeypatch):
    monkeypatch.setenv("KLURIS_CONFIG", str(tmp_path / "config.yml"))
    monkeypatch.setenv("HOME", str(tmp_path))
    runner = CliRunner()
    create_test_brain(runner, "existing-brain", tmp_path)
    result = runner.invoke(cli, ["create", "new-brain", "--path", str(tmp_path / "existing-brain"), "--description", "test", "--json"])
    assert result.exit_code != 0
    assert "already a brain" in result.output


def test_create_blank_type(tmp_path, monkeypatch):
    monkeypatch.setenv("KLURIS_CONFIG", str(tmp_path / "config.yml"))
    monkeypatch.setenv("HOME", str(tmp_path))
    runner = CliRunner()
    result = runner.invoke(cli, ["create", "my-brain", "--path", str(tmp_path), "--description", "test", "--type", "blank", "--json"])
    assert result.exit_code == 0
    brain = tmp_path / "my-brain"
    dirs = [d for d in brain.iterdir() if d.is_dir() and d.name != ".git"]
    assert len(dirs) == 0


def test_create_research_type(tmp_path, monkeypatch):
    monkeypatch.setenv("KLURIS_CONFIG", str(tmp_path / "config.yml"))
    monkeypatch.setenv("HOME", str(tmp_path))
    runner = CliRunner()
    result = runner.invoke(cli, ["create", "my-brain", "--path", str(tmp_path), "--description", "test", "--type", "research", "--json"])
    assert result.exit_code == 0
    assert (tmp_path / "my-brain" / "literature").is_dir()
    assert (tmp_path / "my-brain" / "experiments").is_dir()


def test_create_product_type(tmp_path, monkeypatch):
    monkeypatch.setenv("KLURIS_CONFIG", str(tmp_path / "config.yml"))
    monkeypatch.setenv("HOME", str(tmp_path))
    runner = CliRunner()
    result = runner.invoke(cli, ["create", "my-brain", "--path", str(tmp_path), "--description", "test", "--type", "product", "--json"])
    assert result.exit_code == 0
    assert (tmp_path / "my-brain" / "prd").is_dir()
    assert (tmp_path / "my-brain" / "features").is_dir()
