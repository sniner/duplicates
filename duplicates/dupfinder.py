import hashlib
import logging
import stat
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

_BLOCK_SIZE = 1 << 20

# Two-stage fingerprinting: for files at least _PARTIAL_THRESHOLD bytes we
# hash a head and tail window first, and only fall back to the full SHA-256
# when several files share the same partial hash. Saves dramatic amounts of
# I/O on collections of large near-duplicates (videos, archives).
_PARTIAL_WINDOW = 4096
_PARTIAL_THRESHOLD = 65536


def _human_size(n: int) -> str:
    x = float(n)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if abs(x) < 1024:
            return f"{x:.1f} {unit}"
        x /= 1024
    return f"{x:.1f} PiB"


class _Progress:
    """Emits a throttled INFO log message at most once per `interval` seconds.

    Used to surface long-running work (directory walks, hash passes) without
    flooding the log. `warmup` keeps the first message from firing
    immediately, so fast scans don't print anything at all.
    """

    def __init__(self, interval: float = 2.0, warmup: float = 1.0) -> None:
        self.interval = interval
        self.next_emit = time.monotonic() + warmup

    def tick(self, msg: str, *args: object) -> None:
        now = time.monotonic()
        if now >= self.next_emit:
            log.info(msg, *args)
            self.next_emit = now + self.interval


@dataclass
class FileEntry:
    """A single file found during scanning."""

    path: Path
    size: int
    age: float
    hash: str | None = None


def _filetype(path: Path) -> str | None:
    try:
        mode = path.lstat().st_mode
    except OSError:
        return None
    if stat.S_ISLNK(mode):
        return "symlink"
    if stat.S_ISDIR(mode):
        return "mountpoint" if path.is_mount() else "directory"
    if stat.S_ISSOCK(mode):
        return "socket"
    if stat.S_ISFIFO(mode):
        return "fifo"
    if stat.S_ISCHR(mode) or stat.S_ISBLK(mode):
        return "device"
    if stat.S_ISREG(mode):
        return "file"
    return None


def _describe(path: Path) -> str:
    ft = _filetype(path)
    return f"{ft} '{path}'" if ft else f"'{path}'"


class DupFinder:
    """Scan directories for files with identical content."""

    def __init__(
        self,
        ignore_symlinks: bool = True,
        ignore_hidden: bool = True,
        ignore_mounts: bool = False,
    ) -> None:
        self.ignore_symlinks = ignore_symlinks
        self.ignore_hidden = ignore_hidden
        self.ignore_mounts = ignore_mounts

    @staticmethod
    def _fingerprint(path: Path, blocksize: int = _BLOCK_SIZE) -> str:
        m = hashlib.sha256()
        with open(path, "rb") as f:
            while block := f.read(blocksize):
                m.update(block)
        return m.hexdigest()

    @staticmethod
    def _partial_fingerprint(path: Path, size: int) -> str:
        # Precondition: only called for size >= _PARTIAL_THRESHOLD, which is
        # always > 2 * _PARTIAL_WINDOW, so head and tail don't overlap.
        m = hashlib.sha256()
        with open(path, "rb") as f:
            m.update(f.read(_PARTIAL_WINDOW))
            f.seek(size - _PARTIAL_WINDOW)
            m.update(f.read(_PARTIAL_WINDOW))
        return m.hexdigest()

    def _partial_hash_log(self, f: FileEntry) -> str:
        log.info("Partial-hashing %s (%s)", f.path, _human_size(f.size))
        return self._partial_fingerprint(f.path, f.size)

    def _full_hash_log(self, f: FileEntry) -> str:
        log.info("Full-hashing %s (%s)", f.path, _human_size(f.size))
        f.hash = self._fingerprint(f.path)
        return f.hash

    @staticmethod
    def _stat_file(path: Path) -> FileEntry:
        log.debug("FILE: %s", path)
        st = path.stat()
        return FileEntry(
            path=path,
            size=st.st_size,
            age=max(st.st_mtime, st.st_ctime),
        )

    def _scan_dir(
        self,
        root: Path,
        files: list[FileEntry],
        progress: _Progress,
    ) -> None:
        # Iterative walk with explicit stack so deep trees don't hit the
        # Python recursion limit. When following symlinks we remember
        # already-visited (resolved) directories to defuse symlink cycles.
        visited: set[Path] = set()
        stack: list[Path] = [root]
        while stack:
            path = stack.pop()
            log.debug("DIR: %s", path)
            if not self.ignore_symlinks:
                try:
                    resolved = path.resolve(strict=True)
                except OSError as exc:
                    log.debug("Cannot resolve '%s': %s", path, exc)
                    continue
                if resolved in visited:
                    log.debug("Skipping already-visited directory '%s'", path)
                    continue
                visited.add(resolved)
            try:
                entries = list(path.iterdir())
            except OSError as exc:
                log.debug("Cannot enter '%s': %s", path, exc)
                continue
            for entry in entries:
                try:
                    if self.ignore_symlinks and entry.is_symlink():
                        log.debug("Ignoring symlink '%s'", entry)
                    elif self.ignore_hidden and entry.name.startswith("."):
                        log.debug("Ignoring hidden %s", _describe(entry))
                    elif entry.is_dir():
                        if self.ignore_mounts and entry.is_mount():
                            log.debug("Ignoring mountpoint '%s'", entry)
                        else:
                            stack.append(entry)
                    elif entry.is_file():
                        files.append(self._stat_file(entry))
                        progress.tick("Scanned %d file(s) so far...", len(files))
                    else:
                        log.debug("Ignoring %s", _describe(entry))
                except OSError as exc:
                    log.error("Cannot access '%s': %s", entry, exc)

    def _collect(
        self,
        paths: tuple[Path | str, ...],
        progress: _Progress,
    ) -> list[FileEntry]:
        files: list[FileEntry] = []
        for raw in paths:
            path = raw if isinstance(raw, Path) else Path(str(raw))
            try:
                if not path.exists():
                    log.info("'%s' not found", path)
                    continue
                if path.is_dir():
                    self._scan_dir(path, files, progress)
                elif path.is_file():
                    files.append(self._stat_file(path))
                else:
                    log.debug("Ignoring %s", _describe(path))
            except OSError as exc:
                log.error("Cannot access '%s': %s", path, exc)
        return files

    @staticmethod
    def _bucket_groups(
        groups: list[list[FileEntry]],
        hasher: Callable[[FileEntry], str],
        min_size: int = 0,
    ) -> tuple[list[list[FileEntry]], list[FileEntry], list[FileEntry]]:
        """Sub-bucket each group via `hasher`.

        Returns `(multi, singletons, unreadable)`:

        - `multi`: sub-buckets with at least two entries (still candidates).
        - `singletons`: sub-buckets reduced to exactly one entry (proven unique).
        - `unreadable`: entries whose hash could not be computed.

        Groups whose member size is below `min_size` are passed through to
        `multi` unchanged — useful for the partial-hash pass, where small
        files don't benefit from the seek-to-tail step.
        """
        multi: list[list[FileEntry]] = []
        singletons: list[FileEntry] = []
        unreadable: list[FileEntry] = []
        for group in groups:
            if group and group[0].size < min_size:
                multi.append(group)
                continue
            buckets: dict[str, list[FileEntry]] = {}
            for f in group:
                try:
                    key = hasher(f)
                except OSError as exc:
                    log.error("Unable to read '%s': %s", f.path, exc)
                    unreadable.append(f)
                    continue
                buckets.setdefault(key, []).append(f)
            for items in buckets.values():
                if len(items) == 1:
                    singletons.append(items[0])
                else:
                    multi.append(items)
        return multi, singletons, unreadable

    def scan(
        self,
        *paths: Path | str,
    ) -> tuple[list[FileEntry], list[list[FileEntry]], list[FileEntry]]:
        """Scan the given paths.

        Returns a triple `(unique, duplicates, unreadable)`:

        - `unique`: files with no duplicate in the scanned set.
        - `duplicates`: a list of duplicate groups, each a list of files
          with identical content. Groups are unordered; callers can sort
          by `age` to identify the original.
        - `unreadable`: files that could not be fingerprinted (permission
          denied, I/O error). They cannot be classified and are returned
          separately rather than silently dropped.

        Empty files are always treated as unique. Order within each list
        reflects filesystem traversal and is not guaranteed to be stable.
        """
        progress = _Progress()

        log.info("Scanning %d path(s)...", len(paths))
        files = self._collect(paths, progress)

        # Phase 1: bucket by size. Files alone in their size bucket can't be
        # duplicates of anything; empty files are always treated as unique.
        by_size: dict[int, list[FileEntry]] = {}
        for f in files:
            by_size.setdefault(f.size, []).append(f)
        log.info("Discovered %d file(s) in %d size group(s)", len(files), len(by_size))

        uniq: list[FileEntry] = []
        candidates: list[list[FileEntry]] = []
        for size, group in by_size.items():
            if size == 0:
                if len(group) > 1:
                    log.info("%d empty files are not considered identical", len(group))
                uniq.extend(group)
            elif len(group) == 1:
                uniq.append(group[0])
            else:
                candidates.append(group)

        # Phase 2: cheap partial hash (head + tail) on large files. Groups
        # whose files are smaller than _PARTIAL_THRESHOLD pass through to the
        # full-hash phase unchanged — the seek to the tail wouldn't save
        # enough I/O to be worth it.
        partial_count = sum(
            len(g) for g in candidates if g and g[0].size >= _PARTIAL_THRESHOLD
        )
        if partial_count:
            log.info("Partial-hashing %d file(s)...", partial_count)
        survivors, partial_uniq, partial_unreadable = self._bucket_groups(
            candidates,
            self._partial_hash_log,
            min_size=_PARTIAL_THRESHOLD,
        )
        uniq.extend(partial_uniq)

        # Phase 3: full SHA-256 on whatever the partial pass couldn't separate.
        full_count = sum(len(g) for g in survivors)
        if full_count:
            log.info("Full-hashing %d file(s)...", full_count)
        dups, full_uniq, full_unreadable = self._bucket_groups(
            survivors,
            self._full_hash_log,
        )
        uniq.extend(full_uniq)

        return uniq, dups, partial_unreadable + full_unreadable


# vim: set et sw=4 ts=4:
