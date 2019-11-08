# duplicates

[![Build Status](https://travis-ci.org/sniner/duplicates.svg?branch=master)](https://travis-ci.org/sniner/duplicates)

Scan for identical files (duplicates) in subdirectories.

## Requirements

* Python >= 3.6
* MS Windows is not supported

## Description

To find files with identical content the given directories will be scanned and
for files of same size their SHA-256 fingerprints are calculated and compared.
Two files with identical fingerprints are considered to have the same content.
There is a tiny chance for two files with same fingerprint to have different
content, but this chance is [very
remote](https://stackoverflow.com/questions/4014090).

Symbolic links and hidden entries are ignored by default, this behaviour can
be changed with CLI options `--follow`/`--hidden` and constructor options
`ignore_hidden`/`ignore_symlinks`.

## CLI examples

This one will give you a short command overview:

```console
$ duplicates --help
```

Scan directories `dirA`, `dirB` and `dirC` for duplicates and report all found
identical files:

```console
$ duplicates dirA dirB dirC

dirA/file01
        dirA/file01.bak
        dirB/file.bak
dirA/file02
        dirB/file02~
```

The oldest file is printed without indent, all identical files are printed
indented by a tab character. The oldest file is supposed to be the original.

If you are willing to take risks, you can delete all duplicates at once.
I wouldn't dare, but you get the picture:

```console
$ duplicates --dups-only dirA dirB | while read dups ; do xargs -0 rm $dups ; done
```

With `--dups-only` all duplicates for one original are output on one line,
separated by `\0` (ASCII code zero).

For [fish shell](https://fishshell.com/) it looks almost identical:

```console
$ duplicates --dups-only dirA dirB | while read -la dups ; xargs -0 rm $dups ; end
```

## Python examples

```python
import duplicates

df = duplicates.DupFinder(verbose=True)
uniq, dups = df.scan(".")
```

`uniq` is a list of unique file objects. `dups` is a list of identical files,
which in turn are lists of file objects, the first being the oldest element
and thus the supposed original.

A file object is a dict consisting of the following elements:

* `path`: a pathlib.Path object
* `age`: modification time in seconds ([Unix time](https://docs.python.org/3/library/os.html#os.stat_result))
* `size`: file size in bytes
* `hash`: the SHA-256 fingerprint (not calculated for unique files)
