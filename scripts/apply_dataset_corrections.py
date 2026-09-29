#!/usr/bin/env python3
"""Apply the reviewed WebMainBench 545 reference corrections."""

import argparse
from pathlib import Path

from dataset_corrections import correct_jsonl


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path, help="Original WebMainBench JSONL")
    parser.add_argument("output", type=Path, help="Corrected JSONL to create")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("data/corrections/WebMainBench_545.json"),
    )
    args = parser.parse_args()
    if args.input.resolve() == args.output.resolve():
        parser.error("output must differ from input")
    count = correct_jsonl(args.input, args.output, args.manifest)
    print(f"Wrote {count} corrected rows to {args.output}")


if __name__ == "__main__":
    main()
