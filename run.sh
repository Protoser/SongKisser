#!/usr/bin/env bash
# Set up the virtualenv (first run only), install deps, and start the bot.
set -e

cd "$(dirname "$0")"

if [ ! -d .venv ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
fi

source .venv/bin/activate
pip install -r requirements.txt
python main.py
