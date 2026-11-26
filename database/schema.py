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
    formatting_json TEXT NOT NULL DEFAULT '', -- Formatação rica (fonte, tamanho, negrito, sublinhado, riscado)
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

CREATE TRIGGER IF NOT EXISTS trg_diaries_au AFTER UPDATE OF content ON diaries
BEGIN
    DELETE FROM diaries_fts WHERE diary_id = old.id;
    INSERT INTO diaries_fts(diary_id, content) VALUES (new.id, new.content);
END;
"""

# Tabelas virtuais FTS5 trigram (indexam substrings sem acento em C nativo para pesquisa instantânea)
CREATE_DIARIES_FTS_TRIGRAM = """
CREATE VIRTUAL TABLE IF NOT EXISTS diaries_fts_trigram USING fts5(
    diary_id UNINDEXED,
    content_norm,
    tokenize='trigram'
);
"""

CREATE_DIARIES_TRIGRAM_TRIGGERS = """
CREATE TRIGGER IF NOT EXISTS trg_diaries_tri_ai AFTER INSERT ON diaries
BEGIN
    INSERT INTO diaries_fts_trigram(diary_id, content_norm)
    VALUES (new.id, new.content_normalized);
END;

CREATE TRIGGER IF NOT EXISTS trg_diaries_tri_ad AFTER DELETE ON diaries
BEGIN
    DELETE FROM diaries_fts_trigram WHERE diary_id = old.id;
END;

CREATE TRIGGER IF NOT EXISTS trg_diaries_tri_au AFTER UPDATE OF content_normalized ON diaries
BEGIN
    DELETE FROM diaries_fts_trigram WHERE diary_id = old.id;
    INSERT INTO diaries_fts_trigram(diary_id, content_norm)
    VALUES (new.id, new.content_normalized);
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
    content_normalized TEXT NOT NULL DEFAULT '', -- Sem acentos e em minúsculas para pesquisa rápida
    formatting_json TEXT NOT NULL DEFAULT '', -- Formatação rica (fonte, tamanho, negrito, itálico, sublinhado, riscado)
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
CREATE INDEX IF NOT EXISTS idx_notes_user_updated ON notes(user_id, updated_at);
CREATE INDEX IF NOT EXISTS idx_notes_updated ON notes(updated_at);
"""

CREATE_NOTES_FTS_TRIGRAM = """
CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts_trigram USING fts5(
    note_id UNINDEXED,
    title_norm,
    content_norm,
    tokenize='trigram'
);
"""

CREATE_NOTES_TRIGRAM_TRIGGERS = """
CREATE TRIGGER IF NOT EXISTS trg_notes_tri_ai AFTER INSERT ON notes
BEGIN
    INSERT INTO notes_fts_trigram(note_id, title_norm, content_norm)
    VALUES (new.id, new.title_normalized, new.content_normalized);
END;

CREATE TRIGGER IF NOT EXISTS trg_notes_tri_ad AFTER DELETE ON notes
BEGIN
    DELETE FROM notes_fts_trigram WHERE note_id = old.id;
END;

CREATE TRIGGER IF NOT EXISTS trg_notes_tri_au AFTER UPDATE OF title_normalized, content_normalized ON notes
BEGIN
    DELETE FROM notes_fts_trigram WHERE note_id = old.id;
    INSERT INTO notes_fts_trigram(note_id, title_norm, content_norm)
    VALUES (new.id, new.title_normalized, new.content_normalized);
END;
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
    entry_date TEXT NOT NULL DEFAULT '',
    target_type TEXT NOT NULL DEFAULT 'note',
    folder_id INTEGER DEFAULT NULL,
    folder_name TEXT NOT NULL DEFAULT '',
    note_id INTEGER DEFAULT NULL,
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
    retention_days INTEGER NOT NULL DEFAULT 7, -- Dias de retenção (ciclo semanal de 7 dias)
    last_run_at TEXT NOT NULL DEFAULT '',
    last_backup_file TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT ''
);
"""

# Tabela para Agendamentos e Lembretes com Notificação do Windows
CREATE_SCHEDULES_TABLE = """
CREATE TABLE IF NOT EXISTS schedules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    title_normalized TEXT NOT NULL DEFAULT '',
    content TEXT NOT NULL DEFAULT '',
    schedule_date TEXT NOT NULL, -- Formato ISO: YYYY-MM-DD
    schedule_time TEXT NOT NULL, -- Formato: HH:MM
    status TEXT NOT NULL DEFAULT 'pendente', -- 'pendente', 'notificado', 'concluido', 'cancelado'
    priority TEXT NOT NULL DEFAULT 'normal', -- 'baixa', 'normal', 'alta', 'urgente'
    repeat_interval TEXT NOT NULL DEFAULT 'none', -- 'none', 'daily', 'weekly', 'monthly'
    notified_at TEXT DEFAULT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);
"""

CREATE_SCHEDULES_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_schedules_user_status ON schedules(user_id, status);
CREATE INDEX IF NOT EXISTS idx_schedules_datetime ON schedules(schedule_date, schedule_time);
CREATE INDEX IF NOT EXISTS idx_schedules_user_date ON schedules(user_id, schedule_date);
CREATE INDEX IF NOT EXISTS idx_schedules_title_norm ON schedules(user_id, title_normalized);
"""

# ==============================================================================
# GERENCIADOR DE TAREFAS (Evolução do menu Agendamento)
# ==============================================================================

CREATE_TAREFAS_TABLE = """
CREATE TABLE IF NOT EXISTS tarefas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    title_normalized TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    description_normalized TEXT NOT NULL DEFAULT '',
    start_date TEXT NOT NULL DEFAULT '', -- YYYY-MM-DD
    due_date TEXT NOT NULL DEFAULT '', -- YYYY-MM-DD (data prevista para conclusão)
    due_time TEXT NOT NULL DEFAULT '', -- HH:MM (opcional)
    priority TEXT NOT NULL DEFAULT 'media', -- 'baixa', 'media', 'alta', 'urgente'
    status TEXT NOT NULL DEFAULT 'pendente', -- 'pendente', 'em_andamento', 'concluida', 'cancelada'
    category TEXT NOT NULL DEFAULT '',
    category_normalized TEXT NOT NULL DEFAULT '',
    reminder_enabled INTEGER NOT NULL DEFAULT 0,
    completed_at TEXT DEFAULT NULL, -- YYYY-MM-DD HH:MM:SS
    legacy_schedule_id INTEGER DEFAULT NULL, -- Referência de migração segura de schedules
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);
"""

CREATE_HISTORICO_TAREFAS_TABLE = """
CREATE TABLE IF NOT EXISTS historico_tarefas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL,
    status_at_time TEXT NOT NULL DEFAULT 'pendente',
    note TEXT NOT NULL,
    note_normalized TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL, -- YYYY-MM-DD HH:MM:SS
    FOREIGN KEY(task_id) REFERENCES tarefas(id) ON DELETE CASCADE
);
"""

CREATE_LEMBRETES_TAREFAS_TABLE = """
CREATE TABLE IF NOT EXISTS lembretes_tarefas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL,
    reminder_type TEXT NOT NULL DEFAULT 'custom', -- 'custom', 'due_day', 'advance', 'overdue'
    remind_date TEXT NOT NULL DEFAULT '', -- YYYY-MM-DD (usado em 'custom')
    remind_time TEXT NOT NULL DEFAULT '09:00', -- HH:MM
    advance_minutes INTEGER NOT NULL DEFAULT 0, -- Minutos de antecedência (usado em 'advance')
    repeat_interval TEXT NOT NULL DEFAULT 'none', -- 'none', 'daily', 'weekly', 'monthly'
    is_active INTEGER NOT NULL DEFAULT 1,
    is_sent INTEGER NOT NULL DEFAULT 0,
    last_notified_date TEXT DEFAULT NULL, -- YYYY-MM-DD (controle anti-repetição diária)
    notified_at TEXT DEFAULT NULL, -- YYYY-MM-DD HH:MM:SS
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(task_id) REFERENCES tarefas(id) ON DELETE CASCADE
);
"""

CREATE_TAREFAS_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_tarefas_user_status ON tarefas(user_id, status);
CREATE INDEX IF NOT EXISTS idx_tarefas_user_due ON tarefas(user_id, due_date, due_time);
CREATE INDEX IF NOT EXISTS idx_tarefas_user_priority ON tarefas(user_id, priority);
CREATE INDEX IF NOT EXISTS idx_tarefas_user_updated ON tarefas(user_id, updated_at);
CREATE INDEX IF NOT EXISTS idx_tarefas_user_title_norm ON tarefas(user_id, title_normalized);
CREATE UNIQUE INDEX IF NOT EXISTS idx_tarefas_legacy_schedule ON tarefas(legacy_schedule_id) WHERE legacy_schedule_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_historico_tarefas_task ON historico_tarefas(task_id, created_at, id);
CREATE INDEX IF NOT EXISTS idx_lembretes_tarefas_task ON lembretes_tarefas(task_id);
CREATE INDEX IF NOT EXISTS idx_lembretes_tarefas_active ON lembretes_tarefas(is_active, is_sent, reminder_type);
"""
