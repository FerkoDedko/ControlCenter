@echo off
cd /d "%~dp0"
if not exist ".venv" (
    py -3.13 -m venv .venv 2>nul || py -3.12 -m venv .venv 2>nul || py -m venv .venv
)
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\pip.exe install -r requirements.txt -r requirements-optional.txt pyinstaller customtkinter
.venv\Scripts\pyinstaller.exe --noconfirm --clean CommandCenter.spec
echo.
set ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe
if not exist "%ISCC%" set ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe
if exist "%ISCC%" (
    "%ISCC%" installer.iss
    echo Installer: installer_output\CommandCenter_Setup.exe
) else (
    echo Inno Setup not found - skipping the installer. Get it free from jrsoftware.org
)
echo Done. Your app is in dist\CommandCenter\CommandCenter.exe  (zip the whole CommandCenter folder to share it)
pause
