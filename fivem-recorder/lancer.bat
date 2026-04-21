@echo off
title FiveM Recorder - Installation et lancement
echo ============================================
echo   FiveM Movement Recorder
echo ============================================
echo.

:: Verifie que Python est installe
py --version >nul 2>&1
if errorlevel 1 (
    echo ERREUR : Python n'est pas installe.
    echo Telechargez-le sur https://www.python.org
    pause
    exit /b 1
)

:: Installe les dependances
echo Installation des dependances...
py -m pip install pynput psutil --quiet
if errorlevel 1 (
    echo ERREUR lors de l'installation des dependances.
    pause
    exit /b 1
)

echo Dependances OK.
echo.
echo Lancement de l'application...
echo.

:: Lance le script depuis le meme dossier que ce .bat
cd /d "%~dp0"
py fivem_recorder.py

pause
