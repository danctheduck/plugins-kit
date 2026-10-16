@echo off
:: UE Python Script Runner -- deterministic standalone-first launcher.
:: ue_runner.py re-execs into the plugin venv when bootstrap has provisioned it.
setlocal enabledelayedexpansion
set "SCRIPT_DIR=%~dp0"
set "STANDALONE_PY=%USERPROFILE%\.local\share\python-standalone\python\python.exe"
set "VENV_PY=%USERPROFILE%\.claude\plugins\data\plugins-kit\unreal-kit\.venv\Scripts\python.exe"

:: CLAUDE_BOOTSTRAP_DATA_ROOT is set only for a session that redirects bootstrap's
:: data tree (scripts\claude_plugin_test.py). Under it the plugin venv is the one
:: in that tree, and a missing redirected venv is a refusal: falling back to the
:: production venv would run the published release in a session meant to test the
:: working copy. Same exit code and message shape as bootstrap_guard's re-exec.
if defined CLAUDE_BOOTSTRAP_DATA_ROOT (
    set "_DATA_ROOT=!CLAUDE_BOOTSTRAP_DATA_ROOT:/=\!"
    set "VENV_PY=!_DATA_ROOT!\plugins-kit\unreal-kit\.venv\Scripts\python.exe"
    if not exist "!VENV_PY!" (
        echo [ue-runner] CLAUDE_BOOTSTRAP_DATA_ROOT redirects bootstrap data, but the redirected unreal-kit venv is missing: !VENV_PY! 1>&2
        echo [ue-runner] Run a bootstrap pass in this claudx session so it provisions unreal-kit into the redirected tree, then retry. Refusing to use the production venv. 1>&2
        exit /b 2
    )
)

set "PY="
if exist "%STANDALONE_PY%" set "PY=%STANDALONE_PY%"

:: BOOTSTRAP_PYTHON is accepted only as a validated fallback. It must resolve
:: under the deterministic standalone install directory; never use a bare PATH
:: name here, which can select the Windows Store alias stub.
set "_STANDALONE_DIR=%USERPROFILE%\.local\share\python-standalone\"
if not defined PY if defined BOOTSTRAP_PYTHON if exist "%BOOTSTRAP_PYTHON%" (
    rem Either slash direction, since the persisted value uses "/"; any case;
    rem and no ".." anywhere after the directory prefix.
    set "_BP=!BOOTSTRAP_PYTHON:/=\!"
    set "_TRIMMED=!_BP:*%_STANDALONE_DIR%=!"
    if /I "!_BP!"=="!_STANDALONE_DIR!!_TRIMMED!" if "!_TRIMMED:..=!"=="!_TRIMMED!" set "PY=%BOOTSTRAP_PYTHON%"
)

:: A provisioned plugin venv is the final deterministic local fallback. The
:: target script's guard will re-exec into it and validate its dependencies.
if not defined PY if exist "%VENV_PY%" set "PY=%VENV_PY%"

if not defined PY (
    echo [ue-runner] no usable Python interpreter found. 1>&2
    echo [ue-runner] Install/enable plugins-kit:bootstrap and start a new session so it can provision unreal-kit, then retry. 1>&2
    exit /b 3
)
"%PY%" "%SCRIPT_DIR%ue_runner.py" %*
exit /b %ERRORLEVEL%
