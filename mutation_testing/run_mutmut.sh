#!/usr/bin/env bash
# Runs mutmut and writes a short report. Linux only, mutmut needs fork.
# On Windows use run_in_docker.sh, it runs this script inside a Linux container.
#
#   bash mutation_testing/run_mutmut.sh                                       # whole project
#   bash mutation_testing/run_mutmut.sh src/edceleste/services/event_bus.py   # only these files
#
# Set MIN_MUTATION_SCORE (e.g. 75) to fail when the score is lower, CI does that.
#
# Report, in REPORT_DIR (default mutation_testing/report):
#   summary.txt      - mutation score and how many mutants were killed, survived, had no tests
#   survivors.txt    - every mutant the tests did not catch, with its diff
#   all_results.txt  - status of every mutant
#   mutmut_run.log   - full output of `mutmut run`
set -euo pipefail
cd "$(dirname "$0")/.."

report_dir="${REPORT_DIR:-mutation_testing/report}"

mutant_name_patterns=()
for source_file in "$@"; do
    # src/edceleste/services/event_bus.py -> edceleste.services.event_bus.*
    module_name="${source_file#src/}"
    module_name="${module_name%.py}"
    module_name="${module_name//\//.}"
    mutant_name_patterns+=("$module_name.*")
done

mkdir -p "$report_dir"
# mutmut prints a line per mutant, so its output goes to a log and is shown only on failure
if ! mutmut run --max-children "$(nproc)" "${mutant_name_patterns[@]}" > "$report_dir/mutmut_run.log" 2>&1; then
    # A file with only protocols or constants has no code to mutate
    if grep -q "Filtered for specific mutants, but nothing matches" "$report_dir/mutmut_run.log"; then
        echo "No mutants in the given files, nothing to test." | tee "$report_dir/summary.txt"
        exit 0
    fi
    tr '\r' '\n' < "$report_dir/mutmut_run.log" | tail -n 40
    exit 1
fi

mutmut results --all true > "$report_dir/all_results.txt"

# "not checked" are mutants outside the files given above
checked_count=$(grep -vc ": not checked$" "$report_dir/all_results.txt" || true)
caught_count=$(grep -cE ": (killed|timeout)$" "$report_dir/all_results.txt" || true)
mutation_score=$(awk -v caught="$caught_count" -v checked="$checked_count" \
    'BEGIN { printf "%.1f", checked ? 100 * caught / checked : 100 }')

{
    echo "mutation score: $caught_count/$checked_count = $mutation_score%"
    echo
    grep -v ": not checked$" "$report_dir/all_results.txt" | sed 's/.*: //' | sort | uniq -c
} > "$report_dir/summary.txt"

grep -E ": (survived|no tests)$" "$report_dir/all_results.txt" | while read -r result_line; do
    mutant_name="${result_line%%:*}"
    echo "=== $result_line"
    mutmut show "$mutant_name"
    echo
done > "$report_dir/survivors.txt" || true

cat "$report_dir/summary.txt"

if [ -n "${MIN_MUTATION_SCORE:-}" ] \
    && awk -v score="$mutation_score" -v min="$MIN_MUTATION_SCORE" 'BEGIN { exit !(score < min) }'; then
    echo
    echo "Mutation score $mutation_score% is below the required $MIN_MUTATION_SCORE%."
    echo "See mutation_testing/report/survivors.txt for the changes no test caught."
    exit 1
fi
