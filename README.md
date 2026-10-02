# plan-shard

Split monolithic AI-generated plans into executable shards.

Claude Code's Plan Mode (and similar agent planners) produce one giant markdown
plan. Change a single bullet and the whole document gets rewritten. plan-shard
cuts the monolith into numbered `PLAN_001.md` / `PLAN_002.md` / … shards, each
carrying its dependency order and resume index in frontmatter — so feedback can
be applied to **one shard at a time** without regenerating everything.

Zero dependencies. Python 3.9+. Stdlib only.

## Install

```bash
pip install plan-shard
```

## Usage

**1. Shard a plan**

```bash
plan-shard shard plan.md -o shards/
```

Produces:

```
shards/
  PLAN_001.md   # preamble / overview
  PLAN_002.md
  PLAN_003.md
  ...
  PLAN_INDEX.md # table of all shards
```

Each shard starts with frontmatter:

```yaml
---
shard: 3
total: 6
title: "Step 1: Add the Redis client"
source: plan.md
depends_on: [2, 4]
resume_index: 3
status: pending
revisions: []
---
```

**2. Apply feedback to one shard**

```bash
plan-shard feedback shards/PLAN_003.md \
  --old "app/cache.py" \
  --new "app/caching.py" \
  --note "rename module"
```

Only that file is modified; every other shard stays byte-identical. The change
is logged in the shard's `revisions` list. If the pattern isn't found, nothing
is written and the command fails loudly.

**3. Track progress**

```bash
plan-shard list shards/     # table of shards, deps, status
plan-shard done shards/PLAN_003.md   # mark done ( --undo to revert )
plan-shard resume shards/   # print the next pending shard
```

**Options**

- `shard --level 3` — split on `###` headings instead of `##` (default: 2)
- `feedback --all` — replace all occurrences (default: first only, with a warning)

## How splitting works

- Every heading at the chosen level starts a new shard.
- Text before the first heading becomes shard 1 (titled from the `# H1`, or
  "Overview"); if there is no preamble, the first heading is shard 1.
- `depends_on` is sequential (each shard depends on the previous one) plus any
  `PLAN_XXX` references found in the shard's own body.
- `PLAN_INDEX.md` lists every shard with its title, dependencies, and status.

## Honest limitations

- **Splitting is heuristic.** It keys off markdown heading levels. Plans that
  don't use headings (or use them inconsistently) will slice badly — a
  heading-free plan becomes a single shard, and deeply nested plans may need
  `--level 3` or manual adjustment.
- **`--feedback` is text-level, not semantic.** It does exact string
  replacement inside one shard. It won't reword surrounding prose, update
  cross-shard references, or understand what your change *means*. If a rename
  ripples across shards, apply feedback to each affected shard yourself.
- **Dependency detection is shallow.** `depends_on` combines sequential order
  with literal `PLAN_XXX` mentions. It doesn't parse "after step 2" prose or
  build a real dependency graph.
- **No concurrency safety.** Shard files are plain markdown; two processes
  editing the same shard can clobber each other (writes are atomic per file,
  but there's no locking).
- **Frontmatter is a small YAML subset**, not full YAML. Hand-editing exotic
  YAML inside the frontmatter block may not round-trip.

## Development

```bash
python -m pytest tests/ -q   # 24 tests
```

## License

MIT
