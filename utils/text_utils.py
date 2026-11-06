import re
import unicodedata
from typing import Optional


def remove_accents(text: Optional[str]) -> str:
    """
    Remove todos os acentos e diacríticos de uma string.
    Exemplo: 'emissão' -> 'emissao', 'AÇÃO' -> 'ACAO'
    """
    if not text:
        return ""
    # Decompõe caracteres acentuados (NFD) e filtra marcas de combinação de diacríticos (Mn)
    normalized = unicodedata.normalize("NFD", text)
    return "".join(c for c in normalized if unicodedata.category(c) != "Mn")


def normalize_text(text: Optional[str]) -> str:
    """
    Converte o texto para minúsculas e remove acentos para indexação e buscas precisas.
    Exemplo: 'Atenção aos Detalhes!' -> 'atencao aos detalhes!'
    """
    if not text:
        return ""
    return remove_accents(text).lower().strip()


def extract_snippet(content: str, query: str, context_chars: int = 80) -> str:
    """
    Localiza a ocorrência da busca (sem diferenciar maiúsculas e acentos)
    e extrai um trecho com contexto ao redor da palavra.
    Exemplo: '...houve um erro na emissão de notas fiscais...'
    """
    if not content:
        return "(Sem conteúdo)"

    if not query:
        # Retorna o início do conteúdo se não houver busca
        first_line = content.strip().split("\n")[0]
        if len(first_line) > context_chars * 2:
            return first_line[: context_chars * 2].strip() + "..."
        return first_line

    norm_content = normalize_text(content)
    norm_query = normalize_text(query)

    pos = norm_content.find(norm_query)
    if pos == -1:
        # Se não achou na versão normalizada (ex: query com múltiplos termos), tenta achar pelo menos o primeiro termo
        terms = norm_query.split()
        for term in terms:
            if len(term) >= 3:
                pos = norm_content.find(term)
                if pos != -1:
                    norm_query = term
                    break

    if pos == -1:
        # Fallback: exibe início
        first_line = content.strip().split("\n")[0]
        if len(first_line) > context_chars * 2:
            return first_line[: context_chars * 2].strip() + "..."
        return first_line

    # Calcula limites do snippet
    start = max(0, pos - context_chars)
    end = min(len(content), pos + len(norm_query) + context_chars)

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
