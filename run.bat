@echo off
REM Inicia o gerenciador em modo desenvolvimento (precisa de Python + PySide6).
REM Usa pythonw.exe pra rodar sem janela de console; cai pra python.exe se faltar.
cd /d "%~dp0"
where pythonw >nul 2>nul && (
    start "" pythonw -m server_app_manager
) || (
    python -m server_app_manager
)
