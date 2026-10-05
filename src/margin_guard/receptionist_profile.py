from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


DEFAULT_PROFILE = Path(__file__).parent / "config" / "business_profile.example.json"


def load_profile() -> dict[str, Any]:
    path = Path(os.environ.get("BUSINESS_PROFILE", str(DEFAULT_PROFILE))).expanduser()
    try:
        profile = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Unable to load business profile at {path}: {exc}") from exc
    if not isinstance(profile, dict) or not str(profile.get("business_name", "")).strip():
        raise RuntimeError("Business profile must be an object with a business_name.")
    for key in ("languages", "hours", "service_area", "services", "faqs"):
        if not isinstance(profile.get(key, []), list):
            raise RuntimeError(f"Business profile field {key!r} must be a list.")
    return profile


def find_faqs(query: str) -> list[dict[str, str]]:
    q = query.casefold().strip()
    profile = load_profile()
    faqs = profile.get("faqs", [])
    if not q:
        return [{"question": str(item.get("question", "")), "answer": str(item.get("answer", ""))} for item in faqs[:10]]
    terms = set(q.split())
    scored = []
    for item in faqs:
        question = str(item.get("question", ""))
        answer = str(item.get("answer", ""))
        haystack = f"{question} {answer}".casefold()
        score = sum(1 for term in terms if term in haystack)
        if score:
            scored.append((score, {"question": question, "answer": answer}))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [item for _, item in scored[:5]]
