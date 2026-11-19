import logging
from typing import Optional, List, Dict, Any
from database.connection import get_connection
from models.user import User
from utils.text_utils import normalize_text, extract_snippet
from utils.date_utils import is_valid_iso_date

logger = logging.getLogger(__name__)


class SearchService:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path

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
        Executa pesquisa avançada de anotações com filtros múltiplos:
        - Termo ou expressão (insensível a maiúsculas e sem diferenciar acentuação)
        - Data inicial e final
        - Data exata
        - Filtro de usuário (respeitando estritamente as permissões)
        - Ordenação cronológica (decrescente ou crescente)
        """
        conn = get_connection(self.db_path)
        try:
            cursor = conn.cursor()

            query_conditions = ["TRIM(d.content) != ''"]
            params: List[Any] = []

            # 1. Controle rigoroso de acesso do usuário
            if not requester.can_view_other_diaries:
                # Usuário comum só pode pesquisar em suas próprias anotações
                query_conditions.append("d.user_id = ?")
                params.append(requester.id)
            else:
                # Administrador autorizado pode filtrar por um usuário específico ou ver todos
                if target_user_id is not None and target_user_id > 0:
                    query_conditions.append("d.user_id = ?")
                    params.append(target_user_id)

            # 2. Filtro por data exata
            if exact_date and is_valid_iso_date(exact_date):
                query_conditions.append("d.entry_date = ?")
                params.append(exact_date)
            else:
                # 3. Filtro por período (data inicial e/ou final)
                if start_date and is_valid_iso_date(start_date):
                    query_conditions.append("d.entry_date >= ?")
                    params.append(start_date)

                if end_date and is_valid_iso_date(end_date):
                    query_conditions.append("d.entry_date <= ?")
                    params.append(end_date)

            # 4. Filtro por conteúdo textual (com normalização de acentos e minúsculas)
            clean_query = query.strip() if query else ""
            if clean_query:
                norm_query = normalize_text(clean_query)
                # Utiliza a função customizada lower_no_accents e content_normalized para garantir casamento exato de acentos
                # e substrings dentro de frases ou palavras compostas
                query_conditions.append("lower_no_accents(d.content) LIKE ?")
                params.append(f"%{norm_query}%")

            where_clause = " AND ".join(query_conditions)
            order_direction = "DESC" if order_desc else "ASC"

            sql = f"""
                SELECT
                    d.id,
                    d.user_id,
                    d.entry_date,
                    d.content,
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
            rows = cursor.fetchall()

            results: List[Dict[str, Any]] = []
            for row in rows:
                content = row["content"]
                snippet = extract_snippet(content, clean_query)
                results.append({
                    "source_type": "diary",
                    "id": row["id"],
                    "user_id": row["user_id"],
                    "entry_date": row["entry_date"],
                    "content": content,
                    "snippet": snippet,
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                    "full_name": row["full_name"],
                    "username": row["username"],
                })

            return results
        finally:
            conn.close()

    def _build_folder_path_map(self, conn, user_id: int) -> Dict[int, str]:
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
        conn = get_connection(self.db_path)
        try:
            cursor = conn.cursor()

            query_conditions = ["(TRIM(n.title) != '' OR TRIM(n.content) != '')"]
            params: List[Any] = []

            if not requester.can_view_other_diaries:
                query_conditions.append("n.user_id = ?")
                params.append(requester.id)
            else:
                if target_user_id is not None and target_user_id > 0:
                    query_conditions.append("n.user_id = ?")
                    params.append(target_user_id)

            if exact_date and is_valid_iso_date(exact_date):
                query_conditions.append("substr(n.updated_at, 1, 10) = ?")
                params.append(exact_date)
            else:
                if start_date and is_valid_iso_date(start_date):
                    query_conditions.append("substr(n.updated_at, 1, 10) >= ?")
                    params.append(start_date)
                if end_date and is_valid_iso_date(end_date):
                    query_conditions.append("substr(n.updated_at, 1, 10) <= ?")
                    params.append(end_date)

            clean_query = query.strip() if query else ""
            if clean_query:
                norm_query = normalize_text(clean_query)
                query_conditions.append(
                    "(lower_no_accents(n.title) LIKE ? OR lower_no_accents(n.content) LIKE ?)"
                )
                like_pat = f"%{norm_query}%"
                params.extend([like_pat, like_pat])

            where_clause = " AND ".join(query_conditions)
            order_direction = "DESC" if order_desc else "ASC"

            sql = f"""
                SELECT
                    n.id,
                    n.user_id,
                    n.folder_id,
                    n.title,
                    n.content,
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
            rows = cursor.fetchall()

            path_cache: Dict[int, Dict[int, str]] = {}
            results: List[Dict[str, Any]] = []
            for row in rows:
                uid = row["user_id"]
                if uid not in path_cache:
                    path_cache[uid] = self._build_folder_path_map(conn, uid)

                fid = row["folder_id"]
                folder_path = path_cache[uid].get(fid, "Raiz (Sem pasta)") if fid is not None else "Raiz (Sem pasta)"
                content = row["content"] or ""
                snippet = extract_snippet(content, clean_query) if content.strip() else "(Arquivo/Nota sem conteúdo)"

                results.append({
                    "source_type": "note",
                    "id": row["id"],
                    "note_id": row["id"],
                    "folder_id": fid,
                    "folder_path": folder_path,
                    "title": row["title"],
                    "user_id": uid,
                    "entry_date": (row["updated_at"] or "")[:10],
                    "content": content,
                    "snippet": snippet,
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                    "full_name": row["full_name"],
                    "username": row["username"],
                })

            return results
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
        Pesquisa unificada conforme o escopo escolhido:
        - 'diaries': apenas anotações do Diário
        - 'notes': apenas notas e arquivos em Pastas
        - 'all': Diário + Pastas e Arquivos
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

        diary_res = self.search_diaries(
            requester=requester,
            query=query,
            start_date=start_date,
            end_date=end_date,
            exact_date=exact_date,
            target_user_id=target_user_id,
            order_desc=order_desc,
            limit=limit,
        )
        note_res = self.search_notes(
            requester=requester,
            query=query,
            start_date=start_date,
            end_date=end_date,
            exact_date=exact_date,
            target_user_id=target_user_id,
            order_desc=order_desc,
            limit=limit,
        )

        combined = diary_res + note_res
        combined.sort(
            key=lambda x: ((x.get("entry_date") or ""), (x.get("updated_at") or "")),
            reverse=order_desc,
        )
        return combined[:limit]
