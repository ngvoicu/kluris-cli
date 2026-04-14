"""Tests for the WSL-aware browser-open helper used by `kluris mri --open`."""

from pathlib import Path
from unittest.mock import patch

from kluris.cli import _is_wsl, _open_in_browser


def test_is_wsl_detects_wsl_distro_name_env(monkeypatch):
    monkeypatch.setenv("WSL_DISTRO_NAME", "Ubuntu-24.04")
    assert _is_wsl() is True


def test_is_wsl_returns_false_without_env_and_without_microsoft_in_proc(monkeypatch):
    monkeypatch.delenv("WSL_DISTRO_NAME", raising=False)
    with patch("builtins.open", side_effect=OSError("no /proc/version")):
        assert _is_wsl() is False


def test_open_in_browser_uses_wslview_when_available_in_wsl(tmp_path, monkeypatch):
    monkeypatch.setenv("WSL_DISTRO_NAME", "Ubuntu-24.04")
    html = tmp_path / "brain-mri.html"
    html.write_text("<html></html>", encoding="utf-8")

    with patch("shutil.which", side_effect=lambda cmd: "/usr/bin/wslview" if cmd == "wslview" else None), \
         patch("subprocess.Popen") as popen, \
         patch("webbrowser.open") as wb_open:
        _open_in_browser(html)

    popen.assert_called_once()
    args = popen.call_args.args[0]
    assert args[0] == "wslview"
    assert args[1] == str(html)
    wb_open.assert_not_called()


def test_open_in_browser_falls_back_to_explorer_in_wsl_without_wslview(tmp_path, monkeypatch):
    monkeypatch.setenv("WSL_DISTRO_NAME", "Ubuntu-24.04")
    html = tmp_path / "brain-mri.html"
    html.write_text("<html></html>", encoding="utf-8")

    def fake_which(cmd):
        return "/mnt/c/Windows/explorer.exe" if cmd == "explorer.exe" else None

    with patch("shutil.which", side_effect=fake_which), \
         patch("subprocess.Popen") as popen, \
         patch("webbrowser.open") as wb_open:
        _open_in_browser(html)

    popen.assert_called_once()
    args = popen.call_args.args[0]
    assert args[0] == "explorer.exe"
    wb_open.assert_not_called()


def test_open_in_browser_uses_webbrowser_outside_wsl(tmp_path, monkeypatch):
    monkeypatch.delenv("WSL_DISTRO_NAME", raising=False)
    html = tmp_path / "brain-mri.html"
    html.write_text("<html></html>", encoding="utf-8")

    with patch("builtins.open", side_effect=OSError), \
         patch("subprocess.Popen") as popen, \
         patch("webbrowser.open") as wb_open:
        _open_in_browser(html)

    wb_open.assert_called_once()
    assert wb_open.call_args.args[0].startswith("file://")
    popen.assert_not_called()
