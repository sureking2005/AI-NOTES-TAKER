import uuid
import re
from typing import List, Dict, Tuple
from rapidfuzz import fuzz, process
from backend.app.services.azure_search import query_term
from backend.app.services.glossary import load_glossary_from_blob


# ===============================
# 🔧 TEXT NORMALIZATION
# ===============================
def normalize_text(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^\w\s\.]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


# ===============================
# 🧠 BUILD PHRASE INDEX
# ===============================
def build_phrase_index(glossary_dict: Dict[str, str]) -> Dict[str, str]:
    """
    Builds phrase-level dictionary.
    Ensures longest phrases matched first.
    """
    sorted_terms = sorted(glossary_dict.keys(), key=len, reverse=True)
    return {term: glossary_dict[term] for term in sorted_terms}


# ===============================
# ⚡ ENTERPRISE HYBRID CORRECTION
# ===============================
def correct_transcript_enterprise(
    transcript_segments: List[Dict],
    glossary_path: str = None,
    fuzzy_threshold: int = 88,
    azure_threshold: float = 1.5
) -> Tuple[List[Dict], List[Dict], Dict]:

    glossary_dict = {}
    if glossary_path:
        glossary_dict = load_glossary_from_blob("glossary", glossary_path)

    phrase_index = build_phrase_index(glossary_dict)

    correction_log = []
    total_checked = 0
    total_corrected = 0

    azure_cache = {}  # prevent repeated network calls

    corrected_segments = []

    for segment in transcript_segments:

        original_text = segment.get("text", "")

        # Safety guard
        if not isinstance(original_text, str):
            original_text = str(original_text)

        normalized_segment = normalize_text(original_text)

        total_checked += len(normalized_segment.split())

        # -------------------------------
        # 🔵 LAYER 1 — EXACT PHRASE MATCH
        # -------------------------------
        for wrong_phrase, correct_phrase in phrase_index.items():
            if wrong_phrase in normalized_segment:
                normalized_segment = normalized_segment.replace(
                    wrong_phrase,
                    correct_phrase
                )

                total_corrected += 1

                correction_log.append({
                    "id": str(uuid.uuid4()),
                    "original": wrong_phrase,
                    "corrected": correct_phrase,
                    "source": "exact_phrase",
                    "context": original_text
                })

        # -------------------------------
        # 🟡 LAYER 2 — FUZZY PHRASE MATCH
        # -------------------------------
        for wrong_phrase, correct_phrase in phrase_index.items():

            score = fuzz.partial_ratio(wrong_phrase, normalized_segment)

            if score >= fuzzy_threshold and wrong_phrase not in normalized_segment:
                normalized_segment = re.sub(
                    wrong_phrase,
                    correct_phrase,
                    normalized_segment
                )

                total_corrected += 1

                correction_log.append({
                    "id": str(uuid.uuid4()),
                    "original": wrong_phrase,
                    "corrected": correct_phrase,
                    "source": "fuzzy_match",
                    "confidence": score,
                    "context": original_text
                })

        # -------------------------------
        # 🟣 LAYER 3 — AZURE SEMANTIC FALLBACK
        # -------------------------------
        if not isinstance(normalized_segment, str):
            normalized_segment = str(normalized_segment)

        words = normalized_segment.split()
        rebuilt_words = []

        for word in words:

            if word in azure_cache:
                azure_match = azure_cache[word]
            else:
                azure_match = query_term(word, min_score=azure_threshold)
                azure_cache[word] = azure_match

            if azure_match:

    # Ensure string
                if isinstance(azure_match, dict):
                    azure_match = azure_match.get("correct_term")

                if isinstance(azure_match, str) and azure_match.lower() != word.lower():

                    rebuilt_words.append(azure_match)
                    total_corrected += 1

                    correction_log.append({
                        "id": str(uuid.uuid4()),
                        "original": word,
                        "corrected": azure_match,
                        "source": "azure_semantic",
                        "context": original_text
                    })
                else:
                    rebuilt_words.append(word)
            else:
                rebuilt_words.append(word)

        # -------------------------------
        # 🧹 LAYER 4 — DUPLICATE CLEANUP
        # -------------------------------
        cleaned_words = []
        for word in rebuilt_words:
            if not cleaned_words or cleaned_words[-1] != word:
                cleaned_words.append(word)

        final_text = " ".join(cleaned_words)

        segment["text"] = final_text
        corrected_segments.append(segment)

    stats = {
        "total_checked": total_checked,
        "total_corrected": total_corrected,
        "correction_rate": round(
            total_corrected / total_checked, 3
        ) if total_checked else 0
    }

    return corrected_segments, correction_log, stats