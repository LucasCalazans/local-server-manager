@echo off
REM Gera a pasta `dist\ServerAppManager\` contendo ServerAppManager.exe + _internal\.
REM Usamos --onedir (em vez de --onefile) por robustez: nao extrai DLLs em %TEMP%
REM a cada boot, entao nao sofre de race com Defender e starta mais rapido.
cd /d "%~dp0"
python -m pip install -r requirements.txt
python -m pip install pyinstaller
pyinstaller --noconfirm --windowed --collect-data qtawesome --hidden-import PySide6.QtNetwork --name "ServerAppManager" main.py
echo.
echo Pronto: dist\ServerAppManager\ServerAppManager.exe
