import os
import json
import tempfile
from backend.app.services.azure_blob_storage import download_file_from_blob


def load_glossary_from_blob(container: str, blob_name: str) -> dict:
    """
    Downloads glossary JSON from Azure Blob,
    loads into dictionary,
    deletes temp file safely.
    """

    # Create temporary file
    with tempfile.NamedTemporaryFile(delete=False, suffix=".json") as tmp:
        temp_path = tmp.name

    # Download blob to temp file
    download_file_from_blob(container, blob_name, temp_path)

    # Load JSON
    with open(temp_path, "r", encoding="utf-8") as f:
        glossary_list = json.load(f)

    # Cleanup
    os.remove(temp_path)

    # Convert to dictionary
    return {
        item["wrong_term"].lower(): item["correct_term"]
        for item in glossary_list
    }   