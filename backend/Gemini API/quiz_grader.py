"""Grade an ownership quiz response against private item evidence."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import TypedDict

from google import genai


class QuizGrade(TypedDict):
    """Structured ownership quiz result."""

    passed: bool
    score: int
    rationale: str
    matched_details: list[str]
    missing_details: list[str]


class OwnershipQuizGrader:
    """Use Gemma 4 vision to assess whether a response shows item knowledge."""

    MODEL = "gemma-4-26b-a4b-it"
    PASSING_SCORE = 70

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

    def grade_response(
        self,
        claimant_response: str,
        detailed_description: str,
        expected_details: list[str],
        image_path: str | Path,
        grading_guide: str = "",
    ) -> QuizGrade:
        """Grade one free-response answer using the photo and private evidence.

        This result is for the recovery workflow. Do not expose matched or missing
        details to claimants, since they could use that feedback to retry-guess.
        """
        answer = claimant_response.strip()
        description = detailed_description.strip()
        if not answer:
            raise ValueError("claimant_response must not be empty.")
        if not description:
            raise ValueError("detailed_description must not be empty.")
        if not expected_details:
            raise ValueError("expected_details must contain private quiz evidence.")

        path = Path(image_path)
        if not path.is_file():
            raise FileNotFoundError(f"Image not found: {path}")

        evidence_json = json.dumps(
            {
                "detailed_description": description,
                "expected_details": expected_details,
            },
            ensure_ascii=False,
        )
        grading_guide_json = json.dumps(grading_guide.strip(), ensure_ascii=False)
        answer_json = json.dumps(answer, ensure_ascii=False)
        prompt = f"""Assess whether this free-response answer provides credible,
specific knowledge of ownership of the item in the attached image. The answer
does not need exact wording. Be fair to a genuine owner who may forget a detail,
describe it imprecisely, or use a synonym. At the same time, do not pass someone
based only on generic guesses, details plainly visible in the public-facing
listing, or unsupported claims.

Compare the response with the private evidence below and the image. Give credit
only for accurate, independently useful details. Consider the combination of
correct details and whether it is unlikely to be guessed. Do not require every
detail. Contradictions about distinctive features should reduce confidence.
Do not reward verbosity by itself.

Use a score from 0 to 100. Set passed to true only when score is at least
{self.PASSING_SCORE} and the answer contains multiple meaningful matching
details, including at least one relatively distinctive detail. If the evidence
is insufficient to distinguish an owner from a guesser, set passed to false.

Return exactly one JSON object with:
- "passed": boolean
- "score": integer from 0 to 100
- "rationale": brief internal explanation, without revealing unnecessary
  sensitive item details
- "matched_details": array of private evidence items supported by the answer
- "missing_details": array of expected evidence items not supplied

Private evidence:
{evidence_json}

Quiz-specific grading guidance:
{grading_guide_json}

Claimant response:
{answer_json}

Return valid JSON only, with no markdown fences or extra fields."""

        uploaded_image = self.client.files.upload(path=str(path))
        response = self.client.models.generate_content(
            model=self.MODEL,
            contents=[uploaded_image, prompt],
            config={"response_mime_type": "application/json"},
        )

        if not response.text:
            raise RuntimeError("Gemma returned an empty response for the grade.")

        try:
            result = json.loads(response.text)
        except json.JSONDecodeError as exc:
            raise RuntimeError("Gemma returned invalid JSON for the grade.") from exc

        passed = result.get("passed")
        score = result.get("score")
        rationale = result.get("rationale")
        matched = result.get("matched_details")
        missing = result.get("missing_details")
        if not isinstance(passed, bool):
            raise RuntimeError("Gemma response is missing boolean passed.")
        if not isinstance(score, int) or not 0 <= score <= 100:
            raise RuntimeError("Gemma response has an invalid score.")
        if passed != (score >= self.PASSING_SCORE):
            raise RuntimeError("Gemma pass/fail result conflicts with its score.")
        if not isinstance(rationale, str) or not rationale.strip():
            raise RuntimeError("Gemma response is missing the grading rationale.")
        if not isinstance(matched, list) or not all(
            isinstance(detail, str) for detail in matched
        ):
            raise RuntimeError("Gemma returned invalid matched_details.")
        if not isinstance(missing, list) or not all(
            isinstance(detail, str) for detail in missing
        ):
            raise RuntimeError("Gemma returned invalid missing_details.")

        return {
            "passed": passed,
            "score": score,
            "rationale": rationale.strip(),
            "matched_details": matched,
            "missing_details": missing,
        }
