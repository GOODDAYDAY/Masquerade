#!/bin/bash
set -e
# Run a complete game using default config
# Prerequisite: pip install -e ".[dev]" and set API key in .env

echo "Starting Masquerade game..."
python -m backend.main "$@"
