#!/bin/bash
set -e
# Start the Game Theater dev server
# Prerequisite: npm install in frontend/

cd "$(dirname "$0")/../frontend"

echo "Starting Masquerade Theater (dev server)..."
echo "Open http://localhost:5173 in your browser"
echo ""

npx vite
