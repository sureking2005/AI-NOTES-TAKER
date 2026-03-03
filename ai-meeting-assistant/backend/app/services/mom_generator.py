import ollama
import json
import re
from backend.app.schemas.schemas import MoMSchema


def generate_mom(transcript, glossary_text=""):
    """
    Enhanced MoM generation with better decision extraction
    Optimized for Hinglish content and multi-speaker meetings
    """

    # ===============================
    # Action Confidence Calculator
    # ===============================
    def calculate_action_confidence(task_text, owner, due_date):
        score = 0

        strong_verbs = [
            "will", "must", "shall", "agreed", "commit", "assigned",
            "push", "prepare", "optimize", "implement", "complete",
            "develop", "test", "fix", "build", "deploy"
        ]
        medium_verbs = ["should", "please", "need to", "can", "would like"]

        text_lower = task_text.lower()

        # Verb strength (40 points max)
        if any(v in text_lower for v in strong_verbs):
            score += 40
        elif any(v in text_lower for v in medium_verbs):
            score += 25
        else:
            score += 15

        # Owner clarity (25 points max)
        if owner and owner not in ["Not specified", "Unassigned", ""]:
            score += 25
        else:
            score += 5

        # Due date clarity (20 points max)
        if due_date and due_date not in ["Not specified", ""]:
            score += 20
        else:
            score += 5

        # Length clarity (15 points max)
        if len(task_text.split()) > 4:
            score += 15

        return min(score, 100)

    # ===============================
    # Format Transcript Cleanly
    # ===============================
    full_text = ""
    for seg in transcript:
        speaker = seg.get("speaker", "Speaker")
        text = seg.get("text", "")

        # Remove duplicate consecutive words
        words = text.split()
        cleaned = []
        for w in words:
            if not cleaned or cleaned[-1].lower() != w.lower():
                cleaned.append(w)

        text = " ".join(cleaned)
        full_text += f"{speaker}: {text}\n"

    if not full_text.strip():
        return json.dumps(MoMSchema().model_dump(by_alias=True))

    # ===============================
    # IMPROVED PROMPT for Better Extraction
    # ===============================
    prompt = f"""You are an expert meeting analyst specializing in technical and product meetings.
Your task is to extract comprehensive and accurate Minutes of Meeting (MoM) from the transcript.

CRITICAL INSTRUCTIONS:

1. DECISIONS: Extract what the team COMMITTED to or AGREED on:
   - Use phrases like: "will", "agreed to", "decided to", "committed to"
   - Examples: "We decided to use semantic embeddings", "Team agreed to optimize threshold"
   - Include: Strategic decisions, technology choices, approach changes

2. ACTION ITEMS: Extract specific tasks with:
   - task: WHAT needs to be done
   - owner: WHO will do it (extract from context: "I will", "she will", "team will")
   - due_date: WHEN (keep exact phrasing: "tomorrow", "next 5 days", "Friday")
   - priority: HIGH/MEDIUM/LOW based on urgency
   
   Examples from transcript:
   - "push updated UI build" → owner: speaker name, due: "tomorrow", priority: "High"
   - "prepare ML report" → owner: speaker name, due: "before demo", priority: "High"

3. RISKS: Extract potential problems or concerns:
   - Scalability issues
   - Technical challenges
   - Timing concerns
   - Resource constraints

4. DISCUSSION POINTS: What topics were discussed
   - ML pipeline improvements
   - Performance metrics
   - Security implementation
   - Demo preparation

5. SUMMARY: Group discussions by TOPICS (not chronologically)

IMPORTANT RULES:
- Do NOT fabricate information
- Keep deadlines EXACTLY as spoken
- If owner unclear, use "Team" or "Unassigned"
- Extract at least 3 decisions if meeting length > 2 minutes
- Extract at least 2 action items if mentioned
- Focus on COMMITMENTS and AGREEMENTS

Transcript:
{full_text}

Glossary (technical terms):
{glossary_text if glossary_text else "None provided"}

RESPOND ONLY WITH VALID JSON (no markdown, no explanations):
{{
  "Summary by Topics": [
    "Topic 1: Key discussion points about this topic",
    "Topic 2: What was discussed here",
    "Topic 3: Decisions or actions for this topic"
  ],
  "Key Discussion Points": [
    "Discussion point 1",
    "Discussion point 2",
    "Discussion point 3"
  ],
  "Decisions": [
    "Decision 1: What team decided or committed to",
    "Decision 2: Another clear decision made",
    "Decision 3: Strategic choice agreed upon"
  ],
  "Action Items": [
    {{
      "task": "Specific task description",
      "owner": "Person or team assigned",
      "due_date": "Exact deadline mentioned",
      "priority": "High|Medium|Low"
    }},
    {{
      "task": "Another action item",
      "owner": "Assigned person",
      "due_date": "When it's due",
      "priority": "High|Medium|Low"
    }}
  ],
  "Risks": [
    "Risk 1: Potential issue identified",
    "Risk 2: Challenge or blocker"
  ],
  "Open Questions": [
    "Question 1: Unresolved topic",
    "Question 2: What needs clarification"
  ]
}}"""

    # ===============================
    # Call Ollama with Optimized Settings
    # ===============================
    try:
        response = ollama.chat(
            model="neural-chat",  # ✅ Use neural-chat or dolphin-mixtral for better results
            messages=[{"role": "user", "content": prompt}],
            options={
                "temperature": 0.1,  # ✅ Lower for more structured output
                "top_p": 0.7,  # ✅ Reduced for consistency
                "num_predict": 3000,  # ✅ Longer output
                "repeat_penalty": 1.1  # ✅ Avoid repetition
            },
            format="json"
        )

        content = response["message"]["content"]

    except Exception as e:
        print(f"❌ Ollama error: {e}")
        print("Falling back to mistral model...")
        response = ollama.chat(
            model="mistral",
            messages=[{"role": "user", "content": prompt}],
            options={
                "temperature": 0.1,
                "top_p": 0.7,
                "num_predict": 3000
            },
            format="json"
        )
        content = response["message"]["content"]

    # ===============================
    # Safe JSON Parsing with Retry
    # ===============================
    try:
        mom_data = json.loads(content)
    except json.JSONDecodeError:
        print("❌ JSON PARSE FAILED - Attempting recovery")
        print("LLM OUTPUT:", content[:500])
        
        # Try to extract JSON from response
        match = re.search(r'\{.*\}', content, re.DOTALL)
        if match:
            try:
                mom_data = json.loads(match.group())
            except:
                print("❌ JSON recovery failed")
                return json.dumps(MoMSchema().model_dump(by_alias=True))
        else:
            return json.dumps(MoMSchema().model_dump(by_alias=True))

    # ===============================
    # Ensure Required Sections
    # ===============================
    mom_data.setdefault("Summary by Topics", [])
    mom_data.setdefault("Key Discussion Points", [])
    mom_data.setdefault("Decisions", [])
    mom_data.setdefault("Action Items", [])
    mom_data.setdefault("Risks", [])
    mom_data.setdefault("Open Questions", [])

    # ===============================
    # Filter Out Weak Decisions
    # ===============================
    filtered_decisions = []
    weak_words = ["can", "could", "may", "might", "possibly", "perhaps"]

    for decision in mom_data.get("Decisions", []):
        if isinstance(decision, dict):
            decision_text = decision.get("text", "")
        else:
            decision_text = str(decision)

        decision_text = decision_text.strip()
        lower = decision_text.lower()

        # Only filter if ONLY weak word is present
        has_weak = any(f" {w} " in f" {lower} " for w in weak_words)
        has_strong = any(v in lower for v in ["will", "decided", "agreed", "committed", "must"])

        if decision_text and (not has_weak or has_strong):
            filtered_decisions.append(decision_text)

    mom_data["Decisions"] = filtered_decisions

    # ===============================
    # Validate & Enhance Action Items
    # ===============================
    validated_actions = []

    for item in mom_data.get("Action Items", []):
        if isinstance(item, dict):
            task = item.get("task", "").strip()
            owner = item.get("owner", "Unassigned").strip()
            due_date = item.get("due_date", "Not specified").strip()
            priority = item.get("priority", "Medium").strip()

            # Only add non-empty tasks
            if task:
                confidence = calculate_action_confidence(task, owner, due_date)

                validated_actions.append({
                    "task": task,
                    "owner": owner if owner else "Unassigned",
                    "due_date": due_date if due_date else "Not specified",
                    "priority": priority if priority in ["High", "Medium", "Low"] else "Medium",
                    "confidence_score": confidence
                })

    mom_data["Action Items"] = validated_actions

    # ===============================
    # Normalize List Fields
    # ===============================
    def normalize_list_of_strings(field_name):
        if field_name in mom_data and isinstance(mom_data[field_name], list):
            normalized = []
            for item in mom_data[field_name]:
                if isinstance(item, dict):
                    # Extract first string value
                    for v in item.values():
                        if isinstance(v, str) and v.strip():
                            normalized.append(v.strip())
                            break
                else:
                    item_str = str(item).strip()
                    if item_str:
                        normalized.append(item_str)
            
            # Remove duplicates while preserving order
            seen = set()
            unique = []
            for item in normalized:
                if item.lower() not in seen:
                    seen.add(item.lower())
                    unique.append(item)
            
            mom_data[field_name] = unique

    # Normalize all list fields
    for field in ["Summary by Topics", "Key Discussion Points", "Decisions", "Risks", "Open Questions"]:
        normalize_list_of_strings(field)

    # ===============================
    # Schema Validation
    # ===============================
    try:
        validated = MoMSchema(**mom_data)
        return validated.model_dump_json(by_alias=True)
    except Exception as e:
        print(f"⚠️ Schema validation warning: {str(e)}")
        # Return as-is if schema validation fails
        return json.dumps(mom_data)