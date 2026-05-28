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


def print_summary(all_file_stats):
    """Print the overall summary report across all processed CSV files."""
    print(f"\n{'='*80}")
    print("OVERALL SUMMARY REPORT")
    print(f"{'='*80}")

    categories = [
        ('unrestricted', 'All Schedules (Unrestricted)'),
        ('standard',     'Standard OpenMP Schedules (Static, Dynamic, Guided)'),
        ('extended',     'Extended OpenMP Schedules (Standard + Auto, Static Steal, Trapezoidal)'),
    ]

    for cat_key, cat_label in categories:
        print(f"\n--- {cat_label} ---")

        schedule_counts: dict[str, int] = defaultdict(int)
        sig_base_default_counts: dict[str, int] = defaultdict(int)
        sig_best_default_counts: dict[str, int] = defaultdict(int)
        static1_count = 0
        total = 0

        for file_stats in all_file_stats:
            stats = file_stats.get(cat_key)
            if stats is None:
                continue
            total += 1
            kind = stats['schedule_kind']
            schedule_counts[kind] += 1
            if stats['significant_base_default']:
                sig_base_default_counts[kind] += 1
            if stats['significant_best_default']:
                sig_best_default_counts[kind] += 1
            if stats['is_static1']:
                static1_count += 1

        print(f"  Total CSVs with data: {total}")

        print(f"\n  Times each scheduling kind is optimal:")
        for kind, count in sorted(schedule_counts.items(), key=lambda x: -x[1]):
            print(f"    {kind:20s}: {count}")

        print(f"\n  Times a scheduling kind is optimal with significant speedup (>= {SIGNIFICANT_SPEEDUP_THRESHOLD}x)"
              f" vs optimal base with default scheduling:")
        if sig_base_default_counts:
            for kind, count in sorted(sig_base_default_counts.items(), key=lambda x: -x[1]):
                print(f"    {kind:20s}: {count}")
        else:
            print("    (none)")

        print(f"\n  Times a scheduling kind is optimal with significant speedup (>= {SIGNIFICANT_SPEEDUP_THRESHOLD}x)"
              f" vs best algorithm with default scheduling:")
        if sig_best_default_counts:
            for kind, count in sorted(sig_best_default_counts.items(), key=lambda x: -x[1]):
                print(f"    {kind:20s}: {count}")
        else:
            print("    (none)")

        print(f"\n  Times a base-algorithm restricted to static,1 is optimal: {static1_count} / {total}")


def main():
    if len(sys.argv) < 2:
        print("Usage: python processData.py <base_directory>")
        sys.exit(1)

    base_dir = sys.argv[1]

    if not os.path.isdir(base_dir):
        print(f"Error: {base_dir} is not a valid directory")
        sys.exit(1)

    print(f"Searching for CSV files in: {base_dir}")
    csv_files = find_csv_files(base_dir)

    if not csv_files:
        print("No matching CSV files found.")
        sys.exit(0)

    print(f"Found {len(csv_files)} CSV file(s)")

    all_file_stats = []
    for csv_file in sorted(csv_files):
        try:
            stats = analyze_file(csv_file)
            if stats is not None:
                all_file_stats.append(stats)
        except Exception as e:
            print(f"\n{'='*80}")
            print(f"ERROR processing file: {csv_file}")
            print(f"Error message: {e}")
            print(f"{'='*80}\n")

    print_summary(all_file_stats)


if __name__ == "__main__":
    main()
