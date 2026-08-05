"""Dialogos para cadastrar/editar aplicacoes e servicos pela interface."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

import re

from .config import Application, Environment, Service


def _next_dup_name(name: str) -> str:
    """'Backend' -> 'Backend 2'; 'Backend 2' -> 'Backend 3'."""
    m = re.match(r"^(.*?)(\s+)(\d+)\s*$", name)
    if m:
        return f"{m.group(1)}{m.group(2)}{int(m.group(3)) + 1}"
    return f"{name.rstrip()} 2"


class EnvironmentDialog(QDialog):
    """Edita a maquina de um ambiente (aba). Nao mexe nas aplicacoes dele."""

    def __init__(self, parent=None, env: Environment | None = None):
        super().__init__(parent)
        self.setWindowTitle("Ambiente")
        self.setMinimumWidth(520)
        self._env = env

        self.name_edit = QLineEdit(env.name if env else "")
        self.name_edit.setPlaceholderText("Ex.: Este Computador, prism-server")

        self.kind_combo = QComboBox()
        self.kind_combo.addItem("Esta maquina (WSL local)", "local")
        self.kind_combo.addItem("Remota via ssh", "ssh")
        cur = env.kind if env else "local"
        self.kind_combo.setCurrentIndex(1 if cur == "ssh" else 0)
        self.kind_combo.currentIndexChanged.connect(self._update_visibility)

        self.host_edit = QLineEdit(env.ssh_host if env else "")
        self.host_edit.setPlaceholderText("Alias ou user@host do ssh — ex.: prism-server")
        self.distro_edit = QLineEdit(env.distro if env else "")
        self.distro_edit.setPlaceholderText("Ex.: Ubuntu (vazio = distro padrao)")
        self.init_edit = QLineEdit(env.shell_init if env else "")
        self.init_edit.setPlaceholderText(
            'export NVM_DIR="$HOME/.nvm"; [ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh"'
        )
        self.url_host_edit = QLineEdit(env.url_host if env else "")
        self.url_host_edit.setPlaceholderText("Ex.: 192.168.0.3 (vazio = abre a URL como esta)")

        form = QFormLayout()
        form.addRow("Nome:", self.name_edit)
        form.addRow("Onde roda:", self.kind_combo)
        self._host_row = self.host_edit
        form.addRow("Host ssh:", self.host_edit)
        form.addRow("Distro WSL:", self.distro_edit)
        form.addRow("Shell init:", self.init_edit)
        form.addRow("Host das URLs:", self.url_host_edit)
        self._form = form

        self.hint = QLabel()
        self.hint.setWordWrap(True)
        self.hint.setStyleSheet("color: #8b949e;")

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)
        layout.addLayout(form)
        layout.addWidget(self.hint)
        layout.addStretch()
        layout.addWidget(buttons)

        self._update_visibility()

    def _update_visibility(self) -> None:
        is_ssh = self.kind_combo.currentData() == "ssh"
        self.host_edit.setEnabled(is_ssh)
        self.url_host_edit.setEnabled(is_ssh)
        if is_ssh:
            self.hint.setText(
                "Os comandos saem pelo WSL desta maquina e entram por ssh no host "
                "— eh o WSL que tem o ~/.ssh/config e a rota da tailnet, nao o "
                "Windows. A chave precisa funcionar sem senha (BatchMode).\n\n"
                "\"Distro WSL\" aqui eh a distro local de onde o ssh sai. "
                "\"Host das URLs\" substitui localhost ao abrir no navegador, ja "
                "que o localhost de la nao eh o daqui.\n\n"
                "Servicos com runtime=\"windows\" nao sobem por ssh: eles cairiam "
                "numa sessao Windows sem desktop."
            )
        else:
            self.hint.setText(
                "Os comandos rodam no WSL desta maquina — o comportamento "
                "padrao. \"Shell init\" eh prependido a cada comando, util "
                "quando o npm vem do nvm e o ~/.bashrc nao carrega em shell "
                "nao-interativo."
            )

    def _on_accept(self) -> None:
        if not self.name_edit.text().strip():
            QMessageBox.warning(self, "Nome vazio", "Informe um nome para o ambiente.")
            return
        if self.kind_combo.currentData() == "ssh" and not self.host_edit.text().strip():
            QMessageBox.warning(
                self, "Host vazio",
                "Um ambiente remoto precisa do host/alias do ssh.",
            )
            return
        self.accept()

    def result_environment(self) -> Environment:
        env = Environment(
            name=self.name_edit.text().strip(),
            kind=self.kind_combo.currentData(),
            ssh_host=self.host_edit.text().strip(),
            distro=self.distro_edit.text().strip(),
            shell_init=self.init_edit.text().strip(),
            url_host=self.url_host_edit.text().strip(),
        )
        if self._env is not None:
            env.id = self._env.id
        return env


class ServiceDialog(QDialog):
    """Edita um servico (nome, pasta WSL, comando e URL opcional)."""

    def __init__(self, parent=None, service: Service | None = None):
        super().__init__(parent)
        self.setWindowTitle("Servico")
        self.setMinimumWidth(460)

        self.name_edit = QLineEdit(service.name if service else "")
        self.dir_edit = QLineEdit(service.directory if service else "")
        self.cmd_edit = QLineEdit(service.command if service else "")
        self.stop_edit = QLineEdit(service.stop_command if service else "")
        self.health_edit = QLineEdit(service.health_command if service else "")
        self.url_edit = QLineEdit(service.url if service else "")
        self.prod_check = QCheckBox(
            "Servico de producao (so monitora via URL — sem botoes de iniciar/parar/log)"
        )
        self.prod_check.setChecked(bool(service.is_prod) if service else False)

        # Onde rodar o comando.
        self.runtime_combo = QComboBox()
        self.runtime_combo.addItem("WSL (Linux/Ubuntu)", "wsl")
        self.runtime_combo.addItem("Windows (cmd.exe nativo)", "windows")
        cur_runtime = service.runtime if service else "wsl"
        idx = self.runtime_combo.findData(cur_runtime)
        self.runtime_combo.setCurrentIndex(idx if idx >= 0 else 0)

        self.name_edit.setPlaceholderText("Ex.: Backend")
        self.stop_edit.setPlaceholderText("Opcional: comando p/ parar (ex.: docker compose down, make stop)")
        self.health_edit.setPlaceholderText(
            "Opcional: comando que retorna 0 se vivo (ex.: tasklist /FI \"IMAGENAME eq electron.exe\" | findstr /I electron)"
        )
        self.url_edit.setPlaceholderText("http://localhost:8000")

        form = QFormLayout()
        form.addRow("Nome:", self.name_edit)
        form.addRow("URL:", self.url_edit)
        form.addRow("", self.prod_check)
        # Linhas que so fazem sentido pra servico local — ocultadas/exibidas
        # conforme o checkbox "producao".
        self._runtime_label = QLabel("Onde rodar:")
        self._dir_label = QLabel("Pasta:")
        self._cmd_label = QLabel("Comando:")
        self._stop_label = QLabel("Comando p/ parar:")
        self._health_label = QLabel("Comando p/ checar:")
        form.addRow(self._runtime_label, self.runtime_combo)
        form.addRow(self._dir_label, self.dir_edit)
        form.addRow(self._cmd_label, self.cmd_edit)
        form.addRow(self._stop_label, self.stop_edit)
        form.addRow(self._health_label, self.health_edit)

        # Placeholder/label adapta ao runtime escolhido.
        self.runtime_combo.currentIndexChanged.connect(self._update_runtime_hints)
        self._update_runtime_hints()

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

        self._service_id = service.id if service else None

        self.prod_check.toggled.connect(self._update_local_fields_visibility)
        self._update_local_fields_visibility(self.prod_check.isChecked())

    def _update_local_fields_visibility(self, is_prod: bool) -> None:
        """Esconde campos local-only quando o servico eh de producao."""
        for w in (self._runtime_label, self.runtime_combo,
                  self._dir_label, self.dir_edit,
                  self._cmd_label, self.cmd_edit,
                  self._stop_label, self.stop_edit,
                  self._health_label, self.health_edit):
            w.setVisible(not is_prod)

    def _update_runtime_hints(self) -> None:
        """Adapta placeholders de pasta/comando ao runtime escolhido."""
        runtime = self.runtime_combo.currentData()
        if runtime == "windows":
            self._dir_label.setText("Pasta (Windows):")
            self.dir_edit.setPlaceholderText(r"Ex.: C:\projects\meu-app")
            self.cmd_edit.setPlaceholderText(r"Ex.: npm run dev   (cmd.exe nativo)")
        else:
            self._dir_label.setText("Pasta (WSL):")
            self.dir_edit.setPlaceholderText("/home/usuario/projeto/api")
            self.cmd_edit.setPlaceholderText(
                "source .venv/bin/activate && python manage.py runserver"
            )

    def _on_accept(self) -> None:
        if not self.name_edit.text().strip():
            QMessageBox.warning(self, "Campo obrigatorio", "Informe o nome do servico.")
            return
        if self.prod_check.isChecked():
            # Producao: precisa de URL pra monitorar
            if not self.url_edit.text().strip():
                QMessageBox.warning(
                    self, "Campo obrigatorio",
                    "Servicos de producao precisam de URL pra monitoramento.",
                )
                return
        else:
            if not self.dir_edit.text().strip():
                QMessageBox.warning(self, "Campo obrigatorio", "Informe a pasta do servico.")
                return
            if not self.cmd_edit.text().strip():
                QMessageBox.warning(self, "Campo obrigatorio", "Informe o comando do servico.")
                return
        self.accept()

    def result_service(self) -> Service:
        is_prod = self.prod_check.isChecked()
        svc = Service(
            name=self.name_edit.text().strip(),
            directory="" if is_prod else self.dir_edit.text().strip(),
            command="" if is_prod else self.cmd_edit.text().strip(),
            url=self.url_edit.text().strip(),
            stop_command="" if is_prod else self.stop_edit.text().strip(),
            is_prod=is_prod,
            runtime=("wsl" if is_prod else (self.runtime_combo.currentData() or "wsl")),
            health_command="" if is_prod else self.health_edit.text().strip(),
        )
        if self._service_id:
            svc.id = self._service_id
        return svc


class ApplicationDialog(QDialog):
    """Edita uma aplicacao: nome + lista de servicos."""

    def __init__(self, parent=None, application: Application | None = None):
        super().__init__(parent)
        self.setWindowTitle("Aplicacao")
        self.setMinimumWidth(520)

        self._app_id = application.id if application else None
        self._services: list[Service] = (
            [Service.from_dict(s.to_dict()) for s in application.services]
            if application
            else []
        )
        self._icon_path: str = application.icon_path if application else ""

        self.name_edit = QLineEdit(application.name if application else "")
        self.name_edit.setPlaceholderText("Ex.: Meu Site")

        # Icone/imagem do app — aparece como background do card.
        self.icon_preview = QLabel()
        self.icon_preview.setFixedSize(72, 72)
        self.icon_preview.setAlignment(Qt.AlignCenter)
        self.icon_preview.setStyleSheet(
            "border: 1px dashed #30363d; border-radius: 6px;"
        )
        choose_icon_btn = QPushButton("Selecionar...")
        clear_icon_btn = QPushButton("Limpar")
        choose_icon_btn.clicked.connect(self._choose_icon)
        clear_icon_btn.clicked.connect(self._clear_icon)
        icon_btns = QVBoxLayout()
        icon_btns.setSpacing(4)
        icon_btns.addWidget(choose_icon_btn)
        icon_btns.addWidget(clear_icon_btn)
        icon_btns.addStretch()
        self.icon_row = QHBoxLayout()
        self.icon_row.setSpacing(10)
        self.icon_row.addWidget(self.icon_preview)
        self.icon_row.addLayout(icon_btns)
        self.icon_row.addStretch()
        self._refresh_icon_preview()

        self.list = QListWidget()
        self._refresh_list()

        add_btn = QPushButton("Adicionar servico")
        edit_btn = QPushButton("Editar")
        dup_btn = QPushButton("Duplicar")
        del_btn = QPushButton("Remover")
        add_btn.clicked.connect(self._add_service)
        edit_btn.clicked.connect(self._edit_service)
        dup_btn.clicked.connect(self._duplicate_service)
        del_btn.clicked.connect(self._del_service)

        svc_buttons = QHBoxLayout()
        svc_buttons.addWidget(add_btn)
        svc_buttons.addWidget(edit_btn)
        svc_buttons.addWidget(dup_btn)
        svc_buttons.addWidget(del_btn)
        svc_buttons.addStretch()

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.addRow("Nome:", self.name_edit)
        form.addRow("Imagem:", self.icon_row)
        layout.addLayout(form)
        layout.addWidget(QLabel("Servicos:"))
        layout.addWidget(self.list)
        layout.addLayout(svc_buttons)
        layout.addWidget(buttons)

    def _choose_icon(self) -> None:
        start_dir = ""
        if self._icon_path:
            from pathlib import Path
            p = Path(self._icon_path)
            if p.exists():
                start_dir = str(p.parent)
        path, _ = QFileDialog.getOpenFileName(
            self, "Selecionar imagem",
            start_dir,
            "Imagens (*.png *.jpg *.jpeg *.bmp *.svg *.webp *.ico)",
        )
        if path:
            self._icon_path = path
            self._refresh_icon_preview()

    def _clear_icon(self) -> None:
        self._icon_path = ""
        self._refresh_icon_preview()

    def _refresh_icon_preview(self) -> None:
        if not self._icon_path:
            self.icon_preview.clear()
            self.icon_preview.setText("(sem imagem)")
            self.icon_preview.setStyleSheet(
                "border: 1px dashed #30363d; border-radius: 6px; color: #8b949e; font-size: 10px;"
            )
            return
        pix = QPixmap(self._icon_path)
        if pix.isNull():
            self.icon_preview.setText("(invalida)")
            self.icon_preview.setStyleSheet(
                "border: 1px dashed #f85149; border-radius: 6px; color: #f85149; font-size: 10px;"
            )
            return
        self.icon_preview.setPixmap(
            pix.scaled(72, 72, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        )
        self.icon_preview.setStyleSheet("border: 1px solid #30363d; border-radius: 6px;")

    def _refresh_list(self) -> None:
        self.list.clear()
        for svc in self._services:
            item = QListWidgetItem(f"{svc.name}  —  {svc.command}")
            self.list.addItem(item)

    def _selected_index(self) -> int:
        return self.list.currentRow()

    def _add_service(self) -> None:
        dlg = ServiceDialog(self)
        if dlg.exec() == QDialog.Accepted:
            self._services.append(dlg.result_service())
            self._refresh_list()

    def _edit_service(self) -> None:
        idx = self._selected_index()
        if idx < 0:
            return
        dlg = ServiceDialog(self, self._services[idx])
        if dlg.exec() == QDialog.Accepted:
            self._services[idx] = dlg.result_service()
            self._refresh_list()

    def _duplicate_service(self) -> None:
        idx = self._selected_index()
        if idx < 0:
            return
        original = self._services[idx]
        # Cria copia: novo ID, nome com sufixo numerico incrementado
        clone = Service.from_dict(original.to_dict())
        from .config import new_id
        clone.id = new_id()
        clone.name = _next_dup_name(original.name)
        # Abre dialog ja com a copia carregada pra edicao
        dlg = ServiceDialog(self, clone)
        if dlg.exec() == QDialog.Accepted:
            edited = dlg.result_service()
            # Garante que o ID da copia eh novo (ServiceDialog preserva _service_id)
            edited.id = clone.id
            # Insere logo apos o original
            self._services.insert(idx + 1, edited)
            self._refresh_list()
            self.list.setCurrentRow(idx + 1)

    def _del_service(self) -> None:
        idx = self._selected_index()
        if idx < 0:
            return
        del self._services[idx]
        self._refresh_list()

    def _on_accept(self) -> None:
        if not self.name_edit.text().strip():
            QMessageBox.warning(self, "Campo obrigatorio", "Informe o nome da aplicacao.")
            return
        self.accept()

    def result_application(self) -> Application:
        app = Application(
            name=self.name_edit.text().strip(),
            icon_path=self._icon_path,
            services=self._services,
        )
        if self._app_id:
            app.id = self._app_id
        return app
