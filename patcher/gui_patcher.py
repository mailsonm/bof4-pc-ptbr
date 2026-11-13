#!/usr/bin/env python3
"""Breath of Fire IV - PT-BR Translation Patcher GUI.

Modern Tkinter GUI for one-click installation and restoration of the Portuguese (PT-BR)
translation patch for Breath of Fire IV PC (GOG / Steam).
"""

import os
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from patcher import BoF4Patcher, auto_detect_game_path, VERSION


class BoF4PatcherGUI(tk.Tk):
    """Graphical interface for Breath of Fire IV Translation Manager."""

    def __init__(self):
        super().__init__()
        self.title(f"Breath of Fire IV - Patch PT-BR v{VERSION}")
        self.geometry("640x480")
        self.minsize(580, 440)
        self.configure(bg="#181a20")

        self.patcher = None
        self.setup_styles()
        self.build_ui()

        # Try auto-detect
        detected = auto_detect_game_path()
        if detected:
            self.path_var.set(detected)
            self.on_path_changed()

    def setup_styles(self):
        self.style = ttk.Style(self)
        self.style.theme_use("clam")

        self.style.configure(".", background="#181a20", foreground="#f0f2f5", font=("Segoe UI", 10))
        self.style.configure("TLabel", background="#181a20", foreground="#e1e4ea")
        self.style.configure("Title.TLabel", font=("Segoe UI", 16, "bold"), foreground="#4dd0e1")
        self.style.configure("Subtitle.TLabel", font=("Segoe UI", 9), foreground="#9aa0a6")
        self.style.configure("Status.TLabel", font=("Segoe UI", 10, "bold"))
        self.style.configure("TFrame", background="#181a20")
        self.style.configure("Card.TFrame", background="#222630", relief="flat")
        self.style.configure("TProgressbar", thickness=16, troughcolor="#1e222d", background="#4dd0e1")

    def build_ui(self):
        # Header
        header_frame = ttk.Frame(self)
        header_frame.pack(fill="x", padx=24, pady=(18, 10))

        title_lbl = ttk.Label(header_frame, text="Breath of Fire IV — Tradução PT-BR", style="Title.TLabel")
        title_lbl.pack(anchor="w")

        sub_lbl = ttk.Label(
            header_frame,
            text=f"Compatível com versões GOG e Steam (PC) • v{VERSION}",
            style="Subtitle.TLabel",
        )
        sub_lbl.pack(anchor="w", pady=(2, 0))

        # Main Card
        card = ttk.Frame(self, style="Card.TFrame", padding=16)
        card.pack(fill="both", expand=True, padx=24, pady=10)

        # Path Selection
        dir_lbl = ttk.Label(card, text="Pasta de Instalação do Jogo:", font=("Segoe UI", 10, "bold"), background="#222630")
        dir_lbl.pack(anchor="w", pady=(0, 6))

        path_box = ttk.Frame(card, style="Card.TFrame")
        path_box.pack(fill="x", pady=(0, 12))

        self.path_var = tk.StringVar()
        self.path_entry = tk.Entry(
            path_box,
            textvariable=self.path_var,
            bg="#16181f",
            fg="#ffffff",
            insertbackground="#ffffff",
            relief="flat",
            font=("Segoe UI", 10),
            highlightthickness=1,
            highlightbackground="#3a3f50",
            highlightcolor="#4dd0e1",
        )
        self.path_entry.pack(side="left", fill="x", expand=True, ipady=6, padx=(0, 8))
        self.path_var.trace_add("write", lambda *args: self.on_path_changed())

        browse_btn = tk.Button(
            path_box,
            text="Procurar...",
            command=self.browse_folder,
            bg="#2d3345",
            fg="#ffffff",
            activebackground="#3b435b",
            activeforeground="#ffffff",
            relief="flat",
            padx=12,
            pady=4,
            cursor="hand2",
        )
        browse_btn.pack(side="right")

        # Status Box
        status_box = ttk.Frame(card, style="Card.TFrame")
        status_box.pack(fill="x", pady=(0, 16))

        self.game_status_lbl = ttk.Label(
            status_box, text="⚪ Nenhuma pasta selecionada", background="#222630", style="Status.TLabel"
        )
        self.game_status_lbl.pack(anchor="w", pady=2)

        self.patch_status_lbl = ttk.Label(
            status_box, text="", background="#222630", foreground="#9aa0a6"
        )
        self.patch_status_lbl.pack(anchor="w", pady=2)

        # Progress Section
        self.progress_lbl = ttk.Label(card, text="", background="#222630", foreground="#b0bec5")
        self.progress_lbl.pack(anchor="w", pady=(0, 4))

        self.progress_bar = ttk.Progressbar(card, mode="determinate")
        self.progress_bar.pack(fill="x", pady=(0, 16))

        # Action Buttons
        btn_box = ttk.Frame(card, style="Card.TFrame")
        btn_box.pack(fill="x", pady=(4, 0))

        self.patch_btn = tk.Button(
            btn_box,
            text="✨ Instalar Tradução PT-BR",
            command=self.start_patch,
            bg="#00838f",
            fg="#ffffff",
            activebackground="#0097a7",
            activeforeground="#ffffff",
            font=("Segoe UI", 11, "bold"),
            relief="flat",
            pady=8,
            cursor="hand2",
            state="disabled",
        )
        self.patch_btn.pack(side="left", fill="x", expand=True, padx=(0, 6))

        self.restore_btn = tk.Button(
            btn_box,
            text="🔄 Restaurar Inglês Original",
            command=self.start_restore,
            bg="#374151",
            fg="#ffffff",
            activebackground="#4b5563",
            activeforeground="#ffffff",
            font=("Segoe UI", 10),
            relief="flat",
            pady=8,
            cursor="hand2",
            state="disabled",
        )
        self.restore_btn.pack(side="right", fill="x", expand=True, padx=(6, 0))

        # Footer
        footer = ttk.Frame(self)
        footer.pack(fill="x", padx=24, pady=(6, 12))

        credits_lbl = ttk.Label(
            footer,
            text="Tradução PS1: nhojunior • Port PC & Ferramentas: Mailson Maia Alves",
            style="Subtitle.TLabel",
        )
        credits_lbl.pack(side="left")

        about_btn = tk.Button(
            footer,
            text="Créditos & Info",
            command=self.show_credits,
            bg="#181a20",
            fg="#4dd0e1",
            relief="flat",
            cursor="hand2",
            activebackground="#181a20",
            activeforeground="#80deea",
        )
        about_btn.pack(side="right")

    def browse_folder(self):
        folder = filedialog.askdirectory(title="Selecione a pasta de instalação do Breath of Fire IV")
        if folder:
            self.path_var.set(folder)

    def on_path_changed(self):
        path = self.path_var.get().strip()
        if not path:
            self.game_status_lbl.config(text="⚪ Nenhuma pasta selecionada", foreground="#e1e4ea")
            self.patch_status_lbl.config(text="")
            self.patch_btn.config(state="disabled")
            self.restore_btn.config(state="disabled")
            return

        self.patcher = BoF4Patcher(path)
        valid, msg = self.patcher.validate_game_dir()
        if not valid:
            self.game_status_lbl.config(text=f"❌ {msg}", foreground="#ff5252")
            self.patch_status_lbl.config(text="Selecione a pasta que contém o arquivo 'BOF4.exe'.")
            self.patch_btn.config(state="disabled")
            self.restore_btn.config(state="disabled")
            return

        # Valid directory
        self.game_status_lbl.config(text="🟢 Jogo detectado: Breath of Fire IV PC", foreground="#69f0ae")
        is_patched = self.patcher.is_patched()
        has_backup = self.patcher.has_backup()

        if is_patched:
            self.patch_status_lbl.config(
                text="Idioma Atual: Português (PT-BR) [Patch Ativo]", foreground="#4dd0e1"
            )
            self.patch_btn.config(text="✨ Reinstalar Tradução PT-BR", state="normal")
            self.restore_btn.config(state="normal" if has_backup else "disabled")
        else:
            self.patch_status_lbl.config(
                text="Idioma Atual: Inglês (Original)", foreground="#b0bec5"
            )
            self.patch_btn.config(text="✨ Instalar Tradução PT-BR", state="normal")
            self.restore_btn.config(state="normal" if has_backup else "disabled")

    def progress_callback(self, current, total, text):
        percent = (current / total) * 100
        self.progress_bar["value"] = percent
        self.progress_lbl.config(text=f"{text} ({current}/{total})")
        self.update_idletasks()

    def start_patch(self):
        if not self.patcher:
            return

        self.patch_btn.config(state="disabled")
        self.restore_btn.config(state="disabled")
        self.progress_bar["value"] = 0

        def run():
            try:
                count, errors = self.patcher.apply_patch(self.progress_callback)
                self.progress_lbl.config(text="Concluído com sucesso!")
                self.progress_bar["value"] = 100
                messagebox.showinfo(
                    "Sucesso!",
                    f"Tradução aplicada com sucesso!\n\n{count} arquivos foram atualizados para PT-BR.\nUm backup dos arquivos originais em inglês foi salvo com segurança em 'DAT_BACKUP_EN'.\n\nBom jogo!",
                )
            except Exception as e:
                messagebox.showerror("Erro ao aplicar patch", str(e))
            finally:
                self.on_path_changed()

        threading.Thread(target=run, daemon=True).start()

    def start_restore(self):
        if not self.patcher:
            return

        confirm = messagebox.askyesno(
            "Confirmar Restauração",
            "Deseja restaurar todos os arquivos originais em inglês a partir do backup 'DAT_BACKUP_EN'?",
        )
        if not confirm:
            return

        self.patch_btn.config(state="disabled")
        self.restore_btn.config(state="disabled")
        self.progress_bar["value"] = 0

        def run():
            try:
                count, errors = self.patcher.restore_backup(self.progress_callback)
                self.progress_lbl.config(text="Restauração concluída!")
                self.progress_bar["value"] = 100
                messagebox.showinfo(
                    "Restaurado",
                    f"Restauração concluída com sucesso!\n\n{count} arquivos foram revertidos para o inglês original.",
                )
            except Exception as e:
                messagebox.showerror("Erro ao restaurar", str(e))
            finally:
                self.on_path_changed()

        threading.Thread(target=run, daemon=True).start()

    def show_credits(self):
        info = (
            "Breath of Fire IV — Tradução para Português (PT-BR) no PC\n"
            f"Versão do Mod: {VERSION}\n\n"
            "Créditos Formais:\n"
            "• nhojunior e equipe: Autores da tradução original para PlayStation 1 (v1.1a).\n"
            "• Mailson Maia Alves: Engenharia reversa, porte dos diálogos e arquivos DAT, adaptação de ponteiros e desenvolvimento do instalador/patcher para PC (GOG e Steam).\n"
            "• CAPCOM Co., Ltd. & GOG.com: Desenvolvedores e publicadores do relançamento clássico no PC.\n\n"
            "Compatibilidade:\n"
            "• GOG Galaxy / Offline Installer (Windows e Linux/Steam Deck)\n"
            "• Steam (AppID 4249150) (Windows e Proton/Steam Deck)\n"
            "• Versão clássica de CD-ROM (2003)"
        )
        messagebox.showinfo("Créditos & Informações", info)


if __name__ == "__main__":
    app = BoF4PatcherGUI()
    app.mainloop()
