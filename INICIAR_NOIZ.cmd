@echo off
setlocal
cd /d "%~dp0"
where uv >nul 2>nul
if errorlevel 1 (
    echo No se encontro uv. Instala uv siguiendo:
    echo https://docs.astral.sh/uv/getting-started/installation/
    echo Cierra y vuelve a abrir esta ventana despues de instalarlo.
    pause
    exit /b 1
)
echo Preparando Noiz Transmission 0.2...
uv sync --locked --extra desktop
if errorlevel 1 goto error
uv run --locked --extra desktop noiz-transmission
if errorlevel 1 goto error
exit /b 0
:error
echo.
echo No se pudo iniciar. Conserva el mensaje anterior para diagnosticarlo.
pause
exit /b 1
