"""Feedback tests: targeted single-shard edits must not touch other shards."""
import os

import pytest

from plan_shard import (
    FeedbackError,
    apply_feedback,
    list_shards,
    mark_done,
    parse_frontmatter,
    read_shard,
    resume_point,
    split_plan,
    write_shards,
)

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


@pytest.fixture
def shard_dir(tmp_path):
    with open(os.path.join(FIXTURES, "plan_sample.md"), encoding="utf-8") as f:
        text = f.read()
    shards = split_plan(text, source_name="plan_sample.md")
    write_shards(shards, str(tmp_path))
    return str(tmp_path)


def _snapshot(directory):
    snap = {}
    for name in sorted(os.listdir(directory)):
        if name == "PLAN_INDEX.md":
            continue
        with open(os.path.join(directory, name), encoding="utf-8") as f:
            snap[name] = f.read()
    return snap


def test_feedback_replaces_only_target_shard(shard_dir):
    before = _snapshot(shard_dir)
    target = os.path.join(shard_dir, "PLAN_003.md")
    result = apply_feedback(target, old="app/cache.py", new="app/caching.py",
                            note="rename module")
    assert result["replacements"] == 1
    after = _snapshot(shard_dir)
    for name in before:
        if name == "PLAN_003.md":
            assert "app/caching.py" in after[name]
            assert "app/cache.py" not in after[name].split("---", 2)[-1]
        else:
            assert after[name] == before[name], "untargeted shard modified: %s" % name


def test_feedback_appends_revision_log(shard_dir):
    target = os.path.join(shard_dir, "PLAN_004.md")
    apply_feedback(target, old="reporting endpoints", new="reporting routes",
                   note="wording fix")
    shard, _ = read_shard(target)
    assert len(shard.revisions) == 1
    assert "wording fix" in shard.revisions[0]
    # frontmatter fields preserved
    assert shard.index == 4
    assert shard.total == 6
    assert shard.title == "Step 2: Cache decorator"
    assert shard.status == "pending"


def test_feedback_pattern_not_found_raises(shard_dir):
    target = os.path.join(shard_dir, "PLAN_002.md")
    before = _snapshot(shard_dir)
    with pytest.raises(FeedbackError):
        apply_feedback(target, old="this text does not exist", new="x")
    assert _snapshot(shard_dir) == before  # nothing written on failure


def test_feedback_multiple_occurrences_first_only(shard_dir):
    target = os.path.join(shard_dir, "PLAN_003.md")
    # "the" appears 3x in the Step 1 body (heading + "the `redis`" + "the decorator")
    result = apply_feedback(target, old="the", new="THE")
    assert result["multiple"] is True
    assert result["occurrences"] == 3
    assert result["replacements"] == 1
    shard, _ = read_shard(target)
    assert shard.body.count("THE") == 1


def test_feedback_replace_all(shard_dir):
    target = os.path.join(shard_dir, "PLAN_003.md")
    result = apply_feedback(target, old="the", new="THE", replace_all=True)
    assert result["replacements"] == result["occurrences"] == 3
    shard, _ = read_shard(target)
    assert "the `redis`" not in shard.body
    assert "the decorator" not in shard.body
    assert "Add the Redis" not in shard.body


def test_feedback_does_not_touch_index(shard_dir):
    index_path = os.path.join(shard_dir, "PLAN_INDEX.md")
    with open(index_path, encoding="utf-8") as f:
        before = f.read()
    apply_feedback(os.path.join(shard_dir, "PLAN_005.md"),
                   old="Invalidate on writes.", new="Invalidate on writes via events.")
    with open(index_path, encoding="utf-8") as f:
        assert f.read() == before


def test_done_and_resume(shard_dir):
    assert resume_point(shard_dir).endswith("PLAN_001.md")
    mark_done(os.path.join(shard_dir, "PLAN_001.md"))
    mark_done(os.path.join(shard_dir, "PLAN_002.md"))
    nxt = resume_point(shard_dir)
    assert nxt.endswith("PLAN_003.md")
    shard, _ = read_shard(os.path.join(shard_dir, "PLAN_001.md"))
    assert shard.status == "done"
    # undo
    mark_done(os.path.join(shard_dir, "PLAN_001.md"), done=False)
    assert resume_point(shard_dir).endswith("PLAN_001.md")


def test_resume_all_done(shard_dir):
    for s in list_shards(shard_dir):
        mark_done(os.path.join(shard_dir, "PLAN_%03d.md" % s.index))
    assert resume_point(shard_dir) is None


def test_list_shards(shard_dir):
    rows = list_shards(shard_dir)
    assert len(rows) == 6
    assert [r.index for r in rows] == [1, 2, 3, 4, 5, 6]
    assert all(r.status == "pending" for r in rows)


def test_feedback_preserves_other_frontmatter_on_reread(shard_dir):
    target = os.path.join(shard_dir, "PLAN_003.md")
    apply_feedback(target, old="Connection settings", new="Conn settings")
    with open(target, encoding="utf-8") as f:
        meta, _ = parse_frontmatter(f.read())
    assert meta["depends_on"] == [2, 4]
    assert meta["resume_index"] == 3
    assert meta["source"] == "plan_sample.md"
