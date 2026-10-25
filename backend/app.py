from __future__ import annotations

import json
import logging
import sys
import tempfile
from pathlib import Path

from flask import Flask, jsonify, request
from flask_cors import CORS
from werkzeug.utils import secure_filename

BASE_DIR = Path(__file__).resolve().parent
DATABASE_DIR = BASE_DIR / "Database"
GEMINI_DIR = BASE_DIR / "Gemini API"
UPLOAD_DIR = BASE_DIR / "uploads"
ALLOWED_IMAGE_EXTENSIONS = {".bmp", ".gif", ".jpeg", ".jpg", ".png", ".webp"}

sys.path.insert(0, str(DATABASE_DIR))
sys.path.insert(0, str(GEMINI_DIR))

from database_storage import DatabaseStorage
from image_parse import FoundItemDescriber
from quiz_generation import OwnershipQuizGenerator
from quiz_grader import OwnershipQuizGrader

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024
CORS(app, resources={r"/api/*": {"origins": "*"}})
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

storage = DatabaseStorage()


def public_item(record: dict[str, str]) -> dict[str, object]:
    try:
        comments = json.loads(record["comments"] or "[]")
    except json.JSONDecodeError:
        comments = []
    if not isinstance(comments, list) or not all(
        isinstance(comment, str) for comment in comments
    ):
        comments = []

    return {
        "id": record["item_id"],
        "title": record["item_title"] or "Found item",
        "category": record["item_category"] or "Personal items",
        "location": record["location_description"] or "Campus",
        "description": record["about_item"] or record["vague_description"],
        "comments": comments,
        "demoMode": record.get("demo_mode") == "true",
    }


@app.errorhandler(413)
def request_too_large(_error: Exception):
    return jsonify({"status": "error", "message": "Image must be 10 MB or smaller."}), 413


@app.route("/api/items", methods=["GET"])
def get_items():
    records = reversed(storage.list_items())
    return jsonify({"status": "success", "data": [public_item(row) for row in records]})


@app.route("/api/items", methods=["POST"])
def create_item():
    title = request.form.get("title", "").strip()
    category = request.form.get("category", "").strip()
    location = request.form.get("location", "").strip()
    reported_description = request.form.get("description", "").strip()
    image = request.files.get("image")

    if not all((title, category, location, reported_description)):
        return jsonify(
            {
                "status": "error",
                "message": "Title, category, location, and description are required.",
            }
        ), 400
    if image is None or not image.filename:
        return jsonify(
            {"status": "error", "message": "A photo is required to create a recovery quiz."}
        ), 400

    suffix = Path(secure_filename(image.filename)).suffix.lower()
    if suffix not in ALLOWED_IMAGE_EXTENSIONS or not image.mimetype.startswith("image/"):
        return jsonify({"status": "error", "message": "Upload a supported image file."}), 400

    try:
        with tempfile.TemporaryDirectory(dir=UPLOAD_DIR) as temp_dir:
            staged_image = Path(temp_dir) / f"item{suffix}"
            image.save(staged_image)

            try:
                descriptions = FoundItemDescriber().describe_image(staged_image)
                quiz = OwnershipQuizGenerator().generate_quiz(
                    descriptions["detailed_description"], staged_image
                )
            except Exception:
                app.logger.exception("Gemini could not process the uploaded item.")
                return jsonify(
                    {
                        "status": "error",
                        "message": "Could not analyze the item photo. Please try again.",
                    }
                ), 502

            record = storage.add_item(
                title=title,
                category=category,
                location_description=location,
                vague_description=reported_description,
                detailed_description=descriptions["detailed_description"],
                quiz_question=quiz["question"],
                grading_guide=quiz["grading_guide"],
                expected_details=quiz["expected_details"],
                about_item=descriptions["public_description"],
                image_path=staged_image,
            )
    except Exception:
        app.logger.exception("Could not save the uploaded item.")
        return jsonify(
            {"status": "error", "message": "Could not save the item. Please try again."}
        ), 500

    return jsonify({"status": "success", "data": public_item(record)}), 201


@app.route("/api/items/<item_id>/quiz", methods=["GET"])
def get_item_quiz(item_id: str):
    record = storage.get_item(item_id)
    if record is None:
        return jsonify({"status": "error", "message": "Item not found."}), 404

    try:
        details = json.loads(record["expected_details"] or "[]")
    except json.JSONDecodeError:
        details = []
    if (
        not record["quiz_question"]
        or not isinstance(details, list)
        or not details
    ):
        return jsonify(
            {
                "status": "error",
                "message": "This item does not have enough photo detail for a recovery quiz.",
            }
        ), 409

    return jsonify(
        {
            "status": "success",
            "data": {"question": record["quiz_question"]},
        }
    )


@app.route("/api/items/<item_id>/claims", methods=["POST"])
def grade_claim(item_id: str):
    record = storage.get_item(item_id)
    if record is None:
        return jsonify({"status": "error", "message": "Item not found."}), 404

    if not request.is_json:
        return jsonify({"status": "error", "message": "A JSON response is required."}), 400
    body = request.get_json()
    if not isinstance(body, dict):
        return jsonify({"status": "error", "message": "A JSON answer is required."}), 400
    answer = body.get("answer", "")
    if not isinstance(answer, str) or not answer.strip():
        return jsonify({"status": "error", "message": "An answer is required."}), 400

    try:
        expected_details = json.loads(record["expected_details"] or "[]")
    except json.JSONDecodeError:
        expected_details = []
    is_demo = record.get("demo_mode") == "true"
    image_path = storage.get_image_path(item_id)
    if not isinstance(expected_details, list) or not expected_details:
        return jsonify(
            {
                "status": "error",
                "message": "This item does not have enough quiz evidence to verify a response.",
            }
        ), 409

    if is_demo:
        answer_text = " ".join(answer.lower().split())
        matched_details = sum(
            1
            for detail in expected_details
            if " ".join(detail.lower().split()) in answer_text
        )
        passed = matched_details >= 2
        return jsonify(
            {
                "status": "success",
                "data": {
                    "passed": passed,
                    "message": (
                        "Demo answer accepted. This is not a real ownership verification."
                        if passed
                        else "Demo answer not accepted. Include more of the item details."
                    ),
                },
            }
        )

    if not image_path:
        return jsonify(
            {
                "status": "error",
                "message": "This item cannot be verified because its photo evidence is unavailable.",
            }
        ), 409

    try:
        grade = OwnershipQuizGrader().grade_response(
            claimant_response=answer,
            detailed_description=record["detailed_description"],
            expected_details=expected_details,
            image_path=image_path,
            grading_guide=record["grading_guide"],
        )
    except (ValueError, RuntimeError):
        app.logger.exception("Gemini could not grade the ownership response.")
        return jsonify(
            {"status": "error", "message": "Could not verify this response. Please try again."}
        ), 502
    except Exception:
        app.logger.exception("Could not grade the ownership response.")
        return jsonify(
            {"status": "error", "message": "Could not verify this response. Please try again."}
        ), 500

    return jsonify(
        {
            "status": "success",
            "data": {
                "passed": grade["passed"],
                "message": (
                    "Your answer has been verified. Please contact the finder."
                    if grade["passed"]
                    else "Your answer could not be verified. Please contact the finder."
                ),
            },
        }
    )


@app.route("/api/items/<item_id>/comments", methods=["POST"])
def add_item_comment(item_id: str):
    if not request.is_json:
        return jsonify({"status": "error", "message": "A JSON comment is required."}), 400
    body = request.get_json()
    if not isinstance(body, dict):
        return jsonify({"status": "error", "message": "A JSON comment is required."}), 400
    comment = body.get("comment", "")
    if not isinstance(comment, str) or not comment.strip():
        return jsonify({"status": "error", "message": "Comment cannot be empty."}), 400

    try:
        record = storage.add_comment(item_id, comment)
    except KeyError:
        return jsonify({"status": "error", "message": "Item not found."}), 404
    except ValueError as error:
        return jsonify({"status": "error", "message": str(error)}), 400
    except Exception:
        app.logger.exception("Could not save item comment.")
        return jsonify(
            {"status": "error", "message": "Could not save the comment. Please try again."}
        ), 500

    return jsonify({"status": "success", "data": public_item(record)}), 201


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    app.run(host="0.0.0.0", port=5001, debug=False)
