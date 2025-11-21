"""
Example: Using the Batch API for asynchronous processing.

This example demonstrates:
1. Creating a JSONL batch input file
2. Uploading it to the API
3. Creating a batch job
4. Monitoring batch progress
5. Downloading results
"""

import json
import time
from pathlib import Path
import requests


# Configuration
BASE_URL = "http://localhost:8000"
API_KEY = None  # Set this if you have API key authentication enabled


def create_batch_file(output_path: str = "batch_input.jsonl"):
    """Create a sample batch input JSONL file."""
    requests_data = [
        {
            "custom_id": "math-1",
            "method": "POST",
            "url": "/v1/chat/completions",
            "body": {
                "model": "claude-sonnet-4-5-20250929",
                "messages": [
                    {"role": "user", "content": "What is 25 * 47?"}
                ],
                "max_tokens": 100
            }
        },
        {
            "custom_id": "geography-1",
            "method": "POST",
            "url": "/v1/chat/completions",
            "body": {
                "model": "claude-sonnet-4-5-20250929",
                "messages": [
                    {"role": "user", "content": "What is the capital of Japan?"}
                ],
                "max_tokens": 100
            }
        },
        {
            "custom_id": "coding-1",
            "method": "POST",
            "url": "/v1/chat/completions",
            "body": {
                "model": "claude-sonnet-4-5-20250929",
                "messages": [
                    {"role": "user", "content": "Write a Python function to check if a number is prime."}
                ],
                "max_tokens": 500
            }
        },
        {
            "custom_id": "science-1",
            "method": "POST",
            "url": "/v1/chat/completions",
            "body": {
                "model": "claude-sonnet-4-5-20250929",
                "messages": [
                    {"role": "user", "content": "Explain photosynthesis in simple terms."}
                ],
                "max_tokens": 300
            }
        },
        {
            "custom_id": "history-1",
            "method": "POST",
            "url": "/v1/chat/completions",
            "body": {
                "model": "claude-sonnet-4-5-20250929",
                "messages": [
                    {"role": "user", "content": "Who was the first person to walk on the moon?"}
                ],
                "max_tokens": 100
            }
        },
    ]

    # Write to JSONL file
    with open(output_path, "w") as f:
        for req in requests_data:
            f.write(json.dumps(req) + "\n")

    print(f"✅ Created batch input file: {output_path}")
    print(f"   Contains {len(requests_data)} requests")
    return output_path


def upload_file(file_path: str):
    """Upload a JSONL file for batch processing."""
    url = f"{BASE_URL}/v1/files"

    headers = {}
    if API_KEY:
        headers["Authorization"] = f"Bearer {API_KEY}"

    with open(file_path, "rb") as f:
        files = {"file": (Path(file_path).name, f, "application/jsonl")}
        data = {"purpose": "batch"}

        response = requests.post(url, files=files, data=data, headers=headers)
        response.raise_for_status()

    file_obj = response.json()
    print(f"✅ Uploaded file: {file_obj['id']}")
    print(f"   Filename: {file_obj['filename']}")
    print(f"   Size: {file_obj['bytes']} bytes")
    return file_obj["id"]


def create_batch(file_id: str):
    """Create a batch job from an uploaded file."""
    url = f"{BASE_URL}/v1/batches"

    headers = {"Content-Type": "application/json"}
    if API_KEY:
        headers["Authorization"] = f"Bearer {API_KEY}"

    payload = {
        "input_file_id": file_id,
        "endpoint": "/v1/chat/completions",
        "completion_window": "24h",
        "metadata": {
            "description": "Example batch job",
            "created_by": "batch_example.py"
        }
    }

    response = requests.post(url, json=payload, headers=headers)
    response.raise_for_status()

    batch = response.json()
    print(f"✅ Created batch: {batch['id']}")
    print(f"   Status: {batch['status']}")
    print(f"   Total requests: {batch['request_counts']['total']}")
    return batch["id"]


def get_batch_status(batch_id: str):
    """Get the current status of a batch job."""
    url = f"{BASE_URL}/v1/batches/{batch_id}"

    headers = {}
    if API_KEY:
        headers["Authorization"] = f"Bearer {API_KEY}"

    response = requests.get(url, headers=headers)
    response.raise_for_status()

    return response.json()


def wait_for_completion(batch_id: str, poll_interval: int = 2, max_wait: int = 300):
    """Poll batch status until completion or timeout."""
    print(f"\n⏳ Waiting for batch {batch_id} to complete...")

    start_time = time.time()
    while time.time() - start_time < max_wait:
        batch = get_batch_status(batch_id)
        status = batch["status"]
        counts = batch["request_counts"]

        print(f"   Status: {status} | Completed: {counts['completed']}/{counts['total']} | Failed: {counts['failed']}")

        if status == "completed":
            print(f"✅ Batch completed successfully!")
            return batch
        elif status == "failed":
            print(f"❌ Batch failed!")
            return batch
        elif status in ["cancelled", "expired"]:
            print(f"⚠️  Batch {status}")
            return batch

        time.sleep(poll_interval)

    print(f"⏰ Timeout waiting for batch completion")
    return batch


def download_results(batch: dict, output_path: str = "batch_output.jsonl"):
    """Download batch results to a file."""
    if not batch.get("output_file_id"):
        print("❌ No output file available")
        return None

    url = f"{BASE_URL}/v1/files/{batch['output_file_id']}/content"

    headers = {}
    if API_KEY:
        headers["Authorization"] = f"Bearer {API_KEY}"

    response = requests.get(url, headers=headers)
    response.raise_for_status()

    with open(output_path, "wb") as f:
        f.write(response.content)

    print(f"✅ Downloaded results: {output_path}")
    return output_path


def parse_results(results_file: str):
    """Parse and display results from batch output."""
    print(f"\n📊 Results from {results_file}:")
    print("=" * 80)

    with open(results_file, "r") as f:
        for line in f:
            if not line.strip():
                continue

            result = json.loads(line)
            custom_id = result["custom_id"]
            response = result.get("response", {})
            status_code = response.get("status_code")

            print(f"\n🔹 Request: {custom_id}")
            print(f"   Status: {status_code}")

            if status_code == 200:
                body = response.get("body", {})
                if body and "choices" in body:
                    content = body["choices"][0]["message"]["content"]
                    print(f"   Response: {content[:150]}{'...' if len(content) > 150 else ''}")

                    if "usage" in body:
                        usage = body["usage"]
                        print(f"   Tokens: {usage['prompt_tokens']} prompt + {usage['completion_tokens']} completion = {usage['total_tokens']} total")
            else:
                error = result.get("error", {})
                print(f"   Error: {error.get('message', 'Unknown error')}")


def main():
    """Run the complete batch processing workflow."""
    print("🚀 Batch API Example")
    print("=" * 80)

    try:
        # Step 1: Create batch input file
        print("\n📝 Step 1: Creating batch input file...")
        batch_file = create_batch_file()

        # Step 2: Upload file
        print("\n📤 Step 2: Uploading file...")
        file_id = upload_file(batch_file)

        # Step 3: Create batch job
        print("\n🎯 Step 3: Creating batch job...")
        batch_id = create_batch(file_id)

        # Step 4: Wait for completion
        print("\n⏱️  Step 4: Monitoring batch progress...")
        batch = wait_for_completion(batch_id)

        # Step 5: Download results
        if batch["status"] == "completed":
            print("\n📥 Step 5: Downloading results...")
            results_file = download_results(batch)

            if results_file:
                parse_results(results_file)

        print("\n" + "=" * 80)
        print("✅ Batch processing complete!")

    except requests.exceptions.RequestException as e:
        print(f"\n❌ API Error: {e}")
        if hasattr(e.response, 'text'):
            print(f"   Response: {e.response.text}")
    except Exception as e:
        print(f"\n❌ Error: {e}")


if __name__ == "__main__":
    main()
