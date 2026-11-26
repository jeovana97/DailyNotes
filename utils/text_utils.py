import unicodedata
from typing import Optional

# Tabela rápida de tradução para acentos latinos comuns (C-level via str.translate)
_LATIN_ACCENT_MAP = str.maketrans(
    "ÁÀÂÃÄÅáàâãäåÉÈÊËéèêëÍÌÎÏíìîïÓÒÔÕÖØóòôõöøÚÙÛÜúùûüÇçÑñÝŸýÿ",
    "AAAAAAaaaaaaEEEEeeeeIIIIiiiiOOOOOOooooooUUUUuuuuCcNnYYyy",
)


def remove_accents(text: Optional[str]) -> str:
    """
    Remove todos os acentos e diacríticos de uma string com caminho rápido (fast-path).
    Exemplo: 'emissão' -> 'emissao', 'AÇÃO' -> 'ACAO'
    """
    if not text:
        return ""
    if text.isascii():
        return text
    translated = text.translate(_LATIN_ACCENT_MAP)
    if translated.isascii():
        return translated
    # Fallback completo NFD para caracteres fora da tabela latina comum
    normalized = unicodedata.normalize("NFD", translated)
    return "".join(c for c in normalized if unicodedata.category(c) != "Mn")


def normalize_text(text: Optional[str]) -> str:
    """
    Converte o texto para minúsculas e remove acentos para indexação e buscas precisas.
    Exemplo: 'Atenção aos Detalhes!' -> 'atencao aos detalhes!'
    """
    if not text:
        return ""
    if text.isascii():
        return text.lower().strip()
    return remove_accents(text).lower().strip()


def extract_snippet(
    content: str,
    query: str,
    context_chars: int = 80,
    norm_content: Optional[str] = None,
    norm_query: Optional[str] = None,
) -> str:
    """
    Localiza a ocorrência da busca (sem diferenciar maiúsculas e acentos)
    e extrai um trecho com contexto ao redor da palavra.
    Aceita `norm_content` e `norm_query` pré-calculados para evitar re-normalização em lote.
    """
    if not content:
        return "(Sem conteúdo)"

    if not query:
        # Retorna o início do conteúdo se não houver busca
        first_line = content.strip().split("\n", 1)[0]
        if len(first_line) > context_chars * 2:
            return first_line[: context_chars * 2].strip() + "..."
        return first_line

    n_query = norm_query if norm_query is not None else normalize_text(query)
    if not n_query:
        first_line = content.strip().split("\n", 1)[0]
        if len(first_line) > context_chars * 2:
            return first_line[: context_chars * 2].strip() + "..."
        return first_line

    if norm_content is not None:
        n_content = norm_content
        # Compensa espaços/quebras iniciais removidos pelo .strip() na normalização salva no banco
        leading_ws = len(content) - len(content.lstrip())
    else:
        n_content = normalize_text(content)
        leading_ws = len(content) - len(content.lstrip())

    pos = n_content.find(n_query)
    match_len = len(n_query)
    if pos == -1:
        # Se não achou na expressão completa, tenta localizar ao menos o primeiro termo relevante
        for term in n_query.split():
            if len(term) >= 3:
                pos = n_content.find(term)
                if pos != -1:
                    match_len = len(term)
                    break

    if pos == -1:
        first_line = content.strip().split("\n", 1)[0]
        if len(first_line) > context_chars * 2:
            return first_line[: context_chars * 2].strip() + "..."
        return first_line

    orig_pos = min(len(content), pos + leading_ws)
    start = max(0, orig_pos - context_chars)
    end = min(len(content), orig_pos + match_len + context_chars)

    snippet = content[start:end].replace("\r\n", " ").replace("\n", " ").strip()

    prefix = "... " if start > 0 else ""
    suffix = " ..." if end < len(content) else ""

    return f"{prefix}{snippet}{suffix}"


def detect_encoding(file_path: str) -> str:
    """
    Detecta a codificação correta de um arquivo de texto.
    Prioriza UTF-8 (com ou sem BOM), Windows-1252 e ISO-8859-1.
    """
    encodings_to_try = ["utf-8-sig", "utf-8", "cp1252", "iso-8859-1"]

    with open(file_path, "rb") as f:
        raw_data = f.read()

    for enc in encodings_to_try:
        try:
            raw_data.decode(enc)
            return enc
        except UnicodeDecodeError:
            continue

    # Fallback seguro
    return "latin1"
