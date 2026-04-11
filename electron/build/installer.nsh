; NFS-e Validador — customizações do instalador
; Este arquivo é incluído no script NSIS gerado pelo electron-builder

!macro customInstall
  ; Mostrar página de detalhes (arquivos sendo instalados)
  SetDetailsPrint both

  ; Encerrar versão anterior se estiver rodando
  DetailPrint "Verificando processos anteriores..."
  nsExec::Exec 'taskkill /F /IM "NFS-e Validador.exe" /T'
  Sleep 1000
  DetailPrint "Instalação iniciada."
!macroend

!macro customUnInstall
  SetDetailsPrint both
  DetailPrint "Encerrando NFS-e Validador..."
  nsExec::Exec 'taskkill /F /IM "NFS-e Validador.exe" /T'
  Sleep 1000
!macroend
