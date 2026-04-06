import os
import asyncio
import tempfile
import atexit
import shutil
import json
import logging
from typing import AsyncGenerator, Dict, Any, Optional, List
from pathlib import Path

logger = logging.getLogger(__name__)


class GeminiCodeCLI:
    def __init__(self, timeout: int = 600000, cwd: Optional[str] = None):
        self.timeout = timeout / 1000  # Convert ms to seconds
        self.temp_dir = None
        self.gemini_cli_path = os.getenv("GEMINI_CLI_PATH", "gemini")

        # If cwd is provided, use it
        if cwd:
            self.cwd = Path(cwd)
            if not self.cwd.exists():
                logger.error(f"ERROR: Specified working directory does not exist: {self.cwd}")
                raise ValueError(f"Working directory does not exist: {self.cwd}")
        else:
            # Create isolated temp directory
            self.temp_dir = tempfile.mkdtemp(prefix="gemini_code_workspace_")
            self.cwd = Path(self.temp_dir)
            logger.info(f"Using temporary isolated workspace: {self.cwd}")
            atexit.register(self._cleanup_temp_dir)

        # Gemini API Key from environment
        self.gemini_api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")

    async def verify_cli(self) -> bool:
        """Verify Gemini CLI is working and authenticated."""
        try:
            logger.info("Testing Gemini CLI...")
            # Run gemini --version to check if it's installed
            process = await asyncio.create_subprocess_exec(
                self.gemini_cli_path,
                "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()
            if process.returncode == 0:
                logger.info(f"✅ Gemini CLI verified: {stdout.decode().strip()}")
                return True
            else:
                logger.warning(f"⚠️ Gemini CLI verification failed: {stderr.decode().strip()}")
                return False
        except Exception as e:
            logger.error(f"Gemini CLI verification failed: {e}")
            logger.warning("Please ensure Gemini CLI is installed: npm install -g @google/gemini-cli")
            return False

    async def run_completion(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        stream: bool = True,
        session_id: Optional[str] = None,
        continue_session: bool = False,
        gemini_options: Optional[Dict] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Run Gemini Agent using the CLI and yield response chunks."""
        
        # Build command
        cmd = [self.gemini_cli_path, "--output-format", "stream-json"]
        
        # Add model if specified
        if gemini_options and gemini_options.get("model"):
            cmd.extend(["--model", gemini_options["model"]])
            
        # Handle session continuity
        if continue_session and session_id:
            cmd.extend(["--resume", session_id])
        elif session_id:
            # Try to resume by session ID if it looks like one
            cmd.extend(["--resume", session_id])
            
        # Add prompt
        cmd.extend(["--prompt", prompt])
        
        # Add system prompt as a separate instruction if supported or prepend to prompt
        if system_prompt:
            # Most CLIs don't have a direct flag for system prompt, 
            # so we prepend it to the prompt if needed, but for agentic CLI
            # we might just pass it as part of the context or use a flag if available.
            # For Gemini CLI, we can use a custom prompt file or just prepend.
            prompt = f"{system_prompt}\n\n{prompt}"
            # Update the last element (prompt)
            cmd[-1] = prompt

        logger.debug(f"Running Gemini CLI command: {' '.join(cmd)}")
        
        # Set up environment
        env = dict(os.environ)
        if self.gemini_api_key:
            env["GEMINI_API_KEY"] = self.gemini_api_key
            env["GOOGLE_API_KEY"] = self.gemini_api_key

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.cwd,
                env=env,
            )

            # Read stdout line by line (NDJSON)
            while True:
                line = await process.stdout.readline()
                if not line:
                    break
                    
                line_str = line.decode().strip()
                if not line_str:
                    continue
                    
                try:
                    event = json.loads(line_str)
                    yield event
                except json.JSONDecodeError:
                    logger.warning(f"Failed to parse Gemini CLI output: {line_str}")
                    
            await process.wait()
            if process.returncode != 0:
                stderr = await process.stderr.read()
                error_msg = stderr.decode().strip()
                logger.error(f"Gemini CLI exited with error code {process.returncode}: {error_msg}")
                yield {
                    "type": "error",
                    "subtype": "execution_failed",
                    "error_message": error_msg or f"Exit code {process.returncode}",
                }

        except Exception as e:
            logger.error(f"Gemini CLI execution error: {e}")
            yield {
                "type": "error",
                "subtype": "exception",
                "error_message": str(e),
            }

    def parse_message(self, messages: List[Dict[str, Any]]) -> Optional[str]:
        """Extract assistant text from Gemini CLI events."""
        text_parts = []
        for msg in messages:
            if msg.get("type") == "message" and "content" in msg:
                text_parts.append(msg["content"])
            elif msg.get("type") == "result" and "content" in msg:
                # Some versions might put final result in result event
                text_parts.append(msg["content"])
        
        return "".join(text_parts) if text_parts else None

    def extract_metadata(self, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Extract metadata from Gemini CLI events."""
        metadata = {
            "session_id": None,
            "total_cost_usd": 0.0,
            "duration_ms": 0,
            "num_turns": 0,
            "model": None,
            "usage": None,
            "stop_reason": None,
        }

        for msg in messages:
            if msg.get("type") == "init":
                metadata["session_id"] = msg.get("session_id")
                metadata["model"] = msg.get("model")
            elif msg.get("type") == "result":
                metadata.update({
                    "session_id": msg.get("session_id", metadata["session_id"]),
                    "usage": msg.get("usage"),
                    "duration_ms": msg.get("duration_ms", 0),
                    "total_cost_usd": msg.get("total_cost_usd", 0.0),
                    "stop_reason": msg.get("stop_reason"),
                })
        
        return metadata

    def map_stop_reason_openai(self, stop_reason: Optional[str]) -> str:
        """Map Gemini stop_reason to OpenAI finish_reason."""
        if stop_reason == "MAX_TOKENS":
            return "length"
        return "stop"

    def estimate_token_usage(
        self, prompt: str, completion: str, model: Optional[str] = None
    ) -> Dict[str, int]:
        """Estimate token usage."""
        prompt_tokens = max(1, len(prompt) // 4)
        completion_tokens = max(1, len(completion) // 4)
        return {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        }

    def _cleanup_temp_dir(self):
        """Clean up temporary directory."""
        if self.temp_dir and os.path.exists(self.temp_dir):
            try:
                shutil.rmtree(self.temp_dir)
            except Exception:
                pass
