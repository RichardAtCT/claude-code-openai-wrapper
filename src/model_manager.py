"""
Dynamic Model Management for Claude Code OpenAI Wrapper.

Provides intelligent model discovery, validation, and caching to reduce
the need for manual model list updates while maintaining reliability.
"""

import asyncio
import logging
import time
from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor
import json
import os

from src.constants import CLAUDE_MODELS

logger = logging.getLogger(__name__)


@dataclass
class ModelInfo:
    """Information about a Claude model."""
    id: str
    family: str  # e.g., "claude-4.5", "claude-4.0"
    variant: str  # e.g., "sonnet", "haiku", "opus"
    available: bool = True
    last_validated: Optional[float] = None
    validation_error: Optional[str] = None


class ModelManager:
    """Manages Claude model discovery, validation, and caching."""
    
    def __init__(self, claude_cli=None):
        self.claude_cli = claude_cli
        self._model_cache: Dict[str, ModelInfo] = {}
        self._cache_timestamp: Optional[float] = None
        self._cache_duration_minutes = 60  # Cache for 1 hour
        self._validation_timeout_seconds = 10
        self._load_base_models()
    
    def _load_base_models(self):
        """Load base models from constants with metadata parsing."""
        for model_id in CLAUDE_MODELS:
            model_info = self._parse_model_id(model_id)
            self._model_cache[model_id] = model_info
        logger.info(f"Loaded {len(self._model_cache)} base models from constants")
    
    def _parse_model_id(self, model_id: str) -> ModelInfo:
        """Parse model ID to extract family and variant information."""
        parts = model_id.split('-')
        
        # Extract variant (sonnet, haiku, opus)
        variant = "unknown"
        for part in parts:
            if part in ["sonnet", "haiku", "opus"]:
                variant = part
                break
        
        # Extract family (4.5, 4.1, 4.0, etc.)
        family = "unknown"
        for i, part in enumerate(parts):
            if part.isdigit() and i + 1 < len(parts):
                next_part = parts[i + 1]
                if next_part.replace('.', '').isdigit():
                    family = f"claude-{part}.{next_part}"
                    break
                elif next_part.isdigit():
                    family = f"claude-{part}.{next_part}"
                    break
        
        return ModelInfo(
            id=model_id,
            family=family,
            variant=variant
        )
    
    async def discover_additional_models(self) -> List[str]:
        """
        Attempt to discover additional models by testing common patterns.
        This is experimental and may not find all models.
        """
        if not self.claude_cli:
            return []
        
        discovered = []
        
        # Common model patterns to test
        test_patterns = [
            # Claude 4.5 family
            "claude-sonnet-4-5-20241201",  # Potential future release
            "claude-haiku-4-5-20241201",
            "claude-opus-4-5-20250929",   # Already added but test for validation
            
            # Claude 4.2 family (hypothetical)
            "claude-sonnet-4-2-20241201",
            "claude-haiku-4-2-20241201",
            "claude-opus-4-2-20241201",
            
            # Common date patterns for recent months
            "claude-sonnet-4-5-20251101",
            "claude-sonnet-4-5-20251201",
        ]
        
        logger.info(f"Testing {len(test_patterns)} potential model patterns...")
        
        # Test patterns concurrently with timeout
        async def test_model(model_id: str) -> Optional[str]:
            try:
                # Quick validation test with timeout
                test_result = await asyncio.wait_for(
                    self._validate_single_model(model_id),
                    timeout=self._validation_timeout_seconds
                )
                if test_result:
                    return model_id
            except asyncio.TimeoutError:
                logger.debug(f"Model test timeout for {model_id}")
            except Exception as e:
                logger.debug(f"Model test failed for {model_id}: {e}")
            return None
        
        # Test up to 5 models concurrently to avoid overwhelming the API
        semaphore = asyncio.Semaphore(3)
        
        async def test_with_semaphore(model_id: str) -> Optional[str]:
            async with semaphore:
                return await test_model(model_id)
        
        results = await asyncio.gather(
            *[test_with_semaphore(pattern) for pattern in test_patterns],
            return_exceptions=True
        )
        
        # Collect successful discoveries
        for result in results:
            if isinstance(result, str):
                discovered.append(result)
                logger.info(f"Discovered new model: {result}")
        
        return discovered
    
    async def _validate_single_model(self, model_id: str) -> bool:
        """Validate a single model by attempting a minimal API call."""
        if not self.claude_cli:
            return False
        
        try:
            # Attempt a very short API call to test model availability
            messages = []
            async for message in self.claude_cli.run_completion(
                prompt="test",
                model=model_id,
                max_turns=1
            ):
                messages.append(message)
                # If we get any response, the model exists
                if messages:
                    return True
            
            return len(messages) > 0
            
        except Exception as e:
            error_str = str(e).lower()
            # Check for specific error patterns that indicate model doesn't exist
            if any(pattern in error_str for pattern in [
                "model not found",
                "invalid model",
                "model does not exist",
                "unknown model",
                "model not available"
            ]):
                return False
            
            # For other errors, assume model might exist but there's a different issue
            logger.debug(f"Validation error for {model_id}: {e}")
            return False
    
    async def validate_available_models(self, force_refresh: bool = False) -> List[str]:
        """
        Validate which models are currently available and cache the results.
        
        Args:
            force_refresh: If True, ignore cache and re-validate all models
            
        Returns:
            List of available model IDs
        """
        current_time = time.time()
        
        # Check if we need to refresh the cache
        if (not force_refresh and 
            self._cache_timestamp and 
            current_time - self._cache_timestamp < (self._cache_duration_minutes * 60)):
            # Return cached available models
            return [model_id for model_id, info in self._model_cache.items() if info.available]
        
        if not self.claude_cli:
            logger.warning("Claude CLI not available, returning all base models")
            return list(CLAUDE_MODELS)
        
        logger.info("Validating model availability...")
        
        # Validate existing models concurrently
        validation_tasks = []
        model_ids = list(self._model_cache.keys())
        
        async def validate_model(model_id: str) -> Tuple[str, bool, Optional[str]]:
            try:
                is_valid = await asyncio.wait_for(
                    self._validate_single_model(model_id),
                    timeout=self._validation_timeout_seconds
                )
                return model_id, is_valid, None
            except Exception as e:
                return model_id, False, str(e)
        
        # Limit concurrent validations to avoid overwhelming the API
        semaphore = asyncio.Semaphore(2)
        
        async def validate_with_semaphore(model_id: str) -> Tuple[str, bool, Optional[str]]:
            async with semaphore:
                return await validate_model(model_id)
        
        validation_results = await asyncio.gather(
            *[validate_with_semaphore(model_id) for model_id in model_ids],
            return_exceptions=True
        )
        
        # Update cache with validation results
        available_models = []
        for result in validation_results:
            if isinstance(result, tuple):
                model_id, is_valid, error = result
                if model_id in self._model_cache:
                    self._model_cache[model_id].available = is_valid
                    self._model_cache[model_id].last_validated = current_time
                    self._model_cache[model_id].validation_error = error
                    
                    if is_valid:
                        available_models.append(model_id)
                    elif error:
                        logger.debug(f"Model {model_id} unavailable: {error}")
        
        # Try to discover additional models
        try:
            discovered = await self.discover_additional_models()
            for model_id in discovered:
                if model_id not in self._model_cache:
                    self._model_cache[model_id] = self._parse_model_id(model_id)
                    self._model_cache[model_id].available = True
                    self._model_cache[model_id].last_validated = current_time
                    available_models.append(model_id)
        except Exception as e:
            logger.debug(f"Model discovery failed: {e}")
        
        self._cache_timestamp = current_time
        
        logger.info(f"Validation complete: {len(available_models)} models available")
        return available_models
    
    def get_available_models(self) -> List[str]:
        """Get currently cached available models (synchronous)."""
        return [model_id for model_id, info in self._model_cache.items() if info.available]
    
    def get_model_info(self, model_id: str) -> Optional[ModelInfo]:
        """Get detailed information about a specific model."""
        return self._model_cache.get(model_id)
    
    def get_models_by_family(self, family: str) -> List[str]:
        """Get all available models from a specific family."""
        return [
            model_id for model_id, info in self._model_cache.items()
            if info.available and info.family == family
        ]
    
    def get_models_by_variant(self, variant: str) -> List[str]:
        """Get all available models of a specific variant (sonnet, haiku, opus)."""
        return [
            model_id for model_id, info in self._model_cache.items()
            if info.available and info.variant == variant
        ]
    
    def add_custom_model(self, model_id: str) -> None:
        """Add a custom model to the cache (will be validated on next refresh)."""
        if model_id not in self._model_cache:
            self._model_cache[model_id] = self._parse_model_id(model_id)
            logger.info(f"Added custom model to cache: {model_id}")
    
    def get_cache_stats(self) -> Dict[str, any]:
        """Get statistics about the model cache."""
        total_models = len(self._model_cache)
        available_models = len([m for m in self._model_cache.values() if m.available])
        
        return {
            "total_models": total_models,
            "available_models": available_models,
            "last_validation": self._cache_timestamp,
            "cache_age_minutes": (
                (time.time() - self._cache_timestamp) / 60 
                if self._cache_timestamp else None
            ),
            "families": list(set(info.family for info in self._model_cache.values())),
            "variants": list(set(info.variant for info in self._model_cache.values())),
        }


# Global model manager instance (will be initialized with claude_cli)
model_manager: Optional[ModelManager] = None


def initialize_model_manager(claude_cli=None):
    """Initialize the global model manager."""
    global model_manager
    model_manager = ModelManager(claude_cli)
    return model_manager


def get_model_manager() -> Optional[ModelManager]:
    """Get the global model manager instance."""
    return model_manager