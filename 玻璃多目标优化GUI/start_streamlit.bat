@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo ================================================================
echo   MGEA - Streamlit App
echo ================================================================
echo.

REM Find Rscript - try all common locations
set RSCRIPT=

REM 1. Try Windows registry (R install path)
for /f "tokens=2*" %%a in ('reg query "HKLM\SOFTWARE\R-core\R64" /v "InstallPath" 2^>nul') do set "R_HOME=%%b"
if defined R_HOME if exist "%R_HOME%\bin\Rscript.exe" set "RSCRIPT=%R_HOME%\bin\Rscript.exe"

REM 2. Try registry for current user
if not defined RSCRIPT (
    for /f "tokens=2*" %%a in ('reg query "HKCU\SOFTWARE\R-core\R64" /v "InstallPath" 2^>nul') do set "R_HOME=%%b"
    if defined R_HOME if exist "%R_HOME%\bin\Rscript.exe" set "RSCRIPT=%R_HOME%\bin\Rscript.exe"
)

REM 3. Search Program Files for any R-x.x.x
if not defined RSCRIPT (
    for /d %%i in ("C:\Program Files\R\R-*") do (
        if exist "%%i\bin\Rscript.exe" set "RSCRIPT=%%i\bin\Rscript.exe"
    )
)

REM 4. Search user-local AppData
if not defined RSCRIPT (
    for /d %%i in ("%LOCALAPPDATA%\Programs\R\R-*") do (
        if exist "%%i\bin\Rscript.exe" set "RSCRIPT=%%i\bin\Rscript.exe"
    )
)

REM 5. Also try C:\R
if not defined RSCRIPT (
    for /d %%i in ("C:\R\R-*") do (
        if exist "%%i\bin\Rscript.exe" set "RSCRIPT=%%i\bin\Rscript.exe"
    )
)

REM 6. Fallback: PATH
if not defined RSCRIPT (
    where Rscript.exe >nul 2>&1
    if not errorlevel 1 set RSCRIPT=Rscript.exe
)

if defined RSCRIPT (
    echo   Found R: %RSCRIPT%
    set MGEA_RSCRIPT=%RSCRIPT%
) else (
    echo   Auto-detection failed.
    echo   Please enter the full path to Rscript.exe:
    echo   ^(e.g. C:\Program Files\R\R-4.4.0\bin\Rscript.exe^)
    echo.
    set /p "RSCRIPT=Path: "
    if exist "!RSCRIPT!" (
        set MGEA_RSCRIPT=!RSCRIPT!
    ) else (
        echo.
        echo   [ERROR] Invalid path. R must be installed first.
        echo   https://cran.r-project.org/
        pause
        exit /b 1
    )
)

echo.
echo   Installing Python packages...
pip install streamlit pandas numpy plotly -q 2>nul

REM Clean temp files from previous runs
if exist "job_queue" rmdir /s /q "job_queue"
del /q tmp*.json 2>nul

echo.
echo   Starting MGEA Streamlit App...
echo   Browser will open at http://localhost:8501
echo   Press Ctrl+C to stop
echo ================================================================

streamlit run mgea_app.py
pause
