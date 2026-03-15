#!/bin/bash
set -e
# Run integration tests

cd "$(dirname "$0")/.."

echo "Running tests..."
echo "=== Spy Game Tests ==="
python -m backend.tests.test_spy_game
echo ""
echo "=== Blank Game Tests ==="
python -m backend.tests.test_blank_game
echo ""
echo "=== Script Pipeline Tests ==="
python -m backend.tests.test_script_pipeline
echo ""
echo "=== Werewolf AC Tests ==="
python -m backend.tests.verify_ac
echo ""
echo "All tests completed."
