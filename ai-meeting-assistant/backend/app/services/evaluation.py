import json

def evaluate_action_items(mom_data):
    """
    Calculates MoM quality based on completeness of action items.
    
    Scoring:
    - Each action item has max 3 points (task, owner, due_date)
    - Score = avg completeness across all action items
    - If no action items, return 0.0
    """
    action_items = mom_data.get("Action Items", [])

    # ✅ FIX: Handle both dict and list formats
    if not action_items:
        return 0.0

    completeness_scores = []

    for item in action_items:
        # Handle both dict and string formats
        if isinstance(item, dict):
            score = 0

            # Task must exist and be non-empty
            task = item.get("task", "")
            if task and len(task.strip()) > 0:
                score += 1

            # Owner must exist and NOT be "Unassigned" or "Not specified"
            owner = item.get("owner", "")
            if owner and owner not in ["Unassigned", "Not specified", "", "unassigned"]:
                score += 1

            # Due date must exist and NOT be "Not specified"
            due_date = item.get("due_date", "")
            if due_date and due_date not in ["Not specified", "", "not specified"]:
                score += 1

            # Convert to percentage (0-100)
            completeness = score / 3.0
            completeness_scores.append(completeness)
        else:
            # If item is a string, give it some score since it has content
            if str(item).strip():
                completeness_scores.append(0.5)  # Partial credit for string items
            else:
                completeness_scores.append(0.0)

    # Return average completeness
    if completeness_scores:
        avg_score = sum(completeness_scores) / len(completeness_scores)
        return round(avg_score, 3)
    else:
        return 0.0


def evaluate_transcription(reference_text, predicted_text):
    """
    Calculate Word Error Rate (WER) accuracy.
    Returns accuracy score (1 - WER)
    
    Uses jiwer library for WER calculation.
    """
    from jiwer import wer
    
    error_rate = wer(reference_text, predicted_text)
    accuracy = 1 - error_rate
    
    # Clamp to 0-1 range
    accuracy = max(0.0, min(1.0, accuracy))
    
    return round(accuracy, 3)


# TEST: Run this to verify scoring works
if __name__ == "__main__":
    # Test case 1: Empty action items
    test1 = {
        "Action Items": []
    }
    print(f"Test 1 (Empty): {evaluate_action_items(test1)}")  # Should be 0.0
    
    # Test case 2: Complete action items
    test2 = {
        "Action Items": [
            {
                "task": "Fix bug in login",
                "owner": "Alice",
                "due_date": "Friday",
                "priority": "High",
                "confidence_score": 95
            },
            {
                "task": "Update documentation",
                "owner": "Bob",
                "due_date": "Next week",
                "priority": "Medium",
                "confidence_score": 85
            }
        ]
    }
    print(f"Test 2 (Complete): {evaluate_action_items(test2)}")  # Should be 1.0
    
    # Test case 3: Partial action items
    test3 = {
        "Action Items": [
            {
                "task": "Fix bug",
                "owner": "Alice",
                "due_date": "Not specified"
            }
        ]
    }
    print(f"Test 3 (Partial): {evaluate_action_items(test3)}")  # Should be 0.666
    
    # Test case 4: Unassigned items
    test4 = {
        "Action Items": [
            {
                "task": "Fix bug",
                "owner": "Unassigned",
                "due_date": "Not specified"
            }
        ]
    }
    print(f"Test 4 (Unassigned): {evaluate_action_items(test4)}")  # Should be 0.333