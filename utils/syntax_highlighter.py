import re
import tkinter as tk
from typing import Optional, Tuple, List, Callable
import customtkinter as ctk


# Paleta de cores para Syntax Highlighting (Modo Claro, Modo Escuro)
SYNTAX_COLORS = {
    # XML
    "syntax_xml_bracket": ("#0369A1", "#38BDF8"),     # Azul ciano para < > </ />
    "syntax_xml_tag": ("#1D4ED8", "#60A5FA"),         # Azul forte para nome da tag
    "syntax_xml_attr_name": ("#7C3AED", "#C084FC"),   # Roxo/Lilás para nome do atributo
    "syntax_xml_attr_val": ("#15803D", "#4ADE80"),    # Verde para valor do atributo "..."
    "syntax_xml_comment": ("#64748B", "#94A3B8"),     # Cinza para <!-- comentários -->
    "syntax_xml_cdata": ("#B45309", "#FBBF24"),       # Âmbar para CDATA
    # SQL
    "syntax_sql_keyword": ("#BE185D", "#F472B6"),     # Rosa/Magenta vibrante para palavras-chave SQL
    "syntax_sql_function": ("#0284C7", "#38BDF8"),    # Azul Ciano para funções SQL
    "syntax_sql_string": ("#15803D", "#4ADE80"),      # Verde para strings '...'
    "syntax_sql_number": ("#C2410C", "#FB923C"),      # Laranja para números
    "syntax_sql_operator": ("#6D28D9", "#A78BFA"),    # Violeta para operadores
    "syntax_sql_comment": ("#64748B", "#94A3B8"),     # Cinza para comentários -- e /* */
}

ALL_SYNTAX_TAGS = tuple(SYNTAX_COLORS.keys())

SQL_KEYWORDS = {
    "SELECT", "FROM", "WHERE", "AND", "OR", "NOT", "IN", "EXISTS", "BETWEEN",
    "LIKE", "ILIKE", "IS", "NULL", "TRUE", "FALSE", "AS", "ON", "USING",
    "JOIN", "INNER", "LEFT", "RIGHT", "FULL", "OUTER", "CROSS", "NATURAL",
    "INSERT", "INTO", "VALUES", "UPDATE", "SET", "DELETE", "MERGE", "MATCHED",
    "CREATE", "ALTER", "DROP", "TRUNCATE", "RENAME", "REPLACE",
    "TABLE", "VIEW", "MATERIALIZED", "INDEX", "UNIQUE", "SEQUENCE", "SYNONYM",
    "PROCEDURE", "FUNCTION", "PACKAGE", "BODY", "TRIGGER", "TYPE", "DATABASE", "SCHEMA",
    "PRIMARY", "KEY", "FOREIGN", "REFERENCES", "CONSTRAINT", "CHECK", "DEFAULT",
    "GROUP", "ORDER", "BY", "HAVING", "ASC", "DESC", "NULLS", "FIRST", "LAST",
    "UNION", "ALL", "INTERSECT", "MINUS", "EXCEPT", "DISTINCT",
    "LIMIT", "OFFSET", "FETCH", "NEXT", "ROWS", "ONLY", "TOP", "ROWNUM", "ROWID",
    "CASE", "WHEN", "THEN", "ELSE", "END", "IF", "ELSIF", "LOOP", "WHILE", "FOR",
    "BEGIN", "DECLARE", "EXCEPTION", "RAISE", "RETURN", "EXIT", "CONTINUE", "GOTO",
    "CURSOR", "OPEN", "CLOSE", "BULK", "COLLECT", "FORALL", "record", "ROWTYPE", "TYPE",
    "COMMIT", "ROLLBACK", "SAVEPOINT", "TRANSACTION", "WORK", "GRANT", "REVOKE",
    "NUMBER", "VARCHAR2", "NVARCHAR2", "VARCHAR", "CHAR", "NCHAR", "CLOB", "NCLOB",
    "BLOB", "DATE", "TIMESTAMP", "INTERVAL", "INTEGER", "INT", "SMALLINT", "BIGINT",
    "DECIMAL", "NUMERIC", "FLOAT", "DOUBLE", "REAL", "BOOLEAN", "RAW", "LONG", "XMLTYPE",
    "DUAL", "SYSDATE", "SYSTIMESTAMP", "CURRENT_DATE", "CURRENT_TIMESTAMP", "USER",
    "PRAGMA", "AUTONOMOUS_TRANSACTION", "EXCEPTION_INIT", "NOCOPY", "DETERMINISTIC",
    "WITH", "RECURSIVE", "OVER", "PARTITION", "WINDOW", "ROWS", "RANGE", "UNBOUNDED",
    "PRECEDING", "FOLLOWING", "CURRENT", "ROW", "RETURNING", "NOCYCLE", "START", "CONNECT", "PRIOR",
}

SQL_FUNCTIONS = {
    "COUNT", "SUM", "AVG", "MIN", "MAX", "STDDEV", "VARIANCE",
    "NVL", "NVL2", "COALESCE", "DECODE", "NULLIF", "GREATEST", "LEAST",
    "TO_CHAR", "TO_DATE", "TO_NUMBER", "TO_TIMESTAMP", "TO_CLOB", "CAST", "CONVERT",
    "SUBSTR", "SUBSTRING", "INSTR", "LENGTH", "CHAR_LENGTH", "REPLACE", "TRANSLATE",
    "TRIM", "LTRIM", "RTRIM", "LPAD", "RPAD", "UPPER", "LOWER", "INITCAP", "CONCAT",
    "ROUND", "TRUNC", "MOD", "ABS", "CEIL", "CEILING", "FLOOR", "SIGN", "POWER", "SQRT",
    "ADD_MONTHS", "MONTHS_BETWEEN", "LAST_DAY", "NEXT_DAY", "EXTRACT", "SYSDATE",
    "LISTAGG", "WM_CONCAT", "STRING_AGG", "GROUP_CONCAT",
    "ROW_NUMBER", "RANK", "DENSE_RANK", "NTILE", "LAG", "LEAD", "FIRST_VALUE", "LAST_VALUE",
    "REGEXP_LIKE", "REGEXP_REPLACE", "REGEXP_SUBSTR", "REGEXP_INSTR", "REGEXP_COUNT",
    "XMLELEMENT", "XMLAGG", "XMLFOREST", "XMLATTRIBUTES", "EXTRACTVALUE", "XMLTABLE",
    "DBMS_OUTPUT", "PUT_LINE", "RAISE_APPLICATION_ERROR", "SQLCODE", "SQLERRM",
}

# Expressões compiladas para performance
_RE_XML_COMMENT = re.compile(r"<!--[\s\S]*?-->")
_RE_XML_CDATA = re.compile(r"<!\[CDATA\[[\s\S]*?\]\]>")
_RE_XML_TAG = re.compile(r"(<\?xml[\s\S]*?\?>|</?[a-zA-Z_][\w:.\-]*(?:\s+[^<>]*?)?/?>)")
_RE_XML_TAG_PARTS = re.compile(r"^(<\?|\?|</|<)([a-zA-Z_][\w:.\-]*)(.*?)(\?>|/>|>)$", re.DOTALL)
_RE_XML_ATTR = re.compile(r'([a-zA-Z_][\w:.\-]*)(\s*=\s*)("[^"]*"|\'[^\']*\')')

_RE_SQL_COMMENT = re.compile(r"(--[^\n]*|/\*[\s\S]*?\*/)")
_RE_SQL_STRING = re.compile(r"('(?:''|[^'])*')")
_RE_SQL_NUMBER = re.compile(r"\b(\d+(?:\.\d+)?)\b")
_RE_SQL_WORD = re.compile(r"\b([a-zA-Z_][a-zA-Z0-9_$#]*)\b")
_RE_SQL_OPERATOR = re.compile(r"(:=|<>|!=|<=|>=|\|\|=|\|\||=)")

# Detectores rápidos para realce automático ao abrir notas
_RE_HAS_XML = re.compile(r"</?[a-zA-Z_][\w:.\-]*(?:\s+[^<>]*?)?>")
_RE_HAS_SQL = re.compile(
    r"\b(SELECT\s+[\s\S]+?\bFROM\b|INSERT\s+INTO\b|UPDATE\s+\w+[\s\S]+?\bSET\b|"
    r"DELETE\s+FROM\b|CREATE\s+(?:OR\s+REPLACE\s+)?(?:TABLE|VIEW|PROCEDURE|FUNCTION|PACKAGE|TRIGGER|INDEX|SEQUENCE)\b|"
    r"ALTER\s+(?:TABLE|VIEW|PROCEDURE|FUNCTION|PACKAGE|TRIGGER|SESSION)\b|"
    r"BEGIN\b[\s\S]+?\bEND\s*;)",
    re.IGNORECASE,
)


def configure_syntax_tags(text_widget: tk.Text) -> None:
    """Configura as tags de cores de sintaxe (XML e SQL) de acordo com o tema atual (Claro/Escuro)."""
    try:
        mode = ctk.get_appearance_mode()
        is_dark = (mode == "Dark")
        idx = 1 if is_dark else 0

        for tag_name, color_pair in SYNTAX_COLORS.items():
            color = color_pair[idx]
            if tag_name in ("syntax_xml_tag", "syntax_sql_keyword", "syntax_sql_function"):
                text_widget.tag_configure(tag_name, foreground=color, font=("Segoe UI", 11, "bold"))
            elif tag_name in ("syntax_xml_comment", "syntax_sql_comment"):
                text_widget.tag_configure(tag_name, foreground=color, font=("Segoe UI", 11, "italic"))
            else:
                text_widget.tag_configure(tag_name, foreground=color)

        # Garante que a seleção de texto ('sel') fique sempre visível acima das cores de sintaxe
        text_widget.tag_raise("sel")
    except Exception:
        pass


def clear_syntax_tags(text_widget: tk.Text, start_idx: str = "1.0", end_idx: str = "end") -> None:
    """Remove as tags de coloração de sintaxe XML/SQL no intervalo especificado."""
    try:
        for tag_name in ALL_SYNTAX_TAGS:
            text_widget.tag_remove(tag_name, start_idx, end_idx)
    except Exception:
        pass


def convert_selection_case(
    ctk_textbox: ctk.CTkTextbox,
    uppercase: bool = True,
    fallback_entry: Optional[ctk.CTkEntry] = None,
) -> Tuple[bool, str]:
    """
    Converte o texto selecionado no editor (ou no campo de título, se selecionado lá)
    para MAIÚSCULAS (uppercase=True) ou minúsculas (uppercase=False).
    Mantém a seleção ativa após a conversão para facilitar alternância.
    """
    text_widget = ctk_textbox._textbox

    # 1. Verifica se há seleção na caixa de texto principal
    sel_ranges = text_widget.tag_ranges("sel")
    if sel_ranges:
        start_idx = text_widget.index("sel.first")
        end_idx = text_widget.index("sel.last")
        selected_text = text_widget.get(start_idx, end_idx)
        if not selected_text:
            return False, "Selecione um trecho de texto para converter."

        converted = selected_text.upper() if uppercase else selected_text.lower()
        if converted != selected_text:
            # Preserva tags existentes no trecho e registra separador de Undo (Ctrl+Z)
            active_tags = [
                t for t in text_widget.tag_names(start_idx)
                if t not in ("sel", "spelling_error")
            ]
            try:
                text_widget.edit_separator()
            except Exception:
                pass
            text_widget.delete(start_idx, end_idx)
            text_widget.insert(start_idx, converted)
            try:
                text_widget.edit_separator()
            except Exception:
                pass
            new_end_idx = f"{start_idx} + {len(converted)} chars"
            for t in active_tags:
                text_widget.tag_add(t, start_idx, new_end_idx)
            text_widget.tag_add("sel", start_idx, new_end_idx)
            text_widget.mark_set("insert", new_end_idx)
            text_widget.focus_set()
        else:
            text_widget.tag_add("sel", start_idx, end_idx)

        return True, ""

    # 2. Verifica se há seleção no campo de título (ex: Nome da Nota em Notas & Pastas)
    if fallback_entry is not None:
        try:
            inner_entry = fallback_entry._entry
            if inner_entry.selection_present():
                sel_start = inner_entry.index("sel.first")
                sel_end = inner_entry.index("sel.last")
                full_val = inner_entry.get()
                sub = full_val[sel_start:sel_end]
                conv = sub.upper() if uppercase else sub.lower()
                inner_entry.delete(sel_start, sel_end)
                inner_entry.insert(sel_start, conv)
                inner_entry.select_range(sel_start, sel_start + len(conv))
                inner_entry.focus_set()
                return True, ""
        except Exception:
            pass

    target_label = "MAIÚSCULO" if uppercase else "minúsculo"
    return (
        False,
        f"Selecione primeiro no texto o trecho que deseja transformar em {target_label}.",
    )


def format_xml_string(raw_text: str) -> str:
    """
    Indenta e organiza código XML (mesmo que esteja em uma única linha ou seja um fragmento)
    preservando todo o conteúdo e textos ao redor.
    """
    if not raw_text or "<" not in raw_text or ">" not in raw_text:
        return raw_text

    # Quebra entre tags coladas: ><  ->  >\n<
    formatted = re.sub(r">\s*<", ">\n<", raw_text.strip())
    lines = [ln.strip() for ln in formatted.splitlines() if ln.strip()]

    result_lines: List[str] = []
    indent_level = 0
    indent_str = "  "

    for line in lines:
        # Tag de fechamento: </tag>
        if re.match(r"^</[a-zA-Z_][\w:.\-]*\s*>", line):
            indent_level = max(0, indent_level - 1)
            result_lines.append(f"{indent_str * indent_level}{line}")
        # Declaração XML, comentário, CDATA ou tag auto-fechada: <?xml...?>, <!--...-->, <tag/>
        elif (
            line.startswith("<?")
            or line.startswith("<!")
            or line.endswith("/>")
        ):
            result_lines.append(f"{indent_str * indent_level}{line}")
        # Tag que abre e fecha na mesma linha: <tag>valor</tag>
        elif re.match(r"^<[a-zA-Z_][\w:.\-]*(?:\s+[^<>]*?)?>.*</[a-zA-Z_][\w:.\-]*\s*>$", line):
            result_lines.append(f"{indent_str * indent_level}{line}")
        # Tag de abertura: <tag ...>
        elif re.match(r"^<[a-zA-Z_][\w:.\-]*(?:\s+[^<>]*?)?>$", line):
            result_lines.append(f"{indent_str * indent_level}{line}")
            indent_level += 1
        else:
            result_lines.append(f"{indent_str * indent_level}{line}")

    return "\n".join(result_lines)


def format_sql_string(raw_text: str) -> str:
    """
    Formata código SQL/PLSQL:
    - Converte palavras-chave e funções SQL para MAIÚSCULAS (preservando strings e comentários intactos).
    - Se a query estiver em uma única linha longa, organiza as cláusulas principais em linhas.
    """
    if not raw_text or not raw_text.strip():
        return raw_text

    # Protege comentários e strings durante a conversão de keywords
    protected_spans: List[Tuple[int, int]] = []
    for m in _RE_SQL_COMMENT.finditer(raw_text):
        protected_spans.append((m.start(), m.end()))
    for m in _RE_SQL_STRING.finditer(raw_text):
        protected_spans.append((m.start(), m.end()))

    def _is_protected(pos: int) -> bool:
        for s, e in protected_spans:
            if s <= pos < e:
                return True
        return False

    def _replace_word(match: re.Match) -> str:
        if _is_protected(match.start()):
            return match.group(0)
        word = match.group(1)
        upper_w = word.upper()
        if upper_w in SQL_KEYWORDS or upper_w in SQL_FUNCTIONS:
            return upper_w
        return word

    result = _RE_SQL_WORD.sub(_replace_word, raw_text)

    # Se for uma consulta em linha única com mais de 70 caracteres, quebra nas cláusulas principais
    non_empty_lines = [ln for ln in result.strip().splitlines() if ln.strip()]
    if len(non_empty_lines) == 1 and len(non_empty_lines[0]) > 70:
        clause_pattern = re.compile(
            r"\s+\b(FROM|WHERE|INNER\s+JOIN|LEFT\s+(?:OUTER\s+)?JOIN|RIGHT\s+(?:OUTER\s+)?JOIN|"
            r"FULL\s+(?:OUTER\s+)?JOIN|GROUP\s+BY|ORDER\s+BY|HAVING|UNION(?:\s+ALL)?|VALUES|SET)\b",
            re.IGNORECASE,
        )
        result = clause_pattern.sub(lambda m: f"\n{m.group(1).upper()}", result)

    return result


def highlight_xml_range(text_widget: tk.Text, start_idx: str = "1.0", end_idx: str = "end") -> None:
    """Aplica coloração de sintaxe XML no intervalo indicado do widget de texto."""
    configure_syntax_tags(text_widget)
    clear_syntax_tags(text_widget, start_idx, end_idx)

    segment = text_widget.get(start_idx, end_idx)
    if not segment:
        return

    # 1. Tags XML (<tag attr="val">, </tag>, <?xml ...?>)
    for match in _RE_XML_TAG.finditer(segment):
        tag_start = match.start()
        tag_text = match.group(0)

        parts = _RE_XML_TAG_PARTS.match(tag_text)
        if not parts:
            s_pos = f"{start_idx} + {tag_start} chars"
            e_pos = f"{start_idx} + {match.end()} chars"
            text_widget.tag_add("syntax_xml_tag", s_pos, e_pos)
            continue

        open_br, tag_name, attrs_part, close_br = parts.groups()

        # Delimitador de abertura (<, </, <?)
        p0 = tag_start
        p1 = p0 + len(open_br)
        text_widget.tag_add("syntax_xml_bracket", f"{start_idx} + {p0} chars", f"{start_idx} + {p1} chars")

        # Nome da tag
        p2 = p1 + len(tag_name)
        text_widget.tag_add("syntax_xml_tag", f"{start_idx} + {p1} chars", f"{start_idx} + {p2} chars")

        # Atributos dentro da tag
        if attrs_part:
            attr_offset = p2
            for attr_m in _RE_XML_ATTR.finditer(attrs_part):
                a_name_s = attr_offset + attr_m.start(1)
                a_name_e = attr_offset + attr_m.end(1)
                text_widget.tag_add(
                    "syntax_xml_attr_name",
                    f"{start_idx} + {a_name_s} chars",
                    f"{start_idx} + {a_name_e} chars",
                )

                a_val_s = attr_offset + attr_m.start(3)
                a_val_e = attr_offset + attr_m.end(3)
                text_widget.tag_add(
                    "syntax_xml_attr_val",
                    f"{start_idx} + {a_val_s} chars",
                    f"{start_idx} + {a_val_e} chars",
                )

        # Delimitador de fechamento (>, />, ?>)
        p3 = match.end() - len(close_br)
        p4 = match.end()
        text_widget.tag_add("syntax_xml_bracket", f"{start_idx} + {p3} chars", f"{start_idx} + {p4} chars")

    # 2. CDATA
    for match in _RE_XML_CDATA.finditer(segment):
        s_pos = f"{start_idx} + {match.start()} chars"
        e_pos = f"{start_idx} + {match.end()} chars"
        text_widget.tag_add("syntax_xml_cdata", s_pos, e_pos)

    # 3. Comentários XML (<!-- ... -->)
    for match in _RE_XML_COMMENT.finditer(segment):
        s_pos = f"{start_idx} + {match.start()} chars"
        e_pos = f"{start_idx} + {match.end()} chars"
        text_widget.tag_add("syntax_xml_comment", s_pos, e_pos)


def highlight_sql_range(text_widget: tk.Text, start_idx: str = "1.0", end_idx: str = "end") -> None:
    """Aplica coloração de sintaxe SQL/PLSQL no intervalo indicado do widget de texto."""
    configure_syntax_tags(text_widget)
    clear_syntax_tags(text_widget, start_idx, end_idx)

    segment = text_widget.get(start_idx, end_idx)
    if not segment:
        return

    # 1. Identifica intervalos de comentários e strings para não colorir keywords dentro deles
    protected_spans: List[Tuple[int, int, str]] = []
    for m in _RE_SQL_COMMENT.finditer(segment):
        protected_spans.append((m.start(), m.end(), "syntax_sql_comment"))

    for m in _RE_SQL_STRING.finditer(segment):
        # Só adiciona string se não estiver dentro de um comentário
        in_comment = any(cs <= m.start() < ce for cs, ce, _ in protected_spans)
        if not in_comment:
            protected_spans.append((m.start(), m.end(), "syntax_sql_string"))

    def _in_protected(pos: int) -> bool:
        for s, e, _ in protected_spans:
            if s <= pos < e:
                return True
        return False

    # 2. Operadores SQL
    for m in _RE_SQL_OPERATOR.finditer(segment):
        if not _in_protected(m.start()):
            text_widget.tag_add(
                "syntax_sql_operator",
                f"{start_idx} + {m.start()} chars",
                f"{start_idx} + {m.end()} chars",
            )

    # 3. Números
    for m in _RE_SQL_NUMBER.finditer(segment):
        if not _in_protected(m.start()):
            text_widget.tag_add(
                "syntax_sql_number",
                f"{start_idx} + {m.start()} chars",
                f"{start_idx} + {m.end()} chars",
            )

    # 4. Palavras-chave e Funções SQL
    for m in _RE_SQL_WORD.finditer(segment):
        if _in_protected(m.start()):
            continue
        upper_w = m.group(1).upper()
        if upper_w in SQL_FUNCTIONS:
            text_widget.tag_add(
                "syntax_sql_function",
                f"{start_idx} + {m.start()} chars",
                f"{start_idx} + {m.end()} chars",
            )
        elif upper_w in SQL_KEYWORDS:
            text_widget.tag_add(
                "syntax_sql_keyword",
                f"{start_idx} + {m.start()} chars",
                f"{start_idx} + {m.end()} chars",
            )

    # 5. Strings e Comentários
    for s, e, tag_name in protected_spans:
        text_widget.tag_add(
            tag_name,
            f"{start_idx} + {s} chars",
            f"{start_idx} + {e} chars",
        )


def format_and_highlight_xml(ctk_textbox: ctk.CTkTextbox, indent_xml: bool = True) -> bool:
    """
    Formata (indenta) e aplica coloração XML ao trecho selecionado
    ou a todo o texto caso não haja seleção.
    """
    text_widget = ctk_textbox._textbox
    sel_ranges = text_widget.tag_ranges("sel")

    if sel_ranges:
        start_idx = text_widget.index("sel.first")
        end_idx = text_widget.index("sel.last")
        raw = text_widget.get(start_idx, end_idx)
        if not raw.strip():
            return False
        formatted = format_xml_string(raw) if indent_xml else raw
        if formatted != raw:
            try:
                text_widget.edit_separator()
            except Exception:
                pass
            text_widget.delete(start_idx, end_idx)
            text_widget.insert(start_idx, formatted)
            try:
                text_widget.edit_separator()
            except Exception:
                pass
            end_idx = f"{start_idx} + {len(formatted)} chars"
            text_widget.tag_add("sel", start_idx, end_idx)
        highlight_xml_range(text_widget, start_idx, end_idx)
        return True
    else:
        raw = text_widget.get("1.0", "end-1c")
        if not raw.strip():
            return False
        if indent_xml and _RE_HAS_XML.search(raw):
            formatted = format_xml_string(raw)
            if formatted != raw:
                try:
                    text_widget.edit_separator()
                except Exception:
                    pass
                text_widget.delete("1.0", "end")
                text_widget.insert("1.0", formatted)
                try:
                    text_widget.edit_separator()
                except Exception:
                    pass
        highlight_xml_range(text_widget, "1.0", "end-1c")
        return True


def format_and_highlight_sql(ctk_textbox: ctk.CTkTextbox, format_keywords: bool = True) -> bool:
    """
    Formata (padroniza palavras-chave em maiúsculo e estrutura cláusulas) e aplica
    coloração SQL ao trecho selecionado ou a todo o texto caso não haja seleção.
    """
    text_widget = ctk_textbox._textbox
    sel_ranges = text_widget.tag_ranges("sel")

    if sel_ranges:
        start_idx = text_widget.index("sel.first")
        end_idx = text_widget.index("sel.last")
        raw = text_widget.get(start_idx, end_idx)
        if not raw.strip():
            return False
        formatted = format_sql_string(raw) if format_keywords else raw
        if formatted != raw:
            try:
                text_widget.edit_separator()
            except Exception:
                pass
            text_widget.delete(start_idx, end_idx)
            text_widget.insert(start_idx, formatted)
            try:
                text_widget.edit_separator()
            except Exception:
                pass
            end_idx = f"{start_idx} + {len(formatted)} chars"
            text_widget.tag_add("sel", start_idx, end_idx)
        highlight_sql_range(text_widget, start_idx, end_idx)
        return True
    else:
        raw = text_widget.get("1.0", "end-1c")
        if not raw.strip():
            return False
        formatted = format_sql_string(raw) if format_keywords else raw
        if formatted != raw:
            try:
                text_widget.edit_separator()
            except Exception:
                pass
            text_widget.delete("1.0", "end")
            text_widget.insert("1.0", formatted)
            try:
                text_widget.edit_separator()
            except Exception:
                pass
        highlight_sql_range(text_widget, "1.0", "end-1c")
        return True


def perform_undo(
    ctk_textbox: ctk.CTkTextbox,
    on_change_callback: Optional[Callable[[], None]] = None,
) -> bool:
    """
    Executa o Desfazer (Ctrl+Z) no editor de texto de forma segura,
    reaplicando realce de sintaxe e atualizando contadores/status.
    """
    text_widget = ctk_textbox._textbox
    try:
        if str(text_widget.cget("state")) == "disabled":
            return False
        text_widget.edit_undo()
    except tk.TclError:
        return False
    except Exception:
        return False

    auto_highlight_content(ctk_textbox)
    try:
        text_widget.see("insert")
        text_widget.focus_set()
    except Exception:
        pass

    if on_change_callback:
        on_change_callback()
    return True


def perform_redo(
    ctk_textbox: ctk.CTkTextbox,
    on_change_callback: Optional[Callable[[], None]] = None,
) -> bool:
    """
    Executa o Refazer (Ctrl+Y) no editor de texto de forma segura,
    reaplicando realce de sintaxe e atualizando contadores/status.
    """
    text_widget = ctk_textbox._textbox
    try:
        if str(text_widget.cget("state")) == "disabled":
            return False
        text_widget.edit_redo()
    except tk.TclError:
        return False
    except Exception:
        return False

    auto_highlight_content(ctk_textbox)
    try:
        text_widget.see("insert")
        text_widget.focus_set()
    except Exception:
        pass

    if on_change_callback:
        on_change_callback()
    return True


def reset_undo_stack(ctk_textbox: ctk.CTkTextbox) -> None:
    """
    Limpa o histórico de Undo/Redo após carregar uma nota do banco,
    evitando que o Ctrl+Z apague o texto original carregado.
    """
    try:
        ctk_textbox._textbox.edit_reset()
    except Exception:
        pass


def enable_undo_redo(
    ctk_textbox: ctk.CTkTextbox,
    on_change_callback: Optional[Callable[[], None]] = None,
) -> None:
    """
    Habilita e configura a pilha de Desfazer (Ctrl+Z) e Refazer (Ctrl+Y) no CTkTextbox,
    criando separadores automáticos ao digitar palavras/linhas e ao colar texto.
    """
    text_widget = ctk_textbox._textbox
    try:
        text_widget.configure(undo=True, autoseparators=True, maxundo=-1)
    except Exception:
        pass

    def _on_undo_event(_event=None):
        perform_undo(ctk_textbox, on_change_callback)
        return "break"

    def _on_redo_event(_event=None):
        perform_redo(ctk_textbox, on_change_callback)
        return "break"

    def _on_word_boundary_key(event):
        # Cria um ponto de parada no Undo a cada palavra/linha digitada
        if event.keysym in ("space", "Return", "KP_Enter", "Tab", "BackSpace", "Delete", "period", "comma", "semicolon"):
            try:
                text_widget.edit_separator()
            except Exception:
                pass

    text_widget.bind("<<Undo>>", _on_undo_event)
    text_widget.bind("<Control-z>", _on_undo_event)
    text_widget.bind("<Control-Z>", _on_undo_event)
    text_widget.bind("<<Redo>>", _on_redo_event)
    text_widget.bind("<Control-y>", _on_redo_event)
    text_widget.bind("<Control-Y>", _on_redo_event)
    text_widget.bind("<KeyPress>", _on_word_boundary_key, add="+")


def auto_highlight_content(ctk_textbox: ctk.CTkTextbox) -> Optional[str]:
    """
    Detecta automaticamente se o texto possui estruturas XML e/ou SQL e aplica a
    coloração de sintaxe correspondente (útil ao carregar uma nota ou colar texto).
    Retorna 'XML', 'SQL', 'XML+SQL' ou None.
    """
    try:
        text_widget = ctk_textbox._textbox
        content = text_widget.get("1.0", "end-1c")
        if not content or not content.strip():
            clear_syntax_tags(text_widget)
            return None

        has_xml = bool(_RE_HAS_XML.search(content))
        has_sql = bool(_RE_HAS_SQL.search(content))

        if not has_xml and not has_sql:
            return None

        configure_syntax_tags(text_widget)

        if has_xml and not has_sql:
            highlight_xml_range(text_widget, "1.0", "end-1c")
            return "XML"
        elif has_sql and not has_xml:
            highlight_sql_range(text_widget, "1.0", "end-1c")
            return "SQL"
        else:
            # Possui ambos (ex: SQL com XMLType ou nota com SQL e XML)
            highlight_sql_range(text_widget, "1.0", "end-1c")
            # Aplica tags XML por cima apenas nos trechos de tags <...>
            for match in _RE_XML_TAG.finditer(content):
                s_idx = f"1.0 + {match.start()} chars"
                e_idx = f"1.0 + {match.end()} chars"
                highlight_xml_range(text_widget, s_idx, e_idx)
            return "XML+SQL"
    except Exception:
        return None
