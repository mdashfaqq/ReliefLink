"""Multilingual triage of free-text help requests.

Given a message like "We are trapped on the terrace, water rising, grandmother
needs insulin" this module returns:
  * needs      - which kinds of help are required (rescue, medical, water, food, shelter)
  * urgency    - a 0-100 score and a level (CRITICAL / HIGH / MEDIUM / LOW)
  * reasons    - the human-readable evidence behind the score, so coordinators
                 can trust or override it
  * people     - estimated number of people affected

Design goals:
  * Explainable: every point of urgency is traceable to a phrase in the message.
    In a disaster, a coordinator must be able to see *why* a request was ranked.
  * Works offline and instantly on a laptop: the default engine is a weighted
    lexicon with negation handling, covering English, Hindi (Devanagari and
    romanized) and Tamil (script and romanized).
  * Optional semantic layer: with USE_EMBEDDINGS=1, a multilingual sentence
    embedding model refines the need classification for phrasing the lexicon misses.
"""

from __future__ import annotations

import math
import os
import re
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Lexicons. Weights express how strongly a phrase signals the category.
# ---------------------------------------------------------------------------

NEED_LEXICON: dict[str, dict[str, float]] = {
    "rescue": {
        "trapped": 3, "stuck": 2.5, "stranded": 2.5, "marooned": 2.5, "rescue": 3,
        "on the roof": 3, "on roof": 3, "terrace": 2, "first floor": 1, "can't get out": 3,
        "cannot get out": 3, "evacuate": 2, "boat": 2, "water rising": 3, "water level rising": 3,
        "neck deep": 3, "chest deep": 3, "waist deep": 2, "submerged": 2, "drowning": 3,
        "washed away": 3, "swept away": 3, "waist level": 2, "live wire": 3, "electric wire": 3,
        "electric pole": 3, "pole fell": 3, "not answering": 1.5, "no response from": 1.5,
        "bachao": 3, "phanse": 3, "fanse": 3, "phas gaye": 3,
        "फंसे": 3, "फंस": 3, "बचाओ": 3, "बचाइए": 3, "नाव": 2, "छत पर": 3, "पानी बढ़": 3,
        "மாட்டி": 3, "சிக்கி": 3, "காப்பாற்று": 3, "படகு": 2, "மொட்டை மாடி": 2,
        "தண்ணீர் ஏறு": 3, "மாடியில்": 2,
    },
    "medical": {
        "injured": 3, "injury": 3, "bleeding": 3, "unconscious": 3, "fainted": 3, "fell on": 2,
        "asthma": 2.5, "inhaler": 2.5, "seizure": 3, "fits": 2,
        "fever": 2, "chest pain": 3, "heart attack": 3, "breathing": 2.5, "breathe": 2.5,
        "medicine": 2.5, "medicines": 2.5, "insulin": 3, "dialysis": 3, "oxygen": 3,
        "pregnant": 2, "labour": 3, "labor pain": 3, "delivery": 2, "doctor": 2.5,
        "ambulance": 3, "fracture": 3, "snake bite": 3, "snakebite": 3, "diarrhea": 2.5,
        "vomiting": 2, "bp": 1.5, "sugar patient": 2, "diabetic": 2, "wound": 2.5,
        "ghayal": 3, "dawai": 2.5, "davai": 2.5, "bimar": 2,
        "घायल": 3, "दवाई": 2.5, "दवा": 2.5, "डॉक्टर": 2.5, "बीमार": 2, "बुखार": 2,
        "காயம்": 3, "மருந்து": 2.5, "மருத்துவர்": 2.5, "டாக்டர்": 2.5, "காய்ச்சல்": 2,
        "ஆம்புலன்ஸ்": 3, "marundhu": 2.5,
    },
    "water": {
        "drinking water": 3, "clean water": 3, "no water to drink": 3, "water bottle": 2.5,
        "water bottles": 2.5, "thirsty": 3, "thirst": 2.5, "water to drink": 3,
        "peene ka paani": 3, "paani nahi": 2.5, "पीने का पानी": 3, "प्यास": 3,
        "குடிநீர்": 3, "குடிக்க தண்ணீர்": 3, "தாகம்": 3, "kudineer": 3, "thanni illa": 2.5,
    },
    "food": {
        "food": 3, "hungry": 3, "starving": 3, "no food": 3, "meals": 2.5, "rice": 1.5,
        "milk": 2, "baby food": 3, "ration": 2, "not eaten": 3, "haven't eaten": 3,
        "khana": 3, "bhookh": 3, "bhukh": 3, "खाना": 3, "भूख": 3, "भोजन": 3, "दूध": 2,
        "உணவு": 3, "சாப்பாடு": 3, "பசி": 3, "பால்": 2, "saapadu": 3, "sapadu": 3,
    },
    "shelter": {
        "shelter": 3, "homeless": 3, "house collapsed": 3, "house damaged": 2.5,
        "wall collapsed": 2.5, "roof collapsed": 3, "place to stay": 3, "nowhere to stay": 3,
        "relief camp": 2, "blanket": 2, "blankets": 2, "tent": 2,
        "आश्रय": 3, "रहने की जगह": 3, "घर गिर": 3, "कंबल": 2,
        "தங்க இடம்": 3, "வீடு இடிந்து": 3, "போர்வை": 2, "முகாம்": 2,
    },
}

# Phrases that indicate a threat to life right now (strongest urgency driver).
THREAT_CUES: dict[str, float] = {
    "unconscious": 18, "not breathing": 22, "can't breathe": 20, "cannot breathe": 20,
    "breathing difficulty": 16, "difficulty breathing": 16, "heavy bleeding": 18,
    "bleeding": 12, "chest pain": 16, "heart attack": 20, "drowning": 22,
    "water rising": 14, "water level rising": 14, "neck deep": 16, "chest deep": 14,
    "on the roof": 10, "on roof": 10, "on the terrace": 8, "trapped": 12, "can't get out": 12,
    "cannot get out": 12, "cannot open": 10, "swept away": 22, "fainted": 16, "bleeding heavily": 18,
    "fell on": 14, "electric pole": 16, "pole fell": 16, "seizure": 18, "not answering": 10,
    "no response from": 10, "oxygen support": 20, "labour": 22, "labor pain": 22, "cannot reach hospital": 10, "can't reach hospital": 10,
    "snake bite": 35, "snakebite": 35, "live wire": 16, "stranded": 8, "waist level": 10, "waist deep": 10, "electrocuted": 20, "electric shock": 18,
    "current shock": 18, "collapsed": 10, "dialysis": 12, "oxygen": 14,
    "washed away": 20, "fracture": 8,
    "बेहोश": 18, "सांस नहीं": 20, "खून": 12, "डूब": 20, "फंसे": 12, "पानी बढ़": 14, "छत पर": 8,
    "மயக்கம்": 18, "மூச்சு": 14, "இரத்தம்": 12, "மூழ்கி": 20, "மாட்டி": 12, "சிக்கி": 12,
    "தண்ணீர் ஏறு": 14,
}

VULNERABLE_CUES: dict[str, str] = {
    "newborn": "newborn", "infant": "infant", "baby": "baby", "child": "child",
    "children": "children", "kids": "children", "elderly": "elderly", "old man": "elderly",
    "old woman": "elderly", "old lady": "elderly", "grandmother": "elderly",
    "grandfather": "elderly", "senior citizen": "elderly", "pregnant": "pregnant woman",
    "disabled": "person with disability", "wheelchair": "person with disability",
    "bedridden": "bedridden person", "paralysed": "bedridden person", "paralyzed": "bedridden person",
    "diabetic": "chronic patient", "insulin": "chronic patient",
    "बच्चे": "children", "बच्चा": "child", "बुजुर्ग": "elderly", "गर्भवती": "pregnant woman",
    "குழந்தை": "child", "முதியவர்": "elderly", "வயதான": "elderly", "கர்ப்பிணி": "pregnant woman",
    "patti": "elderly", "thatha": "elderly",
}

CATEGORY_BASE = {"rescue": 45, "medical": 40, "water": 25, "food": 20, "shelter": 15, "other": 10}

# English negators precede the phrase; Hindi/Tamil negators usually follow it.
_NEG_BEFORE = re.compile(r"\b(no|not|none|without|never|nobody|no one)\b[\w\s']{0,14}$", re.I)
_NEG_AFTER = re.compile(r"^\s*(?:\S+\s+)?(?:nahi|nahin|नहीं|नही|இல்லை|illai|illa)(?![a-z])", re.I)

# Resources: "no food" / "உணவு இல்லை" means the person NEEDS food, so negation must
# not suppress these. Negation only applies to conditions ("no one is injured").
NON_NEGATABLE = {
    "medicine", "medicines", "insulin", "oxygen", "doctor", "ambulance", "boat",
    "food", "milk", "meals", "rice", "ration", "baby food", "drinking water", "clean water",
    "water bottle", "water bottles", "shelter", "blanket", "blankets", "tent", "place to stay",
    "dawai", "davai", "khana", "saapadu", "sapadu", "marundhu", "kudineer",
    "दवाई", "दवा", "डॉक्टर", "खाना", "भोजन", "दूध", "आश्रय", "कंबल", "नाव", "पीने का पानी",
    "peene ka paani", "inhaler",
    "மருந்து", "மருத்துவர்", "டாக்டர்", "உணவு", "சாப்பாடு", "பால்", "குடிநீர்", "போர்வை", "படகு",
}

_FLOOD_RE = re.compile(
    r"water\s+(?:is\s+|has\s+)?(?:rising|entering|entered|coming in|seeping in)"
    r"|water\s+(?:is\s+|has\s+)?(?:reached|up to|till|at)\s+(?:our\s+|my\s+|the\s+)?(chest|neck|waist|door|knee|first floor)"
    r"|(?:up to|till)\s+(?:our|my)\s+(chest|neck|waist)",
    re.I,
)
_DEEP = {"chest": 16, "neck": 20, "waist": 10, "door": 10, "knee": 4, "first floor": 12}

# Group settings imply many affected people even when no number is given.
_GROUP_RE = re.compile(r"relief camp|community hall|old age home|orphanage|shelter home|hostel", re.I)

_NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "twelve": 12, "fifteen": 15, "twenty": 20,
}
_PEOPLE_RE = re.compile(
    r"(\d{1,4}|" + "|".join(_NUMBER_WORDS) + r")\s*(?:\w+\s)?(people|persons|members|of us|families|family members|"
    r"residents|kids|children|log|लोग|पேர்|பேர்)",
    re.I,
)
_FAMILY_RE = re.compile(r"family of (\d{1,2}|" + "|".join(_NUMBER_WORDS) + r")", re.I)
_WAIT_RE = re.compile(r"(since (yesterday|last night|morning|\d+ (hours|days))|(\d+|two|three) days|"
                      r"(\d+|two|three|four|five|six) hours)", re.I)


def _has_latin(term: str) -> bool:
    return bool(re.search(r"[a-z]", term, re.I))


def _find(term: str, text: str) -> list[tuple[int, int]]:
    """Find a term. Latin terms need word boundaries; Indic scripts match as substrings
    because Tamil and Hindi attach suffixes directly to words."""
    if _has_latin(term):
        pattern = rf"(?<![a-z]){re.escape(term)}(?![a-z])"
    else:
        pattern = re.escape(term)
    return [m.span() for m in re.finditer(pattern, text, re.I)]


def _is_negated(text: str, start: int, end: int) -> bool:
    before = text[max(0, start - 22):start]
    after = text[end:end + 16]
    return bool(_NEG_BEFORE.search(before) or _NEG_AFTER.search(after))


def _matches(lexicon: dict, text: str) -> list[tuple[str, float]]:
    """Return (term, weight) for non-negated occurrences, skipping terms fully
    contained in a longer matched term (so 'water rising' doesn't also count 'water')."""
    hits, taken = [], []
    for term in sorted(lexicon, key=len, reverse=True):
        for s, e in _find(term, text):
            if any(s >= ts and e <= te for ts, te in taken):
                continue
            if term not in NON_NEGATABLE and _is_negated(text, s, e):
                continue
            taken.append((s, e))
            hits.append((term, lexicon[term]))
            break  # count each term once
    return hits


def detect_language(text: str) -> str:
    if re.search(r"[஀-௿]", text):
        return "ta"
    if re.search(r"[ऀ-ॿ]", text):
        return "hi"
    return "en"


def estimate_people(text: str) -> int:
    counts = []
    for m in _PEOPLE_RE.finditer(text):
        raw = m.group(1).lower()
        counts.append(_NUMBER_WORDS.get(raw) or int(raw))
    for m in _FAMILY_RE.finditer(text):
        raw = m.group(1).lower()
        counts.append(_NUMBER_WORDS.get(raw) or int(raw))
    if not counts and _GROUP_RE.search(text):
        return 20
    return max(counts) if counts else 1


@dataclass
class TriageResult:
    category: str
    needs: list[str]
    urgency: int
    level: str
    people: int
    language: str
    reasons: list[str] = field(default_factory=list)
    needs_review: bool = False   # low-confidence result: a human coordinator should check it

    def to_dict(self) -> dict:
        return self.__dict__.copy()


def level_for(score: float) -> str:
    if score >= 70:
        return "CRITICAL"
    if score >= 50:
        return "HIGH"
    if score >= 30:
        return "MEDIUM"
    return "LOW"


_embedder = None
_prototype_vecs = None
PROTOTYPES = {
    "rescue": "We are trapped by flood water and need to be rescued by boat",
    "medical": "Someone is sick or injured and needs a doctor or medicine urgently",
    "water": "We have no clean drinking water",
    "food": "We are hungry and have no food to eat",
    "shelter": "Our house is destroyed and we need a place to stay",
}


def _semantic_scores(text: str) -> dict[str, float] | None:
    """Cosine similarity to each category prototype, using a multilingual model.
    Returns None when embeddings are disabled or unavailable."""
    global _embedder, _prototype_vecs
    if os.getenv("USE_EMBEDDINGS") != "1":
        return None
    try:
        if _embedder is None:
            from sentence_transformers import SentenceTransformer
            _embedder = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
            _prototype_vecs = _embedder.encode(list(PROTOTYPES.values()), normalize_embeddings=True)
        v = _embedder.encode([text], normalize_embeddings=True)[0]
        return {cat: float(v @ p) for cat, p in zip(PROTOTYPES, _prototype_vecs)}
    except Exception:
        return None


def triage(text: str, report_count: int = 1) -> TriageResult:
    text = (text or "").strip()
    reasons: list[str] = []

    need_scores: dict[str, float] = {}
    need_terms: dict[str, list[str]] = {}
    for cat, lex in NEED_LEXICON.items():
        hits = _matches(lex, text)
        if hits:
            need_scores[cat] = sum(w for _, w in hits)
            need_terms[cat] = [t for t, _ in hits]

    semantic = _semantic_scores(text)
    if semantic:
        for cat, sim in semantic.items():
            if sim > 0.45:  # blend: semantic evidence can add a need the lexicon missed
                need_scores[cat] = need_scores.get(cat, 0) + (sim - 0.45) * 10

    flood = _FLOOD_RE.search(text)
    if flood:
        need_scores["rescue"] = need_scores.get("rescue", 0) + 3
        need_terms.setdefault("rescue", []).insert(0, flood.group(0))

    needs_review = False
    if not need_scores:
        # No known phrase matched: ask the statistical model, and flag for a human.
        from .classifier import predict_category
        guess = predict_category(text)
        if guess:
            need_scores[guess[0]] = 1.0
            reasons.append(f"{guess[0]}: inferred by ML model ({guess[1]:.0%} confidence)")
        needs_review = True

    needs = sorted(need_scores, key=need_scores.get, reverse=True)
    category = needs[0] if needs else "other"
    for cat in needs:
        if cat in need_terms:
            reasons.append(f"{cat}: " + ", ".join(f'"{t}"' for t in need_terms[cat][:3]))

    score = float(CATEGORY_BASE[category])
    # Secondary needs add a little: someone needing rescue AND medicine is worse off.
    score += sum(4 for c in needs[1:3])

    threat_hits = _matches(THREAT_CUES, text)
    if flood and not any(t in flood.group(0).lower() for t, _ in threat_hits):
        depth = next((g for g in flood.groups() if g), None)
        threat_hits.append((flood.group(0), _DEEP.get(depth.lower(), 12) if depth else 12))
    threat = min(40.0, sum(w for _, w in threat_hits))
    if threat_hits:
        score += threat
        reasons.append("life-threat cues: " + ", ".join(f'"{t}"' for t, _ in threat_hits[:4]))

    vulnerable = sorted({VULNERABLE_CUES[t] for t, _ in _matches({k: 1 for k in VULNERABLE_CUES}, text)})
    if vulnerable:
        score += min(16, 8 * len(vulnerable))
        reasons.append("vulnerable: " + ", ".join(vulnerable))

    people = estimate_people(text)
    if people > 1:
        score += min(10.0, 5 * math.log2(people))
        reasons.append(f"{people} people affected")

    if _WAIT_RE.search(text):
        score += 6
        reasons.append("waiting a long time")

    if report_count > 1:
        score += min(8, 3 * (report_count - 1))
        reasons.append(f"corroborated by {report_count} reports")

    # Safety floor: under-triage can cost a life, over-triage costs minutes.
    # Any explicit threat to life is ranked at least HIGH.
    if threat_hits:
        score = max(score, 55.0)
    # An unrecognized message is not the same as an unimportant one: it goes to
    # the human review queue at MEDIUM or above instead of sinking to the bottom.
    if needs_review:
        score = max(score, 30.0)
        reasons.append("unrecognized wording: flagged for human review")

    urgency = int(round(min(100.0, score)))
    return TriageResult(
        category=category, needs=needs or ["other"], urgency=urgency, level=level_for(urgency),
        people=people, language=detect_language(text), reasons=reasons, needs_review=needs_review,
    )
