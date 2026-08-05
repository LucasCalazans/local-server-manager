"""Janela principal do gerenciador de aplicacoes."""

from __future__ import annotations

import time

import os
import tempfile
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

_UPDATE_LOG = Path(tempfile.gettempdir()) / "appmgr-update.log"


def _ulog(msg: str) -> None:
    """Log estruturado de acoes do UpdateDialog em %TEMP%/appmgr-update.log."""
    try:
        with _UPDATE_LOG.open("a", encoding="utf-8") as f:
            f.write(f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] {msg}\n")
    except Exception:
        pass

import html as _html
import re

import qtawesome as qta
from PySide6.QtCore import QEvent, QMimeData, QObject, QPoint, QProcess, QRect, QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import (
    QColor,
    QDesktopServices,
    QDrag,
    QFont,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QTextCursor,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QStyle,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from .config import CONFIG_PATH, Application, Config, load_config, save_config
from .dialogs import ApplicationDialog
from .process import (
    ProcessManager,
    build_status_script,
    build_tail_argv_windows,
    build_unified_tail_script,
    probe_health_command,
    probe_url,
    running_ids_windows,
    win_logfile,
    wsl_argv,
    wsl_logfile,
    wsl_stdin_payload,
)
from .updater import (
    BuildError,
    find_python,
    install_and_relaunch,
    installed_exe_path,
    is_frozen,
    run_build,
)

STATUS_INTERVAL_MS = 2500
# Tempo maximo em que um servico fica "iniciando" sem ser detectado rodando.
# Se passou disso, considera que falhou pra iniciar e volta a cinza.
STARTING_TIMEOUT_S = 45.0

# ---- paleta dark coesa --------------------------------------------------
BG_APP = "#0f1419"
BG_CARD = "#1c2128"
BG_CARD_HOVER = "#22272e"
BORDER = "#30363d"
TEXT = "#e6edf3"
TEXT_MUTED = "#8b949e"
ACCENT = "#2f81f7"
GREEN = "#3fb950"
YELLOW = "#d29922"
GREY = "#6e7681"
RED = "#f85149"
LOG_BG = "#0d1117"

APP_STYLESHEET = f"""
QWidget {{
    background: {BG_APP};
    color: {TEXT};
    font-family: "Segoe UI", "Inter", system-ui, sans-serif;
    font-size: 13px;
}}
QScrollArea, QScrollArea > QWidget > QWidget {{
    background: {BG_APP};
    border: none;
}}
QFrame#card {{
    background: {BG_CARD};
    border: 1px solid {BORDER};
    border-radius: 10px;
}}
QFrame#card:hover {{
    background: {BG_CARD_HOVER};
}}
QLabel {{
    background: transparent;
    color: {TEXT};
}}
QLabel#cardTitle {{
    font-size: 15px;
    font-weight: 600;
}}
QLabel#muted {{
    color: {TEXT_MUTED};
}}
QLineEdit {{
    background: {BG_APP};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 6px 8px;
}}
QLineEdit:focus {{
    border-color: {ACCENT};
}}
QPushButton {{
    background: {BG_CARD};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 5px 12px;
    min-height: 18px;
}}
QPushButton:hover {{
    background: {BG_CARD_HOVER};
    border-color: {GREY};
}}
QPushButton:pressed {{
    background: {BG_APP};
}}
QPushButton[role="start"] {{
    background: rgba(63, 185, 80, 0.14);
    border-color: rgba(63, 185, 80, 0.4);
    color: {GREEN};
}}
QPushButton[role="start"]:hover {{
    background: rgba(63, 185, 80, 0.22);
    border-color: {GREEN};
}}
QPushButton[role="stop"] {{
    background: rgba(248, 81, 73, 0.12);
    border-color: rgba(248, 81, 73, 0.35);
    color: {RED};
}}
QPushButton[role="stop"]:hover {{
    background: rgba(248, 81, 73, 0.20);
    border-color: {RED};
}}
QPushButton[role="restart"] {{
    background: rgba(210, 153, 34, 0.12);
    border-color: rgba(210, 153, 34, 0.35);
    color: {YELLOW};
}}
QPushButton[role="restart"]:hover {{
    background: rgba(210, 153, 34, 0.20);
    border-color: {YELLOW};
}}
QPushButton[role="primary"] {{
    background: {ACCENT};
    border-color: {ACCENT};
    color: white;
}}
QPushButton[role="primary"]:hover {{
    background: #4a92f8;
    border-color: #4a92f8;
}}
QPushButton[role="danger"] {{
    color: {RED};
}}
QPushButton[role="danger"]:hover {{
    background: rgba(248, 81, 73, 0.15);
    border-color: {RED};
}}
QDialog {{
    background: {BG_APP};
}}
QPlainTextEdit#logView {{
    background: {LOG_BG};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 6px;
}}
QFrame#logPanel {{
    background: {BG_CARD};
    border: 1px solid {BORDER};
    border-radius: 8px;
}}
QSplitter::handle {{
    background: {BG_APP};
}}
QSplitter::handle:horizontal {{
    width: 4px;
}}
QScrollBar:vertical {{
    background: {BG_APP};
    width: 10px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {BORDER};
    border-radius: 5px;
    min-height: 24px;
}}
QScrollBar::handle:vertical:hover {{
    background: {GREY};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
"""

STATUS_STOPPED = "stopped"
STATUS_STARTING = "starting"
STATUS_RUNNING = "running"

_DOT_COLORS = {
    STATUS_STOPPED: GREY,
    STATUS_STARTING: YELLOW,
    STATUS_RUNNING: GREEN,
}
_DOT_LABEL = {
    STATUS_STOPPED: "parado",
    STATUS_STARTING: "iniciando…",
    STATUS_RUNNING: "rodando",
}


def _dot_style(state: str) -> str:
    color = _DOT_COLORS[state]
    # font-size grande pro ponto ficar bem visivel;
    # padding-right pra separar do texto sem precisar de outro widget.
    return f"color: {color}; font-size: 20px; padding-right: 6px;"


def _set_role(btn: QPushButton, role: str) -> None:
    """Marca o botao com uma role para o QSS dinamico encontrar."""
    btn.setProperty("role", role)
    btn.style().unpolish(btn)
    btn.style().polish(btn)


# Nomes de icones (FontAwesome 5 Solid via QtAwesome).
ICON_PLAY = "fa5s.play"
ICON_STOP = "fa5s.stop"
ICON_RESTART = "fa5s.sync-alt"
ICON_PLAY_ALL = "fa5s.forward"
ICON_STOP_ALL = "fa5s.times-circle"
ICON_OPEN = "fa5s.external-link-alt"
ICON_CLOSE = "fa5s.times"
ICON_EDIT = "fa5s.pen"
ICON_DELETE = "fa5s.trash"

# Cor padrao do icone por role
_ICON_COLOR_BY_ROLE = {
    "start": GREEN,
    "stop": RED,
    "restart": YELLOW,
    "danger": RED,
    "primary": "white",
}


def _icon_button(icon_name: str, tooltip: str, role: str | None = None,
                 width: int = 34) -> QPushButton:
    """QPushButton compacto, so com QIcon + tooltip explicativo.

    Usa QtAwesome pra renderizar icones FontAwesome embarcados (sem rede).
    """
    color = _ICON_COLOR_BY_ROLE.get(role or "", TEXT)
    btn = QPushButton()
    btn.setIcon(qta.icon(icon_name, color=color))
    btn.setIconSize(QSize(14, 14))
    btn.setToolTip(tooltip)
    btn.setFixedWidth(width)
    btn.setCursor(Qt.PointingHandCursor)
    if role:
        _set_role(btn, role)
    return btn


class SettingsDialog(QDialog):
    def __init__(self, parent, config: Config, on_update_requested):
        super().__init__(parent)
        self.setWindowTitle("Configuracoes")
        self.setMinimumWidth(540)
        self._on_update_requested = on_update_requested

        self.distro_edit = QLineEdit(config.distro)
        self.distro_edit.setPlaceholderText("Ex.: Ubuntu (vazio = distro padrao)")
        self.init_edit = QLineEdit(config.shell_init)
        self.init_edit.setPlaceholderText(
            'export NVM_DIR="$HOME/.nvm"; [ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh"'
        )

        form = QFormLayout()
        form.addRow("Distro WSL:", self.distro_edit)
        form.addRow("Shell init:", self.init_edit)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        # Botao de atualizar aplicacao (recompila o EXE e relanca).
        update_btn = QPushButton("Atualizar aplicacao")
        update_btn.setToolTip("Recompila o source e substitui o EXE em uso")
        update_btn.clicked.connect(self._handle_update_clicked)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)
        layout.addLayout(form)
        hint = QLabel(
            "Shell init eh prependido a cada comando. Util quando o npm vem do "
            "nvm e o ~/.bashrc nao carrega em shell nao-interativo."
        )
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        # Separador + secao de manutencao
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet(f"color: {BORDER}; background: {BORDER}; max-height: 1px;")
        layout.addWidget(sep)
        maint_label = QLabel("Manutencao")
        maint_label.setStyleSheet("font-weight: 600;")
        layout.addWidget(maint_label)
        layout.addWidget(update_btn)

        layout.addStretch()
        layout.addWidget(buttons)

    def _handle_update_clicked(self) -> None:
        # Fecha o Settings primeiro pra abrir o Update por cima limpo
        self.accept()
        self._on_update_requested()


# Cabecalho que o `tail -v` emite ao trocar de arquivo: `==> /caminho <==`.
_TAIL_HEADER_RE = re.compile(r"^==> (.+) <==$")
# Sequencias ANSI (cores do vite/uvicorn/etc) — viram lixo num QPlainTextEdit.
_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[a-zA-Z]")

# Paleta pros prefixos de origem, distribuida em round-robin pra que servicos
# vizinhos na lista nunca caiam na mesma cor.
_LOG_LABEL_COLORS = [
    "#7ee787", "#79c0ff", "#d2a8ff", "#ffa657",
    "#f778ba", "#56d4dd", "#e3b341", "#a5d6ff",
]

# Largura fixa do prefixo, pra que o corpo dos logs fique alinhado em coluna.
_LABEL_WIDTH = 30


class UnifiedLogPanel(QFrame):
    """Painel lateral com os logs de todos os servicos, prefixados pela origem.

    Os servicos WSL sao seguidos por UM processo so (`tail -v -F` sobre todos
    os arquivos), que emite `==> arquivo <==` a cada troca de origem — eh dai
    que sai a atribuicao de cada linha. Servicos com runtime="windows" nao
    entram nesse tail (o log deles fica no %TEMP% do Windows), entao cada um
    ganha seu proprio processo de tail via PowerShell.
    """

    BACKLOG_LINES = 30
    MAX_BLOCKS = 8000
    # Acumula linhas e escreve em lote: appendHtml por linha trava a UI quando
    # um servico despeja centenas de linhas de uma vez (build, stack trace).
    FLUSH_MS = 120

    def __init__(self, parent, config: Config, on_close):
        super().__init__(parent)
        self.setObjectName("logPanel")
        self.setFrameShape(QFrame.StyledPanel)
        self._on_close = on_close

        self.view = QPlainTextEdit()
        self.view.setObjectName("logView")
        self.view.setReadOnly(True)
        self.view.setMaximumBlockCount(self.MAX_BLOCKS)
        self.view.setLineWrapMode(QPlainTextEdit.NoWrap)
        mono = QFont("Cascadia Mono", 10)
        mono.setStyleHint(QFont.Monospace)
        self.view.setFont(mono)

        self.count_lbl = QLabel()
        self.count_lbl.setObjectName("muted")
        self.count_lbl.setStyleSheet(f"color: {TEXT_MUTED};")

        title = QLabel("Logs")
        title.setStyleSheet("font-weight: 600;")
        clear_btn = QPushButton("Limpar")
        clear_btn.clicked.connect(self.view.clear)
        # Botao de icone em vez de um "x" em texto: o padding de 12px do QSS
        # global nao deixa espaco pro caractere num botao estreito.
        close_btn = _icon_button(ICON_CLOSE, "Fechar painel de logs", width=30)
        close_btn.clicked.connect(lambda: self._on_close())

        header = QHBoxLayout()
        header.setSpacing(8)
        header.addWidget(title)
        header.addWidget(self.count_lbl)
        header.addStretch()
        header.addWidget(clear_btn)
        header.addWidget(close_btn)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 10)
        layout.setSpacing(6)
        layout.addLayout(header)
        layout.addWidget(self.view)

        # logpath -> (rotulo ja formatado, cor)
        self._sources: dict[str, tuple[str, str]] = {}
        self._procs: list[QProcess] = []
        # Buffers de linha parcial: o tail entrega chunks que cortam linhas ao meio.
        self._partial: dict[QProcess, str] = {}
        # De qual arquivo veio a ultima linha do tail unificado (WSL).
        self._current_src: str = ""
        # Linhas em branco seguradas ate saber se sao conteudo ou separador
        # de secao do tail (ver _on_wsl_output).
        self._blank_held: int = 0
        self._pending: list[str] = []

        self._flush_timer = QTimer(self)
        self._flush_timer.timeout.connect(self._flush)
        self._flush_timer.start(self.FLUSH_MS)

        self.reload_sources(config)

    # ----- ciclo de vida dos tails --------------------------------------
    def reload_sources(self, config: Config) -> None:
        """(Re)inicia os tails conforme a config atual."""
        self.stop_all()
        self._sources.clear()
        self._current_src = ""

        wsl_ids: list[str] = []
        win_svcs: list = []
        idx = 0
        for app in config.applications:
            for svc in app.services:
                # Servico de producao nao roda localmente — nao tem log.
                if getattr(svc, "is_prod", False):
                    continue
                color = _LOG_LABEL_COLORS[idx % len(_LOG_LABEL_COLORS)]
                idx += 1
                label = self._format_label(app.name, svc.name)
                if getattr(svc, "runtime", "wsl") == "windows":
                    self._sources[win_logfile(svc.id)] = (label, color)
                    win_svcs.append(svc)
                else:
                    self._sources[wsl_logfile(svc.id)] = (label, color)
                    wsl_ids.append(svc.id)

        n = len(self._sources)
        self.count_lbl.setText(
            f"  ·  {n} servico" + ("s" if n != 1 else "")
        )

        if wsl_ids:
            script = build_unified_tail_script(wsl_ids, self.BACKLOG_LINES)
            proc = self._new_proc(self._on_wsl_output)
            argv = wsl_argv(config.distro)
            proc.start(argv[0], argv[1:])
            proc.waitForStarted(2000)
            proc.write(wsl_stdin_payload(script).encode("utf-8"))
            proc.closeWriteChannel()

        # Cada servico Windows precisa do proprio tail (PowerShell nao segue
        # varios arquivos ao mesmo tempo de forma confiavel).
        for svc in win_svcs:
            path = win_logfile(svc.id)
            proc = self._new_proc(
                lambda p=None, src=path: self._on_win_output(src)
            )
            argv = build_tail_argv_windows(svc.id)
            proc.start(argv[0], argv[1:])

        if not self._sources:
            self.view.setPlainText("Nenhum servico local cadastrado.")

        # closeEvent para o timer; reabrir a janela cai aqui e o religa.
        self._flush_timer.start(self.FLUSH_MS)

    def _new_proc(self, on_ready) -> QProcess:
        proc = QProcess(self)
        proc.setProcessChannelMode(QProcess.MergedChannels)
        proc.readyReadStandardOutput.connect(on_ready)
        self._procs.append(proc)
        self._partial[proc] = ""
        return proc

    def stop_all(self) -> None:
        for proc in self._procs:
            if proc.state() != QProcess.NotRunning:
                proc.kill()
                proc.waitForFinished(1000)
            proc.deleteLater()
        self._procs.clear()
        self._partial.clear()

    # ----- leitura e formatacao -----------------------------------------
    @staticmethod
    def _format_label(app_name: str, svc_name: str) -> str:
        label = f"{app_name} · {svc_name}"
        if len(label) > _LABEL_WIDTH:
            label = label[: _LABEL_WIDTH - 1] + "…"
        return label.ljust(_LABEL_WIDTH)

    def _read_lines(self, proc: QProcess) -> list[str]:
        """Le o que chegou e devolve linhas completas, guardando o resto."""
        chunk = bytes(proc.readAllStandardOutput()).decode("utf-8", "replace")
        data = self._partial.get(proc, "") + chunk.replace("\r\n", "\n")
        lines = data.split("\n")
        self._partial[proc] = lines.pop()  # ultimo pedaco pode estar incompleto
        return lines

    def _on_wsl_output(self) -> None:
        proc = self.sender()
        if not isinstance(proc, QProcess):
            return
        for line in self._read_lines(proc):
            header = _TAIL_HEADER_RE.match(line.strip())
            if header:
                # Troca de arquivo: passa a atribuir as proximas linhas a ele.
                # A linha em branco que veio antes eh o separador de secao do
                # proprio tail, nao conteudo do log — descarta.
                self._blank_held = 0
                self._current_src = header.group(1)
                continue
            if not line.strip():
                # Ainda nao da pra saber se eh linha em branco do log ou o
                # separador antes do proximo cabecalho: segura ate ter certeza.
                self._blank_held += 1
                continue
            for _ in range(self._blank_held):
                self._queue(self._current_src, "")
            self._blank_held = 0
            self._queue(self._current_src, line)

    def _on_win_output(self, src: str) -> None:
        proc = self.sender()
        if not isinstance(proc, QProcess):
            return
        for line in self._read_lines(proc):
            self._queue(src, line)

    def _queue(self, src: str, text: str) -> None:
        label, color = self._sources.get(src, ("?".ljust(_LABEL_WIDTH), TEXT_MUTED))
        clean = _ANSI_RE.sub("", text)
        self._pending.append(
            f'<span style="color:{color}; white-space:pre;">{_html.escape(label)}</span>'
            f'<span style="color:{BORDER}; white-space:pre;"> │ </span>'
            f'<span style="white-space:pre;">{_html.escape(clean)}</span>'
        )

    def _flush(self) -> None:
        if not self._pending:
            return
        bar = self.view.verticalScrollBar()
        # So gruda no fim se o usuario ja estava no fim — se ele rolou pra
        # cima pra ler algo, respeita a posicao dele.
        at_bottom = bar.value() >= bar.maximum() - 4
        self.view.setUpdatesEnabled(False)
        for html_line in self._pending:
            self.view.appendHtml(html_line)
        self._pending.clear()
        self.view.setUpdatesEnabled(True)
        if at_bottom:
            self.view.moveCursor(QTextCursor.End)
            bar.setValue(bar.maximum())

    def suspend(self) -> None:
        """Derruba os tails ao fechar o painel; reabrir recomeca do backlog."""
        self._flush_timer.stop()
        self.stop_all()


class _ProbeBridge(QObject):
    """Ponte para receber resultado dos probes URL em thread de fundo."""
    result_ready = Signal(object)  # set[str] com service_ids vivos


class _BuildBridge(QObject):
    """Sinais Qt usados pela thread de build pra postar pra UI thread."""
    line = Signal(str)
    finished_ok = Signal(str)  # path do diretorio gerado (--onedir)
    failed = Signal(str)


def _build_in_thread(bridge: "_BuildBridge", source_dir: Path, python: str) -> None:
    """Roda em threading.Thread regular (sem QThread). Sinais via bridge."""
    _ulog(f"thread de build iniciada: source={source_dir} python={python}")
    try:
        out = run_build(source_dir, python, bridge.line.emit)
        _ulog(f"run_build retornou OK: {out}")
        bridge.finished_ok.emit(str(out))
    except BuildError as exc:
        _ulog(f"BuildError: {exc}")
        bridge.failed.emit(str(exc))
    except Exception as exc:
        _ulog(f"erro inesperado: {exc!r}\n{traceback.format_exc()}")
        bridge.failed.emit(f"erro inesperado: {exc!r}")
    _ulog("thread de build encerrando")


class UpdateDialog(QDialog):
    """Recompila o source via PyInstaller e (se rodando como EXE) reinicia."""

    def __init__(self, parent, config: Config, on_source_dir_changed):
        super().__init__(parent)
        self.setWindowTitle("Atualizar")
        self.setMinimumSize(720, 480)
        self.config = config
        self._on_source_dir_changed = on_source_dir_changed
        self._build_thread: threading.Thread | None = None
        self._build_bridge: _BuildBridge | None = None
        self._built_exe: Path | None = None
        self._busy = False

        # Source dir input
        src_row = QHBoxLayout()
        src_row.setSpacing(6)
        self.src_edit = QLineEdit(config.source_dir)
        self.src_edit.setPlaceholderText(
            r"Pasta do projeto (com main.py). Ex.: \\wsl.localhost\ubuntu\home\<user>\projects\local-server-manager"
        )
        browse = QPushButton("Procurar")
        browse.clicked.connect(self._browse_source)
        src_row.addWidget(self.src_edit)
        src_row.addWidget(browse)

        # Status header
        self.status_lbl = QLabel(self._initial_status())
        self.status_lbl.setWordWrap(True)
        self.status_lbl.setObjectName("muted")

        # Log view
        self.log = QPlainTextEdit()
        self.log.setObjectName("logView")
        self.log.setReadOnly(True)
        mono = QFont("Cascadia Mono", 9)
        mono.setStyleHint(QFont.Monospace)
        self.log.setFont(mono)

        # Botao unico: build + (se frozen) substitui o EXE e reinicia.
        self.action_btn = QPushButton(
            "Atualizar e reiniciar" if is_frozen() else "Compilar EXE"
        )
        _set_role(self.action_btn, "primary")
        self.action_btn.clicked.connect(self._start_build)

        self.close_btn = QPushButton("Fechar")
        self.close_btn.clicked.connect(self.reject)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(self.action_btn)
        btn_row.addWidget(self.close_btn)

        form = QFormLayout()
        form.addRow("Source:", src_row)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)
        layout.addLayout(form)
        layout.addWidget(self.status_lbl)
        layout.addWidget(self.log)
        layout.addLayout(btn_row)

    def _initial_status(self) -> str:
        if is_frozen():
            exe = installed_exe_path()
            return (
                f"EXE em {exe}\n"
                "Ao clicar, o source eh recompilado, o EXE eh substituido e o app reabre sozinho."
            )
        return (
            "Modo desenvolvimento (python). O build gera o EXE em "
            "dist\\ServerAppManager.exe — voce mesmo precisa copia-lo pro local instalado."
        )

    def _browse_source(self) -> None:
        start = self.src_edit.text().strip() or str(Path.home())
        chosen = QFileDialog.getExistingDirectory(self, "Pasta do source", start)
        if chosen:
            self.src_edit.setText(chosen)

    def _append_log(self, line: str) -> None:
        self.log.moveCursor(QTextCursor.End)
        self.log.insertPlainText(line + "\n")
        self.log.moveCursor(QTextCursor.End)

    def _start_build(self) -> None:
        _ulog("=" * 50)
        _ulog(f"_start_build clicado; frozen={is_frozen()}; sys.executable={getattr(__import__('sys'), 'executable', '?')}")
        src = self.src_edit.text().strip()
        _ulog(f"source_dir entrada: {src!r}")
        if not src:
            _ulog("ABORTADO: pasta vazia")
            QMessageBox.warning(self, "Pasta vazia", "Informe a pasta do source.")
            return
        source_dir = Path(src)
        if not (source_dir / "main.py").exists():
            _ulog(f"ABORTADO: main.py nao existe em {source_dir}")
            QMessageBox.warning(
                self, "main.py nao encontrado",
                f"A pasta {source_dir} nao contem main.py.",
            )
            return
        python = find_python()
        _ulog(f"find_python retornou: {python!r}; PATH inclui: {os.environ.get('PATH', '')[:200]}")
        if not python:
            _ulog("ABORTADO: Python externo nao encontrado")
            QMessageBox.critical(
                self, "Python nao encontrado",
                "Nenhum Python externo no PATH (python, py, python3). "
                "Instale Python 3.10+ no Windows e tente de novo.",
            )
            return

        # Persiste o source_dir se mudou
        if src != self.config.source_dir:
            self.config.source_dir = src
            self._on_source_dir_changed(src)

        self.log.clear()
        self.status_lbl.setText("Compilando... isso pode levar 1-3 minutos.")
        self._set_busy(True)

        _ulog("criando _BuildBridge")
        # Bridge eh QObject vivendo na main thread; signals emitidos da thread
        # de build chegam aqui via Qt.QueuedConnection automaticamente.
        self._build_bridge = _BuildBridge(self)
        self._build_bridge.line.connect(self._append_log)
        self._build_bridge.finished_ok.connect(self._on_build_ok)
        self._build_bridge.failed.connect(self._on_build_failed)
        _ulog("criando threading.Thread")
        self._build_thread = threading.Thread(
            target=_build_in_thread,
            args=(self._build_bridge, source_dir, python),
            daemon=True,
            name="build-worker",
        )
        _ulog("chamando .start() na thread")
        self._build_thread.start()
        _ulog(f"thread.start() retornou; thread alive={self._build_thread.is_alive()}")

    def _on_build_ok(self, exe_path: str) -> None:
        _ulog(f"_on_build_ok recebido: exe_path={exe_path}")
        self._built_exe = Path(exe_path)
        installed = installed_exe_path()
        _ulog(f"installed_exe_path()={installed}; frozen={is_frozen()}")
        if not installed:
            # Modo dev: so avisa onde o EXE foi gerado.
            _ulog("modo dev — nao reinicia")
            self._set_busy(False)
            self.status_lbl.setText(
                f"Build OK: {exe_path}\nCopie a pasta pra "
                "%LOCALAPPDATA%\\Programs\\ServerAppManager\\ pra atualizar a versao instalada."
            )
            return

        # Modo EXE: ja dispara install_and_relaunch e fecha o app.
        self.status_lbl.setText(
            f"Build OK. Substituindo a pasta em {installed.parent} e reiniciando..."
        )
        _ulog(f"chamando install_and_relaunch(new={self._built_exe}, installed={installed})")
        try:
            install_and_relaunch(self._built_exe, installed)
        except Exception as exc:
            _ulog(f"install_and_relaunch raised: {exc!r}\n{traceback.format_exc()}")
            self._set_busy(False)
            QMessageBox.critical(self, "Falha ao instalar", str(exc))
            return
        _ulog("install_and_relaunch retornou OK; chamando QApplication.quit()")
        QApplication.instance().quit()
        _ulog("QApplication.quit() retornou; saindo do _on_build_ok")

    def _on_build_failed(self, msg: str) -> None:
        _ulog(f"_on_build_failed: {msg}")
        self._set_busy(False)
        self.status_lbl.setText(f"Falhou: {msg}")

    def _set_busy(self, busy: bool) -> None:
        """Bloqueia/desbloqueia controles e fechamento durante o build.

        Nao mexemos em windowFlags em runtime: setWindowFlag faz setParent
        internamente, o que esconde o dialog e quebra o modal. O bloqueio
        efetivo de fechamento eh feito por closeEvent/reject/keyPressEvent
        abaixo — o X da titlebar continua visivel mas ignorado.
        """
        self._busy = busy
        self.action_btn.setEnabled(not busy)
        self.close_btn.setEnabled(not busy)
        self.src_edit.setEnabled(not busy)

    # Bloqueia fechamento (X da titlebar, Alt+F4) enquanto busy
    def closeEvent(self, event) -> None:
        if self._busy:
            event.ignore()
            return
        super().closeEvent(event)

    # Bloqueia Esc enquanto busy
    def reject(self) -> None:
        if self._busy:
            return
        super().reject()

    def keyPressEvent(self, event) -> None:
        if self._busy and event.key() in (Qt.Key_Escape, Qt.Key_Return, Qt.Key_Enter):
            event.ignore()
            return
        super().keyPressEvent(event)


class _AppCard(QFrame):
    """Card de uma aplicacao que pode ser arrastado pra reordenar."""

    DRAG_MIME = "application/x-appmgr-app-id"

    def __init__(self, app_id: str, bg_pixmap: QPixmap | None = None, parent=None):
        super().__init__(parent)
        self.app_id = app_id
        self._drag_start: QPoint | None = None
        self._bg_pixmap = bg_pixmap
        if bg_pixmap is not None:
            # paintEvent vai cuidar de TUDO; nao deixa o stylesheet desenhar fundo.
            self.setAttribute(Qt.WA_StyledBackground, False)

    # Opacidade da imagem de fundo (0.0 = invisivel, 1.0 = totalmente opaca).
    # Mantida sutil pra nao competir com o texto/botoes do card.
    BG_IMAGE_OPACITY = 0.12

    def paintEvent(self, e) -> None:
        if self._bg_pixmap is None:
            super().paintEvent(e)
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        rect = self.rect()
        radius = 10
        # Clip arredondado
        path = QPainterPath()
        path.addRoundedRect(rect, radius, radius)
        painter.setClipPath(path)
        # 1. Fundo solido do tema
        painter.fillRect(rect, QColor(BG_CARD))
        # 2. Imagem por cima com baixa opacidade (vira marca d'agua)
        scaled = self._bg_pixmap.scaled(
            self.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation
        )
        x = (self.width() - scaled.width()) // 2
        y = (self.height() - scaled.height()) // 2
        painter.setOpacity(self.BG_IMAGE_OPACITY)
        painter.drawPixmap(x, y, scaled)
        painter.setOpacity(1.0)
        # 3. Border
        painter.setClipping(False)
        painter.setPen(QPen(QColor(BORDER), 1))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(rect.adjusted(0, 0, -1, -1), radius, radius)
        painter.end()

    def _is_interactive_child(self, child) -> bool:
        if child is None or child is self:
            return False
        # Sobe pela hierarquia ate self pra ver se algum ancestor eh interativo.
        node = child
        while node is not None and node is not self:
            if isinstance(node, (QPushButton, QLineEdit, QPlainTextEdit)):
                return True
            node = node.parentWidget()
        return False

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            child = self.childAt(event.position().toPoint())
            if not self._is_interactive_child(child):
                self._drag_start = event.position().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._drag_start is None or not (event.buttons() & Qt.LeftButton):
            super().mouseMoveEvent(event)
            return
        dist = (event.position().toPoint() - self._drag_start).manhattanLength()
        if dist < QApplication.startDragDistance():
            return
        # Inicia o drag.
        drag = QDrag(self)
        mime = QMimeData()
        mime.setData(self.DRAG_MIME, self.app_id.encode("utf-8"))
        drag.setMimeData(mime)
        # Pixmap do card como preview do drag (visual feedback)
        drag.setPixmap(self.grab())
        drag.setHotSpot(self._drag_start)
        self._drag_start = None
        drag.exec(Qt.MoveAction)

    def mouseReleaseEvent(self, event) -> None:
        self._drag_start = None
        super().mouseReleaseEvent(event)


class _FlowLayout(QLayout):
    """Layout em fluxo: organiza children em linhas e quebra quando nao cabe.

    Comporta-se como text wrapping — colunas se ajustam automaticamente ao
    largura disponivel. Cards de tamanho fixo "transbordam" pra proxima linha
    em vez de overflowar horizontalmente.
    """

    def __init__(self, parent=None, h_spacing: int = 12, v_spacing: int = 12):
        super().__init__(parent)
        self._items: list = []
        self._h_space = h_spacing
        self._v_space = v_spacing
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, item) -> None:
        self._items.append(item)

    def insertItem(self, index: int, item) -> None:
        self._items.insert(index, item)
        self.invalidate()

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int):
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index: int):
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def expandingDirections(self):
        return Qt.Orientations(Qt.Orientation(0))

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return self._do_layout(QRect(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect: QRect) -> None:
        super().setGeometry(rect)
        self._do_layout(rect, test_only=False)

    def sizeHint(self) -> QSize:
        return self.minimumSize()

    def minimumSize(self) -> QSize:
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        m = self.contentsMargins()
        size += QSize(m.left() + m.right(), m.top() + m.bottom())
        return size

    def _do_layout(self, rect: QRect, test_only: bool) -> int:
        m = self.contentsMargins()
        x = rect.x() + m.left()
        y = rect.y() + m.top()
        right = rect.right() - m.right()
        line_height = 0
        for item in self._items:
            w = item.sizeHint().width()
            h = item.sizeHint().height()
            next_x = x + w + self._h_space
            if next_x - self._h_space > right and line_height > 0:
                # Quebra de linha
                x = rect.x() + m.left()
                y = y + line_height + self._v_space
                next_x = x + w + self._h_space
                line_height = 0
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), QSize(w, h)))
            x = next_x
            line_height = max(line_height, h)
        return y + line_height - rect.y() + m.bottom()


class _CardsGridContainer(QWidget):
    """Container com FlowLayout que aceita drops pra reordenar os cards."""

    cards_reordered = Signal()

    def __init__(self, card_width: int, card_gap: int = 12, parent=None):
        super().__init__(parent)
        self.card_width = card_width
        self.card_gap = card_gap
        self.setAcceptDrops(True)
        self.flow = _FlowLayout(self, h_spacing=card_gap, v_spacing=card_gap)
        self.setLayout(self.flow)
        # Permite que o QScrollArea calcule altura pelo width (= scroll vertical)
        sp = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.MinimumExpanding)
        sp.setHeightForWidth(True)
        self.setSizePolicy(sp)
        self._cards: list[QWidget] = []

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, w: int) -> int:
        return self.flow.heightForWidth(w)

    def add_card(self, w: QWidget) -> None:
        self._cards.append(w)
        self.flow.addWidget(w)

    def clear_cards(self) -> None:
        while self.flow.count():
            item = self.flow.takeAt(0)
            wid = item.widget()
            if wid is not None:
                wid.deleteLater()
        self._cards = []

    def cards(self) -> list[QWidget]:
        return list(self._cards)

    def _reapply_layout(self) -> None:
        """Repopula o FlowLayout com self._cards na ordem atual (sem destruir)."""
        # Remove sem deletar
        while self.flow.count():
            self.flow.takeAt(0)
        for c in self._cards:
            self.flow.addWidget(c)
        self.flow.invalidate()
        self.updateGeometry()

    def dragEnterEvent(self, e) -> None:
        if e.mimeData().hasFormat(_AppCard.DRAG_MIME):
            e.acceptProposedAction()

    def dragMoveEvent(self, e) -> None:
        if e.mimeData().hasFormat(_AppCard.DRAG_MIME):
            e.acceptProposedAction()

    def dropEvent(self, e) -> None:
        if not e.mimeData().hasFormat(_AppCard.DRAG_MIME):
            return
        app_id = bytes(e.mimeData().data(_AppCard.DRAG_MIME)).decode("utf-8")
        source = next(
            (c for c in self._cards if isinstance(c, _AppCard) and c.app_id == app_id),
            None,
        )
        if source is None:
            return
        cur_index = self._cards.index(source)
        pos = e.position().toPoint()
        others = [c for c in self._cards if c is not source]
        target_index = self._index_at(pos, others)
        if target_index == cur_index:
            e.acceptProposedAction()
            return
        del self._cards[cur_index]
        self._cards.insert(target_index, source)
        self._reapply_layout()
        self.cards_reordered.emit()
        e.acceptProposedAction()

    def _index_at(self, pos, cards: list[QWidget]) -> int:
        """Acha o indice de insercao baseado em pos (ordem de leitura)."""
        for i, c in enumerate(cards):
            r = c.geometry()
            cx, cy = r.center().x(), r.center().y()
            if pos.y() < cy and pos.x() < r.right() + self.card_gap // 2:
                return i
            if abs(pos.y() - cy) < r.height() / 2 and pos.x() < cx:
                return i
        return len(cards)


# Backwards-compat alias
_CardsContainer = _CardsGridContainer


class MainWindow(QWidget):
    # Largura da janela quando o painel de logs abre / esta fechado.
    WIDTH_WITH_LOGS = 1380
    WIDTH_NO_LOGS = 920  # cabe 2 colunas de cards confortavelmente
    CARDS_MIN_W = 420    # 1 coluna minima de card
    LOGS_MIN_W = 420
    # Tamanho padronizado de cada card de aplicacao no grid
    CARD_WIDTH = 380
    CARD_HEIGHT = 320

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Server App Manager")
        self.resize(self.WIDTH_NO_LOGS, 780)
        self.setStyleSheet(APP_STYLESHEET)

        self.config: Config = load_config()
        self.manager = ProcessManager(self.config)

        # service_id -> widgets pra atualizar dinamicamente
        self._dots: dict[str, QLabel] = {}
        self._names: dict[str, QLabel] = {}
        self._start_btns: dict[str, QPushButton] = {}
        self._stop_btns: dict[str, QPushButton] = {}
        self._restart_btns: dict[str, QPushButton] = {}
        # app.id -> botoes "iniciar tudo" / "parar tudo" (toggle por estado)
        self._start_all_btns: dict[str, QPushButton] = {}
        self._stop_all_btns: dict[str, QPushButton] = {}
        # app.id -> Application (pra _apply_status saber qual estado tem)
        self._apps_by_id: dict[str, Application] = {}
        self._running: set[str] = set()
        self._running_by_pid: set[str] = set()
        # service_id -> timestamp em que entrou em "starting"
        self._starting: dict[str, float] = {}
        self._status_proc: QProcess | None = None
        # Painel lateral unico de logs (criado sob demanda pelo botao "Logs").
        self._log_panel: UnifiedLogPanel | None = None
        # Pool pra probes TCP. As tarefas rodam em thread de fundo dedicada
        # (nao bloqueia a UI nem com varios servicos sem responder).
        self._probe_pool = ThreadPoolExecutor(max_workers=8, thread_name_prefix="probe")
        self._running_by_url: set[str] = set()
        self._probe_in_flight = False
        self._probe_bridge = _ProbeBridge()
        self._probe_bridge.result_ready.connect(self._on_url_probe_done)

        self._build_ui()
        self._setup_tray()
        self.rebuild()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll_status)
        self._timer.start(STATUS_INTERVAL_MS)
        self._poll_status()

    # ----- system tray --------------------------------------------------
    def _setup_tray(self) -> None:
        # Sem isso, esconder a janela pra tray faria o app inteiro fechar.
        app = QApplication.instance()
        if app is not None:
            app.setQuitOnLastWindowClosed(False)

        if not QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = None
            return

        icon = self.windowIcon()
        if icon.isNull():
            icon = self.style().standardIcon(QStyle.SP_ComputerIcon)

        self.tray = QSystemTrayIcon(icon, self)
        self.tray.setToolTip("Server App Manager")

        menu = QMenu(self)
        show_act = menu.addAction("Mostrar")
        show_act.triggered.connect(self._show_from_tray)
        menu.addSeparator()
        quit_act = menu.addAction("Sair")
        quit_act.triggered.connect(self._really_quit_app)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

    def _on_tray_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.Trigger:  # single click esquerdo
            self._show_from_tray()

    def _show_from_tray(self) -> None:
        if self.isMinimized() or not self.isVisible():
            self.showNormal()
        self.raise_()
        self.activateWindow()

    # Chamado tambem pelo IPC server quando segunda instancia tenta abrir.
    def show_from_anywhere(self) -> None:
        self._show_from_tray()

    def _really_quit_app(self) -> None:
        # closeEvent ja faz cleanup + app.quit()
        self.close()

    # Minimize -> bandeja
    def changeEvent(self, event) -> None:
        if event.type() == QEvent.WindowStateChange and self.tray is not None:
            if self.windowState() & Qt.WindowMinimized:
                # Adia o hide pra depois do evento ser processado
                QTimer.singleShot(0, self._minimize_to_tray)
        super().changeEvent(event)

    def _minimize_to_tray(self) -> None:
        self.hide()
        if self.tray is None:
            return
        if not getattr(self, "_tray_hint_shown", False):
            self.tray.showMessage(
                "Server App Manager",
                "Continuo rodando na bandeja. Clique no icone pra reabrir.",
                QSystemTrayIcon.Information,
                3000,
            )
            self._tray_hint_shown = True

    # X / Alt+F4 -> SAI de verdade. Pra mandar pra bandeja, minimize.
    def closeEvent(self, event) -> None:
        # Cleanup
        if self._log_panel is not None:
            self._log_panel.suspend()
        self._probe_pool.shutdown(wait=False, cancel_futures=True)
        if self.tray is not None:
            self.tray.hide()
        super().closeEvent(event)
        # Forca quit do app inteiro (QApplication.setQuitOnLastWindowClosed(False)
        # estah setado, entao precisamos pedir explicito).
        app = QApplication.instance()
        if app is not None:
            app.quit()

    # ----- construcao da UI ---------------------------------------------
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 18)
        root.setSpacing(14)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        title = QLabel("Server App Manager")
        title.setStyleSheet("font-size: 16px; font-weight: 600;")
        toolbar.addWidget(title)
        toolbar.addStretch()

        add_btn = QPushButton("+ Aplicacao")
        _set_role(add_btn, "primary")
        logs_btn = QPushButton("Logs")
        logs_btn.setToolTip("Abre/fecha o painel com os logs de todos os servicos")
        reload_btn = QPushButton("Recarregar")
        settings_btn = QPushButton("Configuracoes")
        open_cfg_btn = QPushButton("Abrir config")
        add_btn.clicked.connect(self._add_application)
        logs_btn.clicked.connect(self._open_logs)
        reload_btn.clicked.connect(self._reload)
        settings_btn.clicked.connect(self._open_settings)
        open_cfg_btn.clicked.connect(self._open_config_file)
        for b in (add_btn, logs_btn, reload_btn, settings_btn, open_cfg_btn):
            toolbar.addWidget(b)
        root.addLayout(toolbar)

        # Splitter horizontal: cards a esquerda, painel de logs a direita.
        self.main_splitter = QSplitter(Qt.Horizontal)

        # ScrollArea + grid de cards (responsivo, drag-drop nativo).
        self.cards_container = _CardsGridContainer(self.CARD_WIDTH)
        self.cards_container.cards_reordered.connect(self._on_apps_reordered)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setMinimumWidth(self.CARDS_MIN_W)
        # Sem scroll horizontal — colunas adaptam pelo width disponivel.
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setWidget(self.cards_container)
        self.main_splitter.addWidget(self.scroll)

        # Cards mantem o tamanho preferido; o painel de logs (adicionado sob
        # demanda em _open_logs) absorve o espaco extra.
        self.main_splitter.setStretchFactor(0, 0)
        self.main_splitter.setCollapsible(0, False)
        root.addWidget(self.main_splitter)

    def rebuild(self) -> None:
        """Recria os cards a partir da config atual."""
        scroll_y = self.scroll.verticalScrollBar().value() if hasattr(self, "scroll") else 0

        self._dots.clear()
        self._names.clear()
        self._start_btns.clear()
        self._stop_btns.clear()
        self._restart_btns.clear()
        self._start_all_btns.clear()
        self._stop_all_btns.clear()
        self._apps_by_id.clear()
        self.cards_container.clear_cards()

        if not self.config.applications:
            empty = QLabel(
                "Nenhuma aplicacao cadastrada.\n\n"
                "Clique em \"+ Aplicacao\" para cadastrar seu primeiro projeto."
            )
            empty.setObjectName("muted")
            empty.setAlignment(Qt.AlignCenter)
            empty.setWordWrap(True)
            empty.setStyleSheet(f"color: {TEXT_MUTED}; padding: 60px; font-size: 14px;")
            self.cards_container.add_card(empty)
            return

        for app in self.config.applications:
            self.cards_container.add_card(self._build_card(app))
        self._apply_status()
        if scroll_y:
            QTimer.singleShot(0, lambda y=scroll_y: self.scroll.verticalScrollBar().setValue(y))

    def _on_apps_reordered(self) -> None:
        """Salva nova ordem das aplicacoes apos drag-drop."""
        apps_by_id = {a.id: a for a in self.config.applications}
        new_order = []
        for c in self.cards_container.cards():
            if isinstance(c, _AppCard) and c.app_id in apps_by_id:
                new_order.append(apps_by_id[c.app_id])
        if len(new_order) != len(self.config.applications):
            return
        if [a.id for a in new_order] == [a.id for a in self.config.applications]:
            return
        self.config.applications = new_order
        save_config(self.config)

    _STATE_ORDER = {STATUS_RUNNING: 0, STATUS_STARTING: 1, STATUS_STOPPED: 2}

    def _sorted_services(self, app: Application):
        """Ordena: rodando -> iniciando -> parado; alfabetico em empate."""
        def key(s):
            return (self._STATE_ORDER[self._service_state(s.id)], s.name)
        return sorted(app.services, key=key)

    def _build_card(self, app: Application) -> _AppCard:
        # Carrega imagem opcional pra usar como background do card.
        bg_pixmap = None
        if getattr(app, "icon_path", "") and Path(app.icon_path).exists():
            pix = QPixmap(app.icon_path)
            if not pix.isNull():
                bg_pixmap = pix

        card = _AppCard(app.id, bg_pixmap=bg_pixmap)
        # Sem imagem: usa o stylesheet padrao (#card). Com imagem: paintEvent.
        if bg_pixmap is None:
            card.setObjectName("card")
        card.setFixedSize(self.CARD_WIDTH, self.CARD_HEIGHT)
        card.setToolTip("Arraste pra reordenar")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)

        n_total = len(app.services)
        n_local = sum(1 for s in app.services if not getattr(s, "is_prod", False))
        # "Iniciar tudo / Parar tudo" so faz sentido com >1 servico local.
        show_bulk = n_local > 1

        header = QHBoxLayout()
        header.setSpacing(6)
        title = QLabel(app.name)
        title.setObjectName("cardTitle")
        header.addWidget(title)

        sub_text = f"  ·  {n_total} servico" + ("s" if n_total != 1 else "")
        sub = QLabel(sub_text)
        sub.setObjectName("muted")
        header.addWidget(sub)

        header.addStretch()

        if show_bulk:
            start_all = _icon_button(ICON_PLAY_ALL, "Iniciar tudo", role="start")
            stop_all = _icon_button(ICON_STOP_ALL, "Parar tudo", role="stop")
            start_all.clicked.connect(lambda _, a=app: self._start_all(a))
            stop_all.clicked.connect(lambda _, a=app: self._stop_all(a))
            header.addWidget(start_all)
            header.addWidget(stop_all)
            self._start_all_btns[app.id] = start_all
            self._stop_all_btns[app.id] = stop_all
            self._apps_by_id[app.id] = app

        edit_app = _icon_button(ICON_EDIT, "Editar aplicacao")
        del_app = _icon_button(ICON_DELETE, "Remover aplicacao", role="danger")
        edit_app.clicked.connect(lambda _, a=app: self._edit_application(a))
        del_app.clicked.connect(lambda _, a=app: self._delete_application(a))
        header.addWidget(edit_app)
        header.addWidget(del_app)
        layout.addLayout(header)

        if not app.services:
            none_lbl = QLabel("(sem servicos — clique em \"Editar\" para adicionar)")
            none_lbl.setObjectName("muted")
            none_lbl.setWordWrap(True)
            layout.addWidget(none_lbl)
            layout.addStretch()
            return card

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet(f"color: {BORDER}; background: {BORDER}; max-height: 1px;")
        layout.addWidget(sep)

        # Lista de servicos em scroll interno — mantem o card com altura fixa
        # mesmo quando tem muitos servicos.
        svc_scroll = QScrollArea(card)
        svc_scroll.setWidgetResizable(True)
        svc_scroll.setFrameShape(QFrame.NoFrame)
        svc_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        svc_scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
        )
        svc_content = QWidget()
        svc_content.setStyleSheet("background: transparent;")
        svc_layout = QVBoxLayout(svc_content)
        svc_layout.setContentsMargins(0, 0, 0, 0)
        svc_layout.setSpacing(4)
        svc_layout.setAlignment(Qt.AlignTop)
        for svc in self._sorted_services(app):
            svc_layout.addWidget(self._build_service_row(svc))
        svc_scroll.setWidget(svc_content)
        layout.addWidget(svc_scroll, 1)  # stretch=1 ocupa espaco restante

        return card

    def _build_service_row(self, svc) -> QWidget:
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(2, 2, 2, 2)
        h.setSpacing(6)

        dot = QLabel("●")
        dot.setStyleSheet(_dot_style(STATUS_STOPPED))
        dot.setToolTip(_DOT_LABEL[STATUS_STOPPED])
        self._dots[svc.id] = dot
        h.addWidget(dot)

        name = QLabel(svc.name)
        name.setStyleSheet("font-weight: 500;")
        name.setToolTip(svc.name)  # nome completo no hover
        # Ignored no horizontal: o label pode encolher abaixo da largura do
        # texto em vez de empurrar os botoes pra fora do card quando o nome
        # eh longo (o nome completo continua no tooltip).
        name.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self._names[svc.id] = name
        h.addWidget(name, 1)  # nome ocupa o espaco flexivel

        if getattr(svc, "is_prod", False):
            badge = QLabel("PROD")
            badge.setStyleSheet(
                f"background: rgba(47,129,247,0.18); color: {ACCENT}; "
                "border: 1px solid rgba(47,129,247,0.4); border-radius: 4px; "
                "padding: 1px 6px; font-size: 10px; font-weight: 600;"
            )
            h.addWidget(badge)

        if getattr(svc, "is_prod", False):
            # Servico de producao: so monitorado por URL. So mostra "Abrir".
            if svc.url:
                open_btn = _icon_button(ICON_OPEN, f"Abrir {svc.url}")
                open_btn.clicked.connect(
                    lambda _, u=svc.url: QDesktopServices.openUrl(QUrl(u))
                )
                h.addWidget(open_btn)
            return row

        # Servico local: botoes de controle (todos como icones).
        start = _icon_button(ICON_PLAY, "Iniciar", role="start")
        stop = _icon_button(ICON_STOP, "Parar", role="stop")
        restart = _icon_button(ICON_RESTART, "Reiniciar", role="restart")
        start.clicked.connect(lambda _, s=svc: self._start(s))
        stop.clicked.connect(lambda _, s=svc: self._stop(s))
        restart.clicked.connect(lambda _, s=svc: self._restart(s))
        # Start so aparece quando STOPPED; Stop/Reiniciar quando STARTING ou RUNNING.
        stop.setVisible(False)
        restart.setVisible(False)
        self._start_btns[svc.id] = start
        self._stop_btns[svc.id] = stop
        self._restart_btns[svc.id] = restart
        h.addWidget(start)
        h.addWidget(stop)
        h.addWidget(restart)

        if svc.url:
            open_btn = _icon_button(ICON_OPEN, f"Abrir {svc.url}")
            open_btn.clicked.connect(
                lambda _, u=svc.url: QDesktopServices.openUrl(QUrl(u))
            )
            h.addWidget(open_btn)

        return row

    def _open_logs(self) -> None:
        """Alterna o painel lateral com os logs de todos os servicos."""
        if self._log_panel is not None and self._log_panel.isVisible():
            self._close_logs()
            return

        if self._log_panel is None:
            self._log_panel = UnifiedLogPanel(
                self, self.config, on_close=self._close_logs
            )
            self._log_panel.setMinimumWidth(self.LOGS_MIN_W)
            self.main_splitter.addWidget(self._log_panel)
            self.main_splitter.setStretchFactor(1, 1)
            self.main_splitter.setCollapsible(1, False)
        else:
            # Fechar o painel derruba os tails; reabrir precisa recomeca-los.
            self._log_panel.reload_sources(self.config)
            self._log_panel.setVisible(True)

        # Alarga a janela para acomodar o painel sem espremer os cards.
        cur = self.size()
        target_w = max(cur.width(), self.WIDTH_WITH_LOGS)
        if cur.width() < target_w:
            self.resize(target_w, cur.height())
        self.main_splitter.setSizes(
            [self.CARDS_MIN_W, max(self.LOGS_MIN_W, target_w - self.CARDS_MIN_W - 8)]
        )

    def _close_logs(self) -> None:
        if self._log_panel is None:
            return
        self._log_panel.suspend()
        self._log_panel.setVisible(False)
        # Volta a janela ao tamanho compacto.
        cur = self.size()
        if cur.width() > self.WIDTH_NO_LOGS:
            self.resize(self.WIDTH_NO_LOGS, cur.height())

    def _refresh_log_panel(self) -> None:
        """Re-sincroniza os tails quando a lista de servicos muda."""
        if self._log_panel is not None and self._log_panel.isVisible():
            self._log_panel.reload_sources(self.config)

    # closeEvent esta definido mais acima junto com a logica da tray.

    # ----- acoes de processo --------------------------------------------
    def _start(self, svc) -> None:
        self.manager.start(svc)
        self._starting[svc.id] = time.monotonic()
        self._apply_status()

    def _stop(self, svc) -> None:
        self.manager.stop(svc)
        self._running.discard(svc.id)
        self._starting.pop(svc.id, None)
        self._apply_status()

    def _restart(self, svc) -> None:
        """Para e inicia o servico em seguida.

        A parada usa a mesma logica do botao "Parar": roda o `stop_command`
        quando ele existe e, de qualquer forma, mata o process group do
        comando que o start disparou. Como o stop eh sincrono, quando ele
        retorna o processo antigo ja morreu e o start pode subir limpo.
        """
        self._stop(svc)
        self._start(svc)

    def _start_all(self, app: Application) -> None:
        for svc in app.services:
            if getattr(svc, "is_prod", False):
                continue
            self._start(svc)

    def _stop_all(self, app: Application) -> None:
        for svc in app.services:
            if getattr(svc, "is_prod", False):
                continue
            self._stop(svc)

    # ----- status (polling nao-bloqueante via QProcess) -----------------
    def _poll_status(self) -> None:
        if self._status_proc is not None:
            return  # ainda processando o tick anterior
        argv = wsl_argv(self.config.distro)
        proc = QProcess(self)
        proc.finished.connect(lambda *_: self._on_status_done(proc))
        proc.errorOccurred.connect(lambda *_: self._on_status_done(proc))
        self._status_proc = proc
        proc.start(argv[0], argv[1:])
        # Script vai via stdin embalado em base64 (ver wsl_stdin_payload).
        proc.waitForStarted(2000)
        proc.write(wsl_stdin_payload(build_status_script()).encode("utf-8"))
        proc.closeWriteChannel()

    def _on_status_done(self, proc: QProcess) -> None:
        if self._status_proc is not proc:
            return
        out = bytes(proc.readAllStandardOutput()).decode("utf-8", "replace")
        wsl_alive = {line.strip() for line in out.splitlines() if line.strip()}
        # Junta com PIDs Windows nativos (servicos com runtime="windows").
        try:
            win_alive = running_ids_windows()
        except Exception:
            win_alive = set()
        self._running_by_pid = wsl_alive | win_alive
        self._status_proc = None
        self._dispatch_url_probes()
        self._recompute_running_and_apply()

    def _dispatch_url_probes(self) -> None:
        if self._probe_in_flight:
            return
        url_targets = [
            (svc.id, svc.url)
            for app in self.config.applications
            for svc in app.services
            if svc.url
        ]
        # health_command targets: precisa do service inteiro pra ter dir/runtime
        health_targets = [
            svc
            for app in self.config.applications
            for svc in app.services
            if getattr(svc, "health_command", "").strip() and not getattr(svc, "is_prod", False)
        ]
        if not url_targets and not health_targets:
            self._on_url_probe_done(set())
            return
        self._probe_in_flight = True
        threading.Thread(
            target=self._run_probes,
            args=(url_targets, health_targets, self.config.distro, self.config.shell_init),
            daemon=True,
        ).start()

    def _run_probes(self, url_targets, health_targets, distro, shell_init) -> None:
        alive: set[str] = set()
        try:
            futs = {}
            for sid, url in url_targets:
                f = self._probe_pool.submit(probe_url, url, 0.3)
                futs[f] = sid
            for svc in health_targets:
                f = self._probe_pool.submit(probe_health_command, svc, distro, shell_init, 2.0)
                futs[f] = svc.id
            for fut in as_completed(futs, timeout=3.0):
                try:
                    if fut.result():
                        alive.add(futs[fut])
                except Exception:
                    pass
        except Exception:
            pass
        self._probe_bridge.result_ready.emit(alive)

    def _on_url_probe_done(self, alive: object) -> None:
        self._running_by_url = set(alive) if alive else set()
        self._probe_in_flight = False
        self._recompute_running_and_apply()

    def _recompute_running_and_apply(self) -> None:
        # Snapshot anterior pra detectar mudancas de ordem
        old_state_by_sid = {
            sid: self._service_state(sid) for sid in self._dots
        }
        self._running = self._running_by_pid | self._running_by_url
        for sid in list(self._starting):
            if sid in self._running:
                self._starting.pop(sid, None)
        now = time.monotonic()
        for sid, t in list(self._starting.items()):
            if now - t > STARTING_TIMEOUT_S:
                self._starting.pop(sid, None)

        # Se algum servico mudou de estado, rebuild pra reordenar (rodando primeiro).
        new_state_by_sid = {sid: self._service_state(sid) for sid in self._dots}
        if old_state_by_sid != new_state_by_sid:
            self.rebuild()
        else:
            self._apply_status()

    def _service_state(self, sid: str) -> str:
        if sid in self._running:
            return STATUS_RUNNING
        if sid in self._starting:
            return STATUS_STARTING
        return STATUS_STOPPED

    def _apply_status(self) -> None:
        for sid, dot in self._dots.items():
            state = self._service_state(sid)
            dot.setStyleSheet(_dot_style(state))
            dot.setToolTip(_DOT_LABEL[state])
            start_btn = self._start_btns.get(sid)
            stop_btn = self._stop_btns.get(sid)
            restart_btn = self._restart_btns.get(sid)
            if start_btn is not None and stop_btn is not None:
                is_stopped = state == STATUS_STOPPED
                start_btn.setVisible(is_stopped)
                stop_btn.setVisible(not is_stopped)
                if restart_btn is not None:
                    restart_btn.setVisible(not is_stopped)

        # Botoes "Iniciar tudo" / "Parar tudo" so quando faz sentido.
        for app_id, app in self._apps_by_id.items():
            states = [
                self._service_state(s.id)
                for s in app.services
                if not getattr(s, "is_prod", False)
            ]
            any_stopped = any(s == STATUS_STOPPED for s in states)
            any_active = any(s != STATUS_STOPPED for s in states)
            sa = self._start_all_btns.get(app_id)
            so = self._stop_all_btns.get(app_id)
            if sa is not None:
                sa.setVisible(any_stopped)
            if so is not None:
                so.setVisible(any_active)

    # ----- config / CRUD -------------------------------------------------
    def _save_and_rebuild(self) -> None:
        save_config(self.config)
        self.manager.config = self.config
        self.rebuild()
        self._refresh_log_panel()

    def _add_application(self) -> None:
        dlg = ApplicationDialog(self)
        if dlg.exec() == QDialog.Accepted:
            self.config.applications.append(dlg.result_application())
            self._save_and_rebuild()

    def _edit_application(self, app: Application) -> None:
        dlg = ApplicationDialog(self, app)
        if dlg.exec() == QDialog.Accepted:
            idx = self.config.applications.index(app)
            self.config.applications[idx] = dlg.result_application()
            self._save_and_rebuild()

    def _delete_application(self, app: Application) -> None:
        resp = QMessageBox.question(
            self, "Remover", f"Remover a aplicacao \"{app.name}\"?"
        )
        if resp == QMessageBox.Yes:
            self.config.applications.remove(app)
            self._save_and_rebuild()

    def _reload(self) -> None:
        self.config = load_config()
        self.manager.config = self.config
        self.rebuild()
        self._refresh_log_panel()

    def _open_settings(self) -> None:
        dlg = SettingsDialog(self, self.config, on_update_requested=self._open_update)
        if dlg.exec() == QDialog.Accepted:
            self.config.distro = dlg.distro_edit.text().strip()
            self.config.shell_init = dlg.init_edit.text().strip()
            self._save_and_rebuild()

    def _open_config_file(self) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(CONFIG_PATH)))

    def _open_update(self) -> None:
        dlg = UpdateDialog(self, self.config, on_source_dir_changed=self._save_source_dir)
        dlg.exec()

    def _save_source_dir(self, source_dir: str) -> None:
        self.config.source_dir = source_dir
        save_config(self.config)
