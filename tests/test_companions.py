"""Tests for embedded companion playbook helpers."""

from __future__ import annotations

import inspect

import yaml

from kluris.core import companions
from kluris.core.config import BrainEntry, GlobalConfig


def _fake_vendored(tmp_path, monkeypatch):
    root = tmp_path / "vendored"
    for name in companions.KNOWN:
        d = root / name
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text(f"# {name}\n", encoding="utf-8")
    monkeypatch.setattr(companions, "_VENDORED", root)
    return root


def test_install_copies_files_to_home(tmp_path, monkeypatch):
    _fake_vendored(tmp_path, monkeypatch)
    home = tmp_path / "home"

    companions.install("specmint-core", home)

    installed = home / ".kluris" / "companions" / "specmint-core"
    assert (installed / "SKILL.md").read_text(encoding="utf-8") == "# specmint-core\n"
    assert [p.name for p in installed.iterdir()] == ["SKILL.md"]


def test_install_keeps_existing_dir_on_copy_failure(tmp_path, monkeypatch):
    _fake_vendored(tmp_path, monkeypatch)
    home = tmp_path / "home"
    companions.install("specmint-core", home)
    skill = home / ".kluris" / "companions" / "specmint-core" / "SKILL.md"
    skill.write_text("old", encoding="utf-8")
    (tmp_path / "vendored" / "specmint-core" / "SKILL.md").unlink()

    try:
        companions.install("specmint-core", home)
    except FileNotFoundError:
        pass

    assert skill.read_text(encoding="utf-8") == "old"


def test_uninstall_removes_dir(tmp_path, monkeypatch):
    _fake_vendored(tmp_path, monkeypatch)
    home = tmp_path / "home"
    companions.install("specmint-core", home)

    companions.uninstall("specmint-core", home)

    assert not (home / ".kluris" / "companions" / "specmint-core").exists()


def test_refresh_overwrites_user_modifications(tmp_path, monkeypatch):
    _fake_vendored(tmp_path, monkeypatch)
    home = tmp_path / "home"
    companions.install("specmint-core", home)
    skill = home / ".kluris" / "companions" / "specmint-core" / "SKILL.md"
    skill.write_text("garbage", encoding="utf-8")

    companions.refresh("specmint-core", home)

    assert skill.read_text(encoding="utf-8") == "# specmint-core\n"


def test_refresh_idempotent_back_to_back(tmp_path, monkeypatch):
    _fake_vendored(tmp_path, monkeypatch)
    home = tmp_path / "home"

    companions.refresh("specmint-core", home)
    companions.refresh("specmint-core", home)

    assert companions.is_installed("specmint-core", home)


def test_normalize_dedupes_and_orders_known_names():
    assert companions.normalize(["specmint-tdd", "foo", "specmint-core", "specmint-tdd"]) == [
        "specmint-core",
        "specmint-tdd",
    ]


def test_referenced_reads_known_companions_from_brain_configs(tmp_path):
    brain = tmp_path / "brain"
    brain.mkdir()
    (brain / "kluris.yml").write_text(
        yaml.dump({
            "name": "brain",
            "companions": ["specmint-tdd", "unknown", "specmint-core"],
        }),
        encoding="utf-8",
    )

    refs = companions.referenced(GlobalConfig(
        brains={"brain": BrainEntry(path=str(brain))}
    ))

    assert refs == ["specmint-core", "specmint-tdd"]


def test_vendored_companions_are_single_file_self_contained():
    forbidden = [
        "commands/",
        "references/",
        "agents/",
        ".claude-plugin",
        "plugin.json",
        "npx skills",
        "/plugin marketplace",
    ]
    for name in companions.KNOWN:
        root = companions.vendored_dir(name)
        assert [p.name for p in root.iterdir()] == ["SKILL.md"]
        content = (root / "SKILL.md").read_text(encoding="utf-8")
        for pattern in forbidden:
            assert pattern not in content


def test_companions_module_no_upstream_coupling():
    source = inspect.getsource(companions)
    assert "github.com" not in source
    assert "git clone" not in source
    assert "npx" not in source
    assert "/specmint/" not in source
