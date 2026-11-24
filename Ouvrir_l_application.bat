@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
title ERGOVA Prospection - laisse cette fenetre ouverte

rem --- 1. Python est-il installe ? ---
where python >nul 2>nul
if errorlevel 1 (
  echo.
  echo  Python n'est pas installe sur ce PC.
  echo.
  echo  1. Telecharge-le ici : https://www.python.org/downloads/
  echo  2. Pendant l'installation, COCHE la case "Add python.exe to PATH"
  echo  3. Relance ce fichier.
  echo.
  start "" "https://www.python.org/downloads/"
  pause
  exit /b
)

rem --- 2. Installation automatique des modules au premier lancement ---
python -c "import requests, openpyxl" >nul 2>nul
if errorlevel 1 (
  echo Premier lancement : installation des modules necessaires...
  python -m pip install --user -r requirements.txt
  if errorlevel 1 (
    echo.
    echo  L'installation a echoue. Verifie ta connexion Internet puis relance.
    pause
    exit /b
  )
)

rem --- 3. Lancement ---
python app_web.py
pause
