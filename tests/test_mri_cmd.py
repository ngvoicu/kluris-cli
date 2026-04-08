"""Tests for kluris mri CLI command."""

import json

from click.testing import CliRunner

from kluris.cli import cli
from conftest import create_test_brain


def test_mri_generates_html(tmp_path, monkeypatch):
    monkeypatch.setenv("KLURIS_CONFIG", str(tmp_path / "config.yml"))
    monkeypatch.setenv("HOME", str(tmp_path))
    runner = CliRunner()
    create_test_brain(runner, "my-brain", tmp_path)
    result = runner.invoke(cli, ["mri"])
    assert result.exit_code == 0
    assert (tmp_path / "my-brain" / "brain-mri.html").exists()


def test_mri_custom_output(tmp_path, monkeypatch):
    monkeypatch.setenv("KLURIS_CONFIG", str(tmp_path / "config.yml"))
    monkeypatch.setenv("HOME", str(tmp_path))
    runner = CliRunner()
    create_test_brain(runner, "my-brain", tmp_path)
    custom = tmp_path / "custom-output.html"
    result = runner.invoke(cli, ["mri", "--output", str(custom)])
    assert result.exit_code == 0
    assert custom.exists()


def test_mri_summary(tmp_path, monkeypatch):
    monkeypatch.setenv("KLURIS_CONFIG", str(tmp_path / "config.yml"))
    monkeypatch.setenv("HOME", str(tmp_path))
    runner = CliRunner()
    create_test_brain(runner, "my-brain", tmp_path)
    result = runner.invoke(cli, ["mri"])
    assert "nodes" in result.output.lower() or "MRI" in result.output


def test_mri_json(tmp_path, monkeypatch):
    monkeypatch.setenv("KLURIS_CONFIG", str(tmp_path / "config.yml"))
    monkeypatch.setenv("HOME", str(tmp_path))
    runner = CliRunner()
    create_test_brain(runner, "my-brain", tmp_path)
    result = runner.invoke(cli, ["mri", "--json"])
    data = json.loads(result.output)
    assert data["ok"] is True
    # Unified schema: mri always emits {ok, brains: [...]} regardless of brain count.
    assert "brains" in data
    assert len(data["brains"]) == 1
    entry = data["brains"][0]
    assert entry["name"] == "my-brain"
    assert "nodes" in entry
    assert "edges" in entry
    assert "preflight_fixes" in entry


def test_mri_runs_dream_preflight(tmp_path, monkeypatch):
    monkeypatch.setenv("KLURIS_CONFIG", str(tmp_path / "config.yml"))
    monkeypatch.setenv("HOME", str(tmp_path))
    runner = CliRunner()
    create_test_brain(runner, "my-brain", tmp_path)
    neuron = tmp_path / "my-brain" / "projects" / "orphan.md"
    neuron.write_text(
        "---\nparent: ./map.md\ntags: []\ncreated: 2026-04-01\nupdated: 2026-04-01\n---\n# Orphan\n",
        encoding="utf-8",
    )
    result = runner.invoke(cli, ["mri", "--json"])
    data = json.loads(result.output)
    map_content = (tmp_path / "my-brain" / "projects" / "map.md").read_text(encoding="utf-8")

    assert result.exit_code == 0
    entry = data["brains"][0]
    assert entry["preflight_fixes"]["orphan_references_added"] >= 1
    assert "orphan.md" in map_content


def test_mri_brain_all_emits_single_json_envelope(tmp_path, monkeypatch):
    """`mri --brain all --json` returns ONE JSON envelope with a `brains` array."""
    monkeypatch.setenv("KLURIS_CONFIG", str(tmp_path / "config.yml"))
    monkeypatch.setenv("HOME", str(tmp_path))
    runner = CliRunner()
    create_test_brain(runner, "brain-a", tmp_path)
    create_test_brain(runner, "brain-b", tmp_path)

    result = runner.invoke(cli, ["mri", "--brain", "all", "--json", "--no-open"])
    assert result.exit_code == 0
    # Must parse as a single JSON document (no concatenated objects)
    data = json.loads(result.output)
    assert data["ok"] is True
    assert "brains" in data
    assert len(data["brains"]) == 2
    names = {b["name"] for b in data["brains"]}
    assert names == {"brain-a", "brain-b"}


def test_mri_output_with_brain_all_rejected(tmp_path, monkeypatch):
    """`--output --brain all` is rejected because the file would overwrite N times."""
    monkeypatch.setenv("KLURIS_CONFIG", str(tmp_path / "config.yml"))
    monkeypatch.setenv("HOME", str(tmp_path))
    runner = CliRunner()
    create_test_brain(runner, "brain-a", tmp_path)
    create_test_brain(runner, "brain-b", tmp_path)

    result = runner.invoke(
        cli,
        ["mri", "--brain", "all", "--output", str(tmp_path / "shared.html"), "--no-open"],
    )
    assert result.exit_code != 0
    assert "--output" in result.output and "all" in result.output
