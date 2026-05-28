#!/usr/bin/env python3
"""
Compare *_tuningResults_* files found in common subdirectories of two given
root directories.  Results are printed sorted by speedup (highest first),
where speedup = dir1_optimumPerformance / dir2_optimumPerformance.
"""

import csv
import sys
from pathlib import Path


def find_tuning_files(base: Path) -> dict[str, Path]:
    """Map relative subdir path -> path of the first *_tuningResults_* file."""
    mapping: dict[str, Path] = {}
    for dirpath in sorted(base.rglob("*")):
        if not dirpath.is_dir():
            continue
        matches = sorted(dirpath.glob("*_tuningResults_*"))
        if matches:
            rel = str(dirpath.relative_to(base))
            mapping[rel] = matches[0]
            if len(matches) > 1:
                print(
                    f"Warning: multiple tuning files in {dirpath}; using {matches[0].name}",
                    file=sys.stderr,
                )
    # Also check the base directory itself
    matches = sorted(base.glob("*_tuningResults_*"))
    if matches:
        mapping["."] = matches[0]
    return mapping


def last_data_row(filepath: Path) -> tuple[dict, str] | tuple[None, None]:
    """Return (row_dict, raw_line) for the last non-empty data row in a CSV."""
    with filepath.open(newline="") as fh:
        reader = csv.DictReader(fh)
        last_row: dict | None = None
        for row in reader:
            last_row = row

    if last_row is None:
        return None, None

    # Reconstruct the raw line from ordered values so we don't re-read the file
    raw = ",".join(last_row.values())
    return last_row, raw


def main() -> None:
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <dir1> <dir2>", file=sys.stderr)
        sys.exit(1)

    dir1, dir2 = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()

    for d in (dir1, dir2):
        if not d.is_dir():
            print(f"Error: {d} is not a directory.", file=sys.stderr)
            sys.exit(1)

    files1 = find_tuning_files(dir1)
    files2 = find_tuning_files(dir2)

    common = sorted(set(files1) & set(files2))

    if not common:
        print("No common subdirectories with tuning result files found.")
        return

    results = []
    for rel_dir in common:
        row1, line1 = last_data_row(files1[rel_dir])
        row2, line2 = last_data_row(files2[rel_dir])

        if row1 is None or row2 is None:
            print(f"Warning: empty tuning file in {rel_dir}; skipping.", file=sys.stderr)
            continue

        opt1 = float(row1["optimumPerformance[ns]"])
        opt2 = float(row2["optimumPerformance[ns]"])
        speedup = opt1 / opt2

        results.append(
            dict(
                rel_dir=rel_dir,
                speedup=speedup,
                file1=files1[rel_dir],
                file2=files2[rel_dir],
                line1=line1,
                line2=line2,
            )
        )

    results.sort(key=lambda r: r["speedup"], reverse=True)

    for r in results:
        label = r["rel_dir"]
        print(f"=== {label} ===")
        print(f"  Speedup (dir1 / dir2 optimumPerformance[ns]): {r['speedup']:.4f}x")
        print(f"  dir1  {r['file1']}")
        print(f"        {r['line1']}")
        print(f"  dir2  {r['file2']}")
        print(f"        {r['line2']}")
        print()


if __name__ == "__main__":
    main()
