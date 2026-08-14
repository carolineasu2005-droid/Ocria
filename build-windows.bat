@echo off
chcp 65001 >nul
setlocal

set "PROJECT_DIR=%~dp0"
cd /d "%PROJECT_DIR%"

if not exist "venv\Scripts\python.exe" (
    py -3.11 -m venv venv
    if errorlevel 1 exit /b 1
)

"venv\Scripts\python.exe" -m pip install -r requirements.txt -r requirements-ocr.txt -r requirements-build.txt
if errorlevel 1 exit /b 1

"venv\Scripts\python.exe" -m unittest discover -s tests -v
if errorlevel 1 exit /b 1

"venv\Scripts\python.exe" -m PyInstaller --clean --noconfirm BossOCR.spec
if errorlevel 1 exit /b 1

rem Safe smoke test: no keywords, no forwarding, and no BOSS window interaction.
"dist\Ocria\Ocria.exe" --no-forward --auto --duration-seconds 0
if errorlevel 1 exit /b 1

if not exist "release" mkdir "release"
if exist "release\Ocria-Am7-Windows-x64.zip" del /q "release\Ocria-Am7-Windows-x64.zip"
powershell -NoProfile -Command "Compress-Archive -Path 'dist\Ocria\*' -DestinationPath 'release\Ocria-Am7-Windows-x64.zip' -CompressionLevel Optimal"
if errorlevel 1 exit /b 1

certutil -hashfile "release\Ocria-Am7-Windows-x64.zip" SHA256
echo.
echo Build completed: release\Ocria-Am7-Windows-x64.zip

endlocal
