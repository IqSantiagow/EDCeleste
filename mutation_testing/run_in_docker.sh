#!/usr/bin/env bash
# Runs run_mutmut.sh inside a Linux container, because mutmut does not run on Windows.
# Needs Docker Desktop running. Takes the same arguments as run_mutmut.sh:
#
#   bash mutation_testing/run_in_docker.sh                                       # whole project
#   bash mutation_testing/run_in_docker.sh src/edceleste/services/event_bus.py   # only these files
#
# The container works on a copy of the repo, uncommitted changes included,
# so mutmut never touches your files. The report lands in mutation_testing/report/.
#
# However the script ends, mutation_testing/report/done.txt then says "exit code N".
# A caller that runs the script in the background waits for that file.
set -euo pipefail
cd "$(dirname "$0")/.."

rm -rf mutation_testing/report
mkdir -p mutation_testing/report
trap 'echo "exit code $?" > mutation_testing/report/done.txt' EXIT

# `docker info` fails while Docker Desktop is not running. Never pipe it: the client part
# prints even when the engine is down, and a pipe hides the exit code.
if ! docker info > /dev/null 2>&1; then
    echo "Docker Desktop is not running. Start it, wait until the engine is up, then run this again." >&2
    exit 1
fi

# Git Bash would otherwise turn /repo into C:/Program Files/Git/repo
export MSYS_NO_PATHCONV=1
# Docker on Windows wants C:/... paths, `pwd -W` gives them in Git Bash
repo_path="$(pwd -W 2>/dev/null || pwd)"
image_name="edceleste-mutmut"

echo "Building $image_name image (the first build downloads a few GB and takes several minutes)..."
tar -cf - pyproject.toml mutation_testing/Dockerfile \
    | docker build --quiet -t "$image_name" -f mutation_testing/Dockerfile - > /dev/null

# The list of files is made here on the host, not in the container: in a git worktree the
# .git file points to a Windows path that git cannot open inside the container.
# A Windows checkout can have CRLF line endings, and bash in the container cannot run a
# script that has them ("set: pipefail\r: invalid option name"), so the CR is cut after the copy.
container_command="tar -xf - -C /work && cd /work && sed -i 's/\r\$//' mutation_testing/*.sh && bash mutation_testing/run_mutmut.sh \"\$@\""
git ls-files -z --cached --others --exclude-standard \
    | tar --null --ignore-failed-read -T - -cf - \
    | docker run --rm -i \
        -v "$repo_path/mutation_testing/report:/report" \
        -e REPORT_DIR=/report \
        -e MIN_MUTATION_SCORE \
        "$image_name" \
        bash -c "$container_command" bash "$@"
