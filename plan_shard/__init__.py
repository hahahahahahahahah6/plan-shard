"""plan-shard: split monolithic AI-generated plans into executable shards.

Claude Code's Plan Mode (and similar agent planners) tend to produce one giant
monolithic markdown plan. Change one bullet and the whole thing gets rewritten.
plan-shard cuts the monolith into numbered PLAN_001.md / PLAN_002.md / ...
shards, each carrying its dependency order and resume index in frontmatter, so
feedback can be applied to a single shard without regenerating everything.
"""

__version__ = "0.1.0"

import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

HEADING_RE = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")
SHARD_FILE_RE = re.compile(r"^PLAN_(\d{3})\.md$")
PLAN_REF_RE = re.compile(r"PLAN_(\d{1,3})")
FENCE = "---"


class PlanShardError(Exception):
    """Base error for plan-shard."""


class FeedbackError(PlanShardError):
    """Raised when --feedback cannot be applied."""


@dataclass
class Shard:
    index: int  # 1-based
    total: int = 0
    title: str = ""
    body: str = ""
    source: str = ""
    depends_on: list = field(default_factory=list)
    resume_index: int = 0
    status: str = "pending"
    revisions: list = field(default_factory=list)


def _utcnow():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------- frontmatter

def dump_frontmatter(shard):
    """Serialize a Shard's metadata to a YAML-ish frontmatter block.

    We emit (and parse) a deliberately small subset: scalar ``key: value``
    lines, integer lists like ``depends_on: [1, 2]``, and a ``revisions:``
    block list. This keeps plan-shard dependency-free.
    """
    lines = [FENCE]
    lines.append("shard: %d" % shard.index)
    lines.append("total: %d" % shard.total)
    lines.append("title: %s" % _quote(shard.title))
    lines.append("source: %s" % _quote(shard.source))
    lines.append("depends_on: [%s]" % ", ".join(str(d) for d in shard.depends_on))
    lines.append("resume_index: %d" % shard.resume_index)
    lines.append("status: %s" % shard.status)
    if shard.revisions:
        lines.append("revisions:")
        for rev in shard.revisions:
            lines.append("  - %s" % rev)
    else:
        lines.append("revisions: []")
    lines.append(FENCE)
    return "\n".join(lines) + "\n"


def _quote(value):
    value = str(value).replace('"', "'")
    if re.search(r"[:#\[\]{}]", value) or value != value.strip() or not value:
        return '"%s"' % value
    return value


def _unquote(value):
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    return value


def parse_frontmatter(text):
    """Split ``text`` into (meta dict, body). Missing frontmatter -> ({}, text)."""
    if not text.startswith(FENCE + "\n"):
        return {}, text
    lines = text.split("\n")
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == FENCE:
            end = i
            break
    if end is None:
        return {}, text
    meta = {}
    current_list = None
    for line in lines[1:end]:
        if not line.strip():
            continue
        if line.startswith("  - ") and current_list is not None:
            meta[current_list].append(line[4:].strip())
            continue
        if ":" not in line:
            current_list = None
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        if value == "":
            # start of a block list
            meta[key] = []
            current_list = key
        elif value == "[]":
            meta[key] = []
            current_list = None
        elif value.startswith("[") and value.endswith("]"):
            inner = value[1:-1].strip()
            items = []
            if inner:
                for part in inner.split(","):
                    part = part.strip()
                    items.append(int(part) if re.fullmatch(r"\d+", part) else _unquote(part))
            meta[key] = items
            current_list = None
        elif re.fullmatch(r"\d+", value):
            meta[key] = int(value)
            current_list = None
        else:
            meta[key] = _unquote(value)
            current_list = None
    body = "\n".join(lines[end + 1:])
    return meta, body


def _meta_to_shard(meta, body, index):
    return Shard(
        index=int(meta.get("shard", index)),
        total=int(meta.get("total", 0)),
        title=str(meta.get("title", "")),
        body=body,
        source=str(meta.get("source", "")),
        depends_on=list(meta.get("depends_on", [])),
        resume_index=int(meta.get("resume_index", index)),
        status=str(meta.get("status", "pending")),
        revisions=list(meta.get("revisions", [])),
    )


# ---------------------------------------------------------------- splitting

def split_plan(text, source_name="plan.md", level=2):
    """Split a monolithic plan into Shard objects.

    Heuristic: every heading with exactly ``level`` hashes starts a new shard.
    Text before the first heading becomes shard 1 (titled from the H1, or
    "Overview") when non-empty; otherwise the first heading starts shard 1.
    Each shard depends on the previous one, plus any PLAN_XXX it references.
    """
    lines = text.split("\n")
    # (line_index, title) for headings at exactly `level`
    heads = []
    for i, line in enumerate(lines):
        m = HEADING_RE.match(line)
        if m and len(m.group(1)) == level:
            heads.append((i, m.group(2).strip()))

    sections = []  # (title, body_text)
    if not heads:
        title = _first_h1(lines) or "Full plan"
        sections.append((title, text.strip() + "\n"))
    else:
        first_head_line = heads[0][0]
        preamble = "\n".join(lines[:first_head_line]).strip()
        if preamble:
            title = _first_h1(preamble.split("\n")) or "Overview"
            sections.append((title, preamble + "\n"))
        for n, (line_i, title) in enumerate(heads):
            end = heads[n + 1][0] if n + 1 < len(heads) else len(lines)
            body = "\n".join(lines[line_i:end]).strip() + "\n"
            sections.append((title, body))

    total = len(sections)
    shards = []
    for i, (title, body) in enumerate(sections, start=1):
        deps = [i - 1] if i > 1 else []
        for ref in PLAN_REF_RE.findall(body):
            d = int(ref)
            if d != i and d not in deps and 1 <= d <= 999:
                deps.append(d)
        deps.sort()
        shards.append(Shard(
            index=i,
            total=total,
            title=title,
            body=body,
            source=source_name,
            depends_on=deps,
            resume_index=i,
        ))
    return shards


def _first_h1(lines):
    for line in lines:
        m = HEADING_RE.match(line)
        if m and len(m.group(1)) == 1:
            return m.group(2).strip()
    return ""


def shard_filename(index):
    return "PLAN_%03d.md" % index


def write_shards(shards, out_dir):
    """Write shards + PLAN_INDEX.md into out_dir. Returns list of paths."""
    os.makedirs(out_dir, exist_ok=True)
    paths = []
    for shard in shards:
        path = os.path.join(out_dir, shard_filename(shard.index))
        _atomic_write(path, dump_frontmatter(shard) + shard.body)
        paths.append(path)
    index_path = os.path.join(out_dir, "PLAN_INDEX.md")
    _atomic_write(index_path, render_index(shards))
    paths.append(index_path)
    return paths


def render_index(shards):
    lines = ["# Plan Index", ""]
    if shards:
        lines.append("Source: %s" % shards[0].source)
        lines.append("Shards: %d" % len(shards))
        lines.append("Generated: %s" % _utcnow())
        lines.append("")
    lines.append("| # | File | Title | Depends on | Status |")
    lines.append("|---|------|-------|------------|--------|")
    for s in shards:
        deps = ", ".join("PLAN_%03d" % d for d in s.depends_on) or "-"
        lines.append("| %d | %s | %s | %s | %s |" % (
            s.index, shard_filename(s.index), s.title, deps, s.status))
    lines.append("")
    lines.append("Resume: run `plan-shard resume <dir>` for the next pending shard.")
    lines.append("")
    return "\n".join(lines)


def _atomic_write(path, text):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


# ---------------------------------------------------------------- shard ops

def read_shard(path):
    with open(path, encoding="utf-8") as f:
        text = f.read()
    meta, body = parse_frontmatter(text)
    m = SHARD_FILE_RE.match(os.path.basename(path))
    index = int(m.group(1)) if m else int(meta.get("shard", 0))
    return _meta_to_shard(meta, body, index), path


def iter_shard_files(shard_dir):
    files = []
    for name in sorted(os.listdir(shard_dir)):
        if SHARD_FILE_RE.match(name):
            files.append(os.path.join(shard_dir, name))
    return files


def apply_feedback(path, old, new, note="", replace_all=False):
    """Apply a targeted text replacement to ONE shard file.

    Only ``path`` is modified; every other file in the directory is untouched.
    The change is logged in the shard's frontmatter ``revisions`` list.
    Raises FeedbackError if ``old`` is not found.
    """
    shard, _ = read_shard(path)
    count = shard.body.count(old)
    if count == 0:
        raise FeedbackError("pattern not found in %s" % os.path.basename(path))
    if replace_all:
        shard.body = shard.body.replace(old, new)
        replaced = count
    else:
        shard.body = shard.body.replace(old, new, 1)
        replaced = 1
    stamp = _utcnow()
    entry = "%s | %s" % (stamp, note or "feedback: replaced %d occurrence(s)" % replaced)
    shard.revisions.append(entry)
    _atomic_write(path, dump_frontmatter(shard) + shard.body)
    return {"replacements": replaced, "occurrences": count, "multiple": count > 1}


def mark_done(path, done=True):
    shard, _ = read_shard(path)
    shard.status = "done" if done else "pending"
    _atomic_write(path, dump_frontmatter(shard) + shard.body)
    return shard.status


def list_shards(shard_dir):
    rows = []
    for path in iter_shard_files(shard_dir):
        shard, _ = read_shard(path)
        rows.append(shard)
    return rows


def resume_point(shard_dir):
    """Path of the first shard whose status is not done, or None."""
    for path in iter_shard_files(shard_dir):
        shard, _ = read_shard(path)
        if shard.status != "done":
            return path
    return None
