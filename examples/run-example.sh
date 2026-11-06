#!/bin/sh
# Run the checker on the bundled examples.
# Run from the repo root: sh examples/run-example.sh
# The check run exits 1 because three example names fail on purpose —
# that is the expected result here.
set -e
cd "$(dirname "$0")/.."
echo "--- check the sample list ---"
python3 src/branch_name_checker.py --file examples/branches.txt || true
echo "--- one good name, one bad name ---"
python3 src/branch_name_checker.py feature/add-login BadBranchName || true
echo "--- the same list, with the example config ---"
python3 src/branch_name_checker.py --config examples/config.json --file examples/branches.txt || true
