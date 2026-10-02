"""Command-line interface for plan-shard."""

import argparse
import os
import sys

from . import (
    FeedbackError,
    PlanShardError,
    apply_feedback,
    list_shards,
    mark_done,
    read_shard,
    resume_point,
    shard_filename,
    split_plan,
    write_shards,
    __version__,
)


def cmd_shard(args):
    with open(args.plan, encoding="utf-8") as f:
        text = f.read()
    if not text.strip():
        print("error: plan file is empty", file=sys.stderr)
        return 1
    shards = split_plan(text, source_name=os.path.basename(args.plan), level=args.level)
    out_dir = args.output or os.path.splitext(args.plan)[0] + "_shards"
    paths = write_shards(shards, out_dir)
    print("split into %d shards in %s/" % (len(shards), out_dir))
    for shard in shards:
        print("  %s  %s" % (shard_filename(shard.index), shard.title))
    print("index: %s" % paths[-1])
    return 0


def cmd_feedback(args):
    try:
        result = apply_feedback(args.shard, args.old, args.new,
                                note=args.note or "", replace_all=args.all)
    except FeedbackError as e:
        print("error: %s" % e, file=sys.stderr)
        return 1
    except (OSError, PlanShardError) as e:
        print("error: %s" % e, file=sys.stderr)
        return 1
    print("updated %s: %d replacement(s)" % (args.shard, result["replacements"]))
    if result["multiple"] and not args.all:
        print("note: pattern occurred %d times; only the first was replaced "
              "(use --all to replace all)" % result["occurrences"])
    print("other shards untouched; revision logged in frontmatter.")
    return 0


def cmd_list(args):
    rows = list_shards(args.dir)
    if not rows:
        print("no shards found in %s" % args.dir)
        return 0
    print("%-12s %-6s %-40s %s" % ("FILE", "STATUS", "TITLE", "DEPENDS ON"))
    for s in rows:
        deps = ",".join(str(d) for d in s.depends_on) or "-"
        print("%-12s %-6s %-40s %s" % (
            shard_filename(s.index), s.status, s.title[:40], deps))
    return 0


def cmd_done(args):
    try:
        status = mark_done(args.shard, done=not args.undo)
    except (OSError, PlanShardError) as e:
        print("error: %s" % e, file=sys.stderr)
        return 1
    print("%s marked %s" % (args.shard, status))
    return 0


def cmd_resume(args):
    nxt = resume_point(args.dir)
    if nxt is None:
        print("all shards done - nothing to resume")
        return 0
    shard, _ = read_shard(nxt)
    print("resume at %s" % nxt)
    print("  shard %d/%d: %s" % (shard.index, shard.total, shard.title))
    return 0


def build_parser():
    p = argparse.ArgumentParser(
        prog="plan-shard",
        description="Split monolithic AI plans into executable shards; "
                    "apply targeted feedback to one shard at a time.")
    p.add_argument("--version", action="version", version="plan-shard " + __version__)
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("shard", help="split a plan markdown into PLAN_*.md shards")
    s.add_argument("plan", help="monolithic plan markdown file")
    s.add_argument("-o", "--output", default=None,
                   help="output directory (default: <plan>_shards)")
    s.add_argument("--level", type=int, default=2, choices=[2, 3, 4],
                   help="heading level to split on (default: 2)")
    s.set_defaults(func=cmd_shard)

    f = sub.add_parser("feedback",
                       help="apply a targeted text change to ONE shard only")
    f.add_argument("shard", help="shard file, e.g. shards/PLAN_003.md")
    f.add_argument("--old", required=True, help="exact text to replace")
    f.add_argument("--new", required=True, help="replacement text")
    f.add_argument("--note", default="", help="revision note for the log")
    f.add_argument("--all", action="store_true",
                   help="replace all occurrences (default: first only)")
    f.set_defaults(func=cmd_feedback)

    l = sub.add_parser("list", help="list shards in a directory")
    l.add_argument("dir", help="shard directory")
    l.set_defaults(func=cmd_list)

    d = sub.add_parser("done", help="mark a shard done (or --undo)")
    d.add_argument("shard", help="shard file")
    d.add_argument("--undo", action="store_true", help="mark back to pending")
    d.set_defaults(func=cmd_done)

    r = sub.add_parser("resume", help="print the next pending shard")
    r.add_argument("dir", help="shard directory")
    r.set_defaults(func=cmd_resume)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
