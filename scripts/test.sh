#!/bin/bash
set -e
cd "$(dirname "$0")/.."

echo "========================================"
echo "  Masquerade - Run Tests"
echo "========================================"
echo ""

cd frontend
npx vitest run

echo ""
echo "========================================"
echo "  Tests: ALL PASSED"
echo "========================================"
