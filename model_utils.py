"""
Model name utilities for handling chat mode and progress markers via model suffix.

This module provides utilities for parsing model names to determine
whether chat mode should be activated and whether progress markers
should be shown based on model suffixes.
"""

from typing import Tuple
import logging

logger = logging.getLogger(__name__)


class ModelUtils:
    """Utilities for handling model names and mode detection."""
    
    CHAT_SUFFIX = "-chat"
    CHAT_PROGRESS_SUFFIX = "-chat-progress"
    
    @classmethod
    def parse_model_and_mode(cls, model_name: str) -> Tuple[str, bool, bool]:
        """
        Parse model name to extract base model, chat mode, and progress markers.
        
        Args:
            model_name: The full model name, potentially with suffixes
            
        Returns:
            tuple: (base_model_name, is_chat_mode, show_progress_markers)
            
        Examples:
            >>> ModelUtils.parse_model_and_mode("claude-3-5-sonnet-20241022")
            ("claude-3-5-sonnet-20241022", False, False)
            
            >>> ModelUtils.parse_model_and_mode("claude-3-5-sonnet-20241022-chat")
            ("claude-3-5-sonnet-20241022", True, False)
            
            >>> ModelUtils.parse_model_and_mode("claude-3-5-sonnet-20241022-chat-progress")
            ("claude-3-5-sonnet-20241022", True, True)
        """
        # Check for -chat-progress suffix first (it's more specific)
        if model_name.endswith(cls.CHAT_PROGRESS_SUFFIX):
            base_model = model_name[:-len(cls.CHAT_PROGRESS_SUFFIX)]
            logger.debug(f"Detected chat mode with progress markers: {model_name} -> base: {base_model}")
            return base_model, True, True
        
        # Check for -chat suffix
        if model_name.endswith(cls.CHAT_SUFFIX):
            base_model = model_name[:-len(cls.CHAT_SUFFIX)]
            logger.debug(f"Detected chat mode model: {model_name} -> base: {base_model}")
            return base_model, True, False
        
        # Standard model - no chat mode, no progress markers
        logger.debug(f"Standard model detected: {model_name}")
        return model_name, False, False
    
    @classmethod
    def create_chat_variant(cls, base_model: str) -> str:
        """
        Create chat mode variant name for a base model.
        
        Args:
            base_model: The base model name without suffix
            
        Returns:
            str: The chat mode variant with -chat suffix
            
        Example:
            >>> ModelUtils.create_chat_variant("claude-3-5-sonnet-20241022")
            "claude-3-5-sonnet-20241022-chat"
        """
        return f"{base_model}{cls.CHAT_SUFFIX}"
    
    @classmethod
    def create_chat_progress_variant(cls, base_model: str) -> str:
        """
        Create chat mode with progress markers variant name for a base model.
        
        Args:
            base_model: The base model name without suffix
            
        Returns:
            str: The chat mode variant with -chat-progress suffix
            
        Example:
            >>> ModelUtils.create_chat_progress_variant("claude-3-5-sonnet-20241022")
            "claude-3-5-sonnet-20241022-chat-progress"
        """
        return f"{base_model}{cls.CHAT_PROGRESS_SUFFIX}"
    
    @classmethod
    def is_chat_mode_model(cls, model_name: str) -> bool:
        """
        Quick check if a model name indicates chat mode.
        
        Args:
            model_name: The model name to check
            
        Returns:
            bool: True if model name ends with -chat or -chat-progress suffix
        """
        return model_name.endswith(cls.CHAT_SUFFIX) or model_name.endswith(cls.CHAT_PROGRESS_SUFFIX)