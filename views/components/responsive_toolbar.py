"""
Barra de Ferramentas com suporte a Overflow / Transbordamento Dinâmico ('>>').
Permite agrupar botões compactos (símbolos e ícones). Se a janela estiver estreita
e nem todos os botões couberem na tela, os botões excedentes são ocultados e acessíveis
através de um menu popup acionado pelo botão '»' ou '>>'.
"""

import tkinter as tk
from typing import List, Dict, Any, Optional, Callable
import customtkinter as ctk

import config


class WidgetTooltip:
    """
    Tooltip flutuante leve para widgets CustomTkinter/Tkinter.
    Exibe o nome/descrição do botão ao passar o mouse sobre o ícone.
    """

    def __init__(self, widget, text: str, delay_ms: int = 320):
        self.widget = widget
        self.text = text
        self.delay_ms = delay_ms
        self._after_id: Optional[str] = None
        self._tip_window: Optional[tk.Toplevel] = None

        self.widget.bind("<Enter>", self._on_enter, add="+")
        self.widget.bind("<Leave>", self._on_leave, add="+")
        self.widget.bind("<ButtonPress>", self._on_leave, add="+")
        self.widget.bind("<Unmap>", self._on_leave, add="+")
        self.widget.bind("<Destroy>", self._on_leave, add="+")

    def _on_enter(self, event=None):
        self._cancel_timer()
        if not self.text:
            return
        try:
            if not self.widget.winfo_exists():
                return
            self._after_id = self.widget.after(self.delay_ms, self._show_tooltip)
        except Exception:
            pass

    def _on_leave(self, event=None):
        self._cancel_timer()
        self._hide_tooltip()

    def _cancel_timer(self):
        if self._after_id is not None:
            try:
                self.widget.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None

    def _show_tooltip(self):
        self._after_id = None
        if self._tip_window is not None:
            return
        try:
            if not self.widget.winfo_exists() or not self.widget.winfo_ismapped():
                return
        except Exception:
            return

        mode = ctk.get_appearance_mode()
        is_dark = (mode == "Dark")
        bg_color = "#0F172A" if is_dark else "#1E293B"
        fg_color = "#F8FAFC"
        border_color = "#475569" if is_dark else "#334155"

        tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        try:
            tw.wm_attributes("-topmost", True)
        except Exception:
            pass

        frame = tk.Frame(
            tw,
            bg=bg_color,
            highlightbackground=border_color,
            highlightthickness=1,
            bd=0,
        )
        frame.pack()

        lbl = tk.Label(
            frame,
            text=self.text,
            bg=bg_color,
            fg=fg_color,
            font=("Segoe UI", 9, "bold"),
            padx=8,
            pady=4,
            justify="left",
        )
        lbl.pack()

        tw.update_idletasks()
        tip_w = tw.winfo_reqwidth()
        tip_h = tw.winfo_reqheight()

        x = self.widget.winfo_rootx()
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4

        sw = self.widget.winfo_screenwidth()
        sh = self.widget.winfo_screenheight()
        if x + tip_w > sw - 8:
            x = max(8, sw - tip_w - 8)
        if y + tip_h > sh - 8:
            y = max(8, self.widget.winfo_rooty() - tip_h - 4)

        tw.wm_geometry(f"+{x}+{y}")
        self._tip_window = tw

    def _hide_tooltip(self):
        if self._tip_window is not None:
            try:
                self._tip_window.destroy()
            except Exception:
                pass
            self._tip_window = None


class ResponsiveToolbar(ctk.CTkFrame):
    """
    Barra de botões responsiva que monitora a largura disponível (<Configure>)
    e move os botões que não couberem para um menu de transbordamento '»'.
    """

    def __init__(
        self,
        master,
        height: int = 36,
        fg_color: Optional[str] = None,
        corner_radius: int = 8,
        item_spacing: int = 4,
        overflow_button_width: int = 32,
        **kwargs,
    ):
        super().__init__(
            master,
            height=height,
            fg_color=fg_color or "transparent",
            corner_radius=corner_radius,
            **kwargs,
        )
        self.item_spacing = item_spacing
        self.overflow_button_width = overflow_button_width
        self.items: List[Dict[str, Any]] = []
        self._resize_job = None
        self._last_width = 0

        # Botão de overflow '»'
        self.btn_overflow = ctk.CTkButton(
            self,
            text="»",
            width=self.overflow_button_width,
            height=height - 6,
            corner_radius=6,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color=config.COLORS["card_dark"],
            hover_color=config.COLORS["primary"],
            text_color=config.COLORS["button_text"],
            command=self._show_overflow_menu,
        )
        self._overflow_tooltip = WidgetTooltip(self.btn_overflow, "Mais opções (»)")

        self.bind("<Configure>", self._on_configure)

    def add_button(
        self,
        key: str,
        symbol_text: str,
        full_label: str,
        command: Optional[Callable[[], None]] = None,
        width: int = 34,
        height: int = 28,
        fg_color: Optional[str] = None,
        hover_color: Optional[str] = None,
        text_color: Optional[str] = None,
        font_size: int = 12,
        font_weight: str = "bold",
    ) -> ctk.CTkButton:
        """
        Adiciona um botão de ação.
        - symbol_text: Ícone ou texto compacto (ex: '💾', '↩️', '🔠', 'XML')
        - full_label: Nome descritivo completo para o menu de overflow e tooltip
        """
        btn = ctk.CTkButton(
            self,
            text=symbol_text,
            width=width,
            height=height,
            corner_radius=6,
            font=ctk.CTkFont(size=font_size, weight=font_weight),
            fg_color=fg_color or config.COLORS["card_dark"],
            hover_color=hover_color or config.COLORS["primary"],
            text_color=text_color or config.COLORS["button_text"],
            command=command,
        )
        tooltip = WidgetTooltip(btn, full_label)

        self.items.append({
            "type": "button",
            "key": key,
            "widget": btn,
            "tooltip": tooltip,
            "symbol_text": symbol_text,
            "full_label": full_label,
            "command": command,
            "width": width,
            "is_visible": False,
        })
        self._schedule_reflow()
        return btn

    def add_separator(self, key: str = "sep", width: int = 12):
        """Adiciona um separador vertical discreto."""
        lbl_sep = ctk.CTkLabel(
            self,
            text="|",
            font=ctk.CTkFont(size=13),
            text_color=config.COLORS["border_dark"],
            width=width,
        )
        self.items.append({
            "type": "separator",
            "key": key,
            "widget": lbl_sep,
            "width": width,
            "is_visible": False,
        })
        self._schedule_reflow()

    def _on_configure(self, event):
        if abs(event.width - self._last_width) >= 10:
            self._last_width = event.width
            self._schedule_reflow()

    def _schedule_reflow(self):
        if self._resize_job is not None:
            try:
                self.after_cancel(self._resize_job)
            except Exception:
                pass
        self._resize_job = self.after(35, self.reflow)

    def reflow(self):
        """Recalcula quais itens cabem na largura atual e posiciona o botão '»'."""
        self._resize_job = None
        try:
            if not self.winfo_exists():
                return
        except Exception:
            return

        avail_width = self.winfo_width()
        if avail_width <= 20:
            # Janela ainda sendo inicializada / desenhada
            avail_width = 800

        # Margem de segurança interna para paddings e controles à direita
        usable_width = avail_width - 8
        total_needed = sum(item["width"] + self.item_spacing for item in self.items)

        fits_all = (total_needed <= usable_width)
        limit_width = usable_width if fits_all else (usable_width - self.overflow_button_width - self.item_spacing)

        current_x = 0
        overflow_needed = False

        for item in self.items:
            item_w = item["width"] + self.item_spacing
            if fits_all or (current_x + item_w <= limit_width):
                if not item["is_visible"]:
                    item["widget"].pack(side="left", padx=(0, self.item_spacing), pady=3)
                    item["is_visible"] = True
                current_x += item_w
            else:
                if item["is_visible"]:
                    item["widget"].pack_forget()
                    item["is_visible"] = False
                if item["type"] == "button":
                    overflow_needed = True

        if overflow_needed:
            if not self.btn_overflow.winfo_ismapped():
                self.btn_overflow.pack(side="left", padx=(2, 0), pady=3)
        else:
            if self.btn_overflow.winfo_ismapped():
                self.btn_overflow.pack_forget()

    def _show_overflow_menu(self):
        """Abre o menu dropdown com todas as ações que não couberam na barra visível."""
        hidden_buttons = [
            it for it in self.items
            if it["type"] == "button" and not it["is_visible"]
        ]
        if not hidden_buttons:
            return

        mode = ctk.get_appearance_mode()
        is_dark = (mode == "Dark")
        menu_bg = config.COLORS["card_dark"][1 if is_dark else 0]
        menu_fg = config.COLORS["text_dark"][1 if is_dark else 0]
        active_bg = config.COLORS["primary"][1 if is_dark else 0]

        menu = tk.Menu(
            self,
            tearoff=0,
            bg=menu_bg,
            fg=menu_fg,
            activebackground=active_bg,
            activeforeground="#FFFFFF",
            font=("Segoe UI", 10),
            relief="flat",
            bd=1,
        )

        for btn_info in hidden_buttons:
            cmd = btn_info.get("command")
            label = btn_info.get("full_label") or btn_info.get("symbol_text")
            menu.add_command(
                label=f"{label}",
                command=cmd,
            )

        x = self.btn_overflow.winfo_rootx()
        y = self.btn_overflow.winfo_rooty() + self.btn_overflow.winfo_height() + 2
        try:
            menu.tk_popup(x, y)
        finally:
            menu.grab_release()

