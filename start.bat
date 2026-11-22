@echo off
cd /d "%~dp0"
if not exist ".venv" (
    echo Setting up Command Center for the first run. This takes a minute...
    py -3.13 -m venv .venv 2>nul || py -3.12 -m venv .venv 2>nul || py -m venv .venv
    .venv\Scripts\python.exe -m pip install --upgrade pip
    .venv\Scripts\pip.exe install -r requirements.txt -r requirements-optional.txt
)
start "" .venv\Scripts\pythonw.exe main.py
