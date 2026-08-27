"""Safe retention for inactive, rebuildable deployment environments."""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path


def prune_inactive_releases(
    releases_root: Path,
    protected: set[Path],
    *,
    keep_inactive: int = 1,
    apply: bool = False,
) -> list[Path]:
    if keep_inactive < 0:
        raise ValueError("keep_inactive cannot be negative")
    root = releases_root.resolve()
    protected_paths = {path.resolve() for path in protected if path.exists()}
    releases = sorted(
        (path for path in root.iterdir() if path.is_dir() and not path.is_symlink()),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    inactive = [path for path in releases if path.resolve() not in protected_paths]
    removable = inactive[max(0, keep_inactive):]
    for path in removable:
        resolved = path.resolve()
        if resolved.parent != root:
            raise RuntimeError(f"Refusing unsafe release path: {resolved}")
        if apply:
            shutil.rmtree(resolved)
    return removable


def main() -> int:
    parser = argparse.ArgumentParser(description="Prune inactive Field Mouse releases")
    parser.add_argument("--releases-root", type=Path, required=True)
    parser.add_argument("--protect", type=Path, action="append", default=[])
    parser.add_argument("--keep-inactive", type=int, default=1)
    parser.add_argument("--apply", action="store_true")
    arguments = parser.parse_args()
    removed = prune_inactive_releases(
        arguments.releases_root,
        set(arguments.protect),
        keep_inactive=arguments.keep_inactive,
        apply=arguments.apply,
    )
    for path in removed:
        print(f"{'Pruned' if arguments.apply else 'Would prune'}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
