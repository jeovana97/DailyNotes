import os
import re
import csv
import shutil
import sqlite3
import logging
import datetime
from typing import List, Dict, Any, Tuple, Optional
import config
from database.connection import get_connection
from database.schema import CREATE_BACKUP_SETTINGS_TABLE
from models.diary import DiaryEntry
from utils.date_utils import format_date_br, get_current_timestamp, get_today_iso

logger = logging.getLogger(__name__)

WEEKDAY_NAMES_PT = [
    "Segunda-feira",
    "Terça-feira",
    "Quarta-feira",
    "Quinta-feira",
    "Sexta-feira",
    "Sábado",
    "Domingo",
]


class BackupService:
    DEFAULT_RETENTION_DAYS = 7

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or config.DB_PATH
        self._ensure_settings_table()

    def _ensure_settings_table(self) -> None:
        """Garante que a tabela de configuração de backup automático exista no banco."""
        try:
            conn = get_connection(self.db_path)
            try:
                with conn:
                    conn.execute(CREATE_BACKUP_SETTINGS_TABLE)
                    cursor = conn.execute("PRAGMA table_info(backup_settings)")
                    cols = {row["name"] for row in cursor.fetchall()}
                    if "retention_days" not in cols:
                        conn.execute(
                            f"ALTER TABLE backup_settings ADD COLUMN retention_days INTEGER NOT NULL DEFAULT {self.DEFAULT_RETENTION_DAYS}"
                        )
            finally:
                conn.close()
        except Exception as e:
            logger.warning("Aviso ao verificar tabela backup_settings: %s", e)

    def get_auto_backup_settings(self) -> Dict[str, Any]:
        """Retorna as configurações atuais de backup automático."""
        default_dir = os.path.join(config.DATA_DIR, "backups")
        defaults = {
            "enabled": False,
            "target_dir": default_dir,
            "schedule_date": get_today_iso(),
            "schedule_time": "18:00",
            "repeat_daily": True,
            "retention_days": self.DEFAULT_RETENTION_DAYS,
            "last_run_at": "",
            "last_backup_file": "",
            "updated_at": "",
        }
        try:
            conn = get_connection(self.db_path)
            try:
                row = conn.execute("SELECT * FROM backup_settings WHERE id = 1").fetchone()
                if not row:
                    return defaults
                row_keys = row.keys()
                retention_val = (
                    int(row["retention_days"])
                    if "retention_days" in row_keys and row["retention_days"]
                    else self.DEFAULT_RETENTION_DAYS
                )
                return {
                    "enabled": bool(row["enabled"]),
                    "target_dir": row["target_dir"] or default_dir,
                    "schedule_date": row["schedule_date"] or get_today_iso(),
                    "schedule_time": row["schedule_time"] or "18:00",
                    "repeat_daily": bool(row["repeat_daily"]),
                    "retention_days": max(1, retention_val),
                    "last_run_at": row["last_run_at"] or "",
                    "last_backup_file": row["last_backup_file"] or "",
                    "updated_at": row["updated_at"] or "",
                }
            finally:
                conn.close()
        except Exception as e:
            logger.warning("Erro ao ler configurações de backup automático: %s", e)
            return defaults

    def save_auto_backup_settings(
        self,
        enabled: bool,
        target_dir: str,
        schedule_date_iso: str,
        schedule_time: str,
        repeat_daily: bool = True,
        retention_days: int = DEFAULT_RETENTION_DAYS,
    ) -> Tuple[bool, str]:
        """Valida e salva as configurações de backup automático no banco de dados."""
        target_dir = (target_dir or "").strip()
        if not target_dir:
            return False, "Informe o local (pasta) onde o arquivo de backup será salvo."

        try:
            os.makedirs(target_dir, exist_ok=True)
        except Exception as e:
            return False, f"Não foi possível acessar ou criar a pasta de destino:\n{e}"

        # Valida horário (HH:MM)
        raw_time = (schedule_time or "").strip()
        parts = raw_time.split(":")
        if len(parts) != 2 or not parts[0].isdigit() or not parts[1].isdigit():
            return False, "Horário inválido. Informe no formato HH:MM (ex: 18:00 ou 08:30)."

        hour = int(parts[0])
        minute = int(parts[1])
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            return False, "Horário inválido. A hora deve estar entre 00 e 23 e os minutos entre 00 e 59."

        normalized_time = f"{hour:02d}:{minute:02d}"

        if not schedule_date_iso:
            schedule_date_iso = get_today_iso()

        retention_days = max(1, int(retention_days or self.DEFAULT_RETENTION_DAYS))
        now_ts = get_current_timestamp()
        try:
            conn = get_connection(self.db_path)
            try:
                with conn:
                    existing = conn.execute("SELECT id FROM backup_settings WHERE id = 1").fetchone()
                    if existing:
                        conn.execute(
                            """
                            UPDATE backup_settings
                            SET enabled = ?,
                                target_dir = ?,
                                schedule_date = ?,
                                schedule_time = ?,
                                repeat_daily = ?,
                                retention_days = ?,
                                updated_at = ?
                            WHERE id = 1
                            """,
                            (
                                1 if enabled else 0,
                                target_dir,
                                schedule_date_iso,
                                normalized_time,
                                1 if repeat_daily else 0,
                                retention_days,
                                now_ts,
                            ),
                        )
                    else:
                        conn.execute(
                            """
                            INSERT INTO backup_settings (
                                id, enabled, target_dir, schedule_date, schedule_time,
                                repeat_daily, retention_days, last_run_at, last_backup_file, updated_at
                            )
                            VALUES (1, ?, ?, ?, ?, ?, ?, '', '', ?)
                            """,
                            (
                                1 if enabled else 0,
                                target_dir,
                                schedule_date_iso,
                                normalized_time,
                                1 if repeat_daily else 0,
                                retention_days,
                                now_ts,
                            ),
                        )
            finally:
                conn.close()

            # Aplica imediatamente a política de retenção de 7 dias na pasta configurada
            self.cleanup_old_backups(target_dir=target_dir, retention_days=retention_days)

            status_txt = "ATIVADO" if enabled else "DESATIVADO"
            return (
                True,
                f"Configuração de Backup Automático ({status_txt}) salva com sucesso! "
                f"(Retenção semanal ativa: mantém apenas os últimos {retention_days} dias).",
            )
        except Exception as e:
            logger.error("Erro ao salvar configurações de backup automático: %s", e)
            return False, f"Erro ao salvar configuração: {e}"

    @staticmethod
    def _extract_backup_datetime(file_path: str) -> datetime.datetime:
        """
        Extrai a data/hora de geração de um arquivo de backup pelo padrão no nome
        (ex: backup_diario_auto_20261106_180000.db) ou pela data de modificação do arquivo.
        """
        fname = os.path.basename(file_path)
        match = re.search(r"(\d{8})(?:_(\d{6}))?", fname)
        if match:
            date_part = match.group(1)
            time_part = match.group(2) or "000000"
            try:
                return datetime.datetime.strptime(f"{date_part}_{time_part}", "%Y%m%d_%H%M%S")
            except ValueError:
                pass
        try:
            mtime = os.path.getmtime(file_path)
            return datetime.datetime.fromtimestamp(mtime)
        except Exception:
            return datetime.datetime.now()

    @staticmethod
    def _is_managed_backup_file(filename: str) -> bool:
        """Verifica se o arquivo na pasta é um backup gerenciado do sistema (.db)."""
        lower = filename.lower()
        return lower.startswith("backup_diario") and lower.endswith(".db")

    def list_managed_backups(self, target_dir: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Lista os arquivos de backup gerenciados na pasta informada (ou na pasta do backup automático),
        ordenados do mais recente para o mais antigo.
        """
        if not target_dir:
            settings = self.get_auto_backup_settings()
            target_dir = settings.get("target_dir") or ""

        if not target_dir or not os.path.isdir(target_dir):
            return []

        items: List[Dict[str, Any]] = []
        try:
            for entry in os.scandir(target_dir):
                if not entry.is_file() or not self._is_managed_backup_file(entry.name):
                    continue
                dt = self._extract_backup_datetime(entry.path)
                try:
                    size_bytes = entry.stat().st_size
                except Exception:
                    size_bytes = 0
                items.append(
                    {
                        "filename": entry.name,
                        "path": entry.path,
                        "datetime": dt,
                        "date_iso": dt.strftime("%Y-%m-%d"),
                        "weekday": WEEKDAY_NAMES_PT[dt.weekday()],
                        "size_bytes": size_bytes,
                    }
                )
        except Exception as e:
            logger.warning("Erro ao listar backups na pasta %s: %s", target_dir, e)

        items.sort(key=lambda x: (x["datetime"], x["filename"]), reverse=True)
        return items

    def cleanup_old_backups(
        self,
        target_dir: str,
        retention_days: int = DEFAULT_RETENTION_DAYS,
        now: Optional[datetime.datetime] = None,
        keep_file: Optional[str] = None,
    ) -> List[str]:
        """
        Aplica a rotação semanal / retenção de `retention_days` (padrão: 7 dias):
        1. Mantém apenas os arquivos dos últimos `retention_days` dias (ex: 7 dias).
        2. Quando um novo backup é gerado na semana seguinte (ex: 7 dias depois, no mesmo dia da semana)
           ou no mesmo dia, o arquivo antigo correspondente é removido/substituído pelo novo.
        3. Garante que no máximo `retention_days` arquivos diários permaneçam na pasta.
        Retorna a lista de caminhos dos arquivos removidos.
        """
        if not target_dir or not os.path.isdir(target_dir):
            return []

        retention_days = max(1, int(retention_days or self.DEFAULT_RETENTION_DAYS))
        ref_dt = now or datetime.datetime.now()
        ref_date = ref_dt.date()
        # Janela de 7 dias: hoje (dia 0) até 6 dias atrás = 7 dias no total.
        # Qualquer arquivo com idade >= 7 dias (ex: mesmo dia da semana passada) é substituído/removido.
        oldest_allowed_date = ref_date - datetime.timedelta(days=retention_days - 1)

        keep_norm = os.path.normcase(os.path.abspath(keep_file)) if keep_file else None
        backups = self.list_managed_backups(target_dir)

        # Garante que keep_file, se existir, seja tratado como prioridade máxima no seu dia
        if keep_norm:
            backups.sort(
                key=lambda x: (
                    1 if os.path.normcase(os.path.abspath(x["path"])) == keep_norm else 0,
                    x["datetime"],
                    x["filename"],
                ),
                reverse=True,
            )

        removed_files: List[str] = []
        seen_dates = set()
        kept_count = 0

        for item in backups:
            fpath = item["path"]
            fpath_norm = os.path.normcase(os.path.abspath(fpath))
            file_date = item["datetime"].date()

            is_explicit_keep = keep_norm is not None and fpath_norm == keep_norm

            should_delete = False
            if not is_explicit_keep:
                # 1. Expirado pela janela de 7 dias (idade >= retention_days, ou seja, da semana passada ou anterior)
                if file_date < oldest_allowed_date:
                    should_delete = True
                # 2. Já existe um backup mais recente para esta mesma data (substitui backup anterior do mesmo dia)
                elif file_date in seen_dates:
                    should_delete = True
                # 3. Já atingiu o limite máximo de 7 arquivos diários mantidos
                elif kept_count >= retention_days:
                    should_delete = True

            if should_delete:
                try:
                    os.remove(fpath)
                    removed_files.append(fpath)
                    logger.info("Backup antigo removido pela rotação de %d dias: %s", retention_days, fpath)
                except Exception as e:
                    logger.warning("Não foi possível remover backup antigo %s: %s", fpath, e)
            else:
                seen_dates.add(file_date)
                kept_count += 1

        return removed_files

    def check_and_run_due_auto_backup(
        self, now: Optional[datetime.datetime] = None
    ) -> Tuple[bool, Optional[str]]:
        """
        Verifica se há um backup automático agendado pendente para execução no momento atual.
        Se estiver no horário/data programados e ainda não tiver sido executado para o ciclo,
        gera o arquivo .db automaticamente na pasta configurada e aplica a retenção de 7 dias,
        substituindo os arquivos da semana anterior.
        Retorna (executou_backup, caminho_do_arquivo).
        """
        settings = self.get_auto_backup_settings()
        if not settings.get("enabled"):
            return False, None

        target_dir = (settings.get("target_dir") or "").strip()
        if not target_dir:
            return False, None

        now_dt = now or datetime.datetime.now()
        retention_days = int(settings.get("retention_days") or self.DEFAULT_RETENTION_DAYS)

        # Mesmo antes do horário, garante limpeza de arquivos vencidos (> 7 dias) se a pasta existir
        if os.path.isdir(target_dir):
            self.cleanup_old_backups(
                target_dir=target_dir,
                retention_days=retention_days,
                now=now_dt,
            )

        today_iso = now_dt.strftime("%Y-%m-%d")
        now_ts = now_dt.strftime("%Y-%m-%d %H:%M:%S")

        sched_date = settings.get("schedule_date") or today_iso
        sched_time = settings.get("schedule_time") or "18:00"
        repeat_daily = bool(settings.get("repeat_daily"))
        last_run_at = settings.get("last_run_at") or ""

        if repeat_daily:
            # Se a data inicial agendada for no futuro, aguarda chegar na data
            if today_iso < sched_date:
                return False, None
            due_timestamp = f"{today_iso} {sched_time}:00"
        else:
            # Executa na data e horário específicos configurados
            due_timestamp = f"{sched_date} {sched_time}:00"

        if now_ts < due_timestamp:
            return False, None

        if last_run_at and last_run_at >= due_timestamp:
            return False, None

        filename = f"backup_diario_auto_{now_dt.strftime('%Y%m%d_%H%M%S')}.db"
        dest_file_path = os.path.join(target_dir, filename)

        ok, _ = self.create_database_backup(dest_file_path)
        if not ok:
            return False, None

        # Aplica rotação semanal (mantém apenas 7 dias e substitui o da semana anterior)
        self.cleanup_old_backups(
            target_dir=target_dir,
            retention_days=retention_days,
            now=now_dt,
            keep_file=dest_file_path,
        )

        try:
            conn = get_connection(self.db_path)
            try:
                with conn:
                    conn.execute(
                        """
                        UPDATE backup_settings
                        SET last_run_at = ?, last_backup_file = ?
                        WHERE id = 1
                        """,
                        (now_ts, dest_file_path),
                    )
            finally:
                conn.close()
        except Exception as e:
            logger.warning("Erro ao registrar execução do backup automático: %s", e)

        logger.info("Backup automático gerado com sucesso em: %s", dest_file_path)
        return True, dest_file_path

    def create_database_backup(self, destination_file_path: str) -> Tuple[bool, str]:
        """
        Gera uma cópia de segurança (backup) consistente do banco de dados SQLite
        utilizando a API nativa de backup do SQLite (conn.backup), evitando inconsistências
        mesmo que haja leituras ou escritas simultâneas.
        """
        if not destination_file_path:
            return False, "Caminho de destino do backup não informado."

        try:
            os.makedirs(os.path.dirname(os.path.abspath(destination_file_path)), exist_ok=True)

            source_conn = get_connection(self.db_path)
            dest_conn = sqlite3.connect(destination_file_path)

            try:
                # Realiza o backup atômico
                source_conn.backup(dest_conn)
            finally:
                dest_conn.close()
                source_conn.close()

            # Se for um arquivo gerenciado (backup_diario*.db), aplica a retenção de 7 dias na pasta
            dest_abs = os.path.abspath(destination_file_path)
            if self._is_managed_backup_file(os.path.basename(dest_abs)):
                settings = self.get_auto_backup_settings()
                retention_days = int(settings.get("retention_days") or self.DEFAULT_RETENTION_DAYS)
                file_dt = self._extract_backup_datetime(dest_abs)
                self.cleanup_old_backups(
                    target_dir=os.path.dirname(dest_abs),
                    retention_days=retention_days,
                    now=file_dt,
                    keep_file=dest_abs,
                )

            return True, f"Backup realizado com sucesso em:\n{destination_file_path}"
        except Exception as e:
            logger.error("Erro ao criar backup do banco de dados: %s", e)
            return False, f"Falha ao realizar backup: {str(e)}"

    def restore_database_backup(self, backup_file_path: str) -> Tuple[bool, str]:
        """
        Restaura o banco de dados a partir de um arquivo de backup.
        Passos de segurança:
        1. Valida se o arquivo de backup é um banco SQLite válido e contém as tabelas necessárias.
        2. Cria uma cópia de segurança do banco atual antes de sobrescrever.
        3. Realiza a restauração segura via backup API ou cópia segura.
        """
        if not os.path.isfile(backup_file_path):
            return False, "Arquivo de backup não encontrado."

        # 1. Validação do arquivo de backup
        try:
            test_conn = sqlite3.connect(backup_file_path)
            cursor = test_conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name IN ('users', 'diaries')")
            tables = [row[0] for row in cursor.fetchall()]
            test_conn.close()

            if "users" not in tables or "diaries" not in tables:
                return False, "O arquivo selecionado não é um backup válido do Diário de Anotações (tabelas ausentes)."
        except Exception as e:
            return False, f"Arquivo corrompido ou formato SQLite inválido: {str(e)}"

        # 2. Cópia preventiva de segurança do banco atual
        if os.path.exists(self.db_path):
            safety_copy = f"{self.db_path}.safety_{int(sqlite3.sqlite_version_info[0])}.bak"
            try:
                shutil.copy2(self.db_path, safety_copy)
            except Exception as e:
                logger.warning("Não foi possível criar cópia preventiva de segurança: %s", e)

        # 3. Restauração atômica
        try:
            backup_conn = sqlite3.connect(backup_file_path)
            target_conn = get_connection(self.db_path)
            try:
                backup_conn.backup(target_conn)
            finally:
                target_conn.close()
                backup_conn.close()

            from database.migrations import init_db
            init_db(self.db_path)

            return True, "Banco de dados restaurado com sucesso!"
        except Exception as e:
            logger.error("Erro durante a restauração do banco: %s", e)
            return False, f"Erro ao restaurar banco de dados: {str(e)}"

    def export_entry_to_txt(self, entry: DiaryEntry, target_file_path: str) -> Tuple[bool, str]:
        """
        Exporta uma única anotação do diário para um arquivo TXT formatado em UTF-8.
        """
        try:
            os.makedirs(os.path.dirname(os.path.abspath(target_file_path)), exist_ok=True)
            data_formatada = format_date_br(entry.entry_date)
            autor = entry.author_name or "Usuário"

            header = (
                f"====================================================\n"
                f"DIÁRIO DE ANOTAÇÕES - {data_formatada}\n"
                f"Autor: {autor}\n"
                f"Última alteração: {entry.updated_at}\n"
                f"====================================================\n\n"
            )

            with open(target_file_path, "w", encoding="utf-8") as f:
                f.write(header)
                f.write(entry.content)

            return True, f"Anotação exportada com sucesso para:\n{target_file_path}"
        except Exception as e:
            return False, f"Erro ao exportar anotação: {str(e)}"

    def export_entries_to_folder(self, entries: List[DiaryEntry], target_dir: str) -> Tuple[int, int, str]:
        """
        Exporta múltiplas anotações para uma pasta, nomeando cada arquivo como 'DD MM AAAA.txt'.
        Retorna (exportados, erros, mensagem).
        """
        if not os.path.isdir(target_dir):
            try:
                os.makedirs(target_dir, exist_ok=True)
            except Exception as e:
                return 0, len(entries), f"Pasta de destino inválida: {str(e)}"

        exported = 0
        errors = 0

        for entry in entries:
            # Formato do nome: DD MM AAAA.txt
            parts = entry.entry_date.split("-")
            if len(parts) == 3:
                filename = f"{parts[2]} {parts[1]} {parts[0]}.txt"
            else:
                filename = f"{entry.entry_date}.txt"

            target_path = os.path.join(target_dir, filename)
            try:
                with open(target_path, "w", encoding="utf-8") as f:
                    f.write(entry.content)
                exported += 1
            except Exception:
                errors += 1

        return exported, errors, f"{exported} anotações exportadas com sucesso ({errors} erros)."

    def export_search_results_to_csv(self, search_results: List[Dict[str, Any]], target_csv_path: str) -> Tuple[bool, str]:
        """
        Exporta a lista de resultados da pesquisa avançada para um arquivo CSV formatado,
        utilizando UTF-8 com BOM (utf-8-sig) para compatibilidade perfeita com o Microsoft Excel.
        """
        try:
            os.makedirs(os.path.dirname(os.path.abspath(target_csv_path)), exist_ok=True)

            with open(target_csv_path, "w", newline="", encoding="utf-8-sig") as csvfile:
                fieldnames = ["Data", "Usuário", "Nome Completo", "Trecho Encontrado", "Última Alteração", "Conteúdo Completo"]
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames, delimiter=";")
                writer.writeheader()

                for item in search_results:
                    writer.writerow({
                        "Data": format_date_br(item.get("entry_date", "")),
                        "Usuário": item.get("username", ""),
                        "Nome Completo": item.get("full_name", ""),
                        "Trecho Encontrado": item.get("snippet", ""),
                        "Última Alteração": item.get("updated_at", ""),
                        "Conteúdo Completo": item.get("content", "").replace("\r\n", " ").replace("\n", " "),
                    })

            return True, f"Resultados exportados para CSV com sucesso em:\n{target_csv_path}"
        except Exception as e:
            return False, f"Erro ao exportar CSV: {str(e)}"
