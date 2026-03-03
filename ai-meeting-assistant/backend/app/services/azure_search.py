import os
import uuid
import json
from datetime import datetime
from azure.search.documents import SearchClient
from azure.core.credentials import AzureKeyCredential

SEARCH_ENDPOINT = os.getenv("AZURE_SEARCH_ENDPOINT")
SEARCH_KEY = os.getenv("AZURE_SEARCH_KEY")
SEARCH_INDEX = os.getenv("AZURE_SEARCH_INDEX")

if not all([SEARCH_ENDPOINT, SEARCH_KEY, SEARCH_INDEX]):
    raise RuntimeError("Azure Search environment variables missing")

search_client = SearchClient(
    endpoint=SEARCH_ENDPOINT,
    index_name=SEARCH_INDEX,
    credential=AzureKeyCredential(SEARCH_KEY)
)


def query_term(term: str, min_score: float = 1.5):
    """
    Search for a term correction in Azure Search
    """
    try:
        results = search_client.search(
            search_text=term,
            search_fields=["wrong_term"],
            top=1
        )

        for result in results:
            score = result.get("@search.score", 0)
            correct_term = result.get("correct_term")

            if score >= min_score and isinstance(correct_term, str):
                return correct_term

        return None
    except Exception as e:
        print(f"❌ Error searching term: {e}")
        return None


def upload_glossary_to_search(glossary_list: list, meeting_id):
    """
    Auto push glossary to Azure Search
    """
    try:
        documents = []

        for item in glossary_list:
            documents.append({
                "id": str(uuid.uuid4()),
                "wrong_term": item["wrong_term"].lower(),
                "correct_term": item["correct_term"],
                "source_meeting_id": str(meeting_id)
                # ❌ REMOVED: "timestamp" field - not in Azure Search schema
            })

        if documents:
            search_client.upload_documents(documents)
            print(f"✅ Uploaded {len(documents)} glossary terms to Azure Search")
    except Exception as e:
        print(f"⚠️ Warning: Could not upload glossary to search: {e}")
        # Don't fail the meeting upload if search fails
        pass