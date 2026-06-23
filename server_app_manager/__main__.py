import sys

from PySide6.QtCore import QTimer
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication

from .mainwindow import MainWindow

# Identificador do servidor local pra single-instance.
# Inclui o usuario pra evitar colisao em maquina multi-user.
import getpass
_IPC_NAME = f"ServerAppManager-IPC-{getpass.getuser()}"


def _try_show_existing() -> bool:
    """Tenta conectar a uma instancia ja rodando e pedir pra abrir a janela.

    Retorna True se conectou (significa que outra instancia esta viva — esta
    aqui deve sair). False se nao ha instancia: ela continua normalmente.
    """
    sock = QLocalSocket()
    sock.connectToServer(_IPC_NAME)
    if not sock.waitForConnected(500):
        return False
    sock.write(b"SHOW")
    sock.flush()
    sock.waitForBytesWritten(1000)
    sock.disconnectFromServer()
    return True


def _start_ipc_server(window: MainWindow) -> QLocalServer:
    """Inicia o QLocalServer que recebe pedidos de outras instancias."""
    # Limpa socket leftover (crash anterior pode ter deixado o servidor "fantasma")
    QLocalServer.removeServer(_IPC_NAME)

    server = QLocalServer()
    server.setSocketOptions(QLocalServer.UserAccessOption)
    server.listen(_IPC_NAME)

    def on_new_connection():
        conn = server.nextPendingConnection()
        if conn is None:
            return
        def on_ready():
            try:
                _ = bytes(conn.readAll())
            except Exception:
                pass
            # Independente do conteudo, mostra a janela
            window.show_from_anywhere()
            conn.disconnectFromServer()
        conn.readyRead.connect(on_ready)
        # Fallback: se nao receber nada em 500ms, ja mostra mesmo assim
        QTimer.singleShot(500, lambda: (window.show_from_anywhere(), conn.disconnectFromServer()))

    server.newConnection.connect(on_new_connection)
    return server


def main() -> int:
    # Single instance: se ja tem uma rodando, manda ela mostrar a janela e sai.
    # Precisa de QApplication minimamente inicializado pra QLocalSocket.
    bootstrap_app = QApplication(sys.argv)
    if _try_show_existing():
        return 0
    # Continua: esta eh a primeira instancia
    bootstrap_app.setApplicationName("Server App Manager")

    win = MainWindow()
    # Mantem ref no QApplication pro server nao ser GCed
    bootstrap_app._ipc_server = _start_ipc_server(win)

    win.show()
    return bootstrap_app.exec()


if __name__ == "__main__":
    sys.exit(main())
