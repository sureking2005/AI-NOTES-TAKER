import uuid
import re
from typing import List, Dict
from backend.app.services.azure_search import query_term
from backend.app.services.glossary import load_glossary_from_blob


def clean_word(word: str) -> str:
    """
    Remove punctuation for matching.
    Keep original word for output.
    """
    return re.sub(r"[^\w]", "", word).lower()


def is_likely_duplicate(word: str, prev_word: str, threshold: int = 2) -> bool:
    """
    Check if word is a duplicate of previous word (within edit distance)
    """
    if not prev_word:
        return False
    
    # Exact match
    if clean_word(word).lower() == clean_word(prev_word).lower():
        return True
    
    # Similar length and similar characters (likely duplicate due to audio)
    if abs(len(word) - len(prev_word)) <= 1:
        same_chars = sum(1 for a, b in zip(word.lower(), prev_word.lower()) if a == b)
        if same_chars > len(word) - threshold:
            return True
    
    return False


def correct_transcript(transcript_segments, glossary_path=None):
    """
    ✅ IMPROVED: Correct transcript without creating duplicates
    
    Handles:
    - Glossary-based corrections
    - Azure Search lookups
    - Duplicate prevention
    - Better statistics
    """
    glossary_dict = {}
    
    if glossary_path:
        try:
            glossary_dict = load_glossary_from_blob("glossary", glossary_path)
        except Exception as e:
            print(f"⚠️ Warning: Could not load glossary: {e}")
            glossary_dict = {}
    
    corrected_segments = []
    correction_log = []
    
    total_checked = 0
    total_corrected = 0
    azure_cache = {}
    
    for segment in transcript_segments:
        original_text = segment.get("text", "")
        words = original_text.split()
        new_words = []
        prev_word = None
        last_correction = None
        
        for i, word in enumerate(words):
            total_checked += 1
            cleaned = clean_word(word)
            corrected_word = None
            source = None
            
            # ✅ STEP 1: Check if likely duplicate (from Azure Speech repetition)
            if is_likely_duplicate(word, prev_word):
                # Skip duplicate words from Azure Speech errors
                print(f"  [Skipping duplicate] '{word}' (prev: '{prev_word}')")
                continue
            
            # ✅ STEP 2: Try glossary first (most reliable)
            if cleaned in glossary_dict:
                corrected_word = glossary_dict[cleaned]
                source = "glossary"
            
            # ✅ STEP 3: Try Azure Search if glossary miss
            else:
                if cleaned in azure_cache:
                    azure_match = azure_cache[cleaned]
                else:
                    azure_match = query_term(cleaned, min_score=1.5)
                    azure_cache[cleaned] = azure_match
                
                if azure_match:
                    corrected_word = azure_match
                    source = "azure_search"
            
            # ✅ STEP 4: Apply correction or keep original
            if corrected_word and corrected_word.lower() != cleaned:
                # ✅ Avoid repeating the same correction back-to-back
                if last_correction and corrected_word.lower() == last_correction.lower():
                    # This correction was just applied, skip it
                    new_words.append(word)  # Keep original
                else:
                    total_corrected += 1
                    new_words.append(corrected_word)
                    last_correction = corrected_word
                    
                    correction_log.append({
                        "id": str(uuid.uuid4()),
                        "original": word,
                        "corrected": corrected_word,
                        "source": source,
                        "context": original_text[:100]  # First 100 chars of context
                    })
            else:
                new_words.append(word)
                last_correction = None
            
            prev_word = word
        
        # Update segment with corrected text
        new_segment = segment.copy()
        new_segment["text"] = " ".join(new_words)
        corrected_segments.append(new_segment)
    
    # Calculate statistics
    stats = {
        "total_checked": total_checked,
        "total_corrected": total_corrected,
        "correction_rate": round(total_corrected / total_checked, 3) if total_checked else 0
    }
    
    print(f"\n✅ Correction Summary:")
    print(f"   Total words checked: {total_checked}")
    print(f"   Total corrections: {total_corrected}")
    print(f"   Correction rate: {stats['correction_rate'] * 100:.1f}%")
    
    return corrected_segments, correction_log, stats