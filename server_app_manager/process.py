"""Disparo e controle de processos no WSL a partir do Windows.

Estrategia de parada confiavel:
  - O comando do usuario roda num grupo de processos proprio (`set -m` + job
    em background), e o PID do lider do grupo eh gravado num pidfile em /tmp.
  - Parar envia o sinal para o grupo inteiro (`kill -- -PGID`), derrubando
    tambem os filhos (ex.: vite/esbuild disparados pelo `npm run dev`).
  - O status eh lido direto dos pidfiles, entao continua correto mesmo apos
    reiniciar a interface.

Por que o transporte do script eh tao chato:
  - `wsl.exe -- bash -lc "<script>"` NAO funciona: o wsl.exe expande variaveis
    `$VAR` no argv usando o env do Windows ANTES de entregar pro bash, o que
    corrompe `$HOME`, `$NVM_DIR`, `$!`, etc.
  - Passar o script via STDIN tambem nao eh trivial: o `bash -l` do WSL ignora
    stdin que contenha caractere `\n` (descoberta empirica) — so executa se
    receber uma unica linha terminada *sem* newline.
  - Solucao: codificar o script em base64, mandar via stdin como uma unica
    linha (`F=$(mktemp); echo <b64> | base64 -d > "$F"; bash -l "$F"`), e
    deixar o bash executar a partir do arquivo decodificado.
"""

from __future__ import annotations

import base64
import glob
import os
import socket
import subprocess
import sys
import tempfile
from urllib.parse import urlparse

from .config import Config, Service


def probe_url(url: str, timeout: float = 0.3) -> bool:
    """Retorna True se conseguiu abrir TCP na host:porta da URL.

    Usado para detectar servicos vivos cujo pidfile nao bate (ex.: comando
    `docker compose up -d` que termina rapido) ou processos legados que
    nao foram iniciados por essa sessao do app.
    """
    if not url:
        return False
    try:
        u = urlparse(url)
        host = u.hostname or "localhost"
        port = u.port or (443 if u.scheme == "https" else 80)
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False
    except Exception:
        return False

IS_WINDOWS = sys.platform.startswith("win")

# Em Windows, evita abrir uma janela de console preta a cada chamada.
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0) if IS_WINDOWS else 0


def _pidfile(service_id: str) -> str:
    return f"/tmp/appmgr-{service_id}.pid"


def _logfile(service_id: str) -> str:
    return f"/tmp/appmgr-{service_id}.log"


def wsl_logfile(service_id: str) -> str:
    """Caminho do log de um servico WSL (visivel pra UI)."""
    return _logfile(service_id)


def wsl_argv(distro: str) -> list[str]:
    """Argv para invocar `bash -l` no WSL. O script vai por STDIN."""
    argv = ["wsl.exe"]
    if distro:
        argv += ["-d", distro]
    argv += ["--", "bash", "-l"]
    return argv


def wsl_stdin_payload(script: str, keep_file: bool = False) -> str:
    """Empacota `script` numa unica linha apta pra ir via stdin do `bash -l`.

    Codifica em base64 e gera um one-liner que decodifica num tmpfile e
    executa via `bash -l`. Sem `\n` (o bash do WSL ignora stdin com newlines)
    e sem expor `$VAR` que possa ser expandido pelo wsl.exe.
    """
    b64 = base64.b64encode(script.encode("utf-8")).decode("ascii")
    cleanup = "" if keep_file else '; rm -f "$F"'
    return (
        'F=$(mktemp /tmp/appmgr-XXXXXX.sh); '
        f'echo {b64} | base64 -d > "$F"; '
        f'bash -l "$F"{cleanup}'
    )


def _shell_dir(directory: str) -> str:
    """Converte o diretorio do servico em uma expressao shell segura.

    `~` e `~/...` no inicio sao deixados sem aspas para o bash expandir;
    o restante (com possiveis espacos) vai em aspas duplas.
    """
    d = directory
    if d == "~":
        return "~"
    if d.startswith("~/"):
        rest = d[2:].replace('"', '\\"')
        return f'~/"{rest}"'
    return '"' + d.replace('"', '\\"') + '"'


def build_launch_script(service: Service, shell_init: str) -> str:
    pid = _pidfile(service.id)
    log = _logfile(service.id)
    dir_expr = _shell_dir(service.directory)
    lines = [
        # Garante que o log existe desde o inicio, mesmo que o cd falhe — assim
        # o botao "Log" sempre tem algo pra mostrar (inclusive o erro de cd).
        f": >'{log}'",
    ]
    if shell_init.strip():
        lines.append(shell_init.strip())
    lines.append("set -m")
    lines.append(
        f'cd {dir_expr} || {{ echo "appmgr: cd falhou em {service.directory}" >>"{log}"; exit 1; }}'
    )
    # O grupo `{ ...; } &` vira lider de process group por causa do `set -m`.
    # Usamos `jobs -p %%` em vez de `$!` porque no bash do WSL (5.1.16) em
    # shell nao-interativo `$!` vem vazio apos `{ ...; } &`.
    lines.append(f"{{ {service.command} ; }} </dev/null >>'{log}' 2>&1 &")
    lines.append(f"jobs -p %% >'{pid}'")
    lines.append("wait")
    return "\n".join(lines)


def build_unified_tail_script(service_ids: list[str], backlog: int = 30) -> str:
    """Segue os logs de varios servicos WSL num unico processo.

    `tail -v` forca o cabecalho `==> <arquivo> <==` sempre — inclusive com um
    unico arquivo — e o reemite a cada troca de origem enquanto segue. Eh isso
    que permite a UI saber de qual servico veio cada linha sem precisar de um
    processo por servico. `-F` segue rotacao/recriacao do arquivo, entao um
    servico que ainda nem iniciou passa a aparecer sozinho quando subir.
    """
    logs = [_logfile(sid) for sid in service_ids]
    quoted = " ".join(f"'{p}'" for p in logs)
    # touch garante que todos existam: sem isso o tail reclama dos ausentes.
    return f"touch {quoted} 2>/dev/null; tail -v -n {backlog} -F {quoted}"


def build_stop_script(service: Service, shell_init: str) -> str:
    """Monta o script de parada.

    Se `service.stop_command` esta preenchido, executa ele no diretorio do
    servico (com shell_init) — util para servicos fire-and-forget tipo
    `docker compose up -d`, em que o kill por PID nao alcanca o servico real.
    Sempre tenta tambem matar o pidfile no fim.
    """
    pid = _pidfile(service.id)
    log = _logfile(service.id)
    dir_expr = _shell_dir(service.directory)
    parts: list[str] = []

    if service.stop_command.strip():
        # init + cd + comando, com saida no log do servico pra ficar visivel
        init = shell_init.strip()
        if init:
            parts.append(init)
        parts.append(
            f'echo "--- appmgr: stop_command: {service.stop_command} ---" >>"{log}"'
        )
        parts.append(
            f'cd {dir_expr} || {{ echo "appmgr: cd falhou em {service.directory}" >>"{log}"; }}'
        )
        parts.append(f'{{ {service.stop_command} ; }} >>"{log}" 2>&1 || true')

    # Kill por PID — opera mesmo se o pidfile nao existir mais.
    parts.append(
        f"p=$(cat '{pid}' 2>/dev/null); "
        'if [ -n "$p" ]; then '
        'kill -TERM -- -"$p" 2>/dev/null; '
        'for i in 1 2 3 4 5 6 7 8 9 10; do kill -0 "$p" 2>/dev/null || break; sleep 0.3; done; '
        'kill -KILL -- -"$p" 2>/dev/null; '
        "fi; "
        f"rm -f '{pid}'"
    )
    return "\n".join(parts)


def build_status_script() -> str:
    # Imprime o id de cada servico cujo pidfile aponta para um processo vivo.
    return (
        "for f in /tmp/appmgr-*.pid; do "
        '[ -e "$f" ] || continue; '
        'p=$(cat "$f" 2>/dev/null); '
        'if [ -n "$p" ] && kill -0 "$p" 2>/dev/null; then '
        'b=$(basename "$f" .pid); echo "${b#appmgr-}"; '
        "fi; "
        "done"
    )


# ============================================================
# Suporte para servicos com runtime="windows" (cmd.exe nativo)
# ============================================================

def _win_pidfile(service_id: str) -> str:
    return os.path.join(tempfile.gettempdir(), f"appmgr-win-{service_id}.pid")


def win_logfile(service_id: str) -> str:
    """Caminho do arquivo de log de um servico Windows (visivel pra UI)."""
    return os.path.join(tempfile.gettempdir(), f"appmgr-win-{service_id}.log")


def windows_pid_alive(pid: int) -> bool:
    """Verifica via tasklist se um PID Windows ainda esta rodando."""
    try:
        out = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/NH", "/FO", "CSV"],
            capture_output=True, text=True,
            creationflags=_NO_WINDOW,
            timeout=10,
        ).stdout
        # CSV: "exename.exe","12345","Console","1","12,345 K"
        return f'"{pid}"' in out
    except Exception:
        return False


def _split_unc(unc: str) -> tuple[str | None, str]:
    """Quebra UNC em (share, rest). \\\\srv\\share\\sub -> (\\\\srv\\share, \\sub)."""
    parts = unc.lstrip("\\").split("\\", 2)
    if len(parts) < 2:
        return None, ""
    share = "\\\\" + "\\".join(parts[:2])
    rest = "\\" + parts[2] if len(parts) > 2 else ""
    return share, rest


def _existing_mount_letter(share: str) -> str | None:
    """Retorna letra de drive (A-Z) ja mapeada pro share, ou None."""
    try:
        out = subprocess.run(
            ["net", "use"], capture_output=True, text=True,
            creationflags=_NO_WINDOW, timeout=10,
        ).stdout
    except Exception:
        return None
    target = share.lower().rstrip("\\")
    for line in out.splitlines():
        if target not in line.lower():
            continue
        for tok in line.split():
            if len(tok) == 2 and tok[1] == ":" and tok[0].isalpha():
                return tok[0].upper()
    return None


def _find_free_drive_letter() -> str | None:
    for letter in "YXWVUTSRQPONMLKJIHGFEDCB":
        if not os.path.exists(f"{letter}:\\"):
            return letter
    return None


def _mount_unc(share: str) -> str | None:
    """Mapeia o share numa letra de drive (reusa mount existente se houver)."""
    existing = _existing_mount_letter(share)
    if existing:
        return existing
    letter = _find_free_drive_letter()
    if not letter:
        return None
    rc = subprocess.run(
        ["net", "use", f"{letter}:", share, "/persistent:no"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=_NO_WINDOW, timeout=15,
    ).returncode
    return letter if rc == 0 else None


def _ps_encoded_command(script: str) -> str:
    """Codifica script PowerShell em base64 UTF-16LE pra -EncodedCommand."""
    return base64.b64encode(script.encode("utf-16-le")).decode("ascii")


def _wrap_windows_cmd(directory: str, command: str) -> tuple[list[str], str | None]:
    """Retorna (argv_pra_Popen, cwd_pra_Popen) pra rodar `command` em `directory`.

      - Path UNC (\\\\server\\share\\...): usa PowerShell com Set-Location
        (cmd.exe nao acessa UNC do WSL via subprocess, mesmo com `net use` —
        Plan 9 redirector eh per-session).
      - Path Windows nativo: passa cwd direto pro Popen (CreateProcess seta o
        dir antes do cmd subir). NAO usa `cd /d "..."` no comando porque as
        aspas internas corrompem o parsing do cmd quando subprocess.Popen
        escapa argv com `\\"`.
      - Sem diretorio: cmd.exe puro.
    """
    if not directory:
        return ["cmd.exe", "/c", command], None
    d = directory.replace("/", "\\")
    is_unc = d.startswith("\\\\")
    if not is_unc:
        cwd = d if os.path.isdir(d) else None
        return ["cmd.exe", "/c", command], cwd
    # PowerShell aceita UNC nativamente como Set-Location.
    # Executa o comando user via Invoke-Expression (suporta .\app.exe,
    # comandos compostos com `;`, etc). PS5 nao suporta `&&` — se o user
    # precisar disso, deve usar pasta Windows nativa em vez de UNC.
    # *>&1 mescla todas as streams (Error/Warning/Verbose/Debug) no stdout
    # pra evitar o cabecalho `#< CLIXML` que PS escreve quando stderr eh
    # redirecionado separadamente.
    ps_script = (
        f"$ErrorActionPreference='Continue'\n"
        f"Set-Location -LiteralPath '{d}'\n"
        f"Invoke-Expression {_ps_escape_single(command)} *>&1\n"
    )
    return [
        "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
        "-EncodedCommand", _ps_encoded_command(ps_script),
    ], None


def _ps_escape_single(s: str) -> str:
    """Coloca string entre aspas simples PowerShell, escapando aspas."""
    return "'" + s.replace("'", "''") + "'"


def start_windows(service: Service) -> subprocess.Popen | None:
    """Inicia o comando no cmd.exe nativo do Windows, retornando o Popen."""
    pid_path = _win_pidfile(service.id)
    log_path = win_logfile(service.id)
    try:
        open(log_path, "w", encoding="utf-8").close()
    except OSError:
        pass
    try:
        log_file = open(log_path, "a", encoding="utf-8", buffering=1)
    except OSError:
        log_file = subprocess.DEVNULL  # type: ignore

    argv, cwd = _wrap_windows_cmd(service.directory, service.command)
    try:
        proc = subprocess.Popen(
            argv,
            cwd=cwd,
            stdin=subprocess.DEVNULL,
            stdout=log_file,
            stderr=log_file,
            creationflags=_NO_WINDOW | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
        )
    except Exception as exc:
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(f"appmgr: falhou ao iniciar: {exc!r}\n")
        except OSError:
            pass
        return None

    try:
        with open(pid_path, "w", encoding="utf-8") as f:
            f.write(str(proc.pid))
    except OSError:
        pass
    return proc


def stop_windows(service: Service) -> None:
    """Para um servico Windows: roda stop_command (se houver) e mata o PID/tree."""
    pid_path = _win_pidfile(service.id)
    log_path = win_logfile(service.id)

    if service.stop_command.strip():
        argv, cwd = _wrap_windows_cmd(service.directory, service.stop_command)
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(f"\n--- appmgr: stop_command: {service.stop_command} ---\n")
                subprocess.run(
                    argv,
                    cwd=cwd,
                    stdin=subprocess.DEVNULL,
                    stdout=f, stderr=f,
                    creationflags=_NO_WINDOW,
                    timeout=60,
                )
        except Exception:
            pass

    # Mata o PID e a tree de processos filhos
    try:
        with open(pid_path, "r") as f:
            pid = int(f.read().strip())
    except (OSError, ValueError):
        pid = None
    if pid:
        try:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=_NO_WINDOW,
                timeout=15,
            )
        except Exception:
            pass

    try:
        os.unlink(pid_path)
    except OSError:
        pass


def running_ids_windows() -> set[str]:
    """Conjunto de service IDs com pidfile Windows apontando pra processo vivo."""
    alive = set()
    pattern = os.path.join(tempfile.gettempdir(), "appmgr-win-*.pid")
    for pidfile in glob.glob(pattern):
        try:
            with open(pidfile, "r") as f:
                pid = int(f.read().strip())
        except (OSError, ValueError):
            continue
        basename = os.path.basename(pidfile)
        sid = basename[len("appmgr-win-"):-len(".pid")]
        if windows_pid_alive(pid):
            alive.add(sid)
    return alive


def probe_health_command(service: Service, distro: str, shell_init: str,
                         timeout: float = 2.0) -> bool:
    """Roda o `health_command` do servico e retorna True se exit==0.

    Usa o mesmo runtime do servico (WSL ou Windows). Diretorio e shell_init
    sao aplicados pra que o comando tenha o mesmo contexto que o `command`
    principal teria. Saidas sao descartadas.
    """
    cmd = (getattr(service, "health_command", "") or "").strip()
    if not cmd:
        return False
    try:
        if getattr(service, "runtime", "wsl") == "windows":
            argv, cwd = _wrap_windows_cmd(service.directory, cmd)
            rc = subprocess.run(
                argv, cwd=cwd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=_NO_WINDOW,
                timeout=timeout,
            ).returncode
        else:
            parts: list[str] = []
            if shell_init.strip():
                parts.append(shell_init.strip())
            if service.directory:
                parts.append(f"cd {_shell_dir(service.directory)} 2>/dev/null || true")
            parts.append(cmd)
            script = "\n".join(parts)
            rc = subprocess.run(
                wsl_argv(distro),
                input=wsl_stdin_payload(script),
                text=True,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=_NO_WINDOW,
                timeout=timeout,
            ).returncode
        return rc == 0
    except Exception:
        return False


def build_tail_argv_windows(service_id: str) -> list[str]:
    """Argv pra rodar `Get-Content -Wait` no PowerShell — equivalente do tail -F."""
    log = win_logfile(service_id)
    # PowerShell escape: aspas duplas dentro de single quotes
    cmd = (
        f"if (-not (Test-Path '{log}')) {{ New-Item '{log}' -ItemType File | Out-Null }}; "
        f"Get-Content -Path '{log}' -Wait -Tail 500"
    )
    return ["powershell.exe", "-NoProfile", "-Command", cmd]


class ProcessManager:
    """Dispara, para e consulta servicos no WSL."""

    def __init__(self, config: Config):
        self.config = config
        # service_id -> Popen do relay wsl.exe (enquanto esta sessao o iniciou)
        self._relays: dict[str, subprocess.Popen] = {}

    def _run_blocking(self, script: str, capture: bool = False, timeout: int = 30):
        return subprocess.run(
            wsl_argv(self.config.distro),
            input=wsl_stdin_payload(script),
            text=True,
            stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=_NO_WINDOW,
            timeout=timeout,
        )

    def start(self, service: Service) -> None:
        if getattr(service, "runtime", "wsl") == "windows":
            proc = start_windows(service)
            if proc is not None:
                self._relays[service.id] = proc
            return
        # WSL (default)
        script = build_launch_script(service, self.config.shell_init)
        proc = subprocess.Popen(
            wsl_argv(self.config.distro),
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=_NO_WINDOW,
            text=True,
        )
        try:
            proc.stdin.write(wsl_stdin_payload(script))
            proc.stdin.close()
        except Exception:
            pass
        self._relays[service.id] = proc

    def stop(self, service: Service) -> None:
        if getattr(service, "runtime", "wsl") == "windows":
            stop_windows(service)
            relay = self._relays.pop(service.id, None)
            if relay and relay.poll() is None:
                try:
                    relay.terminate()
                except Exception:
                    pass
            return
        # WSL
        script = build_stop_script(service, self.config.shell_init)
        try:
            self._run_blocking(script, timeout=60)
        except subprocess.TimeoutExpired:
            pass
        relay = self._relays.pop(service.id, None)
        if relay and relay.poll() is None:
            try:
                relay.terminate()
            except Exception:
                pass

    def running_ids(self) -> set[str]:
        """Consulta sincrona — uniao de pidfiles WSL e Windows."""
        wsl_alive = set()
        try:
            out = self._run_blocking(build_status_script(), capture=True, timeout=15).stdout
            wsl_alive = {line.strip() for line in out.splitlines() if line.strip()}
        except Exception:
            pass
        try:
            win_alive = running_ids_windows()
        except Exception:
            win_alive = set()
        return wsl_alive | win_alive
