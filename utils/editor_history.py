"""
Gerenciador Unificado de Histórico (Desfazer / Refazer - Ctrl+Z / Ctrl+Y) para editores CTkTextbox.
Diferente da pilha nativa do Tkinter (que só rastreia texto puro), este gerenciador captura
snapshots completos contendo:
- Conteúdo de texto
- Formatação rica completa (Fonte, Tamanho, Negrito, Itálico, Sublinhado, Riscado)
- Coloração de sintaxe XML/SQL (e limpeza de cores)
- Posição do cursor e seleção ativa

Assim, Ctrl+Z e Ctrl+Y desfazem e refazem de forma consistente tanto digitação/colagem/recorte
quanto qualquer botão da barra de ações (Fonte, Tamanho, B, I, U, S, MAIÚSCULO, minúsculo,
XML, SQL e Limpar Cores).
"""

from dataclasses import dataclass
import tkinter as tk
from typing import Callable, List, Optional, Tuple
import customtkinter as ctk


@dataclass(frozen=True)
class EditorSnapshot:
    text: str
    formatting_json: str
    syntax_spans: Tuple[Tuple[str, str, str], ...]
    cursor: str
    selection: Optional[Tuple[str, str]]

    def content_key(self) -> Tuple[str, str, Tuple[Tuple[str, str, str], ...]]:
        return (self.text, self.formatting_json, self.syntax_spans)


class EditorHistoryManager:
    """Pilha unificada de Undo/Redo acoplada a um CTkTextbox."""

    BOUNDARY_KEYSYMS = frozenset({
        "space", "Return", "KP_Enter", "Tab",
        "period", "comma", "semicolon", "colon", "exclam", "question",
    })
    DELETE_KEYSYMS = frozenset({"BackSpace", "Delete"})
    NAV_AND_MOD_KEYSYMS = frozenset({
        "Left", "Right", "Up", "Down", "Home", "End", "Prior", "Next",
        "Shift_L", "Shift_R", "Control_L", "Control_R", "Alt_L", "Alt_R",
        "Caps_Lock", "Num_Lock", "Scroll_Lock", "Escape", "Insert",
        "F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8", "F9", "F10", "F11", "F12",
        "Win_L", "Win_R", "Super_L", "Super_R", "Menu",
    })

    def __init__(
        self,
        ctk_textbox: ctk.CTkTextbox,
        on_change_callback: Optional[Callable[[], None]] = None,
        max_states: int = 150,
        typing_debounce_ms: int = 600,
    ):
        self.ctk_textbox = ctk_textbox
        self.tb = ctk_textbox._textbox
        self.on_change_callback = on_change_callback
        self.max_states = max_states
        self.typing_debounce_ms = typing_debounce_ms

        self._undo_stack: List[EditorSnapshot] = []
        self._redo_stack: List[EditorSnapshot] = []
        self._current_state: Optional[EditorSnapshot] = None

        self._restoring = False
        self._debounce_job: Optional[str] = None
        self._last_edit_kind: Optional[str] = None
        self._had_selection_on_press = False

        self._bind_events()
        self.reset()

    def _is_editable(self) -> bool:
        try:
            return str(self.tb.cget("state")) != "disabled"
        except Exception:
            return True

    def _get_rich_text(self):
        return getattr(self.ctk_textbox, "_rich_text", None)

    def _bind_events(self):
        self.tb.bind("<KeyPress>", self._on_key_press, add="+")
        self.tb.bind("<KeyRelease>", self._on_key_release, add="+")
        self.tb.bind("<<Cut>>", self._on_cut_event, add="+")

    def _cancel_debounce(self):
        if self._debounce_job is not None:
            try:
                self.tb.after_cancel(self._debounce_job)
            except Exception:
                pass
            self._debounce_job = None

    def _schedule_debounce(self):
        self._cancel_debounce()
        try:
            if self.tb.winfo_exists():
                self._debounce_job = self.tb.after(
                    self.typing_debounce_ms, self._on_debounce_timeout
                )
        except Exception:
            self._debounce_job = None

    def _on_debounce_timeout(self):
        self._debounce_job = None
        self.record_snapshot()

    def capture_snapshot(self) -> EditorSnapshot:
        """Captura o estado completo atual do editor."""
        from utils.syntax_highlighter import ALL_SYNTAX_TAGS

        try:
            text = self.tb.get("1.0", "end-1c")
        except Exception:
            text = ""

        rich_text = self._get_rich_text()
        try:
            fmt_json = rich_text.serialize() if rich_text is not None else ""
        except Exception:
            fmt_json = ""

        syntax_list: List[Tuple[str, str, str]] = []
        try:
            for tag_name in ALL_SYNTAX_TAGS:
                ranges = self.tb.tag_ranges(tag_name)
                for i in range(0, len(ranges), 2):
                    s = str(ranges[i])
                    e = str(ranges[i + 1])
                    if self.tb.compare(s, "<", e):
                        syntax_list.append((tag_name, s, e))
        except Exception:
            pass

        try:
            cursor = str(self.tb.index("insert"))
        except Exception:
            cursor = "1.0"

        selection: Optional[Tuple[str, str]] = None
        try:
            sel = self.tb.tag_ranges("sel")
            if sel and len(sel) >= 2:
                selection = (str(sel[0]), str(sel[1]))
        except Exception:
            pass

        return EditorSnapshot(
            text=text,
            formatting_json=fmt_json,
            syntax_spans=tuple(syntax_list),
            cursor=cursor,
            selection=selection,
        )

    def reset(self):
        """Define o estado atual do editor como marco inicial limpo (ex.: ao abrir nota)."""
        self._cancel_debounce()
        self._undo_stack.clear()
        self._redo_stack.clear()
        self._last_edit_kind = None
        self._current_state = self.capture_snapshot()
        try:
            self.tb.edit_reset()
        except Exception:
            pass

    def _push_undo(self, snap: EditorSnapshot):
        self._undo_stack.append(snap)
        if len(self._undo_stack) > self.max_states:
            self._undo_stack.pop(0)

    def commit_pending(self):
        """
        Fecha qualquer edição de digitação pendente como um checkpoint separado.
        Deve ser chamado ANTES de executar ações atômicas (botões de fonte, tamanho,
        negrito, itálico, sublinhado, riscado, XML, SQL, maiúsculo/minúsculo, colar, etc.).
        """
        if self._restoring or not self._is_editable():
            return
        self._cancel_debounce()
        live = self.capture_snapshot()
        if self._current_state is None:
            self._current_state = live
            return
        if live.content_key() != self._current_state.content_key():
            self._push_undo(self._current_state)
            self._current_state = live
            self._redo_stack.clear()

    def record_snapshot(self):
        """
        Registra o estado atual na pilha caso tenha havido alteração em relação
        ao último estado salvo. Deve ser chamado APÓS ações atômicas ou pausas de digitação.
        """
        if self._restoring or not self._is_editable():
            return
        self._cancel_debounce()
        live = self.capture_snapshot()
        if self._current_state is None:
            self._current_state = live
            return
        if live.content_key() != self._current_state.content_key():
            self._push_undo(self._current_state)
            self._current_state = live
            self._redo_stack.clear()

    def _on_key_press(self, event):
        if self._restoring or not self._is_editable():
            return
        # Ignora atalhos com Ctrl/Alt (tratados por seus próprios handlers)
        if event.state & 0x4:
            return
        keysym = getattr(event, "keysym", "")
        if keysym in self.NAV_AND_MOD_KEYSYMS:
            return

        has_sel = False
        try:
            has_sel = bool(self.tb.tag_ranges("sel"))
        except Exception:
            pass
        self._had_selection_on_press = has_sel

        if keysym in self.DELETE_KEYSYMS:
            if has_sel or self._last_edit_kind == "insert":
                self.commit_pending()
            self._last_edit_kind = "delete"
        elif getattr(event, "char", "") and (
            event.char.isprintable() or keysym in ("Return", "KP_Enter", "Tab")
        ):
            if has_sel or self._last_edit_kind == "delete":
                self.commit_pending()
            self._last_edit_kind = "insert"

    def _on_key_release(self, event):
        if self._restoring or not self._is_editable():
            return
        if event.state & 0x4:
            return
        keysym = getattr(event, "keysym", "")
        if keysym in self.NAV_AND_MOD_KEYSYMS:
            return

        is_delete = keysym in self.DELETE_KEYSYMS
        is_boundary = keysym in self.BOUNDARY_KEYSYMS
        is_char = bool(getattr(event, "char", "")) and (
            event.char.isprintable() or is_boundary
        )

        if not (is_delete or is_char or is_boundary):
            return

        # Se o usuário começou uma nova edição após ter dado Undo, invalida o Redo
        if self._redo_stack and self._current_state is not None:
            live = self.capture_snapshot()
            if live.content_key() != self._current_state.content_key():
                self._redo_stack.clear()

        if is_boundary or self._had_selection_on_press:
            self._had_selection_on_press = False
            self._cancel_debounce()
            try:
                # Agenda após idle para garantir que RichTextController já aplicou tags na letra
                self.tb.after_idle(self.record_snapshot)
            except Exception:
                self.record_snapshot()
        else:
            self._schedule_debounce()

    def _on_cut_event(self, _event=None):
        if self._restoring or not self._is_editable():
            return
        self.commit_pending()
        try:
            self.tb.after_idle(self.record_snapshot)
        except Exception:
            pass

    def _restore_snapshot(self, snap: EditorSnapshot, override_callback: Optional[Callable[[], None]] = None):
        """Restaura integralmente texto, cores de sintaxe, formatação rica, cursor e seleção."""
        from utils.syntax_highlighter import configure_syntax_tags, clear_syntax_tags

        self._restoring = True
        self._cancel_debounce()
        try:
            self.tb.delete("1.0", "end")
            if snap.text:
                self.tb.insert("1.0", snap.text)

            clear_syntax_tags(self.tb, "1.0", "end")
            if snap.syntax_spans:
                configure_syntax_tags(self.tb)
                for tag_name, s, e in snap.syntax_spans:
                    try:
                        self.tb.tag_add(tag_name, s, e)
                    except Exception:
                        pass

            rich_text = self._get_rich_text()
            if rich_text is not None:
                rich_text.load(snap.formatting_json)

            try:
                self.tb.tag_remove("sel", "1.0", "end")
                if snap.selection:
                    self.tb.tag_add("sel", snap.selection[0], snap.selection[1])
                self.tb.mark_set("insert", snap.cursor)
                self.tb.see(snap.cursor)
                self.tb.focus_set()
            except Exception:
                pass

            if rich_text is not None:
                rich_text.sync_toolbar_state()

            try:
                self.tb.edit_reset()
            except Exception:
                pass
        finally:
            self._restoring = False
            self._last_edit_kind = None

        cb = override_callback or self.on_change_callback
        if cb:
            try:
                cb()
            except Exception:
                pass

    def undo(self, override_callback: Optional[Callable[[], None]] = None) -> bool:
        """Desfaz a última ação (edição de texto, formatação rica, XML/SQL, etc.)."""
        if self._restoring or not self._is_editable():
            return False

        self._cancel_debounce()
        live = self.capture_snapshot()

        # Caso 1: há edição recente ainda não consolidada no checkpoint atual
        if self._current_state is not None and live.content_key() != self._current_state.content_key():
            self._redo_stack.append(live)
            self._restore_snapshot(self._current_state, override_callback=override_callback)
            return True

        # Caso 2: volta para o checkpoint anterior na pilha de undo
        if not self._undo_stack:
            return False

        if self._current_state is not None:
            self._redo_stack.append(self._current_state)

        target = self._undo_stack.pop()
        self._current_state = target
        self._restore_snapshot(target, override_callback=override_callback)
        return True

    def redo(self, override_callback: Optional[Callable[[], None]] = None) -> bool:
        """Refaz a última ação desfeita."""
        if self._restoring or not self._is_editable() or not self._redo_stack:
            return False

        self._cancel_debounce()
        if self._current_state is not None:
            self._push_undo(self._current_state)

        target = self._redo_stack.pop()
        self._current_state = target
        self._restore_snapshot(target, override_callback=override_callback)
        return True

    def can_undo(self) -> bool:
        if self._undo_stack:
            return True
        if self._current_state is not None:
            live = self.capture_snapshot()
            return live.content_key() != self._current_state.content_key()
        return False

    def can_redo(self) -> bool:
        return bool(self._redo_stack)


def attach_editor_history(
    ctk_textbox: ctk.CTkTextbox,
    on_change_callback: Optional[Callable[[], None]] = None,
) -> EditorHistoryManager:
    """Anexa (ou atualiza callback de) um EditorHistoryManager no CTkTextbox."""
    existing = getattr(ctk_textbox, "_history_manager", None)
    if existing is not None:
        if on_change_callback is not None:
            existing.on_change_callback = on_change_callback
        return existing
    mgr = EditorHistoryManager(ctk_textbox, on_change_callback=on_change_callback)
    ctk_textbox._history_manager = mgr
    return mgr


def get_editor_history(ctk_textbox: ctk.CTkTextbox) -> Optional[EditorHistoryManager]:
    return getattr(ctk_textbox, "_history_manager", None)


def commit_history_before_action(ctk_textbox: ctk.CTkTextbox) -> None:
    mgr = get_editor_history(ctk_textbox)
    if mgr is not None:
        mgr.commit_pending()


def record_history_after_action(ctk_textbox: ctk.CTkTextbox) -> None:
    mgr = get_editor_history(ctk_textbox)
    if mgr is not None:
        mgr.record_snapshot()


def reset_editor_history(ctk_textbox: ctk.CTkTextbox) -> None:
    mgr = get_editor_history(ctk_textbox)
    if mgr is not None:
        mgr.reset()
