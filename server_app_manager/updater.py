"""Self-update do EXE: rebuilda via PyInstaller e troca o binario em execucao."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def is_frozen() -> bool:
    return getattr(sys, "frozen", False)


def installed_exe_path() -> Path | None:
    """Retorna o caminho do EXE em execucao se estiver frozen (PyInstaller)."""
    return Path(sys.executable) if is_frozen() else None


def find_python() -> str | None:
    """Acha um Python externo no PATH (necessario para rodar pyinstaller).

    Quando rodando frozen, `sys.executable` aponta pro EXE — nao serve.
    Tenta `python`, `py`, `python3` nessa ordem.
    """
    for candidate in ("python.exe", "py.exe", "python3.exe", "python", "py", "python3"):
        path = shutil.which(candidate)
        if path:
            # py.exe é launcher; precisa rodar como `py -3 -m ...` para garantir Python 3.
            if Path(path).name.lower().startswith("py.exe"):
                return path
            return path
    return None


def _py_argv(python: str, *args: str) -> list[str]:
    """Monta argv pra invocar Python (lida com py.exe vs python.exe)."""
    if Path(python).name.lower().startswith("py.exe"):
        return [python, "-3", *args]
    return [python, *args]


# Flag pra suprimir janelas de console em subprocess no Windows.
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class BuildError(RuntimeError):
    pass


def run_build(source_dir: Path, python: str, on_line) -> Path:
    """Roda pip install pyinstaller/PySide6 e depois `pyinstaller ... main.py`.

    Usa o modo `--onedir`: gera uma pasta com o EXE + DLLs lado a lado, em
    vez de um unico EXE que extrai tudo em %TEMP% a cada boot. Isso evita
    falhas tipo "Failed to load Python DLL" causadas por race no bootloader
    e/ou pelo Defender escanear o _MEI<random> recem-extraido.

    Args:
        source_dir: pasta com main.py
        python: caminho do Python externo (de find_python)
        on_line: callable invocado pra cada linha de output (str)

    Retorna o caminho da PASTA gerada (contendo o EXE e _internal/).
    """
    if not source_dir.exists():
        raise BuildError(f"Pasta do source nao encontrada: {source_dir}")
    if not (source_dir / "main.py").exists():
        raise BuildError(f"main.py nao encontrado em {source_dir}")

    def _stream(argv: list[str], label: str) -> int:
        on_line(f"[{label}] {' '.join(argv)}")
        proc = subprocess.Popen(
            argv,
            cwd=str(source_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            creationflags=_NO_WINDOW,
        )
        assert proc.stdout is not None
        for line in proc.stdout:
            on_line(line.rstrip())
        return proc.wait()

    rc = _stream(
        _py_argv(python, "-m", "pip", "install", "--upgrade",
                 "pip", "pyinstaller", "PySide6", "QtAwesome"),
        "pip",
    )
    if rc != 0:
        raise BuildError(f"pip install falhou (rc={rc})")

    rc = _stream(
        _py_argv(
            python, "-m", "PyInstaller", "--noconfirm", "--windowed",
            "--collect-data", "qtawesome",
            "--hidden-import", "PySide6.QtNetwork",
            "--name", "ServerAppManager", "main.py",
        ),
        "pyinstaller",
    )
    if rc != 0:
        raise BuildError(f"PyInstaller falhou (rc={rc})")

    out_dir = source_dir / "dist" / "ServerAppManager"
    exe = out_dir / "ServerAppManager.exe"
    if not exe.exists():
        raise BuildError(f"EXE nao foi gerado em {exe}")
    return out_dir


def install_and_relaunch(new_dir: Path, installed_exe: Path) -> None:
    """Substitui a pasta instalada inteira (--onedir) e relanca o EXE.

    new_dir: pasta gerada pelo PyInstaller (`dist/ServerAppManager/`)
    installed_exe: caminho do EXE atualmente em uso (dentro da install dir)

    Usa um script PowerShell auxiliar disparado detached. PowerShell eh mais
    confiavel que .bat (try/catch real, suporte nativo a UNC paths, logging
    estruturado). Tudo registrado em %TEMP%/appmgr-relaunch.log.
    """
    installed_dir = installed_exe.parent
    exe_name = installed_exe.name

    log_path = Path(tempfile.gettempdir()) / "appmgr-relaunch.log"
    ps_path = Path(tempfile.gettempdir()) / "appmgr-relaunch.ps1"

    # Log Python-side imediato — prova que chegamos aqui (caso o subprocess falhe)
    try:
        log_path.write_text(
            f"[python] install_and_relaunch chamado\n"
            f"[python] new_dir={new_dir}\n"
            f"[python] installed_exe={installed_exe}\n"
            f"[python] gerando script em {ps_path}\n",
            encoding="utf-8",
        )
    except Exception:
        pass

    # PowerShell script: taskkill + robocopy direto sobre install dir
    # (pula rename porque Defender/Search-Indexer seguram handle no dir
    # apos o EXE morrer — robocopy tem retry por arquivo, mais robusto).
    ps_script = f"""$ErrorActionPreference = 'Continue'
$LOG = '{log_path}'
$INSTALL_DIR = '{installed_dir}'
$EXE_NAME = '{exe_name}'
$NEW_DIR = '{new_dir}'

function Log($msg) {{
    "[$(Get-Date -Format 'HH:mm:ss.fff')] $msg" | Out-File -FilePath $LOG -Append -Encoding utf8
}}

Log "powershell iniciado"
Log "INSTALL_DIR=$INSTALL_DIR"
Log "NEW_DIR=$NEW_DIR"

# 1. Mata EXE e qualquer processo filho (tree kill).
Start-Sleep -Seconds 2
Log "esperou 2s; matando EXE e filhos"
$procName = [IO.Path]::GetFileNameWithoutExtension($EXE_NAME)
$pids = (Get-Process -Name $procName -ErrorAction SilentlyContinue).Id
foreach ($p in $pids) {{
    Log "taskkill /F /T /PID $p"
    Start-Process -FilePath taskkill.exe -ArgumentList "/F /T /PID $p" -NoNewWindow -Wait -ErrorAction SilentlyContinue | Out-Null
}}
Start-Sleep -Seconds 3
Log "esperou 3s pra Windows liberar handles"

# 2. robocopy /MIR direto sobre o install dir. Retry generoso por arquivo
#    individual (/R:60 /W:1 = 60 tentativas de 1s cada). /MIR copia tudo
#    do source + apaga arquivos extras no destino.
Log "robocopy /MIR $NEW_DIR -> $INSTALL_DIR (retry agressivo)"
$rc = (Start-Process -FilePath robocopy.exe `
    -ArgumentList "`"$NEW_DIR`" `"$INSTALL_DIR`" /MIR /NJH /NJS /NFL /NDL /R:60 /W:1" `
    -NoNewWindow -Wait -PassThru).ExitCode
# Robocopy: <8 = OK (mesmo com warnings); >=8 = falha real
Log "robocopy exit=$rc (0-7 = OK, 8+ = erro)"

# 3. Valida que o EXE existe E foi atualizado (hash bate com source)
$NEW_EXE = Join-Path $INSTALL_DIR $EXE_NAME
$SRC_EXE = Join-Path $NEW_DIR $EXE_NAME
if (-not (Test-Path $NEW_EXE)) {{
    Log "FAIL: $NEW_EXE sumiu apos copy"
    exit 1
}}
try {{
    $hashInstalled = (Get-FileHash $NEW_EXE -ErrorAction Stop).Hash
    $hashSource = (Get-FileHash $SRC_EXE -ErrorAction Stop).Hash
    if ($hashInstalled -ne $hashSource) {{
        Log "WARN: hash do EXE instalado nao bate com source"
        Log "  installed=$hashInstalled"
        Log "  source=$hashSource"
    }} else {{
        Log "hash do EXE bate com source - atualizacao OK"
    }}
}} catch {{
    Log "WARN: nao consegui comparar hash: $_"
}}

# 4. Lanca o EXE novo
Start-Sleep -Seconds 1
Log "lancando $NEW_EXE"
try {{
    Start-Process -FilePath $NEW_EXE -ErrorAction Stop
    Log "Start-Process retornou OK"
}} catch {{
    Log "FAIL ao lancar: $_"
    exit 1
}}

# Auto-cleanup do proprio script
Remove-Item -Path $PSCommandPath -Force -ErrorAction SilentlyContinue
"""
    # IMPORTANTE: utf-8-sig escreve com BOM, que o PowerShell respeita pra
    # detectar UTF-8 (senao ele assume cp1252 e quebra caracteres unicode).
    ps_path.write_text(ps_script, encoding="utf-8-sig")

    flags = (
        getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        | _NO_WINDOW
    )
    try:
        proc = subprocess.Popen(
            [
                "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
                "-WindowStyle", "Hidden",
                "-File", str(ps_path),
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=flags,
            close_fds=True,
        )
        with log_path.open("a", encoding="utf-8") as f:
            f.write(f"[python] Popen disparou powershell pid={proc.pid}\n")
    except Exception as exc:
        with log_path.open("a", encoding="utf-8") as f:
            f.write(f"[python] FAIL Popen: {exc!r}\n")
        raise
