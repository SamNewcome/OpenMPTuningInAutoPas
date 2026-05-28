#!/usr/bin/env python3
"""
Compare *_tuningResults_* files found in common subdirectories of two given
root directories.  Results are printed sorted by speedup (highest first),
where speedup = dir1_optimumPerformance / dir2_optimumPerformance.
"""

import argparse
import csv
import statistics
import sys
from pathlib import Path


def find_tuning_files(base: Path, pattern: str = "*_tuningResults_*") -> dict[str, Path]:
    """Map relative subdir path -> path of the first file matching pattern."""
    mapping: dict[str, Path] = {}
    for dirpath in sorted(base.rglob("*")):
        if not dirpath.is_dir():
            continue
        matches = sorted(dirpath.glob(pattern))
        if matches:
            rel = str(dirpath.relative_to(base))
            mapping[rel] = matches[0]
            if len(matches) > 1:
                print(
                    f"Warning: multiple files matching '{pattern}' in {dirpath};"
                    f" using {matches[0].name}",
                    file=sys.stderr,
                )
    # Also check the base directory itself
    matches = sorted(base.glob(pattern))
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

    raw = ",".join(last_row.values())
    return last_row, raw


def best_chunk1_performance(tuning_data_file: Path) -> float | None:
    """Return the minimum Smoothed value among rows with OpenMPChunkSize == '1'."""
    best: float | None = None
    with tuning_data_file.open(newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            if row.get("OpenMPChunkSize", "").strip() != "1":
                continue
            try:
                val = float(row["Smoothed"])
            except (KeyError, ValueError):
                continue
            if best is None or val < best:
                best = val
    return best


def print_stats(label: str, values: list[float]) -> None:
    print(f"=== {label} ===")
    print(f"  Count:  {len(values)}")
    print(f"  Mean:   {statistics.mean(values):.4f}")
    if len(values) >= 2:
        print(f"  Std dev: {statistics.stdev(values):.4f}")
        qs = statistics.quantiles(values, n=4)
        print(f"  Q1 (lower quartile): {qs[0]:.4f}")
        print(f"  Median: {statistics.median(values):.4f}")
        print(f"  Q3 (upper quartile): {qs[2]:.4f}")
    else:
        print(f"  Median: {statistics.median(values):.4f}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compare tuning results between two directories."
    )
    parser.add_argument("dir1", help="First directory")
    parser.add_argument("dir2", help="Second directory")
    parser.add_argument(
        "--chunk1",
        action="store_true",
        help=(
            "Also check whether any chunk-size-1 entry in dir1's *_tuningData_* file"
            " outperforms dir2's optimum, and report the best such speedup."
        ),
    )
    args = parser.parse_args()

    dir1, dir2 = Path(args.dir1).resolve(), Path(args.dir2).resolve()

    for d in (dir1, dir2):
        if not d.is_dir():
            print(f"Error: {d} is not a directory.", file=sys.stderr)
            sys.exit(1)

    files1 = find_tuning_files(dir1)
    files2 = find_tuning_files(dir2)
    data_files1 = find_tuning_files(dir1, "*_tuningData_*") if args.chunk1 else {}

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

        chunk1_speedup: float | None = None
        if args.chunk1 and rel_dir in data_files1:
            best_c1 = best_chunk1_performance(data_files1[rel_dir])
            if best_c1 is not None:
                chunk1_speedup = best_c1 / opt2

        results.append(
            dict(
                rel_dir=rel_dir,
                speedup=speedup,
                chunk1_speedup=chunk1_speedup,
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
        if args.chunk1:
            if r["chunk1_speedup"] is not None:
                c1 = r["chunk1_speedup"]
                verdict = "outperforms" if c1 < 1.0 else "does not outperform"
                print(
                    f"  Best chunk-size-1 entry (Smoothed / dir2 optimum):"
                    f" {c1:.4f}x  [{verdict} dir2]"
                )
            else:
                print("  Best chunk-size-1: no tuningData file or no chunk-size-1 rows found")
        print()

    speedups = [r["speedup"] for r in results]
    if speedups:
        print_stats("Speedup Statistics (dir1 / dir2 optimumPerformance[ns])", speedups)

    if args.chunk1:
        c1_speedups = [r["chunk1_speedup"] for r in results if r["chunk1_speedup"] is not None]
        if c1_speedups:
            print()
            print_stats(
                "Chunk-size-1 Best Speedup Statistics (best Smoothed / dir2 optimum)",
                c1_speedups,
            )


if __name__ == "__main__":
    main()
