"""Exercise quiz generation and grading with a local found-item image.

Usage:
    python test.py [image_path] [--response "claimant's description"]

By default, this makes two Gemma API requests: one to generate the quiz evidence
and one to grade the sample response. Pass --skip-generation with --details and
--expected-detail to test grading using existing private quiz evidence.
"""

import argparse
from pathlib import Path

from quiz_generation import OwnershipQuizGenerator
from quiz_grader import OwnershipQuizGrader


SAMPLE_DETAILED_DESCRIPTION = (
    "A small black wireless earbud charging case with a smooth, rounded-"
    "rectangular shape. The case appears slightly scuffed near one corner, "
    "with a tiny white mark on the front."
)
SAMPLE_CLAIMANT_RESPONSE = (
    "It is a small black earbud case, rounded rectangular, with a scuff near "
    "one corner and a tiny white mark on the front."
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate and grade an ownership quiz for a found-item photo."
    )
    parser.add_argument(
        "image",
        nargs="?",
        type=Path,
        default=Path(__file__).with_name("found_item.jpg"),
        help="Image file (default: found_item.jpg beside this script)",
    )
    parser.add_argument(
        "--description",
        default=SAMPLE_DETAILED_DESCRIPTION,
        help="Private detailed description of the item",
    )
    parser.add_argument(
        "--response",
        default=SAMPLE_CLAIMANT_RESPONSE,
        help="Free-response answer to grade",
    )
    parser.add_argument(
        "--skip-generation",
        action="store_true",
        help="Use supplied --details and --expected-detail instead of generating quiz evidence",
    )
    parser.add_argument(
        "--details",
        help="Existing private detailed description (requires --skip-generation)",
    )
    parser.add_argument(
        "--expected-detail",
        action="append",
        default=[],
        help="Private expected detail; repeat this option for multiple details",
    )
    args = parser.parse_args()

    if args.skip_generation:
        if not args.details or not args.expected_detail:
            parser.error("--skip-generation requires --details and at least one --expected-detail")
        detailed_description = args.details
        expected_details = args.expected_detail
        question = None
    else:
        quiz = OwnershipQuizGenerator().generate_quiz(args.description, args.image)
        detailed_description = args.description
        expected_details = quiz["expected_details"]
        question = quiz["question"]
        if not expected_details:
            raise SystemExit(
                "Quiz generation found too few specific details to grade this item "
                "reliably. Use a clearer item photo or a more detailed private "
                "description, then try again."
            )

    if question:
        print("CLAIMANT-FACING QUESTION")
        print(question)
    print("\nSAMPLE CLAIMANT RESPONSE")
    print(args.response)

    grade = OwnershipQuizGrader().grade_response(
        claimant_response=args.response,
        detailed_description=detailed_description,
        expected_details=expected_details,
        image_path=args.image,
    )

    print("\nGRADE (internal; keep details private)")
    print(f"Passed: {grade['passed']}")
    print(f"Score: {grade['score']}/100")
    print(f"Rationale: {grade['rationale']}")
    print("Matched details:")
    for detail in grade["matched_details"]:
        print(f"- {detail}")
    print("Missing details:")
    for detail in grade["missing_details"]:
        print(f"- {detail}")


if __name__ == "__main__":
    main()
