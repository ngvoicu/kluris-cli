"""MRI visualization — build graph from brain and generate standalone HTML."""

from __future__ import annotations

import json
import re
from pathlib import Path

from kluris.core.frontmatter import read_frontmatter
from kluris.core.linker import LINK_PATTERN, _has_yaml_opt_in_block
from kluris.core.neuron_excerpt import extract as _runtime_extract

# Empty HTML anchor tags used as jump targets (`<a id="foo"></a>term`) show
# up as literal markup in the MRI preview because content is `escapeHtml`'d.
# Strip them from the preview text — the jump-target role is a markdown
# feature, not something a human reading the preview needs to see.
_EMPTY_HTML_ANCHOR = re.compile(r'<a\s+id=["\'][^"\']*["\']\s*>\s*</a>', re.IGNORECASE)


def _strip_empty_html_anchors(text: str) -> str:
    return _EMPTY_HTML_ANCHOR.sub("", text)

SKIP_DIRS = {".git"}
# `kluris.yml` at brain root is the local config; never index it as a node.
SKIP_FILES = {".gitignore", "README.md", "kluris.yml"}
YAML_NEURON_SUFFIXES = {".yml", ".yaml"}


def _all_neuron_files(brain_path: Path) -> list[Path]:
    """Collect markdown neurons plus opted-in yaml neurons.

    MRI has its own narrower SKIP_FILES (it keeps `glossary.md`, `index.md`,
    `brain.md`, `map.md` as visible graph nodes — unlike linker/maps which
    hide them). The yaml opt-in gate is the same.
    """
    files: list[Path] = []
    for item in brain_path.rglob("*.md"):
        if any(part in SKIP_DIRS for part in item.parts):
            continue
        if item.name in SKIP_FILES:
            continue
        files.append(item)
    for suffix in ("*.yml", "*.yaml"):
        for item in brain_path.rglob(suffix):
            if any(part in SKIP_DIRS for part in item.parts):
                continue
            if item.name in SKIP_FILES:
                continue
            if not _has_yaml_opt_in_block(item):
                continue
            files.append(item)
    return files


# Backward-compat alias for any external caller.
_all_md_files = _all_neuron_files


def _extract_title_and_excerpt(path: Path, content: str) -> tuple[str, str, str]:
    """Extract a display title, an authored H1 subtitle, and a short excerpt.

    The display title is always the filename stem (hyphens → spaces,
    title-cased) so compact labels everywhere in the MRI read consistently
    — no matter what H1 the author wrote. The authored H1 is returned
    separately so the modal can still surface it as a subtitle when it
    adds information beyond the filename.

    Excerpt extraction itself is delegated to the read-only runtime
    (:func:`kluris_runtime.neuron_excerpt.extract`) so the MRI viewer
    and the packed chat server's ``lobe_overview`` tool agree on what
    counts as the first non-trivial body line.
    """
    display_title = path.stem.replace("-", " ").title()
    authored_title, excerpt = _runtime_extract(path, content)
    # The runtime falls back to a stem-titleized title when no H1 is
    # present; mri only wants the *authored* H1 here so it can decide
    # whether to surface it as a modal subtitle.
    if authored_title == display_title:
        authored_title = ""
    return display_title, authored_title, excerpt


def _build_content_preview(content: str) -> tuple[str, str, bool]:
    """Return (full_body, preview, truncated) for a markdown document.

    The preview is bounded for the inspector panel; the full body has the same
    title-stripping but no length cap so the modal can show the whole document.
    """
    if not content.strip():
        return "", "", False

    body_lines: list[str] = []
    skipped_title = False

    for raw_line in content.splitlines():
        line = _strip_empty_html_anchors(raw_line).rstrip()
        if not skipped_title and line.strip().startswith("# "):
            skipped_title = True
            continue
        if not body_lines and not line.strip():
            continue
        body_lines.append(line)

    full_body = "\n".join(body_lines).strip()
    if not full_body:
        return "", "", False

    max_lines = 48
    max_chars = 2800
    truncated = len(body_lines) > max_lines or len(full_body) > max_chars
    preview = "\n".join(body_lines[:max_lines]).strip()

    if len(preview) > max_chars:
        preview = preview[:max_chars].rstrip()
        if "\n" in preview:
            preview = preview.rsplit("\n", 1)[0].rstrip()

    if truncated:
        preview = preview.rstrip() + "\n\n..."

    return full_body, preview, truncated


def build_graph(brain_path: Path) -> dict:
    """Build a graph of nodes and edges from a brain directory."""
    nodes = []
    edges = []
    node_ids: dict[str, int] = {}

    files = _all_md_files(brain_path)

    # Create nodes
    for i, f in enumerate(files):
        rel = f.relative_to(brain_path).as_posix()
        node_ids[rel] = i

        # Determine lobe and sublobe
        parts = f.relative_to(brain_path).parts
        lobe = parts[0] if len(parts) > 1 else "root"
        sublobe = "/".join(parts[:-1]) if len(parts) > 2 else lobe

        # Determine type
        if f.name == "brain.md":
            ntype = "brain"
        elif f.name == "index.md":
            ntype = "index"
        elif f.name == "glossary.md":
            ntype = "glossary"
        elif f.name == "map.md":
            ntype = "map"
        else:
            ntype = "neuron"

        meta = {}
        content = ""
        try:
            meta, content = read_frontmatter(f)
        except Exception:
            pass

        # File flavor: yaml neurons get file_type "yaml", everything else
        # (including auto-generated brain.md / map.md / glossary.md / index.md)
        # is "markdown".
        is_yaml = f.suffix.lower() in YAML_NEURON_SUFFIXES
        file_type = "yaml" if is_yaml else "markdown"

        title, authored_title, excerpt = _extract_title_and_excerpt(f, content)
        # Non-neuron nodes (map, brain, glossary, index) use the H1 as their
        # title because their filenames are always the same across every lobe
        # — `map.md`, `brain.md`, `glossary.md` — so the stem collapses every
        # lobe's map node to "Map" in sidebars. The H1 carries the real name
        # (the lobe name) for these nodes.
        if ntype != "neuron" and authored_title:
            title = authored_title
            authored_title = ""
        # Yaml neurons: prefer frontmatter `title` as the display title.
        # Stems like `openapi.yml` title-case poorly ("Openapi"), and the
        # frontmatter title is the author's canonical name for the spec.
        if is_yaml:
            fm_title = meta.get("title")
            if isinstance(fm_title, str) and fm_title.strip():
                title = fm_title.strip()
                authored_title = ""

        content_full, content_preview, preview_truncated = _build_content_preview(content)
        tags = meta.get("tags", [])
        related = meta.get("related", [])

        # authored_title is surfaced in the modal header only when it genuinely
        # differs from the filename-derived display title — so compact labels
        # stay uniform while the author's H1 still shows up for context when
        # it adds something.
        authored_subtitle = authored_title if authored_title and authored_title != title else ""

        nodes.append({
            "id": i,
            "label": title,
            "path": rel,
            "lobe": lobe,
            "sublobe": sublobe,
            "type": ntype,
            "file_type": file_type,
            "file_name": f.name,
            "title": title,
            "authored_title": authored_subtitle,
            "excerpt": excerpt,
            "content_preview": content_preview,
            "content_preview_truncated": preview_truncated,
            "content_full": content_full,
            "tags": tags if isinstance(tags, list) else [],
            "created": str(meta.get("created", "")),
            "updated": str(meta.get("updated", "")),
            "parent": str(meta.get("parent", "")),
            "related": related if isinstance(related, list) else [],
            "status": str(meta.get("status", "")),
            "replaced_by": str(meta.get("replaced_by", "")),
        })

    # Create edges from frontmatter and inline links
    for f in files:
        rel = f.relative_to(brain_path).as_posix()
        source_id = node_ids.get(rel)
        if source_id is None:
            continue

        try:
            meta, content = read_frontmatter(f)
        except Exception:
            continue

        # Parent edge
        parent = meta.get("parent")
        if parent:
            try:
                parent_resolved = (f.parent / parent).resolve().relative_to(brain_path.resolve()).as_posix()
            except (ValueError, OSError):
                parent_resolved = ""
            if parent_resolved in node_ids:
                edges.append({
                    "source": source_id,
                    "target": node_ids[parent_resolved],
                    "type": "parent",
                })

        # Related edges
        related = meta.get("related", [])
        if isinstance(related, list):
            for r in related:
                try:
                    r_resolved = (f.parent / r).resolve().relative_to(brain_path.resolve()).as_posix()
                except (ValueError, OSError):
                    continue
                if r_resolved in node_ids:
                    edges.append({
                        "source": source_id,
                        "target": node_ids[r_resolved],
                        "type": "related",
                    })

        # replaced_by edge — deprecation pointer (treated like a special
        # synapse so the graph data layer keeps it alongside parent/related).
        replaced_by = meta.get("replaced_by")
        if replaced_by:
            try:
                rb_resolved = (f.parent / replaced_by).resolve().relative_to(brain_path.resolve()).as_posix()
            except (ValueError, OSError):
                rb_resolved = ""
            if rb_resolved in node_ids:
                edges.append({
                    "source": source_id,
                    "target": node_ids[rb_resolved],
                    "type": "replaced_by",
                })

        # Inline link edges
        for match in LINK_PATTERN.finditer(content):
            target = match.group(2)
            if target.startswith("http"):
                continue
            # Strip #anchor / ?query so `glossary.md#jwt` still resolves to glossary.md.
            target_path = target.split("#", 1)[0].split("?", 1)[0]
            if not target_path:
                continue
            try:
                t_resolved = (f.parent / target_path).resolve().relative_to(brain_path.resolve()).as_posix()
                if t_resolved in node_ids and t_resolved != rel:
                    # Avoid duplicating parent/related edges
                    existing = {(e["source"], e["target"]) for e in edges}
                    if (source_id, node_ids[t_resolved]) not in existing:
                        edges.append({
                            "source": source_id,
                            "target": node_ids[t_resolved],
                            "type": "inline",
                        })
            except (ValueError, OSError):
                continue

    neighbors: dict[int, set[int]] = {node["id"]: set() for node in nodes}
    edge_counts = {"parent": 0, "related": 0, "inline": 0, "replaced_by": 0}
    for edge in edges:
        neighbors[edge["source"]].add(edge["target"])
        neighbors[edge["target"]].add(edge["source"])
        edge_counts[edge["type"]] = edge_counts.get(edge["type"], 0) + 1

    for node in nodes:
        node["degree"] = len(neighbors[node["id"]])

    return {"nodes": nodes, "edges": edges, "meta": {"edge_counts": edge_counts}}


def generate_mri_html(brain_path: Path, output_path: Path) -> dict:
    """Generate a standalone HTML visualization of the brain graph.

    The MRI opens with a brain-architecture view (Level 1: lobes + cross-lobe
    synapses). Click a lobe to drill into sublobes (Level 2), click a sublobe
    to see neurons (Level 3). Toggle Expert mode for the legacy force graph.
    """
    graph = build_graph(brain_path)
    brain_name = brain_path.name
    graph_json = json.dumps(graph, indent=2)

    html = _render_mri_html(brain_name, graph, graph_json)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")

    return {"nodes": len(graph["nodes"]), "edges": len(graph["edges"])}


def _render_mri_html(brain_name: str, graph: dict, graph_json: str) -> str:
    """Build the standalone MRI HTML string.

    Pulled out of :func:`generate_mri_html` so the f-string does not have to
    interleave with the orchestration code; the function body is one big
    template literal with `{...}` Python interpolations only at the brain
    name and the JSON-encoded graph data.
    """
    neuron_count = sum(1 for n in graph["nodes"] if n["type"] == "neuron")
    edge_count = len(graph["edges"])
    # Lobe count: distinct lobe keys excluding the synthetic "root" bucket.
    lobe_count = len({n["lobe"] for n in graph["nodes"] if n["lobe"] and n["lobe"] != "root"})

    return f"""\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{brain_name} Brain MRI</title>
<style>
{_MRI_CSS}
</style>
</head>
<body>
<div class="app">
  <header class="mri-header">
    <div class="header-left">
      <h1 class="brain-title">{brain_name}</h1>
      <div class="stats">
        <span><span class="num" id="stat-lobes">{lobe_count}</span> lobes</span>
        <span class="dot">·</span>
        <span><span class="num" id="stat-neurons">{neuron_count}</span> neurons</span>
        <span class="dot">·</span>
        <span><span class="num" id="stat-synapses">{edge_count}</span> synapses</span>
      </div>
    </div>

    <nav class="breadcrumb" id="breadcrumb" aria-label="Brain navigation">
      <span class="crumb active" data-level="brain">{brain_name}</span>
    </nav>

    <div class="header-right">
      <div class="mode-switch" aria-label="Stage mode">
        <button class="mode-button active" type="button" data-stage-mode="brain">Brain</button>
        <button class="mode-button" type="button" data-stage-mode="lobe" disabled>Lobe</button>
        <button class="mode-button" type="button" data-stage-mode="sublobe" disabled>Sublobe</button>
        <button class="mode-button" type="button" data-stage-mode="force">Expert</button>
      </div>
      <button class="icon-button" id="btn-fit" type="button" title="Fit to view" aria-label="Fit to view">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M3 7V3h4M21 7V3h-4M3 17v4h4M21 17v4h-4"/></svg>
      </button>
      <button class="icon-button" id="btn-reset" type="button" title="Reset view" aria-label="Reset view">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12a9 9 0 1 0 3-6.7"/><path d="M3 4v5h5"/></svg>
      </button>
    </div>
  </header>

  <div class="body">
    <aside class="panel panel-left" id="panel-left">
      <div class="panel-header">
        <h3>Files</h3>
        <button type="button" class="panel-collapse-btn" id="collapse-left" title="Collapse left panel" aria-label="Collapse left panel">&lsaquo;</button>
      </div>
      <div class="panel-body">
        <nav class="panel-tree" id="panel-tree" aria-label="Brain files"></nav>
      </div>
    </aside>

    <main class="stage" id="stage">
      <div class="stage-hud">
        <div class="hud-pill" id="hud-action">Click a lobe to drill in · scroll to zoom · drag to pan</div>
        <div class="hud-pill" id="hud-keys">Press <kbd>/</kbd> to search · <kbd>E</kbd> for Expert</div>
      </div>
      <canvas id="mri-canvas"></canvas>
    </main>

    <aside class="panel panel-right" id="panel-right">
      <div class="panel-header">
        <h3>Find</h3>
        <button type="button" class="panel-collapse-btn" id="collapse-right" title="Collapse right panel" aria-label="Collapse right panel">&rsaquo;</button>
      </div>
      <label class="search">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3"/></svg>
        <input id="search-input" type="search" placeholder="Search neurons, path, lobe, tag, or yaml" autocomplete="off">
        <kbd>/</kbd>
      </label>

      <div class="panel-section-header">
        <h3>Lobes</h3>
      </div>
      <div class="lobe-filter" id="lobes-list"></div>

      <div class="panel-section-header" style="padding-top:18px">
        <h3>Recent</h3>
      </div>
      <div class="recent-list" id="recent-list"></div>

      <div class="panel-section-header" style="padding-top:18px">
        <h3>Results</h3>
      </div>
      <div id="result-count" class="result-count"></div>
      <div class="results" id="search-results"></div>
    </aside>
  </div>

  <button type="button" class="panel-expand-btn panel-expand-left" id="expand-left" title="Show left panel" aria-label="Show left panel">&rsaquo;</button>
  <button type="button" class="panel-expand-btn panel-expand-right" id="expand-right" title="Show right panel" aria-label="Show right panel">&lsaquo;</button>
</div>

<div id="content-modal" class="modal-overlay" style="display:none">
  <div class="modal-box">
    <div class="modal-header">
      <div class="modal-header-title">
        <button type="button" class="modal-icon-btn" id="modal-back" title="Back">&larr;</button>
        <button type="button" class="modal-icon-btn" id="modal-forward" title="Forward">&rarr;</button>
        <span class="kicker" id="modal-kicker">NEURON</span>
        <div class="modal-title" id="modal-title"></div>
      </div>
      <button type="button" class="modal-close" id="modal-close">&times;</button>
    </div>
    <nav class="modal-tree" id="modal-tree" aria-label="Brain files"></nav>
    <div class="modal-main">
      <div class="modal-stats" id="modal-stats"></div>
      <div class="modal-nav" id="modal-nav"></div>
      <div class="modal-content" id="modal-content"></div>
    </div>
  </div>
</div>

<script>
const graph = {graph_json};
const BRAIN_NAME = {json.dumps(brain_name)};
{_MRI_JS}
</script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Inline CSS — flat, calm, C4-aligned. No glassmorphic blur, no big radial
# gradients. The mockup files in `.specs/mri-c4-redesign/` are the visual
# contract; this stylesheet ports them onto the live MRI shell.
# ---------------------------------------------------------------------------

_MRI_CSS = """\
:root {
  --bg: #0a0f1a;
  --bg-deeper: #060a14;
  --panel: rgba(10, 16, 30, 0.92);
  --panel-strong: rgba(12, 21, 44, 0.96);
  --line: rgba(123, 167, 255, 0.18);
  --line-strong: rgba(123, 167, 255, 0.32);
  --text: #e9f1ff;
  --muted: #8ba7d1;
  --muted-faint: rgba(139, 167, 209, 0.55);
  --accent: #7bf7ff;
  --shadow: 0 30px 80px rgba(0, 0, 0, 0.45);
  --radius: 16px;
  --mono: "SFMono-Regular", "SF Mono", "Monaco", "Cascadia Code", monospace;
  --sans: "Avenir Next", "Segoe UI", system-ui, sans-serif;
}

* { box-sizing: border-box; }

html, body {
  margin: 0;
  padding: 0;
  background: var(--bg-deeper);
  color: var(--text);
  font-family: var(--sans);
  font-size: 13px;
  line-height: 1.5;
  height: 100vh;
  overflow: hidden;
}

.app {
  display: grid;
  grid-template-rows: auto 1fr;
  height: 100vh;
}

/* ===== Header bar ===== */
.mri-header {
  display: grid;
  grid-template-columns: minmax(280px, auto) 1fr minmax(280px, auto);
  gap: 24px;
  align-items: center;
  padding: 14px 22px;
  background: var(--bg);
  border-bottom: 1px solid var(--line);
}
.header-left {
  display: flex;
  align-items: baseline;
  gap: 14px;
  flex-wrap: wrap;
  min-width: 0;
}
.brain-title {
  margin: 0;
  font-size: 1.05rem;
  font-weight: 700;
  letter-spacing: -0.005em;
}
.stats {
  display: flex;
  align-items: baseline;
  gap: 10px;
  color: var(--muted);
  font-family: var(--mono);
  font-size: 0.7rem;
  letter-spacing: 0.04em;
}
.stats .num { color: var(--text); font-weight: 600; }
.stats .dot { color: var(--line-strong); }

.breadcrumb {
  justify-self: center;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 14px;
  background: rgba(8, 15, 32, 0.60);
  border: 1px solid var(--line);
  border-radius: 999px;
  color: var(--muted);
  font-family: var(--mono);
  font-size: 0.72rem;
  letter-spacing: 0.04em;
  flex-wrap: wrap;
}
.breadcrumb .crumb {
  cursor: pointer;
  transition: color 160ms ease;
  background: none;
  border: 0;
  padding: 0;
  font: inherit;
  color: inherit;
}
.breadcrumb .crumb:hover { color: var(--text); }
.breadcrumb .crumb.active { color: var(--text); font-weight: 600; cursor: default; }
.breadcrumb .sep { color: var(--line-strong); }

.header-right {
  display: flex;
  align-items: center;
  gap: 10px;
  justify-self: end;
  flex-wrap: wrap;
}

.mode-switch {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  padding: 3px;
  border-radius: 999px;
  background: rgba(8, 15, 32, 0.72);
  border: 1px solid rgba(255, 255, 255, 0.07);
}
.mode-button {
  appearance: none;
  min-width: 64px;
  height: 26px;
  padding: 0 12px;
  border: 0;
  border-radius: 999px;
  background: transparent;
  color: var(--muted);
  font: inherit;
  font-size: 0.7rem;
  font-weight: 600;
  letter-spacing: 0.04em;
  cursor: pointer;
  transition: background 160ms ease, color 160ms ease;
}
.mode-button:hover:not([disabled]) { color: var(--text); }
.mode-button.active {
  color: #06111f;
  background: var(--accent);
}
.mode-button[disabled] { opacity: 0.30; cursor: not-allowed; }

.icon-button {
  appearance: none;
  width: 30px;
  height: 30px;
  padding: 0;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: rgba(8, 15, 32, 0.45);
  color: var(--muted);
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  transition: color 160ms ease, border-color 160ms ease;
}
.icon-button:hover { color: var(--text); border-color: var(--line-strong); }

/* ===== Body shell ===== */
.body {
  display: grid;
  grid-template-columns: 280px 1fr 320px;
  gap: 0;
  min-height: 0;
  position: relative;
}
.body.left-collapsed { grid-template-columns: 0 1fr 320px; }
.body.right-collapsed { grid-template-columns: 280px 1fr 0; }
.body.left-collapsed.right-collapsed { grid-template-columns: 0 1fr 0; }
.body.left-collapsed .panel-left,
.body.right-collapsed .panel-right { display: none; }

.panel {
  background: var(--bg);
  border-right: 1px solid var(--line);
  display: flex;
  flex-direction: column;
  min-width: 0;
  overflow: hidden;
}
.panel.panel-right {
  border-right: 0;
  border-left: 1px solid var(--line);
}
.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 18px 10px;
}
.panel-header h3 {
  margin: 0;
  font-size: 0.7rem;
  font-weight: 700;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: var(--muted);
}
.panel-section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 18px 6px;
}
.panel-section-header h3 {
  margin: 0;
  font-size: 0.7rem;
  font-weight: 700;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: var(--muted);
}
.panel-collapse-btn {
  appearance: none;
  width: 24px;
  height: 24px;
  padding: 0;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: var(--muted);
  font: inherit;
  font-size: 1rem;
  line-height: 1;
  cursor: pointer;
}
.panel-collapse-btn:hover { color: var(--text); background: rgba(123, 167, 255, 0.08); }

.panel-expand-btn {
  appearance: none;
  position: absolute;
  top: 50%;
  transform: translateY(-50%);
  width: 22px;
  height: 56px;
  border: 1px solid var(--line);
  background: rgba(12, 21, 44, 0.88);
  color: var(--muted);
  cursor: pointer;
  font-size: 0.9rem;
  line-height: 1;
  display: none;
  align-items: center;
  justify-content: center;
  z-index: 25;
  backdrop-filter: blur(8px);
}
.panel-expand-btn:hover { color: var(--text); border-color: var(--line-strong); }
.panel-expand-btn.panel-expand-left {
  left: 0;
  border-radius: 0 8px 8px 0;
  border-left: none;
}
.panel-expand-btn.panel-expand-right {
  right: 0;
  border-radius: 8px 0 0 8px;
  border-right: none;
}
.panel-expand-btn.visible { display: flex; }

.panel-body {
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
  padding: 4px 14px 18px;
}

/* ===== Left panel — file tree ===== */
.panel-tree {
  display: block;
  font-family: var(--sans);
  font-size: 0.78rem;
}
.tree-node {
  padding: 4px 8px 4px 8px;
  border-radius: 6px;
  cursor: pointer;
  color: var(--text);
  font-size: 0.78rem;
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 1px 0;
  min-width: 0;
}
.tree-node:hover { background: rgba(123, 167, 255, 0.06); }
.tree-node.selected { background: rgba(123, 247, 255, 0.10); }
.tree-node .chev { color: var(--muted); width: 10px; flex-shrink: 0; font-family: var(--mono); font-size: 0.7rem; }
.tree-node .icon { width: 14px; flex-shrink: 0; opacity: 0.65; }
.tree-node .label {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.tree-node .count {
  color: var(--muted-faint);
  font-family: var(--mono);
  font-size: 0.66rem;
  flex-shrink: 0;
}
.tree-children { padding-left: 14px; }

/* ===== Stage / canvas ===== */
.stage {
  position: relative;
  background: var(--bg);
  background-image: radial-gradient(rgba(123, 167, 255, 0.08) 1px, transparent 1px);
  background-size: 28px 28px;
  background-position: 0 0;
  overflow: hidden;
  min-width: 0;
}
canvas {
  display: block;
  width: 100%;
  height: 100%;
  cursor: grab;
}
canvas.dragging { cursor: grabbing; }
.stage-hud {
  position: absolute;
  top: 14px;
  left: 14px;
  right: 14px;
  z-index: 5;
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  pointer-events: none;
}
.hud-pill {
  pointer-events: auto;
  padding: 8px 12px;
  background: rgba(8, 15, 32, 0.78);
  border: 1px solid var(--line);
  border-radius: 999px;
  color: var(--muted);
  font-size: 0.72rem;
  backdrop-filter: blur(8px);
}
.hud-pill kbd {
  display: inline-block;
  padding: 1px 6px;
  margin: 0 2px;
  border-radius: 4px;
  background: rgba(123, 167, 255, 0.12);
  border: 1px solid var(--line);
  color: var(--text);
  font-family: var(--mono);
  font-size: 0.66rem;
  font-weight: 600;
}

/* ===== Right panel ===== */
.search {
  margin: 0 18px 12px;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 9px 12px;
  background: rgba(8, 15, 32, 0.60);
  border: 1px solid var(--line);
  border-radius: 10px;
  color: var(--text);
}
.search svg { flex-shrink: 0; opacity: 0.55; }
#search-input {
  flex: 1;
  min-width: 0;
  background: transparent;
  border: 0;
  outline: 0;
  color: inherit;
  font: inherit;
  font-family: var(--mono);
  font-size: 0.78rem;
}
#search-input::placeholder { color: var(--muted-faint); }
.search kbd {
  padding: 1px 6px;
  border-radius: 4px;
  background: rgba(123, 167, 255, 0.10);
  border: 1px solid var(--line);
  color: var(--muted);
  font-family: var(--mono);
  font-size: 0.66rem;
}

.lobe-filter {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 0 14px 8px;
}
.lobe-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 10px;
  border-radius: 10px;
  border: 1px solid transparent;
  cursor: pointer;
  background: transparent;
  color: var(--text);
  font: inherit;
  font-size: 0.78rem;
  text-align: left;
  width: 100%;
  transition: background 160ms ease, border-color 160ms ease;
}
.lobe-row:hover {
  background: rgba(123, 167, 255, 0.05);
  border-color: var(--line);
}
.lobe-row.dimmed { opacity: 0.45; }
.lobe-row .swatch {
  width: 4px;
  height: 22px;
  border-radius: 2px;
  flex-shrink: 0;
  background: var(--bar, var(--accent));
}
.lobe-row .label {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
}
.lobe-row .count {
  color: var(--muted-faint);
  font-family: var(--mono);
  font-size: 0.7rem;
  flex-shrink: 0;
}
.lobe-row .vis {
  color: var(--muted);
  font-size: 0.78rem;
  width: 14px;
  text-align: center;
}

.recent-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 0 14px 8px;
}
.recent-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 5px 8px;
  border-radius: 6px;
  cursor: pointer;
  background: transparent;
  color: var(--text);
  font: inherit;
  font-size: 0.78rem;
  text-align: left;
  width: 100%;
  border: 0;
}
.recent-row:hover { background: rgba(123, 167, 255, 0.06); }
.recent-row .label {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
}
.recent-row .ago {
  color: var(--muted-faint);
  font-family: var(--mono);
  font-size: 0.66rem;
  flex-shrink: 0;
}

.result-count {
  padding: 0 18px 6px;
  color: var(--muted);
  font-size: 0.74rem;
  font-family: var(--mono);
}
.results {
  padding: 0 14px 16px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.result-card {
  appearance: none;
  width: 100%;
  text-align: left;
  border: 1px solid var(--line);
  background: rgba(8, 15, 32, 0.45);
  color: var(--text);
  border-radius: 10px;
  padding: 8px 10px;
  cursor: pointer;
  font: inherit;
  transition: background 160ms ease, border-color 160ms ease;
}
.result-card:hover {
  border-color: var(--line-strong);
  background: rgba(123, 247, 255, 0.06);
}
.result-card .result-title {
  font-weight: 600;
  font-size: 0.84rem;
}
.result-card .result-meta {
  margin-top: 2px;
  color: var(--muted);
  font-size: 0.7rem;
  font-family: var(--mono);
}
.result-card .result-path {
  margin-top: 4px;
  color: var(--muted-faint);
  font-family: var(--mono);
  font-size: 0.66rem;
  word-break: break-all;
}

/* ===== Modal — flat C4 box style ===== */
.modal-overlay {
  position: fixed;
  inset: 0;
  z-index: 100;
  background: rgba(0, 0, 0, 0.7);
  display: flex;
  align-items: center;
  justify-content: center;
}
.modal-box {
  width: 92vw;
  max-height: 92vh;
  background: var(--panel-strong);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  display: grid;
  grid-template-columns: 260px minmax(0, 1fr);
  grid-template-rows: auto 1fr;
  overflow: hidden;
}
.modal-header {
  grid-column: 1 / -1;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 18px;
  border-bottom: 1px solid var(--line);
  background: var(--bg);
}
.modal-header-title {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}
.modal-icon-btn {
  appearance: none;
  width: 26px;
  height: 26px;
  border: 1px solid var(--line);
  border-radius: 6px;
  background: transparent;
  color: var(--muted);
  cursor: pointer;
}
.modal-icon-btn:hover { color: var(--text); border-color: var(--line-strong); }
.modal-header .kicker {
  font-family: var(--mono);
  font-size: 0.62rem;
  letter-spacing: 0.18em;
  color: var(--muted);
  text-transform: uppercase;
  border: 1px solid var(--line);
  border-radius: 4px;
  padding: 2px 8px;
}
.modal-title {
  font-size: 0.95rem;
  font-weight: 700;
  color: var(--text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
}
.modal-close {
  appearance: none;
  background: none;
  border: none;
  color: var(--muted);
  font-size: 1.4rem;
  cursor: pointer;
  padding: 0 4px;
  line-height: 1;
}
.modal-close:hover { color: var(--text); }
.modal-tree {
  grid-row: 2;
  grid-column: 1;
  overflow: auto;
  border-right: 1px solid var(--line);
  padding: 12px 10px;
  background: var(--bg);
  font-family: var(--mono);
  font-size: 0.78rem;
}
.modal-main {
  grid-row: 2;
  grid-column: 2;
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
}
.modal-stats {
  padding: 10px 22px 4px;
  color: var(--muted-faint);
  font-family: var(--mono);
  font-size: 0.74rem;
  letter-spacing: 0.04em;
}
.modal-stats .num { color: var(--text); font-weight: 600; }
.modal-stats .dot { color: var(--line-strong); margin: 0 6px; }
.modal-nav {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding: 8px 22px;
  border-bottom: 1px solid var(--line);
}
.modal-nav:empty { display: none; }
.modal-nav-toggle {
  appearance: none;
  background: transparent;
  border: 1px dashed var(--line);
  color: var(--accent);
  border-radius: 999px;
  padding: 4px 10px;
  font-size: 0.74rem;
  font-family: var(--mono);
  font-weight: 600;
  cursor: pointer;
}
.modal-nav-toggle:hover { background: rgba(123, 247, 255, 0.06); border-color: var(--line-strong); }
.modal-nav-btn {
  appearance: none;
  background: rgba(8, 15, 32, 0.60);
  border: 1px solid var(--line);
  color: var(--accent);
  border-radius: 999px;
  padding: 4px 10px;
  font-size: 0.74rem;
  font-family: var(--mono);
  cursor: pointer;
}
.modal-nav-btn:hover { background: rgba(123, 247, 255, 0.08); border-color: var(--line-strong); }
.modal-content {
  flex: 1;
  overflow: auto;
  margin: 0;
  padding: 16px 22px 24px;
  color: #eef4ff;
  font-family: var(--sans);
  font-size: 0.88rem;
  line-height: 1.65;
}
.modal-content h1 { font-size: 1.3rem; margin: 14px 0 8px; }
.modal-content h2 {
  font-size: 1.05rem;
  margin: 18px 0 8px;
  padding-bottom: 4px;
  border-bottom: 1px solid var(--line);
}
.modal-content h3 { font-size: 0.95rem; margin: 14px 0 6px; }
.modal-content p { margin: 8px 0; }
.modal-content ul,
.modal-content ol { padding-left: 22px; margin: 8px 0; }
.modal-content li { margin: 3px 0; }
.modal-content hr { border: 0; border-top: 1px solid var(--line); margin: 16px 0; }
.modal-content code {
  background: rgba(123, 167, 255, 0.10);
  padding: 1px 6px;
  border-radius: 4px;
  font-family: var(--mono);
  font-size: 0.82rem;
}
.modal-content pre {
  background: var(--bg);
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 10px 12px;
  overflow-x: auto;
  font-size: 0.78rem;
  margin: 10px 0;
}
.modal-content pre code { background: transparent; padding: 0; font-size: 0.78rem; }
.modal-content blockquote {
  margin: 10px 0;
  padding: 4px 14px;
  border-left: 3px solid var(--line);
  background: rgba(123, 167, 255, 0.04);
  border-radius: 0 8px 8px 0;
  color: var(--muted);
}
.modal-content blockquote p { margin: 6px 0; }
.modal-content table {
  border-collapse: collapse;
  margin: 12px 0;
  font-size: 0.82rem;
  display: block;
  overflow-x: auto;
  max-width: 100%;
}
.modal-content th,
.modal-content td {
  border: 1px solid var(--line);
  padding: 6px 10px;
  text-align: left;
  vertical-align: top;
}
.modal-content thead th { background: rgba(123, 167, 255, 0.08); font-weight: 600; }
.modal-content tbody tr:nth-child(even) td { background: rgba(123, 167, 255, 0.03); }
.modal-content a { color: var(--accent); }
.modal-tree-folder { margin: 2px 0; }
.modal-tree-folder-label {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 3px 6px;
  color: var(--muted);
  cursor: pointer;
  border-radius: 4px;
}
.modal-tree-folder-label:hover { background: rgba(123, 167, 255, 0.06); color: var(--text); }
.modal-tree-folder-label .caret {
  display: inline-block;
  width: 10px;
  text-align: center;
}
.modal-tree-folder.collapsed > .modal-tree-children { display: none; }
.modal-tree-folder.collapsed > .modal-tree-folder-label .caret { transform: rotate(-90deg); }
.modal-tree-children { margin-left: 12px; border-left: 1px solid var(--line); padding-left: 6px; }
.modal-tree-file {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 3px 6px;
  cursor: pointer;
  border-radius: 4px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.modal-tree-file:hover { background: rgba(123, 247, 255, 0.06); color: var(--accent); }
.modal-tree-file.active { background: rgba(123, 247, 255, 0.12); color: var(--accent); }
.yaml-preview {
  background: var(--bg);
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 12px 14px;
  overflow-x: auto;
  font-size: 0.78rem;
  line-height: 1.55;
  margin: 0;
}
.yaml-preview code {
  background: transparent;
  padding: 0;
  font-family: var(--mono);
  font-size: 0.78rem;
  white-space: pre;
}
.yaml-key { color: var(--accent); }
.yaml-string { color: #7df7b4; }
.yaml-num { color: #f8c76d; }
.yaml-bool { color: #ff8bd8; }
.yaml-comment { color: var(--muted); font-style: italic; }
.content-link {
  appearance: none;
  background: none;
  border: none;
  color: var(--accent);
  font: inherit;
  cursor: pointer;
  padding: 0;
  text-decoration: underline;
  text-decoration-color: rgba(123, 247, 255, 0.3);
  text-underline-offset: 2px;
}
.content-link:hover { text-decoration-color: var(--accent); }
.content-link-broken {
  color: #ff8a8a;
  text-decoration: line-through;
  text-decoration-color: rgba(255, 138, 138, 0.55);
  cursor: help;
}

/* Responsive: collapse the right panel on narrow screens */
@media (max-width: 1100px) {
  .body { grid-template-columns: 240px 1fr 0; }
  .body .panel-right { display: none; }
}
@media (max-width: 720px) {
  .body { grid-template-columns: 0 1fr 0; }
  .body .panel-left { display: none; }
}
"""


# ---------------------------------------------------------------------------
# Inline JS — canvas C4 levels, edge aggregation, breadcrumb navigation,
# legacy force graph (Expert mode), modal renderer.
#
# Caveat: this whole string is consumed as the body of an f-string in
# `_render_mri_html`. Inside this constant we are NOT in an f-string, so
# `{` / `}` and `\n` / `\\n` follow normal Python rules — `\\n` is a real
# backslash-n in the emitted JS, and a single `\n` becomes a real newline
# in Python. JS string literals that need an actual `\n` use `\\n`.
# ---------------------------------------------------------------------------

_MRI_JS = r"""
// ============================================================
// Constants & module state
// ============================================================
const FORCE_PAIRWISE_LIMIT = 180;
const DETAIL_EDGE_LIMIT = 700;

// Lobe palette — first 3 anchored to mockup colors so the demo brain
// (projects/infrastructure/knowledge) renders identically to the static HTML.
const lobePalette = ['#7bf7ff', '#ff8bd8', '#f8c76d', '#7df7b4', '#9ea9ff', '#ffa06f', '#b8f0c1', '#f2a8ff'];
const uniqueLobes = [...new Set(graph.nodes.map(n => n.lobe))]
  .filter(l => l && l !== 'root')
  .sort((a, b) => a.localeCompare(b));

function lobeColor(lobe) {
  const idx = uniqueLobes.indexOf(lobe);
  return lobePalette[(idx >= 0 ? idx : 0) % lobePalette.length];
}

const canvas = document.getElementById('mri-canvas');
const ctx = canvas.getContext('2d');
const searchInput = document.getElementById('search-input');
const resultsEl = document.getElementById('search-results');
const resultCountEl = document.getElementById('result-count');
const lobesListEl = document.getElementById('lobes-list');
const recentListEl = document.getElementById('recent-list');
const breadcrumbEl = document.getElementById('breadcrumb');
const stage = document.getElementById('stage');
const modeButtons = [...document.querySelectorAll('[data-stage-mode]')];

const neighbors = new Map();
for (const node of graph.nodes) neighbors.set(node.id, new Set());
for (const edge of graph.edges) {
  neighbors.get(edge.source)?.add(edge.target);
  neighbors.get(edge.target)?.add(edge.source);
}

let W = 0;
let H = 0;
const camera = { x: 0, y: 0, scale: 1 };

// Stage modes: 'brain' | 'lobe' | 'sublobe' | 'force'.
//   - 'brain'   = Level 1 (lobes + cross-lobe synapse edges, no physics)
//   - 'lobe'    = Level 2 (sublobes inside one lobe + outbound stubs)
//   - 'sublobe' = Level 3 (neurons inside one sublobe, layered DAG)
//   - 'force'   = legacy force-directed graph (Expert mode) with perf caps
let stageMode = 'brain';
let activeLobe = null;        // selected lobe key when in 'lobe' or 'sublobe' mode
let activeSublobe = null;     // selected sublobe key when in 'sublobe' mode
let needsDraw = true;
let pointer = { x: 0, y: 0 };
let selectedId = null;
let hoveredId = null;
let draggingNodeId = null;
let isPanning = false;
let dragMoved = false;
let dragOffset = { x: 0, y: 0 };
let lastPointer = { x: 0, y: 0 };

// L1/L2/L3 layout state — populated by layoutBrainMap / layoutLobeMap /
// layoutSublobeMap on every stage transition or filter change. Boxes are
// {key, title, kicker, lobe, color, x, y, w, h, ...}; aggregateEdges
// produces the edges between L1/L2 boxes.
let brainBoxes = [];
let lobeBoxes = [];
let sublobeBoxes = [];
let brainEdges = [];   // aggregate edges at L1 (cross-lobe)
let lobeEdges = [];    // aggregate edges at L2 (cross-sublobe within active lobe)
let lobeOutbound = []; // outbound stubs at the L2 lobe boundary
let sublobeOutbound = []; // outbound stubs at the L3 sublobe boundary
let sublobeNeuronEdges = []; // {source, target, type, sx, sy, tx, ty, points}
let highlightedEdge = null;  // {a, b} keys of the lobe pair to flash
let highlightedEdgeUntil = 0;

// Multi-select visibility toggles for lobes (right-sidebar filter).
const hiddenLobes = new Set();

function requestDraw() { needsDraw = true; }

// ============================================================
// Aggregate edges helper — used by L1 (level='brain') and L2 (level='lobe')
// ============================================================
//
// Returns a Map<"a||b", {a, b, forward, reverse}> where:
//   - keys are the two participating lobe / sublobe keys joined sorted by
//     localeCompare (so the iteration order is stable across calls);
//   - forward = edges from the first key (lexicographic) to the second;
//   - reverse = edges in the opposite direction.
//
// Self-edges (within the same lobe at L1, or same sublobe at L2) are dropped
// — they are not "cross-boundary." `parent:` edges are always excluded
// because they're structural (a neuron's parent must live in the same lobe
// in a well-formed brain), not synapses.
function aggregateEdges(g, level) {
  const result = new Map();
  const keyOf = (node) => {
    if (level === 'brain') return node.lobe;
    if (level === 'lobe') return node.sublobe;
    return null;
  };
  const nodeMap = new Map(g.nodes.map(n => [n.id, n]));
  for (const edge of g.edges) {
    if (edge.type === 'parent') continue;
    const src = nodeMap.get(edge.source);
    const tgt = nodeMap.get(edge.target);
    if (!src || !tgt) continue;
    const sk = keyOf(src);
    const tk = keyOf(tgt);
    if (!sk || !tk) continue;
    if (sk === tk) continue;
    const [a, b] = sk.localeCompare(tk) <= 0 ? [sk, tk] : [tk, sk];
    const cellKey = a + '||' + b;
    if (!result.has(cellKey)) {
      result.set(cellKey, { a, b, forward: 0, reverse: 0 });
    }
    const cell = result.get(cellKey);
    if (sk === a) cell.forward += 1;
    else cell.reverse += 1;
  }
  return result;
}

// ============================================================
// Lobe / sublobe metadata derived from the graph
// ============================================================
function lobeTitle(lobeKey) {
  const mapNode = graph.nodes.find(n => n.type === 'map' && n.lobe === lobeKey && n.sublobe === lobeKey);
  return mapNode?.title || lobeKey;
}
function sublobeTitle(sublobeKey) {
  const mapNode = graph.nodes.find(n => n.type === 'map' && n.sublobe === sublobeKey);
  return mapNode?.title || sublobeKey.split('/').pop() || sublobeKey;
}
function lobeDescription(lobeKey) {
  const mapNode = graph.nodes.find(n => n.type === 'map' && n.lobe === lobeKey && n.sublobe === lobeKey);
  if (!mapNode) return '';
  return (mapNode.excerpt || mapNode.content_preview || '').split('\n')[0].trim();
}
function sublobeDescription(sublobeKey) {
  const mapNode = graph.nodes.find(n => n.type === 'map' && n.sublobe === sublobeKey);
  if (!mapNode) return '';
  return (mapNode.excerpt || mapNode.content_preview || '').split('\n')[0].trim();
}
function lobeStats(lobeKey) {
  let neurons = 0;
  const subs = new Set();
  for (const n of graph.nodes) {
    if (n.lobe !== lobeKey) continue;
    if (n.type === 'neuron') neurons += 1;
    if (n.sublobe && n.sublobe !== n.lobe) subs.add(n.sublobe);
  }
  return { neurons, sublobes: subs.size };
}
function sublobeStats(sublobeKey) {
  let neurons = 0;
  for (const n of graph.nodes) {
    if (n.sublobe === sublobeKey && n.type === 'neuron') neurons += 1;
  }
  return { neurons };
}

// ============================================================
// Shared layout primitives (used at L1 and L2)
// ============================================================
//
// items must be [{key, ...payload}]. Returns the same array enriched with
// {x, y, w, h}. Three regimes per the spec:
//   - 1..4 items: single horizontal row, equal spacing
//   - 5..6 items: 2-row / 2-col grid (3 cols if landscape, 2 cols if portrait)
//   - 7+ items: radial orbit (alphabetical clockwise from 12 o'clock)
function layoutGrid(items, viewport, opts) {
  const n = items.length;
  if (n === 0) return [];
  const W_ = viewport.width;
  const H_ = viewport.height;
  const boxW = (opts && opts.width) || 240;
  const boxH = (opts && opts.height) || 140;
  if (n <= 4) {
    const cellW = Math.min(W_ / Math.max(1, n), 320);
    const y = H_ / 2;
    return items.map((item, i) => ({
      ...item,
      x: W_ / 2 - ((n - 1) * cellW) / 2 + i * cellW,
      y,
      w: boxW,
      h: boxH,
    }));
  }
  if (n <= 6) {
    const cols = W_ > H_ ? 3 : 2;
    const rows = Math.ceil(n / cols);
    const cellW = Math.min(W_ / cols, 320);
    const cellH = Math.min(H_ / rows, 220);
    return items.map((item, i) => {
      const col = i % cols;
      const row = Math.floor(i / cols);
      return {
        ...item,
        x: W_ / 2 - ((cols - 1) * cellW) / 2 + col * cellW,
        y: H_ / 2 - ((rows - 1) * cellH) / 2 + row * cellH,
        w: boxW,
        h: boxH,
      };
    });
  }
  const radius = Math.min(W_, H_) * 0.34;
  return items.map((item, i) => {
    const angle = -Math.PI / 2 + (i / n) * Math.PI * 2;
    return {
      ...item,
      x: W_ / 2 + Math.cos(angle) * radius,
      y: H_ / 2 + Math.sin(angle) * radius,
      w: 220,
      h: 130,
    };
  });
}

function layoutBrainMap(lobes, viewport) {
  return layoutGrid(lobes, viewport, { width: 260, height: 140 });
}
function layoutLobeMap(sublobes, viewport) {
  return layoutGrid(sublobes, viewport, { width: 240, height: 130 });
}

// Layered DAG layout for L3.
// Rank 0 = the sublobe's map.md (the index). Rank 1+ = parent: descendants.
// Within a rank, sort by tags[0] then by filename so the layout is
// deterministic across runs.
function layoutSublobeMap(lobeKey, sublobeKey, neuronsForLevel, viewport) {
  if (!neuronsForLevel.length) return [];
  const idMap = new Map(neuronsForLevel.map(n => [n.id, n]));
  // Find the index node (map.md for this sublobe), if any.
  const indexNode = neuronsForLevel.find(n => n.type === 'map');
  const ranks = new Map();
  const queue = [];
  if (indexNode) {
    ranks.set(indexNode.id, 0);
    queue.push(indexNode.id);
  }
  // BFS via parent edges among neurons in this sublobe.
  // graph.edges is the global edge list; we filter to {parent} and
  // both endpoints in this sublobe.
  const parentEdges = graph.edges.filter(e =>
    e.type === 'parent' && idMap.has(e.source) && idMap.has(e.target)
  );
  while (queue.length) {
    const pid = queue.shift();
    const r = ranks.get(pid);
    for (const e of parentEdges) {
      if (e.target === pid && !ranks.has(e.source)) {
        ranks.set(e.source, r + 1);
        queue.push(e.source);
      }
    }
  }
  // Unranked nodes get rank 1 (orphan neurons sitting under the sublobe).
  for (const n of neuronsForLevel) {
    if (!ranks.has(n.id)) ranks.set(n.id, indexNode ? 1 : 0);
  }
  // Group by rank, sort each rank.
  const byRank = new Map();
  for (const n of neuronsForLevel) {
    const r = ranks.get(n.id);
    if (!byRank.has(r)) byRank.set(r, []);
    byRank.get(r).push(n);
  }
  const tagFor = (node) => (node.tags && node.tags[0]) || '';
  for (const list of byRank.values()) {
    list.sort((a, b) => {
      const ta = tagFor(a);
      const tb = tagFor(b);
      if (ta !== tb) return ta.localeCompare(tb);
      return (a.file_name || a.path || '').localeCompare(b.file_name || b.path || '');
    });
  }
  const rankKeys = [...byRank.keys()].sort((a, b) => a - b);
  const boxW = 220;
  const boxH = 110;
  const colGap = 28;
  const rowGap = 70;
  const out = [];
  rankKeys.forEach((r, rowIdx) => {
    const list = byRank.get(r);
    const totalW = list.length * boxW + (list.length - 1) * colGap;
    const startX = viewport.width / 2 - totalW / 2 + boxW / 2;
    const y = 90 + rowIdx * (boxH + rowGap);
    list.forEach((n, colIdx) => {
      out.push({
        ...n,
        rank: r,
        x: startX + colIdx * (boxW + colGap),
        y: y + boxH / 2,
        w: boxW,
        h: boxH,
        kicker: r === 0 && n.type === 'map' ? 'INDEX' : 'NEURON',
        color: lobeColor(lobeKey),
        deprecated: n.status === 'deprecated',
      });
    });
  });
  return out;
}

// ============================================================
// C4 box renderer — shared across all three levels
// ============================================================
//
// item: {x, y, w, h, kicker, title, desc, statsLine, color, deprecated, dim}
function drawC4Box(item, opts) {
  opts = opts || {};
  const { x, y, w, h } = item;
  const left = x - w / 2;
  const top = y - h / 2;
  ctx.save();
  if (item.dim) ctx.globalAlpha = 0.30;
  // Body
  ctx.fillStyle = 'rgba(12, 21, 44, 0.96)';
  ctx.beginPath();
  ctx.roundRect(left, top, w, h, 14);
  ctx.fill();
  // Border
  ctx.lineWidth = opts.hover ? 1.6 : 1.0;
  ctx.strokeStyle = opts.hover
    ? 'rgba(123, 167, 255, 0.42)'
    : 'rgba(123, 167, 255, 0.20)';
  ctx.stroke();
  // Color bar (4px) at the left edge, inset 14px top/bottom.
  ctx.beginPath();
  if (item.deprecated) {
    // Dotted-stripe pattern for deprecated neurons
    ctx.setLineDash([3, 4]);
    ctx.strokeStyle = item.color;
    ctx.lineWidth = 4;
    ctx.moveTo(left + 2, top + 14);
    ctx.lineTo(left + 2, top + h - 14);
    ctx.stroke();
    ctx.setLineDash([]);
  } else {
    ctx.fillStyle = item.color;
    ctx.roundRect(left, top + 14, 4, h - 28, [0, 4, 4, 0]);
    ctx.fill();
  }
  // Kicker
  ctx.fillStyle = '#8ba7d1';
  ctx.font = 'bold 10px "SFMono-Regular", monospace';
  ctx.textAlign = 'left';
  ctx.fillText(String(item.kicker || '').toUpperCase(), left + 14, top + 22);
  // Title
  ctx.fillStyle = '#e9f1ff';
  ctx.font = 'bold 15px "Avenir Next", "Segoe UI", sans-serif';
  const titleStr = String(item.title || '');
  const titleMax = w - 24;
  ctx.fillText(_truncate(titleStr, titleMax, '15px "Avenir Next", "Segoe UI", sans-serif'),
    left + 14, top + 44);
  // Separator
  ctx.strokeStyle = 'rgba(123, 167, 255, 0.15)';
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(left + 14, top + 54);
  ctx.lineTo(left + w - 14, top + 54);
  ctx.stroke();
  // Description (1 line, truncated)
  if (item.desc) {
    ctx.fillStyle = '#8ba7d1';
    ctx.font = '11px "Avenir Next", "Segoe UI", sans-serif';
    ctx.fillText(_truncate(item.desc, w - 24, '11px "Avenir Next", "Segoe UI", sans-serif'),
      left + 14, top + 70);
  }
  // Stats line (mono, muted)
  if (item.statsLine) {
    ctx.fillStyle = 'rgba(139, 167, 209, 0.65)';
    ctx.font = '10px "SFMono-Regular", monospace';
    ctx.fillText(_truncate(item.statsLine, w - 24, '10px "SFMono-Regular", monospace'),
      left + 14, top + h - 14);
  }
  // Tag chips (L3 only)
  if (item.tagChips && item.tagChips.length) {
    let tx = left + 14;
    const ty = top + h - 30;
    ctx.font = 'bold 9px "SFMono-Regular", monospace';
    for (const chip of item.tagChips.slice(0, 2)) {
      const padX = 6;
      const m = ctx.measureText(chip);
      const cw = m.width + padX * 2;
      const ch = 14;
      ctx.fillStyle = 'rgba(123, 167, 255, 0.10)';
      ctx.beginPath();
      ctx.roundRect(tx, ty, cw, ch, 4);
      ctx.fill();
      ctx.strokeStyle = 'rgba(123, 167, 255, 0.18)';
      ctx.lineWidth = 1;
      ctx.stroke();
      ctx.fillStyle = '#8ba7d1';
      ctx.fillText(chip, tx + padX, ty + 10);
      tx += cw + 4;
      if (tx > left + w - 14) break;
    }
  }
  // Search dim halo (yellow)
  if (item.matchHalo) {
    ctx.strokeStyle = 'rgba(255, 220, 100, 0.78)';
    ctx.lineWidth = 2.4;
    ctx.beginPath();
    ctx.roundRect(left - 2, top - 2, w + 4, h + 4, 16);
    ctx.stroke();
  }
  ctx.restore();
}

function _truncate(s, maxPx, font) {
  ctx.save();
  ctx.font = font;
  if (ctx.measureText(s).width <= maxPx) {
    ctx.restore();
    return s;
  }
  let lo = 0, hi = s.length;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    const cand = s.slice(0, mid) + '…';
    if (ctx.measureText(cand).width <= maxPx) lo = mid + 1;
    else hi = mid;
  }
  ctx.restore();
  return s.slice(0, Math.max(0, lo - 1)) + '…';
}

// ============================================================
// Aggregate edge renderer (L1 + L2)
// ============================================================
//
// `cell` is {a, b, forward, reverse} from aggregateEdges.
// `boxByKey` is Map<key, box> that gives the participants their geometry.
function drawAggregateEdge(cell, boxByKey, opts) {
  opts = opts || {};
  const ba = boxByKey.get(cell.a);
  const bb = boxByKey.get(cell.b);
  if (!ba || !bb) return;
  const dim = opts.dim || false;
  const total = cell.forward + cell.reverse;
  const thickness = Math.max(1, Math.min(6, Math.log2(total + 1) * 1.4));
  // Orthogonal route with rounded mid-corner.
  const sx = ba.x;
  const sy = ba.y;
  const tx = bb.x;
  const ty = bb.y;
  const midY = (sy + ty) / 2;
  ctx.save();
  ctx.globalAlpha = dim ? 0.18 : 0.78;
  ctx.strokeStyle = opts.highlight ? '#ffdc64' : 'rgba(139, 167, 209, 0.78)';
  ctx.lineWidth = opts.highlight ? thickness + 1 : thickness;
  ctx.lineCap = 'round';
  ctx.lineJoin = 'round';
  ctx.beginPath();
  ctx.moveTo(sx, sy);
  ctx.lineTo(sx, midY);
  ctx.lineTo(tx, midY);
  ctx.lineTo(tx, ty);
  ctx.stroke();
  ctx.restore();
  // Edge label pill
  const symmetric = cell.forward === cell.reverse;
  const label = symmetric
    ? '↔ ' + total
    : '→ ' + cell.forward + ' / ← ' + cell.reverse;
  const pillX = (sx + tx) / 2;
  const pillY = midY;
  ctx.save();
  ctx.font = 'bold 10px "SFMono-Regular", monospace';
  const m = ctx.measureText(label);
  const padX = 8;
  const padY = 4;
  const pillW = m.width + padX * 2;
  const pillH = 18;
  const pillLeft = pillX - pillW / 2;
  const pillTop = pillY - pillH / 2;
  ctx.fillStyle = 'rgba(8, 15, 32, 0.92)';
  ctx.beginPath();
  ctx.roundRect(pillLeft, pillTop, pillW, pillH, 6);
  ctx.fill();
  ctx.strokeStyle = 'rgba(123, 167, 255, 0.30)';
  ctx.lineWidth = 1;
  ctx.stroke();
  ctx.fillStyle = '#e9f1ff';
  ctx.textAlign = 'center';
  ctx.fillText(label, pillX, pillY + 3);
  ctx.restore();
  // Stash midpoint on cell for edge hit testing.
  cell._midX = pillX;
  cell._midY = pillY;
  cell._w = pillW;
  cell._h = pillH;
}

// ============================================================
// L1 — Brain Map
// ============================================================
function buildBrainBoxes() {
  const items = uniqueLobes.map(lobeKey => {
    const stats = lobeStats(lobeKey);
    return {
      key: lobeKey,
      kicker: 'LOBE',
      title: lobeTitle(lobeKey),
      desc: lobeDescription(lobeKey),
      color: lobeColor(lobeKey),
      lobe: lobeKey,
      statsLine: stats.neurons + ' neurons · ' + stats.sublobes + ' sublobes',
    };
  });
  const rect = stage.getBoundingClientRect();
  const viewport = { width: rect.width || 900, height: rect.height || 600 };
  return layoutBrainMap(items, viewport);
}

function buildBrainEdges() {
  // aggregateEdges returns Map; spread to a stable array (its iteration
  // order is already stable because we sort uniqueLobes when we build it).
  const cells = aggregateEdges(graph, 'brain');
  return [...cells.values()];
}

function drawBrainMap() {
  brainBoxes = buildBrainBoxes();
  brainEdges = buildBrainEdges();
  const boxByKey = new Map(brainBoxes.map(b => [b.key, b]));
  const query = searchInput.value.trim().toLowerCase();
  const dimNonMatch = (key) => {
    if (!query) return false;
    const t = (lobeTitle(key) || '').toLowerCase();
    return !t.includes(query) && !key.toLowerCase().includes(query);
  };
  const flashActive = highlightedEdge && performance.now() < highlightedEdgeUntil;
  const flashKeys = flashActive
    ? new Set([highlightedEdge.a, highlightedEdge.b])
    : null;
  // Pass 1: edges (behind the boxes)
  for (const cell of brainEdges) {
    const dim = (flashActive && !flashKeys.has(cell.a) && !flashKeys.has(cell.b))
      || (query && dimNonMatch(cell.a) && dimNonMatch(cell.b));
    drawAggregateEdge(cell, boxByKey, {
      dim,
      highlight: flashActive && flashKeys.has(cell.a) && flashKeys.has(cell.b),
    });
  }
  // Pass 2: boxes
  for (const box of brainBoxes) {
    const filteredOut = hiddenLobes.has(box.key);
    const dim = filteredOut
      || (flashActive && !flashKeys.has(box.key))
      || dimNonMatch(box.key);
    drawC4Box({
      ...box,
      dim,
      matchHalo: query && !filteredOut && !dim
        && (lobeTitle(box.key) || '').toLowerCase().includes(query),
    }, { hover: hoveredId === '__lobe__' + box.key });
  }
}

function hitTestBrainMap(worldX, worldY) {
  // Boxes
  for (const box of brainBoxes) {
    if (worldX >= box.x - box.w / 2 && worldX <= box.x + box.w / 2 &&
        worldY >= box.y - box.h / 2 && worldY <= box.y + box.h / 2) {
      return { kind: 'lobe', key: box.key };
    }
  }
  // Edge label pills
  for (const cell of brainEdges) {
    if (cell._midX == null) continue;
    if (Math.abs(worldX - cell._midX) <= cell._w / 2 &&
        Math.abs(worldY - cell._midY) <= cell._h / 2) {
      return { kind: 'edge', a: cell.a, b: cell.b };
    }
  }
  return null;
}

// ============================================================
// L2 — Lobe Map
// ============================================================
function buildLobeBoxes(lobeKey) {
  // Find sublobes (depth-2 keys, e.g. "projects/foo") under this lobe.
  const subs = new Map();
  for (const n of graph.nodes) {
    if (n.lobe !== lobeKey) continue;
    if (!n.sublobe || n.sublobe === n.lobe) continue;
    const parts = n.sublobe.split('/');
    if (parts.length < 2) continue;
    const key = parts.slice(0, 2).join('/');
    if (!subs.has(key)) subs.set(key, { key, neurons: 0 });
    if (n.type === 'neuron') subs.get(key).neurons += 1;
  }
  const items = [...subs.values()]
    .sort((a, b) => a.key.localeCompare(b.key))
    .map(info => ({
      key: info.key,
      kicker: 'SUBLOBE',
      title: sublobeTitle(info.key),
      desc: sublobeDescription(info.key),
      color: lobeColor(lobeKey),
      lobe: lobeKey,
      sublobe: info.key,
      statsLine: info.neurons + ' neurons',
    }));
  if (!items.length) {
    // Empty lobe placeholder — single card prompting the user to drop directly to L3.
    items.push({
      key: lobeKey + '/__empty__',
      kicker: 'EMPTY',
      title: 'No sublobes',
      desc: 'Click ▶ to view neurons inside ' + lobeTitle(lobeKey),
      color: lobeColor(lobeKey),
      lobe: lobeKey,
      sublobe: lobeKey,
      statsLine: 'click to view neurons',
      empty: true,
    });
  }
  const rect = stage.getBoundingClientRect();
  const viewport = { width: rect.width || 900, height: rect.height || 600 };
  return layoutLobeMap(items, viewport);
}

function buildLobeEdges(lobeKey) {
  // Filter graph to nodes within this lobe, then run aggregateEdges at
  // sublobe granularity. We do this by building a temporary graph view.
  const memberIds = new Set();
  for (const n of graph.nodes) {
    if (n.lobe === lobeKey) memberIds.add(n.id);
  }
  const view = {
    nodes: graph.nodes.filter(n => memberIds.has(n.id)),
    edges: graph.edges.filter(e => memberIds.has(e.source) && memberIds.has(e.target)),
  };
  return [...aggregateEdges(view, 'lobe').values()];
}

function buildLobeOutbound(lobeKey) {
  // For each non-parent edge with source in lobeKey and target outside (or vice versa),
  // count by direction grouped by the other lobe.
  const groups = new Map(); // otherLobe -> {forward, reverse}
  const nodeMap = new Map(graph.nodes.map(n => [n.id, n]));
  for (const e of graph.edges) {
    if (e.type === 'parent') continue;
    const s = nodeMap.get(e.source);
    const t = nodeMap.get(e.target);
    if (!s || !t) continue;
    if (s.lobe === t.lobe) continue;
    if (s.lobe !== lobeKey && t.lobe !== lobeKey) continue;
    const other = s.lobe === lobeKey ? t.lobe : s.lobe;
    if (!groups.has(other)) groups.set(other, { other, forward: 0, reverse: 0 });
    if (s.lobe === lobeKey) groups.get(other).forward += 1;
    else groups.get(other).reverse += 1;
  }
  return [...groups.values()].sort((a, b) =>
    (b.forward + b.reverse) - (a.forward + a.reverse));
}

function drawLobeMap(lobeKey) {
  lobeBoxes = buildLobeBoxes(lobeKey);
  lobeEdges = buildLobeEdges(lobeKey);
  lobeOutbound = buildLobeOutbound(lobeKey);
  const boxByKey = new Map(lobeBoxes.map(b => [b.key, b]));
  // Lobe frame — draw an outer rounded-rect that contains all sublobes,
  // with the lobe color as a dotted bar on the left.
  if (lobeBoxes.length) {
    const minX = Math.min(...lobeBoxes.map(b => b.x - b.w / 2));
    const maxX = Math.max(...lobeBoxes.map(b => b.x + b.w / 2));
    const minY = Math.min(...lobeBoxes.map(b => b.y - b.h / 2));
    const maxY = Math.max(...lobeBoxes.map(b => b.y + b.h / 2));
    const pad = 40;
    ctx.save();
    ctx.strokeStyle = 'rgba(123, 167, 255, 0.18)';
    ctx.setLineDash([6, 6]);
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.roundRect(minX - pad, minY - pad - 28, maxX - minX + pad * 2, maxY - minY + pad * 2 + 28, 18);
    ctx.stroke();
    ctx.setLineDash([]);
    // Frame title
    ctx.font = 'bold 10px "SFMono-Regular", monospace';
    ctx.fillStyle = '#8ba7d1';
    ctx.fillText('LOBE · ' + lobeTitle(lobeKey).toUpperCase(), minX - pad + 14, minY - pad - 12);
    ctx.restore();
  }
  const query = searchInput.value.trim().toLowerCase();
  const matchSublobe = (key) => {
    if (!query) return false;
    return (sublobeTitle(key) || '').toLowerCase().includes(query)
      || key.toLowerCase().includes(query);
  };
  // Aggregate edges between sublobes
  for (const cell of lobeEdges) {
    const dim = query && !matchSublobe(cell.a) && !matchSublobe(cell.b);
    drawAggregateEdge(cell, boxByKey, { dim });
  }
  // Sublobe boxes
  for (const box of lobeBoxes) {
    const matches = matchSublobe(box.key);
    drawC4Box({
      ...box,
      dim: query && !matches,
      matchHalo: query && matches,
    }, { hover: hoveredId === '__sublobe__' + box.key });
  }
  // Outbound stubs at the bottom of the lobe frame
  if (lobeBoxes.length && lobeOutbound.length) {
    const maxY = Math.max(...lobeBoxes.map(b => b.y + b.h / 2));
    let stubY = maxY + 70;
    let stubX = stage.getBoundingClientRect().width / 2 - (lobeOutbound.length * 130) / 2;
    ctx.save();
    ctx.font = 'bold 10px "SFMono-Regular", monospace';
    for (const stub of lobeOutbound) {
      const f = stub.forward;
      const r = stub.reverse;
      const label = (f && r) ? '→ ' + stub.other + ' (' + f + ') ← (' + r + ')'
        : (f ? '→ ' + stub.other + ' (' + f + ')' : '← ' + stub.other + ' (' + r + ')');
      const m = ctx.measureText(label);
      const w = m.width + 16;
      const h = 22;
      ctx.fillStyle = 'rgba(8, 15, 32, 0.78)';
      ctx.beginPath();
      ctx.roundRect(stubX, stubY - h / 2, w, h, 6);
      ctx.fill();
      ctx.strokeStyle = 'rgba(123, 167, 255, 0.30)';
      ctx.lineWidth = 1;
      ctx.stroke();
      ctx.fillStyle = '#e9f1ff';
      ctx.textAlign = 'left';
      ctx.fillText(label, stubX + 8, stubY + 3);
      stub._x = stubX;
      stub._y = stubY - h / 2;
      stub._w = w;
      stub._h = h;
      stubX += w + 12;
    }
    ctx.restore();
  }
}

function hitTestLobeMap(worldX, worldY) {
  for (const box of lobeBoxes) {
    if (worldX >= box.x - box.w / 2 && worldX <= box.x + box.w / 2 &&
        worldY >= box.y - box.h / 2 && worldY <= box.y + box.h / 2) {
      return { kind: 'sublobe', key: box.key, empty: !!box.empty, lobe: box.lobe };
    }
  }
  for (const cell of lobeEdges) {
    if (cell._midX == null) continue;
    if (Math.abs(worldX - cell._midX) <= cell._w / 2 &&
        Math.abs(worldY - cell._midY) <= cell._h / 2) {
      return { kind: 'edge', a: cell.a, b: cell.b };
    }
  }
  for (const stub of lobeOutbound) {
    if (stub._x == null) continue;
    if (worldX >= stub._x && worldX <= stub._x + stub._w &&
        worldY >= stub._y && worldY <= stub._y + stub._h) {
      return { kind: 'outbound-lobe', other: stub.other };
    }
  }
  return null;
}

// ============================================================
// L3 — Sublobe Map (layered DAG of neurons)
// ============================================================
function buildSublobeNeurons(lobeKey, sublobeKey) {
  // Members of this sublobe — exact match, plus any deeper descendants
  // (e.g. projects/backend/endpoints/* for sublobe projects/backend) so
  // the view stays self-contained and includes inner-rank children.
  return graph.nodes.filter(n =>
    n.sublobe === sublobeKey ||
    (n.sublobe && n.sublobe.startsWith(sublobeKey + '/')));
}

function buildSublobeOutbound(lobeKey, sublobeKey) {
  // Cross-sublobe edges leaving this sublobe.
  const groups = new Map();
  const memberIds = new Set();
  for (const n of graph.nodes) {
    if (n.sublobe === sublobeKey || (n.sublobe && n.sublobe.startsWith(sublobeKey + '/'))) {
      memberIds.add(n.id);
    }
  }
  const nodeMap = new Map(graph.nodes.map(n => [n.id, n]));
  for (const e of graph.edges) {
    if (e.type === 'parent') continue;
    const s = nodeMap.get(e.source);
    const t = nodeMap.get(e.target);
    if (!s || !t) continue;
    const sIn = memberIds.has(e.source);
    const tIn = memberIds.has(e.target);
    if (sIn === tIn) continue;
    const otherNode = sIn ? t : s;
    const otherKey = otherNode.sublobe || otherNode.lobe;
    const labelLobe = otherNode.lobe;
    const key = otherKey + '||' + labelLobe;
    if (!groups.has(key)) groups.set(key, { key: otherKey, lobe: labelLobe, forward: 0, reverse: 0 });
    if (sIn) groups.get(key).forward += 1;
    else groups.get(key).reverse += 1;
  }
  return [...groups.values()];
}

function drawSublobeMap(lobeKey, sublobeKey) {
  const members = buildSublobeNeurons(lobeKey, sublobeKey);
  const rect = stage.getBoundingClientRect();
  const viewport = { width: rect.width || 900, height: rect.height || 600 };
  sublobeBoxes = layoutSublobeMap(lobeKey, sublobeKey, members, viewport);
  sublobeOutbound = buildSublobeOutbound(lobeKey, sublobeKey);
  const boxById = new Map(sublobeBoxes.map(b => [b.id, b]));
  // Edges within this sublobe — three styles per edge type.
  sublobeNeuronEdges = [];
  for (const e of graph.edges) {
    if (!boxById.has(e.source) || !boxById.has(e.target)) continue;
    sublobeNeuronEdges.push(e);
  }
  // Sublobe frame
  if (sublobeBoxes.length) {
    const minX = Math.min(...sublobeBoxes.map(b => b.x - b.w / 2));
    const maxX = Math.max(...sublobeBoxes.map(b => b.x + b.w / 2));
    const minY = Math.min(...sublobeBoxes.map(b => b.y - b.h / 2));
    const maxY = Math.max(...sublobeBoxes.map(b => b.y + b.h / 2));
    const pad = 40;
    ctx.save();
    ctx.strokeStyle = 'rgba(123, 167, 255, 0.18)';
    ctx.setLineDash([6, 6]);
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.roundRect(minX - pad, minY - pad - 28, maxX - minX + pad * 2, maxY - minY + pad * 2 + 28, 18);
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.font = 'bold 10px "SFMono-Regular", monospace';
    ctx.fillStyle = '#8ba7d1';
    ctx.fillText('SUBLOBE · ' + sublobeTitle(sublobeKey).toUpperCase(),
      minX - pad + 14, minY - pad - 12);
    ctx.restore();
  }
  // Edges with three styles (parent solid, related dashed, replaced_by dotted)
  for (const e of sublobeNeuronEdges) {
    const a = boxById.get(e.source);
    const b = boxById.get(e.target);
    ctx.save();
    ctx.strokeStyle = 'rgba(139, 167, 209, 0.55)';
    ctx.lineWidth = 1.4;
    if (e.type === 'parent') {
      ctx.setLineDash([]);
      ctx.beginPath();
      ctx.moveTo(a.x, a.y + a.h / 2);
      const midY = (a.y + a.h / 2 + b.y - b.h / 2) / 2;
      ctx.lineTo(a.x, midY);
      ctx.lineTo(b.x, midY);
      ctx.lineTo(b.x, b.y - b.h / 2);
      ctx.stroke();
      // Arrowhead at target
      _drawArrow(b.x, b.y - b.h / 2, b.x, b.y - b.h / 2 - 6);
    } else if (e.type === 'replaced_by') {
      ctx.setLineDash([2, 4]);
      ctx.beginPath();
      ctx.moveTo(a.x, a.y);
      ctx.lineTo(b.x, b.y);
      ctx.stroke();
      ctx.setLineDash([]);
      _drawArrow(b.x, b.y, a.x, a.y);
    } else {
      // related (or inline) — dashed, no arrow
      ctx.setLineDash([6, 4]);
      ctx.beginPath();
      ctx.moveTo(a.x, a.y);
      ctx.lineTo(b.x, b.y);
      ctx.stroke();
      ctx.setLineDash([]);
    }
    ctx.restore();
  }
  const query = searchInput.value.trim().toLowerCase();
  const nodeMatches = (n) => {
    if (!query) return false;
    const hay = [
      n.title, n.path, n.file_name, n.lobe, n.type, n.file_type || '',
      ...(n.tags || []), n.excerpt || '',
    ].join(' ').toLowerCase();
    return hay.includes(query);
  };
  // Boxes
  for (const box of sublobeBoxes) {
    const matches = nodeMatches(box);
    drawC4Box({
      ...box,
      title: box.title || box.label,
      desc: box.updated || '',
      tagChips: (box.tags || []).slice(0, 2),
      statsLine: box.path,
      dim: query && !matches,
      matchHalo: query && matches,
    }, { hover: hoveredId === box.id });
  }
  // Outbound stubs at the bottom
  if (sublobeBoxes.length && sublobeOutbound.length) {
    const maxY = Math.max(...sublobeBoxes.map(b => b.y + b.h / 2));
    let stubY = maxY + 70;
    let stubX = viewport.width / 2 - (sublobeOutbound.length * 150) / 2;
    ctx.save();
    ctx.font = 'bold 10px "SFMono-Regular", monospace';
    for (const stub of sublobeOutbound) {
      const f = stub.forward;
      const r = stub.reverse;
      const label = (f && r) ? '→ ' + stub.key + ' (' + f + ') ← (' + r + ')'
        : (f ? '→ ' + stub.key + ' (' + f + ')' : '← ' + stub.key + ' (' + r + ')');
      const m = ctx.measureText(label);
      const w = m.width + 16;
      const h = 22;
      ctx.fillStyle = 'rgba(8, 15, 32, 0.78)';
      ctx.beginPath();
      ctx.roundRect(stubX, stubY - h / 2, w, h, 6);
      ctx.fill();
      ctx.strokeStyle = 'rgba(123, 167, 255, 0.30)';
      ctx.lineWidth = 1;
      ctx.stroke();
      ctx.fillStyle = '#e9f1ff';
      ctx.textAlign = 'left';
      ctx.fillText(label, stubX + 8, stubY + 3);
      stub._x = stubX;
      stub._y = stubY - h / 2;
      stub._w = w;
      stub._h = h;
      stubX += w + 12;
    }
    ctx.restore();
  }
}

function _drawArrow(x, y, fromX, fromY) {
  const angle = Math.atan2(y - fromY, x - fromX);
  const len = 6;
  ctx.save();
  ctx.fillStyle = 'rgba(139, 167, 209, 0.78)';
  ctx.beginPath();
  ctx.moveTo(x, y);
  ctx.lineTo(x - len * Math.cos(angle - 0.4), y - len * Math.sin(angle - 0.4));
  ctx.lineTo(x - len * Math.cos(angle + 0.4), y - len * Math.sin(angle + 0.4));
  ctx.closePath();
  ctx.fill();
  ctx.restore();
}

function hitTestSublobeMap(worldX, worldY) {
  for (const box of sublobeBoxes) {
    if (worldX >= box.x - box.w / 2 && worldX <= box.x + box.w / 2 &&
        worldY >= box.y - box.h / 2 && worldY <= box.y + box.h / 2) {
      return { kind: 'neuron', id: box.id };
    }
  }
  for (const stub of sublobeOutbound) {
    if (stub._x == null) continue;
    if (worldX >= stub._x && worldX <= stub._x + stub._w &&
        worldY >= stub._y && worldY <= stub._y + stub._h) {
      return { kind: 'outbound-sublobe', other: stub.key, lobe: stub.lobe };
    }
  }
  return null;
}

// ============================================================
// Stage transitions & breadcrumb
// ============================================================
function setStageMode(mode, lobeKey, sublobeKey, opts) {
  opts = opts || {};
  const instant = !!opts.instant;
  if (!['brain', 'lobe', 'sublobe', 'force'].includes(mode)) {
    mode = 'brain';
  }
  stageMode = mode;
  if (mode === 'lobe') activeLobe = lobeKey || activeLobe || uniqueLobes[0] || null;
  if (mode === 'sublobe') {
    activeLobe = lobeKey || activeLobe;
    activeSublobe = sublobeKey || activeSublobe;
  }
  if (mode === 'brain') {
    selectedId = null;
  }
  // Reflect on mode buttons; disable Lobe/Sublobe when no context.
  for (const btn of modeButtons) {
    const m = btn.dataset.stageMode;
    btn.classList.toggle('active', m === mode);
    btn.setAttribute('aria-pressed', m === mode ? 'true' : 'false');
    if (m === 'lobe') btn.disabled = !activeLobe;
    else if (m === 'sublobe') btn.disabled = !activeSublobe;
    else btn.disabled = false;
  }
  renderBreadcrumb();
  // Reset camera to identity for C4 modes; force mode reuses fitToFilteredNodes.
  if (mode === 'force') {
    if (legacyForce && legacyForce.initialized) {
      legacyForce.fit(instant);
    } else {
      initLegacyForce();
      legacyForce.fit(true);
    }
  } else {
    if (instant) {
      camera.x = 0;
      camera.y = 0;
      camera.scale = 1;
    } else {
      animateCamera(0, 0, 1, 240);
    }
  }
  requestDraw();
}

function renderBreadcrumb() {
  const segments = [];
  segments.push({ label: BRAIN_NAME, level: 'brain' });
  if (stageMode === 'lobe' || stageMode === 'sublobe') {
    if (activeLobe) segments.push({ label: lobeTitle(activeLobe), level: 'lobe', key: activeLobe });
  }
  if (stageMode === 'sublobe' && activeSublobe) {
    segments.push({ label: sublobeTitle(activeSublobe), level: 'sublobe', key: activeSublobe });
  }
  if (stageMode === 'force') {
    segments.push({ label: 'Expert', level: 'force' });
  }
  breadcrumbEl.innerHTML = '';
  segments.forEach((seg, idx) => {
    const isLast = idx === segments.length - 1;
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'crumb' + (isLast ? ' active' : '');
    btn.dataset.level = seg.level;
    if (seg.key) btn.dataset.key = seg.key;
    btn.textContent = seg.label;
    btn.addEventListener('click', () => {
      if (isLast) return;
      if (seg.level === 'brain') setStageMode('brain');
      else if (seg.level === 'lobe') setStageMode('lobe', seg.key);
    });
    breadcrumbEl.appendChild(btn);
    if (!isLast) {
      const sep = document.createElement('span');
      sep.className = 'sep';
      sep.textContent = '›';
      breadcrumbEl.appendChild(sep);
    }
  });
}

function focusLobe(lobeKey) { setStageMode('lobe', lobeKey); }
function focusSublobe(lobeKey, sublobeKey) { setStageMode('sublobe', lobeKey, sublobeKey); }

// ============================================================
// Camera / pointer plumbing
// ============================================================
let cameraAnim = null;
function animateCamera(tx, ty, ts, duration) {
  const sx = camera.x, sy = camera.y, ss = camera.scale;
  const start = performance.now();
  if (cameraAnim) cancelAnimationFrame(cameraAnim);
  function step(now) {
    const t = Math.min(1, (now - start) / duration);
    const ease = t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;
    camera.x = sx + (tx - sx) * ease;
    camera.y = sy + (ty - sy) * ease;
    camera.scale = ss + (ts - ss) * ease;
    requestDraw();
    if (t < 1) cameraAnim = requestAnimationFrame(step);
    else cameraAnim = null;
  }
  cameraAnim = requestAnimationFrame(step);
}

function resize() {
  const rect = stage.getBoundingClientRect();
  W = canvas.width = Math.floor(rect.width * devicePixelRatio);
  H = canvas.height = Math.floor(rect.height * devicePixelRatio);
  canvas.style.width = rect.width + 'px';
  canvas.style.height = rect.height + 'px';
  ctx.setTransform(devicePixelRatio, 0, 0, devicePixelRatio, 0, 0);
  if (legacyForce) legacyForce.buildAnchors(rect.width, rect.height);
  requestDraw();
}

function toWorld(clientX, clientY) {
  const rect = canvas.getBoundingClientRect();
  return {
    x: (clientX - rect.left - camera.x) / camera.scale,
    y: (clientY - rect.top - camera.y) / camera.scale,
  };
}

// ============================================================
// Master draw + animation loop
// ============================================================
function draw() {
  const rect = canvas.getBoundingClientRect();
  ctx.clearRect(0, 0, rect.width, rect.height);
  ctx.save();
  ctx.translate(camera.x, camera.y);
  ctx.scale(camera.scale, camera.scale);
  if (stageMode === 'brain') {
    drawBrainMap();
  } else if (stageMode === 'lobe' && activeLobe) {
    drawLobeMap(activeLobe);
  } else if (stageMode === 'sublobe' && activeLobe && activeSublobe) {
    drawSublobeMap(activeLobe, activeSublobe);
  } else if (stageMode === 'force') {
    legacyForce && legacyForce.draw();
  }
  ctx.restore();
}

function loop() {
  if (stageMode === 'force') {
    if (legacyForce) {
      const ticks = legacyForce.filteredNodes.length > FORCE_PAIRWISE_LIMIT ? 1 : 2;
      for (let i = 0; i < ticks; i++) legacyForce.tick();
      draw();
    }
  } else if (needsDraw) {
    draw();
    needsDraw = false;
  }
  // The flash highlight on L1 needs to expire on its own.
  if (highlightedEdge && performance.now() < highlightedEdgeUntil) {
    requestDraw();
  } else if (highlightedEdge && performance.now() >= highlightedEdgeUntil) {
    highlightedEdge = null;
    requestDraw();
  }
  requestAnimationFrame(loop);
}

// ============================================================
// Pointer events — route to the active level's hit tester
// ============================================================
canvas.addEventListener('pointerdown', event => {
  canvas.setPointerCapture(event.pointerId);
  dragMoved = false;
  lastPointer = { x: event.clientX, y: event.clientY };
  isPanning = true;
  canvas.classList.add('dragging');
});

canvas.addEventListener('pointermove', event => {
  pointer = { x: event.clientX, y: event.clientY };
  const world = toWorld(event.clientX, event.clientY);
  let hit = null;
  if (stageMode === 'brain') hit = hitTestBrainMap(world.x, world.y);
  else if (stageMode === 'lobe') hit = hitTestLobeMap(world.x, world.y);
  else if (stageMode === 'sublobe') hit = hitTestSublobeMap(world.x, world.y);
  // Force mode has its own hit-test inside legacyForce.
  if (stageMode === 'force' && legacyForce) {
    hit = legacyForce.hitTest(world.x, world.y);
  }
  if (hit) {
    if (hit.kind === 'lobe') hoveredId = '__lobe__' + hit.key;
    else if (hit.kind === 'sublobe') hoveredId = '__sublobe__' + hit.key;
    else if (hit.kind === 'neuron') hoveredId = hit.id;
    else hoveredId = null;
  } else hoveredId = null;
  const dx = event.clientX - lastPointer.x;
  const dy = event.clientY - lastPointer.y;
  if (Math.abs(dx) > 1 || Math.abs(dy) > 1) dragMoved = true;
  lastPointer = { x: event.clientX, y: event.clientY };
  if (isPanning) {
    camera.x += dx;
    camera.y += dy;
  }
  requestDraw();
});

canvas.addEventListener('pointerup', event => {
  isPanning = false;
  canvas.classList.remove('dragging');
  if (dragMoved) return;
  const world = toWorld(event.clientX, event.clientY);
  if (stageMode === 'brain') {
    const hit = hitTestBrainMap(world.x, world.y);
    if (!hit) return;
    if (hit.kind === 'lobe') focusLobe(hit.key);
    else if (hit.kind === 'edge') {
      highlightedEdge = { a: hit.a, b: hit.b };
      highlightedEdgeUntil = performance.now() + 1200;
      requestDraw();
    }
    return;
  }
  if (stageMode === 'lobe') {
    const hit = hitTestLobeMap(world.x, world.y);
    if (!hit) return;
    if (hit.kind === 'sublobe') {
      if (hit.empty) {
        // Empty lobe placeholder: drop directly to L3 of the lobe itself.
        focusSublobe(hit.lobe, hit.lobe);
      } else {
        focusSublobe(hit.lobe, hit.key);
      }
    } else if (hit.kind === 'outbound-lobe') {
      // Navigate back to L1 with the target lobe pre-selected (flashes
      // the edge between the current and target lobe so the user can see
      // the relationship).
      const currentLobe = activeLobe;
      setStageMode('brain');
      if (currentLobe && hit.other) {
        const [a, b] = currentLobe.localeCompare(hit.other) <= 0
          ? [currentLobe, hit.other]
          : [hit.other, currentLobe];
        highlightedEdge = { a, b };
        highlightedEdgeUntil = performance.now() + 1500;
        requestDraw();
      }
    }
    return;
  }
  if (stageMode === 'sublobe') {
    const hit = hitTestSublobeMap(world.x, world.y);
    if (!hit) return;
    if (hit.kind === 'neuron') {
      const node = graph.nodes.find(n => n.id === hit.id);
      if (node) {
        selectedId = node.id;
        openModal(node);
      }
    } else if (hit.kind === 'outbound-sublobe') {
      // Navigate to L2 of the parent lobe of the target.
      setStageMode('lobe', hit.lobe);
    }
    return;
  }
  if (stageMode === 'force' && legacyForce) {
    legacyForce.handleClick(world.x, world.y);
  }
});

canvas.addEventListener('pointerleave', () => {
  hoveredId = null;
  isPanning = false;
  canvas.classList.remove('dragging');
  requestDraw();
});

canvas.addEventListener('wheel', event => {
  event.preventDefault();
  const rect = canvas.getBoundingClientRect();
  const mouseX = event.clientX - rect.left;
  const mouseY = event.clientY - rect.top;
  const worldX = (mouseX - camera.x) / camera.scale;
  const worldY = (mouseY - camera.y) / camera.scale;
  const nextScale = Math.min(2.6, Math.max(0.35, camera.scale * (event.deltaY < 0 ? 1.08 : 0.92)));
  camera.x = mouseX - worldX * nextScale;
  camera.y = mouseY - worldY * nextScale;
  camera.scale = nextScale;
  requestDraw();
}, { passive: false });

// ============================================================
// Search / filter / lobe filter
// ============================================================
function refreshSearch() {
  const query = searchInput.value.trim().toLowerCase();
  // Render results panel with grouped Neurons / Sublobes / Lobes counts.
  resultsEl.innerHTML = '';
  if (!query) {
    resultCountEl.textContent = '';
    requestDraw();
    return;
  }
  const matches = { Neurons: [], Sublobes: [], Lobes: [] };
  for (const lobeKey of uniqueLobes) {
    if (lobeKey.toLowerCase().includes(query) || (lobeTitle(lobeKey) || '').toLowerCase().includes(query)) {
      matches.Lobes.push({ kind: 'lobe', key: lobeKey, title: lobeTitle(lobeKey) });
    }
  }
  const seenSubs = new Set();
  for (const n of graph.nodes) {
    if (n.sublobe && n.sublobe !== n.lobe && !seenSubs.has(n.sublobe)) {
      const t = (sublobeTitle(n.sublobe) || '').toLowerCase();
      if (t.includes(query) || n.sublobe.toLowerCase().includes(query)) {
        matches.Sublobes.push({ kind: 'sublobe', key: n.sublobe, lobe: n.lobe, title: sublobeTitle(n.sublobe) });
        seenSubs.add(n.sublobe);
      }
    }
  }
  for (const n of graph.nodes) {
    if (n.type !== 'neuron' && n.type !== 'glossary' && n.type !== 'index') continue;
    const hay = [
      n.title, n.path, n.file_name, n.lobe, n.type, n.file_type || '',
      ...(n.tags || []), n.excerpt || '',
    ].join(' ').toLowerCase();
    if (hay.includes(query)) matches.Neurons.push({ kind: 'neuron', node: n });
  }
  const total = matches.Neurons.length + matches.Sublobes.length + matches.Lobes.length;
  resultCountEl.textContent = total + ' result' + (total === 1 ? '' : 's');
  for (const group of ['Lobes', 'Sublobes', 'Neurons']) {
    if (!matches[group].length) continue;
    const heading = document.createElement('div');
    heading.className = 'panel-section-header';
    heading.style.padding = '4px 4px';
    heading.innerHTML = '<h3>' + group + ' (' + matches[group].length + ')</h3>';
    resultsEl.appendChild(heading);
    for (const m of matches[group].slice(0, 12)) {
      const card = document.createElement('button');
      card.type = 'button';
      card.className = 'result-card';
      let title = '';
      let meta = '';
      let path = '';
      if (m.kind === 'lobe') {
        title = m.title;
        meta = 'lobe';
      } else if (m.kind === 'sublobe') {
        title = m.title;
        meta = 'sublobe · ' + m.lobe;
      } else {
        title = m.node.title;
        meta = m.node.type + ' · ' + (m.node.sublobe || m.node.lobe);
        path = m.node.path;
      }
      card.innerHTML =
        '<div class="result-title">' + escapeHtml(title) + '</div>' +
        '<div class="result-meta">' + escapeHtml(meta) + '</div>' +
        (path ? '<div class="result-path">' + escapeHtml(path) + '</div>' : '');
      card.addEventListener('click', () => {
        if (m.kind === 'lobe') focusLobe(m.key);
        else if (m.kind === 'sublobe') focusSublobe(m.lobe, m.key);
        else if (m.kind === 'neuron') {
          // Drop into the deepest level that contains this neuron.
          if (m.node.sublobe && m.node.sublobe !== m.node.lobe) {
            const parts = m.node.sublobe.split('/');
            const subKey = parts.length > 2 ? parts.slice(0, 2).join('/') : m.node.sublobe;
            focusSublobe(m.node.lobe, subKey);
          } else {
            focusLobe(m.node.lobe);
          }
          selectedId = m.node.id;
          openModal(m.node);
        }
      });
      resultsEl.appendChild(card);
    }
  }
  requestDraw();
}

function searchEnterJump() {
  // If exactly one result across all groups, jump to its level.
  const query = searchInput.value.trim().toLowerCase();
  if (!query) return;
  // Reuse the matching logic from refreshSearch by walking the result cards.
  const cards = resultsEl.querySelectorAll('.result-card');
  if (cards.length === 1) cards[0].click();
}

function renderLobeFilter() {
  lobesListEl.innerHTML = '';
  for (const lobeKey of uniqueLobes) {
    const stats = lobeStats(lobeKey);
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'lobe-row' + (hiddenLobes.has(lobeKey) ? ' dimmed' : '');
    btn.style.setProperty('--bar', lobeColor(lobeKey));
    btn.dataset.lobe = lobeKey;
    btn.innerHTML =
      '<span class="swatch"></span>' +
      '<span class="label">' + escapeHtml(lobeTitle(lobeKey)) + '</span>' +
      '<span class="count">' + stats.neurons + '</span>' +
      '<span class="vis">' + (hiddenLobes.has(lobeKey) ? '○' : '●') + '</span>';
    btn.addEventListener('click', () => {
      if (hiddenLobes.has(lobeKey)) hiddenLobes.delete(lobeKey);
      else hiddenLobes.add(lobeKey);
      renderLobeFilter();
      requestDraw();
    });
    lobesListEl.appendChild(btn);
  }
}

function renderRecent() {
  recentListEl.innerHTML = '';
  const neurons = graph.nodes
    .filter(n => n.type === 'neuron' && n.updated)
    .sort((a, b) => String(b.updated).localeCompare(String(a.updated)))
    .slice(0, 5);
  for (const n of neurons) {
    const row = document.createElement('button');
    row.type = 'button';
    row.className = 'recent-row';
    row.innerHTML =
      '<span class="label">' + escapeHtml(n.title) + '</span>' +
      '<span class="ago">' + escapeHtml(_relAgo(n.updated)) + '</span>';
    row.addEventListener('click', () => {
      // Drop into the level containing this neuron and open modal.
      if (n.sublobe && n.sublobe !== n.lobe) {
        const parts = n.sublobe.split('/');
        const subKey = parts.length > 2 ? parts.slice(0, 2).join('/') : n.sublobe;
        focusSublobe(n.lobe, subKey);
      } else {
        focusLobe(n.lobe);
      }
      selectedId = n.id;
      openModal(n);
    });
    recentListEl.appendChild(row);
  }
}

function _relAgo(dateStr) {
  if (!dateStr) return '';
  const t = Date.parse(dateStr);
  if (isNaN(t)) return '';
  const diff = Date.now() - t;
  const days = Math.round(diff / 86400000);
  if (days < 1) return 'today';
  if (days < 60) return days + 'd';
  const months = Math.round(days / 30);
  if (months < 24) return months + 'mo';
  return Math.round(days / 365) + 'y';
}

// ============================================================
// File tree (left sidebar)
// ============================================================
const treeRoot = { folders: new Map(), files: [] };
let treeBuilt = false;
function buildFileTree() {
  treeRoot.folders = new Map();
  treeRoot.files = [];
  const entries = graph.nodes
    .filter(n => (n.type === 'neuron' || n.type === 'glossary') && n.path)
    .sort((a, b) => a.path.localeCompare(b.path));
  for (const node of entries) {
    const parts = node.path.split('/');
    let cursor = treeRoot;
    for (let i = 0; i < parts.length - 1; i++) {
      const part = parts[i];
      if (!cursor.folders.has(part)) {
        cursor.folders.set(part, { folders: new Map(), files: [] });
      }
      cursor = cursor.folders.get(part);
    }
    cursor.files.push(node);
  }
  treeBuilt = true;
}
const treeCollapsed = {
  'modal-tree': new Set(),
  'panel-tree': new Set(),
};
function renderTreeFolder(name, folder, pathSoFar, targetId) {
  const full = pathSoFar ? pathSoFar + '/' + name : name;
  const collapsed = (treeCollapsed[targetId] || new Set()).has(full);
  const caret = collapsed ? '▸' : '▾';
  const subFolderHtml = [...folder.folders.entries()]
    .sort((a, b) => a[0].localeCompare(b[0]))
    .map(([n, f]) => renderTreeFolder(n, f, full, targetId))
    .join('');
  const fileHtml = folder.files
    .sort((a, b) => a.title.localeCompare(b.title))
    .map(node => '<div class="modal-tree-file" data-tree-node="' + node.id +
      '" title="' + escapeHtml(node.path) + '"><span class="icon">📄</span>' +
      escapeHtml(node.title) + '</div>')
    .join('');
  // Lobe color for top-level folders
  const topLobeColor = pathSoFar === '' && uniqueLobes.includes(name)
    ? ' style="--bar:' + lobeColor(name) + '"'
    : '';
  return (
    '<div class="modal-tree-folder' + (collapsed ? ' collapsed' : '') +
      '" data-tree-folder="' + escapeHtml(full) + '"' + topLobeColor + '>' +
    '<div class="modal-tree-folder-label"><span class="caret">' + caret +
      '</span><span class="icon">📁</span>' + escapeHtml(name) + '</div>' +
    '<div class="modal-tree-children">' + subFolderHtml + fileHtml + '</div>' +
    '</div>'
  );
}
function renderFileTree(activeNodeId, targetId) {
  if (!targetId) targetId = 'modal-tree';
  if (!treeBuilt) buildFileTree();
  const treeEl = document.getElementById(targetId);
  if (!treeEl) return;
  if (!treeCollapsed[targetId]) treeCollapsed[targetId] = new Set();
  const topFolders = [...treeRoot.folders.entries()]
    .sort((a, b) => a[0].localeCompare(b[0]))
    .map(([n, f]) => renderTreeFolder(n, f, '', targetId))
    .join('');
  const topFiles = treeRoot.files
    .sort((a, b) => a.title.localeCompare(b.title))
    .map(node => '<div class="modal-tree-file" data-tree-node="' + node.id +
      '" title="' + escapeHtml(node.path) + '"><span class="icon">📄</span>' +
      escapeHtml(node.title) + '</div>')
    .join('');
  treeEl.innerHTML = topFolders + topFiles;
  if (activeNodeId != null) {
    for (const el of treeEl.querySelectorAll('.modal-tree-file')) {
      if (Number(el.dataset.treeNode) === activeNodeId) el.classList.add('active');
    }
  }
  for (const el of treeEl.querySelectorAll('.modal-tree-folder-label')) {
    el.addEventListener('click', () => {
      const folder = el.closest('.modal-tree-folder');
      const path = folder?.dataset.treeFolder;
      if (!path) return;
      const collapsedSet = treeCollapsed[targetId];
      if (collapsedSet.has(path)) {
        collapsedSet.delete(path);
        folder.classList.remove('collapsed');
      } else {
        collapsedSet.add(path);
        folder.classList.add('collapsed');
      }
    });
  }
  for (const el of treeEl.querySelectorAll('.modal-tree-file')) {
    el.addEventListener('click', () => {
      const target = graph.nodes.find(n => n.id === Number(el.dataset.treeNode));
      if (target) {
        selectedId = target.id;
        // Focus into the level that contains it.
        if (target.sublobe && target.sublobe !== target.lobe) {
          const parts = target.sublobe.split('/');
          const subKey = parts.length > 2 ? parts.slice(0, 2).join('/') : target.sublobe;
          focusSublobe(target.lobe, subKey);
        } else if (target.lobe && target.lobe !== 'root') {
          focusLobe(target.lobe);
        }
        openModal(target);
      }
    });
  }
}

// ============================================================
// Helpers — escapeHtml, markdown / yaml renderers (unchanged from prior MRI)
// ============================================================
function escapeHtml(value) {
  return String(value || '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;');
}

function renderInline(text) {
  let html = escapeHtml(text);
  html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
  html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  html = html.replace(/(^|[^*])\*([^*]+)\*/g, '$1<em>$2</em>');
  html = html.replace(
    /\[([^\]]+)\]\(([^)\s]+)\)/g,
    '<a class="md-link" href="#" data-md-link="$2">$1</a>'
  );
  return html;
}
function _isTableRow(line) { return /^\s*\|.*\|\s*$/.test(line); }
function _isTableSeparator(line) {
  return /^\s*\|[\s:|\-]+\|\s*$/.test(line) && /-/.test(line);
}
function _parseRow(line) {
  let row = line.trim();
  if (row.startsWith('|')) row = row.slice(1);
  if (row.endsWith('|')) row = row.slice(0, -1);
  return row.split('|').map(c => c.trim());
}
function _renderTable(headerLine, bodyLines) {
  const headers = _parseRow(headerLine);
  let html = '<table><thead><tr>';
  for (const h of headers) html += '<th>' + renderInline(h) + '</th>';
  html += '</tr></thead><tbody>';
  for (const row of bodyLines) {
    const cells = _parseRow(row);
    html += '<tr>';
    for (const c of cells) html += '<td>' + renderInline(c) + '</td>';
    html += '</tr>';
  }
  html += '</tbody></table>';
  return html;
}
function renderMarkdown(md) {
  const lines = (md || '').split(/\r?\n/);
  const out = [];
  let inCode = false;
  let codeBuf = [];
  let listType = null;
  let inQuote = false;
  function flushList() {
    if (listType) { out.push('</' + listType + '>'); listType = null; }
  }
  function flushQuote() {
    if (inQuote) { out.push('</blockquote>'); inQuote = false; }
  }
  let i = 0;
  while (i < lines.length) {
    const raw = lines[i];
    if (inCode) {
      if (/^```/.test(raw)) {
        out.push('<pre><code>' + escapeHtml(codeBuf.join('\n')) + '</code></pre>');
        codeBuf = []; inCode = false;
      } else { codeBuf.push(raw); }
      i++; continue;
    }
    if (/^```/.test(raw)) {
      flushList(); flushQuote(); inCode = true; i++; continue;
    }
    if (
      _isTableRow(raw) &&
      i + 1 < lines.length &&
      _isTableSeparator(lines[i + 1])
    ) {
      flushList(); flushQuote();
      const header = raw;
      const body = [];
      i += 2;
      while (i < lines.length && _isTableRow(lines[i])) {
        body.push(lines[i]); i++;
      }
      out.push(_renderTable(header, body));
      continue;
    }
    const h = /^(#{1,6})\s+(.*)$/.exec(raw);
    if (h) {
      flushList(); flushQuote();
      const level = h[1].length;
      out.push('<h' + level + '>' + renderInline(h[2]) + '</h' + level + '>');
      i++; continue;
    }
    const ul = /^[-*]\s+(.*)$/.exec(raw);
    const ol = /^\d+\.\s+(.*)$/.exec(raw);
    if (ul) {
      flushQuote();
      if (listType !== 'ul') { flushList(); out.push('<ul>'); listType = 'ul'; }
      out.push('<li>' + renderInline(ul[1]) + '</li>');
      i++; continue;
    }
    if (ol) {
      flushQuote();
      if (listType !== 'ol') { flushList(); out.push('<ol>'); listType = 'ol'; }
      out.push('<li>' + renderInline(ol[1]) + '</li>');
      i++; continue;
    }
    const bq = /^>\s?(.*)$/.exec(raw);
    if (bq) {
      flushList();
      if (!inQuote) { out.push('<blockquote>'); inQuote = true; }
      out.push('<p>' + renderInline(bq[1]) + '</p>');
      i++; continue;
    }
    flushList(); flushQuote();
    if (/^\s*$/.test(raw)) { out.push(''); i++; continue; }
    if (/^[-=]{3,}\s*$/.test(raw)) { out.push('<hr>'); i++; continue; }
    out.push('<p>' + renderInline(raw) + '</p>');
    i++;
  }
  flushList(); flushQuote();
  if (inCode) {
    out.push('<pre><code>' + escapeHtml(codeBuf.join('\n')) + '</code></pre>');
  }
  return out.join('\n');
}
function _highlightYamlLine(escapedLine) {
  if (/^\s*#/.test(escapedLine)) {
    return '<span class="yaml-comment">' + escapedLine + '</span>';
  }
  let html = escapedLine;
  html = html.replace(/(\s)(#.*)$/, '$1<span class="yaml-comment">$2</span>');
  html = html.replace(
    /^(\s*-?\s*)('[^']*'|"[^"]*"|[\w./\-]+)(\s*:)/,
    '$1<span class="yaml-key">$2</span>$3'
  );
  html = html.replace(
    /(:\s|-\s)('[^']*'|"[^"]*")/g,
    '$1<span class="yaml-string">$2</span>'
  );
  html = html.replace(
    /(:\s|-\s)(true|false|null|yes|no)\b/g,
    '$1<span class="yaml-bool">$2</span>'
  );
  html = html.replace(
    /(:\s|-\s)(-?\d+(?:\.\d+)?)\b/g,
    '$1<span class="yaml-num">$2</span>'
  );
  return html;
}
function renderYaml(text) {
  const lines = (text || '').split(/\r?\n/);
  const highlighted = lines
    .map(l => _highlightYamlLine(escapeHtml(l)))
    .join('\n');
  return '<pre class="yaml-preview"><code>' + highlighted + '</code></pre>';
}

// ============================================================
// Modal — open neuron details with C4 kicker, monospace stats
// ============================================================
const navHistory = [];
let navIndex = -1;
function pushNav(id) {
  if (navHistory[navIndex] === id) return;
  navHistory.splice(navIndex + 1);
  navHistory.push(id);
  navIndex = navHistory.length - 1;
}
function openModal(node) {
  pushNav(node.id);
  const modal = document.getElementById('content-modal');
  const breadcrumb = node.path.split('/').map(p => p.replace(/\.(md|yml|yaml)$/, '')).join(' / ');
  document.getElementById('modal-kicker').textContent =
    node.type === 'glossary' ? 'GLOSSARY' :
    node.type === 'index' ? 'INDEX' :
    node.type === 'map' ? 'MAP' :
    node.file_type === 'yaml' ? 'YAML' : 'NEURON';
  document.getElementById('modal-title').textContent = node.title;
  // Stats line (mono)
  const statsEl = document.getElementById('modal-stats');
  const parts = [];
  if (node.lobe && node.lobe !== 'root') parts.push(node.lobe);
  if (node.sublobe && node.sublobe !== node.lobe) parts.push(node.sublobe);
  if (node.tags && node.tags.length) parts.push('tags: ' + node.tags.join(', '));
  if (node.updated) parts.push('updated ' + node.updated);
  statsEl.innerHTML =
    '<span>' + escapeHtml(breadcrumb) + '</span>' +
    (parts.length ? '<span class="dot">·</span><span>' + escapeHtml(parts.join(' · ')) + '</span>' : '');
  renderFileTree(node.id, 'modal-tree');
  const raw = node.content_full || node.content_preview || 'No content.';
  const isYaml = node.file_type === 'yaml';
  const modalContent = document.getElementById('modal-content');
  modalContent.innerHTML = isYaml ? renderYaml(raw) : renderMarkdown(raw);
  if (!isYaml) {
    const nodePath = node.path.replace(/[^/]+$/, '');
    for (const a of modalContent.querySelectorAll('a.md-link[data-md-link]')) {
      const href = a.dataset.mdLink || '';
      const noAnchor = href.split('#')[0].split('?')[0];
      if (!noAnchor || /^https?:/.test(noAnchor)) continue;
      if (!/\.(md|ya?ml)$/i.test(noAnchor)) continue;
      const linkParts = (nodePath + noAnchor).split('/');
      const resolved = [];
      for (const p of linkParts) {
        if (p === '..') resolved.pop();
        else if (p && p !== '.') resolved.push(p);
      }
      const resolvedPath = resolved.join('/');
      const target = graph.nodes.find(n => n.path === resolvedPath);
      a.classList.remove('md-link');
      a.removeAttribute('href');
      if (target) {
        a.classList.add('content-link');
        a.dataset.modalNav = String(target.id);
        const anchor = href.includes('#') ? '#' + href.split('#')[1] : '';
        a.title = target.path + anchor;
      } else {
        a.classList.add('content-link-broken');
        a.title = 'broken link: ' + href;
      }
    }
    for (const btn of modalContent.querySelectorAll('[data-modal-nav]')) {
      btn.addEventListener('click', () => {
        const target = graph.nodes.find(n => n.id === Number(btn.dataset.modalNav));
        if (target) { openModal(target); }
      });
    }
  }
  // Synapse nav buttons (linked neurons)
  const navEl = document.getElementById('modal-nav');
  const connected = [...(neighbors.get(node.id) || [])]
    .map(id => graph.nodes.find(n => n.id === id))
    .filter(n => n && n.type === 'neuron')
    .sort((a, b) => a.title.localeCompare(b.title));
  const NAV_COLLAPSE = 6;
  const currentParts = node.path.split('/');
  const currentParent = currentParts.length >= 2 ? currentParts[currentParts.length - 2] : '';
  const allNavHtml = connected.map(n => {
    const np = n.path.split('/');
    const parent = np.length >= 2 ? np[np.length - 2] : '';
    const label = parent && parent !== currentParent ? parent + ' / ' + n.title : n.title;
    return '<button type="button" class="modal-nav-btn" data-modal-nav="' + n.id +
      '" title="' + escapeHtml(n.path) + '">' + escapeHtml(label) + '</button>';
  });
  const hasOverflow = connected.length > NAV_COLLAPSE;
  function renderNav(expanded) {
    const btns = expanded ? allNavHtml.join('') : allNavHtml.slice(0, NAV_COLLAPSE).join('');
    const toggle = hasOverflow
      ? '<button type="button" class="modal-nav-toggle" id="modal-nav-toggle">' +
        (expanded ? 'show less' : '+' + (connected.length - NAV_COLLAPSE) + ' more') + '</button>'
      : '';
    navEl.innerHTML = btns + toggle;
    for (const btn of navEl.querySelectorAll('[data-modal-nav]')) {
      btn.addEventListener('click', () => {
        const target = graph.nodes.find(n => n.id === Number(btn.dataset.modalNav));
        if (target) { openModal(target); }
      });
    }
    const tog = document.getElementById('modal-nav-toggle');
    if (tog) tog.addEventListener('click', () => renderNav(!expanded));
  }
  renderNav(false);
  modal.style.display = 'flex';
}

// ============================================================
// Legacy force graph (Expert mode) — preserved verbatim from v2.16.3 logic,
// scoped under `legacyForce` so it doesn't collide with the C4 levels.
// ============================================================
let legacyForce = null;
function initLegacyForce() {
  if (legacyForce) return;
  const lobeAnchors = new Map();
  const depthMap = new Map();
  const treeParent = new Map();
  function buildTree() {
    depthMap.clear();
    const parentEdges = graph.edges.filter(e => e.type === 'parent');
    for (const n of graph.nodes) if (n.type === 'brain') depthMap.set(n.id, 0);
    let frontier = [...depthMap.keys()];
    while (frontier.length) {
      const next = [];
      for (const pid of frontier) {
        for (const e of parentEdges) {
          if (e.target === pid && !depthMap.has(e.source)) {
            depthMap.set(e.source, depthMap.get(pid) + 1);
            treeParent.set(e.source, pid);
            next.push(e.source);
          }
        }
      }
      frontier = next;
    }
    for (const n of graph.nodes) {
      if (!depthMap.has(n.id)) depthMap.set(n.id, n.type === 'map' ? 1 : 2);
    }
  }
  buildTree();
  function _hexToRgb(hex) {
    return [
      parseInt(hex.slice(1, 3), 16),
      parseInt(hex.slice(3, 5), 16),
      parseInt(hex.slice(5, 7), 16),
    ];
  }
  function _desaturate(hex, amount) {
    const [r, g, b] = _hexToRgb(hex);
    const gray = (r + g + b) / 3;
    return 'rgb(' + Math.round(r + (gray - r) * amount) + ',' +
      Math.round(g + (gray - g) * amount) + ',' +
      Math.round(b + (gray - b) * amount) + ')';
  }
  function colorForNode(node) {
    if (node.type === 'brain') return '#ffffff';
    if (node.type === 'glossary') return '#ffc6f4';
    if (node.type === 'index') return '#ffd28e';
    if (node.type === 'map') return lobeColor(node.lobe);
    if (node.file_type === 'yaml') return '#9ea9ff';
    return _desaturate(lobeColor(node.lobe), 0.3);
  }
  function nodeRadius(node) {
    if (node.type === 'brain') return 22;
    if (node.type === 'glossary') return 13;
    if (node.type === 'index') return 11;
    if (node.type === 'map') {
      const d = depthMap.get(node.id) || 1;
      return d <= 1 ? 30 : 22;
    }
    return Math.max(6, 5 + Math.min(node.degree || 0, 6) * 0.6);
  }
  function buildAnchors(width, height) {
    const cx = width / 2;
    const cy = height / 2;
    // Elliptical anchor ring so lobes always sit inside the viewport, no
    // matter the aspect ratio. With a landscape stage the old min-based
    // radius pushed top/bottom lobes off-canvas. width * 0.36 / height * 0.36
    // leaves ~14% margin on each side for orbit + hull spread.
    const rx = width * 0.36;
    const ry = height * 0.36;
    const nonRoot = uniqueLobes;
    lobeAnchors.set('root', { x: cx, y: cy * 0.86 });
    nonRoot.forEach((lobe, i) => {
      const angle = -Math.PI / 2 + (i / Math.max(1, nonRoot.length)) * Math.PI * 2;
      lobeAnchors.set(lobe, { x: cx + Math.cos(angle) * rx, y: cy + Math.sin(angle) * ry });
    });
  }
  function initializeNodes() {
    const dim = stage.getBoundingClientRect();
    const lobeCounters = new Map();
    return graph.nodes.map((node, idx) => {
      const anchor = lobeAnchors.get(node.lobe) || lobeAnchors.get('root') ||
        { x: dim.width / 2, y: dim.height / 2 };
      let tx, ty;
      const d = depthMap.get(node.id) || 0;
      if (node.type === 'brain') {
        tx = dim.width / 2; ty = dim.height / 2;
      } else if (node.type === 'glossary') {
        tx = dim.width / 2; ty = dim.height * 0.12;
      } else if (node.type === 'index') {
        tx = dim.width * 0.14; ty = dim.height * 0.14;
      } else if (node.type === 'map') {
        if (d <= 1) { tx = anchor.x; ty = anchor.y; }
        else {
          const c = lobeCounters.get('sublobe_' + node.lobe) || 0;
          lobeCounters.set('sublobe_' + node.lobe, c + 1);
          const subAngle = -Math.PI / 2 + (c / 3) * Math.PI * 2;
          tx = anchor.x + Math.cos(subAngle) * 65;
          ty = anchor.y + Math.sin(subAngle) * 65;
        }
      } else {
        const c = lobeCounters.get(node.lobe) || 0;
        lobeCounters.set(node.lobe, c + 1);
        const orbitR = 70 + c * 22;
        const angle = c * 0.85 + idx * 0.13;
        tx = anchor.x + Math.cos(angle) * orbitR;
        ty = anchor.y + Math.sin(angle) * orbitR;
      }
      const searchText = [
        node.title, node.path, node.file_name, node.lobe, node.type,
        node.file_type || '', ...(node.tags || []), node.excerpt || '',
        node.content_preview || '',
      ].join(' ').toLowerCase();
      return {
        ...node,
        searchText,
        color: colorForNode(node),
        radius: nodeRadius(node),
        depth: d,
        x: tx + (Math.random() - 0.5) * 6,
        y: ty + (Math.random() - 0.5) * 6,
        vx: 0, vy: 0,
        targetX: tx, targetY: ty,
      };
    });
  }
  let nodes = [];
  let filteredNodes = [];
  function visibleNode(node) {
    if (node.type === 'brain') return false;
    if (node.type === 'map') return false;
    if (hiddenLobes.has(node.lobe)) return false;
    const query = searchInput.value.trim().toLowerCase();
    if (!query) return true;
    return node.searchText.includes(query);
  }
  function refreshVisibility() {
    filteredNodes = nodes.filter(visibleNode);
  }
  function tick() {
    const visibleIds = new Set(filteredNodes.map(n => n.id));
    if (filteredNodes.length <= FORCE_PAIRWISE_LIMIT) {
      for (let i = 0; i < filteredNodes.length; i++) {
        for (let j = i + 1; j < filteredNodes.length; j++) {
          const a = filteredNodes[i];
          const b = filteredNodes[j];
          const dx = b.x - a.x;
          const dy = b.y - a.y;
          const distance = Math.max(24, Math.hypot(dx, dy));
          const crossLobe = a.lobe !== b.lobe ? 2.6 : 1.0;
          const force = (1200 * crossLobe) / (distance * distance);
          const ux = dx / distance;
          const uy = dy / distance;
          a.vx -= ux * force;
          a.vy -= uy * force;
          b.vx += ux * force;
          b.vy += uy * force;
        }
      }
    }
    const lobeCentroids = new Map();
    for (const lobe of uniqueLobes) {
      const members = filteredNodes.filter(n => n.lobe === lobe);
      if (!members.length) continue;
      const cx = members.reduce((s, n) => s + n.x, 0) / members.length;
      const cy = members.reduce((s, n) => s + n.y, 0) / members.length;
      lobeCentroids.set(lobe, { x: cx, y: cy, members });
      for (const n of members) {
        if (n.type !== 'brain') {
          n.vx += (cx - n.x) * 0.002;
          n.vy += (cy - n.y) * 0.002;
        }
      }
    }
    // Push different lobes apart at the centroid level so their hulls never overlap.
    const lobeKeys = [...lobeCentroids.keys()];
    for (let i = 0; i < lobeKeys.length; i++) {
      for (let j = i + 1; j < lobeKeys.length; j++) {
        const a = lobeCentroids.get(lobeKeys[i]);
        const b = lobeCentroids.get(lobeKeys[j]);
        const dx = b.x - a.x;
        const dy = b.y - a.y;
        const dist = Math.max(60, Math.hypot(dx, dy));
        const aSpread = Math.max(80, Math.sqrt(a.members.length) * 50);
        const bSpread = Math.max(80, Math.sqrt(b.members.length) * 50);
        const minDist = aSpread + bSpread + 220;
        if (dist < minDist) {
          const push = (minDist - dist) * 0.030;
          const ux = dx / dist;
          const uy = dy / dist;
          for (const n of a.members) { n.vx -= ux * push; n.vy -= uy * push; }
          for (const n of b.members) { n.vx += ux * push; n.vy += uy * push; }
        }
      }
    }
    let springCount = 0;
    for (const edge of graph.edges) {
      if (!visibleIds.has(edge.source) || !visibleIds.has(edge.target)) continue;
      const touchesSelection = selectedId != null && (edge.source === selectedId || edge.target === selectedId);
      if (
        filteredNodes.length > FORCE_PAIRWISE_LIMIT &&
        edge.type !== 'parent' &&
        !touchesSelection
      ) continue;
      if (springCount > DETAIL_EDGE_LIMIT && !touchesSelection) continue;
      springCount += 1;
      const source = nodes[edge.source];
      const target = nodes[edge.target];
      const dx = target.x - source.x;
      const dy = target.y - source.y;
      const distance = Math.max(30, Math.hypot(dx, dy));
      const ideal = edge.type === 'parent' ? 80 : edge.type === 'related' ? 160 : 145;
      const force = (distance - ideal) * 0.0026;
      const ux = dx / distance;
      const uy = dy / distance;
      source.vx += ux * force;
      source.vy += uy * force;
      target.vx -= ux * force;
      target.vy -= uy * force;
    }
    for (const node of filteredNodes) {
      const anchorPull = node.type === 'brain' ? 0.015 : node.type === 'map' ? 0.014 : 0.006;
      node.vx += (node.targetX - node.x) * anchorPull;
      node.vy += (node.targetY - node.y) * anchorPull;
      if (draggingNodeId === node.id) { node.vx = 0; node.vy = 0; continue; }
      node.vx *= 0.88; node.vy *= 0.88;
      node.x += node.vx; node.y += node.vy;
    }
  }
  function draw() {
    let drawnEdges = 0;
    const visibleIds = new Set(filteredNodes.map(n => n.id));
    const query = searchInput.value.trim().toLowerCase();
    for (const edge of graph.edges) {
      if (!visibleIds.has(edge.source) || !visibleIds.has(edge.target)) continue;
      const selected = selectedId != null && (edge.source === selectedId || edge.target === selectedId);
      if (
        filteredNodes.length > FORCE_PAIRWISE_LIMIT &&
        edge.type !== 'parent' &&
        !selected
      ) continue;
      if (drawnEdges > DETAIL_EDGE_LIMIT && !selected) continue;
      drawnEdges += 1;
      const s = nodes[edge.source];
      const t = nodes[edge.target];
      ctx.save();
      ctx.strokeStyle = edge.type === 'parent' ? 'rgba(248, 199, 109, 0.42)' :
        edge.type === 'related' ? 'rgba(123, 247, 255, 0.44)' :
        edge.type === 'replaced_by' ? 'rgba(255, 138, 138, 0.55)' :
        'rgba(255, 139, 216, 0.34)';
      ctx.lineWidth = selected ? 2.5 : 1.2;
      if (edge.type === 'related') ctx.setLineDash([8, 8]);
      else if (edge.type === 'inline') ctx.setLineDash([2, 7]);
      else if (edge.type === 'replaced_by') ctx.setLineDash([2, 4]);
      else ctx.setLineDash([]);
      ctx.beginPath();
      ctx.moveTo(s.x, s.y);
      ctx.lineTo(t.x, t.y);
      ctx.stroke();
      ctx.restore();
    }
    ctx.setLineDash([]);
    for (const node of filteredNodes) {
      if (node.type === 'brain') continue;
      const isSelected = node.id === selectedId;
      const dimmed = query && !node.searchText.includes(query);
      ctx.globalAlpha = dimmed ? 0.22 : 1;
      ctx.beginPath();
      ctx.arc(node.x, node.y, node.radius, 0, Math.PI * 2);
      ctx.fillStyle = node.color;
      ctx.fill();
      if (isSelected) {
        ctx.strokeStyle = '#ffffff';
        ctx.lineWidth = 2;
        ctx.stroke();
      }
    }
    ctx.globalAlpha = 1;
  }
  function fit(instant) {
    const rect = stage.getBoundingClientRect();
    if (!filteredNodes.length) {
      camera.x = 0; camera.y = 0; camera.scale = 1;
      requestDraw();
      return;
    }
    const padding = 140;
    const xs = filteredNodes.map(n => n.targetX != null ? n.targetX : n.x);
    const ys = filteredNodes.map(n => n.targetY != null ? n.targetY : n.y);
    const minX = Math.min(...xs) - padding;
    const maxX = Math.max(...xs) + padding;
    const minY = Math.min(...ys) - padding;
    const maxY = Math.max(...ys) + padding;
    const w = Math.max(1, maxX - minX);
    const h = Math.max(1, maxY - minY);
    const scale = Math.min(rect.width / w, rect.height / h) * 0.80;
    const clampedScale = Math.min(2.4, Math.max(0.42, scale));
    const cx = (minX + maxX) / 2;
    const cy = (minY + maxY) / 2;
    const tx = rect.width / 2 - cx * clampedScale;
    const ty = rect.height / 2 - cy * clampedScale;
    if (instant) {
      camera.x = tx; camera.y = ty; camera.scale = clampedScale;
      requestDraw();
    } else {
      animateCamera(tx, ty, clampedScale, 280);
    }
  }
  function hitTest(worldX, worldY) {
    let best = null;
    let bestDist = Infinity;
    for (const node of filteredNodes) {
      const d = Math.hypot(node.x - worldX, node.y - worldY);
      if (d <= node.radius + 8 && d < bestDist) {
        bestDist = d;
        best = node;
      }
    }
    return best ? { kind: 'neuron', id: best.id } : null;
  }
  function handleClick(worldX, worldY) {
    const hit = hitTest(worldX, worldY);
    if (hit) {
      const node = graph.nodes.find(n => n.id === hit.id);
      if (node) {
        selectedId = node.id;
        openModal(node);
      }
    }
  }
  buildAnchors(stage.getBoundingClientRect().width, stage.getBoundingClientRect().height);
  nodes = initializeNodes();
  refreshVisibility();
  legacyForce = {
    initialized: true,
    nodes,
    get filteredNodes() { return filteredNodes; },
    tick,
    draw,
    fit,
    hitTest,
    handleClick,
    refresh: refreshVisibility,
    buildAnchors: (w, h) => buildAnchors(w, h),
  };
}

// ============================================================
// Wire up controls
// ============================================================
searchInput.addEventListener('input', () => {
  refreshSearch();
  if (legacyForce) legacyForce.refresh();
  requestDraw();
});
searchInput.addEventListener('keydown', event => {
  if (event.key === 'Enter') {
    event.preventDefault();
    searchEnterJump();
  }
});
for (const button of modeButtons) {
  button.addEventListener('click', () => {
    const m = button.dataset.stageMode;
    if (button.disabled) return;
    if (m === 'lobe' && !activeLobe) return;
    if (m === 'sublobe' && !activeSublobe) return;
    setStageMode(m, activeLobe, activeSublobe);
  });
}
document.getElementById('btn-reset').addEventListener('click', () => {
  searchInput.value = '';
  hiddenLobes.clear();
  selectedId = null;
  activeLobe = null;
  activeSublobe = null;
  renderLobeFilter();
  refreshSearch();
  setStageMode('brain', null, null, { instant: true });
});
document.getElementById('btn-fit').addEventListener('click', () => {
  if (stageMode === 'force' && legacyForce) legacyForce.fit(false);
  else animateCamera(0, 0, 1, 240);
});

// Panel collapse — toggle a class on the body grid; show/hide expand button.
function togglePanel(side) {
  const body = document.querySelector('.body');
  const cls = side + '-collapsed';
  const collapsed = body.classList.toggle(cls);
  const expandBtn = document.getElementById('expand-' + side);
  if (expandBtn) expandBtn.classList.toggle('visible', collapsed);
  requestAnimationFrame(() => {
    resize();
    requestDraw();
  });
}
document.getElementById('collapse-left').addEventListener('click', () => togglePanel('left'));
document.getElementById('collapse-right').addEventListener('click', () => togglePanel('right'));
document.getElementById('expand-left').addEventListener('click', () => togglePanel('left'));
document.getElementById('expand-right').addEventListener('click', () => togglePanel('right'));

document.getElementById('modal-back').addEventListener('click', () => {
  if (navIndex > 0) {
    navIndex--;
    const node = graph.nodes.find(n => n.id === navHistory[navIndex]);
    if (node) { selectedId = node.id; openModal(node); }
  }
});
document.getElementById('modal-forward').addEventListener('click', () => {
  if (navIndex < navHistory.length - 1) {
    navIndex++;
    const node = graph.nodes.find(n => n.id === navHistory[navIndex]);
    if (node) { selectedId = node.id; openModal(node); }
  }
});
document.getElementById('modal-close').addEventListener('click', () => {
  document.getElementById('content-modal').style.display = 'none';
});
document.getElementById('content-modal').addEventListener('click', event => {
  if (event.target === event.currentTarget) event.currentTarget.style.display = 'none';
});
document.addEventListener('keydown', event => {
  if (event.key === 'Escape') {
    document.getElementById('content-modal').style.display = 'none';
  }
  if (event.key === '/' && event.target !== searchInput) {
    event.preventDefault();
    searchInput.focus();
    searchInput.select();
  }
  if ((event.key === 'e' || event.key === 'E') && event.target !== searchInput) {
    if (stageMode === 'force') setStageMode('brain');
    else setStageMode('force');
  }
});

// ============================================================
// Bootstrap
// ============================================================
resize();
addEventListener('resize', resize);
renderLobeFilter();
renderRecent();
renderFileTree(null, 'panel-tree');
renderBreadcrumb();
setStageMode('brain', null, null, { instant: true });
loop();
"""
