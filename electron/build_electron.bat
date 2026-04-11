@echo off
cd /d "%~dp0"
title NFS-e Validador - Build e Publicar

echo.
echo ================================================
echo   NFS-e Validador - Build + Publicar no GitHub
echo ================================================
echo.

node --version >nul 2>&1
if errorlevel 1 (echo [ERRO] Node.js nao encontrado & pause & exit /b 1)
for /f "tokens=*" %%v in ('node --version 2^>^&1') do echo   Node.js: %%v

gh --version >nul 2>&1
if errorlevel 1 (
    echo [AVISO] Instalando GitHub CLI...
    winget install GitHub.cli --silent
)

gh auth status >nul 2>&1
if errorlevel 1 (
    echo.
    echo [AUTH] Faca login no GitHub:
    gh auth login
    if errorlevel 1 (echo [ERRO] Login falhou & pause & exit /b 1)
)
echo   GitHub CLI: OK

for /f "tokens=2 delims=:, " %%v in ('findstr /i "\"version\"" package.json') do set RAW_VER=%%v
set APP_VER=%RAW_VER:"=%
echo   Versao: %APP_VER%

set EXE_NAME=NFS-e-Validador-Setup-%APP_VER%.exe
set BLK_NAME=NFS-e-Validador-Setup-%APP_VER%.exe.blockmap

echo   Arquivo: %EXE_NAME%

set CSC_IDENTITY_AUTO_DISCOVERY=false
set WIN_CSC_LINK=
set CSC_LINK=

echo.
echo [1/4] Preparando icone...
if not exist build mkdir build
if exist ..\nfse.ico (
    copy /y ..\nfse.ico build\nfse.ico >nul
    echo        OK.
) else (
    cd ..
    python gerar_icone.py
    cd electron
    copy /y ..\nfse.ico build\nfse.ico >nul
)

echo.
echo [2/4] Instalando dependencias npm...
call npm install
if errorlevel 1 (echo [ERRO] npm install falhou & pause & exit /b 1)
echo        OK.

echo.
echo [3/4] Compilando instalador v%APP_VER%...
echo        Aguarde 5-10 minutos...
if exist dist rmdir /s /q dist >nul 2>&1
call npm run build
if errorlevel 1 (echo [ERRO] Build falhou & pause & exit /b 1)

if not exist "dist\%EXE_NAME%" (
    echo [ERRO] Setup nao gerado: dist\%EXE_NAME%
    pause & exit /b 1
)
echo        OK: %EXE_NAME%

echo.
echo [4/4] Publicando no GitHub Release v%APP_VER%...
cd dist

gh release create "v%APP_VER%" "%EXE_NAME%" "%BLK_NAME%" "latest.yml" --title "NFS-e Validador v%APP_VER%" --notes "NFS-e Validador v%APP_VER%" --repo XMLVariavel/nfse-validador

if errorlevel 1 (
    echo.
    echo [AVISO] Publicacao falhou - release v%APP_VER% pode ja existir.
    echo         Delete o release no GitHub e tente novamente.
    cd ..
    pause & exit /b 1
)

cd ..

echo.
echo ================================================
echo   CONCLUIDO! v%APP_VER% publicado no GitHub
echo ================================================
echo.
echo   Arquivo publicado: %EXE_NAME%
echo   Os apps instalados vao detectar automaticamente.
echo.
pause
