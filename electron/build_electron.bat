@echo off
cd /d "%~dp0"
title NFS-e Validador - Build e Publicar

echo.
echo ================================================
echo   NFS-e Validador - Build + Publicar no GitHub
echo ================================================
echo.

:: Verificar Node.js
node --version >nul 2>&1
if errorlevel 1 (echo [ERRO] Node.js nao encontrado & pause & exit /b 1)
for /f "tokens=*" %%v in ('node --version 2^>^&1') do echo   Node.js: %%v

:: Verificar GitHub CLI
gh --version >nul 2>&1
if errorlevel 1 (
    echo [AVISO] Instalando GitHub CLI...
    winget install GitHub.cli --silent
)

:: Verificar login GitHub
gh auth status >nul 2>&1
if errorlevel 1 (
    echo.
    echo [AUTH] Faca login no GitHub:
    gh auth login
    if errorlevel 1 (echo [ERRO] Login falhou & pause & exit /b 1)
)
echo   GitHub CLI: OK

:: Verificar Inno Setup
set INNO_PATH=
if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" set INNO_PATH=C:\Program Files (x86)\Inno Setup 6\ISCC.exe
if exist "C:\Program Files\Inno Setup 6\ISCC.exe"       set INNO_PATH=C:\Program Files\Inno Setup 6\ISCC.exe
if "%INNO_PATH%"=="" (
    echo.
    echo [AVISO] Inno Setup nao encontrado.
    echo         Baixe em: https://jrsoftware.org/isdl.php
    echo         Instale e rode este script novamente.
    pause & exit /b 1
)
echo   Inno Setup: OK

:: Pegar versao do package.json
for /f "tokens=2 delims=:, " %%v in ('findstr /i "\"version\"" package.json') do set RAW_VER=%%v
set APP_VER=%RAW_VER:"=%
echo   Versao: %APP_VER%

:: Nome do exe de saida
set EXE_NAME=NFS-e-Validador-Setup-%APP_VER%.exe

:: Desabilitar code signing
set CSC_IDENTITY_AUTO_DISCOVERY=false
set WIN_CSC_LINK=
set CSC_LINK=

:: [0] Sincronizar versao.json
echo.
echo [0/4] Sincronizando versao.json...
for /f "tokens=2 delims=-/ " %%a in ('echo %DATE%') do set _M=%%a
for /f "tokens=1 delims=-/ " %%a in ('echo %DATE%') do set _D=%%a
for /f "tokens=3 delims=-/ " %%a in ('echo %DATE%') do set _Y=%%a
echo {"versao": "%APP_VER%", "data": "%_Y%-%_M%-%_D%"} > ..\versao.json
echo        OK: versao.json = %APP_VER%

:: [1] Preparar icone
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

:: [2] npm install
echo.
echo [2/4] Instalando dependencias npm...
call npm install
if errorlevel 1 (echo [ERRO] npm install falhou & pause & exit /b 1)
echo        OK.

:: [3] Gerar win-unpacked (sem instalador NSIS)
echo.
echo [3/4] Compilando app v%APP_VER%...
echo        Aguarde 3-5 minutos...
if exist dist rmdir /s /q dist >nul 2>&1

:: npm run pack = electron-builder --dir (gera win-unpacked sem instalador)
call npm run pack
if errorlevel 1 (echo [ERRO] Build falhou & pause & exit /b 1)

if not exist "dist\win-unpacked\NFS-e Validador.exe" (
    echo [ERRO] win-unpacked nao gerado.
    pause & exit /b 1
)
echo        OK: dist\win-unpacked pronto

:: [3.5] Compilar instalador com Inno Setup
echo.
echo [3.5/4] Compilando instalador Inno Setup...
"%INNO_PATH%" "setup.iss" /DAppVersion=%APP_VER%
if errorlevel 1 (echo [ERRO] Inno Setup falhou & pause & exit /b 1)

if not exist "dist\%EXE_NAME%" (
    echo [ERRO] Instalador nao gerado: dist\%EXE_NAME%
    pause & exit /b 1
)
echo        OK: %EXE_NAME%

:: [3.6] Gerar ZIP delta
echo.
echo [3.6/4] Gerando ZIP delta para atualizacao rapida...
call criar_update_zip.bat %APP_VER%
if errorlevel 1 (echo [AVISO] ZIP delta falhou - continuando sem ele)

:: [4] Publicar no GitHub
echo.
echo [4/4] Publicando no GitHub Release v%APP_VER%...
cd dist

set RELEASE_FILES=%EXE_NAME%
if exist "update-%APP_VER%.zip" set RELEASE_FILES=%EXE_NAME% "update-%APP_VER%.zip"

gh release create "v%APP_VER%" ^
    %RELEASE_FILES% ^
    --title "NFS-e Validador v%APP_VER%" ^
    --notes "NFS-e Validador v%APP_VER%" ^
    --repo XMLVariavel/nfse-validador

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
echo   Instalador: dist\%EXE_NAME%
echo   Release:    https://github.com/XMLVariavel/nfse-validador/releases
echo.
pause
