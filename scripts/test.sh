#!/bin/bash
set -e
# Run all tests
# Prerequisite: pip install -e ".[dev]"

echo "Running tests..."
python -m pytest tests/ -v
echo "Tests completed."
