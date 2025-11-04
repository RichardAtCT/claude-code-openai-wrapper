import os
import logging
from typing import Optional, Dict, Any, Tuple
from fastapi import HTTPException, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from dotenv import load_dotenv

logger = logging.getLogger(__name__)
load_dotenv()


class ClaudeCodeAuthManager:
    """Manages authentication for Claude Code SDK integration."""
    
    def __init__(self):
        self.env_api_key = os.getenv("API_KEY")  # Environment API key
        self.auth_method = self._detect_auth_method()
        self.auth_status = self._validate_auth_method()
    
    def get_api_key(self):
        """Get the active API key (environment or runtime-generated)."""
        # Try to import runtime_api_key from main module
        try:
            from src import main
            if hasattr(main, 'runtime_api_key') and main.runtime_api_key:
                return main.runtime_api_key
        except ImportError:
            pass
        
        # Fall back to environment variable
        return self.env_api_key
    
    def _detect_auth_method(self) -> str:
        """Detect which Claude Code authentication method is configured."""
        if os.getenv("CLAUDE_CODE_USE_BEDROCK") == "1":
            return "bedrock"
        elif os.getenv("CLAUDE_CODE_USE_VERTEX") == "1":
            return "vertex"
        elif os.getenv("ANTHROPIC_API_KEY"):
            return "anthropic"
        else:
            # If no explicit method, assume Claude Code CLI is already authenticated
            return "claude_cli"
    
    def _validate_auth_method(self) -> Dict[str, Any]:
        """Validate the detected authentication method."""
        method = self.auth_method
        status = {
            "method": method,
            "valid": False,
            "errors": [],
            "config": {}
        }
        
        if method == "anthropic":
            status.update(self._validate_anthropic_auth())
        elif method == "bedrock":
            status.update(self._validate_bedrock_auth())
        elif method == "vertex":
            status.update(self._validate_vertex_auth())
        elif method == "claude_cli":
            status.update(self._validate_claude_cli_auth())
        else:
            status["errors"].append("No Claude Code authentication method configured")
        
        return status
    
    def _validate_anthropic_auth(self) -> Dict[str, Any]:
        """Validate Anthropic API key authentication."""
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            return {
                "valid": False,
                "errors": ["ANTHROPIC_API_KEY environment variable not set"],
                "config": {}
            }
        
        if len(api_key) < 10:  # Basic sanity check
            return {
                "valid": False,
                "errors": ["ANTHROPIC_API_KEY appears to be invalid (too short)"],
                "config": {}
            }
        
        return {
            "valid": True,
            "errors": [],
            "config": {
                "api_key_present": True,
                "api_key_length": len(api_key)
            }
        }
    
    def _validate_bedrock_auth(self) -> Dict[str, Any]:
        """Validate AWS Bedrock authentication."""
        errors = []
        config = {}
        
        # Check if Bedrock is enabled
        if os.getenv("CLAUDE_CODE_USE_BEDROCK") != "1":
            errors.append("CLAUDE_CODE_USE_BEDROCK must be set to '1'")
        
        # Check AWS credentials
        aws_access_key = os.getenv("AWS_ACCESS_KEY_ID")
        aws_secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")
        aws_region = os.getenv("AWS_REGION", os.getenv("AWS_DEFAULT_REGION"))
        
        if not aws_access_key:
            errors.append("AWS_ACCESS_KEY_ID environment variable not set")
        if not aws_secret_key:
            errors.append("AWS_SECRET_ACCESS_KEY environment variable not set")
        if not aws_region:
            errors.append("AWS_REGION or AWS_DEFAULT_REGION environment variable not set")
        
        config.update({
            "aws_access_key_present": bool(aws_access_key),
            "aws_secret_key_present": bool(aws_secret_key),
            "aws_region": aws_region,
        })
        
        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "config": config
        }
    
    def _validate_vertex_auth(self) -> Dict[str, Any]:
        """Validate Google Vertex AI authentication."""
        errors = []
        config = {}
        
        # Check if Vertex is enabled
        if os.getenv("CLAUDE_CODE_USE_VERTEX") != "1":
            errors.append("CLAUDE_CODE_USE_VERTEX must be set to '1'")
        
        # Check required Vertex AI environment variables
        project_id = os.getenv("ANTHROPIC_VERTEX_PROJECT_ID")
        region = os.getenv("CLOUD_ML_REGION")
        
        if not project_id:
            errors.append("ANTHROPIC_VERTEX_PROJECT_ID environment variable not set")
        if not region:
            errors.append("CLOUD_ML_REGION environment variable not set")
        
        config.update({
            "project_id": project_id,
            "region": region,
        })
        
        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "config": config
        }
    
    def _validate_claude_cli_auth(self) -> Dict[str, Any]:
        """Validate that Claude Code CLI is already authenticated."""
        # For CLI authentication, we assume it's valid and let the SDK handle auth
        # The actual validation will happen when we try to use the SDK
        return {
            "valid": True,
            "errors": [],
            "config": {
                "method": "Claude Code CLI authentication",
                "note": "Using existing Claude Code CLI authentication"
            }
        }
    
    def get_claude_code_env_vars(self) -> Dict[str, str]:
        """Get environment variables needed for Claude Code SDK."""
        env_vars = {}
        
        if self.auth_method == "anthropic":
            if os.getenv("ANTHROPIC_API_KEY"):
                env_vars["ANTHROPIC_API_KEY"] = os.getenv("ANTHROPIC_API_KEY")
        
        elif self.auth_method == "bedrock":
            env_vars["CLAUDE_CODE_USE_BEDROCK"] = "1"
            if os.getenv("AWS_ACCESS_KEY_ID"):
                env_vars["AWS_ACCESS_KEY_ID"] = os.getenv("AWS_ACCESS_KEY_ID")
            if os.getenv("AWS_SECRET_ACCESS_KEY"):
                env_vars["AWS_SECRET_ACCESS_KEY"] = os.getenv("AWS_SECRET_ACCESS_KEY")
            if os.getenv("AWS_REGION"):
                env_vars["AWS_REGION"] = os.getenv("AWS_REGION")
        
        elif self.auth_method == "vertex":
            env_vars["CLAUDE_CODE_USE_VERTEX"] = "1"
            if os.getenv("ANTHROPIC_VERTEX_PROJECT_ID"):
                env_vars["ANTHROPIC_VERTEX_PROJECT_ID"] = os.getenv("ANTHROPIC_VERTEX_PROJECT_ID")
            if os.getenv("CLOUD_ML_REGION"):
                env_vars["CLOUD_ML_REGION"] = os.getenv("CLOUD_ML_REGION")
            if os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
                env_vars["GOOGLE_APPLICATION_CREDENTIALS"] = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        
        elif self.auth_method == "claude_cli":
            # For CLI auth, don't set any environment variables
            # Let Claude Code SDK use the existing CLI authentication
            pass
        
        return env_vars


# Initialize the auth manager
auth_manager = ClaudeCodeAuthManager()

# HTTP Bearer security scheme (for FastAPI endpoint protection)
security = HTTPBearer(auto_error=False)


async def verify_api_key(request: Request, credentials: Optional[HTTPAuthorizationCredentials] = None):
    """
    Verify API key if one is configured for FastAPI endpoint protection.
    This is separate from Claude Code authentication.
    """
    # Get the active API key (environment or runtime-generated)
    active_api_key = auth_manager.get_api_key()
    
    # If no API key is configured, allow all requests
    if not active_api_key:
        return True
    
    # Get credentials from Authorization header
    if credentials is None:
        credentials = await security(request)
    
    # Check if credentials were provided
    if not credentials:
        raise HTTPException(
            status_code=401,
            detail="Missing API key",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Verify the API key
    if credentials.credentials != active_api_key:
        raise HTTPException(
            status_code=401,
            detail="Invalid API key",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return True


def validate_claude_code_auth() -> Tuple[bool, Dict[str, Any]]:
    """
    Validate Claude Code authentication and return status.
    Returns (is_valid, status_info)
    """
    status = auth_manager.auth_status
    
    if not status["valid"]:
        logger.error(f"Claude Code authentication failed: {status['errors']}")
        return False, status
    
    logger.info(f"Claude Code authentication validated: {status['method']}")
    return True, status


def get_claude_code_auth_info() -> Dict[str, Any]:
    """Get Claude Code authentication information for diagnostics."""
    return {
        "method": auth_manager.auth_method,
        "status": auth_manager.auth_status,
        "environment_variables": list(auth_manager.get_claude_code_env_vars().keys())
    }