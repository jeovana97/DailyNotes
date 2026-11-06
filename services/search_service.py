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
