from dataclasses import dataclass
from typing import Optional


@dataclass
class DiaryEntry:
    id: Optional[int]
    user_id: int
    entry_date: str  # YYYY-MM-DD
    content: str
    content_normalized: str = ""
    created_at: str = ""
    updated_at: str = ""
    author_name: Optional[str] = None
    author_username: Optional[str] = None

    @classmethod
    def from_row(cls, row) -> "DiaryEntry":
        """Instancia um DiaryEntry a partir de um sqlite3.Row."""
        keys = row.keys()
        return cls(
            id=row["id"],
            user_id=row["user_id"],
            entry_date=row["entry_date"],
            content=row["content"],
            content_normalized=row["content_normalized"] if "content_normalized" in keys else "",
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            author_name=row["full_name"] if "full_name" in keys else None,
            author_username=row["username"] if "username" in keys else None,
        )
