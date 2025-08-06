"""
Dynamic model discovery for Claude Code CLI.
Extracts available models from the Claude CLI binary at runtime.
"""

import subprocess
import re
import json
import os
import time
import logging
from typing import Set, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

# Fallback models
FALLBACK_MODELS = {
    "claude-sonnet-4-20250514",
    "claude-opus-4-20250514",
    "claude-opus-4-1-20250805",
    "claude-3-7-sonnet-20250219", 
    "claude-3-5-sonnet-20241022",
    "claude-3-5-haiku-20241022",
    "claude-3-sonnet-20240229",
}

# Cache settings
CACHE_FILE = Path.home() / ".claude-code-wrapper" / "model_cache.json"
CACHE_TTL_HOURS = 24  # Cache for 24 hours

# Model pattern to extract from binary
MODEL_PATTERN = re.compile(r'claude-(?:sonnet|opus|haiku|3)[^"\'\s]+-20\d{6}')


class ModelDiscovery:
    """Discovers available Claude models from the CLI binary."""
    
    def __init__(self):
        self._models: Optional[Set[str]] = None
        self._last_discovery_time: float = 0
        
    def get_models(self) -> Set[str]:
        """Get available models, using cache if available."""
        # Return cached models if still valid
        if self._models and self._is_cache_valid():
            logger.debug(f"Using cached models: {len(self._models)} models")
            return self._models
            
        # Try to load from file cache
        cached_models = self._load_cache()
        if cached_models:
            self._models = cached_models
            logger.info(f"Loaded {len(cached_models)} models from cache")
            return cached_models
            
        # Discover models from CLI
        discovered_models = self._discover_models()
        if discovered_models:
            self._models = discovered_models
            self._save_cache(discovered_models)
            logger.info(f"Discovered {len(discovered_models)} models from Claude CLI")
            return discovered_models
            
        # Fall back to hardcoded list
        logger.warning("Model discovery failed, using fallback models")
        self._models = FALLBACK_MODELS
        return FALLBACK_MODELS
    
    def _is_cache_valid(self) -> bool:
        """Check if in-memory cache is still valid."""
        if not self._last_discovery_time:
            return False
        elapsed_hours = (time.time() - self._last_discovery_time) / 3600
        return elapsed_hours < CACHE_TTL_HOURS
    
    def _load_cache(self) -> Optional[Set[str]]:
        """Load models from file cache if valid."""
        try:
            if not CACHE_FILE.exists():
                return None
                
            with open(CACHE_FILE, 'r') as f:
                data = json.load(f)
                
            timestamp = data.get('timestamp', 0)
            elapsed_hours = (time.time() - timestamp) / 3600
            
            if elapsed_hours >= CACHE_TTL_HOURS:
                logger.debug("Cache expired")
                return None
                
            models = set(data.get('models', []))
            self._last_discovery_time = timestamp
            return models if models else None
            
        except Exception as e:
            logger.debug(f"Failed to load cache: {e}")
            return None
    
    def _save_cache(self, models: Set[str]) -> None:
        """Save models to file cache."""
        try:
            CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
            
            data = {
                'timestamp': time.time(),
                'models': sorted(list(models))
            }
            
            with open(CACHE_FILE, 'w') as f:
                json.dump(data, f, indent=2)
                
            self._last_discovery_time = data['timestamp']
            logger.debug(f"Saved {len(models)} models to cache")
            
        except Exception as e:
            logger.warning(f"Failed to save cache: {e}")
    
    def _discover_models(self) -> Optional[Set[str]]:
        """Discover models from Claude CLI binary."""
        try:
            # Find Claude CLI location
            result = subprocess.run(
                ['which', 'claude'],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode != 0:
                logger.debug("Claude CLI not found in PATH")
                return None
                
            claude_path = result.stdout.strip()
            if not claude_path or not os.path.exists(claude_path):
                logger.debug("Invalid Claude CLI path")
                return None
            
            # Extract models from binary
            # Use grep with binary flag to search in binary files
            result = subprocess.run(
                ['grep', '-ao', r'claude-\(sonnet\|opus\|haiku\|3\)[^"\']*-20[0-9]\{6\}', claude_path],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode != 0:
                logger.debug("grep failed to extract models")
                return None
            
            # Parse models from output
            models = set()
            for line in result.stdout.strip().split('\n'):
                if line:
                    # Clean up any binary artifacts
                    match = MODEL_PATTERN.search(line)
                    if match:
                        models.add(match.group(0))
            
            # Validate we found reasonable number of models
            if len(models) < 3:  # Expect at least 3 models
                logger.warning(f"Only found {len(models)} models, seems insufficient")
                return None
                
            return models
            
        except subprocess.TimeoutExpired:
            logger.warning("Model discovery timed out")
            return None
        except Exception as e:
            logger.error(f"Model discovery failed: {e}")
            return None
    
    def clear_cache(self) -> None:
        """Clear the model cache."""
        self._models = None
        self._last_discovery_time = 0
        try:
            if CACHE_FILE.exists():
                CACHE_FILE.unlink()
                logger.info("Cleared model cache")
        except Exception as e:
            logger.warning(f"Failed to clear cache file: {e}")


# Global instance
_model_discovery = ModelDiscovery()


def get_supported_models() -> Set[str]:
    """Get the set of supported Claude models."""
    return _model_discovery.get_models()


def clear_model_cache() -> None:
    """Clear the model cache to force re-discovery."""
    _model_discovery.clear_cache()