import argparse
import json
import logging
import re
import sys
import time
from pathlib import Path

from duplicates.dupfinder import DupFinder, FileEntry


def _natural_key(text: str | Path) -> list[int | str]:
    parts = re.split("([0-9]+)", str(text))
    return [int(p) if p.isdigit() else p.lower() for p in parts]


def _path_sort(items: list[FileEntry]) -> list[FileEntry]:
    return sorted(items, key=lambda f: _natural_key(f.path))


def _dup_sort(items: list[FileEntry]) -> list[FileEntry]:
    return sorted(items, key=lambda f: (f.age, _natural_key(f.path)))


def _count(n: int, singular: str, plural: str) -> str:
    return f"{n} {singular if n == 1 else plural}"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Search for identical files.")
    parser.add_argument("path", type=Path, nargs="+", help="Paths to scan.")
    parser.add_argument(
        "--follow",
        action="store_true",
        help="Follow symlinks (ignored by default).",
    )
    parser.add_argument(
        "--hidden",
        action="store_true",
        help="Include hidden files and directories (ignored by default).",
    )
    parser.add_argument(
        "--one-file-system",
        action="store_true",
        help="Do not enter mounted file systems.",
    )
    parser.add_argument(
        "--unique",
        action="store_true",
        help="Also include unique files in the output.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print more information.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Print debug output.",
    )
    output = parser.add_mutually_exclusive_group()
    output.add_argument(
        "--json",
        action="store_true",
        help="Emit results as JSON on stdout, including a statistics block.",
    )
    output.add_argument(
        "--dups-only",
        action="store_true",
        help="Print only duplicates, no uniques and no originals, zero-delimited.",
    )
    output.add_argument(
        "--summary",
        action="store_true",
        help="Print the final summary line.",
    )
    return parser


def _configure_logging(verbose: bool, debug: bool) -> None:
    if debug:
        level = logging.DEBUG
    elif verbose:
        level = logging.INFO
    else:
        level = logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(levelname)s: %(message)s",
        stream=sys.stderr,
    )


def _entry_dict(f: FileEntry) -> dict[str, object]:
    return {"path": str(f.path), "size": f.size, "age": f.age}


def _build_json_result(
    *,
    scanned_paths: list[Path],
    uniq: list[FileEntry],
    dups: list[list[FileEntry]],
    unreadable: list[FileEntry],
    include_unique: bool,
    elapsed: float,
) -> dict[str, object]:
    dup_blocks: list[dict[str, object]] = []
    dup_copies = 0
    dup_bytes = 0
    for group in dups:
        sorted_group = _dup_sort(group)
        first = sorted_group[0]
        # All files in a duplicate group share the same content, hence the
        # same hash and size — record them once at the group level.
        dup_blocks.append(
            {
                "hash": f"sha256:{first.hash}" if first.hash else None,
                "size": first.size,
                "files": [{"path": str(f.path), "age": f.age} for f in sorted_group],
            }
        )
        dup_copies += len(group) - 1
        dup_bytes += (len(group) - 1) * first.size

    total = len(uniq) + sum(len(g) for g in dups) + len(unreadable)
    total_bytes = (
        sum(f.size for f in uniq)
        + sum(f.size for g in dups for f in g)
        + sum(f.size for f in unreadable)
    )

    result: dict[str, object] = {
        "scanned_paths": [str(p) for p in scanned_paths],
        "duplicates": dup_blocks,
    }
    if include_unique:
        result["unique"] = [_entry_dict(f) for f in _path_sort(uniq)]
    if unreadable:
        result["unreadable"] = [_entry_dict(f) for f in unreadable]
    result["statistics"] = {
        "total_files": total,
        "total_bytes": total_bytes,
        "unique_files": len(uniq),
        "duplicate_groups": len(dups),
        "duplicate_copies": dup_copies,
        "duplicate_bytes": dup_bytes,
        "unreadable_files": len(unreadable),
        "elapsed_seconds": round(elapsed, 4),
    }
    return result


def main() -> None:
    args = _build_parser().parse_args()
    _configure_logging(args.verbose, args.debug)

    df = DupFinder(
        ignore_symlinks=not args.follow,
        ignore_hidden=not args.hidden,
        ignore_mounts=args.one_file_system,
    )

    t0 = time.perf_counter()
    try:
        uniq, dups, unreadable = df.scan(*args.path)
    except KeyboardInterrupt:
        print("Stopped.", file=sys.stderr)
        return
    elapsed = time.perf_counter() - t0

    if args.json:
        result = _build_json_result(
            scanned_paths=args.path,
            uniq=uniq,
            dups=dups,
            unreadable=unreadable,
            include_unique=args.unique,
            elapsed=elapsed,
        )
        print(json.dumps(result, indent=2))
        return

    if args.unique and not args.dups_only:
        for item in _path_sort(uniq):
            print(item.path)
        print("")

    dup_files = 0
    for group in dups:
        dup_files += len(group)
        sorted_group = _dup_sort(group)
        if args.dups_only:
            print(*[f.path for f in sorted_group[1:]], sep="\0")
        else:
            print(sorted_group[0].path)
            for f in sorted_group[1:]:
                print("\t", f.path, sep="")

    if args.verbose or args.summary:
        total = len(uniq) + dup_files + len(unreadable)
        copies = dup_files - len(dups)
        parts = [
            f"{_count(total, 'file', 'files')} total,",
            f"{_count(copies, 'duplicate', 'duplicates')}",
            f"out of {_count(len(dups), 'file', 'files')}",
        ]
        if unreadable:
            parts.append(f"({_count(len(unreadable), 'unreadable', 'unreadable')})")
        parts.append(f"in {elapsed:.4f}s")
        print("SUMMARY:", *parts, file=sys.stderr)


if __name__ == "__main__":
    main()


# vim: set et sw=4 ts=4:
