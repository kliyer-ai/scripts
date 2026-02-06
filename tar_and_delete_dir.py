#!/usr/bin/env python3
import argparse
import os
import sys
import tarfile
import tempfile
from datetime import datetime
from pathlib import Path


def parse_cutoff(ts: str) -> float:
    """
    Parse cutoff timestamp like "YYYY-MM-DD HH:MM:SS" into epoch seconds (local time).
    """
    try:
        dt = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
    except ValueError as e:
        raise ValueError(f"Invalid cutoff timestamp '{ts}'. Expected 'YYYY-MM-DD HH:MM:SS'.") from e
    return dt.timestamp()


def is_within(child: Path, parent: Path) -> bool:
    """
    True if child is inside parent (or equal). Resolves symlinks.
    """
    try:
        child = child.resolve()
        parent = parent.resolve()
        child.relative_to(parent)
        return True
    except Exception:
        return False


def collect_files(target_dir: Path, cutoff_epoch: float) -> list[Path]:
    """
    Collect all regular files under target_dir with mtime <= cutoff.
    """
    files: list[Path] = []
    for root, _, filenames in os.walk(target_dir):
        root_p = Path(root)
        for name in filenames:
            p = root_p / name
            try:
                st = p.stat(follow_symlinks=False)
            except OSError:
                continue
            if not p.is_file():
                continue
            if st.st_mtime <= cutoff_epoch:
                files.append(p)
    return files


def archive_files(target_dir: Path, files: list[Path], archive_path: Path) -> int:
    """
    Create a tar archive containing exactly `files`.
    Paths in tar are stored relative to target_dir (like the bash script behavior).
    Returns the number of archived members.
    """
    count = 0
    with tarfile.open(archive_path, mode="w") as tf:
        for p in files:
            rel = p.relative_to(target_dir)
            tf.add(p, arcname=str(rel), recursive=False)
            count += 1
    return count


def verify_archive_count(archive_path: Path) -> int:
    with tarfile.open(archive_path, mode="r") as tf:
        return sum(1 for _ in tf.getmembers())


def delete_files(files: list[Path]) -> None:
    for p in files:
        try:
            p.unlink()
        except FileNotFoundError:
            # If it vanished between collection and delete, ignore (same spirit as rm -f)
            pass


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Archive (tar) and then delete files in a directory with mtime <= cutoff timestamp."
    )
    ap.add_argument(
        "--execute",
        dest="dry_run",
        action="store_false",
        default=True,
        help="Actually archive and delete (default: dry-run).",
    )
    ap.add_argument("directory", type=Path, help="Target directory to scan")
    ap.add_argument("cutoff_timestamp", type=str, help='Cutoff timestamp, e.g. "2025-12-01 00:00:00"')
    ap.add_argument("archive_tar", type=Path, help="Path to output .tar file (must be outside target directory)")
    args = ap.parse_args()

    target_dir = args.directory
    if not target_dir.is_dir():
        print(f"Error: '{target_dir}' is not a directory", file=sys.stderr)
        return 2

    # Resolve absolute paths to avoid weirdness
    target_dir_abs = target_dir.resolve()

    archive_path = args.archive_tar
    archive_parent = archive_path.parent
    if not archive_parent.is_dir():
        print(f"Error: Archive directory '{archive_parent}' does not exist", file=sys.stderr)
        return 2

    archive_path_abs = archive_parent.resolve() / archive_path.name

    # Safety: do not store the archive inside the directory you are archiving
    if is_within(archive_path_abs, target_dir_abs):
        print("Error: archive must NOT be created inside the target directory.", file=sys.stderr)
        print(f"Archive: {archive_path_abs}", file=sys.stderr)
        print(f"Target:  {target_dir_abs}", file=sys.stderr)
        return 2

    try:
        cutoff_epoch = parse_cutoff(args.cutoff_timestamp)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2

    # Build list once (like the bash script)
    files = collect_files(target_dir_abs, cutoff_epoch)

    if not files:
        print(f"No files older than '{args.cutoff_timestamp}' found in '{target_dir_abs}'. Nothing to do.")
        return 0

    print(f"Found {len(files)} file(s) in '{target_dir_abs}' with mtime <= '{args.cutoff_timestamp}'")

    if args.dry_run:
        print(f"[DRY-RUN] Would archive to: {archive_path_abs}")
        print("[DRY-RUN] Files that would be archived and deleted:")
        for p in files:
            print(p)
        return 0

    # Write to a temp file in the archive directory, then atomically move into place.
    # This avoids leaving a partial archive at the final path if something fails.
    tmp_fd, tmp_name = tempfile.mkstemp(prefix=archive_path.name + ".", suffix=".tmp", dir=str(archive_parent))
    os.close(tmp_fd)
    tmp_path = Path(tmp_name)

    try:
        print(f"Archiving into: {archive_path_abs}")
        archived_count = archive_files(target_dir_abs, files, tmp_path)

        # Verify created and non-empty
        if not tmp_path.exists() or tmp_path.stat().st_size == 0:
            raise RuntimeError("Archive was not created or is empty. No files will be deleted.")

        # Verify archive integrity and count
        verified_count = verify_archive_count(tmp_path)
        if verified_count != len(files) or verified_count != archived_count:
            raise RuntimeError(
                f"Archive contains {verified_count} files but expected {len(files)}. No files will be deleted."
            )

        # Move into final location
        tmp_path.replace(archive_path_abs)

        print(f"Archive created and verified successfully ({verified_count} files). Now deleting the archived files...")
        delete_files(files)

        print(f"Done. Files up to '{args.cutoff_timestamp}' have been archived and removed from '{target_dir_abs}'.")
        return 0

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        print("No files will be deleted.", file=sys.stderr)
        # Best effort cleanup of temp archive
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except Exception:
            pass
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
