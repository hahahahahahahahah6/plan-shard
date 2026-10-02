"""End-to-end CLI tests: shard -> feedback -> done -> resume."""
import os

import pytest

from plan_shard.cli import main

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
PLAN = os.path.join(FIXTURES, "plan_sample.md")


def test_cli_full_flow(tmp_path, capsys):
    out = str(tmp_path / "shards")
    assert main(["shard", PLAN, "-o", out]) == 0
    printed = capsys.readouterr().out
    assert "split into 6 shards" in printed

    assert main(["list", out]) == 0
    assert "PLAN_003.md" in capsys.readouterr().out

    target = os.path.join(out, "PLAN_003.md")
    assert main(["feedback", target, "--old", "app/cache.py",
                 "--new", "app/caching.py", "--note", "rename"]) == 0

    assert main(["done", target]) == 0
    assert main(["resume", out]) == 0
    assert "PLAN_001.md" in capsys.readouterr().out  # 001 still pending


def test_cli_feedback_missing_pattern(tmp_path, capsys):
    out = str(tmp_path / "shards")
    assert main(["shard", PLAN, "-o", out]) == 0
    target = os.path.join(out, "PLAN_002.md")
    assert main(["feedback", target, "--old", "nope-not-here", "--new", "x"]) == 1
    assert "not found" in capsys.readouterr().err


def test_cli_shard_empty_plan(tmp_path, capsys):
    empty = tmp_path / "empty.md"
    empty.write_text("\n", encoding="utf-8")
    assert main(["shard", str(empty), "-o", str(tmp_path / "o")]) == 1
    assert "empty" in capsys.readouterr().err
