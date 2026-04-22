#!/usr/bin/env python3
"""Sync embedded specmint companion SKILL.md files into kluris."""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CORE = (ROOT / "../../specmint/specmint-core").resolve()
DEFAULT_TDD = (ROOT / "../../specmint/specmint-tdd").resolve()
DEST_ROOT = ROOT / "src" / "kluris" / "vendored"
SIDE_CAR_PATTERNS = (
    "commands/",
    "references/",
    "agents/",
    ".claude-plugin",
    "plugin.json",
    "npx skills",
    "/plugin marketplace",
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Copy specmint companion SKILL.md files into kluris vendored data."
    )
    parser.add_argument("--core", type=Path, default=DEFAULT_CORE)
    parser.add_argument("--tdd", type=Path, default=DEFAULT_TDD)
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail if the source SKILL.md mentions plugin install or sidecar paths.",
    )
    return parser.parse_args()


def _replace_section(content: str, heading: str, next_heading: str, replacement: str) -> str:
    pattern = rf"\n## {re.escape(heading)}\n.*?(?=\n## {re.escape(next_heading)}\n)"
    replacement = replacement.strip()
    if not replacement:
        return re.sub(pattern, "\n", content, flags=re.S)
    return re.sub(pattern, f"\n## {replacement}\n\n", content, flags=re.S)


def _sanitize_for_kluris(name: str, content: str) -> str:
    """Return the single-file companion copy shipped inside kluris."""
    content = _replace_section(content, "Claude Code Plugin", "Session Start", "")
    content = _replace_section(
        content,
        "Command Ownership Map",
        "Spec Format",
        (
            "Embedded Companion Mode\n\n"
            f"This `SKILL.md` is embedded by Kluris as the `{name}` companion. "
            "Do not load plugin sidecar folders or slash-command files; all "
            "runtime instructions needed by Kluris users are in this file."
        ),
    )
    content = _replace_section(
        content,
        "Cross-Tool Compatibility",
        "Behavioral Notes",
        (
            "Kluris Companion Compatibility\n\n"
            "When this file is referenced from a Kluris-generated skill, read "
            "and follow it directly from `~/.kluris/companions/<name>/SKILL.md`. "
            "Do not ask the user to install specmint separately. Specs remain "
            "plain markdown/YAML files that humans can edit and Git can diff."
        ),
    )

    replacements = {
        "See `references/spec-format.md` for the full SPEC.md template.": (
            "Use the Spec Format section in this file as the canonical SPEC.md template."
        ),
        "comprehensive SPEC.md. See `references/spec-format.md` for the full template.": (
            "comprehensive SPEC.md using the Spec Format section in this file."
        ),
        "`references/spec-format.md` has the full template with examples.": (
            "The Spec Format section in this file has the template rules."
        ),
        "Plugin users: see `commands/openapi.md` for the full phase-by-phase workflow.": (
            "Use the OpenAPI workflow in this section; no sidecar command file is required."
        ),
    }
    for old, new in replacements.items():
        content = content.replace(old, new)

    content = re.sub(r"\n{3,}", "\n\n", content)
    return content.strip() + "\n"


def _forbidden_hits(content: str) -> list[str]:
    return [pattern for pattern in SIDE_CAR_PATTERNS if pattern in content]


def _copy_skill(name: str, source: Path, *, strict: bool) -> None:
    source = source.expanduser().resolve()
    source_skill = source / "SKILL.md"
    if not source_skill.is_file():
        raise SystemExit(f"{name}: missing SKILL.md at {source_skill}")

    content = source_skill.read_text(encoding="utf-8")
    hits = _forbidden_hits(content)
    if hits:
        message = (
            f"{name}: SKILL.md mentions plugin install or sidecar paths "
            f"({', '.join(hits)}). Kluris will vendor a sanitized single-file copy."
        )
        if strict:
            raise SystemExit(message)
        print(f"warning: {message}", file=sys.stderr)

    content = _sanitize_for_kluris(name, content)
    output_hits = _forbidden_hits(content)
    if output_hits:
        raise SystemExit(
            f"{name}: sanitized SKILL.md still mentions forbidden paths: "
            f"{', '.join(output_hits)}"
        )

    dest = DEST_ROOT / name
    shutil.rmtree(dest, ignore_errors=True)
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "SKILL.md").write_text(content, encoding="utf-8")
    print(f"synced {name}: {source_skill} -> {dest / 'SKILL.md'}")


def main() -> int:
    args = _parse_args()
    _copy_skill("specmint-core", args.core, strict=args.strict)
    _copy_skill("specmint-tdd", args.tdd, strict=args.strict)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
