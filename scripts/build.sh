#!/bin/bash
set -e
cd "$(dirname "$0")/.."

echo "========================================"
echo "  Masquerade - Build Check"
echo "========================================"
echo ""

echo "[1/2] TypeScript type check..."
cd frontend
npx tsc --noEmit
echo "TypeScript: OK"

echo ""
echo "[2/2] Vite build..."
npx vite build

echo ""
echo "========================================"
echo "  Build: ALL PASSED"
echo "========================================"
