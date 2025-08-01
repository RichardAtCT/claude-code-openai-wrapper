"""
Model name utilities for handling chat mode via model suffix.

This module provides utilities for parsing model names to determine
whether chat mode should be activated based on a "-chat" suffix.
"""

from typing import Tuple
import logging

logger = logging.getLogger(__name__)


class ModelUtils:
    """Utilities for handling model names and chat mode detection."""
    
    CHAT_SUFFIX = "-chat"
    
    @classmethod
    def parse_model_and_mode(cls, model_name: str) -> Tuple[str, bool]:
        """
        Parse model name to extract base model and determine if chat mode.
        
        Args:
            model_name: The full model name, potentially with -chat suffix
            
        Returns:
            tuple: (base_model_name, is_chat_mode)
            
        Examples:
            >>> ModelUtils.parse_model_and_mode("claude-3-5-sonnet-20241022")
            ("claude-3-5-sonnet-20241022", False)
            
            >>> ModelUtils.parse_model_and_mode("claude-3-5-sonnet-20241022-chat")
            ("claude-3-5-sonnet-20241022", True)
        """
        if model_name.endswith(cls.CHAT_SUFFIX):
            base_model = model_name[:-len(cls.CHAT_SUFFIX)]
            logger.debug(f"Detected chat mode model: {model_name} -> base: {base_model}")
            return base_model, True
        
        logger.debug(f"Standard model detected: {model_name}")
        return model_name, False
    
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
    def is_chat_mode_model(cls, model_name: str) -> bool:
        """
        Quick check if a model name indicates chat mode.
        
        Args:
            model_name: The model name to check
            
        Returns:
            bool: True if model name ends with -chat suffix
        """
        return model_name.endswith(cls.CHAT_SUFFIX)