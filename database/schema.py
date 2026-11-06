# Definição do esquema do banco de dados SQLite

CREATE_USERS_TABLE = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL COLLATE NOCASE,
    full_name TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'user', -- 'admin' ou 'user'
    can_view_all_diaries INTEGER NOT NULL DEFAULT 0, -- 1 = autorizado a ver diários de outros usuários
    is_active INTEGER NOT NULL DEFAULT 1, -- 1 = ativo, 0 = inativo
    theme_preference TEXT NOT NULL DEFAULT 'dark', -- 'dark' ou 'light'
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""

CREATE_DIARIES_TABLE = """
CREATE TABLE IF NOT EXISTS diaries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    entry_date TEXT NOT NULL, -- Formato ISO: YYYY-MM-DD
    content TEXT NOT NULL DEFAULT '',
    content_normalized TEXT NOT NULL DEFAULT '', -- Sem acentos e em minúsculas
    created_at TEXT NOT NULL, -- YYYY-MM-DD HH:MM:SS
    updated_at TEXT NOT NULL, -- YYYY-MM-DD HH:MM:SS
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT uq_user_entry_date UNIQUE(user_id, entry_date)
);
"""

CREATE_DIARIES_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_diaries_user_date ON diaries(user_id, entry_date);
CREATE INDEX IF NOT EXISTS idx_diaries_date ON diaries(entry_date);
CREATE INDEX IF NOT EXISTS idx_diaries_user ON diaries(user_id);
CREATE INDEX IF NOT EXISTS idx_diaries_content_norm ON diaries(content_normalized);
"""

# Tabela virtual FTS5 para pesquisa textual de altíssima performance
CREATE_DIARIES_FTS = """
CREATE VIRTUAL TABLE IF NOT EXISTS diaries_fts USING fts5(
    diary_id UNINDEXED,
    content,
    tokenize='unicode61 remove_diacritics 2'
);
"""

# Triggers para manter o FTS5 sincronizado automaticamente com a tabela diaries
CREATE_FTS_TRIGGERS = """
CREATE TRIGGER IF NOT EXISTS trg_diaries_ai AFTER INSERT ON diaries
BEGIN
    INSERT INTO diaries_fts(diary_id, content) VALUES (new.id, new.content);
END;

CREATE TRIGGER IF NOT EXISTS trg_diaries_ad AFTER DELETE ON diaries
BEGIN
    DELETE FROM diaries_fts WHERE diary_id = old.id;
END;

CREATE TRIGGER IF NOT EXISTS trg_diaries_au AFTER UPDATE ON diaries
BEGIN
    DELETE FROM diaries_fts WHERE diary_id = old.id;
    INSERT INTO diaries_fts(diary_id, content) VALUES (new.id, new.content);
END;
"""

# Tabelas para o menu de Notas Rápidas / Notas Organizáveis em Pastas e Subpastas
# (Independentes de datas do diário e isoladas da Pesquisa Avançada)
CREATE_NOTE_FOLDERS_TABLE = """
CREATE TABLE IF NOT EXISTS note_folders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    parent_id INTEGER DEFAULT NULL,
    name TEXT NOT NULL,
    name_normalized TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY(parent_id) REFERENCES note_folders(id) ON DELETE CASCADE
);
"""

CREATE_NOTES_TABLE = """
CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    folder_id INTEGER DEFAULT NULL,
    title TEXT NOT NULL,
    title_normalized TEXT NOT NULL DEFAULT '',
    content TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY(folder_id) REFERENCES note_folders(id) ON DELETE CASCADE
);
"""

CREATE_NOTES_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_note_folders_user ON note_folders(user_id);
CREATE INDEX IF NOT EXISTS idx_note_folders_parent ON note_folders(parent_id);
CREATE INDEX IF NOT EXISTS idx_notes_user ON notes(user_id);
CREATE INDEX IF NOT EXISTS idx_notes_folder ON notes(folder_id);
CREATE INDEX IF NOT EXISTS idx_notes_title_norm ON notes(user_id, title_normalized);
"""

# Tabela para persistência do Dicionário Personalizado do Corretor Ortográfico
CREATE_CUSTOM_DICTIONARY_TABLE = """
CREATE TABLE IF NOT EXISTS custom_dictionary (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    word TEXT UNIQUE NOT NULL COLLATE NOCASE,
    created_at TEXT NOT NULL
);
"""

# Tabela para registrar histórico de arquivos TXT importados por usuário
CREATE_IMPORT_HISTORY_TABLE = """
CREATE TABLE IF NOT EXISTS import_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    filename TEXT NOT NULL,
    file_path TEXT NOT NULL DEFAULT '',
    entry_date TEXT NOT NULL,
    imported_at TEXT NOT NULL,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);
"""

# Tabela para configuração de Backup Automático Agendado
CREATE_BACKUP_SETTINGS_TABLE = """
CREATE TABLE IF NOT EXISTS backup_settings (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    enabled INTEGER NOT NULL DEFAULT 0,
    target_dir TEXT NOT NULL DEFAULT '',
    schedule_date TEXT NOT NULL DEFAULT '', -- YYYY-MM-DD
    schedule_time TEXT NOT NULL DEFAULT '18:00', -- HH:MM
    repeat_daily INTEGER NOT NULL DEFAULT 1, -- 1 = repetir diariamente, 0 = apenas na data
    last_run_at TEXT NOT NULL DEFAULT '',
    last_backup_file TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT ''
);
"""
