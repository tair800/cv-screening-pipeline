"""Rule-based extractor. Deterministic, free, and the bar the LLM extractor has to clear.

Usage:
    python src/extract_baseline.py data/samples/cv_0001.txt
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

SKILL_VOCABULARY = [
    "Python", "SQL", "REST APIs", "Git", "JSON",
    "n8n", "Make", "Zapier", "Power Automate", "UiPath", "Airflow",
    "OpenAI API", "Prompt engineering", "RAG", "LangChain", "Dataiku", "Hugging Face",
    "Pandas", "PostgreSQL", "MongoDB", "Power BI", "dbt", "Snowflake",
    "Docker", "CI/CD", "Kubernetes", "Terraform", "Azure", "AWS",
]

LANGUAGE_NAMES = [
    "English", "German", "Russian", "French", "Turkish", "Polish", "Azerbaijani",
]

DEGREE_CODES = ["BSc", "MSc", "BA", "MEng"]

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
PHONE_RE = re.compile(r"\+\d{1,3}[\s\d]{7,}")
YEARS_RE = re.compile(r"(\d{1,2})\s*(?:\+\s*)?(?:years|yrs)", re.IGNORECASE)
CLASSIC_JOB_RE = re.compile(r"^(.+?)\s+—\s+(.+?)\s+\((\d{4})\s*-\s*(\d{4}|Present)\)$", re.MULTILINE)
EDUCATION_RE = re.compile(
    r"\b(" + "|".join(DEGREE_CODES) + r")\s+(?:in\s+)?([A-Za-z ]+?)"
    r"(?:,|\s+from\s+|\s+—\s+)\s*([A-Za-z .é]+?)(?:,|\s+\()?\s*(\d{4})"
)
NAME_LINE_RE = re.compile(r"^(?:My name is\s+)?([A-Z][\w'-]+(?:\s+[A-Z][\w'-]+)+)")
LOCATION_RE = re.compile(r"(?:based in\s+)?([A-Z][\w' -]+,\s*[A-Z][\w' -]+|Remote \(EU\))")


def _find_skills(text: str) -> list[dict]:
    found = []
    seen = set()
    for skill in SKILL_VOCABULARY:
        match = re.search(re.escape(skill), text, re.IGNORECASE)
        if match and skill.lower() not in seen:
            seen.add(skill.lower())
            found.append({"name": skill, "evidence": match.group(0)})
    return found


def _find_name(text: str) -> str | None:
    first_line = text.strip().splitlines()[0] if text.strip() else ""
    if first_line.isupper():
        return first_line.title()
    match = NAME_LINE_RE.match(first_line)
    return match.group(1) if match else None


def _find_location(text: str) -> str | None:
    match = LOCATION_RE.search(text)
    return match.group(1).strip() if match else None


def _find_education(text: str) -> dict | None:
    match = EDUCATION_RE.search(text)
    if not match:
        return None
    return {
        "degree": match.group(1),
        "field": match.group(2).strip(),
        "institution": match.group(3).strip(),
        "year": int(match.group(4)),
    }


def _find_experience(text: str) -> list[dict]:
    jobs = []
    for role, company, start, end in CLASSIC_JOB_RE.findall(text):
        jobs.append({
            "role": role.strip(),
            "company": company.strip(),
            "start_year": int(start),
            "end_year": None if end == "Present" else int(end),
        })
    return jobs


def _find_languages(text: str) -> list[str]:
    return [
        match.group(0)
        for name in LANGUAGE_NAMES
        if (match := re.search(rf"{name}\s*\([^)]+\)", text))
    ]


def extract(cv_id: str, text: str) -> dict:
    email = EMAIL_RE.search(text)
    phone = PHONE_RE.search(text)
    years = YEARS_RE.search(text)

    return {
        "cv_id": cv_id,
        "name": _find_name(text),
        "email": email.group(0) if email else None,
        "phone": phone.group(0).strip() if phone else None,
        "location": _find_location(text),
        "years_experience": int(years.group(1)) if years else None,
        "skills": _find_skills(text),
        "education": _find_education(text),
        "experience": _find_experience(text),
        "languages": _find_languages(text),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the rule-based extractor on one CV.")
    parser.add_argument("cv_path", type=Path, help="path to a CV .txt file")
    args = parser.parse_args()

    text = args.cv_path.read_text(encoding="utf-8")
    record = extract(args.cv_path.stem, text)
    print(json.dumps(record, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
