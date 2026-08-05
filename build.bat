@echo off
REM Gera a pasta `dist\ServerAppManager\` contendo ServerAppManager.exe + _internal\.
REM Usamos --onedir (em vez de --onefile) por robustez: nao extrai DLLs em %TEMP%
REM a cada boot, entao nao sofre de race com Defender e starta mais rapido.
cd /d "%~dp0"
python -m pip install -r requirements.txt
if errorlevel 1 goto :falhou
python -m pip install pyinstaller
if errorlevel 1 goto :falhou
REM `python -m PyInstaller` (e nao `pyinstaller`): o Scripts\ do Python pode nao
REM estar no PATH, e ai o executavel `pyinstaller` nao eh encontrado.
python -m PyInstaller --noconfirm --windowed --collect-data qtawesome --hidden-import PySide6.QtNetwork --name "ServerAppManager" main.py
if errorlevel 1 goto :falhou
echo.
echo Pronto: dist\ServerAppManager\ServerAppManager.exe
exit /b 0

:falhou
echo.
echo BUILD FALHOU - veja o erro acima.
exit /b 1
