"""Git operations wrapper using subprocess."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


def _run(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    """Run a git command and return the result."""
    return subprocess.run(
        args, cwd=cwd, capture_output=True, text=True, check=True,
    )


def _read_git_config(path: Path, key: str) -> str | None:
    """Return a git config value, or None when it is unset."""
    result = subprocess.run(
        ["git", "config", "--get", key],
        cwd=path,
        capture_output=True,
        text=True,
        check=False,
    )
    value = result.stdout.strip()
    return value if result.returncode == 0 and value else None


def _commit_env(path: Path) -> dict[str, str]:
    """Provide transient identity only when git config does not already define one."""
    env = os.environ.copy()
    if _read_git_config(path, "user.name") and _read_git_config(path, "user.email"):
        return env

    env.setdefault("GIT_AUTHOR_NAME", "kluris")
    env.setdefault("GIT_AUTHOR_EMAIL", "kluris@local")
    env.setdefault("GIT_COMMITTER_NAME", env["GIT_AUTHOR_NAME"])
    env.setdefault("GIT_COMMITTER_EMAIL", env["GIT_AUTHOR_EMAIL"])
    return env


def is_git_repo(path: Path) -> bool:
    """Return True when path is inside a git work tree."""
    try:
        result = _run(["git", "rev-parse", "--is-inside-work-tree"], cwd=path)
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False
    return result.stdout.strip() == "true"


def git_init(path: Path) -> None:
    """Initialize a git repo at path."""
    _run(["git", "init"], cwd=path)
    # Set default branch to main
    _run(["git", "checkout", "-b", "main"], cwd=path)


def git_add(path: Path, files: str = "-A") -> None:
    """Stage files. Defaults to staging all."""
    _run(["git", "add", files], cwd=path)


def git_commit(path: Path, message: str) -> None:
    """Create a commit with the given message."""
    subprocess.run(
        ["git", "commit", "-m", message],
        cwd=path,
        capture_output=True,
        text=True,
        check=True,
        env=_commit_env(path),
    )


def git_log(path: Path, limit: int = 10) -> list[dict]:
    """Return recent commits as list of {hash, message, date} dicts."""
    result = _run(
        ["git", "log", f"-{limit}", "--format=%H|%s|%aI"],
        cwd=path,
    )
    entries = []
    for line in result.stdout.strip().splitlines():
        if "|" in line:
            parts = line.split("|", 2)
            entries.append({
                "hash": parts[0],
                "message": parts[1],
                "date": parts[2] if len(parts) > 2 else "",
            })
    return entries


def git_status(path: Path) -> str:
    """Return short git status output. Empty string if clean."""
    result = _run(["git", "status", "--short"], cwd=path)
    return result.stdout.strip()


def git_push(path: Path, remote: str = "origin", branch: str = "main") -> None:
    """Push to remote."""
    _run(["git", "push", remote, branch], cwd=path)


def git_clone(url: str, dest: Path) -> None:
    """Clone a repo to dest path."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    _run(["git", "clone", url, str(dest)], cwd=dest.parent)


def git_file_last_modified(path: Path, filename: str) -> str | None:
    """Get the last modified date of a file from git log."""
    result = _run(
        ["git", "log", "-1", "--format=%aI", "--", filename],
        cwd=path,
    )
    date = result.stdout.strip()
    return date if date else None


def git_file_created_date(path: Path, filename: str) -> str | None:
    """Get the creation date of a file from git log (first commit that added it)."""
    result = _run(
        ["git", "log", "--diff-filter=A", "--format=%aI", "--", filename],
        cwd=path,
    )
    date = result.stdout.strip()
    return date if date else None
