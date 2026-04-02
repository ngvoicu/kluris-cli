"""Agent registry and slash command rendering."""

from __future__ import annotations

from pathlib import Path

AGENT_REGISTRY: dict[str, dict] = {
    "claude": {"dir": ".claude", "subdir": "commands", "format": "md", "args": "$ARGUMENTS"},
    "cursor": {"dir": ".cursor", "subdir": "commands", "format": "md", "args": "$ARGUMENTS"},
    "windsurf": {"dir": ".codeium/windsurf", "subdir": "global_workflows", "format": "md", "args": "$ARGUMENTS"},
    "copilot": {"dir": ".copilot", "subdir": "agents", "format": "agent.md", "args": "$ARGUMENTS"},
    "codex": {"dir": ".codex", "subdir": "skills", "format": "skill.md", "args": "$ARGUMENTS"},
    "gemini": {"dir": ".gemini", "subdir": "commands", "format": "toml", "args": "{{args}}"},
    "kilocode": {"dir": ".config/kilo", "subdir": "commands", "format": "md", "args": "$ARGUMENTS"},
    "junie": {"dir": ".junie", "subdir": "commands", "format": "md", "args": "$ARGUMENTS"},
}

# Full slash command templates matching the spec in reference-templates.md

COMMANDS = {
    "kluris": {
        "description": "Your team's AI brain — read, write, search, learn, and manage shared knowledge",
        "allowed_tools": "Read, Write, Bash(cd:*), Bash(git:*), Bash(grep:*), Bash(find:*), Glob, Grep",
        "body": """\
{args}

{brain_info}

## You are the team's subject matter expert

The brain is a SEPARATE git repo at the path shown above. The current
directory is the PROJECT you're working in.
- ANALYZE the current project
- WRITE to the brain directory
- Never create brain.md, map.md, or kluris.yml in the current project

## Reading protocol

1. Read `<brain_path>/brain.md` — see description, root lobes
2. Pick relevant lobes — read their `map.md` (max 3)
3. Drill into sub-lobes if needed
4. Read specific neurons (max 10)
5. Follow `related:` synapses for connected knowledge
6. Check `glossary.md` for domain terms

## What can you do?

Understand the user's intent from their message:

**Search** — "what do we know about X", "find info about Y"
→ Navigate the brain, read neurons, summarize findings. Read-only.

**Think** — "implement X", "work on Y using brain knowledge"
→ Read the brain first, then work on the task. Apply documented conventions.
  If the task contradicts a documented decision, flag the conflict.

**Learn from project** — "learn the endpoints", "document the schema"
→ Analyze the CURRENT PROJECT, write to the BRAIN.
  Present a plan before writing. Wait for approval.
  Default location: `<brain_path>/services/<project-name>/`
  Never overwrite existing neurons.
  If user asks for OpenAPI: generate `openapi.yml` (OpenAPI 3.1), not markdown.

**Remember** — "remember we chose X", "store that we decided Y"
→ Write a specific piece of knowledge to the brain.
  Find the right lobe, check for existing neurons, ask before writing.

**Create neuron** — "create a decision record about X"
→ Templates: decision (5 sections), incident (6), runbook (5).

**Create lobe** — "create a new section for monitoring"
→ Create directory in brain. Remind user to run `kluris dream`.

## Writing rules

- Frontmatter on every neuron: parent, related, tags, created, updated
- Bidirectional synapses: if A links to B, add reverse link in B
- Focus on decisions and rationale, not just descriptions
- Do NOT edit map.md or brain.md
- After writing, remind user to run `kluris dream` then `kluris push`

## CLI commands (for mechanical operations)

These are terminal commands, not slash commands:
- `kluris dream` — regenerate maps, validate links
- `kluris push` — commit and push brain changes to git
- `kluris mri` — generate interactive visualization
- `kluris templates` — list neuron templates
""",
    },
}


def _render_md(cmd_name: str, cmd: dict, args_placeholder: str,
               copilot: bool = False, brain_info: str = "") -> str:
    """Render a markdown slash command file."""
    body = cmd["body"].replace("{args}", args_placeholder)
    body = body.replace("{brain_info}", brain_info)
    allowed = cmd.get("allowed_tools", "")
    fm = f"---\ndescription: {cmd['description']}\n"
    if copilot:
        fm += f"mode: {cmd_name}\n"
    if allowed:
        fm += f"allowed-tools: {allowed}\n"
    fm += "---\n\n"
    return fm + body + "\n"


def _render_toml(cmd_name: str, cmd: dict, args_placeholder: str, brain_info: str = "") -> str:
    """Render a TOML slash command file."""
    body = cmd["body"].replace("{args}", args_placeholder)
    body = body.replace("{brain_info}", brain_info)
    body = body.replace('"""', '\\"\\"\\"')
    return f'description = "{cmd["description"]}"\n\nprompt = """\n{body}\n"""\n'


def _render_skill_md(cmd_name: str, cmd: dict, args_placeholder: str, brain_info: str = "") -> str:
    """Render a single SKILL.md for one command (spec-kit pattern)."""
    body = cmd["body"].replace("{args}", args_placeholder)
    body = body.replace("{brain_info}", brain_info)
    # Convert kluris.think -> kluris-think for directory name
    skill_name = cmd_name.replace(".", "-")
    frontmatter = (
        "---\n"
        f"name: {skill_name}\n"
        f"description: {cmd['description']}\n"
        "---\n\n"
    )
    return frontmatter + f"# {cmd['description']}\n\n{body}\n"


def render_commands(agent_name: str, output_dir: Path, brain_info: str = "") -> list[Path]:
    """Render all slash command files for an agent into output_dir."""
    reg = AGENT_REGISTRY[agent_name]
    fmt = reg["format"]
    args = reg["args"]
    output_dir.mkdir(parents=True, exist_ok=True)
    files = []

    if fmt == "skill.md":
        for name, cmd in COMMANDS.items():
            skill_name = name.replace(".", "-")
            skill_dir = output_dir / skill_name
            skill_dir.mkdir(parents=True, exist_ok=True)
            content = _render_skill_md(name, cmd, args, brain_info)
            path = skill_dir / "SKILL.md"
            path.write_text(content, encoding="utf-8")
            files.append(path)
    elif fmt == "toml":
        for name, cmd in COMMANDS.items():
            content = _render_toml(name, cmd, args, brain_info)
            path = output_dir / f"{name}.toml"
            path.write_text(content, encoding="utf-8")
            files.append(path)
    elif fmt == "agent.md":
        for name, cmd in COMMANDS.items():
            content = _render_md(name, cmd, args, copilot=True, brain_info=brain_info)
            path = output_dir / f"{name}.agent.md"
            path.write_text(content, encoding="utf-8")
            files.append(path)
    else:
        for name, cmd in COMMANDS.items():
            content = _render_md(name, cmd, args, brain_info=brain_info)
            path = output_dir / f"{name}.md"
            path.write_text(content, encoding="utf-8")
            files.append(path)

    return files


def install_for_agent(agent_name: str, home: Path | None = None) -> list[Path]:
    """Install slash commands for a specific agent at the correct home path."""
    reg = AGENT_REGISTRY[agent_name]
    base = (home or Path.home()) / reg["dir"] / reg["subdir"]
    return render_commands(agent_name, base)
