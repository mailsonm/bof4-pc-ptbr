#!/usr/bin/env python3
"""Launcher script for Breath of Fire IV Save Editor GUI."""

import sys
import os

# Add parent directory to sys.path so modules resolve whether run as script or frozen
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from PyQt6.QtWidgets import QApplication
from gui.app import BoF4EditorWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Breath of Fire IV Save Editor")
    app.setOrganizationName("BreathOfFireIVEditor")

    initial_path = sys.argv[1] if len(sys.argv) > 1 else None
    window = BoF4EditorWindow(initial_path)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
