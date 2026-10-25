@echo off
title Remote Wheel Server - Gamepad de Corrida
cd /d "%~dp0"
echo ========================================================
echo   Iniciando Remote Wheel (Servidor Mobile -^> PC Gamepad)
echo ========================================================
python server.py
pause
