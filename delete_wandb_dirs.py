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
            # Can't stat: skip descending further
            dirnames[:] = []
            continue

        key = (st.st_dev, st.st_ino)
        if follow_symlinks:
            if key in visited:
                # loop detected: don't descend
                dirnames[:] = []
                continue
            visited.add(key)

        yield Path(dirpath), dirnames, filenames


def delete_wandb_dirs(root: Path, follow_symlinks: bool, dry_run: bool) -> int:
    deleted = 0

    for dirpath, dirnames, _ in walk_dirs(root, follow_symlinks):
        # If a child directory is named "wandb", delete it and prevent descending into it
        to_delete = [d for d in dirnames if d == "wandb"]
        if to_delete:
            # Remove from traversal so os.walk won't enter them
            dirnames[:] = [d for d in dirnames if d != "wandb"]

        for name in to_delete:
            target = dirpath / name
            if dry_run:
                print(f"Would delete: {target}")
            else:
                print(f"Deleting: {target}")
                shutil.rmtree(target, ignore_errors=False)
            deleted += 1

    return deleted


# python delete_wandb_dirs.py /path/to/root --dry-run --follow-symlinks
# python delete_wandb_dirs.py /path/to/root --follow-symlinks
def main():
    p = argparse.ArgumentParser(description="Recursively delete directories named 'wandb'.")
    p.add_argument("root", type=Path, help="Root directory to traverse")
    p.add_argument(
        "--execute",
        dest="dry_run",
        action="store_false",
        default=True,
        help="Actually archive and delete (default: dry-run).",
    )
    p.add_argument("--follow-symlinks", action="store_true", help="Follow directory symlinks (loop-protected)")
    args = p.parse_args()

    if not args.root.is_dir():
        print(f"Error: '{args.root}' is not a directory", file=sys.stderr)
        sys.exit(2)

    n = delete_wandb_dirs(args.root.resolve(), args.follow_symlinks, args.dry_run)
    if args.dry_run:
        print(f"Dry run complete. Matched {n} directories.")
    else:
        print(f"Done. Deleted {n} directories.")


if __name__ == "__main__":
    main()
