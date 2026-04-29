# Migration Guide

This document records breaking changes between kluris versions and the
manual cleanup users may want to perform after upgrading. Existing
installations keep working without action — the cleanup is optional.

## 2.15.x → 2.16.0

Kluris 2.16.0 dropped four CLI commands (`clone`, `push`, `pull`, `branch`),
the zip path on `register`, and three persisted config fields
(`BrainEntry.type`, `BrainEntry.repo`, `BrainConfig.git.commit_prefix`).
Existing config files keep working — Pydantic ignores the unused keys at
runtime — but if you want them gone from disk, here's what to remove by
hand.

### Workflow change

The four removed commands were thin wrappers over `git`. Replacements:

| Before | After |
|---|---|
| `kluris clone <url>` | `git clone <url> <path>` then `kluris register <path>` |
| `kluris push -m "msg"` | `git -C <brain-path> add -A && git -C <brain-path> commit -m "msg" && git -C <brain-path> push` |
| `kluris pull` | `git -C <brain-path> pull` |
| `kluris branch <name>` | `git -C <brain-path> checkout [-b] <name>` |
| `kluris register foo.zip` | `unzip foo.zip -d <path>` then `kluris register <path>` |

### Optional: remove dead keys from `~/.kluris/config.yml`

Edit `~/.kluris/config.yml`. For each brain entry, delete the `type:` and
`repo:` lines if they exist. Before:

```yaml
brains:
  my-brain:
    path: /home/me/brains/my-brain
    description: My knowledge base
    type: product-group         # ← delete this line
    repo: git@github.com:...    # ← delete this line
```

After:

```yaml
brains:
  my-brain:
    path: /home/me/brains/my-brain
    description: My knowledge base
```

### Optional: remove dead keys from each `kluris.yml`

Each brain has its own `kluris.yml` at the brain root (gitignored). Open it
and delete the `git:` block if present. Before:

```yaml
name: my-brain
description: My knowledge base
git:
  commit_prefix: "brain:"     # ← delete the entire git: block
agents:
  commands_for: [claude, cursor, ...]
```

After:

```yaml
name: my-brain
description: My knowledge base
agents:
  commands_for: [claude, cursor, ...]
```

### How to find every `kluris.yml`

```bash
kluris list --json | jq -r '.brains[].path' | xargs -I{} echo {}/kluris.yml
```

### Verify

```bash
kluris list                                # should still show every brain
kluris wake-up --brain <name> --json       # should still produce a snapshot
```

Both commands produce the same output before and after the cleanup. The
removal is purely cosmetic — the runtime ignored those keys either way.

## kluris ≤ 1.6.x → 2.x

The legacy `default_brain` field at the top of `~/.kluris/config.yml` is
silently ignored on read (Pydantic's default behavior). The `kluris use
<name>` command was removed; pass `--brain NAME` per call or pick
interactively. No further migration is required.
