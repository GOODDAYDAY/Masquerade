#!/bin/bash
set -e
# Run integration tests

cd "$(dirname "$0")/.."

echo "Running tests..."
python -m backend.tests.test_spy_game
echo "Tests completed."
