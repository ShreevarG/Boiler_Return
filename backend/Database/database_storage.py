"""Pandas-backed CSV storage for found and returned items.

This lightweight storage layer is suitable for a single-process prototype. For
concurrent web workers, move the same interface to a transactional database.
"""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path
from typing import Any

import pandas as pd


class DatabaseStorage:
    """Store item records in data.csv and item photos in Database/Images."""

    COLUMNS = [
        "item_id",
        "item_title",
        "item_category",
        "geo_coord",
        "location_description",
        "comments",
        "vague_description",
        "detailed_description",
        "quiz_question",
        "grading_guide",
        "expected_details",
        "about_item",
        "image_filename",
        "demo_mode",
    ]

    def __init__(
        self,
        csv_path: str | Path | None = None,
        image_dir: str | Path | None = None,
    ) -> None:
        base_dir = Path(__file__).resolve().parent
        self.csv_path = Path(csv_path) if csv_path else base_dir / "data.csv"
        self.image_dir = Path(image_dir) if image_dir else base_dir / "Images"
        self.csv_path.parent.mkdir(parents=True, exist_ok=True)
        self.image_dir.mkdir(parents=True, exist_ok=True)
        self._ensure_csv()

    def _ensure_csv(self) -> None:
        if not self.csv_path.exists() or self.csv_path.stat().st_size == 0:
            pd.DataFrame(columns=self.COLUMNS).to_csv(self.csv_path, index=False)
            return

        # Add newly introduced columns while retaining existing CSV rows.
        frame = pd.read_csv(self.csv_path, dtype=str, keep_default_na=False)
        changed = False
        for column in self.COLUMNS:
            if column not in frame.columns:
                frame[column] = ""
                changed = True
        if changed:
            frame = frame.reindex(columns=self.COLUMNS)
            frame.to_csv(self.csv_path, index=False)

    def _read(self) -> pd.DataFrame:
        self._ensure_csv()
        frame = pd.read_csv(self.csv_path, dtype=str, keep_default_na=False)
        for column in self.COLUMNS:
            if column not in frame.columns:
                frame[column] = ""
        return frame.reindex(columns=self.COLUMNS)

    def _write(self, frame: pd.DataFrame) -> None:
        # Write then replace to avoid leaving a partially written CSV on failure.
        temp_path = self.csv_path.with_suffix(self.csv_path.suffix + ".tmp")
        frame.reindex(columns=self.COLUMNS).to_csv(temp_path, index=False)
        temp_path.replace(self.csv_path)

    def _store_image(self, image_path: str | Path | None) -> str:
        if image_path is None:
            return ""
        source = Path(image_path)
        if not source.is_file():
            raise FileNotFoundError(f"Image not found: {source}")

        # Generate a unique name instead of trusting an uploaded filename.
        suffix = source.suffix.lower()
        filename = f"{uuid.uuid4().hex}{suffix}"
        shutil.copy2(source, self.image_dir / filename)
        return filename

    def add_item(
        self,
        *,
        title: str = "",
        category: str = "",
        geo_coord: str | tuple[float, float] | None = None,
        location_description: str = "",
        comment: str = "",
        vague_description: str = "",
        detailed_description: str = "",
        quiz_question: str = "",
        grading_guide: str = "",
        expected_details: list[str] | None = None,
        about_item: str = "",
        image_path: str | Path | None = None,
        demo_mode: bool = False,
    ) -> dict[str, Any]:
        """Add an item and return its record, including its generated item_id.

        ``comments`` is stored as a JSON list so each comment is preserved.
        Coordinates may be a string (for example ``"40.42,-86.92"``) or a
        latitude/longitude tuple. ``image_filename`` is relative to image_dir.
        """
        frame = self._read()
        item_id = uuid.uuid4().hex
        if isinstance(geo_coord, tuple):
            if len(geo_coord) != 2:
                raise ValueError("geo_coord tuple must contain latitude and longitude.")
            geo_coord_value = f"{geo_coord[0]},{geo_coord[1]}"
        else:
            geo_coord_value = geo_coord or ""

        import json

        comments = [comment] if comment else []
        image_filename = self._store_image(image_path)
        row = {
            "item_id": item_id,
            "item_title": title,
            "item_category": category,
            "geo_coord": geo_coord_value,
            "location_description": location_description,
            "comments": json.dumps(comments, ensure_ascii=False),
            "vague_description": vague_description,
            "detailed_description": detailed_description,
            "quiz_question": quiz_question,
            "grading_guide": grading_guide,
            "expected_details": json.dumps(expected_details or [], ensure_ascii=False),
            "about_item": about_item,
            "image_filename": image_filename,
            "demo_mode": str(demo_mode).lower(),
        }
        frame = pd.concat([frame, pd.DataFrame([row])], ignore_index=True)
        self._write(frame)
        return row

    def get_item(self, item_id: str) -> dict[str, str] | None:
        """Return one item by ID, or None if it does not exist."""
        frame = self._read()
        matches = frame.loc[frame["item_id"] == item_id]
        if matches.empty:
            return None
        return matches.iloc[0].to_dict()

    def list_items(self) -> list[dict[str, str]]:
        """Return all item records as dictionaries."""
        return self._read().to_dict(orient="records")

    def search_items(self, query: str) -> list[dict[str, str]]:
        """Search public descriptions and location text, case-insensitively."""
        query = query.strip()
        if not query:
            return self.list_items()
        frame = self._read()
        searchable = ["location_description", "vague_description", "about_item"]
        matches = frame[searchable].apply(
            lambda column: column.str.contains(query, case=False, regex=False)
        ).any(axis=1)
        return frame.loc[matches].to_dict(orient="records")

    def add_comment(self, item_id: str, comment: str) -> dict[str, str]:
        """Append a comment to an item's comment list and return its updated row."""
        comment = comment.strip()
        if not comment:
            raise ValueError("comment must not be empty.")

        import json

        frame = self._read()
        matches = frame.index[frame["item_id"] == item_id]
        if len(matches) == 0:
            raise KeyError(f"No item found with id {item_id!r}.")
        index = matches[0]
        try:
            comments = json.loads(frame.at[index, "comments"] or "[]")
        except json.JSONDecodeError:
            comments = []
        if not isinstance(comments, list):
            comments = []
        comments.append(comment)
        frame.at[index, "comments"] = json.dumps(comments, ensure_ascii=False)
        self._write(frame)
        return frame.loc[index].to_dict()

    def get_image_path(self, item_id: str) -> Path | None:
        """Return the local image path for an item, or None if unavailable."""
        item = self.get_item(item_id)
        if not item or not item["image_filename"]:
            return None
        path = self.image_dir / Path(item["image_filename"]).name
        return path if path.is_file() else None

    def update_item(self, item_id: str, **updates: Any) -> dict[str, str]:
        """Update text fields for an item; optionally replace its image.

        Pass ``image_path=...`` to store a new image. Image deletion is avoided
        so an old photo can still be recovered if an update is interrupted.
        """
        allowed = set(self.COLUMNS) - {"item_id", "comments", "image_filename"}
        unknown = set(updates) - allowed - {"image_path"}
        if unknown:
            raise ValueError(f"Unsupported item fields: {', '.join(sorted(unknown))}")

        frame = self._read()
        matches = frame.index[frame["item_id"] == item_id]
        if len(matches) == 0:
            raise KeyError(f"No item found with id {item_id!r}.")
        index = matches[0]
        image_path = updates.pop("image_path", None)
        for field, value in updates.items():
            frame.at[index, field] = "" if value is None else str(value)
        if image_path is not None:
            frame.at[index, "image_filename"] = self._store_image(image_path)
        self._write(frame)
        return frame.loc[index].to_dict()

    def delete_item(self, item_id: str, *, delete_image: bool = False) -> bool:
        """Delete an item row; optionally delete its image file as well."""
        frame = self._read()
        matches = frame.index[frame["item_id"] == item_id]
        if len(matches) == 0:
            return False
        index = matches[0]
        image_filename = frame.at[index, "image_filename"]
        self._write(frame.drop(index).reset_index(drop=True))
        if delete_image and image_filename:
            image_path = self.image_dir / Path(image_filename).name
            image_path.unlink(missing_ok=True)
        return True
