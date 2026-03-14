#!/bin/bash
set -e
# Build the project — install dependencies
# Prerequisite: Python 3.11+, uv or pip

echo "Installing dependencies..."
pip install -e ".[dev]"
echo "Build completed."
