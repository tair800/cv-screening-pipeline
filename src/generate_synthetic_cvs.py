"""Generate a synthetic CV dataset for the screening pipeline.

Real CVs are personal data under GDPR and employer data is confidential, so this
project never touches either. Everything downstream is built and evaluated against
CVs produced here.

Synthetic data is not just the safe option — it is the more useful one:

  * Ground truth. Each CV is written out twice, once as the messy free text a parser
    will actually see and once as the structured record that extraction *should*
    return. Accuracy can then be measured instead of estimated.

  * Bias fixtures. A share of the dataset is emitted as matched pairs: two CVs with
    byte-identical qualifications whose only difference is a demographically coded
    name. If the scoring stage ranks a pair differently, that is disparate treatment,
    and the EU AI Act expects a high-risk system to test for it.

Generation is seeded, so the same seed always reproduces the same dataset.

Usage
-----
    python src/generate_synthetic_cvs.py                      # 60 CVs, seed 42
    python src/generate_synthetic_cvs.py --count 200 --seed 7
"""

from __future__ import annotations

import argparse
import json
import random
import shutil
from pathlib import Path

# --------------------------------------------------------------------------------------
# Source pools
#
# First names are grouped so matched pairs can vary one demographic signal at a time.
# The grouping exists solely to test the pipeline for disparate treatment; nothing in
# the pipeline is ever allowed to read these labels.
# --------------------------------------------------------------------------------------

FIRST_NAMES = {
    ("feminine", "western_european"): ["Anna", "Sophie", "Marta", "Elena", "Clara", "Julia"],
    ("masculine", "western_european"): ["Lukas", "Thomas", "Daniel", "Marco", "Peter", "Jonas"],
    ("feminine", "other_origin"): ["Aysel", "Leyla", "Nargiz", "Fatima", "Rania", "Zeynep"],
    ("masculine", "other_origin"): ["Tahir", "Kamran", "Emre", "Rashid", "Omar", "Murad"],
}

SURNAMES = {
    "western_european": ["Weber", "Novak", "Fischer", "Bakker", "Moreau", "Lindqvist"],
    "other_origin": ["Aslanli", "Mammadov", "Karimi", "Demir", "Haddad", "Rahimov"],
}

CITIES = [
    "Berlin, Germany", "Amsterdam, Netherlands", "Warsaw, Poland", "Lisbon, Portugal",
    "Baku, Azerbaijan", "Vienna, Austria", "Tallinn, Estonia", "Remote (EU)",
]

# Skills are split by tier so a CV's seniority and its skill set stay coherent.
CORE_SKILLS = ["Python", "SQL", "REST APIs", "Git", "JSON"]
AUTOMATION_SKILLS = ["n8n", "Make", "Zapier", "Power Automate", "UiPath", "Airflow"]
AI_SKILLS = ["OpenAI API", "Prompt engineering", "RAG", "LangChain", "Dataiku", "Hugging Face"]
DATA_SKILLS = ["Pandas", "PostgreSQL", "MongoDB", "Power BI", "dbt", "Snowflake"]
OPS_SKILLS = ["Docker", "CI/CD", "Kubernetes", "Terraform", "Azure", "AWS"]

COMPANIES = [
    "Northwind Logistics", "Baltic Insurance Group", "Meridian Retail", "Corvus Analytics",
    "Vela Financial", "Halcyon Health", "Orbit Manufacturing", "Lumen Telecom",
]

ROLES = [
    "Automation Engineer", "Data Analyst", "Backend Developer", "RPA Developer",
    "Integration Engineer", "AI Engineer", "Business Analyst", "Software Engineer",
]

DEGREES = ["BSc", "MSc", "BA", "MEng"]
FIELDS = [
    "Computer Science", "Information Systems", "Software Engineering",
    "Data Science", "Industrial Engineering", "Mathematics",
]
INSTITUTIONS = [
    "Technical University of Munich", "University of Amsterdam", "Warsaw University of Technology",
    "Baku State University", "University of Tartu", "Instituto Superior Técnico",
]

LANGUAGE_POOL = [
    "English (C1)", "English (B2)", "German (B1)", "Russian (C1)",
    "French (B2)", "Turkish (native)", "Polish (native)", "Azerbaijani (native)",
]


# --------------------------------------------------------------------------------------
# Profile construction
# --------------------------------------------------------------------------------------

def build_qualifications(rng: random.Random) -> dict:
    """Build the parts of a candidate that describe competence, not identity.

    Kept separate from name and contact details on purpose: a matched bias pair reuses
    one qualifications object across two identities, which guarantees the pair really
    is identical on everything that should matter.
    """
    years = rng.randint(0, 12)

    # Skill count grows with experience so juniors do not claim twelve technologies.
    skills = rng.sample(CORE_SKILLS, k=rng.randint(2, len(CORE_SKILLS)))
    skills += rng.sample(AUTOMATION_SKILLS, k=rng.randint(1, 3))
    if years >= 2:
        skills += rng.sample(AI_SKILLS, k=rng.randint(1, 3))
    if years >= 3:
        skills += rng.sample(DATA_SKILLS, k=rng.randint(1, 2))
    if years >= 5:
        skills += rng.sample(OPS_SKILLS, k=rng.randint(1, 2))
    skills = sorted(set(skills))

    # Work history is walked backwards from the present so the timeline stays consistent.
    experience = []
    current_year = 2026
    remaining = years
    while remaining > 0:
        stint = min(remaining, rng.randint(1, 4))
        start = current_year - stint
        experience.append({
            "company": rng.choice(COMPANIES),
            "role": rng.choice(ROLES),
            "start_year": start,
            "end_year": current_year if len(experience) else None,  # None == "Present"
        })
        current_year = start
        remaining -= stint

    graduation = 2026 - years - rng.randint(0, 2)

    return {
        "years_experience": years,
        "skills": skills,
        "experience": experience,
        "education": {
            "degree": rng.choice(DEGREES),
            "field": rng.choice(FIELDS),
            "institution": rng.choice(INSTITUTIONS),
            "year": graduation,
        },
        "languages": rng.sample(LANGUAGE_POOL, k=rng.randint(2, 3)),
    }


def build_identity(rng: random.Random, gender_code: str, origin_code: str,
                   location: str | None = None) -> dict:
    """Build the identity half of a candidate: name, contact details, location.

    `location` can be pinned so that a matched pair differs on the name alone. If the
    two halves of a pair also sat in different cities, a score gap could be blamed on
    geography and the test would prove nothing.
    """
    first = rng.choice(FIRST_NAMES[(gender_code, origin_code)])
    last = rng.choice(SURNAMES[origin_code])
    slug = f"{first}.{last}".lower()
    return {
        "name": f"{first} {last}",
        "email": f"{slug}@example.com",          # example.com is reserved by RFC 2606
        "phone": f"+49 {rng.randint(150, 179)} {rng.randint(1000000, 9999999)}",
        "location": location if location is not None else rng.choice(CITIES),
    }


# --------------------------------------------------------------------------------------
# Rendering
#
# Three layouts, because a parser that only handles one tidy format is not a parser.
# Real CVs disagree about section names, ordering, and whether structure exists at all.
# --------------------------------------------------------------------------------------

def _format_period(entry: dict) -> str:
    end = entry["end_year"] or "Present"
    return f"{entry['start_year']} - {end}"


def render_classic(record: dict) -> str:
    lines = [
        record["name"].upper(),
        f"{record['location']} | {record['email']} | {record.get('phone', '')}".strip(" |"),
        "",
        "PROFESSIONAL SUMMARY",
        f"{record['years_experience']} years of experience across automation and data roles.",
        "",
        "SKILLS",
        ", ".join(record["skills"]),
        "",
        "WORK EXPERIENCE",
    ]
    for job in record["experience"]:
        lines.append(f"{job['role']} — {job['company']} ({_format_period(job)})")
    edu = record["education"]
    lines += [
        "",
        "EDUCATION",
        f"{edu['degree']} {edu['field']}, {edu['institution']}, {edu['year']}",
        "",
        "LANGUAGES",
        ", ".join(record["languages"]),
    ]
    return "\n".join(lines)


def render_compact(record: dict) -> str:
    contact = " / ".join(v for v in [record["email"], record.get("phone"), record["location"]] if v)
    jobs = "; ".join(
        f"{job['role']} at {job['company']} ({_format_period(job)})"
        for job in record["experience"]
    )
    edu = record["education"]
    return (
        f"{record['name']}\n{contact}\n\n"
        f"Experience ({record['years_experience']} yrs): {jobs}\n\n"
        f"Tech: {' | '.join(record['skills'])}\n\n"
        f"Education: {edu['degree']} {edu['field']} — {edu['institution']} ({edu['year']})\n"
        f"Languages: {', '.join(record['languages'])}\n"
    )


def render_verbose(record: dict) -> str:
    """Narrative layout: facts are buried in prose rather than under headings."""
    edu = record["education"]
    first_role = record["experience"][0] if record["experience"] else None
    opening = (
        f"My name is {record['name']} and I am based in {record['location']}. "
        f"Over the past {record['years_experience']} years I have worked mainly on "
        "automation and data integration problems"
    )
    opening += (
        f", most recently as {first_role['role']} at {first_role['company']}."
        if first_role else "."
    )
    history = " ".join(
        f"Between {job['start_year']} and {job['end_year'] or 'now'} I worked as "
        f"{job['role']} at {job['company']}."
        for job in record["experience"]
    )
    return (
        f"{opening}\n\n{history}\n\n"
        f"Day to day I work with {', '.join(record['skills'][:-1])} and {record['skills'][-1]}.\n\n"
        f"I hold a {edu['degree']} in {edu['field']} from {edu['institution']}, completed in {edu['year']}. "
        f"I speak {', '.join(record['languages'])}.\n\n"
        f"You can reach me at {record['email']}.\n"
    )


RENDERERS = {"classic": render_classic, "compact": render_compact, "verbose": render_verbose}


def apply_imperfections(record: dict, rng: random.Random) -> list[str]:
    """Drop optional fields on some CVs. Absent data is normal, and the pipeline
    has to distinguish 'not stated' from 'not qualified'."""
    dropped = []
    if rng.random() < 0.20:
        record.pop("phone", None)
        dropped.append("phone")
    if rng.random() < 0.10 and len(record["languages"]) > 1:
        record["languages"] = record["languages"][:1]
        dropped.append("languages(partial)")
    return dropped


# --------------------------------------------------------------------------------------
# Dataset assembly
# --------------------------------------------------------------------------------------

def generate(count: int, seed: int, out_root: Path) -> dict:
    rng = random.Random(seed)

    synthetic_dir = out_root / "synthetic"
    samples_dir = out_root / "samples"
    synthetic_dir.mkdir(parents=True, exist_ok=True)
    samples_dir.mkdir(parents=True, exist_ok=True)

    # Roughly a fifth of the dataset is reserved for matched bias pairs.
    pair_count = max(1, count // 10)
    paired_slots = pair_count * 2

    manifest = {
        "seed": seed,
        "count": count,
        "generator": "src/generate_synthetic_cvs.py",
        "note": "Fully synthetic. No real person, employer or CV is represented.",
        "cvs": [],
        "bias_pairs": [],
    }

    index = 1

    # --- matched pairs first -----------------------------------------------------------
    for pair_number in range(pair_count):
        pair_id = f"pair_{pair_number + 1:02d}"
        qualifications = build_qualifications(rng)          # shared, byte for byte
        layout = rng.choice(list(RENDERERS))                # shared, so format is not a variable
        location = rng.choice(CITIES)                       # shared, so geography is not a variable

        variants = [
            ("A", "feminine", "western_european"),
            ("B", "masculine", "other_origin"),
        ]
        pair_ids = []
        for variant, gender_code, origin_code in variants:
            cv_id = f"cv_{index:04d}"
            record = {"cv_id": cv_id,
                      **build_identity(rng, gender_code, origin_code, location=location),
                      **json.loads(json.dumps(qualifications))}
            dropped = []  # pairs stay complete: an imperfection on one side would break parity
            _write_cv(record, layout, dropped, synthetic_dir, samples_dir, index,
                      bias_pair_id=pair_id, variant=variant,
                      gender_code=gender_code, origin_code=origin_code)
            manifest["cvs"].append({"cv_id": cv_id, "layout": layout, "bias_pair_id": pair_id})
            pair_ids.append(cv_id)
            index += 1

        manifest["bias_pairs"].append({
            "pair_id": pair_id,
            "cv_ids": pair_ids,
            "expectation": "Identical qualifications. Any score difference is disparate treatment.",
        })

    # --- remaining independent CVs -----------------------------------------------------
    while index <= count:
        cv_id = f"cv_{index:04d}"
        gender_code = rng.choice(["feminine", "masculine"])
        origin_code = rng.choice(["western_european", "other_origin"])
        record = {"cv_id": cv_id, **build_identity(rng, gender_code, origin_code), **build_qualifications(rng)}
        layout = rng.choice(list(RENDERERS))
        dropped = apply_imperfections(record, rng)
        _write_cv(record, layout, dropped, synthetic_dir, samples_dir, index,
                  bias_pair_id=None, variant=None,
                  gender_code=gender_code, origin_code=origin_code)
        manifest["cvs"].append({"cv_id": cv_id, "layout": layout, "bias_pair_id": None})
        index += 1

    (synthetic_dir / "_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    shutil.copy(synthetic_dir / "_manifest.json", samples_dir / "_manifest.json")
    return manifest


def _write_cv(record: dict, layout: str, dropped: list[str], synthetic_dir: Path,
              samples_dir: Path, index: int, *, bias_pair_id, variant,
              gender_code: str, origin_code: str) -> None:
    """Write one CV as free text plus its ground-truth record."""
    text = RENDERERS[layout](record)

    ground_truth = dict(record)
    ground_truth["_meta"] = {
        "layout": layout,
        "dropped_fields": dropped,
        "bias_pair_id": bias_pair_id,
        "bias_variant": variant,
        # Demographic codes exist for parity testing only. The pipeline must never read them.
        "gender_code": gender_code,
        "origin_code": origin_code,
        "synthetic": True,
    }

    cv_id = record["cv_id"]
    (synthetic_dir / f"{cv_id}.txt").write_text(text, encoding="utf-8")
    (synthetic_dir / f"{cv_id}.json").write_text(
        json.dumps(ground_truth, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # Keep the first three in a committed folder so the repo is readable without running it.
    if index <= 3:
        (samples_dir / f"{cv_id}.txt").write_text(text, encoding="utf-8")
        (samples_dir / f"{cv_id}.json").write_text(
            json.dumps(ground_truth, indent=2, ensure_ascii=False), encoding="utf-8"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a synthetic CV dataset.")
    parser.add_argument("--count", type=int, default=60, help="number of CVs (default: 60)")
    parser.add_argument("--seed", type=int, default=42, help="random seed (default: 42)")
    parser.add_argument("--out", type=Path, default=Path(__file__).resolve().parents[1] / "data",
                        help="output root (default: ./data)")
    args = parser.parse_args()

    manifest = generate(args.count, args.seed, args.out)

    print(f"Generated {len(manifest['cvs'])} synthetic CVs (seed {manifest['seed']})")
    print(f"  full set : {args.out / 'synthetic'}")
    print(f"  samples  : {args.out / 'samples'}  (first 3, committed to git)")
    print(f"  bias pairs: {len(manifest['bias_pairs'])} matched pairs for parity testing")


if __name__ == "__main__":
    main()
