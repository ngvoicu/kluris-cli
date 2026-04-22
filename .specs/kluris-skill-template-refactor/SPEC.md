---
id: kluris-skill-template-refactor
title: kluris v2.11.0 — Command Cleanup + Embedded Companions + SKILL.md Refactor
status: completed
created: 2026-04-22
updated: 2026-04-22
priority: medium
tags: [kluris, v2.11.0, companions, skill-template, cli-cleanup, specmint]
---

# kluris v2.11.0 — Command Cleanup + Embedded Companions + SKILL.md Refactor

## Overview

Coordinated refactor of kluris-cli and kluris-site. Four coupled changes:

1. **Remove 4 redundant CLI commands**: `install-skills`, `uninstall-skills`,
   `neuron`, `lobe`. Their replacements are already in muscle-memory paths
   (`create`/`clone`/`register`/`remove`/`doctor` auto-refresh skills; agents
   write neurons directly via their Write tool + `kluris dream`).
2. **Embed specmint-core and specmint-tdd inside the kluris package** as
   reference playbooks — NOT as separately-installed skills. Vendored files
   live under `src/kluris/vendored/` at build time; installed copies live
   under `~/.kluris/companions/<name>/` at runtime. Each brain can opt in
   during wizard-style `create`/`clone`/`register`, and can add/remove later.
3. **New `kluris companion` command group** (`add`, `remove`) for managing
   companion opt-ins on existing brains. `kluris list` is expanded to show
   each brain's companions inline.
4. **Refactor `SKILL_BODY` template** — 13 improvements (rename "SME" H2,
   new "When NOT to check" block, dedup, `{brain_path}` fallback, expanded
   CLI examples, etc.) plus a **conditional `{specmint_block}` placeholder**
   that renders per-brain based on that brain's `companions` list.

Version bump **2.10.2 → 2.11.0** (`pyproject.toml` + `src/kluris/__init__.py`).
Doc updates across `README.md`, `AGENTS.md`, kluris-cli `CLAUDE.md`,
kluris-site (`index.html` + `presentation.html`), the workspace-level
`ngvoicu/CLAUDE.md`, AND the brain-generated README that `scaffold_brain()`
writes on `kluris create`.

No new Python dependencies. No npx invocations from kluris. Specmint files
are packaged with kluris and copied into `~/.kluris/companions/` on opt-in.

This `SPEC.md` is the **only** planning artifact for this feature. The older
research/interview notes were intentionally deleted because they described a
different, text-only specmint integration. If implementation needs more
clarification, update this file directly in the Decision Log or Deviations
section rather than recreating sidecar research files.

**Kluris does not version-track companions.** There is no
`get_version()`, no `kluris --version` expansion, no plugin.json read at
runtime, no `refresh_if_stale()` comparison. Companion freshness is
implicitly tied to the kluris version itself: each kluris release ships
whatever specmint state the maintainer synced just before tagging, and
`kluris doctor` unconditionally re-copies vendored → home so a
`pipx upgrade kluris` always lands fresh playbooks. Kluris source code
contains no references to specmint repo paths or git operations — that
knowledge lives only in the maintainer-run `scripts/sync-specmint.py`.

## Acceptance Criteria

### CLI surface

- [x] `kluris install-skills`, `kluris uninstall-skills`, `kluris neuron`,
      and `kluris lobe` all return Click "no such command" errors.
- [x] `kluris --help` lists exactly 17 commands (was 20 — minus 4, plus 1
      new top-level group `companion`).
- [x] `kluris companion --help` shows two subcommands: `add` and `remove`.
- [x] `kluris companion add <name> [--brain X]` and
      `kluris companion remove <name> [--brain X]` accept
      `<name> ∈ {specmint-core, specmint-tdd}` and work on a single
      brain or all brains (`--brain all`).
- [x] `kluris companion add <name>` both persists the opt-in in each
      selected brain's `kluris.yml` AND ensures the companion files exist
      under `~/.kluris/companions/<name>/` before regenerating SKILL.md.
- [x] `kluris companion remove <name>` removes only the selected brain
      opt-ins and regenerates SKILL.md. It does **not** delete
      `~/.kluris/companions/<name>/`; global companion files are cheap,
      reusable, and refreshed by `doctor`.
- [x] `kluris list` text output shows each brain's companion state. If
      the existing Rich table remains, add a `Companions` column; empty
      values read `(none)`. JSON includes `"companions": [...]`.
- [x] `kluris --version` prints `kluris 2.11.0` (no companion version
      expansion — kluris does not track companion versions).
- [x] `kluris create`, `kluris clone`, `kluris register` prompt for
      companions only in wizard-style interactive flows. Fully flag-driven,
      `--json`, non-TTY, and `KLURIS_NO_PROMPT=1` runs skip the prompt
      and persist `companions: []`.

### Embedded companions on disk

- [x] After opt-in for any brain, `~/.kluris/companions/specmint-core/`
      exists and contains exactly one runtime playbook file:
      `SKILL.md`. No `commands/`, `references/`, `agents/`,
      `.claude-plugin/`, README, LICENSE, or other companion sidecars are
      copied into the runtime companion dir.
- [x] Same for `~/.kluris/companions/specmint-tdd/` when opted-in.
- [x] Companion file writes are staged atomically: copy vendored content to
      a sibling temp dir, verify required files, then replace the old
      companion dir. A copy failure leaves any previous companion dir in
      place.
- [x] On `kluris doctor`, every companion referenced by any brain config
      **or** already present on disk is unconditionally re-copied from the
      vendored package. This recreates manually deleted referenced dirs and
      refreshes leftover dirs after `pipx upgrade kluris`. No version
      comparison; refresh is implicit in the kluris version bump.
- [x] `kluris doctor --no-refresh` does not refresh SKILL.md files and does
      not refresh companion dirs.

### Rendered SKILL.md

- [x] Rendered SKILL.md contains a `## Spec-worthy work first` block only
      when the brain has ≥1 companion opt-in.
- [x] When a brain has only `specmint-core`, the block references that
      brain install's absolute runtime companion path
      (`<home>/.kluris/companions/specmint-core/SKILL.md`) and routes
      "TDD project → install tdd via `kluris companion add specmint-tdd`".
- [x] When a brain has only `specmint-tdd`, the block references that
      brain install's absolute runtime companion path similarly.
- [x] When both are installed, the block references both with the
      TDD/non-TDD routing.
- [x] When no companions, the block is omitted entirely (no leftover
      headings or empty sections).
- [x] Rendered SKILL.md uses `## Brain vs current project` (no
      `## You are the team's subject matter expert`).
- [x] Rendered SKILL.md contains a `## When NOT to check the brain`
      exception block (trivial edits, unrelated files, syntactic-only
      refactors).
- [x] Rendered SKILL.md references `{brain_path}` as a direct-read
      fallback for when slash commands aren't available.
- [x] Rendered SKILL.md contains no reference to any removed command
      (`install-skills`, `uninstall-skills`, `neuron`, `lobe`).
- [x] No raw `{placeholder}` tokens leak into rendered output for any
      brain / any companion-state combination.
- [x] The companion block renders in all installed SKILL surfaces:
      per-agent skill dirs, the universal `~/.agents/skills/` mirror, and
      Windsurf workflow files.

### Config / state

- [x] `BrainConfig` Pydantic model has a new `companions: list[str] = []`
      field.
- [x] Reading an older `kluris.yml` without `companions` loads cleanly
      (field defaults to `[]`).
- [x] Writing the `companions` field on mutation (add/remove) round-trips
      correctly.
- [x] Companion names are normalized before writing: only known names are
      persisted, duplicates are removed, and output order follows
      `("specmint-core", "specmint-tdd")`.

### Tests

- [x] `pytest tests/ -v` — all tests pass. Do not rely on an exact test
      count; several command-specific test files are deleted while
      companion lifecycle coverage is added.

### Documentation

- [x] `README.md` (kluris-cli) — no mentions of removed commands; new
      `## Companions` section explaining specmint embedding.
- [x] `AGENTS.md` — `_do_install` caller list updated; new section on
      companion file management.
- [x] `kluris-cli/CLAUDE.md` — command count 20 → 17; new "Companion
      embedding" key design decision; migration paragraph updated.
- [x] `kluris-site/index.html` — commands table updated (remove 4 rows,
      add companion group row); specmint "Works great with" section
      revised to mention built-in embedding.
- [x] `kluris-site/presentation.html` — audit for any command-name
      references to the removed commands; update if found.
- [x] `/Users/gabrielvoicu/Projects/ngvoicu/CLAUDE.md` — kluris version
      reference bumped to 2.11.0; "Common commands" line updated.
- [x] Brain-generated README (from `core/brain.py` `scaffold_brain`)
      updated to mention companions.

### Version

- [x] `pyproject.toml` `version = "2.11.0"`.
- [x] `src/kluris/__init__.py` `__version__ = "2.11.0"`.
- [x] Both match. Verified via `grep -n "2\.10\|2\.11" pyproject.toml
      src/kluris/__init__.py` — only `2.11.0` appears.

## Architecture Diagram

```
Build time (maintainer-only — kluris source has no path/git knowledge):
  ┌─────────────────────────────────────────────────────┐
  │ Local sibling repos on the maintainer's machine     │
  │ (caller passes paths to the script — defaults are   │
  │  the maintainer's layout, overridable via flags):   │
  │   .../specmint/specmint-core/                       │
  │   .../specmint/specmint-tdd/                        │
  └──────────────────────┬──────────────────────────────┘
                         │ scripts/sync-specmint.py (manual, pre-release)
                         │   --core <path>  --tdd <path>   (or defaults)
                         │   copy subtrees → vendored/, no git op required
                         ▼
  ┌─────────────────────────────────────────────────────┐
  │ kluris-cli/src/kluris/vendored/                     │
  │   specmint-core/                                    │
  │     SKILL.md                                        │
  │   specmint-tdd/                                     │
  │     SKILL.md                                        │
  └──────────────────────┬──────────────────────────────┘
                 │ hatch build → wheel
                 ▼
  ┌───────────────────────────────────────────┐
  │ PyPI kluris==2.11.0                       │
  │   (vendored/ shipped as package data)     │
  └───────────────────────────────────────────┘

Runtime (end user on `pipx install kluris`):
  ┌──────────────────────────────────┐
  │ User runs: kluris create <brain> │
  └─────────────┬────────────────────┘
                │ interactive prompt
                ▼
  [?] Install specmint-core? specmint-tdd? both? skip?
                │ user selects e.g. "both"
                ▼
  ┌──────────────────────────────────────────┐
  │ 1. brain's kluris.yml gets:              │
  │    companions: [specmint-core, specmint-tdd]
  │ 2. ~/.kluris/companions/specmint-core/   │
  │    (copied from vendored package)        │
  │ 3. ~/.kluris/companions/specmint-tdd/    │
  │    (copied from vendored package)        │
  │ 4. _do_install() renders per-brain       │
  │    SKILL.md with {specmint_block}        │
  │    pointing at absolute companion paths  │
  └──────────────────────────────────────────┘

Rendered SKILL.md section map (with both companions):
  # Brain: {brain_name}
  ## Spec-worthy work first    ← renders because brain has companions
    → Read <home>/.kluris/companions/specmint-core/SKILL.md (or -tdd)
  ## Bootstrap
  ## Query first — never guess
    ## When NOT to check the brain  [NEW sub-block]
  ## Brain vs current project  [RENAMED — was "You are the SME"]
  ## How the brain is structured
  ## Intent detection  (Search / Think / Learn / Remember / Create)
  ## Writing rules
  ## CLI commands  [EXPANDED with concrete examples, {brain_path} fallback]
```

## Library Choices

| Concern                 | Decision                                                  |
|-------------------------|-----------------------------------------------------------|
| Testing framework       | **pytest** (already in use; no change)                    |
| Templating              | **Inline Python strings** — no Jinja2 (removed in prior refactor per `kluris-cli/CLAUDE.md`). Do NOT reintroduce. |
| Subprocess / npx        | **None.** Kluris does not shell out to npx or any package manager. Specmint files are shipped with the Python package. |
| Interactive prompts     | **Existing Click `prompt`/`IntRange` pattern** (used by `_pick_brain_interactively`). No new `questionary` dep. |
| Version tracking for companions | **None.** Kluris does not track or display companion versions. Companion content travels with the kluris release; bumping kluris implicitly refreshes the bundled playbooks. No `get_version()`, no plugin.json read, no `kluris --version` expansion. |
| Companion payload       | **Exactly one file per companion: `SKILL.md`.** Do not copy `commands/`, `references/`, `agents/`, `.claude-plugin/`, README, LICENSE, or workspace/editor artifacts. The companion SKILL.md must be self-contained enough for the generated Kluris skill to reference it directly. |
| Companion file copy     | **`shutil.copytree`** stdlib with a sibling staging directory. Copy vendored → temp, verify required files, then replace the installed dir. No stale-version comparison, but no half-copied companion dirs either. |
| Packaging              | **Hatch** (already in use). Keep vendored companion files under `src/kluris/vendored/**`; Hatch includes them in the wheel through the existing package selection. Do not add a duplicate `force-include` entry. |

No new runtime dependencies. `pyproject.toml` dependency list unchanged
apart from version bump.

## Phases

### Phase 1 — Remove redundant CLI commands `[completed]`

- [x] [KSTR-01] Delete the `install-skills` Click command in
      `src/kluris/cli.py` (~L2118-2145). Remove its `@cli.command`
      decorator, options, docstring, body, and any supporting helpers
      used ONLY by it (verify via grep).
- [x] [KSTR-02] Delete the `uninstall-skills` Click command in
      `src/kluris/cli.py` (~L2150-2210). Sweep/cleanup logic stays in
      `_do_install()` via `_sweep_kluris()` — still reachable from
      `create`/`clone`/`register`/`remove`/`doctor`.
- [x] [KSTR-03] Delete the `neuron` Click command in `src/kluris/cli.py`
      (~L1316-1387). Agent workflow already bypasses it (Write tool +
      `kluris dream` for map regen).
- [x] [KSTR-04] Delete the `lobe` Click command in `src/kluris/cli.py`
      (~L1390-end-of-function). Same rationale — agents mkdir + Write +
      dream directly.
- [x] [KSTR-05] Verify no other code references the deleted command
      functions (imports, helpers, re-exports). Grep:
      `install_skills|uninstall_skills|def neuron\(|def lobe_cmd`
      should return zero matches in `src/`.

Phase exit check: `kluris --help` lists 16 commands (20 − 4 = 16,
before adding `companion` in Phase 2). Run `pytest tests/` — expect
failures on tests that invoked these commands; those tests are
deleted/rewritten in Phase 4.

### Phase 2 — Vendor specmint + companion subsystem `[completed]`

- [x] [KSTR-06] Create `scripts/sync-specmint.py` — a maintainer-only
      tool that copies the current state of local sibling checkouts
      into the vendored tree. Defaults assume the maintainer's layout
      (`../../specmint/specmint-core/` and `../../specmint/specmint-tdd/`
      relative to kluris-cli) but BOTH paths are overridable via CLI
      flags so no absolute path is hardcoded:
      ```
      python scripts/sync-specmint.py \
        [--core ../../specmint/specmint-core] \
        [--tdd  ../../specmint/specmint-tdd]
      ```
      Mechanism:
      1. Resolve each source path; verify it contains `SKILL.md`.
         Fail clearly if `SKILL.md` is missing.
      2. Sanitize plugin-specific source text into a Kluris companion copy:
         remove Claude/plugin install guidance and rewrite sidecar references
         (`commands/`, `references/`, `agents/`, `.claude-plugin/`,
         `plugin.json`, `npx skills`, `/plugin marketplace`) so the vendored
         `SKILL.md` is self-contained. `--strict` can still fail fast when
         the maintainer wants to validate source self-containment instead of
         using the sanitizer.
      3. For each companion: recreate the vendored companion directory and
         copy only `SKILL.md` into it. Do not copy README, LICENSE,
         commands, references, agents, plugin metadata, local workspace
         files, or editor artifacts.
      4. No version capture. No SYNC.yaml. No git operations. No
         network. The git diff on the resulting commit is the audit
         trail.
      5. The script is the ONLY place in the kluris-cli repo that
         knows about specmint paths. `src/kluris/**` must contain
         zero references to specmint repo paths or specmint git ops
         (verified by grep in KSTR-26).
      The script is not run at user install time; it's a release-prep
      tool for the kluris maintainer, run before tagging a new kluris
      version.
- [x] [KSTR-07] Run the sync script once. Commit the resulting
      `src/kluris/vendored/` tree. Verify the vendored changes are limited
      to `src/kluris/vendored/specmint-core/` and
      `src/kluris/vendored/specmint-tdd/` (plus the sync script from
      KSTR-06 and later planned spec files).
- [x] [KSTR-08] Update `pyproject.toml`:
      - Bump the package version to `2.11.0`.
      - Keep `[tool.hatch.build.targets.wheel] packages = ["src/kluris"]`.
        Do not add a duplicate `force-include` for vendored files; the build
        already includes `src/kluris/vendored/**` once.
      - Verify the build produces a wheel with vendored files included
        (`unzip -l dist/kluris-*.whl | grep vendored`).
- [x] [KSTR-09] Create `src/kluris/core/companions.py`:
      ```python
      """Embedded companion playbooks (specmint-core, specmint-tdd).

      Kluris does not version-track companions. Refresh is unconditional;
      the kluris version itself is the only freshness signal.
      """
      from __future__ import annotations
      import shutil
      from pathlib import Path

      KNOWN = ("specmint-core", "specmint-tdd")
      _VENDORED = Path(__file__).parent.parent / "vendored"
      _HOME_COMPANIONS_REL = Path(".kluris") / "companions"

      def normalize(names: list[str]) -> list[str]: ...
      def vendored_dir(name: str) -> Path: ...
      def installed_dir(name: str, home: Path) -> Path: ...
      def is_installed(name: str, home: Path) -> bool: ...
      def install(name: str, home: Path) -> None:
          """Stage vendored copy, verify required files, then replace dest."""
      def uninstall(name: str, home: Path) -> None:
          """rmtree the home dir for this companion."""
      def refresh(name: str, home: Path) -> None:
          """Same as install — unconditional re-copy. No version compare."""
      def referenced(config: GlobalConfig) -> list[str]:
          """Known companions referenced by any registered brain config."""
      ```
      Module contains zero references to specmint upstream paths or git.
      Only knows the names in `KNOWN` and the vendored subdir layout.
      `install()` never deletes a working existing dir until the staged copy
      succeeds and contains `SKILL.md`. It does not read or require
      `.claude-plugin/plugin.json`, and it does not copy or require any
      companion sidecar directories.
- [x] [KSTR-10] Extend `BrainConfig` in `src/kluris/core/config.py`:
      ```python
      class BrainConfig(BaseModel):
          name: str
          description: str = ""
          git: GitConfig = Field(default_factory=GitConfig)
          agents: AgentsConfig = Field(default_factory=AgentsConfig)
          companions: list[str] = Field(default_factory=list)   # NEW
      ```
      Verify old `kluris.yml` files without `companions` load cleanly
      (field defaults to `[]` per Pydantic). Add a round-trip test in
      Phase 4. Use `Field(default_factory=...)` for mutable defaults touched
      in this spec.
- [x] [KSTR-11] Add `kluris companion` command group with `add` and
      `remove` subcommands in `src/kluris/cli.py`. Pattern:
      ```python
      @cli.group(cls=KlurisGroup)
      def companion(): ...

      @companion.command("add")
      @click.argument("name", type=click.Choice(["specmint-core", "specmint-tdd"]))
      @click.option("--brain", "brain_name", help="Brain name or 'all'")
      @click.option("--json", "as_json", is_flag=True)
      def companion_add(name, brain_name, as_json): ...
      ```
      Behavior on `add`:
      1. Resolve brain(s) — honor `--brain all` for fan-out
      2. Ensure `~/.kluris/companions/<name>/` is populated from
         vendored with `companions.install(name, home)` before rendering
         SKILL.md. This is unconditional refresh, not stale comparison.
      3. Append `<name>` to each resolved brain's `companions` list
         (no-op if already present), normalize/de-dupe, and write
         `kluris.yml`
      4. Call `_do_install()` so SKILL.md regenerates with the new block
      5. JSON output shape:
         `{"ok": true, "name": "<companion>", "brains": ["a", "b"], "opted_in": true, "files_copied": true}`
      Behavior on `remove`:
      1. Resolve brain(s)
      2. Remove `<name>` from each brain's `companions` list, normalize,
         and write `kluris.yml`
      3. Call `_do_install()`
      4. If NO brain references `<name>` anymore, leave
         `~/.kluris/companions/<name>/` in place (small, harmless; user
         can `rm -rf` manually). Document this in help text.
      5. JSON output shape:
         `{"ok": true, "name": "<companion>", "brains": ["a", "b"], "opted_in": false, "files_kept": true}`
- [x] [KSTR-12] Add interactive consent prompt to `create`, `clone`,
      and `register` command bodies. Prompt only when the command is already
      in a wizard-style interactive path (missing required inputs and
      `_is_interactive()`, not `--json`, not `KLURIS_NO_PROMPT`). Fully
      flag-driven calls keep the existing "no prompts" contract and default
      to no companions. Prompt once:
      ```
      Install specmint companions for this brain?
        [1] specmint-core (forge → interview → spec)
        [2] specmint-tdd  (same, with strict red-green-refactor)
        [3] both
        [4] skip
      Choice [4]:
      ```
      Default: `4` (skip). On non-interactive, skip silently (user can
      run `kluris companion add ...` later). Write selection into the
      new brain's `kluris.yml` `companions` field BEFORE `_do_install()`
      runs so the first rendered SKILL.md already has the block. For each
      selected companion, also call `companions.install(name, home)` before
      `_do_install()` so the block never points at a missing playbook.
      Preserve existing `clone`/`register` cleanup contracts if companion
      install fails: the command fails clearly; zip clones still clean up
      owned extracted dirs, directory registration never deletes the user's
      source brain.
- [x] [KSTR-13] Expand `kluris list` output. Text mode: keep the
      existing Rich table style if present and add a `Companions` column
      (or equivalent per-brain field if the table is later replaced).
      Values are `<name1>, <name2>` or `(none)`. JSON mode: include
      `"companions": [...]` in each brain's dict. Lookups read the
      brain's `kluris.yml`; missing/stale brain paths show `(unknown)`
      in text and `"companions": null` in JSON instead of crashing list
      output.
- [x] [KSTR-14] Update workspace `/Users/gabrielvoicu/Projects/ngvoicu/CLAUDE.md`
      table rows for specmint-core and specmint-tdd: drop the pinned
      `v2.0.0` cells (originally `v1.0.1`, bumped during this work). Either delete the Version column entirely
      from those tables or replace the specmint cell values with `—`.
      Rationale: kluris source no longer tracks companion versions, so
      the workspace doc shouldn't either. (No edits to specmint repos
      themselves are required by this spec — those happen out-of-band.)
- [x] [KSTR-15] Extend `kluris doctor` to refresh companions as part of
      the same refresh surface as SKILL.md. When `--no-refresh` is absent,
      compute the target set as:
      1. known companion dirs currently present under `~/.kluris/companions/`
      2. known companion names referenced by any registered brain's
         `kluris.yml`
      For every name in that union, call `companions.refresh(name, home)`
      unconditionally. This recreates a manually deleted dir when a brain
      still opts into it, and refreshes leftover dirs even after all brains
      remove the opt-in. No version compare. Log one line per companion:
      "refreshed specmint-core". Add these results to `doctor --json` under
      `"companions": [{"name": "...", "refreshed": true}]`.

Phase exit check: `pipx install -e .` locally, run `kluris create
foo --path /tmp/foo`, accept specmint-core at the prompt, verify
`~/.kluris/companions/specmint-core/SKILL.md` exists, `kluris list`
shows `specmint-core` in the companion state, `kluris --version` prints exactly
`kluris 2.11.0`.

### Phase 3 — `SKILL_BODY` refactor + `{specmint_block}` `[completed]`

Each task edits `src/kluris/core/agents.py`. The existing placeholders
stay untouched: `{skill_name}`, `{brain_name}`, `{brain_path}`,
`{git_label}`, `{brain_description}`, `{brain_flag_hint}`,
`{brain_flag_hint_inline}`. One new placeholder is added:
**`{specmint_block}`**. The renderer must also accept companion state:

```python
render_skill(..., companions: list[str] | None = None, companion_home: str | None = None)
render_commands(..., companions: list[str] | None = None, companion_home: str | None = None)
_render_workflow(..., companions: list[str] | None = None, companion_home: str | None = None)
```

`_do_install()` is responsible for reading each brain's `kluris.yml`,
normalizing `companions`, computing the absolute runtime companion home
(`Path.home() / ".kluris" / "companions"`), and passing both values into
every render call: per-agent SKILL.md, Windsurf workflow, and universal
`~/.agents/skills/`. Direct unit-test calls can omit `companion_home`
when no companion block is rendered.

Layer-1 generated skill changes in plain English:

- Add an optional `## Spec-worthy work first` block near the top when
  the brain opts into one or more companions. This block points to the
  companion `SKILL.md` path and tells the agent when to read it.
- Keep small one-file edits moving directly; companions are for
  multi-step features, refactors, migrations, and TDD-heavy work.
- Rename the vague "subject matter expert" heading to
  `## Brain vs current project` so the generated skill explains the
  boundary between durable brain knowledge and the user's current repo.
- Add `## When NOT to check the brain` so trivial edits, unrelated files,
  generated/vendor files, and syntax-only refactors don't force a brain
  lookup.
- Collapse repeated "preview, stop, get approval, then write" guidance
  into one `### Approval protocol` section used by Learn/Remember/Create.
- Add a direct `{brain_path}` fallback for machines where the `kluris`
  command is unavailable.
- Expand CLI command examples for remaining commands and remove the
  deleted command references (`install-skills`, `uninstall-skills`,
  `kluris neuron`, `kluris lobe`).
- Tighten duplicate bootstrap/snapshot/deprecation prose and reorganize
  intent detection so the skill reads as: what the brain is, how to use
  it, when to update it.

- [x] [KSTR-16] Finding #2 + #7: Rename the H2 at
      `src/kluris/core/agents.py:119` (`## You are the team's subject
      matter expert`) to `## Brain vs current project`. Collapse the
      three approval/sacred-brain blurbs (L126, L232-233, L250-251,
      L298-299, L310) into one clear "Approval protocol" mini-section
      referenced by the Learn/Remember/Create flows.
- [x] [KSTR-17] Finding #3: Add a `## When NOT to check the brain`
      sub-section (inside or under `## Query first`):
      - Trivial edits (typo fixes, import reorderings, comment-only
        changes)
      - Files clearly outside the brain's domain (generated artifacts,
        vendored third-party code, lockfiles)
      - Syntactic-only refactors (rename variable, extract constant,
        reformat)
      Phrase as an exception list, not blanket permission to skip.
- [x] [KSTR-18] Finding #4: Consolidate snapshot/deprecation guidance.
      Authoritative description stays in `## Bootstrap` (deprecation[]
      bullet L78-83; caching prose L85-87). Replace the duplicates at
      L115-117 and L158-161 with short pointers ("see Bootstrap above
      for deprecation handling").
- [x] [KSTR-19] Finding #5: Expand `## CLI commands` bullets (L357-367)
      with one concrete invocation per command, including real flag
      usage. Remove the `neuron` and `lobe` bullets entirely (commands
      deleted in Phase 1). Example upgrade:
      ```
      - `kluris search "oauth flow" --brain foo --json` — ranked search
        across neurons, glossary, brain.md. First thing to run for
        "what do we know about X". Use `--lobe <name>` to scope,
        `--tag <t>` to filter, `--limit 20` for more. Results with
        `deprecated: true` are stale.
      ```
- [x] [KSTR-20] Finding #6: Add a `{brain_path}` fallback note near
      the top of `## Bootstrap`:
      > If the `kluris` CLI is unavailable (not on PATH, fresh machine
      > before `pipx install kluris`), the brain is a plain filesystem
      > tree at `{brain_path}`. Read `brain.md`, `glossary.md`, and
      > each lobe's `map.md` directly with your Read tool. Slower
      > (no pre-indexed snapshot) but fully functional.
- [x] [KSTR-21] Finding #8: Restructure `## Intent detection` flow —
      "what is this brain" (from Bootstrap) → "how to use it" (Search/
      Think/Learn/Remember/Create) → "when to update it" (Writing rules).
      Reshuffle only; no new content.
- [x] [KSTR-22] Finding #9: Tighten wake-up/search/dream prose in
      `## Intent detection > Search` (L167-185) and `## CLI commands`.
      Target ~30% reduction while preserving every actionable flag
      and the deprecated-result warning.
- [x] [KSTR-23] Finding #1 + #7: Extract the "show preview → STOP →
      await approval → write" protocol into a single `### Approval
      protocol` sub-section inside `## Writing rules`. Have Learn
      (Step 4 wizard L239-251), Remember (L294-299), and Create neuron
      (L302-310) reference it by name instead of restating.
- [x] [KSTR-24] Finding #10: Verify no references remain to the 4
      removed CLI invocations: `install-skills`, `uninstall-skills`,
      `kluris neuron`, and `kluris lobe`. Grep
      `src/kluris/core/agents.py` — those exact command strings must be
      gone post-edit. Domain words like "neuron" and "lobe" remain valid
      in brain content. Also remove the deleted commands from the
      `brain-mutating commands` list at L91-92.
- [x] [KSTR-25] Finding #11: Insert the new `{specmint_block}`
      placeholder between L49 and L51 (after brain header, before
      `## Bootstrap`). Example placement:
      ```python
      SKILL_BODY = """\
      # Brain: {brain_name}

      You are the SME for the **{brain_name}** brain. The brain lives at
      `{brain_path}` ({git_label}). Description: {brain_description}

      This skill is bound to exactly one brain. Do not look for other
      brains. Do not invent brain switching logic.{brain_flag_hint}
      {specmint_block}
      ## Bootstrap
      ...
      """
      ```
      The placeholder is replaced with either:
      - **empty string** when `brain.companions == []`
      - **full block** when ≥1 companion is installed, with paths and
        routing determined by which companions are in the list
      Content variants in `_build_substitutions`:
      ```python
      _SPECMINT_BOTH = """
      ## Spec-worthy work first

      When the user proposes multi-step work (new feature, refactor
      across files, migration, new subsystem), pause before coding
      and follow the embedded specmint playbook:

      - TDD project → read `{companion_home}/specmint-tdd/SKILL.md`
      - Otherwise → read `{companion_home}/specmint-core/SKILL.md`

      These playbooks include the full research → interview →
      spec-writing protocol. Kluris ships them embedded — do NOT
      direct users to install a separate specmint skill/package.

      Small single-file edits don't need a spec — proceed directly.
      """

      _SPECMINT_CORE_ONLY = """... same but only points at core,
      and suggests `kluris companion add specmint-tdd` for TDD work ..."""

      _SPECMINT_TDD_ONLY = """... same but only points at tdd ..."""
      ```
      Do NOT hardcode `:forge` or any specmint sub-command — agent
      resolves the right invocation from the referenced SKILL.md.
      Implementation notes:
      - Add `companions` and `companion_home` parameters to
        `_build_substitutions()`, `render_skill()`, `_render_workflow()`,
        and `render_commands()`.
      - `_build_substitutions()` should require `companion_home` only when
        it needs to render a non-empty companion block; the no-companion
        path stays backwards-compatible for direct unit-test calls.
      - Update `_do_install()`'s `_render_kwargs()` helper to read
        `read_brain_config(Path(entry.path)).companions` when available,
        normalize it through `companions.normalize()`, compute the
        absolute runtime companion home as a POSIX string, and pass both
        values through every render surface.
      - Use the same companion-aware kwargs for the universal
        `~/.agents/skills/` mirror and the Windsurf workflow staging path.
      - Direct unit-test calls may keep the default `companions=None`,
        which behaves exactly like `[]`.
- [x] [KSTR-26] Finding #12 + #13: Final proofread pass. Render
      `SKILL_BODY` mentally for every combination (0/core/tdd/both
      companions, 1-brain / multi-brain). Confirm no raw `{placeholder}`
      tokens survive. Confirm `{brain_flag_hint}` and
      `{brain_flag_hint_inline}` still interpolate correctly after
      structural edits. Run the existing
      `tests/test_agents.py::test_render_skill_substitutes_all_placeholders`
      mentally against the new template. Also grep the entire
      `src/kluris/` tree (excluding `vendored/`) for any reference to
      specmint upstream paths or git operations targeting specmint:
      ```
      grep -rn --exclude-dir=vendored \
        "specmint-core/\|specmint-tdd/\|/specmint/\|\.specmint\." \
        src/kluris/
      ```
      Expected: no upstream repo paths, URLs, git commands, or package-manager
      install commands. Allowed matches are:
      - `KNOWN = ("specmint-core", "specmint-tdd")`
      - rendered companion paths under the absolute runtime
        `.kluris/companions/<name>/` home
      - CLI help/test strings that name the known companions
      Catalog any unexpected hit.

Phase exit check: Read
`src/kluris/core/agents.py:43-420` end-to-end. Confirm: new
heading structure, `{specmint_block}` placeholder in place, no stray
references to removed commands, `## Brain vs current project` and
`## When NOT to check the brain` both present.

### Phase 4 — Tests `[completed]`

- [x] [KSTR-27] `tests/test_agents.py` — rewrite snapshot assertions
      against the new `SKILL_BODY` structure. Every existing test that
      asserts a specific heading string gets updated.
- [x] [KSTR-28] New:
      `tests/test_agents.py::test_specmint_block_none` — render with
      `companions=[]`; assert rendered body does NOT contain
      `## Spec-worthy work first` AND no leftover `{specmint_block}`.
- [x] [KSTR-29] New:
      `tests/test_agents.py::test_specmint_block_core_only` — render
      with `companions=["specmint-core"]`; assert body contains
      `## Spec-worthy work first`, references the `companion_home`
      path supplied by the test (for example
      `/tmp/kluris-companions/specmint-core/SKILL.md`), and does NOT
      reference the tdd path.
- [x] [KSTR-30] New:
      `tests/test_agents.py::test_specmint_block_tdd_only` — same but
      for tdd, using the supplied `companion_home` test path.
- [x] [KSTR-31] New:
      `tests/test_agents.py::test_specmint_block_both` — render with
      `companions=["specmint-core", "specmint-tdd"]`; assert body
      contains both supplied `companion_home` paths and the
      TDD-vs-non-TDD routing.
- [x] [KSTR-32] New:
      `tests/test_agents.py::test_brain_vs_current_project_heading` —
      rendered body contains `## Brain vs current project` and does
      NOT contain `You are the team's subject matter expert`.
- [x] [KSTR-33] New:
      `tests/test_agents.py::test_when_not_to_check_block` — rendered
      body contains `When NOT to check the brain` and ≥1 listed
      exception keyword (e.g. `typo`, `trivial`, `vendored`).
- [x] [KSTR-34] New file `tests/test_companions.py` covering
      `core/companions.py`:
      - `test_install_copies_files_to_home`
      - `test_install_keeps_existing_dir_on_copy_failure`
      - `test_uninstall_removes_dir` (helper-level behavior only; CLI
        remove intentionally does not call it)
      - `test_refresh_overwrites_user_modifications` — write garbage
        into a copied file, call `refresh()`, assert garbage gone
      - `test_refresh_idempotent_back_to_back` — call `refresh()`
        twice, second call still leaves a clean dest tree
      - `test_normalize_dedupes_and_orders_known_names`
      - `test_referenced_reads_known_companions_from_brain_configs`
      - `test_companions_module_no_upstream_coupling` — grep the module
        source to ensure known companion names appear only in `KNOWN` or
        vendored/home layout code, and ensure no upstream paths, URLs,
        package-manager commands, or `git` subprocess imports leak in
      Uses `temp_home` fixture; patches `_VENDORED` to a test fixture
      dir containing a minimal fake tree with only `SKILL.md`. No
      plugin.json or sidecar directory reading.
- [x] [KSTR-35] New file `tests/test_companion_cli.py`:
      - `test_companion_add_specmint_core` — one brain, add core,
        assert kluris.yml updated + companions dir populated +
        SKILL.md contains spec-worthy block
      - `test_companion_remove_specmint_core` — reverse
      - `test_companion_add_all` — `--brain all` with 2 brains
      - `test_companion_add_idempotent` — add twice, no-op second
        time
      - `test_companion_add_noninteractive_json` — `--json` output
        shape
      - `test_companion_remove_leaves_global_dir` — removing the last
        brain opt-in regenerates SKILL.md but leaves the copied playbook
        directory in place
      - `test_companion_add_invalid_name` — `foo` rejected with
        Click choice error
- [x] [KSTR-36] New:
      `tests/test_create.py::test_create_prompt_specmint` (or in
      existing test_create.py) — interactive create prompts for
      companions; monkeypatch `click.prompt` to simulate selection;
      assert resulting `kluris.yml`, copied companion dir, and SKILL.md
      state.
- [x] [KSTR-37] New:
      `tests/test_create.py::test_create_noninteractive_skips_prompt`
      — under `--json`, no prompt fires, `companions=[]` in result.
      Also update existing "all flags skips prompts" coverage to assert
      companion prompt is skipped in fully flag-driven text mode.
- [x] [KSTR-38] New clone/register coverage:
      - `tests/test_clone.py::test_clone_wizard_prompt_specmint`
      - `tests/test_clone.py::test_clone_flag_driven_skips_companion_prompt`
      - `tests/test_register.py::test_register_wizard_prompt_specmint`
      - `tests/test_register.py::test_register_flag_driven_skips_companion_prompt`
      These mirror create behavior and assert config + copied files +
      rendered SKILL.md.
- [x] [KSTR-39] Update `tests/test_cli_extras.py:99-100` — replace
      the positive assertions about `install-skills` / `uninstall-skills`
      (and `neuron` / `lobe` if asserted) in `kluris --help` output
      with negative assertions. Add new positive assertion that
      `companion` appears.
- [x] [KSTR-40] Delete `tests/test_install.py` cases that invoke
      `kluris install-skills` / `kluris uninstall-skills` directly.
      Keep all `_do_install()` tests that go through
      `create`/`clone`/`register`/`remove`/`doctor`. Rewrite the partial
      failure regression to trigger `_do_install()` through `doctor`, since
      the direct install command is gone.
- [x] [KSTR-41] Update `tests/test_json_output.py`: remove JSON tests for
      deleted `install-skills`, `neuron`, and `lobe`; add JSON assertions
      for `companion add/remove`, `list` companion field, and `doctor`
      companion refresh output.
- [x] [KSTR-42] Remove or rewrite every test path that invokes deleted
      `neuron` / `lobe` commands:
      - delete `tests/test_neuron.py`
      - delete `tests/test_lobe.py`
      - update `tests/test_e2e.py` to create neuron files directly and run
        `dream`, matching the agent workflow
      - update `tests/test_brain_resolution.py` cases that used `neuron`
        to use a remaining single-brain command or delete obsolete coverage
      - update `tests/test_agents.py` refresh-trigger assertions to remove
        `kluris neuron` / `kluris lobe`
- [x] [KSTR-43] New:
      `tests/test_cli_extras.py::test_removed_commands_gone` — invoking
      `kluris install-skills`, `uninstall-skills`, `neuron`, `lobe`
      all return Click "no such command" (one test with a loop
      over the 4 names).
- [x] [KSTR-44] New:
      `tests/test_cli_extras.py::test_version_does_not_mention_companions`
      — `kluris --version` output is exactly `kluris 2.11.0` (no
      `specmint-core`, no `specmint-tdd`, no version expansion).
      Regression guard against re-introducing companion version
      tracking.
- [x] [KSTR-45] New:
      `tests/test_list.py::test_list_shows_companions` — brain with
      `companions: [specmint-core]` renders `specmint-core` in the
      text companion state (for the table path, under the `Companions`
      column) and `"companions": ["specmint-core"]` in JSON.
- [x] [KSTR-46] Update `tests/test_config.py` (or add new
      `test_config_companions.py`) — round-trip `companions` field
      in `BrainConfig`: old YAML without the field loads with `[]`;
      write-then-read preserves values.
- [x] [KSTR-47] Update `tests/test_doctor.py` — `doctor` refreshes
      companions referenced by brain config even if the dir was manually
      deleted; `doctor --no-refresh` skips both SKILL.md refresh and
      companion refresh; `doctor --json` includes companion refresh rows.

Phase exit check: `pytest tests/ -v` — all green. Expected count
is intentionally approximate because entire command test files are removed
while companion lifecycle tests are added. The important gate is all tests
green, not the exact count.

### Phase 5 — Documentation `[completed]`

- [x] [KSTR-48] `README.md` (kluris-cli) — full rewrite of affected
      sections:
      - Remove every mention of `install-skills`, `uninstall-skills`,
        `neuron`, `lobe`
      - Add a new `## Companions` section explaining the embedded
        specmint playbooks, opt-in prompt during create, and
        `kluris companion add/remove`
      - Update the "What kluris generates" / "Commands" enumeration
        to 17 commands
      - Revise the existing specmint section (L487-526) to reflect
        that kluris ships specmint embedded with no external setup step
- [x] [KSTR-49] `AGENTS.md` — update the `_do_install` callers list
      (drop `install-skills`, add `companion add/remove`). Add a new
      section on companion file management
      (`~/.kluris/companions/<name>/`, refresh semantics).
- [x] [KSTR-50] `kluris-cli/CLAUDE.md` — five edits:
      (a) L105 command list 20 → 17. Drop `install-skills`,
          `uninstall-skills`, `neuron`, `lobe`. Add `companion` group.
      (b) Add new key design decision: "**Companions are embedded,
          not installed as separate skills** — specmint-core/tdd
          ship inside the kluris package and are copied to
          `~/.kluris/companions/<name>/` on opt-in. Layer-1 SKILL.md
          references their paths; they are NOT auto-loaded as agent
          skills."
      (c) Add config note: "**BrainConfig.companions** — per-brain
          opt-in list; missing from older kluris.yml defaults to `[]`."
      (d) Migration paragraph (L137-146) updated: replace
          install-skills/uninstall-skills mentions with create/clone/
          register/remove/doctor as the auto-refresh surface.
      (e) New section "Companion refresh on doctor" — `kluris doctor`
          calls `companions.refresh()` for the union of referenced and
          installed known companions so pipx-upgraded kluris auto-updates
          the bundled playbooks without version comparison.
- [x] [KSTR-51] `kluris-site/index.html` — three edits:
      (a) Commands table: remove rows for `install-skills`,
          `uninstall-skills`, `neuron`, `lobe`. Add `companion add`
          and `companion remove` rows.
      (b) "Works great with specmint" section (L1321-1334 era):
          revise prose from "kluris pairs with specmint" to
          "kluris ships specmint embedded — opt in during
          `kluris create`, or add later with
          `kluris companion add specmint-core`".
      (c) Verify the surrounding markup remains valid after deletions
          (balanced `<tbody>`, no orphan `<tr>`).
- [x] [KSTR-52] `kluris-site/presentation.html` — grep for mentions
      of the 4 removed commands AND for any CLI command enumerations.
      Update whatever appears. If nothing matches, skip (no change
      needed). Also verify there's no outdated specmint install
      guidance.
- [x] [KSTR-53] `/Users/gabrielvoicu/Projects/ngvoicu/CLAUDE.md`
      (workspace):
      - Bump kluris version reference: `v2.10.1` → `v2.11.0`
      - Update "Common commands" line to reflect new command set
      - Optionally add one line about embedded companions
      Note: the version-column edits for the specmint rows already
      land in KSTR-14; this task only handles the kluris row + commands
      line.
- [x] [KSTR-54] Brain-generated README (written by `scaffold_brain()`
      in `src/kluris/core/brain.py` on `kluris create`) — update the
      generated text to mention companions:
      - Short blurb: "This brain can be paired with specmint
        playbooks via `kluris companion add specmint-core`"
      - Adjust any existing references to the removed commands
- [x] [KSTR-55] Grep full kluris-cli and kluris-site repos for any
      remaining mention of the 4 removed commands.
      `grep -rn "install-skills\|uninstall-skills\|kluris neuron\|
      kluris lobe"` across both repos — zero matches.

Phase exit check: every file listed above passes the grep test.
Manual read of each updated file — no stale cross-references.

### Phase 6 — Version bump + verification `[completed]`

- [x] [KSTR-56] Bump `pyproject.toml` `version = "2.10.2"` → `"2.11.0"`.
- [x] [KSTR-57] Bump `src/kluris/__init__.py`
      `__version__ = "2.10.2"` → `"2.11.0"`. Both must match (per
      `reference_pypi_publish_version_bump.md`).
- [x] [KSTR-58] Run full test suite: `pytest tests/ -v`. All green.
- [x] [KSTR-59] `hatch build --clean`. Inspect wheel:
      `unzip -l dist/kluris-2.11.0-py3-none-any.whl | grep vendored`
      — confirm `kluris/vendored/specmint-core/**` and
      `kluris/vendored/specmint-tdd/**` contain only `SKILL.md` under
      each companion directory.
- [x] [KSTR-60] Local install smoke test: in a scratch dir,
      `pipx install --force dist/kluris-2.11.0-py3-none-any.whl`.
      Run:
      - `kluris --version` → exactly `kluris 2.11.0` (no companions)
      - `kluris --help` → 17 commands
      - `kluris create test-brain --path /tmp/kluris-rc-test` →
        interactive prompt for companions
      - `kluris list` → shows companion state
      - `kluris companion add specmint-tdd --brain test-brain`
      - Read `~/.claude/skills/kluris/SKILL.md` — confirm
        spec-worthy block references both paths
- [x] [KSTR-61] Clean up scratch artifacts. Ready to tag `v2.11.0`
      and publish.

Phase exit check: all KSTR-* tasks checked off. Spec status →
`completed`. Ready for `git tag v2.11.0 && git push origin v2.11.0`
(release / publish is the user's manual action, not part of this
spec).

## Testing Strategy

### Frameworks

- **pytest** — already configured via `[project.optional-dependencies].dev`.
- `tests/conftest.py` fixtures (`cli_runner`, `temp_config`, `temp_home`,
  `temp_brain`, `bare_remote`) — reused. `temp_home` is key for
  companion-file tests since they write under `~/.kluris/`.

### Unit tests

- `tests/test_agents.py` — `SKILL_BODY` rendering under all four
  companion combinations (none/core-only/tdd-only/both), plus heading
  renames and the "when NOT to check" block. See tasks KSTR-27 to
  KSTR-33.
- `tests/test_companions.py` (new) — `core/companions.py` helpers:
  install/uninstall/refresh/normalization/reference discovery. See task
  KSTR-34.
- `tests/test_config.py` (updated) — round-trip `companions` field.
  See task KSTR-46.

### Integration tests

- `tests/test_companion_cli.py` (new) — `kluris companion add/remove`
  end-to-end: config mutation, file copying, SKILL.md regeneration.
  See task KSTR-35.
- `tests/test_create.py` (updated) — consent prompt during create,
  both interactive and `--json` paths. See tasks KSTR-36, KSTR-37.
- `tests/test_install.py` (trimmed) — existing `_do_install()` tests
  via `create`/`clone`/`register`/`remove`/`doctor` remain. Only the
  direct-command cases for `install-skills`/`uninstall-skills` are
  deleted.
- `tests/test_list.py` (updated) — `kluris list` output includes
  companion state. See task KSTR-45.

### CLI surface tests

- `tests/test_cli_extras.py` — `--help` assertions updated for the
  new command set, regression guard for removed commands, version
  string does not mention companions. See tasks KSTR-39, KSTR-43, KSTR-44.

### Edge cases

- **Empty `~/.kluris/config.yml`** — no brains. `kluris companion add`
  fails cleanly with "no brains registered". `kluris doctor` still
  runs companion refresh for any stray companions already on disk
  (edge case — unlikely but worth covering).
- **Brain registered before v2.11.0** (no `companions` in kluris.yml)
  — Pydantic defaults to `[]`; SKILL.md renders without the block.
  User opts in later via `kluris companion add`.
- **User manually creates `~/.kluris/companions/foo/`** (not a known
  companion) — ignored by kluris; `doctor` doesn't touch it. Document
  in KSTR-50.
- **User manually deletes `~/.kluris/companions/specmint-core/`** while
  a brain still has it opted in — `doctor` (or the next `companion add`)
  re-creates from vendored package.
- **`pipx upgrade kluris`** — `doctor` run after upgrade unconditionally
  re-copies vendored → home for every known companion that is referenced by
  a brain config or already present on disk. SKILL.md files also regenerate
  with any template changes. No version compare.
- **Multiple brains, one opted in** — `~/.kluris/companions/specmint-core/`
  exists once globally; both brains' SKILL.md files reference the
  same path. Removing the companion from one brain does not delete
  the global files (other brains still use them). Only when the
  companion is in ZERO brains' config does the global dir become
  eligible for cleanup — and we choose NOT to clean up (cheap, and
  users may re-opt-in later).

### What is NOT tested

- Real network access. Kluris never hits PyPI, npm, or GitHub for
  companion content at any time — neither at user runtime nor at
  maintainer sync time. The sync script just `shutil.copytree`s from
  local sibling checkouts; no `git clone`, no `npx`, no `pip install`.
  The script itself is a maintainer-only pre-release tool and is not
  covered by the pytest suite (manual verification only).
- Specmint's own workflows (forge / resume / pause). That's specmint's
  responsibility. Kluris tests only that the SKILL.md correctly points
  at the vendored paths.
- Actual agent behavior (Claude, Cursor, etc. loading the SKILL.md).
  We assert the rendered text is correct; agent interpretation is
  out of scope.

## Decision Log

| Date       | Decision | Rationale |
|------------|----------|-----------|
| 2026-04-22 | Embed specmint-core and specmint-tdd inside the kluris Python package (vendored dir), not as separately-installed skills | Avoids drift problem with external install surfaces (Claude Code marketplace, `npx skills`, manual). Kluris ships the playbooks at a version it controls. Layer-1 SKILL.md references their paths instead of expecting the agent to auto-load them. |
| 2026-04-22 | Companion opt-in is per-brain, tracked in `kluris.yml` `companions: []` | Different brains serve different workflows — forcing a global choice is wrong. Pydantic default `[]` makes older kluris.yml files load cleanly. |
| 2026-04-22 | Vendored copies live at `~/.kluris/companions/<name>/` (Option A), not per-agent | Single source of truth. Kluris can refresh atomically. No repo pollution. The absolute path isn't a problem since the kluris SKILL.md already embeds absolute `{brain_path}` values. |
| 2026-04-22 | Kluris does not version-track companions. No `get_version()`, no `kluris --version` expansion, no plugin.json read at runtime, no `refresh_if_stale()` | Companion freshness piggybacks on the kluris version. Each kluris release re-syncs upstream just before tagging, so installing a new kluris always lands fresh playbooks. Removes a whole class of staleness/comparison logic, keeps the API surface tiny, and ensures kluris source has zero references to specmint upstream identifiers. |
| 2026-04-22 | Companion payload is exactly `SKILL.md` per companion, with no sidecar files | Kluris companions are referenced by the generated Kluris skill; they are not installed as active Claude Code plugins or full skill/plugin folders. Keeping only `SKILL.md` makes the product model simple: a companion is a readable playbook file. The sync script validates that the vendored output is self-contained and can optionally fail on source sidecar references with `--strict`. |
| 2026-04-22 | Remove 4 CLI commands: `install-skills`, `uninstall-skills`, `neuron`, `lobe` | Skills commands are redundant with the 5 existing `_do_install()` callers (`create`/`clone`/`register`/`remove`/`doctor`). Neuron/lobe are bypassed by the agent workflow (Write tool + `kluris dream`). Hard removal — user explicit, no deprecation alias. |
| 2026-04-22 | New `kluris companion` command group (`add`, `remove`) — NOT a `skills` group | `companion` naming distinguishes these from the layer-1 kluris skills (which are auto-managed and invisible to the user). Scope is strictly "opt in/out of embedded playbooks per brain". |
| 2026-04-22 | `kluris list` absorbs companion display — no separate `kluris companion list` command | `kluris list` already shows brain metadata; adding one line per brain is natural. A dedicated `companion list` would be redundant. |
| 2026-04-22 | Do NOT hardcode `:forge` or any specmint sub-command in the spec-worthy block | Agents resolve the right invocation from the referenced runtime companion `SKILL.md` path. Hardcoding couples kluris templates to specmint's internal command naming. |
| 2026-04-22 | `kluris doctor` unconditionally re-copies referenced or installed known companion files when refresh is enabled (no version compare) | Keeps bundled playbooks current after `pipx upgrade kluris`, recreates missing dirs for brains that still opt in, and matches the existing muscle-memory path for skill refresh. Unconditional refresh is cheaper to maintain than a comparison path and avoids needing a version field altogether. |
| 2026-04-22 | Consent prompt in `create`/`clone`/`register` defaults to skip in non-interactive mode | `--json` and `KLURIS_NO_PROMPT=1` are CI/script contexts — silent skip is safer than defaulting-to-opt-in. User can always run `kluris companion add` later. |
| 2026-04-22 | Companion prompt appears only in wizard-style interactive flows, not fully flag-driven runs | Existing Kluris behavior treats fully specified commands as no-prompt paths. Keeping that contract prevents surprise hangs in scripts while still making companions discoverable in the human wizard path. |
| 2026-04-22 | Version bump to `2.11.0` | Minor bump per semver. Breaking changes (removed commands) justify minor, not patch; but not major since brain layout is unchanged. |
| 2026-04-22 | Sync script reads from local sibling checkouts on the maintainer's machine (paths overridable via `--core` / `--tdd` flags), NOT from GitHub. Kluris source code itself contains zero specmint paths or git operations | Simpler: no network at sync time, no temp-dir cleanup, no `git` requirement on the script side, no SYNC.yaml manifest to maintain. The maintainer takes responsibility for "the working tree I'm syncing from is the state I want shipped". Kluris's runtime contract is "kluris ships specmint at whatever upstream state the maintainer synced before this release" — kluris itself does not need to know upstream paths or git URLs. The sync script (`scripts/sync-specmint.py`, outside `src/kluris/`) is the only file that knows about specmint paths, and even there the paths are CLI flags, not constants. |
| 2026-04-22 | Delete the stale research/interview sidecar files and keep this SPEC.md authoritative | The sidecar files described an older text-only plan with no companions, no config, and no new commands. Keeping them would mislead implementation. Future clarification belongs in this SPEC.md. |
| 2026-04-22 | Sanitize source specmint `SKILL.md` into Kluris companion form during sync | The current specmint source skills are universal/plugin-aware and mention `commands/`, `references/`, and `npx skills`. Kluris must ship only one self-contained `SKILL.md` per companion, so the release sync produces a Kluris-safe embedded copy and rejects the output if forbidden plugin/install references remain. |

## Deviations

| Task | Spec said | Actually did | Why |
|------|-----------|--------------|-----|
| KSTR-06 | Fail whenever the source specmint `SKILL.md` mentions sidecar paths. | Default sync sanitizes source text into a Kluris-safe one-file copy, then fails if the vendored output still mentions sidecar/plugin install paths. `--strict` keeps the fail-fast source validation mode. | The upstream specmint skills intentionally support standalone plugin/skill installs. Sanitizing keeps Kluris companions self-contained without forcing unrelated upstream changes before this release. |
| KSTR-08 / KSTR-59 | Add a Hatch `force-include` entry for vendored files. | Removed the force-include after build inspection showed duplicate wheel entries; the existing `packages = ["src/kluris"]` selection includes `src/kluris/vendored/**` once. | Clean wheel artifacts matter more than retaining a redundant packaging directive. |

## Resume Context

> Implementation completed for v2.11.0. Verified with:
> - `.venv/bin/python -m pytest tests/ -q` → 487 passed
> - `.venv/bin/python -m build` → wheel + sdist built
> - isolated `pipx install dist/kluris-2.11.0-py3-none-any.whl`
> - smoke: `kluris --version`, `kluris create --json`, `kluris companion add specmint-core --json`
>
> Final release steps after this spec update: commit the CLI repo, tag
> `v2.11.0`, push the branch and tag. The kluris-site repo has a separate
> docs/presentation commit to push.
> - `tests/conftest.py` — reuse existing fixtures; `temp_home` is the
>   key one for companion tests
>
> Working directory:
> `/Users/gabrielvoicu/Projects/ngvoicu/kluris/kluris-cli/`
>
> Sync script reads from local sibling repos (paths are CLI flags on
> the script, not constants in kluris source):
> - `/Users/gabrielvoicu/Projects/ngvoicu/specmint/specmint-core/`
> - `/Users/gabrielvoicu/Projects/ngvoicu/specmint/specmint-tdd/`
> Whatever is in the local working tree at sync time gets shipped.
> Kluris itself does NOT track companion versions or know about
> these paths — only the maintainer-run `scripts/sync-specmint.py`
> does, and even there the paths are overridable via `--core` and
> `--tdd` flags.
>
> Version at start: `2.10.2`. Target: `2.11.0`. Bump pyproject.toml
> AND `__init__.py` in Phase 6.
>
> Standing preferences (from memory/feedback):
> - Never run `kluris` commands against live disk during implementation
>   — self-test only via pytest
> - Never touch `~/.kluris/` or `~/.claude/skills/` on the real
>   machine — user self-tests as real user
> - Bump version BEFORE tagging
