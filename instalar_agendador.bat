@echo off
:: instalar_agendador.bat
:: Configura o Agendador de Tarefas do Windows para:
::   - monitorar_docs.py    -> todo dia as 07:00 (novas NTs gov.br)
::   - atualizar_schemas.py -> todo dia as 07:10 (novos XSDs SEFAZ)
::
:: Execute este arquivo como ADMINISTRADOR (botao direito > Executar como administrador)

echo ============================================
echo  NFS-e Validador - Agendador de Tarefas
echo ============================================
echo.

:: Detectar pasta onde este .bat esta
set PASTA=%~dp0
if "%PASTA:~-1%"=="\" set PASTA=%PASTA:~0,-1%

:: Verificar Python
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo ERRO: Python nao encontrado no PATH.
    echo Instale em python.org marcando "Add to PATH".
    pause
    exit /b 1
)
for /f "tokens=*" %%i in ('where python') do set PYTHON=%%i

echo Python : %PYTHON%
echo Pasta  : %PASTA%
echo.

:: Remover tarefas antigas
schtasks /delete /tn "NFS-e Monitor Docs"    /f >nul 2>nul
schtasks /delete /tn "NFS-e Atualizar XSD"   /f >nul 2>nul

:: Tarefa 1: monitorar_docs.py - todo dia as 07:00
echo [1/2] Agendando monitorar_docs.py (todo dia 07:00)...
schtasks /create ^
    /tn "NFS-e Monitor Docs" ^
    /tr "\"%PYTHON%\" \"%PASTA%\monitorar_docs.py\"" ^
    /sc DAILY ^
    /st 07:00 ^
    /ru "%USERNAME%" ^
    /f ^
    /rl HIGHEST

if %errorlevel% equ 0 (
    echo     OK - monitorar_docs.py agendado
) else (
    echo     ERRO - execute como Administrador
    goto :erro
)

:: Tarefa 2: atualizar_schemas.py - todo dia as 07:10
echo [2/2] Agendando atualizar_schemas.py (todo dia 07:10)...
schtasks /create ^
    /tn "NFS-e Atualizar XSD" ^
    /tr "\"%PYTHON%\" \"%PASTA%\atualizar_schemas.py\"" ^
    /sc DAILY ^
    /st 07:10 ^
    /ru "%USERNAME%" ^
    /f ^
    /rl HIGHEST

if %errorlevel% equ 0 (
    echo     OK - atualizar_schemas.py agendado
) else (
    echo     ERRO - execute como Administrador
    goto :erro
)

echo.
echo ============================================
echo  Agendamento configurado com sucesso!
echo ============================================
echo.
echo  Tarefa 1: monitorar_docs.py    - todo dia 07:00
echo  Tarefa 2: atualizar_schemas.py - todo dia 07:10
echo.
echo  O sistema vai verificar automaticamente:
echo    * Novas NTs no portal gov.br/nfse
echo    * Novos schemas XSD da SEFAZ
echo  Tudo sem precisar reiniciar o servidor.
echo.

:: Executar os dois agora para testar
echo Executando monitorar_docs.py agora para testar...
echo.
"%PYTHON%" "%PASTA%\monitorar_docs.py"
echo.
echo Executando atualizar_schemas.py agora para testar...
echo.
"%PYTHON%" "%PASTA%\atualizar_schemas.py"

goto :fim

:erro
echo.
echo ============================================
echo  ERRO: Execute como Administrador
echo ============================================
echo  Botao direito no .bat ^> Executar como administrador
echo.

:fim
echo.
echo Pressione qualquer tecla para fechar...
pause >nul
