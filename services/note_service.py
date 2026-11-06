import os
import logging
from typing import Optional, List, Dict, Tuple, Set
from database.connection import get_connection, get_db
from models.note import NoteFolder, NoteItem
from utils.date_utils import get_current_timestamp
from utils.text_utils import normalize_text

logger = logging.getLogger(__name__)


class NoteService:
    """
    Serviço responsável pelo gerenciamento de Notas Rápidas / Notas Salvas e sua
    organização hierárquica em Pastas e Subpastas.
    - Independente das datas do diário
    - Isolado da Pesquisa Avançada do diário
    - Permite pesquisa dedicada pelo nome (título) da nota salva
    """

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path

    # =========================================================================
    # Gerenciamento de Pastas e Subpastas
    # =========================================================================

    def get_folder(self, user_id: int, folder_id: int) -> Optional[NoteFolder]:
        """Recupera uma pasta pelo ID garantindo que pertença ao usuário."""
        conn = get_connection(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM note_folders WHERE id = ? AND user_id = ?",
                (folder_id, user_id),
            )
            row = cursor.fetchone()
            return NoteFolder.from_row(row) if row else None
        finally:
            conn.close()

    def list_folders(self, user_id: int) -> List[NoteFolder]:
        """Lista todas as pastas e subpastas do usuário em ordem alfabética."""
        conn = get_connection(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM note_folders
                WHERE user_id = ?
                ORDER BY name_normalized ASC, name ASC
                """,
                (user_id,),
            )
            return [NoteFolder.from_row(r) for r in cursor.fetchall()]
        finally:
            conn.close()

    def create_folder(
        self,
        user_id: int,
        name: str,
        parent_id: Optional[int] = None,
    ) -> NoteFolder:
        """
        Cria uma pasta na raiz (parent_id=None) ou uma subpasta dentro de outra pasta.
        """
        clean_name = (name or "").strip()
        if not clean_name:
            raise ValueError("O nome da pasta não pode estar vazio.")

        norm_name = normalize_text(clean_name)
        now = get_current_timestamp()

        with get_db(self.db_path) as conn:
            cursor = conn.cursor()

            if parent_id is not None:
                cursor.execute(
                    "SELECT id FROM note_folders WHERE id = ? AND user_id = ?",
                    (parent_id, user_id),
                )
                if not cursor.fetchone():
                    raise ValueError("Pasta pai não encontrada.")

            # Verifica duplicidade no mesmo nível
            if parent_id is None:
                cursor.execute(
                    """
                    SELECT id FROM note_folders
                    WHERE user_id = ? AND parent_id IS NULL AND name_normalized = ?
                    """,
                    (user_id, norm_name),
                )
            else:
                cursor.execute(
                    """
                    SELECT id FROM note_folders
                    WHERE user_id = ? AND parent_id = ? AND name_normalized = ?
                    """,
                    (user_id, parent_id, norm_name),
                )

            if cursor.fetchone():
                raise ValueError(f"Já existe uma pasta chamada '{clean_name}' neste local.")

            cursor.execute(
                """
                INSERT INTO note_folders (user_id, parent_id, name, name_normalized, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (user_id, parent_id, clean_name, norm_name, now, now),
            )
            folder_id = cursor.lastrowid

        created = self.get_folder(user_id, folder_id)
        if not created:
            raise RuntimeError("Erro ao recuperar pasta após criação.")
        return created

    def rename_folder(self, user_id: int, folder_id: int, new_name: str) -> NoteFolder:
        """Renomeia uma pasta ou subpasta existente."""
        clean_name = (new_name or "").strip()
        if not clean_name:
            raise ValueError("O nome da pasta não pode estar vazio.")

        folder = self.get_folder(user_id, folder_id)
        if not folder:
            raise ValueError("Pasta não encontrada.")

        norm_name = normalize_text(clean_name)
        now = get_current_timestamp()

        with get_db(self.db_path) as conn:
            cursor = conn.cursor()
            if folder.parent_id is None:
                cursor.execute(
                    """
                    SELECT id FROM note_folders
                    WHERE user_id = ? AND parent_id IS NULL AND name_normalized = ? AND id != ?
                    """,
                    (user_id, norm_name, folder_id),
                )
            else:
                cursor.execute(
                    """
                    SELECT id FROM note_folders
                    WHERE user_id = ? AND parent_id = ? AND name_normalized = ? AND id != ?
                    """,
                    (user_id, folder.parent_id, norm_name, folder_id),
                )

            if cursor.fetchone():
                raise ValueError(f"Já existe outra pasta chamada '{clean_name}' neste local.")

            cursor.execute(
                """
                UPDATE note_folders
                SET name = ?, name_normalized = ?, updated_at = ?
                WHERE id = ? AND user_id = ?
                """,
                (clean_name, norm_name, now, folder_id, user_id),
            )

        updated = self.get_folder(user_id, folder_id)
        if not updated:
            raise RuntimeError("Falha ao atualizar pasta.")
        return updated

    def get_descendant_folder_ids(self, user_id: int, folder_id: int) -> Set[int]:
        """Retorna o conjunto de IDs de todas as subpastas descendentes de uma pasta."""
        all_folders = self.list_folders(user_id)
        children_map: Dict[Optional[int], List[int]] = {}
        for f in all_folders:
            children_map.setdefault(f.parent_id, []).append(f.id)

        descendants: Set[int] = set()
        stack = list(children_map.get(folder_id, []))
        while stack:
            cid = stack.pop()
            if cid not in descendants:
                descendants.add(cid)
                stack.extend(children_map.get(cid, []))
        return descendants

    def move_folder(
        self,
        user_id: int,
        folder_id: int,
        new_parent_id: Optional[int],
    ) -> NoteFolder:
        """Move uma pasta para outra pasta pai (ou para a raiz se new_parent_id=None)."""
        folder = self.get_folder(user_id, folder_id)
        if not folder:
            raise ValueError("Pasta não encontrada.")

        if new_parent_id == folder_id:
            raise ValueError("Uma pasta não pode ser movida para dentro de si mesma.")

        if new_parent_id is not None:
            target_parent = self.get_folder(user_id, new_parent_id)
            if not target_parent:
                raise ValueError("Pasta de destino não encontrada.")

            descendants = self.get_descendant_folder_ids(user_id, folder_id)
            if new_parent_id in descendants:
                raise ValueError("Não é possível mover uma pasta para dentro de uma de suas subpastas.")

        now = get_current_timestamp()
        with get_db(self.db_path) as conn:
            cursor = conn.cursor()
            if new_parent_id is None:
                cursor.execute(
                    """
                    SELECT id FROM note_folders
                    WHERE user_id = ? AND parent_id IS NULL AND name_normalized = ? AND id != ?
                    """,
                    (user_id, folder.name_normalized, folder_id),
                )
            else:
                cursor.execute(
                    """
                    SELECT id FROM note_folders
                    WHERE user_id = ? AND parent_id = ? AND name_normalized = ? AND id != ?
                    """,
                    (user_id, new_parent_id, folder.name_normalized, folder_id),
                )
            if cursor.fetchone():
                raise ValueError(f"Já existe uma pasta com o nome '{folder.name}' no destino.")

            cursor.execute(
                """
                UPDATE note_folders
                SET parent_id = ?, updated_at = ?
                WHERE id = ? AND user_id = ?
                """,
                (new_parent_id, now, folder_id, user_id),
            )

        return self.get_folder(user_id, folder_id)

    def delete_folder(self, user_id: int, folder_id: int) -> bool:
        """
        Exclui uma pasta e, em cascata (ON DELETE CASCADE), todas as suas subpastas e notas.
        """
        with get_db(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM note_folders WHERE id = ? AND user_id = ?",
                (folder_id, user_id),
            )
            return cursor.rowcount > 0

    def get_folder_path_map(self, user_id: int) -> Dict[int, str]:
        """
        Retorna um dicionário {folder_id: 'Pasta / Subpasta'} para todas as pastas do usuário.
        """
        folders = self.list_folders(user_id)
        by_id: Dict[int, NoteFolder] = {f.id: f for f in folders if f.id is not None}
        path_map: Dict[int, str] = {}

        for fid in by_id:
            parts = []
            curr_id: Optional[int] = fid
            visited = set()
            while curr_id is not None and curr_id in by_id and curr_id not in visited:
                visited.add(curr_id)
                f_obj = by_id[curr_id]
                parts.append(f_obj.name)
                curr_id = f_obj.parent_id
            parts.reverse()
            path_map[fid] = " / ".join(parts)

        return path_map

    def get_folder_tree_options(
        self,
        user_id: int,
        exclude_folder_id: Optional[int] = None,
    ) -> List[Tuple[Optional[int], str]]:
        """
        Retorna opções hierárquicas de pastas no formato [(None, '📁 Sem pasta (Raiz)'), (id, '📁 ...'), ...].
        Ideal para seletores de pasta na interface.
        """
        folders = self.list_folders(user_id)
        excluded_ids: Set[int] = set()
        if exclude_folder_id is not None:
            excluded_ids.add(exclude_folder_id)
            excluded_ids.update(self.get_descendant_folder_ids(user_id, exclude_folder_id))

        children_map: Dict[Optional[int], List[NoteFolder]] = {}
        for f in folders:
            if f.id in excluded_ids:
                continue
            children_map.setdefault(f.parent_id, []).append(f)

        options: List[Tuple[Optional[int], str]] = [(None, "📁 Sem pasta (Raiz)")]

        def _traverse(parent_id: Optional[int], depth: int):
            for child in children_map.get(parent_id, []):
                if depth == 0:
                    label = f"📁 {child.name}"
                else:
                    indent = "   " * depth
                    label = f"{indent}↳ 📂 {child.name}"
                options.append((child.id, label))
                _traverse(child.id, depth + 1)

        _traverse(None, 0)
        return options

    # =========================================================================
    # Gerenciamento de Notas (Independentes de Datas do Diário)
    # =========================================================================

    def get_note(self, user_id: int, note_id: int) -> Optional[NoteItem]:
        """Recupera uma nota específica pelo ID e usuário."""
        conn = get_connection(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT n.*, f.name AS folder_name
                FROM notes n
                LEFT JOIN note_folders f ON n.folder_id = f.id
                WHERE n.id = ? AND n.user_id = ?
                """,
                (note_id, user_id),
            )
            row = cursor.fetchone()
            return NoteItem.from_row(row) if row else None
        finally:
            conn.close()

    def list_notes(
        self,
        user_id: int,
        folder_id: Optional[int] = None,
        all_notes: bool = True,
    ) -> List[NoteItem]:
        """
        Lista as notas do usuário.
        Se all_notes=True, retorna todas as notas do usuário (em qualquer pasta ou raiz).
        Se all_notes=False, filtra exatamente por folder_id (incluindo None para raiz).
        """
        conn = get_connection(self.db_path)
        try:
            cursor = conn.cursor()
            if all_notes:
                cursor.execute(
                    """
                    SELECT n.*, f.name AS folder_name
                    FROM notes n
                    LEFT JOIN note_folders f ON n.folder_id = f.id
                    WHERE n.user_id = ?
                    ORDER BY n.title_normalized ASC, n.title ASC, n.id ASC
                    """,
                    (user_id,),
                )
            elif folder_id is None:
                cursor.execute(
                    """
                    SELECT n.*, NULL AS folder_name
                    FROM notes n
                    WHERE n.user_id = ? AND n.folder_id IS NULL
                    ORDER BY n.title_normalized ASC, n.title ASC, n.id ASC
                    """,
                    (user_id,),
                )
            else:
                cursor.execute(
                    """
                    SELECT n.*, f.name AS folder_name
                    FROM notes n
                    LEFT JOIN note_folders f ON n.folder_id = f.id
                    WHERE n.user_id = ? AND n.folder_id = ?
                    ORDER BY n.title_normalized ASC, n.title ASC, n.id ASC
                    """,
                    (user_id, folder_id),
                )
            return [NoteItem.from_row(r) for r in cursor.fetchall()]
        finally:
            conn.close()

    def search_notes_by_title(self, user_id: int, title_query: str) -> List[NoteItem]:
        """
        Pesquisa notas do usuário exclusivamente pelo nome (título) da nota salva,
        insensível a maiúsculas/minúsculas e acentuação.
        """
        clean_query = (title_query or "").strip()
        if not clean_query:
            return self.list_notes(user_id, all_notes=True)

        norm_query = normalize_text(clean_query)
        conn = get_connection(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT n.*, f.name AS folder_name
                FROM notes n
                LEFT JOIN note_folders f ON n.folder_id = f.id
                WHERE n.user_id = ?
                  AND (n.title_normalized LIKE ? OR lower_no_accents(n.title) LIKE ?)
                ORDER BY n.title_normalized ASC, n.title ASC, n.id ASC
                """,
                (user_id, f"%{norm_query}%", f"%{norm_query}%"),
            )
            return [NoteItem.from_row(r) for r in cursor.fetchall()]
        finally:
            conn.close()

    def save_note(
        self,
        user_id: int,
        title: str,
        content: str = "",
        folder_id: Optional[int] = None,
        note_id: Optional[int] = None,
    ) -> NoteItem:
        """
        Cria uma nova nota (quando note_id=None) ou atualiza uma nota existente.
        """
        clean_title = (title or "").strip()
        if not clean_title:
            raise ValueError("Informe um nome/título para salvar a nota.")

        norm_title = normalize_text(clean_title)
        now = get_current_timestamp()

        with get_db(self.db_path) as conn:
            cursor = conn.cursor()

            if folder_id is not None:
                cursor.execute(
                    "SELECT id FROM note_folders WHERE id = ? AND user_id = ?",
                    (folder_id, user_id),
                )
                if not cursor.fetchone():
                    raise ValueError("A pasta selecionada não existe.")

            if note_id is None:
                cursor.execute(
                    """
                    INSERT INTO notes (user_id, folder_id, title, title_normalized, content, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (user_id, folder_id, clean_title, norm_title, content, now, now),
                )
                target_id = cursor.lastrowid
            else:
                cursor.execute(
                    "SELECT id FROM notes WHERE id = ? AND user_id = ?",
                    (note_id, user_id),
                )
                if not cursor.fetchone():
                    raise ValueError("Nota não encontrada para atualização.")

                cursor.execute(
                    """
                    UPDATE notes
                    SET folder_id = ?,
                        title = ?,
                        title_normalized = ?,
                        content = ?,
                        updated_at = ?
                    WHERE id = ? AND user_id = ?
                    """,
                    (folder_id, clean_title, norm_title, content, now, note_id, user_id),
                )
                target_id = note_id

        saved = self.get_note(user_id, target_id)
        if not saved:
            raise RuntimeError("Falha ao recuperar a nota após salvamento.")
        return saved

    def move_note(self, user_id: int, note_id: int, target_folder_id: Optional[int]) -> NoteItem:
        """Move uma nota para outra pasta (ou para a raiz se target_folder_id=None)."""
        note = self.get_note(user_id, note_id)
        if not note:
            raise ValueError("Nota não encontrada.")

        return self.save_note(
            user_id=user_id,
            title=note.title,
            content=note.content,
            folder_id=target_folder_id,
            note_id=note.id,
        )

    def delete_note(self, user_id: int, note_id: int) -> bool:
        """Exclui uma nota salva."""
        with get_db(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM notes WHERE id = ? AND user_id = ?",
                (note_id, user_id),
            )
            return cursor.rowcount > 0

    def export_note_to_txt(self, note: NoteItem, target_file_path: str, folder_path: str = "") -> Tuple[bool, str]:
        """Exporta uma nota para arquivo TXT em UTF-8."""
        try:
            os.makedirs(os.path.dirname(os.path.abspath(target_file_path)), exist_ok=True)
            pasta_info = folder_path if folder_path else (note.folder_name or "Raiz")
            header = (
                f"====================================================\n"
                f"NOTA: {note.title}\n"
                f"Pasta: {pasta_info}\n"
                f"Última alteração: {note.updated_at}\n"
                f"====================================================\n\n"
            )
            with open(target_file_path, "w", encoding="utf-8") as f:
                f.write(header)
                f.write(note.content or "")

            return True, f"Nota exportada com sucesso para:\n{target_file_path}"
        except Exception as e:
            return False, f"Erro ao exportar nota: {str(e)}"

