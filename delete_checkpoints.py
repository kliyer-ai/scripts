#!/usr/bin/env python3
import argparse
import os
import shutil
import sys
from pathlib import Path


def walk_dirs(root: Path, follow_symlinks: bool):
    """
    os.walk with optional symlink-following, plus loop protection (inode-based).
    Yields (dirpath, dirnames, filenames) like os.walk.
    """
    visited = set()

    for dirpath, dirnames, filenames in os.walk(root, topdown=True, followlinks=follow_symlinks):
        try:
            st = os.stat(dirpath, follow_symlinks=follow_symlinks)
        except OSError:
            dirnames[:] = []
            continue

        if follow_symlinks:
            key = (st.st_dev, st.st_ino)
            if key in visited:
                dirnames[:] = []
                continue
            visited.add(key)

        yield Path(dirpath), dirnames, filenames


def newest_by_mtime(dirs: list[Path]) -> Path:
    # Using mtime (modification time). If you prefer creation/birth time, that's not portable on Linux.
    return max(dirs, key=lambda p: p.stat().st_mtime)


def prune_checkpoints(root: Path, follow_symlinks: bool, dry_run: bool) -> int:
    deleted = 0

    for dirpath, dirnames, _ in walk_dirs(root, follow_symlinks):
        if "checkpoints" not in dirnames:
            continue

        ckpt_dir = dirpath / "checkpoints"
        if not ckpt_dir.is_dir():
            continue

        subdirs = [p for p in ckpt_dir.iterdir() if p.is_dir()]
        if len(subdirs) <= 1:
            # Still avoid descending into checkpoints if present (often huge)
            dirnames.remove("checkpoints")
            continue

        keep = newest_by_mtime(subdirs)

        print(f"\nIn: {ckpt_dir}")
        print(f"Keeping:  {keep}  (mtime={keep.stat().st_mtime})")

        for p in subdirs:
            if p == keep:
                continue
            if dry_run:
                print(f"Would delete: {p}  (mtime={p.stat().st_mtime})")
            else:
                print(f"Deleting: {p}  (mtime={p.stat().st_mtime})")
                shutil.rmtree(p, ignore_errors=False)
            deleted += 1

        # We already processed this checkpoints dir; don't descend into it.
        dirnames.remove("checkpoints")

    return deleted


def main():
    ap = argparse.ArgumentParser(
        description="Recursively find 'checkpoints' directories and delete all subdirectories except the newest (by mtime)."
    )
    ap.add_argument("root", type=Path, help="Root directory to traverse")
    ap.add_argument(
        "--execute",
        dest="dry_run",
        action="store_false",
        default=True,
        help="Actually archive and delete (default: dry-run).",
    )
    ap.add_argument("--follow-symlinks", action="store_true", help="Follow directory symlinks (loop-protected)")
    args = ap.parse_args()

    if not args.root.is_dir():
        print(f"Error: '{args.root}' is not a directory", file=sys.stderr)
        sys.exit(2)

    n = prune_checkpoints(args.root.resolve(), args.follow_symlinks, args.dry_run)

    if args.dry_run:
        print(f"\nDry run complete. Would delete {n} directories.")
    else:
        print(f"\nDone. Deleted {n} directories.")


if __name__ == "__main__":
    main()
