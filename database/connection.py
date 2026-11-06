import sqlite3
import os
from contextlib import contextmanager
from typing import Optional, Generator
import config
from utils.text_utils import remove_accents, normalize_text


def get_connection(db_path: Optional[str] = None) -> sqlite3.Connection:
    """
    Cria e configura uma conexão com o banco de dados SQLite.
    - Habilita chaves estrangeiras (foreign keys)
    - Habilita modo WAL para alta performance e concorrência
    - Registra funções customizadas no SQLite para busca sem acentos
    """
    target_path = db_path or config.DB_PATH

    # Garante que o diretório pai existe
    if target_path != ":memory:":
        os.makedirs(os.path.dirname(os.path.abspath(target_path)), exist_ok=True)

    conn = sqlite3.connect(target_path, timeout=20.0)
    conn.row_factory = sqlite3.Row

    # Configurações do SQLite
    conn.execute("PRAGMA foreign_keys = ON;")
    if target_path != ":memory:":
        try:
            conn.execute("PRAGMA journal_mode = WAL;")
        except Exception:
            pass

    # Registra funções Python customizadas no SQLite para busca e normalização
    conn.create_function("remove_accents", 1, remove_accents)
    conn.create_function("lower_no_accents", 1, normalize_text)

    return conn


@contextmanager
def get_db(db_path: Optional[str] = None) -> Generator[sqlite3.Connection, None, None]:
    """
    Context manager para transações seguras no banco de dados.
    Faz commit se tudo ocorrer bem, ou rollback em caso de exceção.
    """
    conn = get_connection(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
