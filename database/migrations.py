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
    CREATE_DIARIES_FTS_TRIGRAM,
    CREATE_DIARIES_TRIGRAM_TRIGGERS,
    CREATE_NOTE_FOLDERS_TABLE,
    CREATE_NOTES_TABLE,
    CREATE_NOTES_INDEXES,
    CREATE_NOTES_FTS_TRIGRAM,
    CREATE_NOTES_TRIGRAM_TRIGGERS,
    CREATE_CUSTOM_DICTIONARY_TABLE,
    CREATE_IMPORT_HISTORY_TABLE,
    CREATE_BACKUP_SETTINGS_TABLE,
    CREATE_SCHEDULES_TABLE,
    CREATE_SCHEDULES_INDEXES,
    CREATE_TAREFAS_TABLE,
    CREATE_HISTORICO_TAREFAS_TABLE,
    CREATE_LEMBRETES_TAREFAS_TABLE,
    CREATE_TAREFAS_INDEXES,
)
from utils.text_utils import normalize_text

logger = logging.getLogger(__name__)


def _migrate_legacy_schedules_to_tasks(conn: sqlite3.Connection) -> None:
    """
    Converte de forma segura e idempotente os registros existentes na tabela
    legada `schedules` para as novas tabelas `tarefas`, `historico_tarefas` e
    `lembretes_tarefas`, sem apagar nem modificar os dados antigos.
    """
    legacy_rows = conn.execute(
        """
        SELECT s.*
        FROM schedules s
        LEFT JOIN tarefas t ON t.legacy_schedule_id = s.id
        WHERE t.id IS NULL
        ORDER BY s.id ASC
        """
    ).fetchall()

    if not legacy_rows:
        return

    priority_map = {
        "baixa": "baixa",
        "normal": "media",
        "media": "media",
        "alta": "alta",
        "urgente": "urgente",
    }
    status_map = {
        "pendente": "pendente",
        "notificado": "pendente",
        "em_andamento": "em_andamento",
        "concluido": "concluida",
        "concluida": "concluida",
        "cancelado": "cancelada",
        "cancelada": "cancelada",
    }

    for row in legacy_rows:
        legacy_id = row["id"]
        user_id = row["user_id"]
        title = (row["title"] or "").strip() or f"Agendamento #{legacy_id}"
        description = (row["content"] or "").strip()
        due_date = (row["schedule_date"] or "").strip()
        due_time = (row["schedule_time"] or "").strip()
        created_at = (row["created_at"] or "").strip()
        updated_at = (row["updated_at"] or created_at).strip()
        start_date = created_at[:10] if len(created_at) >= 10 else due_date

        raw_priority = (row["priority"] or "normal").strip().lower()
        priority = priority_map.get(raw_priority, "media")

        raw_status = (row["status"] or "pendente").strip().lower()
        status = status_map.get(raw_status, "pendente")
        completed_at = updated_at if status == "concluida" else None

        repeat_interval = (row["repeat_interval"] or "none").strip().lower()
        if repeat_interval not in ("none", "daily", "weekly", "monthly"):
            repeat_interval = "none"

        notified_at = row["notified_at"]
        is_sent = 1 if (raw_status == "notificado" or bool(notified_at)) else 0
        is_active = 1 if status in ("pendente", "em_andamento") else 0

        cur = conn.execute(
            """
            INSERT INTO tarefas (
                user_id, title, title_normalized, description, description_normalized,
                start_date, due_date, due_time, priority, status,
                category, category_normalized, reminder_enabled,
                completed_at, legacy_schedule_id, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '', '', 1, ?, ?, ?, ?)
            """,
            (
                user_id,
                title,
                normalize_text(title),
                description,
                normalize_text(description),
                start_date,
                due_date,
                due_time,
                priority,
                status,
                completed_at,
                legacy_id,
                created_at,
                updated_at,
            ),
        )
        new_task_id = cur.lastrowid

        # Registro inicial de histórico preservando a origem do agendamento
        hist_note = "Tarefa migrada automaticamente de agendamento anterior."
        conn.execute(
            """
            INSERT INTO historico_tarefas (
                task_id, status_at_time, note, note_normalized, created_at
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                new_task_id,
                status,
                hist_note,
                normalize_text(hist_note),
                created_at,
            ),
        )

        # Lembrete vinculado correspondente ao agendamento original
        if due_date:
            last_notified_date = notified_at[:10] if (notified_at and len(str(notified_at)) >= 10) else None
            conn.execute(
                """
                INSERT INTO lembretes_tarefas (
                    task_id, reminder_type, remind_date, remind_time,
                    advance_minutes, repeat_interval, is_active, is_sent,
                    last_notified_date, notified_at, created_at, updated_at
                )
                VALUES (?, 'custom', ?, ?, 0, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    new_task_id,
                    due_date,
                    due_time or "09:00",
                    repeat_interval,
                    is_active,
                    is_sent,
                    last_notified_date,
                    notified_at,
                    created_at,
                    updated_at,
                ),
            )

    logger.info("Migrados %d agendamento(s) legado(s) para o Gerenciador de Tarefas.", len(legacy_rows))


def init_db(db_path: Optional[str] = None) -> None:
    """
    Inicializa o banco de dados criando as tabelas, índices, migrações incrementais
    e índices de busca textual de alta performance (FTS5 trigram).
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
            conn.execute(CREATE_SCHEDULES_TABLE)
            conn.execute(CREATE_TAREFAS_TABLE)
            conn.execute(CREATE_HISTORICO_TAREFAS_TABLE)
            conn.execute(CREATE_LEMBRETES_TAREFAS_TABLE)

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

            # Migração incremental: garante coluna formatting_json em diaries e notes
            cursor = conn.execute("PRAGMA table_info(diaries)")
            diary_cols = {row["name"] for row in cursor.fetchall()}
            if "formatting_json" not in diary_cols:
                conn.execute(
                    "ALTER TABLE diaries ADD COLUMN formatting_json TEXT NOT NULL DEFAULT ''"
                )

            cursor = conn.execute("PRAGMA table_info(notes)")
            note_cols = {row["name"] for row in cursor.fetchall()}
            if "formatting_json" not in note_cols:
                conn.execute(
                    "ALTER TABLE notes ADD COLUMN formatting_json TEXT NOT NULL DEFAULT ''"
                )

            # Migração incremental: garante coluna content_normalized em notes para pesquisa sem UDF Python
            if "content_normalized" not in note_cols:
                conn.execute(
                    "ALTER TABLE notes ADD COLUMN content_normalized TEXT NOT NULL DEFAULT ''"
                )

            # Backfill único para registros antigos sem content_normalized preenchido
            missing_notes = conn.execute(
                "SELECT id, content FROM notes WHERE content != '' AND content_normalized = ''"
            ).fetchall()
            if missing_notes:
                conn.executemany(
                    "UPDATE notes SET content_normalized = ? WHERE id = ?",
                    [(normalize_text(r["content"]), r["id"]) for r in missing_notes],
                )

            missing_diaries = conn.execute(
                "SELECT id, content FROM diaries WHERE content != '' AND content_normalized = ''"
            ).fetchall()
            if missing_diaries:
                conn.executemany(
                    "UPDATE diaries SET content_normalized = ? WHERE id = ?",
                    [(normalize_text(r["content"]), r["id"]) for r in missing_diaries],
                )

            # Remove índice B-Tree inútil em diaries(content_normalized) que inflava o .db e prejudicava o query planner
            conn.execute("DROP INDEX IF EXISTS idx_diaries_content_norm")

            # 2. Criação dos índices
            for statement in CREATE_DIARIES_INDEXES.strip().split(";"):
                stmt = statement.strip()
                if stmt:
                    conn.execute(stmt)

            for statement in CREATE_NOTES_INDEXES.strip().split(";"):
                stmt = statement.strip()
                if stmt:
                    conn.execute(stmt)

            for statement in CREATE_SCHEDULES_INDEXES.strip().split(";"):
                stmt = statement.strip()
                if stmt:
                    conn.execute(stmt)

            for statement in CREATE_TAREFAS_INDEXES.strip().split(";"):
                stmt = statement.strip()
                if stmt:
                    conn.execute(stmt)

            # Migração segura dos agendamentos existentes (tabela schedules) para o novo Gerenciador de Tarefas
            _migrate_legacy_schedules_to_tasks(conn)

            # 3. Criação da tabela virtual FTS5 padrão (compatibilidade) e triggers
            try:
                conn.execute(CREATE_DIARIES_FTS)
                conn.executescript(CREATE_FTS_TRIGGERS)
            except sqlite3.OperationalError as e:
                logger.warning("FTS5 não disponível ou erro ao criar tabela virtual: %s", e)

            # 4. Criação das tabelas virtuais FTS5 trigram (substrings sem acento em C nativo)
            try:
                conn.execute(CREATE_DIARIES_FTS_TRIGRAM)
                conn.executescript(CREATE_DIARIES_TRIGRAM_TRIGGERS)

                # Backfill único caso diaries_fts_trigram esteja vazia em banco já existente
                has_tri_diary = conn.execute(
                    "SELECT 1 FROM diaries_fts_trigram LIMIT 1"
                ).fetchone()
                if not has_tri_diary:
                    has_diaries = conn.execute(
                        "SELECT 1 FROM diaries WHERE content_normalized != '' LIMIT 1"
                    ).fetchone()
                    if has_diaries:
                        conn.execute(
                            """
                            INSERT INTO diaries_fts_trigram(diary_id, content_norm)
                            SELECT id, content_normalized FROM diaries WHERE content_normalized != ''
                            """
                        )

                conn.execute(CREATE_NOTES_FTS_TRIGRAM)
                conn.executescript(CREATE_NOTES_TRIGRAM_TRIGGERS)

                has_tri_note = conn.execute(
                    "SELECT 1 FROM notes_fts_trigram LIMIT 1"
                ).fetchone()
                if not has_tri_note:
                    has_notes = conn.execute(
                        "SELECT 1 FROM notes WHERE title_normalized != '' OR content_normalized != '' LIMIT 1"
                    ).fetchone()
                    if has_notes:
                        conn.execute(
                            """
                            INSERT INTO notes_fts_trigram(note_id, title_norm, content_norm)
                            SELECT id, title_normalized, content_normalized
                            FROM notes
                            WHERE title_normalized != '' OR content_normalized != ''
                            """
                        )
            except sqlite3.OperationalError as e:
                logger.warning("FTS5 trigram não disponível neste SQLite: %s", e)

        logger.info("Banco de dados inicializado com sucesso.")
    finally:
        conn.close()
