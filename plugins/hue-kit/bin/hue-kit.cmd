@echo off
rem hue-kit -- Windows shim launching the bundled CLI. The CLI re-execs itself
rem under the plugin's bootstrap-provisioned venv, so this only needs any Python.
setlocal enabledelayedexpansion
set "SCRIPT_DIR=%~dp0"
set "PLUGIN_ROOT=%SCRIPT_DIR%.."

rem Under claudx (CLAUDE_PLUGIN_TEST) the working copy is the plugin under test, so a
rem shim running from the plugin cache would run the INSTALLED release. Refuse it.
rem Same scope as bootstrap_lib.env_var_check.cache_root_refusal: only the cache of
rem CLAUDE_PLUGIN_TEST_MARKETPLACE is refused (every cache path when it is unset).
for %%I in ("%SCRIPT_DIR%..") do set "_PR=%%~fI\"
set "_CACHE_NEEDLE=\plugins\cache\"
if defined CLAUDE_PLUGIN_TEST_MARKETPLACE set "_CACHE_NEEDLE=\plugins\cache\%CLAUDE_PLUGIN_TEST_MARKETPLACE%\"
if defined CLAUDE_PLUGIN_TEST if not "!_PR:%_CACHE_NEEDLE%=!"=="!_PR!" goto :cached_copy
set "CLI=%PLUGIN_ROOT%\scripts\hue_kit_cli.py"
rem Prefer the standalone Python bootstrap installs (avoids the WindowsApps
rem Store-alias stub that `where python.exe` otherwise resolves to). The CLI
rem re-execs into the plugin venv itself, so this only needs a working launcher.
set "PY=%USERPROFILE%\.local\share\python-standalone\python\python.exe"

rem BOOTSTRAP_PYTHON is accepted only as a fallback, and only when it names an
rem existing file under the standalone install directory -- never a bare PATH
rem lookup, which is how the Windows Store stub gets picked up.
set "_STANDALONE_DIR=%USERPROFILE%\.local\share\python-standalone\"
if not exist "%PY%" if defined BOOTSTRAP_PYTHON if exist "%BOOTSTRAP_PYTHON%" (
    rem Either slash direction, since the persisted value uses "/"; any case;
    rem and no ".." anywhere after the directory prefix.
    set "_BP=!BOOTSTRAP_PYTHON:/=\!"
    set "_TRIMMED=!_BP:*%_STANDALONE_DIR%=!"
    if /I "!_BP!"=="!_STANDALONE_DIR!!_TRIMMED!" if "!_TRIMMED:..=!"=="!_TRIMMED!" set "PY=%BOOTSTRAP_PYTHON%"
)

if not exist "%PY%" (
    where python.exe >nul 2>&1
    if errorlevel 1 (
        echo hue-kit: no Python interpreter found 1>&2
        exit /b 1
    )
    set "PY=python.exe"
)

"%PY%" "%CLI%" %*
exit /b %ERRORLEVEL%

:cached_copy
echo hue-kit: refusing to run the cached copy at %_PR%: CLAUDE_PLUGIN_TEST is set, so this session tests the working copy and the cached copy is the INSTALLED release. Run the working copy's bin\hue-kit.cmd. 1>&2
exit /b 2
