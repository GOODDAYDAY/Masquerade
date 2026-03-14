#!/bin/bash
set -e
# Build the project — install backend + frontend dependencies
# Prerequisite: Python 3.11+, Node.js 18+

cd "$(dirname "$0")/.."

echo "=== Backend ==="
echo "Installing Python dependencies..."
pip install -e ".[dev,render]"

echo ""
echo "=== Frontend ==="
echo "Installing npm dependencies..."
cd frontend
npm install
echo "Building frontend..."
npx tsc -b
npx vite build
cd ..

echo ""
echo "Build completed."
