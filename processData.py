import os
import sys
import csv
from pathlib import Path
from collections import defaultdict

# Traversals that only support static,1 scheduling
allTraversalsSupportingOnlyStatic1Scheduling = [
    "lc_sliced_balanced",
    "vcl_sliced_balanced",
    "vcl_c01_balanced",
    "vvl_as_built",
    "vlc_sliced_balanced",
    "vlp_sliced_balanced"
]

STANDARD_SCHEDULES = {'static', 'dynamic', 'guided'}
EXTENDED_SCHEDULES = {'static', 'dynamic', 'guided', 'auto', 'static_steal', 'trapezoidal'}

SIGNIFICANT_SPEEDUP_THRESHOLD = 1.2


def find_csv_files(base_dir):
    """Find all CSV files matching the pattern."""
    csv_files = []
    for root, dirs, files in os.walk(base_dir):
        if 'archive' in root.lower():
            continue
        for file in files:
            if '_tuningData_' in file and file.endswith('.csv') and 'archive' not in file.lower():
                csv_files.append(os.path.join(root, file))
    return csv_files


def parse_csv_file(filepath):
    """Parse CSV file and extract relevant data."""
    data = []
    with open(filepath, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row['Reduced'] == '' or row['Reduced'] == '-1':
                continue
            try:
                performance = int(row['Reduced'])
            except ValueError:
                continue

            base_algorithm = (
                row['Container'],
                row['CellSizeFactor'],
                row['Traversal'],
                row['Load Estimator'],
                row['Data Layout'],
                row['Newton 3']
            )
            openmp_config = (
                row['OpenMP Schedule Kind'],
                row['OpenMPChunkSize']
            )
            full_algorithm = base_algorithm + openmp_config

            data.append({
                'base_algorithm': base_algorithm,
                'openmp_config': openmp_config,
                'full_algorithm': full_algorithm,
                'performance': performance,
                'traversal': row['Traversal']
            })
    return data


def get_default_openmp_config(traversal):
    """Determine the default OpenMP configuration based on traversal."""
    if traversal in allTraversalsSupportingOnlyStatic1Scheduling:
        return ('static', '1')
    else:
        return ('dynamic', '1')


def find_optimal_and_compare(data, label, indent="  ", schedule_set=None):
    """
    Find the optimal algorithm (optionally restricted to schedule_set) and compare it
    against (a) that algorithm's base with default scheduling and (b) the best algorithm
    overall that uses default scheduling.

    Returns a stats dict for summary accumulation, or None if no data is available.
    """
    if schedule_set is not None:
        filtered = [e for e in data if e['openmp_config'][0].lower() in schedule_set]
    else:
        filtered = data

    if not filtered:
        print(f"{indent}{label}: No data available for this schedule set.")
        return None

    optimal_entry = min(filtered, key=lambda x: x['performance'])
    optimal_performance = optimal_entry['performance']
    optimal_base = optimal_entry['base_algorithm']
    optimal_traversal = optimal_entry['traversal']
    optimal_algorithm = optimal_entry['full_algorithm']
    optimal_schedule_kind = optimal_algorithm[6]
    optimal_chunk_size = optimal_algorithm[7]

    print(f"\n{indent}{label}:")
    print(f"{indent}  Optimal Algorithm:")
    print(f"{indent}    Container:       {optimal_algorithm[0]}")
    print(f"{indent}    CellSizeFactor:  {optimal_algorithm[1]}")
    print(f"{indent}    Traversal:       {optimal_algorithm[2]}")
    print(f"{indent}    Load Estimator:  {optimal_algorithm[3]}")
    print(f"{indent}    Data Layout:     {optimal_algorithm[4]}")
    print(f"{indent}    Newton 3:        {optimal_algorithm[5]}")
    print(f"{indent}    OpenMP Schedule: {optimal_schedule_kind}, ChunkSize: {optimal_chunk_size}")
    print(f"{indent}    Performance:     {optimal_performance:,}")

    # --- Optimal base algorithm with its default scheduling ---
    default_openmp = get_default_openmp_config(optimal_traversal)
    default_label = f"{default_openmp[0]},{default_openmp[1]}"

    optimal_base_with_default = None
    for entry in data:
        if entry['base_algorithm'] == optimal_base and entry['openmp_config'] == default_openmp:
            optimal_base_with_default = entry['performance']
            break

    speedup_base_default = None
    if optimal_base_with_default is not None:
        speedup_base_default = optimal_base_with_default / optimal_performance
        print(f"\n{indent}  Optimal Base with Default Scheduling ({default_label}):")
        print(f"{indent}    Performance: {optimal_base_with_default:,}")
        print(f"{indent}    Speedup vs optimal base with default: {speedup_base_default:.3f}x")
        #if speedup_base_default >= SIGNIFICANT_SPEEDUP_THRESHOLD:
            #print(f"{indent}    *** SIGNIFICANT SPEEDUP: {speedup_base_default:.3f}x >= {SIGNIFICANT_SPEEDUP_THRESHOLD} ***")
    else:
        print(f"\n{indent}  Optimal Base with Default Scheduling ({default_label}): NOT FOUND")

    # --- Best algorithm (any base) that uses its default scheduling ---
    best_with_default = None
    best_with_default_entry = None
    for entry in data:
        entry_default_openmp = get_default_openmp_config(entry['traversal'])
        if entry['openmp_config'] == entry_default_openmp:
            if best_with_default is None or entry['performance'] < best_with_default:
                best_with_default = entry['performance']
                best_with_default_entry = entry

    speedup_best_default = None
    if best_with_default is not None:
        speedup_best_default = best_with_default / optimal_performance
        best_default_config = get_default_openmp_config(best_with_default_entry['traversal'])
        print(f"\n{indent}  Best Algorithm with Default Scheduling:")
        print(f"{indent}    Traversal:   {best_with_default_entry['base_algorithm'][2]}")
        print(f"{indent}    OpenMP:      {best_default_config[0]},{best_default_config[1]}")
        print(f"{indent}    Performance: {best_with_default:,}")
        print(f"{indent}    Speedup vs best with default: {speedup_best_default:.3f}x")
        if speedup_best_default >= SIGNIFICANT_SPEEDUP_THRESHOLD:
            print(f"{indent}    *** SIGNIFICANT SPEEDUP: {speedup_best_default:.3f}x >= {SIGNIFICANT_SPEEDUP_THRESHOLD} ***")
    else:
        print(f"\n{indent}  Best Algorithm with Default Scheduling: NOT FOUND")

    return {
        'schedule_kind': optimal_schedule_kind.lower(),
        'chunk_size': optimal_chunk_size,
        'speedup_base_default': speedup_base_default,
        'speedup_best_default': speedup_best_default,
        'significant_base_default': speedup_base_default is not None and speedup_base_default >= SIGNIFICANT_SPEEDUP_THRESHOLD,
        'significant_best_default': speedup_best_default is not None and speedup_best_default >= SIGNIFICANT_SPEEDUP_THRESHOLD,
        'is_static1': optimal_schedule_kind.lower() == 'static' and optimal_chunk_size == '1',
    }


def analyze_file(filepath):
    """Analyze a single CSV file. Returns a stats dict for summary accumulation."""
    print(f"\n{'='*80}")
    print(f"File: {filepath}")
    print(f"{'='*80}")

    data = parse_csv_file(filepath)

    if not data:
        print("No valid data found in file.")
        return None

    stats_unrestricted = find_optimal_and_compare(
        data,
        "All Schedules (Unrestricted)",
    )
    stats_standard = find_optimal_and_compare(
        data,
        "Standard OpenMP Schedules (Static, Dynamic, Guided)",
        schedule_set=STANDARD_SCHEDULES,
    )
    stats_extended = find_optimal_and_compare(
        data,
        "Extended OpenMP Schedules (Standard + Auto, Static Steal, Trapezoidal)",
        schedule_set=EXTENDED_SCHEDULES,
    )

    print()
    return {
        'unrestricted': stats_unrestricted,
        'standard': stats_standard,
        'extended': stats_extended,
    }


def collect_schedule_counts(entries, cat_key):
    """
    Aggregate schedule/chunk statistics for a list of (first_level_dir, file_stats) entries.
    Returns a dict of counts.
    """
    schedule_counts: dict[str, int] = defaultdict(int)
    schedule_chunk_counts: dict[tuple, int] = defaultdict(int)
    sig_base_default_counts: dict[str, int] = defaultdict(int)
    sig_best_default_counts: dict[str, int] = defaultdict(int)
    chunk1_count = 0
    chunk_gt1_count = 0
    static1_count = 0
    total = 0

    for _, file_stats in entries:
        stats = file_stats.get(cat_key)
        if stats is None:
            continue
        total += 1
        kind = stats['schedule_kind']
        chunk = stats['chunk_size']
        schedule_counts[kind] += 1
        schedule_chunk_counts[(kind, chunk)] += 1
        if stats['significant_base_default']:
            sig_base_default_counts[kind] += 1
        if stats['significant_best_default']:
            sig_best_default_counts[kind] += 1
        if stats['is_static1']:
            static1_count += 1
        try:
            cs = int(chunk)
            if cs == 1:
                chunk1_count += 1
            elif cs > 1:
                chunk_gt1_count += 1
        except ValueError:
            pass

    return dict(
        schedule_counts=schedule_counts,
        schedule_chunk_counts=schedule_chunk_counts,
        sig_base_default_counts=sig_base_default_counts,
        sig_best_default_counts=sig_best_default_counts,
        chunk1_count=chunk1_count,
        chunk_gt1_count=chunk_gt1_count,
        static1_count=static1_count,
        total=total,
    )


def print_schedule_breakdown(counts, indent="  ", show_sig=False):
    """Print (1) schedule+chunk pairs, (2) schedule totals, (3) chunk-size-1 vs >1."""
    total = counts['total']
    print(f"{indent}Total CSVs with data: {total}")

    if total == 0:
        return

    print(f"\n{indent}Times each schedule+chunk pair is optimal:")
    for (kind, chunk), count in sorted(counts['schedule_chunk_counts'].items(), key=lambda x: -x[1]):
        pair = f"{kind},{chunk}"
        print(f"{indent}  {pair:<26s}: {count}")

    print(f"\n{indent}Times each scheduling kind is optimal:")
    for kind, count in sorted(counts['schedule_counts'].items(), key=lambda x: -x[1]):
        print(f"{indent}  {kind:<20s}: {count}")

    print(f"\n{indent}Chunk size == 1 chosen: {counts['chunk1_count']} / {total}")
    print(f"{indent}Chunk size  > 1 chosen: {counts['chunk_gt1_count']} / {total}")

    if show_sig:
        print(
            f"\n{indent}Times a scheduling kind is optimal with significant speedup"
            f" (>= {SIGNIFICANT_SPEEDUP_THRESHOLD}x) vs optimal base with default scheduling:"
        )
        if counts['sig_base_default_counts']:
            for kind, count in sorted(counts['sig_base_default_counts'].items(), key=lambda x: -x[1]):
                print(f"{indent}  {kind:<20s}: {count}")
        else:
            print(f"{indent}  (none)")

        print(
            f"\n{indent}Times a scheduling kind is optimal with significant speedup"
            f" (>= {SIGNIFICANT_SPEEDUP_THRESHOLD}x) vs best algorithm with default scheduling:"
        )
        if counts['sig_best_default_counts']:
            for kind, count in sorted(counts['sig_best_default_counts'].items(), key=lambda x: -x[1]):
                print(f"{indent}  {kind:<20s}: {count}")
        else:
            print(f"{indent}  (none)")

        print(
            f"\n{indent}Times a base-algorithm restricted to static,1 is optimal:"
            f" {counts['static1_count']} / {total}"
        )


def print_summary(all_file_stats):
    """Print the overall summary report across all processed CSV files.

    all_file_stats: list of (first_level_dir, file_stats_dict)
    """
    print(f"\n{'='*80}")
    print("OVERALL SUMMARY REPORT")
    print(f"{'='*80}")

    by_dir: dict[str, list] = defaultdict(list)
    for entry in all_file_stats:
        first_level, _ = entry
        by_dir[first_level].append(entry)

    categories = [
        ('unrestricted', 'All Schedules (Unrestricted)'),
        ('standard',     'Standard OpenMP Schedules (Static, Dynamic, Guided)'),
        ('extended',     'Extended OpenMP Schedules (Standard + Auto, Static Steal, Trapezoidal)'),
    ]

    for cat_key, cat_label in categories:
        print(f"\n--- {cat_label} ---")

        for dir_name in sorted(by_dir):
            print(f"\n  [Directory: {dir_name}]")
            counts = collect_schedule_counts(by_dir[dir_name], cat_key)
            print_schedule_breakdown(counts, indent="    ")

        print(f"\n  [Overall Total]")
        counts = collect_schedule_counts(all_file_stats, cat_key)
        print_schedule_breakdown(counts, indent="    ", show_sig=True)


def main():
    if len(sys.argv) < 2:
        print("Usage: python processData.py <base_directory>")
        sys.exit(1)

    base_dir = Path(sys.argv[1]).resolve()

    if not base_dir.is_dir():
        print(f"Error: {base_dir} is not a valid directory")
        sys.exit(1)

    print(f"Searching for CSV files in: {base_dir}")
    csv_files = find_csv_files(str(base_dir))

    if not csv_files:
        print("No matching CSV files found.")
        sys.exit(0)

    print(f"Found {len(csv_files)} CSV file(s)")

    all_file_stats = []  # list of (first_level_dir, stats_dict)
    for csv_file in sorted(csv_files):
        rel = Path(csv_file).resolve().relative_to(base_dir)
        first_level = rel.parts[0] if len(rel.parts) > 1 else "."
        try:
            stats = analyze_file(csv_file)
            if stats is not None:
                all_file_stats.append((first_level, stats))
        except Exception as e:
            print(f"\n{'='*80}")
            print(f"ERROR processing file: {csv_file}")
            print(f"Error message: {e}")
            print(f"{'='*80}\n")

    print_summary(all_file_stats)


if __name__ == "__main__":
    main()
