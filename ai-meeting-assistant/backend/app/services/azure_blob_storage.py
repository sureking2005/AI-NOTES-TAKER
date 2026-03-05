import os
from azure.storage.blob import BlobServiceClient
from azure.core.exceptions import ResourceExistsError, ResourceNotFoundError
from fastapi import UploadFile


# ==========================================
# 🔐 Azure Storage Setup
# ==========================================
AZURE_STORAGE_CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING")

if not AZURE_STORAGE_CONNECTION_STRING:
    raise RuntimeError("Azure Storage connection string not configured")

blob_service_client = BlobServiceClient.from_connection_string(
    AZURE_STORAGE_CONNECTION_STRING
)

# ==========================================
# 📦 Ensure Container Exists
# ==========================================
def ensure_container_exists(container: str):
    container_client = blob_service_client.get_container_client(container)
    try:
        container_client.create_container()
        print(f"✅ Container '{container}' created.")
    except ResourceExistsError:
        # Container already exists — perfectly fine
        pass


# ==========================================
# ⬆️ Upload File to Blob
# ==========================================
def upload_file_to_blob(file: UploadFile, container: str, blob_name: str):
    # Ensure container exists (AUTO CREATE)
    ensure_container_exists(container)

    blob_client = blob_service_client.get_blob_client(
        container=container,
        blob=blob_name
    )

    file.file.seek(0)

    blob_client.upload_blob(
        file.file,
        overwrite=True,
        content_type=file.content_type or "application/octet-stream"
    )

    print(f"✅ Uploaded '{blob_name}' to container '{container}'")


# ==========================================
# ⬇️ Download File from Blob
# ==========================================
def download_file_from_blob(container: str, blob_name: str, download_path: str):

    blob_client = blob_service_client.get_blob_client(
        container=container,
        blob=blob_name
    )

    try:
        stream = blob_client.download_blob(
            max_concurrency=8,
            timeout=120
        )

        with open(download_path, "wb") as file:
            for chunk in stream.chunks():
                file.write(chunk)

        size = os.path.getsize(download_path) / (1024*1024)
        print(f"✅ Downloaded {blob_name} ({size:.2f} MB)")

    except ResourceNotFoundError:
        raise Exception(f"Blob '{blob_name}' not found in container '{container}'")