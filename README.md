# duplicates

Scan for identical files (duplicates) in subdirectories.

## Requirements

* Python >= 3.11
* POSIX (Linux, macOS); MS Windows is not supported.

## Installation

```console
$ uv tool install duplicates
```

Or, if you prefer pipx:

```console
$ pipx install duplicates
```

## Description

To find files with identical content, the given directories are scanned and
files of the same size have their SHA-256 fingerprints compared. Two files
with identical fingerprints are considered to have the same content. There
is a tiny chance for two files with the same fingerprint to have different
content, but that chance is [very
remote](https://stackoverflow.com/questions/4014090).

Large files (≥ 64 KiB) are first compared by a cheap "partial" SHA-256 over
their first and last 4 KiB; only files that survive that prefilter are read
in full. For collections of large near-duplicates (videos, archives) this
avoids reading most of the data.

Symbolic links and hidden entries are ignored by default. This behavior can
be changed with the CLI options `--follow` / `--hidden` or the constructor
options `ignore_symlinks` / `ignore_hidden`.

## CLI examples

Print a short command overview:

```console
$ duplicates --help
```

Scan directories `dirA`, `dirB` and `dirC` and report identical files:

```console
$ duplicates dirA dirB dirC

dirA/file01
        dirA/file01.bak
        dirB/file.bak
dirA/file02
        dirB/file02~
```

The oldest file is printed without indent; identical files are listed
indented by a tab. The oldest file is treated as the original.

If you are willing to take risks, you can delete all duplicates at once.
I wouldn't dare, but you get the picture:

```console
$ duplicates --dups-only dirA dirB | while read dups ; do xargs -0 rm $dups ; done
```

With `--dups-only`, all duplicates for one original are printed on a single
line separated by `\0` (ASCII NUL).

For the [fish shell](https://fishshell.com/) the syntax is almost identical:

```console
$ duplicates --dups-only dirA dirB | while read -la dups ; xargs -0 rm $dups ; end
```

### JSON output

For scripted consumption, `--json` emits the full result on stdout
including a `statistics` block with counts and the scan's elapsed time:

```console
$ duplicates --json dirA dirB
{
  "scanned_paths": ["dirA", "dirB"],
  "duplicates": [
    {
      "hash": "sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
      "size": 1234,
      "files": [
        {"path": "dirA/file01", "age": 1700000000.0},
        {"path": "dirA/file01.bak", "age": 1710000000.0}
      ]
    }
  ],
  "statistics": {
    "total_files": 12,
    "unique_files": 10,
    "duplicate_groups": 1,
    "duplicate_copies": 1,
    "duplicate_bytes": 1234,
    "unreadable_files": 0,
    "elapsed_seconds": 0.0123
  }
}
```

`--json` is mutually exclusive with `--dups-only` and `--summary`.
Combine with `--unique` to also include the unique files in the output.

### Progress on long scans

`--verbose` surfaces phase markers and per-file logs to stderr — useful
when running over a slow filesystem (SMB, large library) where the tool
might otherwise look stuck:

```
INFO: Scanning 1 path(s)...
INFO: Scanned 1284 file(s) so far...
INFO: Discovered 4012 file(s) in 3987 size group(s)
INFO: Partial-hashing 12 file(s)...
INFO: Partial-hashing /films/movie.mp4 (5.2 GiB)
INFO: Full-hashing 4 file(s)...
INFO: Full-hashing /films/movie.mp4 (5.2 GiB)
```

`--debug` adds per-directory and per-ignored-entry messages on top.

## Python API

```python
from duplicates import DupFinder

uniq, dups, unreadable = DupFinder().scan(".")
```

`uniq` is a list of unique `FileEntry` objects. `dups` is a list of duplicate
groups, where each group is a list of `FileEntry` objects with identical
content. Use `entry.age` to identify the oldest file in a group. `unreadable`
collects files that could not be fingerprinted (permission denied, I/O error);
they cannot be classified and are returned separately instead of being
silently dropped.

A `FileEntry` is a dataclass with the following fields:

* `path`: a `pathlib.Path`
* `size`: file size in bytes
* `age`: modification time in seconds ([Unix time](https://docs.python.org/3/library/os.html#os.stat_result))
* `hash`: the SHA-256 fingerprint (`None` for unique files where no hash was needed)

Progress messages are emitted via the `logging` module on the `duplicates`
logger; configure logging in your application to see them.

## Development

```console
$ uv sync
$ uv run pytest
$ uv run ruff check .
$ uv run basedpyright
```
