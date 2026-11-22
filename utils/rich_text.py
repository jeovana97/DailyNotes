"""
Motor de Formatação Rica (Rich Text) para editores CTkTextbox (Tkinter tk.Text).
Suporta:
- Seleção de Fonte (família) e Tamanho (por trecho selecionado ou documento inteiro)
- Negrito (bold), Sublinhado (underline) e Riscado (overstrike) — combináveis entre si
- Digitação contínua com estilos ativos quando não há seleção
- Serialização e restauração em JSON (formatting_json), mantendo o texto puro intacto no SQLite
"""

import json
import tkinter as tk
import tkinter.font as tkfont
from typing import Optional, Callable, Dict, List, Tuple, Any
import customtkinter as ctk

import config


AVAILABLE_FONTS: List[str] = [
    "Segoe UI",
    "Arial",
    "Calibri",
    "Consolas",
    "Courier New",
    "Georgia",
    "Tahoma",
    "Times New Roman",
    "Verdana",
]

AVAILABLE_FONT_SIZES: List[str] = [
    "10", "11", "12", "13", "14", "15", "16", "18", "20", "22", "24", "28", "32",
]

DEFAULT_FONT_FAMILY = "Segoe UI"
DEFAULT_FONT_SIZE = 15

TAG_BOLD = "rt_bold"
TAG_UNDERLINE = "rt_underline"
TAG_OVERSTRIKE = "rt_overstrike"
TAG_FAMILY_PREFIX = "rt_family::"
TAG_SIZE_PREFIX = "rt_size::"
TAG_COMP_PREFIX = "rt_comp::"


class RichTextController:
    """
    Controlador de formatação rica acoplado a um CTkTextbox.
    Permite combinar Fonte + Tamanho + Negrito + Sublinhado + Riscado no mesmo trecho
    sem conflitar com destaque de sintaxe XML/SQL ou destaque de busca F3.
    """

    def __init__(
        self,
        ctk_textbox: ctk.CTkTextbox,
        on_change_callback: Optional[Callable[[], None]] = None,
        default_family: str = DEFAULT_FONT_FAMILY,
        default_size: int = DEFAULT_FONT_SIZE,
    ):
        self.ctk_textbox = ctk_textbox
        self.tb = ctk_textbox._textbox
        self.on_change_callback = on_change_callback

        self.default_family = default_family
        self.default_size = default_size
        self.base_family = default_family
        self.base_size = default_size

        # Estados de digitação quando não há texto selecionado
        self.typing_bold = False
        self.typing_underline = False
        self.typing_overstrike = False

        # Referências opcionais aos widgets da barra de ferramentas para sincronização visual
        self._combo_font: Optional[ctk.CTkComboBox] = None
        self._combo_size: Optional[ctk.CTkComboBox] = None
        self._btn_bold: Optional[ctk.CTkButton] = None
        self._btn_underline: Optional[ctk.CTkButton] = None
        self._btn_overstrike: Optional[ctk.CTkButton] = None

        self._font_cache: Dict[Tuple[str, int, bool], tkfont.Font] = {}
        self._pre_key_index: Optional[str] = None
        self._suppress_sync = False

        self._setup_static_tags()
        try:
            # Preserva a seleção visual ('sel') mesmo ao clicar em comboboxes/botões da barra
            self.tb.configure(exportselection=False)
        except Exception:
            pass
        self._bind_events()

    def attach_toolbar_widgets(
        self,
        combo_font: Optional[ctk.CTkComboBox] = None,
        combo_size: Optional[ctk.CTkComboBox] = None,
        btn_bold: Optional[ctk.CTkButton] = None,
        btn_underline: Optional[ctk.CTkButton] = None,
        btn_overstrike: Optional[ctk.CTkButton] = None,
    ):
        """Vincula os controles visuais da barra de ferramentas para refletir o estado ativo."""
        self._combo_font = combo_font
        self._combo_size = combo_size
        self._btn_bold = btn_bold
        self._btn_underline = btn_underline
        self._btn_overstrike = btn_overstrike
        self.sync_toolbar_state()

    def _setup_static_tags(self):
        try:
            self.tb.tag_configure(TAG_UNDERLINE, underline=True)
            self.tb.tag_configure(TAG_OVERSTRIKE, overstrike=True)
        except Exception:
            pass

    def _bind_events(self):
        self.tb.bind("<KeyPress>", self._on_key_press, add="+")
        self.tb.bind("<KeyRelease>", self._on_key_release, add="+")
        self.tb.bind("<ButtonRelease-1>", lambda _e: self.sync_toolbar_state(), add="+")

        self.tb.bind("<Control-b>", lambda _e: (self.toggle_bold(), "break")[1])
        self.tb.bind("<Control-B>", lambda _e: (self.toggle_bold(), "break")[1])
        self.tb.bind("<Control-u>", lambda _e: (self.toggle_underline(), "break")[1])
        self.tb.bind("<Control-U>", lambda _e: (self.toggle_underline(), "break")[1])

    def _get_tk_font(self, family: str, size: int, is_bold: bool) -> tkfont.Font:
        key = (family, int(size), bool(is_bold))
        if key not in self._font_cache:
            self._font_cache[key] = tkfont.Font(
                root=self.tb,
                family=family,
                size=int(size),
                weight="bold" if is_bold else "normal",
            )
        return self._font_cache[key]

    def _apply_base_font(self):
        try:
            self.ctk_textbox.configure(
                font=ctk.CTkFont(family=self.base_family, size=int(self.base_size))
            )
        except Exception:
            pass

    def _is_editable(self) -> bool:
        try:
            return str(self.tb.cget("state")) != "disabled"
        except Exception:
            return True

    def _get_selection(self) -> Optional[Tuple[str, str]]:
        try:
            ranges = self.tb.tag_ranges("sel")
            if ranges and len(ranges) >= 2:
                return (str(ranges[0]), str(ranges[1]))
        except Exception:
            pass
        return None

    def _range_fully_has_tag(self, tag_name: str, start: str, end: str) -> bool:
        """Verifica se TODOS os caracteres no intervalo [start, end) possuem tag_name."""
        cur = self.tb.index(start)
        end_idx = self.tb.index(end)
        if self.tb.compare(cur, ">=", end_idx):
            return False
        while self.tb.compare(cur, "<", end_idx):
            if tag_name not in self.tb.tag_names(cur):
                return False
            cur = self.tb.index(f"{cur} + 1c")
        return True

    def _clear_prefix_tags_in_range(self, prefix: str, start: str, end: str):
        for tag in list(self.tb.tag_names()):
            if tag.startswith(prefix):
                self.tb.tag_remove(tag, start, end)

    def _recompute_composite_fonts(self, start: str, end: str):
        """
        Recalcula as tags compostas de fonte (family + size + bold) no intervalo [start, end)
        agrupando caracteres contíguos com a mesma combinação em runs eficientes.
        """
        s_idx = self.tb.index(start)
        e_idx = self.tb.index(end)
        if self.tb.compare(s_idx, ">=", e_idx):
            return

        # Remove tags compostas antigas neste intervalo
        self._clear_prefix_tags_in_range(TAG_COMP_PREFIX, s_idx, e_idx)

        # Verifica se há alguma tag de fonte/tamanho/negrito no texto antes de iterar
        all_tags = self.tb.tag_names()
        has_any_font_tag = any(
            t == TAG_BOLD or t.startswith(TAG_FAMILY_PREFIX) or t.startswith(TAG_SIZE_PREFIX)
            for t in all_tags
        )
        if not has_any_font_tag:
            return

        cur = s_idx
        run_start = cur
        prev_key: Optional[Tuple[str, int, bool]] = None

        def _flush_run(r_start: str, r_end: str, f_key: Optional[Tuple[str, int, bool]]):
            if f_key is None:
                return
            fam, sz, bld = f_key
            # Se coincide exatamente com a fonte base sem negrito, não precisa de tag composta
            if fam == self.base_family and sz == self.base_size and not bld:
                return
            comp_tag = f"{TAG_COMP_PREFIX}{fam}::{sz}::{1 if bld else 0}"
            self.tb.tag_configure(comp_tag, font=self._get_tk_font(fam, sz, bld))
            self.tb.tag_add(comp_tag, r_start, r_end)
            try:
                self.tb.tag_raise(comp_tag)
            except Exception:
                pass

        while self.tb.compare(cur, "<", e_idx):
            tags_here = self.tb.tag_names(cur)
            fam = self.base_family
            sz = self.base_size
            bld = False
            for t in tags_here:
                if t == TAG_BOLD:
                    bld = True
                elif t.startswith(TAG_FAMILY_PREFIX):
                    fam = t[len(TAG_FAMILY_PREFIX):]
                elif t.startswith(TAG_SIZE_PREFIX):
                    try:
                        sz = int(t[len(TAG_SIZE_PREFIX):])
                    except ValueError:
                        pass
            key = (fam, sz, bld)
            if prev_key is None:
                prev_key = key
                run_start = cur
            elif key != prev_key:
                _flush_run(run_start, cur, prev_key)
                prev_key = key
                run_start = cur
            cur = self.tb.index(f"{cur} + 1c")

        _flush_run(run_start, e_idx, prev_key)

        # Garante sublinhado e riscado acima de sintaxe, e busca/seleção sempre no topo
        for tag in (TAG_UNDERLINE, TAG_OVERSTRIKE, "search_highlight", "search_highlight_current", "sel"):
            try:
                self.tb.tag_raise(tag)
            except Exception:
                pass

    # =========================================================================
    # Ações da Barra de Formatação
    # =========================================================================

    def toggle_bold(self):
        self._toggle_flag(TAG_BOLD, "typing_bold", recompute_font=True)

    def toggle_underline(self):
        self._toggle_flag(TAG_UNDERLINE, "typing_underline", recompute_font=False)

    def toggle_overstrike(self):
        self._toggle_flag(TAG_OVERSTRIKE, "typing_overstrike", recompute_font=False)

    def _toggle_flag(self, tag_name: str, typing_attr: str, recompute_font: bool):
        if not self._is_editable():
            return

        sel = self._get_selection()
        if sel:
            start, end = sel
            already_on = self._range_fully_has_tag(tag_name, start, end)
            if already_on:
                self.tb.tag_remove(tag_name, start, end)
            else:
                self.tb.tag_add(tag_name, start, end)
            if recompute_font:
                self._recompute_composite_fonts(start, end)
            setattr(self, typing_attr, not already_on)
            self._notify_changed()
        else:
            setattr(self, typing_attr, not getattr(self, typing_attr))

        self._update_button_highlights()
        try:
            self.ctk_textbox.focus_set()
        except Exception:
            pass

    def apply_font_family(self, family: str):
        if not self._is_editable() or not family:
            return
        sel = self._get_selection()
        if sel:
            start, end = sel
            self._clear_prefix_tags_in_range(TAG_FAMILY_PREFIX, start, end)
            if family != self.base_family:
                self.tb.tag_add(f"{TAG_FAMILY_PREFIX}{family}", start, end)
            self._recompute_composite_fonts(start, end)
        else:
            self.base_family = family
            self._apply_base_font()
            self._recompute_composite_fonts("1.0", "end-1c")

        self._notify_changed()
        self.sync_toolbar_state()
        try:
            self.ctk_textbox.focus_set()
        except Exception:
            pass

    def apply_font_size(self, size_val: Any):
        if not self._is_editable():
            return
        try:
            size = max(8, min(72, int(str(size_val).strip())))
        except Exception:
            return

        sel = self._get_selection()
        if sel:
            start, end = sel
            self._clear_prefix_tags_in_range(TAG_SIZE_PREFIX, start, end)
            if size != self.base_size:
                self.tb.tag_add(f"{TAG_SIZE_PREFIX}{size}", start, end)
            self._recompute_composite_fonts(start, end)
        else:
            self.base_size = size
            self._apply_base_font()
            self._recompute_composite_fonts("1.0", "end-1c")

        self._notify_changed()
        self.sync_toolbar_state()
        try:
            self.ctk_textbox.focus_set()
        except Exception:
            pass

    # =========================================================================
    # Digitação Contínua & Sincronização Visual
    # =========================================================================

    def _on_key_press(self, event):
        if not self._is_editable():
            return
        if event.char and (event.char.isprintable() or event.char in ("\r", "\n", "\t")):
            try:
                self._pre_key_index = self.tb.index("insert")
            except Exception:
                self._pre_key_index = None
        else:
            self._pre_key_index = None

    def _on_key_release(self, event):
        if not self._is_editable():
            return
        if self._pre_key_index is not None:
            pre = self._pre_key_index
            self._pre_key_index = None
            try:
                post = self.tb.index("insert")
                if self.tb.compare(pre, "<", post):
                    if self.typing_bold:
                        self.tb.tag_add(TAG_BOLD, pre, post)
                    else:
                        self.tb.tag_remove(TAG_BOLD, pre, post)

                    if self.typing_underline:
                        self.tb.tag_add(TAG_UNDERLINE, pre, post)
                    else:
                        self.tb.tag_remove(TAG_UNDERLINE, pre, post)

                    if self.typing_overstrike:
                        self.tb.tag_add(TAG_OVERSTRIKE, pre, post)
                    else:
                        self.tb.tag_remove(TAG_OVERSTRIKE, pre, post)

                    # Sempre recalcula o intervalo digitado (1 char) para também limpar
                    # tags compostas herdadas quando o usuário desativa o negrito
                    self._recompute_composite_fonts(pre, post)
            except Exception:
                pass
        elif event.keysym in ("Left", "Right", "Up", "Down", "Home", "End", "Prior", "Next"):
            self.sync_toolbar_state()

    def sync_toolbar_state(self):
        """Atualiza os seletores de fonte/tamanho e o destaque de B/U/S conforme a posição atual."""
        if self._suppress_sync:
            return
        try:
            sel = self._get_selection()
            probe_idx = sel[0] if sel else self.tb.index("insert - 1c")
            tags = self.tb.tag_names(probe_idx) if self.tb.compare("1.0", "<", "end-1c") else ()

            fam = self.base_family
            sz = self.base_size
            is_bold = TAG_BOLD in tags
            is_under = TAG_UNDERLINE in tags
            is_strike = TAG_OVERSTRIKE in tags

            for t in tags:
                if t.startswith(TAG_FAMILY_PREFIX):
                    fam = t[len(TAG_FAMILY_PREFIX):]
                elif t.startswith(TAG_SIZE_PREFIX):
                    try:
                        sz = int(t[len(TAG_SIZE_PREFIX):])
                    except ValueError:
                        pass

            self.typing_bold = is_bold
            self.typing_underline = is_under
            self.typing_overstrike = is_strike

            if self._combo_font is not None and self._combo_font.winfo_exists():
                if self._combo_font.get() != fam:
                    self._combo_font.set(fam)
            if self._combo_size is not None and self._combo_size.winfo_exists():
                if self._combo_size.get() != str(sz):
                    self._combo_size.set(str(sz))

            self._update_button_highlights()
        except Exception:
            pass

    def _update_button_highlights(self):
        mapping = [
            (self._btn_bold, self.typing_bold),
            (self._btn_underline, self.typing_underline),
            (self._btn_overstrike, self.typing_overstrike),
        ]
        for btn, active in mapping:
            if btn is None:
                continue
            try:
                if not btn.winfo_exists():
                    continue
                if active:
                    btn.configure(
                        fg_color=config.COLORS["primary"],
                        text_color="#FFFFFF",
                    )
                else:
                    btn.configure(
                        fg_color=config.COLORS["card_dark"],
                        text_color=config.COLORS["button_text"],
                    )
            except Exception:
                pass

    def _notify_changed(self):
        if self.on_change_callback:
            try:
                self.on_change_callback()
            except Exception:
                pass

    # =========================================================================
    # Serialização / Carregamento / Reset
    # =========================================================================

    def reset(self):
        """Limpa todas as tags de formatação rica e restaura fonte/tamanho padrão."""
        self.base_family = self.default_family
        self.base_size = self.default_size
        self.typing_bold = False
        self.typing_underline = False
        self.typing_overstrike = False

        try:
            for tag in list(self.tb.tag_names()):
                if tag in (TAG_BOLD, TAG_UNDERLINE, TAG_OVERSTRIKE) or tag.startswith(
                    (TAG_FAMILY_PREFIX, TAG_SIZE_PREFIX, TAG_COMP_PREFIX)
                ):
                    self.tb.tag_remove(tag, "1.0", "end")
        except Exception:
            pass

        self._apply_base_font()
        self.sync_toolbar_state()

    def serialize(self) -> str:
        """
        Exporta a formatação atual (fonte base, tamanho base e intervalos formatados)
        como string JSON compacta. Retorna '' se não houver formatação customizada.
        """
        spans: List[Dict[str, str]] = []
        try:
            for tag in self.tb.tag_names():
                logical_name: Optional[str] = None
                if tag == TAG_BOLD:
                    logical_name = "bold"
                elif tag == TAG_UNDERLINE:
                    logical_name = "underline"
                elif tag == TAG_OVERSTRIKE:
                    logical_name = "overstrike"
                elif tag.startswith(TAG_FAMILY_PREFIX):
                    logical_name = f"family:{tag[len(TAG_FAMILY_PREFIX):]}"
                elif tag.startswith(TAG_SIZE_PREFIX):
                    logical_name = f"size:{tag[len(TAG_SIZE_PREFIX):]}"

                if not logical_name:
                    continue

                ranges = self.tb.tag_ranges(tag)
                for i in range(0, len(ranges), 2):
                    s = str(ranges[i])
                    e = str(ranges[i + 1])
                    if self.tb.compare(s, "<", e):
                        spans.append({"tag": logical_name, "start": s, "end": e})
        except Exception:
            pass

        if (
            self.base_family == self.default_family
            and self.base_size == self.default_size
            and not spans
        ):
            return ""

        payload = {
            "font_family": self.base_family,
            "font_size": int(self.base_size),
            "spans": spans,
        }
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))

    def load(self, formatting_json: Optional[str]):
        """Restaura a formatação rica salva em JSON sobre o texto já carregado no editor."""
        self._suppress_sync = True
        try:
            self.reset()
            if not formatting_json or not str(formatting_json).strip():
                return

            data = json.loads(formatting_json)
            if not isinstance(data, dict):
                return

            fam = data.get("font_family")
            if isinstance(fam, str) and fam.strip():
                self.base_family = fam.strip()

            sz = data.get("font_size")
            if sz is not None:
                try:
                    self.base_size = max(8, min(72, int(sz)))
                except Exception:
                    pass

            self._apply_base_font()

            for sp in data.get("spans", []):
                if not isinstance(sp, dict):
                    continue
                t_logical = sp.get("tag", "")
                s = sp.get("start")
                e = sp.get("end")
                if not t_logical or not s or not e:
                    continue
                if t_logical == "bold":
                    self.tb.tag_add(TAG_BOLD, s, e)
                elif t_logical == "underline":
                    self.tb.tag_add(TAG_UNDERLINE, s, e)
                elif t_logical == "overstrike":
                    self.tb.tag_add(TAG_OVERSTRIKE, s, e)
                elif t_logical.startswith("family:"):
                    f_name = t_logical.split(":", 1)[1].strip()
                    if f_name:
                        self.tb.tag_add(f"{TAG_FAMILY_PREFIX}{f_name}", s, e)
                elif t_logical.startswith("size:"):
                    sz_str = t_logical.split(":", 1)[1].strip()
                    if sz_str.isdigit():
                        self.tb.tag_add(f"{TAG_SIZE_PREFIX}{sz_str}", s, e)

            self._recompute_composite_fonts("1.0", "end-1c")
        except Exception:
            pass
        finally:
            self._suppress_sync = False
            self.sync_toolbar_state()


def apply_formatting_to_textbox(ctk_textbox: ctk.CTkTextbox, formatting_json: Optional[str]) -> RichTextController:
    """Utilitário rápido para aplicar formatação rica salva em um CTkTextbox de leitura/preview."""
    ctrl = RichTextController(ctk_textbox)
    ctrl.load(formatting_json)
    return ctrl
