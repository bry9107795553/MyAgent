@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion

cd /d "%~dp0"

echo.
echo ============================================================
echo    MyAgent - Push to GitHub
echo    (Double-click tool, no command line knowledge needed)
echo ============================================================
echo.

REM ---------- Step 1: check git ----------
git --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Git is not installed or not in PATH.
    echo         Please install Git from https://git-scm.com/download/win
    echo.
    pause
    exit /b 1
)
echo [OK] Git found.

REM ---------- Step 2: check repo ----------
if not exist ".git" (
    echo [ERROR] This folder is not a git repository.
    echo         Expected: %CD%\.git
    echo.
    pause
    exit /b 1
)
echo [OK] Git repository found.

REM ---------- Step 3: show current commits ----------
echo.
echo ---------- Local commits (newest first) ----------
git log --oneline -8
echo --------------------------------------------------
echo.

REM ---------- Step 4: check remote ----------
set "HASREMOTE="
for /f "delims=" %%i in ('git remote 2^>nul') do set "HASREMOTE=%%i"

if defined HASREMOTE (
    echo [OK] Remote already configured:
    git remote -v
    echo.
    goto :DOPUSH
)

echo [!] No remote repository configured yet.
echo.
echo    Before continuing, create an EMPTY repository on GitHub:
echo      1. Open  https://github.com/new
echo      2. Repository name: MyAgent   (or any name you like)
echo      3. Choose Public
echo      4. IMPORTANT: do NOT check "Add a README file"
echo      5. Click "Create repository"
echo      6. Copy the URL shown, e.g.:
echo         https://github.com/YOURNAME/MyAgent.git
echo.
set /p REPOURL="Paste your repository URL here and press Enter: "

if "%REPOURL%"=="" (
    echo.
    echo [ABORT] No URL entered. Nothing was changed.
    echo.
    pause
    exit /b 1
)

git remote add origin "%REPOURL%"
if errorlevel 1 (
    echo [ERROR] Failed to add remote.
    pause
    exit /b 1
)
echo [OK] Remote added: %REPOURL%
echo.

:DOPUSH
REM ---------- Step 5: detect branch ----------
set "BRANCH="
for /f "delims=" %%b in ('git rev-parse --abbrev-ref HEAD 2^>nul') do set "BRANCH=%%b"
if "%BRANCH%"=="" set "BRANCH=main"
echo [INFO] Current branch: %BRANCH%
echo.

echo ============================================================
echo   Pushing now...
echo.
echo   A GitHub login window may pop up.
echo   Sign in with your GitHub account and allow access.
echo   This is normal and only happens the first time.
echo ============================================================
echo.

git push -u origin %BRANCH%

if errorlevel 1 (
    echo.
    echo ============================================================
    echo   [FAILED] Push did not succeed.
    echo.
    echo   Common causes:
    echo    - Login window was cancelled  -^> run this file again
    echo    - Wrong repository URL        -^> see "Reset" below
    echo    - Repo not empty on GitHub    -^> create a brand new empty one
    echo.
    echo   Reset the remote and try again:
    echo      git remote remove origin
    echo   Then double-click this file again.
    echo ============================================================
    echo.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo   [SUCCESS] Code pushed to GitHub!
echo.
git remote get-url origin
echo.
echo   Open the URL above in your browser to verify.
echo ============================================================
echo.
pause
