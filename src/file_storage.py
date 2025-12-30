"""
File storage manager for batch processing.

Handles upload, storage, retrieval, and cleanup of JSONL files for batch operations.
"""

import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime

from src.models import FileObject, BatchRequestLine, BatchResponseLine
from src.constants import (
    BATCH_STORAGE_DIR,
    BATCH_MAX_FILE_SIZE_MB,
    BATCH_FILE_RETENTION_DAYS,
)

logger = logging.getLogger(__name__)


class FileStorage:
    """Manages file storage for batch processing."""

    def __init__(self, storage_dir: str = BATCH_STORAGE_DIR):
        """Initialize file storage manager.

        Args:
            storage_dir: Base directory for file storage
        """
        self.storage_dir = Path(storage_dir)
        self.files_dir = self.storage_dir / "files"
        self.metadata_dir = self.storage_dir / "metadata"

        # Create directories if they don't exist
        self.files_dir.mkdir(parents=True, exist_ok=True)
        self.metadata_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"FileStorage initialized at {self.storage_dir}")

    def save_file(self, content: bytes, filename: str, purpose: str = "batch") -> FileObject:
        """Save uploaded file and return metadata.

        Args:
            content: File content as bytes
            filename: Original filename
            purpose: Purpose of the file (default: "batch")

        Returns:
            FileObject with metadata about the saved file

        Raises:
            ValueError: If file is too large or invalid
        """
        # Validate file size
        file_size = len(content)
        max_size_bytes = BATCH_MAX_FILE_SIZE_MB * 1024 * 1024
        if file_size > max_size_bytes:
            raise ValueError(
                f"File size {file_size} bytes exceeds maximum of {max_size_bytes} bytes"
            )

        # Create file object
        file_obj = FileObject(
            bytes=file_size, filename=filename, purpose=purpose, status="uploaded"
        )

        # Save file content
        file_path = self.files_dir / file_obj.id
        file_path.write_bytes(content)

        # Save metadata
        metadata_path = self.metadata_dir / f"{file_obj.id}.json"
        metadata_path.write_text(file_obj.model_dump_json(indent=2))

        logger.info(f"Saved file {file_obj.id} ({filename}) - {file_size} bytes")
        return file_obj

    def get_file_metadata(self, file_id: str) -> Optional[FileObject]:
        """Retrieve file metadata by ID.

        Args:
            file_id: File ID to retrieve

        Returns:
            FileObject if found, None otherwise
        """
        metadata_path = self.metadata_dir / f"{file_id}.json"
        if not metadata_path.exists():
            return None

        try:
            data = json.loads(metadata_path.read_text())
            return FileObject(**data)
        except Exception as e:
            logger.error(f"Error loading file metadata {file_id}: {e}")
            return None

    def get_file_content(self, file_id: str) -> Optional[bytes]:
        """Retrieve file content by ID.

        Args:
            file_id: File ID to retrieve

        Returns:
            File content as bytes if found, None otherwise
        """
        file_path = self.files_dir / file_id
        if not file_path.exists():
            return None

        try:
            return file_path.read_bytes()
        except Exception as e:
            logger.error(f"Error reading file content {file_id}: {e}")
            return None

    def parse_batch_input(self, file_id: str) -> List[BatchRequestLine]:
        """Parse JSONL batch input file into request lines.

        Args:
            file_id: ID of the uploaded JSONL file

        Returns:
            List of BatchRequestLine objects

        Raises:
            ValueError: If file not found or invalid JSONL format
        """
        content = self.get_file_content(file_id)
        if content is None:
            raise ValueError(f"File {file_id} not found")

        requests = []
        lines = content.decode("utf-8").strip().split("\n")

        for line_num, line in enumerate(lines, 1):
            if not line.strip():
                continue  # Skip empty lines

            try:
                data = json.loads(line)
                request = BatchRequestLine(**data)
                requests.append(request)
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSON on line {line_num}: {e}")
            except Exception as e:
                raise ValueError(f"Invalid batch request on line {line_num}: {e}")

        logger.info(f"Parsed {len(requests)} requests from file {file_id}")
        return requests

    def save_batch_output(self, batch_id: str, responses: List[BatchResponseLine]) -> str:
        """Save batch output as JSONL file.

        Args:
            batch_id: Batch job ID
            responses: List of response lines

        Returns:
            File ID of the saved output file
        """
        # Create output lines
        output_lines = []
        for response in responses:
            output_lines.append(response.model_dump_json())

        content = "\n".join(output_lines).encode("utf-8")
        filename = f"{batch_id}_output.jsonl"

        file_obj = self.save_file(content, filename, purpose="batch")
        file_obj.status = "processed"

        # Update metadata
        metadata_path = self.metadata_dir / f"{file_obj.id}.json"
        metadata_path.write_text(file_obj.model_dump_json(indent=2))

        logger.info(f"Saved batch output {file_obj.id} with {len(responses)} responses")
        return file_obj.id

    def save_batch_errors(self, batch_id: str, errors: List[Dict[str, Any]]) -> Optional[str]:
        """Save batch errors as JSONL file.

        Args:
            batch_id: Batch job ID
            errors: List of error dictionaries

        Returns:
            File ID of the saved error file, or None if no errors
        """
        if not errors:
            return None

        # Create error lines
        error_lines = []
        for error in errors:
            error_lines.append(json.dumps(error))

        content = "\n".join(error_lines).encode("utf-8")
        filename = f"{batch_id}_errors.jsonl"

        file_obj = self.save_file(content, filename, purpose="batch")
        file_obj.status = "error"

        # Update metadata
        metadata_path = self.metadata_dir / f"{file_obj.id}.json"
        metadata_path.write_text(file_obj.model_dump_json(indent=2))

        logger.info(f"Saved batch errors {file_obj.id} with {len(errors)} errors")
        return file_obj.id

    def list_files(self, purpose: Optional[str] = None) -> List[FileObject]:
        """List all files, optionally filtered by purpose.

        Args:
            purpose: Optional purpose filter (e.g., "batch")

        Returns:
            List of FileObject metadata
        """
        files = []
        for metadata_path in self.metadata_dir.glob("*.json"):
            try:
                data = json.loads(metadata_path.read_text())
                file_obj = FileObject(**data)
                if purpose is None or file_obj.purpose == purpose:
                    files.append(file_obj)
            except Exception as e:
                logger.error(f"Error loading file metadata {metadata_path}: {e}")

        # Sort by creation time (newest first)
        files.sort(key=lambda f: f.created_at, reverse=True)
        return files

    def cleanup_old_files(self) -> int:
        """Remove files older than retention period.

        Returns:
            Number of files deleted
        """
        cutoff_time = datetime.now().timestamp() - (BATCH_FILE_RETENTION_DAYS * 24 * 3600)
        deleted_count = 0

        for metadata_path in self.metadata_dir.glob("*.json"):
            try:
                data = json.loads(metadata_path.read_text())
                file_obj = FileObject(**data)

                if file_obj.created_at < cutoff_time:
                    # Delete file content
                    file_path = self.files_dir / file_obj.id
                    if file_path.exists():
                        file_path.unlink()

                    # Delete metadata
                    metadata_path.unlink()

                    deleted_count += 1
                    logger.info(f"Deleted old file {file_obj.id} ({file_obj.filename})")
            except Exception as e:
                logger.error(f"Error cleaning up file {metadata_path}: {e}")

        if deleted_count > 0:
            logger.info(f"Cleaned up {deleted_count} old files")

        return deleted_count

    def delete_file(self, file_id: str) -> bool:
        """Delete a specific file by ID.

        Args:
            file_id: File ID to delete

        Returns:
            True if deleted, False if not found
        """
        file_path = self.files_dir / file_id
        metadata_path = self.metadata_dir / f"{file_id}.json"

        deleted = False
        if file_path.exists():
            file_path.unlink()
            deleted = True

        if metadata_path.exists():
            metadata_path.unlink()
            deleted = True

        if deleted:
            logger.info(f"Deleted file {file_id}")

        return deleted
