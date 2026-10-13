@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title K-Bond 수집기

rem Python 실행 명령을 안전하게 선택합니다. (&& 구문을 사용하지 않습니다.)
set "PY_EXE="
set "PY_ARGS="

if exist "%~dp0kbond_v3\.venv\Scripts\python.exe" (
    set "PY_EXE=%~dp0kbond_v3\.venv\Scripts\python.exe"
) else if exist "%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" (
    set "PY_EXE=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
) else (
    where python.exe >nul 2>nul
    if not errorlevel 1 set "PY_EXE=python.exe"
)

if not defined PY_EXE (
    where py.exe >nul 2>nul
    if not errorlevel 1 (
        set "PY_EXE=py.exe"
        set "PY_ARGS=-3"
    )
)

if not defined PY_EXE (
    echo [오류] Python을 찾을 수 없습니다. Python을 먼저 설치해 주세요.
    pause
    exit /b 1
)

echo Python: %PY_EXE% %PY_ARGS%
%PY_EXE% %PY_ARGS% -c "import requests, uiautomation, flask" >nul 2>nul
if errorlevel 1 (
    echo 필요한 구성요소를 처음 한 번 설치합니다...
    %PY_EXE% %PY_ARGS% -m pip install -r requirements.txt
    if errorlevel 1 (
        echo [오류] 구성요소 설치에 실패했습니다.
        pause
        exit /b 1
    )
)

echo 대시보드와 수집기를 시작합니다...
start "K-Bond Dashboard" /min "%PY_EXE%" %PY_ARGS% dashboard.py
timeout /t 2 /nobreak >nul
start "" http://127.0.0.1:5000
%PY_EXE% %PY_ARGS% kbond_scraper.py

echo 수집기가 종료되었습니다.
pause
