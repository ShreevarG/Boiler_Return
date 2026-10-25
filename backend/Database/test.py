"""Smoke-test DatabaseStorage without changing the real data.csv or images."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from backend.Database.database_storage import DatabaseStorage


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="boiler_return_db_test_") as temp_dir:
        temp_path = Path(temp_dir)
        storage = DatabaseStorage(
            csv_path=temp_path / "data.csv",
            image_dir=temp_path / "images",
        )

        # Create a tiny fixture file so the image copy behavior is exercised.
        source_image = temp_path / "fixture.jpg"
        source_image.write_bytes(b"test image bytes")

        created = storage.add_item(
            title="Wireless earbuds",
            category="Electronics",
            geo_coord=(40.4237, -86.9212),
            location_description="Near the student union",
            comment="Found on a bench",
            vague_description="A small personal electronic item",
            detailed_description="A black case with a small white mark.",
            quiz_question="Describe the marks on the item.",
            grading_guide="Look for independently specific visual details.",
            expected_details=["black case", "small white mark", "hinged lid"],
            about_item="Found item awaiting its owner.",
            image_path=source_image,
        )
        item_id = created["item_id"]
        assert item_id
        assert created["geo_coord"] == "40.4237,-86.9212"

        fetched = storage.get_item(item_id)
        assert fetched is not None
        assert fetched["item_title"] == "Wireless earbuds"
        assert fetched["item_category"] == "Electronics"
        assert fetched["location_description"] == "Near the student union"
        assert fetched["grading_guide"]
        assert json.loads(fetched["expected_details"]) == [
            "black case",
            "small white mark",
            "hinged lid",
        ]
        assert json.loads(fetched["comments"]) == ["Found on a bench"]

        image_path = storage.get_image_path(item_id)
        assert image_path is not None and image_path.is_file()
        assert image_path.read_bytes() == source_image.read_bytes()
        assert image_path.parent == temp_path / "images"

        assert len(storage.list_items()) == 1
        search_results = storage.search_items("student union")
        assert len(search_results) == 1 and search_results[0]["item_id"] == item_id

        updated = storage.add_comment(item_id, "I may know who owns this.")
        assert json.loads(updated["comments"]) == [
            "Found on a bench",
            "I may know who owns this.",
        ]

        updated = storage.update_item(item_id, about_item="Updated item note")
        assert updated["about_item"] == "Updated item note"
        assert storage.get_item(item_id)["about_item"] == "Updated item note"

        assert storage.delete_item(item_id) is True
        assert storage.get_item(item_id) is None
        assert storage.list_items() == []
        assert storage.delete_item(item_id) is False
        # By default, deleting a row keeps its image file.
        assert image_path.is_file()

    print("DatabaseStorage smoke test passed.")


if __name__ == "__main__":
    main()
