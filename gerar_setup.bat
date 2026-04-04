@echo off
chcp 65001 >nul
title NFS-e Validador — Gerando Instalador

echo.
echo Gerando NFS-e_Validador_Setup.exe
echo Wizard visual de instalacao com 4 telas.
echo.

python --version >nul 2>&1
if errorlevel 1 (echo [ERRO] Python nao encontrado & pause & exit /b 1)
for /f "tokens=*" %%v in ('python --version 2^>^&1') do echo Python: %%v

echo.
echo [1/4] Instalando dependencias...
pip install pyinstaller pillow lxml --quiet --disable-pip-version-check
if errorlevel 1 (echo [ERRO] pip falhou & pause & exit /b 1)
echo       OK.

echo.
echo [2/4] Gerando icone (nfse.ico)...
python gerar_icone.py
if errorlevel 1 (echo [ERRO] gerar_icone.py falhou & pause & exit /b 1)
echo       OK.

if exist build  rmdir /s /q build  >nul 2>&1
if exist dist   rmdir /s /q dist   >nul 2>&1

echo.
echo [3/4] Compilando aplicativo (NFS-e Validador.exe)...
echo       Aguarde 3-5 min...
pyinstaller nfse_app.spec --noconfirm --clean
if errorlevel 1 (echo [ERRO] Falha app & pause & exit /b 1)
if not exist "dist\app\NFS-e Validador.exe" (echo [ERRO] exe nao gerado & pause & exit /b 1)
echo       App OK: dist\app\NFS-e Validador.exe

echo.
echo [4/4] Compilando instalador wizard (Setup.exe)...
echo       Aguarde mais 3-4 min...
pyinstaller nfse_setup.spec --noconfirm --clean
if errorlevel 1 (echo [ERRO] Falha setup & pause & exit /b 1)
if not exist "dist\NFS-e_Validador_Setup.exe" (echo [ERRO] Setup nao gerado & pause & exit /b 1)

echo.
echo ================================================
echo  CONCLUIDO COM SUCESSO!
echo  Arquivo gerado: dist\NFS-e_Validador_Setup.exe
echo ================================================
echo.
echo  Distribua APENAS esse arquivo para a equipe.
echo.
echo  Fluxo apos instalar:
echo    Atalho na Area de Trabalho
echo    rarr NFS-e Validador.exe
echo    rarr Servidor Python (porta 8000)
echo    rarr Chrome/Edge modo App (sem barra de endereco)
echo.
explorer dist
pause
