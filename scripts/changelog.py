"""Generate a simple Markdown changelog section from conventional Git history."""
from __future__ import annotations

import argparse
import subprocess
from datetime import date


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("version")
    parser.add_argument("--since", default="")
    args = parser.parse_args()
    range_spec = f"{args.since}..HEAD" if args.since else "HEAD"
    output = subprocess.run(
        ["git", "log", range_spec, "--pretty=format:- %s (`%h`)"],
        capture_output=True, text=True, check=True,
    ).stdout
    print(f"## {args.version} - {date.today().isoformat()}\n\n{output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
