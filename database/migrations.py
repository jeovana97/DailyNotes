import sqlite3
import logging
from typing import Optional
from .connection import get_connection
from .schema import (
    CREATE_USERS_TABLE,
    CREATE_DIARIES_TABLE,
    CREATE_DIARIES_INDEXES,
    CREATE_DIARIES_FTS,
    CREATE_FTS_TRIGGERS,
    CREATE_NOTE_FOLDERS_TABLE,
    CREATE_NOTES_TABLE,
    CREATE_NOTES_INDEXES,
    CREATE_CUSTOM_DICTIONARY_TABLE,
    CREATE_IMPORT_HISTORY_TABLE,
    CREATE_BACKUP_SETTINGS_TABLE,
)

logger = logging.getLogger(__name__)


def init_db(db_path: Optional[str] = None) -> None:
    """
    Inicializa o banco de dados criando as tabelas, índices e triggers necessários.
    """
    conn = get_connection(db_path)
    try:
        with conn:
            # 1. Criação das tabelas principais
            conn.execute(CREATE_USERS_TABLE)
            conn.execute(CREATE_DIARIES_TABLE)
            conn.execute(CREATE_NOTE_FOLDERS_TABLE)
            conn.execute(CREATE_NOTES_TABLE)
            conn.execute(CREATE_CUSTOM_DICTIONARY_TABLE)
            conn.execute(CREATE_IMPORT_HISTORY_TABLE)
            conn.execute(CREATE_BACKUP_SETTINGS_TABLE)

            # Migração incremental: garante coluna theme_preference em bancos já existentes
            cursor = conn.execute("PRAGMA table_info(users)")
            user_cols = {row["name"] for row in cursor.fetchall()}
            if "theme_preference" not in user_cols:
                conn.execute(
                    "ALTER TABLE users ADD COLUMN theme_preference TEXT NOT NULL DEFAULT 'dark'"
                )

            # Migração incremental: garante coluna retention_days em backup_settings
            cursor = conn.execute("PRAGMA table_info(backup_settings)")
            bkp_cols = {row["name"] for row in cursor.fetchall()}
            if "retention_days" not in bkp_cols:
                conn.execute(
                    "ALTER TABLE backup_settings ADD COLUMN retention_days INTEGER NOT NULL DEFAULT 7"
                )

            # 2. Criação dos índices
            for statement in CREATE_DIARIES_INDEXES.strip().split(";"):
                stmt = statement.strip()
                if stmt:
                    conn.execute(stmt)

            for statement in CREATE_NOTES_INDEXES.strip().split(";"):
                stmt = statement.strip()
                if stmt:
                    conn.execute(stmt)

            # 3. Criação da tabela virtual FTS5 e triggers
            try:
                conn.execute(CREATE_DIARIES_FTS)
                conn.executescript(CREATE_FTS_TRIGGERS)
            except sqlite3.OperationalError as e:
                logger.warning("FTS5 não disponível ou erro ao criar tabela virtual: %s", e)

        logger.info("Banco de dados inicializado com sucesso.")
    finally:
        conn.close()
