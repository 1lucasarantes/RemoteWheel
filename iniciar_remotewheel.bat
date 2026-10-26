@echo off
title Remote Wheel Server - Gamepad de Corrida
cd /d "%~dp0"
echo ========================================================
echo   Iniciando Remote Wheel (Servidor Mobile -^> PC Gamepad)
echo ========================================================

python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERRO] Python nao foi encontrado no sistema!
    echo Por favor instale o Python 3.10+ marcando a opcao "Add Python to PATH":
    echo https://www.python.org/downloads/
    pause
    exit /b 1
)

echo Verificando dependencias...
pip install -r requirements.txt --quiet

echo Iniciando servidor...
python server.py
pause
