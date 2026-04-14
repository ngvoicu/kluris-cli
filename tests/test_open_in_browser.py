"""Tests for the WSL-aware browser-open helper used by `kluris mri --open`."""

import subprocess
from unittest.mock import MagicMock, patch

from kluris.cli import _is_wsl, _open_in_browser


def test_is_wsl_detects_wsl_distro_name_env(monkeypatch):
    monkeypatch.setenv("WSL_DISTRO_NAME", "Ubuntu-24.04")
    assert _is_wsl() is True


def test_is_wsl_returns_false_without_env_and_without_microsoft_in_proc(monkeypatch):
    monkeypatch.delenv("WSL_DISTRO_NAME", raising=False)
    with patch("builtins.open", side_effect=OSError("no /proc/version")):
        assert _is_wsl() is False


def test_open_in_browser_translates_path_and_uses_cmd_start_in_wsl(tmp_path, monkeypatch):
    """The reliable WSL open path: wslpath -w → cmd.exe /c start "" <win-path>.

    `explorer.exe` opens a File Explorer folder window for UNC paths instead
    of handing the file to its default app -- `cmd.exe /c start` does the
    right thing.
    """
    monkeypatch.setenv("WSL_DISTRO_NAME", "Ubuntu-24.04")
    html = tmp_path / "brain-mri.html"
    html.write_text("<html></html>", encoding="utf-8")

    fake_wslpath_result = MagicMock(stdout=r"\\wsl.localhost\Ubuntu-24.04\tmp\brain-mri.html" + "\n")
    with patch("subprocess.run", return_value=fake_wslpath_result) as run, \
         patch("subprocess.Popen") as popen, \
         patch("webbrowser.open") as wb_open:
        _open_in_browser(html)

    run.assert_called_once()
    assert run.call_args.args[0][0] == "wslpath"
    assert run.call_args.args[0][1] == "-w"

    popen.assert_called_once()
    args = popen.call_args.args[0]
    assert args[:4] == ["cmd.exe", "/c", "start", ""]
    assert args[4] == r"\\wsl.localhost\Ubuntu-24.04\tmp\brain-mri.html"
    wb_open.assert_not_called()


def test_open_in_browser_falls_back_to_webbrowser_if_wslpath_missing(tmp_path, monkeypatch):
    """If wslpath is not on PATH, fall back to webbrowser.open rather than crashing."""
    monkeypatch.setenv("WSL_DISTRO_NAME", "Ubuntu-24.04")
    html = tmp_path / "brain-mri.html"
    html.write_text("<html></html>", encoding="utf-8")

    with patch("subprocess.run", side_effect=FileNotFoundError), \
         patch("subprocess.Popen") as popen, \
         patch("webbrowser.open") as wb_open:
        _open_in_browser(html)

    wb_open.assert_called_once()
    assert wb_open.call_args.args[0].startswith("file://")
    popen.assert_not_called()


def test_open_in_browser_falls_back_to_webbrowser_if_wslpath_errors(tmp_path, monkeypatch):
    monkeypatch.setenv("WSL_DISTRO_NAME", "Ubuntu-24.04")
    html = tmp_path / "brain-mri.html"
    html.write_text("<html></html>", encoding="utf-8")

    err = subprocess.CalledProcessError(1, ["wslpath"], stderr="oops")
    with patch("subprocess.run", side_effect=err), \
         patch("subprocess.Popen") as popen, \
         patch("webbrowser.open") as wb_open:
        _open_in_browser(html)

    wb_open.assert_called_once()
    popen.assert_not_called()


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
