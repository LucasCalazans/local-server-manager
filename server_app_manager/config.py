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
class Config:
    # Nome da distro WSL (ex.: "Ubuntu"). Vazio = distro padrão do wsl.exe.
    distro: str = ""
    # Trecho de shell prependido a cada comando, util para carregar nvm/venv
    # quando o ~/.bashrc nao roda em shell nao-interativo. Ex.:
    #   "export NVM_DIR=$HOME/.nvm; . $NVM_DIR/nvm.sh"
    shell_init: str = ""
    # Caminho ate o source do projeto (pasta com main.py). Usado pelo botao
    # "Atualizar" pra rebuildar o EXE. Pode ser caminho Windows ou UNC do WSL.
    source_dir: str = ""
    applications: list[Application] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict) -> "Config":
        return cls(
            distro=data.get("distro", ""),
            shell_init=data.get("shell_init", ""),
            source_dir=data.get("source_dir", ""),
            applications=[
                Application.from_dict(a) for a in data.get("applications", [])
            ],
        )

    def to_dict(self) -> dict:
        return {
            "distro": self.distro,
            "shell_init": self.shell_init,
            "source_dir": self.source_dir,
            "applications": [a.to_dict() for a in self.applications],
        }


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
