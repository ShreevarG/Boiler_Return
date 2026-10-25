"""Create private and public descriptions of a found item from a photo."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import TypedDict

from google import genai


class ItemDescriptions(TypedDict):
    """Descriptions suitable for a private recovery quiz and public listing."""

    detailed_description: str
    public_description: str


class FoundItemDescriber:
    """Use Gemma 4 vision to describe a found item from a local image."""

    MODEL = "gemma-4-26b-a4b-it"

    def __init__(self, api_key: str | None = None) -> None:
        if api_key is None:
            api_key = os.environ.get("GEMINI_API_KEY")

        # Read the adjacent .env without overwriting an explicitly set environment key.
        if not api_key:
            env_file = Path(__file__).with_name(".env")
            if env_file.is_file():
                for line in env_file.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        name, value = line.split("=", 1)
                        if name.strip() == "GEMINI_API_KEY":
                            api_key = value.strip().strip("\"'")
                            break

        if not api_key:
            raise ValueError(
                "Set GEMINI_API_KEY in the environment or in Gemini API/.env."
            )

        self.client = genai.Client(api_key=api_key)

    def describe_image(self, image_path: str | Path) -> ItemDescriptions:
        """Return detailed private and safe public descriptions for an image.

        The detailed description focuses on observable identifying details for a
        later recovery quiz. The public description provides recognition cues
        while withholding distinctive details that could reveal quiz answers.
        """
        path = Path(image_path)
        if not path.is_file():
            raise FileNotFoundError(f"Image not found: {path}")

        prompt = """Analyze the found-item photo and return exactly one JSON object with
these two string fields:

"detailed_description": A clear, thorough account of visible, verifiable
features useful for creating a private ownership quiz. Include item type,
brand/model or text if legible, colors, material, shape, size relative to other
objects, wear/damage, unique marks, attachments, contents visible, and where
the item appears in the photo. Do not guess facts that cannot be seen. Mark
uncertain observations as uncertain. Avoid personal data unrelated to identifying
the item.

"public_description": A short, natural description that helps the owner
recognize the general kind of item and decide to try the recovery quiz. Omit
brand/model, serial numbers, exact text, unique marks, exact contents, and other
distinctive details that could let a stranger pass a quiz. Include only broad
category, general color/type, and found context when visible. Do not claim the
item is present if the image is unclear.

Return valid JSON only. Do not include markdown fences or extra fields."""

        uploaded_image = self.client.files.upload(path=str(path))
        response = self.client.models.generate_content(
            model=self.MODEL,
            contents=[uploaded_image, prompt],
            config={"response_mime_type": "application/json"},
        )

        if not response.text:
            raise RuntimeError("Gemma returned an empty response for the image.")

        try:
            result = json.loads(response.text)
        except json.JSONDecodeError as exc:
            raise RuntimeError("Gemma returned invalid JSON for the descriptions.") from exc

        detailed = result.get("detailed_description")
        public = result.get("public_description")
        if not isinstance(detailed, str) or not detailed.strip():
            raise RuntimeError("Gemma response is missing detailed_description.")
        if not isinstance(public, str) or not public.strip():
            raise RuntimeError("Gemma response is missing public_description.")

        return {
            "detailed_description": detailed.strip(),
            "public_description": public.strip(),
        }
