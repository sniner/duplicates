import hashlib
import logging
import stat
from dataclasses import dataclass
from pathlib import Path


log = logging.getLogger(__name__)


@dataclass
class FileEntry:
    """A single file found during scanning."""

    path: Path
    size: int
    age: float
    hash: str | None = None


def _filetype(path: Path) -> str | None:
    try:
        mode = path.stat().st_mode
    except OSError:
        return None
    if stat.S_ISDIR(mode):
        return "mountpoint" if path.is_mount() else "directory"
    if stat.S_ISLNK(mode):
        return "symlink"
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
    def _fingerprint(path: Path, blocksize: int = 1 << 20) -> str:
        m = hashlib.sha256()
        with open(path, "rb") as f:
            while block := f.read(blocksize):
                m.update(block)
        return m.hexdigest()

    @staticmethod
    def _stat_file(path: Path) -> FileEntry:
        log.debug("FILE: %s", path)
        st = path.stat()
        return FileEntry(
            path=path,
            size=st.st_size,
            age=max(st.st_mtime, st.st_ctime),
        )

    def _scan_dir(self, path: Path, files: list[FileEntry]) -> None:
        log.debug("DIR: %s", path)
        try:
            entries = list(path.iterdir())
        except PermissionError:
            log.info("Access denied to %s", _describe(path))
            return
        for entry in entries:
            try:
                if self.ignore_symlinks and entry.is_symlink():
                    log.info("Ignoring symlink '%s'", entry)
                elif self.ignore_hidden and entry.name.startswith("."):
                    log.info("Ignoring hidden %s", _describe(entry))
                elif entry.is_dir():
                    if self.ignore_mounts and entry.is_mount():
                        log.info("Ignoring mountpoint '%s'", entry)
                    else:
                        self._scan_dir(entry, files)
                elif entry.is_file():
                    files.append(self._stat_file(entry))
                else:
                    log.info("Ignoring %s", _describe(entry))
            except PermissionError:
                log.info("Access denied to %s", _describe(entry))
            except OSError as exc:
                log.error("Cannot access '%s': %s", entry, exc)

    def _collect(self, paths: tuple[Path | str, ...]) -> list[FileEntry]:
        files: list[FileEntry] = []
        for raw in paths:
            path = raw if isinstance(raw, Path) else Path(str(raw))
            if not path.exists():
                log.info("'%s' not found", path)
                continue
            if path.is_dir():
                self._scan_dir(path, files)
            elif path.is_file():
                files.append(self._stat_file(path))
            else:
                log.info("Ignoring %s", _describe(path))
        return files

    def scan(
        self,
        *paths: Path | str,
    ) -> tuple[list[FileEntry], list[list[FileEntry]]]:
        """Scan the given paths and return (unique_files, duplicate_groups).

        Each duplicate group is a list of files with identical content,
        ordered as collected (the caller can sort by age to find the original).
        Empty files are always treated as unique.
        """
        files = self._collect(paths)

        by_size: dict[int, list[FileEntry]] = {}
        for f in files:
            by_size.setdefault(f.size, []).append(f)
        log.debug("%d files of %d different sizes", len(files), len(by_size))

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

        by_hash: dict[str, list[FileEntry]] = {}
        for group in candidates:
            for f in group:
                try:
                    f.hash = self._fingerprint(f.path)
                except (PermissionError, OSError):
                    log.error("Unable to read content of '%s'", f.path)
                    continue
                by_hash.setdefault(f.hash, []).append(f)

        dups: list[list[FileEntry]] = []
        for items in by_hash.values():
            if len(items) == 1:
                uniq.append(items[0])
            else:
                dups.append(items)

        return uniq, dups


# vim: set et sw=4 ts=4:
