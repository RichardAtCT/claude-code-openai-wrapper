"""
Basic tests for batch API functionality.

Tests the core workflow: file upload → batch creation → status check → result retrieval
"""

import json
import pytest
from fastapi.testclient import TestClient
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.main import app

client = TestClient(app)


def create_test_batch_file():
    """Create a sample JSONL batch input file."""
    requests = [
        {
            "custom_id": "request-1",
            "method": "POST",
            "url": "/v1/chat/completions",
            "body": {
                "model": "claude-sonnet-4-5-20250929",
                "messages": [
                    {"role": "user", "content": "What is 2+2?"}
                ],
                "max_tokens": 100
            }
        },
        {
            "custom_id": "request-2",
            "method": "POST",
            "url": "/v1/chat/completions",
            "body": {
                "model": "claude-sonnet-4-5-20250929",
                "messages": [
                    {"role": "user", "content": "What is the capital of France?"}
                ],
                "max_tokens": 100
            }
        }
    ]

    # Convert to JSONL
    jsonl_content = "\n".join([json.dumps(req) for req in requests])
    return jsonl_content.encode('utf-8')


def test_file_upload():
    """Test uploading a JSONL file."""
    file_content = create_test_batch_file()

    response = client.post(
        "/v1/files",
        files={"file": ("test_batch.jsonl", file_content, "application/jsonl")},
        data={"purpose": "batch"}
    )

    assert response.status_code == 200, f"Upload failed: {response.json()}"

    data = response.json()
    assert "id" in data
    assert data["object"] == "file"
    assert data["purpose"] == "batch"
    assert data["filename"] == "test_batch.jsonl"
    assert data["bytes"] > 0

    return data["id"]


def test_batch_creation():
    """Test creating a batch job."""
    # First upload a file
    file_id = test_file_upload()

    # Create batch
    response = client.post(
        "/v1/batches",
        json={
            "input_file_id": file_id,
            "endpoint": "/v1/chat/completions",
            "completion_window": "24h"
        }
    )

    assert response.status_code == 200, f"Batch creation failed: {response.json()}"

    data = response.json()
    assert "id" in data
    assert data["object"] == "batch"
    assert data["input_file_id"] == file_id
    assert data["status"] in ["validating", "in_progress"]

    return data["id"]


def test_get_batch_status():
    """Test retrieving batch status."""
    # Create a batch first
    batch_id = test_batch_creation()

    # Get batch status
    response = client.get(f"/v1/batches/{batch_id}")

    assert response.status_code == 200, f"Get batch failed: {response.json()}"

    data = response.json()
    assert data["id"] == batch_id
    assert data["object"] == "batch"
    assert "status" in data
    assert "request_counts" in data


def test_list_batches():
    """Test listing all batches."""
    response = client.get("/v1/batches")

    assert response.status_code == 200, f"List batches failed: {response.json()}"

    data = response.json()
    assert data["object"] == "list"
    assert "data" in data
    assert isinstance(data["data"], list)


def test_get_file_metadata():
    """Test retrieving file metadata."""
    # Upload a file first
    file_id = test_file_upload()

    # Get file metadata
    response = client.get(f"/v1/files/{file_id}")

    assert response.status_code == 200, f"Get file failed: {response.json()}"

    data = response.json()
    assert data["id"] == file_id
    assert data["object"] == "file"
    assert data["purpose"] == "batch"


def test_file_not_found():
    """Test error handling for non-existent file."""
    response = client.get("/v1/files/file-nonexistent")

    assert response.status_code == 404


def test_batch_not_found():
    """Test error handling for non-existent batch."""
    response = client.get("/v1/batches/batch_nonexistent")

    assert response.status_code == 404


def test_invalid_batch_creation():
    """Test batch creation with invalid input file."""
    response = client.post(
        "/v1/batches",
        json={
            "input_file_id": "file-nonexistent",
            "endpoint": "/v1/chat/completions",
            "completion_window": "24h"
        }
    )

    assert response.status_code == 400  # Should fail validation


if __name__ == "__main__":
    print("Running basic batch API tests...")

    try:
        print("\n1. Testing file upload...")
        test_file_upload()
        print("   ✅ File upload works")

        print("\n2. Testing batch creation...")
        test_batch_creation()
        print("   ✅ Batch creation works")

        print("\n3. Testing batch status retrieval...")
        test_get_batch_status()
        print("   ✅ Batch status retrieval works")

        print("\n4. Testing list batches...")
        test_list_batches()
        print("   ✅ List batches works")

        print("\n5. Testing file metadata retrieval...")
        test_get_file_metadata()
        print("   ✅ File metadata retrieval works")

        print("\n6. Testing error handling...")
        test_file_not_found()
        test_batch_not_found()
        print("   ✅ Error handling works")

        print("\n7. Testing invalid requests...")
        test_invalid_batch_creation()
        print("   ✅ Input validation works")

        print("\n✅ All tests passed!")

    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)
