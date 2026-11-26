import logging
import sqlite3
from typing import Optional, List, Dict, Any
from database.connection import get_connection
from models.user import User
from utils.text_utils import normalize_text, extract_snippet
from utils.date_utils import is_valid_iso_date

logger = logging.getLogger(__name__)


def _escape_fts_trigram(norm_query: str) -> str:
    """Escapa a string normalizada como frase literal para consulta FTS5 trigram."""
    return '"' + norm_query.replace('"', '""') + '"'


class SearchService:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path
        self._fts_tables_cache: Optional[Dict[str, bool]] = None

    def _has_fts_table(self, conn: sqlite3.Connection, table_name: str) -> bool:
        """Verifica (com cache em memória) se a tabela FTS5 trigram está disponível no banco."""
        if self._fts_tables_cache is None:
            try:
                rows = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('diaries_fts_trigram', 'notes_fts_trigram')"
                ).fetchall()
                existing = {r["name"] for r in rows}
                self._fts_tables_cache = {
                    "diaries_fts_trigram": "diaries_fts_trigram" in existing,
                    "notes_fts_trigram": "notes_fts_trigram" in existing,
                }
            except Exception:
                self._fts_tables_cache = {
                    "diaries_fts_trigram": False,
                    "notes_fts_trigram": False,
                }
        return self._fts_tables_cache.get(table_name, False)

    def _query_diaries_rows(
        self,
        conn: sqlite3.Connection,
        requester: User,
        norm_query: str = "",
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        exact_date: Optional[str] = None,
        target_user_id: Optional[int] = None,
        order_desc: bool = True,
        limit: int = 200,
    ) -> List[sqlite3.Row]:
        """Executa a consulta SQL otimizada em C nativo (FTS5 trigram + instr em content_normalized)."""
        cursor = conn.cursor()

        base_conditions = ["d.content_normalized != ''"]
        base_params: List[Any] = []

        # 1. Controle rigoroso de acesso do usuário
        if not requester.can_view_other_diaries:
            base_conditions.append("d.user_id = ?")
            base_params.append(requester.id)
        else:
            if target_user_id is not None and target_user_id > 0:
                base_conditions.append("d.user_id = ?")
                base_params.append(target_user_id)

        # 2. Filtro por data exata ou período
        if exact_date and is_valid_iso_date(exact_date):
            base_conditions.append("d.entry_date = ?")
            base_params.append(exact_date)
        else:
            if start_date and is_valid_iso_date(start_date):
                base_conditions.append("d.entry_date >= ?")
                base_params.append(start_date)
            if end_date and is_valid_iso_date(end_date):
                base_conditions.append("d.entry_date <= ?")
                base_params.append(end_date)

        order_direction = "DESC" if order_desc else "ASC"

        def _build_and_run(use_trigram: bool) -> List[sqlite3.Row]:
            conditions = list(base_conditions)
            params = list(base_params)
            if norm_query:
                if use_trigram:
                    conditions.append(
                        "d.id IN (SELECT diary_id FROM diaries_fts_trigram WHERE diaries_fts_trigram MATCH ?)"
                    )
                    params.append(_escape_fts_trigram(norm_query))
                # Confirma substring exata em C nativo (sem UDF Python)
                conditions.append("instr(+d.content_normalized, ?) > 0")
                params.append(norm_query)

            where_clause = " AND ".join(conditions)
            sql = f"""
                SELECT
                    d.id,
                    d.user_id,
                    d.entry_date,
                    d.content,
                    d.content_normalized,
                    d.created_at,
                    d.updated_at,
                    u.full_name,
                    u.username
                FROM diaries d
                JOIN users u ON d.user_id = u.id
                WHERE {where_clause}
                ORDER BY d.entry_date {order_direction}
                LIMIT ?
            """
            params.append(limit)
            cursor.execute(sql, tuple(params))
            return cursor.fetchall()

        use_trigram = bool(
            norm_query
            and len(norm_query) >= 3
            and self._has_fts_table(conn, "diaries_fts_trigram")
        )
        if use_trigram:
            try:
                return _build_and_run(use_trigram=True)
            except sqlite3.OperationalError as e:
                logger.debug("Fallback de diaries_fts_trigram para instr(): %s", e)

        return _build_and_run(use_trigram=False)

    def search_diaries(
        self,
        requester: User,
        query: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        exact_date: Optional[str] = None,
        target_user_id: Optional[int] = None,
        order_desc: bool = True,
        limit: int = 200,
    ) -> List[Dict[str, Any]]:
        """
        Executa pesquisa avançada de anotações do Diário com filtros múltiplos:
        - Termo ou expressão (insensível a maiúsculas e sem diferenciar acentuação)
        - Data inicial e final / Data exata
        - Filtro de usuário (respeitando estritamente as permissões)
        - Ordenação cronológica (decrescente ou crescente)
        """
        clean_query = query.strip() if query else ""
        norm_query = normalize_text(clean_query) if clean_query else ""

        conn = get_connection(self.db_path)
        try:
            rows = self._query_diaries_rows(
                conn=conn,
                requester=requester,
                norm_query=norm_query,
                start_date=start_date,
                end_date=end_date,
                exact_date=exact_date,
                target_user_id=target_user_id,
                order_desc=order_desc,
                limit=limit,
            )
            return [self._row_to_diary_item(row, clean_query, norm_query) for row in rows]
        finally:
            conn.close()

    @staticmethod
    def _row_to_diary_item(
        row: sqlite3.Row,
        clean_query: str,
        norm_query: str,
        include_snippet: bool = True,
    ) -> Dict[str, Any]:
        content = row["content"] or ""
        norm_content = row["content_normalized"] or ""
        snippet = (
            extract_snippet(content, clean_query, norm_content=norm_content, norm_query=norm_query)
            if include_snippet
            else ""
        )
        return {
            "source_type": "diary",
            "id": row["id"],
            "user_id": row["user_id"],
            "entry_date": row["entry_date"],
            "content": content,
            "_norm_content": norm_content,
            "snippet": snippet,
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "full_name": row["full_name"],
            "username": row["username"],
        }

    def _build_folder_path_map(self, conn: sqlite3.Connection, user_id: int) -> Dict[int, str]:
        """Constrói o mapa {folder_id: 'Pasta Pai / Subpasta'} para o usuário informado."""
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, name, parent_id FROM note_folders WHERE user_id = ?",
            (user_id,),
        )
        folders = {row["id"]: (row["name"], row["parent_id"]) for row in cursor.fetchall()}
        path_map: Dict[int, str] = {}

        def _resolve(fid: int, visited: set) -> str:
            if fid in path_map:
                return path_map[fid]
            if fid not in folders or fid in visited:
                return ""
            visited.add(fid)
            name, parent_id = folders[fid]
            if parent_id is not None and parent_id in folders:
                parent_path = _resolve(parent_id, visited)
                full = f"{parent_path} / {name}" if parent_path else name
            else:
                full = name
            path_map[fid] = full
            return full

        for fid in folders:
            _resolve(fid, set())
        return path_map

    def _query_notes_rows(
        self,
        conn: sqlite3.Connection,
        requester: User,
        norm_query: str = "",
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        exact_date: Optional[str] = None,
        target_user_id: Optional[int] = None,
        order_desc: bool = True,
        limit: int = 200,
    ) -> List[sqlite3.Row]:
        """Executa a consulta SQL otimizada em C nativo para Notas & Pastas."""
        cursor = conn.cursor()

        base_conditions = ["(n.title_normalized != '' OR n.content_normalized != '')"]
        base_params: List[Any] = []

        if not requester.can_view_other_diaries:
            base_conditions.append("n.user_id = ?")
            base_params.append(requester.id)
        else:
            if target_user_id is not None and target_user_id > 0:
                base_conditions.append("n.user_id = ?")
                base_params.append(target_user_id)

        # Comparações diretas de intervalo em updated_at permitem uso de índice B-Tree
        if exact_date and is_valid_iso_date(exact_date):
            base_conditions.append("n.updated_at >= ? AND n.updated_at <= ?")
            base_params.extend([exact_date, f"{exact_date} 23:59:59"])
        else:
            if start_date and is_valid_iso_date(start_date):
                base_conditions.append("n.updated_at >= ?")
                base_params.append(start_date)
            if end_date and is_valid_iso_date(end_date):
                base_conditions.append("n.updated_at <= ?")
                base_params.append(f"{end_date} 23:59:59")

        order_direction = "DESC" if order_desc else "ASC"

        def _build_and_run(use_trigram: bool) -> List[sqlite3.Row]:
            conditions = list(base_conditions)
            params = list(base_params)
            if norm_query:
                if use_trigram:
                    conditions.append(
                        "n.id IN (SELECT note_id FROM notes_fts_trigram WHERE notes_fts_trigram MATCH ?)"
                    )
                    params.append(_escape_fts_trigram(norm_query))
                conditions.append(
                    "(instr(+n.title_normalized, ?) > 0 OR instr(+n.content_normalized, ?) > 0)"
                )
                params.extend([norm_query, norm_query])

            where_clause = " AND ".join(conditions)
            sql = f"""
                SELECT
                    n.id,
                    n.user_id,
                    n.folder_id,
                    n.title,
                    n.content,
                    n.content_normalized,
                    n.created_at,
                    n.updated_at,
                    u.full_name,
                    u.username
                FROM notes n
                JOIN users u ON n.user_id = u.id
                WHERE {where_clause}
                ORDER BY n.updated_at {order_direction}, n.id {order_direction}
                LIMIT ?
            """
            params.append(limit)
            cursor.execute(sql, tuple(params))
            return cursor.fetchall()

        use_trigram = bool(
            norm_query
            and len(norm_query) >= 3
            and self._has_fts_table(conn, "notes_fts_trigram")
        )
        if use_trigram:
            try:
                return _build_and_run(use_trigram=True)
            except sqlite3.OperationalError as e:
                logger.debug("Fallback de notes_fts_trigram para instr(): %s", e)

        return _build_and_run(use_trigram=False)

    def _row_to_note_item(
        self,
        conn: sqlite3.Connection,
        row: sqlite3.Row,
        path_cache: Dict[int, Dict[int, str]],
        clean_query: str,
        norm_query: str,
        include_snippet: bool = True,
    ) -> Dict[str, Any]:
        uid = row["user_id"]
        if uid not in path_cache:
            path_cache[uid] = self._build_folder_path_map(conn, uid)

        fid = row["folder_id"]
        folder_path = path_cache[uid].get(fid, "Raiz (Sem pasta)") if fid is not None else "Raiz (Sem pasta)"
        content = row["content"] or ""
        norm_content = row["content_normalized"] or ""
        if include_snippet:
            snippet = (
                extract_snippet(content, clean_query, norm_content=norm_content, norm_query=norm_query)
                if content.strip()
                else "(Arquivo/Nota sem conteúdo)"
            )
        else:
            snippet = ""

        return {
            "source_type": "note",
            "id": row["id"],
            "note_id": row["id"],
            "folder_id": fid,
            "folder_path": folder_path,
            "title": row["title"],
            "user_id": uid,
            "entry_date": (row["updated_at"] or "")[:10],
            "content": content,
            "_norm_content": norm_content,
            "snippet": snippet,
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "full_name": row["full_name"],
            "username": row["username"],
        }

    def search_notes(
        self,
        requester: User,
        query: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        exact_date: Optional[str] = None,
        target_user_id: Optional[int] = None,
        order_desc: bool = True,
        limit: int = 200,
    ) -> List[Dict[str, Any]]:
        """
        Pesquisa notas e arquivos organizados em pastas (tabelas notes e note_folders),
        buscando tanto no título quanto no conteúdo (insensível a maiúsculas e acentos).
        """
        clean_query = query.strip() if query else ""
        norm_query = normalize_text(clean_query) if clean_query else ""

        conn = get_connection(self.db_path)
        try:
            rows = self._query_notes_rows(
                conn=conn,
                requester=requester,
                norm_query=norm_query,
                start_date=start_date,
                end_date=end_date,
                exact_date=exact_date,
                target_user_id=target_user_id,
                order_desc=order_desc,
                limit=limit,
            )
            path_cache: Dict[int, Dict[int, str]] = {}
            return [
                self._row_to_note_item(conn, row, path_cache, clean_query, norm_query)
                for row in rows
            ]
        finally:
            conn.close()

    def search_all(
        self,
        requester: User,
        query: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        exact_date: Optional[str] = None,
        target_user_id: Optional[int] = None,
        order_desc: bool = True,
        scope: str = "all",
        limit: int = 200,
    ) -> List[Dict[str, Any]]:
        """
        Pesquisa unificada em conexão única conforme o escopo escolhido:
        - 'diaries': apenas anotações do Diário
        - 'notes': apenas notas e arquivos em Pastas
        - 'all': Diário + Pastas e Arquivos (extrai snippets apenas dos itens finais)
        """
        if scope == "diaries":
            return self.search_diaries(
                requester=requester,
                query=query,
                start_date=start_date,
                end_date=end_date,
                exact_date=exact_date,
                target_user_id=target_user_id,
                order_desc=order_desc,
                limit=limit,
            )
        if scope == "notes":
            return self.search_notes(
                requester=requester,
                query=query,
                start_date=start_date,
                end_date=end_date,
                exact_date=exact_date,
                target_user_id=target_user_id,
                order_desc=order_desc,
                limit=limit,
            )

        clean_query = query.strip() if query else ""
        norm_query = normalize_text(clean_query) if clean_query else ""

        conn = get_connection(self.db_path)
        try:
            diary_rows = self._query_diaries_rows(
                conn=conn,
                requester=requester,
                norm_query=norm_query,
                start_date=start_date,
                end_date=end_date,
                exact_date=exact_date,
                target_user_id=target_user_id,
                order_desc=order_desc,
                limit=limit,
            )
            note_rows = self._query_notes_rows(
                conn=conn,
                requester=requester,
                norm_query=norm_query,
                start_date=start_date,
                end_date=end_date,
                exact_date=exact_date,
                target_user_id=target_user_id,
                order_desc=order_desc,
                limit=limit,
            )

            path_cache: Dict[int, Dict[int, str]] = {}
            combined: List[Dict[str, Any]] = [
                self._row_to_diary_item(r, clean_query, norm_query, include_snippet=False)
                for r in diary_rows
            ]
            combined.extend(
                self._row_to_note_item(conn, r, path_cache, clean_query, norm_query, include_snippet=False)
                for r in note_rows
            )

            combined.sort(
                key=lambda x: ((x.get("entry_date") or ""), (x.get("updated_at") or "")),
                reverse=order_desc,
            )
            final_items = combined[:limit]

            # Extrai snippets somente para os resultados que efetivamente serão retornados
            for item in final_items:
                content = item.get("content", "")
                norm_c = item.pop("_norm_content", None)
                if item.get("source_type") == "note" and not content.strip():
                    item["snippet"] = "(Arquivo/Nota sem conteúdo)"
                else:
                    item["snippet"] = extract_snippet(
                        content, clean_query, norm_content=norm_c, norm_query=norm_query
                    )

            return final_items
        finally:
            conn.close()
