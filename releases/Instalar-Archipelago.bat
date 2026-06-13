@echo off
title Instalador del Mod Archipelago para Pokemon Infinite Fusion
color 0A

echo ==============================================================
echo   Instalador de Archipelago para Pokemon Infinite Fusion
echo ==============================================================
echo.
echo Este script instalara o actualizara los archivos de Archipelago
echo en tu juego de Pokemon Infinite Fusion.
echo.
echo Buscando la carpeta del juego...

:: Comprobar si estamos en la carpeta correcta (donde esta Game.exe o Data)
if not exist "Data\Scripts\" (
    color 0C
    echo.
    echo [ERROR] No se pudo encontrar la carpeta Data\Scripts.
    echo.
    echo Asegurate de poner este archivo .bat y la carpeta 998_Experimental
    echo DENTRO DE LA CARPETA PRINCIPAL DEL JUEGO ^(donde se encuentra Game.exe^).
    echo.
    pause
    exit /b
)

echo.
echo [INFO] Carpeta del juego encontrada.
echo Instalando los scripts de Archipelago en Data\Scripts\998_Experimental...
echo.

:: Copiar la carpeta 998_Experimental usando xcopy
xcopy /E /I /Y "998_Experimental" "Data\Scripts\998_Experimental"

echo.
if %ERRORLEVEL% EQU 0 (
    color 0A
    echo ==============================================================
    echo [EXITO] ¡La instalacion se ha completado correctamente!
    echo ==============================================================
    echo Ya puedes abrir el juego. Los cambios de Archipelago estan activos.
) else (
    color 0C
    echo ==============================================================
    echo [ERROR] Hubo un problema al copiar los archivos.
    echo ==============================================================
)
echo.
pause
