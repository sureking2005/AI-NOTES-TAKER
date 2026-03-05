import json
import re


# ============================================================
# TEXT NORMALIZATION (Apply to BOTH reference and predicted)
# ============================================================

def normalize_text(text: str) -> str:
    """
    Normalize text before WER calculation.
    Handles Hinglish, punctuation, numbers, filler words.
    Apply to BOTH reference and predicted text equally.
    """

    # Lowercase everything
    text = text.lower()

    # -------------------------------------------------------
    # Number word → digit conversions (common in speech)
    # -------------------------------------------------------
    number_map = {
        r'\bzero point six\b': '0.6',
        r'\bfive thousand\b': '5000',
        r'\btwo seconds\b': '2 seconds',
        r'\bthree seconds\b': '3 seconds',
        r'\btwenty four hours\b': '24 hours',
        r'\bfive hundred\b': '500',
        r'\bone hundred\b': '100',
        r'\btwo weeks\b': '2 weeks',
        r'\bfive days\b': '5 days',
        r'\bnext five days\b': 'next 5 days',
        r'\bnext two weeks\b': 'next 2 weeks',
    }
    for pattern, replacement in number_map.items():
        text = re.sub(pattern, replacement, text)

    # -------------------------------------------------------
    # Remove filler words that STT sometimes adds/removes
    # -------------------------------------------------------
    fillers = [
        r'\bum\b', r'\buh\b', r'\bhmm\b', r'\byou know\b',
        r'\blike\b', r'\bokay\b', r'\bok\b', r'\bright\b',
        r'\bso\b', r'\bwell\b', r'\bjust\b',
    ]
    for filler in fillers:
        text = re.sub(filler, '', text)

    # -------------------------------------------------------
    # Normalize common Hinglish spellings
    # (STT may transcribe these slightly differently)
    # -------------------------------------------------------
    hinglish_map = {
        r'\bhaan\b': 'haan',
        r'\bhan\b': 'haan',
        r'\bbilkul\b': 'bilkul',
        r'\bbilkull\b': 'bilkul',
        r'\bkarte hain\b': 'karte hain',
        r'\bkarte hai\b': 'karte hain',
        r'\bho gaya\b': 'ho gaya',
        r'\bho gya\b': 'ho gaya',
        r'\bkarna hai\b': 'karna hai',
        r'\bkarna he\b': 'karna hai',
        r'\bchalo\b': 'chalo',
        r'\bchlo\b': 'chalo',
        r'\btheek hai\b': 'theek hai',
        r'\bthik hai\b': 'theek hai',
        r'\bkal tak\b': 'kal tak',
    }
    for pattern, replacement in hinglish_map.items():
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)

    # -------------------------------------------------------
    # Remove all punctuation
    # (STT transcript has different punctuation than reference)
    # -------------------------------------------------------
    text = re.sub(r'[^\w\s]', ' ', text)

    # -------------------------------------------------------
    # Collapse multiple spaces into one
    # -------------------------------------------------------
    text = re.sub(r'\s+', ' ', text)

    return text.strip()


# ============================================================
# WER-BASED TRANSCRIPT ACCURACY EVALUATION
# ============================================================

def evaluate_transcription(reference_text: str, predicted_text: str) -> float:
    """
    Calculate Word Error Rate (WER) accuracy.

    Steps:
    1. Normalize both texts (remove punctuation, lowercase, fix numbers)
    2. Calculate WER using jiwer
    3. Return accuracy = 1 - WER, clamped to 0-1

    Returns float between 0.0 and 1.0
    """
    from jiwer import wer

    # ✅ Normalize BOTH texts before comparison
    normalized_reference = normalize_text(reference_text)
    normalized_predicted = normalize_text(predicted_text)

    # ✅ Safety check — don't compare empty strings
    if not normalized_reference.strip():
        print("⚠️ Reference text is empty after normalization")
        return 0.0

    if not normalized_predicted.strip():
        print("⚠️ Predicted text is empty after normalization")
        return 0.0

    # ✅ Debug print to verify normalization is working
    print(f"\n📊 WER Evaluation:")
    print(f"   Reference (first 100 chars): {normalized_reference[:100]}")
    print(f"   Predicted (first 100 chars): {normalized_predicted[:100]}")

    error_rate = wer(normalized_reference, normalized_predicted)
    accuracy = 1.0 - error_rate

    # Clamp to 0-1 range (WER can exceed 1.0 for very bad transcripts)
    accuracy = max(0.0, min(1.0, accuracy))

    print(f"   WER: {error_rate:.3f} → Accuracy: {accuracy * 100:.2f}%")

    return round(accuracy, 3)


# ============================================================
# MOM QUALITY EVALUATION
# ============================================================

def evaluate_action_items(mom_data: dict) -> float:
    """
    Calculates MoM quality based on completeness of action items.

    Scoring per action item (max 3 points):
    - task exists and non-empty         → +1
    - owner is assigned (not Unassigned) → +1
    - due_date is specified              → +1

    Returns average completeness as float 0.0 to 1.0
    """
    action_items = mom_data.get("Action Items", [])

    if not action_items:
        return 0.0

    completeness_scores = []

    for item in action_items:
        if isinstance(item, dict):
            score = 0

            task = item.get("task", "")
            if task and len(task.strip()) > 0:
                score += 1

            owner = item.get("owner", "")
            if owner and owner not in ["Unassigned", "Not specified", "", "unassigned"]:
                score += 1

            due_date = item.get("due_date", "")
            if due_date and due_date not in ["Not specified", "", "not specified"]:
                score += 1

            completeness_scores.append(score / 3.0)

        else:
            # String item — give partial credit if non-empty
            completeness_scores.append(0.5 if str(item).strip() else 0.0)

    if completeness_scores:
        return round(sum(completeness_scores) / len(completeness_scores), 3)

    return 0.0