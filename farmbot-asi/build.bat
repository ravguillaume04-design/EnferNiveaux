@echo off
title FarmBot ASI - Build
cd /d "%~dp0"

echo ============================================
echo   FarmBot ASI Plugin - Compilation
echo ============================================
echo.

:: ------------------------------------------------------------------ ::
::  Verifie que git est installe                                        ::
:: ------------------------------------------------------------------ ::
git --version >nul 2>&1
if errorlevel 1 (
    echo ERREUR : git n'est pas installe.
    echo Telechargez Git sur https://git-scm.com
    pause & exit /b 1
)

:: ------------------------------------------------------------------ ::
::  Clone les dependances si necessaire                                 ::
:: ------------------------------------------------------------------ ::
if not exist vendor mkdir vendor

if not exist vendor\imgui (
    echo [1/2] Telechargement ImGui...
    git clone --depth=1 https://github.com/ocornut/imgui.git vendor/imgui
    if errorlevel 1 (
        echo ERREUR lors du clone de ImGui.
        pause & exit /b 1
    )
)

if not exist vendor\minhook (
    echo [2/2] Telechargement MinHook...
    git clone --depth=1 https://github.com/TsudaKageyu/minhook.git vendor/minhook
    if errorlevel 1 (
        echo ERREUR lors du clone de MinHook.
        pause & exit /b 1
    )
)

echo Dependances OK.
echo.

:: ------------------------------------------------------------------ ::
::  CMake - detecte Visual Studio 2022 ou 2019                         ::
:: ------------------------------------------------------------------ ::
where cmake >nul 2>&1
if errorlevel 1 (
    echo ERREUR : cmake introuvable.
    echo Installez CMake depuis https://cmake.org ou via Visual Studio Installer.
    pause & exit /b 1
)

if not exist build mkdir build
cd build

echo Configuration CMake...
cmake .. -G "Visual Studio 17 2022" -A x64 2>nul
if errorlevel 1 (
    echo VS2022 introuvable, essai VS2019...
    cmake .. -G "Visual Studio 16 2019" -A x64
    if errorlevel 1 (
        echo ERREUR : aucun generateur Visual Studio trouve.
        echo Installez Visual Studio 2019 ou 2022 avec le composant "Developpement Desktop C++".
        cd ..
        pause & exit /b 1
    )
)

echo.
echo Compilation (Release x64)...
cmake --build . --config Release --parallel
if errorlevel 1 (
    echo.
    echo ERREUR de compilation. Lisez les messages ci-dessus.
    cd ..
    pause & exit /b 1
)

cd ..

:: ------------------------------------------------------------------ ::
::  Copie le .asi dans le dossier courant                               ::
:: ------------------------------------------------------------------ ::
if exist build\Release\FarmBot.asi (
    copy /Y build\Release\FarmBot.asi FarmBot.asi >nul
    echo.
    echo ============================================
    echo   BUILD OK : FarmBot.asi genere !
    echo ============================================
    echo.
    echo Instructions d'installation :
    echo  1. Copie FarmBot.asi dans :
    echo     %%LOCALAPPDATA%%\FiveM\FiveM.app\plugins\
    echo     (cree le dossier plugins\ s'il n'existe pas)
    echo  2. Lance FiveM et rejoins un serveur.
    echo  3. Presse Numpad + pour afficher le menu.
    echo.
) else (
    echo ERREUR : FarmBot.asi introuvable apres la compilation.
)

pause
