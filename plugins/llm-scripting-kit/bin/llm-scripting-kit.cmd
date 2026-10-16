@echo off
rem llm-scripting-kit -- Windows shim invoking the bundled CLI.
rem
rem Interpreter preference:
rem   1. the plugin venv bootstrap provisions -- it has PyYAML, which the CLI
rem      needs to read the layered config.yaml (bootstrap_lib.config_resolve).
rem   2. the standalone Python bootstrap installs -- no third-party packages, so
rem      the CLI degrades to the shipped model baseline (it warns and continues).
rem   3. anything on PATH.
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
set "CLI=%PLUGIN_ROOT%\scripts\llm_scripting_kit_cli.py"
set "DATA_DIR=%USERPROFILE%\.claude\plugins\data\plugins-kit\llm-scripting-kit"
set "VENV_PY=%DATA_DIR%\.venv\Scripts\python.exe"
rem CLAUDE_BOOTSTRAP_DATA_ROOT is set only for a session that redirects bootstrap's
rem data tree (scripts\claude_plugin_test.py). When it is set, this plugin's venv is
rem the one under that tree and nothing else: a missing redirected venv exits 2
rem rather than falling back to the production venv, which holds the published
rem release. When it is unset the chain below is unchanged.
if defined CLAUDE_BOOTSTRAP_DATA_ROOT set "VENV_PY=%CLAUDE_BOOTSTRAP_DATA_ROOT%\plugins-kit\llm-scripting-kit\.venv\Scripts\python.exe"
if defined CLAUDE_BOOTSTRAP_DATA_ROOT if not exist "%VENV_PY%" goto :redirect_missing
set "STANDALONE_PY=%USERPROFILE%\.local\share\python-standalone\python\python.exe"

set "PY="
if exist "%VENV_PY%" set "PY=%VENV_PY%"
if not defined PY if exist "%STANDALONE_PY%" set "PY=%STANDALONE_PY%"
rem BOOTSTRAP_PYTHON is accepted only as a fallback, and only when it names an
rem existing file under the standalone install directory -- never a bare PATH
rem lookup, which is how the Windows Store stub gets picked up.
set "_STANDALONE_DIR=%USERPROFILE%\.local\share\python-standalone\"
if not defined PY if defined BOOTSTRAP_PYTHON if exist "%BOOTSTRAP_PYTHON%" (
    rem Either slash direction, since the persisted value uses "/"; any case;
    rem and no ".." anywhere after the directory prefix.
    set "_BP=!BOOTSTRAP_PYTHON:/=\!"
    set "_TRIMMED=!_BP:*%_STANDALONE_DIR%=!"
    if /I "!_BP!"=="!_STANDALONE_DIR!!_TRIMMED!" if "!_TRIMMED:..=!"=="!_TRIMMED!" set "PY=%BOOTSTRAP_PYTHON%"
)
if not defined PY (
    where python.exe >nul 2>&1
    if errorlevel 1 (
        echo llm-scripting-kit: no Python interpreter found 1>&2
        exit /b 1
    )
    set "PY=python.exe"
)

"%PY%" "%CLI%" %*
exit /b %ERRORLEVEL%

:cached_copy
echo llm-scripting-kit: refusing to run the cached copy at %_PR%: CLAUDE_PLUGIN_TEST is set, so this session tests the working copy and the cached copy is the INSTALLED release. Run the working copy's bin\llm-scripting-kit.cmd. 1>&2
exit /b 2

:redirect_missing
echo llm-scripting-kit: CLAUDE_BOOTSTRAP_DATA_ROOT redirects bootstrap's data tree, but the redirected plugin interpreter is missing at %VENV_PY%; refusing to fall back to the production venv. 1>&2
exit /b 2
