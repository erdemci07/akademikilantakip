from __future__ import annotations

import json

from .models import Analysis, CandidateProfile, Listing
from .settings import Settings

SCHEMA = {
    "name": "listing_eligibility", "strict": True,
    "schema": {
        "type": "object", "additionalProperties": False,
        "properties": {
            "category": {"type": "string", "enum": ["definitely_eligible", "conditional_eligible", "human_review", "ineligible"]},
            "summary": {"type": "string"}, "bachelors_match": {"type": "string"}, "masters_match": {"type": "string"},
            "ales_requirement": {"type": ["string", "null"]}, "language_requirement": {"type": ["string", "null"]},
            "experience_requirement": {"type": ["string", "null"]}, "needs_human_review": {"type": "boolean"},
            "evidence": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["category", "summary", "bachelors_match", "masters_match", "ales_requirement", "language_requirement", "experience_requirement", "needs_human_review", "evidence"],
    },
}


def without_ai() -> Analysis:
    return Analysis(
        category="human_review", summary="OpenAI analizi yapılandırılmadı; koşullar insan tarafından doğrulanmalı.",
        bachelors_match="belirsiz", masters_match="belirsiz", ales_requirement=None, language_requirement=None,
        experience_requirement=None, needs_human_review=True, evidence=[],
    )


def analyze_listing(
    listing: Listing,
    settings: Settings,
    profile: CandidateProfile | None = None,
) -> Analysis:
    if not settings.openai_api_key:
        return without_ai()
    profile = profile or CandidateProfile()
    from openai import OpenAI
    client = OpenAI(api_key=settings.openai_api_key)
    prompt = f"""Aday profili: Lisans={profile.bachelor}; tezli yüksek lisans={profile.masters}; ALES={profile.ales_score}; YDS/YÖKDİL={profile.language_score}.
İlan metni: {listing.text[:80_000]}
Sadece ilan metninde açıkça yazan bilgiyi kullan. Bölüm isimlerini otomatik eşdeğer sayma. ALES/dil puanı adayda yoksa kategori conditional_eligible; eğitim koşulu açıkça farklıysa ineligible; eğitim metni belirsizse human_review; tüm koşullar açıkça karşılanıyorsa definitely_eligible. Kanıt dizisine kısa metin parçaları koy."""
    response = client.responses.create(
        model=settings.openai_model,
        input=[{"role": "system", "content": "Temkinli bir akademik ilan değerlendirme asistanısın."}, {"role": "user", "content": prompt}],
        text={"format": {"type": "json_schema", "name": SCHEMA["name"], "strict": True, "schema": SCHEMA["schema"]}},
    )
    return Analysis(**json.loads(response.output_text))
