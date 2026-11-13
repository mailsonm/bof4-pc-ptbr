"""PyQt6 GUI Application for Breath of Fire IV Save Editor."""

import os
import glob
from typing import Optional, List

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QIcon, QColor
from PyQt6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTabWidget,
    QLabel,
    QPushButton,
    QSpinBox,
    QLineEdit,
    QComboBox,
    QTableWidget,
    QTableWidgetItem,
    QFileDialog,
    QMessageBox,
    QGroupBox,
    QGridLayout,
    QHeaderView,
    QScrollArea,
    QSplitter,
    QStatusBar,
)

from bof4_save import (
    SaveFile,
    DEFAULT_SAVE_DIR,
    MAX_ZENNY,
    MAX_GP,
    MAX_LEVEL,
    MAX_HP,
    MAX_AP,
    MAX_STAT,
    MAX_ITEM_QTY,
    CHARACTER_NAMES,
    FISH_SPECIES,
    FISHING_RODS,
    FISHING_LURES,
    FISHERMAN_RANKS,
    ITEM_CATEGORIES,
    get_item_name,
)

DARK_STYLESHEET = """
QMainWindow, QWidget {
    background-color: #1a1b26;
    color: #c0caf5;
    font-family: 'Segoe UI', 'DejaVu Sans', sans-serif;
    font-size: 13px;
}

QGroupBox {
    border: 1px solid #414868;
    border-radius: 8px;
    margin-top: 14px;
    padding-top: 14px;
    font-weight: bold;
    color: #7aa2f7;
}

QGroupBox::title {
    subcontrol-origin: margin;
    left: 14px;
    padding: 0 6px 0 6px;
}

QTabWidget::pane {
    border: 1px solid #414868;
    border-radius: 8px;
    background: #1f2335;
    top: -1px;
}

QTabBar::tab {
    background: #16161e;
    color: #a9b1d6;
    border: 1px solid #414868;
    padding: 8px 18px;
    margin-right: 2px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    font-weight: bold;
}

QTabBar::tab:selected {
    background: #24283b;
    color: #7aa2f7;
    border-bottom: 2px solid #7aa2f7;
}

QTabBar::tab:hover:!selected {
    background: #24283b;
    color: #c0caf5;
}

QPushButton {
    background-color: #24283b;
    border: 1px solid #414868;
    border-radius: 6px;
    padding: 7px 16px;
    font-weight: bold;
    color: #c0caf5;
}

QPushButton:hover {
    background-color: #3b4261;
    border-color: #7aa2f7;
    color: #ffffff;
}

QPushButton:pressed {
    background-color: #1a1b26;
}

QPushButton#primaryBtn {
    background-color: #7aa2f7;
    color: #15161e;
    border: none;
}

QPushButton#primaryBtn:hover {
    background-color: #89b4fa;
}

QPushButton#goldBtn {
    background-color: #e0af68;
    color: #15161e;
    border: none;
}

QPushButton#goldBtn:hover {
    background-color: #f7b76e;
}

QPushButton#greenBtn {
    background-color: #9ece6a;
    color: #15161e;
    border: none;
}

QPushButton#greenBtn:hover {
    background-color: #a6da75;
}

QLineEdit, QSpinBox, QComboBox {
    background-color: #24283b;
    border: 1px solid #414868;
    border-radius: 5px;
    padding: 5px 10px;
    color: #c0caf5;
    selection-background-color: #7aa2f7;
    selection-color: #15161e;
}

QLineEdit:focus, QSpinBox:focus, QComboBox:focus {
    border: 1px solid #7aa2f7;
}

QTableWidget {
    background-color: #1f2335;
    border: 1px solid #414868;
    border-radius: 6px;
    gridline-color: #292e42;
    selection-background-color: #3d59a1;
    selection-color: #ffffff;
}

QHeaderView::section {
    background-color: #16161e;
    color: #7aa2f7;
    padding: 6px;
    border: 1px solid #292e42;
    font-weight: bold;
}

QScrollBar:vertical {
    border: none;
    background: #16161e;
    width: 10px;
    margin: 0px;
}

QScrollBar::handle:vertical {
    background: #414868;
    min-height: 20px;
    border-radius: 5px;
}

QScrollBar::handle:vertical:hover {
    background: #7aa2f7;
}

QStatusBar {
    background-color: #16161e;
    color: #9aa5ce;
    border-top: 1px solid #292e42;
}
"""


class BoF4EditorWindow(QMainWindow):
    """Main Window for Breath of Fire IV Save Editor."""

    def __init__(self, initial_save_path: Optional[str] = None):
        super().__init__()
        self.setWindowTitle("Breath of Fire IV - Save Editor (PC / GOG / Steam)")
        self.resize(1050, 750)
        self.setStyleSheet(DARK_STYLESHEET)

        self.save_file: Optional[SaveFile] = None
        self.current_save_path: Optional[str] = None

        self._init_ui()

        # Load initial save or auto-detect
        if initial_save_path and os.path.isfile(initial_save_path):
            self.load_save_file(initial_save_path)
        else:
            self._auto_detect_save()

    def _init_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)

        # Top Bar: File & Slot Selector
        top_bar = QHBoxLayout()
        top_bar.setSpacing(10)

        top_bar.addWidget(QLabel("<b>Slot de Save:</b>"))
        self.slot_combo = QComboBox()
        self.slot_combo.setMinimumWidth(260)
        self.slot_combo.currentIndexChanged.connect(self._on_slot_selected)
        top_bar.addWidget(self.slot_combo)

        btn_browse = QPushButton("📁 Abrir Arquivo...")
        btn_browse.clicked.connect(self._browse_save_file)
        top_bar.addWidget(btn_browse)

        btn_reload = QPushButton("🔄 Recarregar")
        btn_reload.clicked.connect(self._reload_save)
        top_bar.addWidget(btn_reload)

        top_bar.addStretch()

        self.btn_god_mode = QPushButton("⚡ God Mode Completo")
        self.btn_god_mode.setObjectName("goldBtn")
        self.btn_god_mode.clicked.connect(self._apply_god_mode_ui)
        top_bar.addWidget(self.btn_god_mode)

        self.btn_save = QPushButton("💾 Salvar Alterações")
        self.btn_save.setObjectName("primaryBtn")
        self.btn_save.clicked.connect(self._save_changes)
        top_bar.addWidget(self.btn_save)

        main_layout.addLayout(top_bar)

        # Status Bar / Checksum Info
        self.status_label = QLabel("Nenhum arquivo carregado.")
        self.status_label.setStyleSheet("color: #7dcfff; padding: 2px 4px; font-weight: bold;")
        main_layout.addWidget(self.status_label)

        # Tabs
        self.tabs = QTabWidget()
        self.tab_general = self._create_general_tab()
        self.tab_characters = self._create_characters_tab()
        self.tab_fishing = self._create_fishing_tab()
        self.tab_inventory = self._create_inventory_tab()

        self.tabs.addTab(self.tab_general, "💰 Geral & Economia")
        self.tabs.addTab(self.tab_characters, "⚔️ Personagens (7)")
        self.tabs.addTab(self.tab_fishing, "🎣 Pescaria & Manillo")
        self.tabs.addTab(self.tab_inventory, "🎒 Inventário & Baú")

        main_layout.addWidget(self.tabs)

        # Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Pronto")

    # ==================== TAB 1: GERAL ====================
    def _create_general_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(14)

        # Economy Box
        grp_econ = QGroupBox("Economia & Recursos")
        grid_econ = QGridLayout(grp_econ)
        grid_econ.setSpacing(12)

        grid_econ.addWidget(QLabel("<b>Zenny (Dinheiro):</b>"), 0, 0)
        self.spin_zenny = QSpinBox()
        self.spin_zenny.setRange(0, MAX_ZENNY)
        self.spin_zenny.setSingleStep(1000)
        grid_econ.addWidget(self.spin_zenny, 0, 1)

        btn_max_zenny = QPushButton("Max (99.999.999)")
        btn_max_zenny.clicked.connect(lambda: self.spin_zenny.setValue(MAX_ZENNY))
        grid_econ.addWidget(btn_max_zenny, 0, 2)

        grid_econ.addWidget(QLabel("<b>Game Points (GP):</b>"), 1, 0)
        self.spin_gp = QSpinBox()
        self.spin_gp.setRange(0, MAX_GP)
        self.spin_gp.setSingleStep(1000)
        grid_econ.addWidget(self.spin_gp, 1, 1)

        btn_max_gp = QPushButton("Max GP (65.000)")
        btn_max_gp.clicked.connect(lambda: self.spin_gp.setValue(65000))
        grid_econ.addWidget(btn_max_gp, 1, 2)

        gp_info = QLabel("<i>Nota: Game Points (GP) aumentam o poder dos sopros de dragão (Kaiser Breath / Punk Breath) nos marcos de 10k, 25k, 35k, 50k e 62k pts.</i>")
        gp_info.setStyleSheet("color: #9aa5ce; font-size: 11px;")
        grid_econ.addWidget(gp_info, 2, 0, 1, 3)

        layout.addWidget(grp_econ)

        # Quick Actions Box
        grp_actions = QGroupBox("Ações Rápidas Globais")
        box_actions = QVBoxLayout(grp_actions)
        box_actions.setSpacing(10)

        btn_full_god = QPushButton("⚡ Aplicar God Mode Completo (Zenny Max + GP 65k + Personagens Lvl 99 + Pesca Max + Itens x99)")
        btn_full_god.setObjectName("goldBtn")
        btn_full_god.clicked.connect(self._apply_god_mode_ui)
        box_actions.addWidget(btn_full_god)

        btn_max_chars = QPushButton("⚔️ Maximizar Todos os 7 Personagens (Nível 99, 9999 HP, 999 AP, Stats 999)")
        btn_max_chars.setObjectName("greenBtn")
        btn_max_chars.clicked.connect(self._maximize_all_characters)
        box_actions.addWidget(btn_max_chars)

        btn_max_all_items = QPushButton("🎒 Desbloquear Catálogo Completo de Itens, Armas, Armaduras e Acessórios (x99)")
        btn_max_all_items.clicked.connect(self._fill_full_catalog_items)
        box_actions.addWidget(btn_max_all_items)

        layout.addWidget(grp_actions)
        layout.addStretch()
        return widget

    # ==================== TAB 2: PERSONAGENS ====================
    def _create_characters_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(14, 14, 14, 14)

        # Character Selector Bar
        top_bar = QHBoxLayout()
        top_bar.addWidget(QLabel("<b>Selecionar Personagem:</b>"))
        self.char_combo = QComboBox()
        for c in CHARACTER_NAMES:
            self.char_combo.addItem(f"[{c['id']}] {c['default_name']} - {c['title']}")
        self.char_combo.currentIndexChanged.connect(self._on_char_selected)
        top_bar.addWidget(self.char_combo)

        btn_max_char = QPushButton("⭐ Maximizar Este Personagem")
        btn_max_char.setObjectName("greenBtn")
        btn_max_char.clicked.connect(self._maximize_current_character)
        top_bar.addWidget(btn_max_char)

        layout.addLayout(top_bar)

        # Stats Area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        stats_widget = QWidget()
        grid = QGridLayout(stats_widget)
        grid.setSpacing(12)

        # Name & Level
        grid.addWidget(QLabel("<b>Nome:</b>"), 0, 0)
        self.char_name = QLineEdit()
        self.char_name.setMaxLength(6)
        grid.addWidget(self.char_name, 0, 1)

        grid.addWidget(QLabel("<b>Nível (1-99):</b>"), 0, 2)
        self.char_level = QSpinBox()
        self.char_level.setRange(1, MAX_LEVEL)
        grid.addWidget(self.char_level, 0, 3)

        grid.addWidget(QLabel("<b>Experiência (EXP):</b>"), 1, 0)
        self.char_exp = QSpinBox()
        self.char_exp.setRange(0, 99_999_999)
        self.char_exp.setSingleStep(1000)
        grid.addWidget(self.char_exp, 1, 1)

        grid.addWidget(QLabel("<b>Mestre (Master ID):</b>"), 1, 2)
        self.char_master = QSpinBox()
        self.char_master.setRange(0, 255)
        grid.addWidget(self.char_master, 1, 3)

        # HP & AP
        grid.addWidget(QLabel("<b>HP Atual:</b>"), 2, 0)
        self.char_cur_hp = QSpinBox()
        self.char_cur_hp.setRange(1, MAX_HP)
        grid.addWidget(self.char_cur_hp, 2, 1)

        grid.addWidget(QLabel("<b>HP Máximo (Total):</b>"), 2, 2)
        self.char_max_hp = QSpinBox()
        self.char_max_hp.setRange(1, MAX_HP)
        grid.addWidget(self.char_max_hp, 2, 3)

        grid.addWidget(QLabel("<b>AP Atual:</b>"), 3, 0)
        self.char_cur_ap = QSpinBox()
        self.char_cur_ap.setRange(0, MAX_AP)
        grid.addWidget(self.char_cur_ap, 3, 1)

        grid.addWidget(QLabel("<b>AP Máximo (Total):</b>"), 3, 2)
        self.char_max_ap = QSpinBox()
        self.char_max_ap.setRange(0, MAX_AP)
        grid.addWidget(self.char_max_ap, 3, 3)

        # Base Stats
        grid.addWidget(QLabel("<b>Poder (PWR):</b>"), 4, 0)
        self.char_pwr = QSpinBox()
        self.char_pwr.setRange(0, MAX_STAT)
        grid.addWidget(self.char_pwr, 4, 1)

        grid.addWidget(QLabel("<b>Defesa (DEF):</b>"), 4, 2)
        self.char_def = QSpinBox()
        self.char_def.setRange(0, MAX_STAT)
        grid.addWidget(self.char_def, 4, 3)

        grid.addWidget(QLabel("<b>Agilidade (AGL):</b>"), 5, 0)
        self.char_agl = QSpinBox()
        self.char_agl.setRange(0, MAX_STAT)
        grid.addWidget(self.char_agl, 5, 1)

        grid.addWidget(QLabel("<b>Sabedoria (WIS):</b>"), 5, 2)
        self.char_wis = QSpinBox()
        self.char_wis.setRange(0, MAX_STAT)
        grid.addWidget(self.char_wis, 5, 3)

        grid.addWidget(QLabel("<b>Pontos de Combo (CP):</b>"), 6, 0)
        self.char_cp = QSpinBox()
        self.char_cp.setRange(0, MAX_STAT)
        grid.addWidget(self.char_cp, 6, 1)

        # Equipment
        grid.addWidget(QLabel("<b>ID Arma Equipada:</b>"), 7, 0)
        self.char_weap = QSpinBox()
        self.char_weap.setRange(0, 255)
        grid.addWidget(self.char_weap, 7, 1)

        grid.addWidget(QLabel("<b>ID Armadura:</b>"), 7, 2)
        self.char_armr = QSpinBox()
        self.char_armr.setRange(0, 255)
        grid.addWidget(self.char_armr, 7, 3)

        grid.addWidget(QLabel("<b>ID Acessório:</b>"), 8, 0)
        self.char_acc = QSpinBox()
        self.char_acc.setRange(0, 255)
        grid.addWidget(self.char_acc, 8, 1)

        scroll.setWidget(stats_widget)
        layout.addWidget(scroll)
        return widget

    # ==================== TAB 3: PESCARIA ====================
    def _create_fishing_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(12)

        # Overview Box
        grp_overview = QGroupBox("Status de Pescador & Equipamento")
        grid = QGridLayout(grp_overview)
        grid.setSpacing(10)

        grid.addWidget(QLabel("<b>Pontuação Total de Pesca:</b>"), 0, 0)
        self.fish_total_label = QLabel("0 pts")
        self.fish_total_label.setStyleSheet("color: #e0af68; font-size: 15px; font-weight: bold;")
        grid.addWidget(self.fish_total_label, 0, 1)

        grid.addWidget(QLabel("<b>Rank de Pescador:</b>"), 0, 2)
        self.fish_rank_combo = QComboBox()
        for r in FISHERMAN_RANKS:
            self.fish_rank_combo.addItem(f"{r['name']} ({r['name_pt']})", r["id"])
        grid.addWidget(self.fish_rank_combo, 0, 3)

        grid.addWidget(QLabel("<b>Vara de Pesca:</b>"), 1, 0)
        self.fish_rod_combo = QComboBox()
        for rod in FISHING_RODS:
            self.fish_rod_combo.addItem(f"{rod['name']} ({rod['name_pt']})", rod["id"])
        grid.addWidget(self.fish_rod_combo, 1, 1)

        grid.addWidget(QLabel("<b>Isca Equipada:</b>"), 1, 2)
        self.fish_lure_combo = QComboBox()
        for lure in FISHING_LURES:
            self.fish_lure_combo.addItem(f"{lure['name']} ({lure['name_pt']})", lure["id"])
        grid.addWidget(self.fish_lure_combo, 1, 3)

        btn_max_fishing = QPushButton("🏆 Tornar Mestre Supremo da Pesca (The Fish + 9.999 pts + Master's Rod)")
        btn_max_fishing.setObjectName("goldBtn")
        btn_max_fishing.clicked.connect(self._maximize_fishing_ui)
        grid.addWidget(btn_max_fishing, 2, 0, 1, 4)

        layout.addWidget(grp_overview)

        # Fish Records Table
        layout.addWidget(QLabel("<b>Livro de Pesca (30 Espécies de Peixes):</b>"))
        self.fish_table = QTableWidget()
        self.fish_table.setColumnCount(6)
        self.fish_table.setHorizontalHeaderLabels([
            "ID", "Nome (PT-BR)", "Nome (EN)", "Tamanho (cm)", "Pontos Obtidos", "Meta Recorde"
        ])
        self.fish_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.fish_table.cellChanged.connect(self._on_fish_cell_changed)
        layout.addWidget(self.fish_table)

        return widget

    # ==================== TAB 4: INVENTARIO ====================
    def _create_inventory_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        # Actions Bar
        actions_bar = QHBoxLayout()
        btn_max_qty = QPushButton("📦 Maximizar Quantidade de Itens Existentes (x99)")
        btn_max_qty.clicked.connect(self._max_existing_items_ui)
        actions_bar.addWidget(btn_max_qty)

        btn_fill_all = QPushButton("🌟 Preencher Catálogo Completo (x99)")
        btn_fill_all.setObjectName("goldBtn")
        btn_fill_all.clicked.connect(self._fill_full_catalog_items)
        actions_bar.addWidget(btn_fill_all)

        actions_bar.addStretch()
        layout.addLayout(actions_bar)

        # Subtabs for Categories
        self.inv_tabs = QTabWidget()
        self.inv_tables: List[QTableWidget] = []

        categories = [
            ("Itens / Consumíveis", 0),
            ("Armas", 1),
            ("Armaduras", 2),
            ("Acessórios", 3),
        ]

        for cat_name, cat_idx in categories:
            table = QTableWidget()
            table.setColumnCount(4)
            table.setHorizontalHeaderLabels(["Slot #", "Nome do Item", "ID do Item", "Quantidade (0-99)"])
            table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
            self.inv_tables.append(table)
            self.inv_tabs.addTab(table, cat_name)

        layout.addWidget(self.inv_tabs)
        return widget

    # ==================== DATA SYNC & LOGIC ====================
    def _auto_detect_save(self):
        saves = glob.glob(os.path.join(DEFAULT_SAVE_DIR, "[0-9][0-9].DAT"))
        self.slot_combo.clear()
        if saves:
            saves.sort()
            for s in saves:
                base = os.path.basename(s)
                self.slot_combo.addItem(f"{base} ({s})", s)
            self.load_save_file(saves[0])
        else:
            self.status_label.setText("Nenhum save encontrado no diretório padrão.")

    def _browse_save_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Selecionar Arquivo de Save de Breath of Fire IV",
            DEFAULT_SAVE_DIR,
            "BoF4 Save Files (*.DAT);;All Files (*)",
        )
        if path:
            self.load_save_file(path)

    def _on_slot_selected(self, index: int):
        if index >= 0 and self.slot_combo.count() > 0:
            path = self.slot_combo.itemData(index)
            if path and path != self.current_save_path:
                self.load_save_file(path)

    def load_save_file(self, file_path: str):
        try:
            self.save_file = SaveFile(file_path)
            self.current_save_path = file_path
            self._populate_ui()
            valid = self.save_file.is_checksum_valid()
            ck_status = "VÁLIDO ✓" if valid else "INVÁLIDO (será corrigido ao salvar)"
            self.status_label.setText(
                f"Arquivo: {os.path.basename(file_path)} | Tamanho: {len(self.save_file.data)} bytes | Checksum: 0x{self.save_file.stored_checksum:02X} ({ck_status})"
            )
            self.status_bar.showMessage(f"Carregado com sucesso: {file_path}", 5000)
        except Exception as e:
            QMessageBox.critical(self, "Erro ao carregar save", f"Falha ao ler {file_path}:\n{e}")

    def _reload_save(self):
        if self.current_save_path:
            self.load_save_file(self.current_save_path)

    def _populate_ui(self):
        if not self.save_file:
            return

        # General
        self.spin_zenny.setValue(self.save_file.zenny)
        self.spin_gp.setValue(self.save_file.gp)

        # Character (first selected)
        self._load_character_to_ui(self.char_combo.currentIndex())

        # Fishing
        self._populate_fishing_ui()

        # Inventory
        self._populate_inventory_ui()

    def _on_char_selected(self, index: int):
        if not self.save_file:
            return
        # Save previous before loading next?
        self._load_character_to_ui(index)

    def _load_character_to_ui(self, index: int):
        if not self.save_file or not (0 <= index < 7):
            return
        char = self.save_file.get_character(index)
        self.char_name.setText(char.name)
        self.char_level.setValue(char.level)
        self.char_exp.setValue(char.exp)
        self.char_cur_hp.setValue(char.current_hp)
        self.char_max_hp.setValue(char.total_max_hp)
        self.char_cur_ap.setValue(char.current_ap)
        self.char_max_ap.setValue(char.total_max_ap)
        self.char_cp.setValue(char.cp)
        self.char_pwr.setValue(char.pwr)
        self.char_def.setValue(char.defense)
        self.char_agl.setValue(char.agl)
        self.char_wis.setValue(char.wis)
        self.char_master.setValue(char.master)
        self.char_weap.setValue(char.weapon)
        self.char_armr.setValue(char.armor)
        self.char_acc.setValue(char.accessory)

    def _save_current_character_from_ui(self):
        if not self.save_file:
            return
        idx = self.char_combo.currentIndex()
        if not (0 <= idx < 7):
            return
        char = self.save_file.get_character(idx)
        char.name = self.char_name.text()
        char.level = self.char_level.value()
        char.exp = self.char_exp.value()
        char.current_hp = self.char_cur_hp.value()
        char.total_max_hp = self.char_max_hp.value()
        char.base_max_hp = self.char_max_hp.value()
        char.current_ap = self.char_cur_ap.value()
        char.total_max_ap = self.char_max_ap.value()
        char.base_max_ap = self.char_max_ap.value()
        char.cp = self.char_cp.value()
        char.pwr = self.char_pwr.value()
        char.defense = self.char_def.value()
        char.agl = self.char_agl.value()
        char.wis = self.char_wis.value()
        char.master = self.char_master.value()
        char.weapon = self.char_weap.value()
        char.armor = self.char_armr.value()
        char.accessory = self.char_acc.value()

    def _maximize_current_character(self):
        if not self.save_file:
            return
        idx = self.char_combo.currentIndex()
        char = self.save_file.get_character(idx)
        char.max_stats()
        self._load_character_to_ui(idx)
        self.status_bar.showMessage(f"Personagem {char.name or idx} maximizado!", 3000)

    def _maximize_all_characters(self):
        if not self.save_file:
            return
        for char in self.save_file.characters:
            char.max_stats()
        self._load_character_to_ui(self.char_combo.currentIndex())
        QMessageBox.information(self, "Sucesso", "Todos os 7 personagens foram elevados ao Nível 99 com atributos no máximo!")

    def _populate_fishing_ui(self):
        if not self.save_file:
            return
        fishing = self.save_file.fishing
        self.fish_total_label.setText(f"{fishing.total_points:,} pts")

        # Rank
        for i in range(self.fish_rank_combo.count()):
            if self.fish_rank_combo.itemData(i) == fishing.rank:
                self.fish_rank_combo.setCurrentIndex(i)
                break

        # Rod
        for i in range(self.fish_rod_combo.count()):
            if self.fish_rod_combo.itemData(i) == fishing.rod:
                self.fish_rod_combo.setCurrentIndex(i)
                break

        # Lure
        for i in range(self.fish_lure_combo.count()):
            if self.fish_lure_combo.itemData(i) == fishing.lure:
                self.fish_lure_combo.setCurrentIndex(i)
                break

        # Table
        self.fish_table.blockSignals(True)
        self.fish_table.setRowCount(30)
        records = fishing.get_all_records()
        for row, rec in enumerate(records):
            item_id = QTableWidgetItem(str(rec["id"]))
            item_id.setFlags(item_id.flags() & ~Qt.ItemFlag.ItemIsEditable)

            item_name_pt = QTableWidgetItem(rec["name_pt"])
            item_name_pt.setFlags(item_name_pt.flags() & ~Qt.ItemFlag.ItemIsEditable)

            item_name_en = QTableWidgetItem(rec["name"])
            item_name_en.setFlags(item_name_en.flags() & ~Qt.ItemFlag.ItemIsEditable)

            item_len = QTableWidgetItem(str(rec["length"]))
            item_pts = QTableWidgetItem(str(rec["points"]))

            item_goal = QTableWidgetItem(f"{rec['max_len']} cm / {rec['max_pts']} pts")
            item_goal.setFlags(item_goal.flags() & ~Qt.ItemFlag.ItemIsEditable)
            item_goal.setForeground(QColor("#7aa2f7"))

            self.fish_table.setItem(row, 0, item_id)
            self.fish_table.setItem(row, 1, item_name_pt)
            self.fish_table.setItem(row, 2, item_name_en)
            self.fish_table.setItem(row, 3, item_len)
            self.fish_table.setItem(row, 4, item_pts)
            self.fish_table.setItem(row, 5, item_goal)

        self.fish_table.blockSignals(False)

    def _on_fish_cell_changed(self, row: int, col: int):
        if not self.save_file or col not in (3, 4):
            return
        try:
            val = int(self.fish_table.item(row, col).text())
            if col == 3:
                self.save_file.fishing.set_fish_length(row, val)
            elif col == 4:
                self.save_file.fishing.set_fish_points(row, val)
                self.fish_total_label.setText(f"{self.save_file.fishing.total_points:,} pts")
        except ValueError:
            pass

    def _maximize_fishing_ui(self):
        if not self.save_file:
            return
        self.save_file.fishing.max_all_fishing()
        self._populate_fishing_ui()
        self.status_bar.showMessage("Livro de pesca e status de pescador maximizados com sucesso!", 3000)

    def _populate_inventory_ui(self):
        if not self.save_file:
            return
        inv = self.save_file.inventory
        for cat_idx, table in enumerate(self.inv_tables):
            table.blockSignals(True)
            table.setRowCount(128)
            slots = inv.get_category_slots(cat_idx)
            for row, s in enumerate(slots):
                slot_item = QTableWidgetItem(f"Slot {s['slot']:03d}")
                slot_item.setFlags(slot_item.flags() & ~Qt.ItemFlag.ItemIsEditable)

                name_item = QTableWidgetItem(s["name"])
                id_item = QTableWidgetItem(str(s["item_id"]))
                qty_item = QTableWidgetItem(str(s["qty"]))

                if s["is_empty"]:
                    name_item.setForeground(QColor("#565f89"))
                    id_item.setForeground(QColor("#565f89"))
                    qty_item.setForeground(QColor("#565f89"))
                else:
                    qty_item.setForeground(QColor("#9ece6a"))

                table.setItem(row, 0, slot_item)
                table.setItem(row, 1, name_item)
                table.setItem(row, 2, id_item)
                table.setItem(row, 3, qty_item)

            table.cellChanged.connect(lambda r, c, cat=cat_idx: self._on_inv_cell_changed(cat, r, c))
            table.blockSignals(False)

    def _on_inv_cell_changed(self, cat_idx: int, row: int, col: int):
        if not self.save_file or col not in (2, 3):
            return
        table = self.inv_tables[cat_idx]
        try:
            iid = int(table.item(row, 2).text())
            qty = int(table.item(row, 3).text())
            self.save_file.inventory.set_slot(cat_idx, row, iid, qty)
            table.item(row, 1).setText(get_item_name(cat_idx, iid))
        except (ValueError, AttributeError):
            pass

    def _max_existing_items_ui(self):
        if not self.save_file:
            return
        self.save_file.inventory.set_all_existing_to_max()
        self._populate_inventory_ui()
        self.status_bar.showMessage("Todos os itens existentes foram definidos para quantidade 99!", 3000)

    def _fill_full_catalog_items(self):
        if not self.save_file:
            return
        reply = QMessageBox.question(
            self,
            "Confirmar Desbloqueio Geral",
            "Deseja preencher todo o inventário (Itens, Armas, Armaduras, Acessórios) com todos os itens do jogo (x99)?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.save_file.inventory.max_all_catalog()
            self._populate_inventory_ui()
            QMessageBox.information(self, "Sucesso", "Todo o catálogo de itens do jogo foi adicionado ao seu inventário!")

    def _apply_god_mode_ui(self):
        if not self.save_file:
            return
        reply = QMessageBox.question(
            self,
            "Aplicar God Mode Completo",
            "Isso irá definir:\n"
            "• Zenny Máximo (99.999.999)\n"
            "• Game Points para 65.000 (Sopros de Dragão Kaiser/Punk)\n"
            "• Todos os 7 personagens no Nível 99 com 9999 HP e atributos máximos\n"
            "• Rank de Pesca 'The Fish', vara Master's Rod e 30 peixes recordes\n"
            "• Quantidade 99 para todos os itens do inventário\n\n"
            "Deseja prosseguir?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.save_file.apply_god_mode()
            self._populate_ui()
            QMessageBox.information(self, "God Mode Ativado", "Todas as melhorias lendárias foram aplicadas com sucesso!")

    def _save_changes(self):
        if not self.save_file or not self.current_save_path:
            QMessageBox.warning(self, "Aviso", "Nenhum arquivo carregado para salvar.")
            return

        try:
            # Sync General
            self.save_file.zenny = self.spin_zenny.value()
            self.save_file.gp = self.spin_gp.value()

            # Sync Current Character
            self._save_current_character_from_ui()

            # Sync Fishing Meta
            self.save_file.fishing.rank = self.fish_rank_combo.currentData()
            self.save_file.fishing.rod = self.fish_rod_combo.currentData()
            self.save_file.fishing.lure = self.fish_lure_combo.currentData()

            # Save to disk with automatic backup
            saved_path = self.save_file.save(self.current_save_path, make_backup=True)

            QMessageBox.information(
                self,
                "Salvo com Sucesso",
                f"O save foi salvo com sucesso em:\n{saved_path}\n\n"
                f"Checksum recalculado: 0x{self.save_file.stored_checksum:02X} (OK)\n"
                "Um backup (.bak) de segurança foi gerado automaticamente.",
            )
            self.status_bar.showMessage(f"Salvo com sucesso: {saved_path}", 5000)
        except Exception as e:
            QMessageBox.critical(self, "Erro ao salvar", f"Ocorreu um erro ao gravar as alterações:\n{e}")
