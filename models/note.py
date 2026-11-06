from dataclasses import dataclass
from typing import Optional


@dataclass
class NoteFolder:
    id: Optional[int]
    user_id: int
    parent_id: Optional[int]
    name: str
    name_normalized: str = ""
    created_at: str = ""
    updated_at: str = ""

    @classmethod
    def from_row(cls, row) -> "NoteFolder":
        """Instancia um NoteFolder a partir de um sqlite3.Row."""
        keys = row.keys()
        return cls(
            id=row["id"],
            user_id=row["user_id"],
            parent_id=row["parent_id"],
            name=row["name"],
            name_normalized=row["name_normalized"] if "name_normalized" in keys else "",
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


@dataclass
class NoteItem:
    id: Optional[int]
    user_id: int
    folder_id: Optional[int]
    title: str
    title_normalized: str = ""
    content: str = ""
    created_at: str = ""
    updated_at: str = ""
    folder_name: Optional[str] = None

    @classmethod
    def from_row(cls, row) -> "NoteItem":
        """Instancia um NoteItem a partir de um sqlite3.Row."""
        keys = row.keys()
        return cls(
            id=row["id"],
            user_id=row["user_id"],
            folder_id=row["folder_id"],
            title=row["title"],
            title_normalized=row["title_normalized"] if "title_normalized" in keys else "",
            content=row["content"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            folder_name=row["folder_name"] if "folder_name" in keys else None,
        )

