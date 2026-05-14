import argparse
import logging
import re
import sys
from pathlib import Path

from duplicates.dupfinder import DupFinder, FileEntry


def _natural_key(text: object) -> list[int | str]:
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
        help="Print also unique files.",
    )
    parser.add_argument(
        "--dups-only",
        action="store_true",
        help="Print only duplicates, no uniques and no originals, zero-delimited.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print more information.",
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Print the final summary.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Print debug output.",
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


def main() -> None:
    args = _build_parser().parse_args()
    _configure_logging(args.verbose, args.debug)

    df = DupFinder(
        ignore_symlinks=not args.follow,
        ignore_hidden=not args.hidden,
        ignore_mounts=args.one_file_system,
    )

    try:
        uniq, dups = df.scan(*args.path)
    except KeyboardInterrupt:
        print("Stopped.", file=sys.stderr)
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
        total = len(uniq) + dup_files
        copies = dup_files - len(dups)
        print(
            "SUMMARY:",
            f"{_count(total, 'file', 'files')} total,",
            f"{_count(copies, 'duplicate', 'duplicates')}",
            f"out of {_count(len(dups), 'file', 'files')}",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()


# vim: set et sw=4 ts=4:
