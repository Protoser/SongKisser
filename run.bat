@echo off
REM Set up the virtualenv (first run only), install deps, and start the bot.
setlocal

if not exist .venv (
    echo Creating virtual environment...
    python -m venv .venv
)

call .venv\Scripts\activate.bat
pip install -r requirements.txt
python main.py
