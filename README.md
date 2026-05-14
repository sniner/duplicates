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
