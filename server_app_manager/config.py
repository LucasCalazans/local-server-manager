"""Carregamento, persistência e modelos de configuração do gerenciador."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from pathlib import Path


CONFIG_DIR = Path.home() / ".server-app-manager"
CONFIG_PATH = CONFIG_DIR / "config.json"


def new_id() -> str:
    return uuid.uuid4().hex


@dataclass
class Service:
    """Um processo iniciável (ex.: Backend em Python, Frontend em npm)."""

    name: str
    directory: str
    command: str
    url: str = ""
    # Comando opcional para parar o servico. Util quando o `command` eh
    # fire-and-forget (ex.: `docker compose up -d`) e o `kill -PID` nao
    # alcanca os processos reais. Quando definido, roda no `directory` antes
    # do kill por pidfile.
    stop_command: str = ""
    # Quando True, o servico nao roda localmente — eh apenas monitorado por
    # probe TCP da URL. UI esconde botoes de Iniciar/Parar/Log; "Iniciar tudo"
    # e "Parar tudo" tambem ignoram esses servicos.
    is_prod: bool = False
    # Onde rodar o comando: "wsl" (default, dentro do WSL Ubuntu) ou
    # "windows" (cmd.exe nativo, pra comandos que precisam das libs Windows).
    runtime: str = "wsl"
    # Comando opcional para health-check: se retorna exit 0, o servico eh
    # considerado vivo (mesmo se foi iniciado fora do gerenciador). Roda no
    # mesmo runtime do servico. Ex.:
    #   Windows: tasklist /FI "IMAGENAME eq electron.exe" | findstr /I electron
    #   WSL:     pgrep -f "uvicorn hermes" >/dev/null
    health_command: str = ""
    id: str = field(default_factory=new_id)

    @classmethod
    def from_dict(cls, data: dict) -> "Service":
        return cls(
            id=data.get("id") or new_id(),
            name=data.get("name", ""),
            directory=data.get("directory", ""),
            command=data.get("command", ""),
            url=data.get("url", ""),
            stop_command=data.get("stop_command", ""),
            is_prod=bool(data.get("is_prod", False)),
            runtime=data.get("runtime", "wsl") or "wsl",
            health_command=data.get("health_command", ""),
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "directory": self.directory,
            "command": self.command,
            "url": self.url,
            "stop_command": self.stop_command,
            "is_prod": self.is_prod,
            "runtime": self.runtime,
            "health_command": self.health_command,
        }


@dataclass
class Application:
    """Uma aplicação que agrupa um ou mais serviços (ex.: front + back)."""

    name: str
    # Caminho absoluto para uma imagem (PNG/JPG/SVG/etc) usada como background
    # do card. Vazio = sem imagem (card usa fundo padrao).
    icon_path: str = ""
    services: list[Service] = field(default_factory=list)
    id: str = field(default_factory=new_id)

    @classmethod
    def from_dict(cls, data: dict) -> "Application":
        return cls(
            id=data.get("id") or new_id(),
            name=data.get("name", ""),
            icon_path=data.get("icon_path", ""),
            services=[Service.from_dict(s) for s in data.get("services", [])],
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "icon_path": self.icon_path,
            "services": [s.to_dict() for s in self.services],
        }


@dataclass
class Environment:
    """Uma maquina onde os servicos rodam — vira uma aba na interface.

    kind="local": os comandos vao pro WSL desta maquina (comportamento
    historico, e o unico que existia antes das abas).

    kind="ssh": os comandos saem pelo WSL **local** e entram por `ssh` no
    host remoto. O WSL eh o tunel de proposito: o app roda no Windows, que
    nao conhece os aliases do `~/.ssh/config` do WSL nem alcanca a faixa
    100.x da tailnet (o NordLynx ocupa a mesma CGNAT). Rodar o ssh de
    dentro do WSL reaproveita a config, as chaves e a rota que ja funcionam
    la.
    """

    name: str
    kind: str = "local"
    # Host/alias do ssh (ex.: "prism-server"), so para kind="ssh".
    ssh_host: str = ""
    # Distro WSL: onde os comandos rodam (local) ou de onde o ssh sai (ssh).
    # Vazio = distro padrao do wsl.exe.
    distro: str = ""
    # Trecho de shell prependido a cada comando, util para carregar nvm/venv
    # quando o ~/.bashrc nao roda em shell nao-interativo. Ex.:
    #   "export NVM_DIR=$HOME/.nvm; . $NVM_DIR/nvm.sh"
    shell_init: str = ""
    # Host que substitui "localhost" ao abrir as URLs dos servicos deste
    # ambiente no navegador (ex.: "192.168.0.3"). Vazio = abre como esta.
    url_host: str = ""
    applications: list[Application] = field(default_factory=list)
    id: str = field(default_factory=new_id)

    @property
    def is_ssh(self) -> bool:
        return self.kind == "ssh"

    @classmethod
    def from_dict(cls, data: dict) -> "Environment":
        return cls(
            id=data.get("id") or new_id(),
            name=data.get("name", ""),
            kind=data.get("kind", "local") or "local",
            ssh_host=data.get("ssh_host", ""),
            distro=data.get("distro", ""),
            shell_init=data.get("shell_init", ""),
            url_host=data.get("url_host", ""),
            applications=[
                Application.from_dict(a) for a in data.get("applications", [])
            ],
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "kind": self.kind,
            "ssh_host": self.ssh_host,
            "distro": self.distro,
            "shell_init": self.shell_init,
            "url_host": self.url_host,
            "applications": [a.to_dict() for a in self.applications],
        }


DEFAULT_ENV_NAME = "Este Computador"


@dataclass
class Config:
    # Caminho ate o source do projeto (pasta com main.py). Usado pelo botao
    # "Atualizar" pra rebuildar o EXE. Pode ser caminho Windows ou UNC do WSL.
    source_dir: str = ""
    environments: list[Environment] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict) -> "Config":
        envs = data.get("environments")
        if envs is None:
            # Config no formato antigo (lista plana de applications, com
            # distro/shell_init globais): vira um unico ambiente local.
            envs = [
                {
                    "name": DEFAULT_ENV_NAME,
                    "kind": "local",
                    "distro": data.get("distro", ""),
                    "shell_init": data.get("shell_init", ""),
                    "applications": data.get("applications", []),
                }
            ]
        cfg = cls(
            source_dir=data.get("source_dir", ""),
            environments=[Environment.from_dict(e) for e in envs],
        )
        if not cfg.environments:
            cfg.environments = [Environment(name=DEFAULT_ENV_NAME)]
        return cfg

    def to_dict(self) -> dict:
        return {
            "source_dir": self.source_dir,
            "environments": [e.to_dict() for e in self.environments],
        }

    def env_by_id(self, env_id: str) -> "Environment | None":
        return next((e for e in self.environments if e.id == env_id), None)

    def env_of_service(self, service_id: str) -> "Environment | None":
        for env in self.environments:
            for app in env.applications:
                if any(s.id == service_id for s in app.services):
                    return env
        return None


def load_config(path: Path = CONFIG_PATH) -> Config:
    if not path.exists():
        cfg = Config()
        save_config(cfg, path)
        return cfg
    with path.open("r", encoding="utf-8") as fh:
        return Config.from_dict(json.load(fh))


def save_config(cfg: Config, path: Path = CONFIG_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(cfg.to_dict(), fh, indent=2, ensure_ascii=False)
