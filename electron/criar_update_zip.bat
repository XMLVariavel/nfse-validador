@echo off
:: ============================================================
:: criar_update_zip.bat
:: Gera o ZIP delta com apenas os arquivos que mudam entre versoes
:: Chamado automaticamente pelo build_electron.bat
:: ============================================================

set APP_VER=%1
if "%APP_VER%"=="" (echo [ERRO] Versao nao informada & exit /b 1)

set ZIP_NAME=update-%APP_VER%.zip
set UNPACKED=dist\win-unpacked

echo [ZIP] Criando delta update-%APP_VER%.zip...

:: Criar pasta temp para o ZIP
if exist dist\update_tmp rmdir /s /q dist\update_tmp
mkdir dist\update_tmp
mkdir dist\update_tmp\resources
mkdir dist\update_tmp\resources\app

:: Copiar apenas os arquivos que mudam entre versoes
:: app.asar — codigo principal do Electron (sempre muda)
copy /y "%UNPACKED%\resources\app.asar" "dist\update_tmp\resources\" >nul

:: Scripts Python (mudam quando ha logica nova)
copy /y "%UNPACKED%\resources\app\server.py"            "dist\update_tmp\resources\app\" >nul
copy /y "%UNPACKED%\resources\app\launcher.py"          "dist\update_tmp\resources\app\" >nul 2>&1
copy /y "%UNPACKED%\resources\app\monitorar_docs.py"    "dist\update_tmp\resources\app\" >nul 2>&1
copy /y "%UNPACKED%\resources\app\atualizar_schemas.py" "dist\update_tmp\resources\app\" >nul 2>&1

:: versao.json (sempre muda)
copy /y "%UNPACKED%\resources\app\versao.json" "dist\update_tmp\resources\app\" >nul

:: static/index.html (muda quando ha mudancas visuais)
mkdir dist\update_tmp\resources\app\static
copy /y "%UNPACKED%\resources\app\static\index.html" "dist\update_tmp\resources\app\static\" >nul

:: Compactar com PowerShell
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "Compress-Archive -Path 'dist\update_tmp\*' -DestinationPath 'dist\%ZIP_NAME%' -Force"

if errorlevel 1 (echo [ERRO] Falha ao criar ZIP & exit /b 1)

:: Limpar pasta temp
rmdir /s /q dist\update_tmp

:: Mostrar tamanho do ZIP
for %%F in ("dist\%ZIP_NAME%") do (
    set /a SIZE_KB=%%~zF/1024
    echo        OK: %ZIP_NAME% !SIZE_KB! KB
)

exit /b 0
