"""Ponto de entrada usado por `python main.py` e pelo PyInstaller."""

import sys

from server_app_manager.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
