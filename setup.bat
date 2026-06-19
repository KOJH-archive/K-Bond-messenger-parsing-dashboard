@echo off
echo Checking Python (py launcher)...
py --version
if %errorlevel% neq 0 (
    echo [ERROR] Python not found. Please install Python.
    pause
    exit /b
)

echo Installing dependencies (uiautomation)...
py -m pip install -r requirements.txt
pause
