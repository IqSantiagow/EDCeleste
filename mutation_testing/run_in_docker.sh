#!/usr/bin/env bash
# Runs run_mutmut.sh inside a Linux container, because mutmut does not run on Windows.
# Needs Docker Desktop running. Takes the same arguments as run_mutmut.sh:
#
#   bash mutation_testing/run_in_docker.sh                                       # whole project
#   bash mutation_testing/run_in_docker.sh src/edceleste/services/event_bus.py   # only these files
#
# The container works on a copy of the repo, uncommitted changes included,
# so mutmut never touches your files. The report lands in mutation_testing/report/.
set -euo pipefail
cd "$(dirname "$0")/.."

# Git Bash would otherwise turn /repo into C:/Program Files/Git/repo
export MSYS_NO_PATHCONV=1
# Docker on Windows wants C:/... paths, `pwd -W` gives them in Git Bash
repo_path="$(pwd -W 2>/dev/null || pwd)"
image_name="edceleste-mutmut"

echo "Building $image_name image (the first build downloads a few GB and takes several minutes)..."
tar -cf - pyproject.toml mutation_testing/Dockerfile \
    | docker build --quiet -t "$image_name" -f mutation_testing/Dockerfile - > /dev/null

rm -rf mutation_testing/report
mkdir -p mutation_testing/report

copy_repo_to_work='cd /repo && git ls-files -z --cached --others --exclude-standard | tar --null --ignore-failed-read -T - -cf - | tar -xf - -C /work'
docker run --rm \
    -v "$repo_path:/repo:ro" \
    -v "$repo_path/mutation_testing/report:/report" \
    -e REPORT_DIR=/report \
    -e MIN_MUTATION_SCORE \
    "$image_name" \
    bash -c "$copy_repo_to_work && cd /work && bash mutation_testing/run_mutmut.sh \"\$@\"" bash "$@"
