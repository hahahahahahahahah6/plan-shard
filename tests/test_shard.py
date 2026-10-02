"""Slicing tests: split a fixture monolith plan into shards and assert structure."""
import os

import pytest

from plan_shard import (
    SHARD_FILE_RE,
    parse_frontmatter,
    render_index,
    split_plan,
    write_shards,
)

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


@pytest.fixture
def plan_text():
    with open(os.path.join(FIXTURES, "plan_sample.md"), encoding="utf-8") as f:
        return f.read()


@pytest.fixture
def shards(plan_text):
    return split_plan(plan_text, source_name="plan_sample.md")


def test_split_count_and_filenames(shards, tmp_path):
    # preamble + 5 H2 sections = 6 shards
    assert len(shards) == 6
    paths = write_shards(shards, str(tmp_path))
    names = sorted(os.path.basename(p) for p in paths)
    assert names == ["PLAN_001.md", "PLAN_002.md", "PLAN_003.md",
                     "PLAN_004.md", "PLAN_005.md", "PLAN_006.md",
                     "PLAN_INDEX.md"]
    for p in paths:
        assert os.path.isfile(p)


def test_preamble_becomes_first_shard(shards):
    first = shards[0]
    assert first.index == 1
    assert first.title == "Plan: Add Redis caching to the API"
    assert "Estimated effort: 2 days." in first.body


def test_section_titles(shards):
    titles = [s.title for s in shards]
    assert titles == [
        "Plan: Add Redis caching to the API",
        "Overview",
        "Step 1: Add the Redis client",
        "Step 2: Cache decorator",
        "Step 3: Wire up endpoints",
        "Acceptance Criteria",
    ]


def test_frontmatter_fields(shards, tmp_path):
    write_shards(shards, str(tmp_path))
    with open(os.path.join(str(tmp_path), "PLAN_003.md"), encoding="utf-8") as f:
        meta, body = parse_frontmatter(f.read())
    assert meta["shard"] == 3
    assert meta["total"] == 6
    assert meta["title"] == "Step 1: Add the Redis client"
    assert meta["source"] == "plan_sample.md"
    assert meta["resume_index"] == 3
    assert meta["status"] == "pending"
    assert meta["revisions"] == []
    assert "app/cache.py" in body  # body preserved verbatim


def test_depends_on_sequential_and_refs(shards):
    by_index = {s.index: s for s in shards}
    assert by_index[1].depends_on == []
    assert by_index[2].depends_on == [1]
    # Step 1 body references PLAN_004 -> depends on previous (2) + ref (4)
    assert by_index[3].depends_on == [2, 4]
    # Step 2 body references PLAN_002 -> previous (3) + ref (2)
    assert by_index[4].depends_on == [2, 3]


def test_no_preamble_plan():
    text = "## Alpha\nbody a\n\n## Beta\nbody b\n"
    shards = split_plan(text, source_name="p.md")
    assert len(shards) == 2
    assert shards[0].title == "Alpha"
    assert shards[0].depends_on == []


def test_no_headings_single_shard():
    text = "Just some notes.\nNo headings at all.\n"
    shards = split_plan(text, source_name="p.md")
    assert len(shards) == 1
    assert shards[0].title == "Full plan"
    assert shards[0].depends_on == []
    assert "Just some notes." in shards[0].body


def test_level3_splitting():
    text = ("## Big\n\n### a\ntext a\n\n### b\ntext b\n")
    shards = split_plan(text, source_name="p.md", level=3)
    # the "## Big" preamble (non-empty) becomes its own leading shard
    assert [s.title for s in shards] == ["Overview", "a", "b"]
    assert "## Big" in shards[0].body


def test_index_file_contents(shards, tmp_path):
    write_shards(shards, str(tmp_path))
    with open(os.path.join(str(tmp_path), "PLAN_INDEX.md"), encoding="utf-8") as f:
        index = f.read()
    assert "Shards: 6" in index
    for i in range(1, 7):
        assert "PLAN_%03d" % i in index
    assert "Acceptance Criteria" in index


def test_render_index_standalone(shards):
    index = render_index(shards)
    assert index.startswith("# Plan Index")
    assert "| 1 | PLAN_001.md |" in index


def test_shard_filenames_match_pattern(shards, tmp_path):
    paths = write_shards(shards, str(tmp_path))
    for p in paths[:-1]:  # skip PLAN_INDEX.md
        assert SHARD_FILE_RE.match(os.path.basename(p))
