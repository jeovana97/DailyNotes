"""
Janela modal dedicada para exibir as novidades e histórico de versões (CHANGELOG.md)
diretamente no aplicativo, sem depender da tela de verificação de atualizações.
"""

import re
import webbrowser
from typing import List, Dict, Any
import customtkinter as ctk

import config
from version import APP_SHORT_NAME, read_changelog_text
from utils.date_utils import format_date_br
from utils.window_utils import center_modal_on_parent


_CATEGORY_META = {
    "added": ("✨ Novidades", "success"),
    "changed": ("🔧 Melhorias e Alterações", "primary"),
    "fixed": ("🛠️ Correções", "warning"),
    "security": ("🔒 Segurança", "secondary"),
    "removed": ("🗑️ Removidos", "danger"),
}


def _clean_md_inline(text: str) -> str:
    """Remove marcações simples de Markdown (**negrito**, `código`) para leitura limpa na UI."""
    cleaned = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    cleaned = re.sub(r"`([^`]+)`", r"\1", cleaned)
    return cleaned.strip()


def parse_changelog(markdown_text: str) -> List[Dict[str, Any]]:
    """
    Analisa o texto do CHANGELOG.md no padrão Keep a Changelog e retorna uma lista de versões:
    [
        {
            "version": "1.5.0",
            "date_iso": "2026-11-19",
            "date_br": "19/11/2026",
            "sections": [
                {"category": "added", "items": ["...", "..."]},
                ...
            ]
        },
        ...
    ]
    """
    versions: List[Dict[str, Any]] = []
    if not markdown_text:
        return versions

    current_ver: Dict[str, Any] = {}
    current_sec: Dict[str, Any] = {}

    re_version = re.compile(r"^##\s+\[?v?([0-9]+\.[0-9]+\.[0-9]+[^\]]*)\]?(?:\s*-\s*([0-9]{4}-[0-9]{2}-[0-9]{2}))?")
    re_section = re.compile(r"^###\s+(.+)$")
    re_bullet = re.compile(r"^\s*[-*]\s+(.+)$")

    for raw_line in markdown_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        m_ver = re_version.match(line)
        if m_ver:
            ver_num = m_ver.group(1).strip()
            date_iso = (m_ver.group(2) or "").strip()
            current_ver = {
                "version": ver_num,
                "date_iso": date_iso,
                "date_br": format_date_br(date_iso) if date_iso else "",
                "sections": [],
            }
            versions.append(current_ver)
            current_sec = {}
            continue

        if not current_ver:
            continue

        m_sec = re_section.match(line)
        if m_sec:
            cat_raw = m_sec.group(1).strip().lower()
            current_sec = {"category": cat_raw, "items": []}
            current_ver["sections"].append(current_sec)
            continue

        m_item = re_bullet.match(raw_line)
        if m_item:
            item_text = _clean_md_inline(m_item.group(1))
            if not current_sec:
                current_sec = {"category": "added", "items": []}
                current_ver["sections"].append(current_sec)
            current_sec["items"].append(item_text)

    return versions


class WhatsNewDialog(ctk.CTkToplevel):
    """Modal moderno para visualizar as novidades e o histórico de versões do DailyNotes."""

    def __init__(self, parent, changelog_text: str = None):
        super().__init__(parent)
        self.title(f"Novidades - {APP_SHORT_NAME} v{config.APP_VERSION}")
        self.resizable(True, True)
        self.minsize(540, 420)
        self.transient(parent)
        self.grab_set()

        center_modal_on_parent(self, parent, 660, 540)

        raw_text = changelog_text if changelog_text is not None else read_changelog_text()
        self.entries = parse_changelog(raw_text)
        self._wrap_labels: List[ctk.CTkLabel] = []

        self._build_ui()
        self._render_entries()

        self.bind("<Escape>", lambda _e: self.destroy())

    def _build_ui(self):
        self.container = ctk.CTkFrame(
            self,
            corner_radius=12,
            fg_color=config.COLORS["card_dark"],
            border_width=1,
            border_color=config.COLORS["border_dark"],
        )
        self.container.pack(fill="both", expand=True, padx=16, pady=16)

        # Cabeçalho
        header = ctk.CTkFrame(self.container, fg_color="transparent")
        header.pack(fill="x", padx=16, pady=(16, 10))

        left_header = ctk.CTkFrame(header, fg_color="transparent")
        left_header.pack(side="left", fill="x", expand=True)

        lbl_badge = ctk.CTkLabel(
            left_header,
            text="✨ NOVIDADES & HISTÓRICO",
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color=config.COLORS["primary"],
            text_color="#FFFFFF",
            corner_radius=6,
            padx=10,
            pady=3,
        )
        lbl_badge.pack(anchor="w")

        lbl_sub = ctk.CTkLabel(
            left_header,
            text=f"Versão instalada: v{config.APP_VERSION}",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=config.COLORS["text_dark"],
            anchor="w",
        )
        lbl_sub.pack(anchor="w", pady=(6, 0))

        # Filtro de versão
        filter_frame = ctk.CTkFrame(header, fg_color="transparent")
        filter_frame.pack(side="right", anchor="ne")

        lbl_filter = ctk.CTkLabel(
            filter_frame,
            text="Filtrar versão:",
            font=ctk.CTkFont(size=11),
            text_color=config.COLORS["text_muted"],
        )
        lbl_filter.pack(anchor="e")

        options = ["Todas as versões"]
        for entry in self.entries:
            ver = entry["version"]
            label = f"v{ver} (Atual)" if ver == config.APP_VERSION else f"v{ver}"
            options.append(label)

        self.combo_version = ctk.CTkComboBox(
            filter_frame,
            values=options,
            width=165,
            height=30,
            corner_radius=6,
            command=lambda _v: self._render_entries(),
        )
        self.combo_version.set("Todas as versões")
        self.combo_version.pack(pady=(3, 0))

        # Área rolável com os cards de versões
        self.scroll = ctk.CTkScrollableFrame(
            self.container,
            corner_radius=10,
            fg_color=config.COLORS["sidebar"],
            border_width=1,
            border_color=config.COLORS["border_dark"],
            scrollbar_button_color=("#CBD5E1", "#334155"),
            scrollbar_button_hover_color=("#94A3B8", "#475569"),
        )
        self.scroll.pack(fill="both", expand=True, padx=16, pady=(0, 12))
        try:
            self.scroll._scrollbar.configure(width=8)
            self.scroll._parent_canvas.bind("<Configure>", self._on_scroll_resize, add="+")
        except Exception:
            pass

        # Rodapé
        footer = ctk.CTkFrame(self.container, fg_color="transparent")
        footer.pack(fill="x", padx=16, pady=(0, 14))

        self.btn_github = ctk.CTkButton(
            footer,
            text="🌐 Ver Releases no GitHub",
            height=34,
            width=180,
            corner_radius=8,
            font=ctk.CTkFont(size=12),
            fg_color=config.COLORS["card_dark_alt"],
            hover_color=config.COLORS["primary"],
            text_color=config.COLORS["button_text"],
            command=lambda: webbrowser.open(config.GITHUB_RELEASES_URL),
        )
        self.btn_github.pack(side="left")

        self.btn_close = ctk.CTkButton(
            footer,
            text="Fechar",
            height=34,
            width=110,
            corner_radius=8,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=config.COLORS["primary"],
            hover_color=config.COLORS["primary_hover"],
            text_color="#FFFFFF",
            command=self.destroy,
        )
        self.btn_close.pack(side="right")

    def _on_scroll_resize(self, event):
        if not self._wrap_labels:
            return
        try:
            scaling = float(self._get_widget_scaling()) or 1.0
        except Exception:
            scaling = 1.0
        usable = max(320, int((event.width / scaling) - 64))
        for lbl in self._wrap_labels:
            try:
                if lbl.winfo_exists() and abs(int(lbl.cget("wraplength") or 0) - usable) > 6:
                    lbl.configure(wraplength=usable)
            except Exception:
                pass

    def _render_entries(self):
        for w in self.scroll.winfo_children():
            w.destroy()
        self._wrap_labels.clear()

        selected = self.combo_version.get()
        filtered = self.entries
        if selected != "Todas as versões":
            target_ver = selected.replace(" (Atual)", "").lstrip("vV").strip()
            filtered = [e for e in self.entries if e["version"] == target_ver]

        if not filtered:
            lbl_empty = ctk.CTkLabel(
                self.scroll,
                text="Nenhuma nota de versão encontrada no histórico local (CHANGELOG.md).",
                font=ctk.CTkFont(size=13),
                text_color=config.COLORS["text_muted"],
            )
            lbl_empty.pack(pady=40)
            return

        for entry in filtered:
            ver = entry["version"]
            date_br = entry.get("date_br", "")
            is_current = (ver == config.APP_VERSION)

            card = ctk.CTkFrame(
                self.scroll,
                corner_radius=10,
                fg_color=config.COLORS["card_dark"],
                border_width=1,
                border_color=config.COLORS["primary"] if is_current else config.COLORS["border_dark"],
            )
            card.pack(fill="x", padx=8, pady=6)

            top_row = ctk.CTkFrame(card, fg_color="transparent")
            top_row.pack(fill="x", padx=14, pady=(12, 6))

            lbl_v = ctk.CTkLabel(
                top_row,
                text=f"🏷️ Versão {ver}",
                font=ctk.CTkFont(size=15, weight="bold"),
                text_color=config.COLORS["text_dark"],
            )
            lbl_v.pack(side="left")

            if is_current:
                lbl_curr = ctk.CTkLabel(
                    top_row,
                    text="ATUAL",
                    font=ctk.CTkFont(size=10, weight="bold"),
                    fg_color=config.COLORS["success"],
                    text_color="#FFFFFF",
                    corner_radius=6,
                    padx=8,
                    pady=2,
                )
                lbl_curr.pack(side="left", padx=(8, 0))

            if date_br:
                lbl_date = ctk.CTkLabel(
                    top_row,
                    text=f"📅 {date_br}",
                    font=ctk.CTkFont(size=11),
                    text_color=config.COLORS["text_muted"],
                )
                lbl_date.pack(side="right")

            for sec in entry.get("sections", []):
                cat_key = sec.get("category", "added")
                cat_title, color_key = _CATEGORY_META.get(cat_key, (cat_key.capitalize(), "primary"))

                lbl_cat = ctk.CTkLabel(
                    card,
                    text=cat_title,
                    font=ctk.CTkFont(size=12, weight="bold"),
                    text_color=config.COLORS.get(color_key, config.COLORS["primary"]),
                    anchor="w",
                )
                lbl_cat.pack(fill="x", padx=14, pady=(6, 2))

                for item_text in sec.get("items", []):
                    lbl_item = ctk.CTkLabel(
                        card,
                        text=f"•  {item_text}",
                        font=ctk.CTkFont(size=12),
                        text_color=config.COLORS["text_dark"],
                        wraplength=540,
                        justify="left",
                        anchor="w",
                    )
                    lbl_item.pack(fill="x", padx=(22, 14), pady=(1, 3))
                    self._wrap_labels.append(lbl_item)

            # Espaçamento inferior do card
            ctk.CTkFrame(card, height=6, fg_color="transparent").pack()
