"""Generate a private, image-grounded ownership question for a found item."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import TypedDict

from google import genai


class OwnershipQuiz(TypedDict):
    """One open-response question and private evaluation guidance."""

    question: str
    grading_guide: str
    expected_details: list[str]


class OwnershipQuizGenerator:
    """Generate one ownership-verification question using Gemma 4 vision."""

    MODEL = "gemma-4-26b-a4b-it"

    def __init__(self, api_key: str | None = None) -> None:
        if api_key is None:
            api_key = os.environ.get("GEMINI_API_KEY")

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

    def generate_quiz(
        self,
        detailed_description: str,
        image_path: str | Path,
    ) -> OwnershipQuiz:
        """Generate one free-response question grounded in the description/photo.

        Keep the returned question public to the claimant. Treat ``grading_guide``
        and ``expected_details`` as private server-side data; never reveal them
        alongside the question.
        """
        description = detailed_description.strip()
        if not description:
            raise ValueError("detailed_description must not be empty.")

        path = Path(image_path)
        if not path.is_file():
            raise FileNotFoundError(f"Image not found: {path}")

        prompt = f"""Create an ownership-verification quiz using the attached photo
of a found item and the reported description below. Return exactly one JSON
object with these fields:

"question": One open-ended free-response question asking the claimant to
describe the item in as much detail as they can. It must not reveal or suggest
the answers. Do not ask multiple numbered questions.

"grading_guide": Private guidance for evaluating the response. Explain that
the claimant need not use exact wording, and that answers should be judged
against independently specific visual details, not broad guesses. Do not make
unsupported claims or expect details not visible in the photo or report.

"expected_details": A JSON array of 3 to 8 concise, independently useful
details from the photo/report that a legitimate owner could recognize. Prefer
distinctive marks, wear, attachments, precise colors/materials, visible contents,
or legible text. Exclude generic item facts, and do not invent information.

The question must not include the expected details, give multiple-choice hints,
or disclose the grading guide. Use the image as evidence. The report may contain
incorrect or uncertain claims; do not treat a claim as visually verified unless
the image supports it. If the image and report do not provide enough specific
details for a meaningful quiz, return an empty expected_details array and say so
in the grading_guide.

Reported description:
{description}

Return valid JSON only, with no markdown fences or extra fields."""

        uploaded_image = self.client.files.upload(path=str(path))
        response = self.client.models.generate_content(
            model=self.MODEL,
            contents=[uploaded_image, prompt],
            config={"response_mime_type": "application/json"},
        )

        if not response.text:
            raise RuntimeError("Gemma returned an empty response for the quiz.")

        try:
            result = json.loads(response.text)
        except json.JSONDecodeError as exc:
            raise RuntimeError("Gemma returned invalid JSON for the quiz.") from exc

        question = result.get("question")
        guide = result.get("grading_guide")
        details = result.get("expected_details")
        if not isinstance(question, str) or not question.strip():
            raise RuntimeError("Gemma response is missing the quiz question.")
        if not isinstance(guide, str) or not guide.strip():
            raise RuntimeError("Gemma response is missing the grading guide.")
        if not isinstance(details, list) or not all(
            isinstance(detail, str) for detail in details
        ):
            raise RuntimeError("Gemma returned invalid expected_details.")

        clean_details = [detail.strip() for detail in details if detail.strip()]
        if clean_details and len(clean_details) < 3:
            raise RuntimeError(
                "Gemma returned fewer than 3 usable expected details; "
                "the quiz does not have enough evidence for reliable grading."
            )

        return {
            "question": question.strip(),
            "grading_guide": guide.strip(),
            "expected_details": clean_details,
        }
