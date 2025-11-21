"""
Batch job manager for processing batch requests.

Manages batch job lifecycle, background processing, and file-based persistence.
"""

import asyncio
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Callable, Awaitable
from datetime import datetime, timedelta
from threading import Lock

from src.models import (
    BatchJob,
    BatchRequest,
    BatchRequestLine,
    BatchResponseLine,
    RequestCounts,
    ChatCompletionResponse,
)
from src.file_storage import FileStorage
from src.constants import (
    BATCH_STORAGE_DIR,
    BATCH_CLEANUP_INTERVAL_MINUTES,
    BATCH_FILE_RETENTION_DAYS,
    BATCH_DEFAULT_TIMEOUT_HOURS,
)

logger = logging.getLogger(__name__)


class BatchManager:
    """Manages batch job processing with file-based persistence."""

    def __init__(
        self,
        file_storage: FileStorage,
        storage_dir: str = BATCH_STORAGE_DIR,
        cleanup_interval_minutes: int = BATCH_CLEANUP_INTERVAL_MINUTES,
    ):
        """Initialize batch manager.

        Args:
            file_storage: FileStorage instance for file operations
            storage_dir: Directory for batch state storage
            cleanup_interval_minutes: Interval for cleanup task
        """
        self.file_storage = file_storage
        self.storage_dir = Path(storage_dir)
        self.batches_dir = self.storage_dir / "batches"
        self.batches_dir.mkdir(parents=True, exist_ok=True)

        self.cleanup_interval_minutes = cleanup_interval_minutes
        self.lock = Lock()
        self._cleanup_task = None
        self._processing_tasks: Dict[str, asyncio.Task] = {}

        # Chat completion handler (will be set externally)
        self._chat_handler: Optional[
            Callable[[BatchRequestLine], Awaitable[ChatCompletionResponse]]
        ] = None

        logger.info(f"BatchManager initialized at {self.storage_dir}")

    def set_chat_handler(
        self, handler: Callable[[BatchRequestLine], Awaitable[ChatCompletionResponse]]
    ):
        """Set the chat completion handler for processing requests.

        Args:
            handler: Async function that processes a single batch request
        """
        self._chat_handler = handler

    def _save_batch(self, batch: BatchJob):
        """Save batch job to file.

        Args:
            batch: BatchJob to save
        """
        batch_path = self.batches_dir / f"{batch.id}.json"
        batch_path.write_text(batch.model_dump_json(indent=2))
        logger.debug(f"Saved batch {batch.id}")

    def _load_batch(self, batch_id: str) -> Optional[BatchJob]:
        """Load batch job from file.

        Args:
            batch_id: Batch ID to load

        Returns:
            BatchJob if found, None otherwise
        """
        batch_path = self.batches_dir / f"{batch_id}.json"
        if not batch_path.exists():
            return None

        try:
            data = json.loads(batch_path.read_text())
            return BatchJob(**data)
        except Exception as e:
            logger.error(f"Error loading batch {batch_id}: {e}")
            return None

    def create_batch(self, batch_request: BatchRequest) -> BatchJob:
        """Create a new batch job.

        Args:
            batch_request: Batch creation request

        Returns:
            Created BatchJob

        Raises:
            ValueError: If input file is invalid
        """
        # Validate input file exists and parse it
        try:
            requests = self.file_storage.parse_batch_input(batch_request.input_file_id)
        except Exception as e:
            raise ValueError(f"Invalid input file: {e}")

        # Create batch job
        expires_at = int(
            (datetime.now() + timedelta(hours=BATCH_DEFAULT_TIMEOUT_HOURS)).timestamp()
        )

        batch = BatchJob(
            endpoint=batch_request.endpoint,
            input_file_id=batch_request.input_file_id,
            completion_window=batch_request.completion_window,
            status="validating",
            expires_at=expires_at,
            metadata=batch_request.metadata,
            request_counts=RequestCounts(total=len(requests), completed=0, failed=0),
        )

        with self.lock:
            self._save_batch(batch)

        logger.info(f"Created batch {batch.id} with {len(requests)} requests")
        return batch

    def get_batch(self, batch_id: str) -> Optional[BatchJob]:
        """Get batch job by ID.

        Args:
            batch_id: Batch ID to retrieve

        Returns:
            BatchJob if found, None otherwise
        """
        with self.lock:
            return self._load_batch(batch_id)

    def list_batches(self, limit: int = 20) -> List[BatchJob]:
        """List all batch jobs.

        Args:
            limit: Maximum number of batches to return

        Returns:
            List of BatchJob objects
        """
        batches = []
        with self.lock:
            for batch_path in self.batches_dir.glob("*.json"):
                try:
                    data = json.loads(batch_path.read_text())
                    batch = BatchJob(**data)
                    batches.append(batch)
                except Exception as e:
                    logger.error(f"Error loading batch {batch_path}: {e}")

        # Sort by creation time (newest first)
        batches.sort(key=lambda b: b.created_at, reverse=True)
        return batches[:limit]

    async def start_processing(self, batch_id: str):
        """Start processing a batch job in the background.

        Args:
            batch_id: Batch ID to process
        """
        if self._chat_handler is None:
            raise RuntimeError("Chat handler not set. Call set_chat_handler() first.")

        batch = self.get_batch(batch_id)
        if batch is None:
            logger.error(f"Batch {batch_id} not found")
            return

        # Update status to in_progress
        batch.status = "in_progress"
        batch.in_progress_at = int(datetime.now().timestamp())
        with self.lock:
            self._save_batch(batch)

        # Create background task
        task = asyncio.create_task(self._process_batch(batch_id))
        self._processing_tasks[batch_id] = task

        logger.info(f"Started processing batch {batch_id}")

    async def _process_batch(self, batch_id: str):
        """Process batch requests sequentially.

        Args:
            batch_id: Batch ID to process
        """
        try:
            batch = self.get_batch(batch_id)
            if batch is None:
                logger.error(f"Batch {batch_id} not found")
                return

            # Parse input requests
            requests = self.file_storage.parse_batch_input(batch.input_file_id)
            logger.info(f"Processing {len(requests)} requests for batch {batch_id}")

            responses: List[BatchResponseLine] = []
            errors: List[Dict] = []

            # Process each request sequentially
            for idx, request_line in enumerate(requests, 1):
                try:
                    logger.debug(
                        f"Processing request {idx}/{len(requests)} (custom_id: {request_line.custom_id})"
                    )

                    # Process single request using the chat handler
                    response = await self._chat_handler(request_line)

                    # Create response line
                    response_line = BatchResponseLine(
                        custom_id=request_line.custom_id,
                        response={
                            "status_code": 200,
                            "request_id": response.id,
                            "body": response.model_dump(),
                        },
                    )
                    responses.append(response_line)

                    # Update batch counts
                    batch.request_counts.completed += 1

                except Exception as e:
                    logger.error(f"Error processing request {request_line.custom_id}: {e}")

                    # Create error response
                    error_response = BatchResponseLine(
                        custom_id=request_line.custom_id,
                        response={"status_code": 500, "body": None},
                        error={
                            "message": str(e),
                            "type": "processing_error",
                            "code": "batch_request_failed",
                        },
                    )
                    responses.append(error_response)
                    errors.append({"custom_id": request_line.custom_id, "error": str(e)})

                    # Update batch counts
                    batch.request_counts.failed += 1

                # Save batch state periodically (every 10 requests)
                if idx % 10 == 0:
                    with self.lock:
                        self._save_batch(batch)

            # Finalize batch
            batch.status = "finalizing"
            batch.finalizing_at = int(datetime.now().timestamp())
            with self.lock:
                self._save_batch(batch)

            # Save output files
            output_file_id = self.file_storage.save_batch_output(batch_id, responses)
            batch.output_file_id = output_file_id

            if errors:
                error_file_id = self.file_storage.save_batch_errors(batch_id, errors)
                batch.error_file_id = error_file_id

            # Mark as completed
            batch.status = "completed"
            batch.completed_at = int(datetime.now().timestamp())
            with self.lock:
                self._save_batch(batch)

            logger.info(
                f"Batch {batch_id} completed: {batch.request_counts.completed} succeeded, "
                f"{batch.request_counts.failed} failed"
            )

        except Exception as e:
            logger.error(f"Fatal error processing batch {batch_id}: {e}")

            # Mark batch as failed
            batch = self.get_batch(batch_id)
            if batch:
                batch.status = "failed"
                batch.failed_at = int(datetime.now().timestamp())
                with self.lock:
                    self._save_batch(batch)

        finally:
            # Remove from processing tasks
            if batch_id in self._processing_tasks:
                del self._processing_tasks[batch_id]

    def cancel_batch(self, batch_id: str) -> Optional[BatchJob]:
        """Cancel a batch job.

        Args:
            batch_id: Batch ID to cancel

        Returns:
            Updated BatchJob if found and cancelled, None otherwise
        """
        batch = self.get_batch(batch_id)
        if batch is None:
            return None

        # Can only cancel if validating, in_progress, or finalizing
        if batch.status not in ["validating", "in_progress", "finalizing"]:
            return batch

        # Cancel the processing task if it exists
        if batch_id in self._processing_tasks:
            task = self._processing_tasks[batch_id]
            task.cancel()
            del self._processing_tasks[batch_id]

        # Update batch status
        batch.status = "cancelled"
        batch.cancelled_at = int(datetime.now().timestamp())
        with self.lock:
            self._save_batch(batch)

        logger.info(f"Cancelled batch {batch_id}")
        return batch

    def start_cleanup_task(self):
        """Start the automatic cleanup task."""
        if self._cleanup_task is not None:
            return  # Already started

        async def cleanup_loop():
            try:
                while True:
                    await asyncio.sleep(self.cleanup_interval_minutes * 60)
                    self._cleanup_old_batches()
            except asyncio.CancelledError:
                logger.info("Batch cleanup task cancelled")
                raise

        try:
            loop = asyncio.get_running_loop()
            self._cleanup_task = loop.create_task(cleanup_loop())
            logger.info(
                f"Started batch cleanup task (interval: {self.cleanup_interval_minutes} minutes)"
            )
        except RuntimeError:
            logger.warning("No running event loop, automatic batch cleanup disabled")

    def _cleanup_old_batches(self):
        """Remove old completed/failed/cancelled batches."""
        cutoff_time = datetime.now().timestamp() - (BATCH_FILE_RETENTION_DAYS * 24 * 3600)
        deleted_count = 0

        with self.lock:
            for batch_path in self.batches_dir.glob("*.json"):
                try:
                    data = json.loads(batch_path.read_text())
                    batch = BatchJob(**data)

                    # Only cleanup completed, failed, cancelled, or expired batches
                    if batch.status in ["completed", "failed", "cancelled", "expired"]:
                        # Check if old enough
                        completion_time = (
                            batch.completed_at
                            or batch.failed_at
                            or batch.cancelled_at
                            or batch.expired_at
                            or batch.created_at
                        )

                        if completion_time < cutoff_time:
                            batch_path.unlink()
                            deleted_count += 1
                            logger.info(f"Cleaned up old batch {batch.id}")
                except Exception as e:
                    logger.error(f"Error cleaning up batch {batch_path}: {e}")

        if deleted_count > 0:
            logger.info(f"Cleaned up {deleted_count} old batches")

        # Also cleanup old files
        self.file_storage.cleanup_old_files()
