from typing import List, Optional, Dict, Any, Union, Literal
from pydantic import BaseModel, Field, field_validator, model_validator
from datetime import datetime
import uuid
import logging

logger = logging.getLogger(__name__)


class ContentPart(BaseModel):
    """Content part for multimodal messages (OpenAI format)."""

    type: Literal["text"]
    text: str


class Message(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: Union[str, List[ContentPart]]
    name: Optional[str] = None

    @model_validator(mode="after")
    def normalize_content(self):
        """Convert array content to string for Claude Code compatibility."""
        if isinstance(self.content, list):
            # Extract text from content parts and concatenate
            text_parts = []
            for part in self.content:
                if isinstance(part, ContentPart) and part.type == "text":
                    text_parts.append(part.text)
                elif isinstance(part, dict) and part.get("type") == "text":
                    text_parts.append(part.get("text", ""))

            # Join all text parts with newlines
            self.content = "\n".join(text_parts) if text_parts else ""

        return self


class StreamOptions(BaseModel):
    """Options for streaming responses."""

    include_usage: bool = Field(
        default=False, description="Include usage information in the final streaming chunk"
    )


class ChatCompletionRequest(BaseModel):
    model: str
    messages: List[Message]
    temperature: Optional[float] = Field(default=1.0, ge=0, le=2)
    top_p: Optional[float] = Field(default=1.0, ge=0, le=1)
    n: Optional[int] = Field(default=1, ge=1)
    stream: Optional[bool] = False
    stop: Optional[Union[str, List[str]]] = None
    max_tokens: Optional[int] = None
    max_completion_tokens: Optional[int] = Field(
        default=None, description="Maximum tokens to generate in the completion (OpenAI standard)"
    )
    presence_penalty: Optional[float] = Field(default=0, ge=-2, le=2)
    frequency_penalty: Optional[float] = Field(default=0, ge=-2, le=2)
    logit_bias: Optional[Dict[str, float]] = None
    user: Optional[str] = None
    session_id: Optional[str] = Field(
        default=None, description="Optional session ID for conversation continuity"
    )
    enable_tools: Optional[bool] = Field(
        default=False,
        description="Enable Claude Code tools (Read, Write, Bash, etc.) - disabled by default for OpenAI compatibility",
    )
    stream_options: Optional[StreamOptions] = Field(
        default=None, description="Options for streaming responses"
    )

    @field_validator("n")
    @classmethod
    def validate_n(cls, v):
        if v > 1:
            raise ValueError(
                "Claude Code SDK does not support multiple choices (n > 1). Only single response generation is supported."
            )
        return v

    def log_parameter_info(self):
        """Log information about parameter handling."""
        info_messages = []
        warnings = []

        if self.temperature != 1.0:
            info_messages.append(
                f"temperature={self.temperature} will be applied via system prompt (best-effort)"
            )

        if self.top_p != 1.0:
            info_messages.append(
                f"top_p={self.top_p} will be applied via system prompt (best-effort)"
            )

        if self.max_tokens is not None or self.max_completion_tokens is not None:
            max_val = self.max_completion_tokens or self.max_tokens
            info_messages.append(
                f"max_tokens={max_val} will be mapped to max_thinking_tokens (best-effort)"
            )

        if self.presence_penalty != 0:
            warnings.append(
                f"presence_penalty={self.presence_penalty} is not supported and will be ignored"
            )

        if self.frequency_penalty != 0:
            warnings.append(
                f"frequency_penalty={self.frequency_penalty} is not supported and will be ignored"
            )

        if self.logit_bias:
            warnings.append("logit_bias is not supported and will be ignored")

        if self.stop:
            warnings.append("stop sequences are not supported and will be ignored")

        for msg in info_messages:
            logger.info(f"OpenAI API compatibility: {msg}")

        for warning in warnings:
            logger.warning(f"OpenAI API compatibility: {warning}")

    def get_sampling_instructions(self) -> Optional[str]:
        """
        Generate sampling instructions based on temperature and top_p.

        Returns system prompt text to approximate the requested sampling behavior.
        """
        instructions = []

        if self.temperature is not None and self.temperature != 1.0:
            if self.temperature < 0.3:
                instructions.append(
                    "Be highly focused and deterministic in your responses. Choose the most likely and predictable options."
                )
            elif self.temperature < 0.7:
                instructions.append(
                    "Be somewhat focused and consistent in your responses, preferring reliable and expected solutions."
                )
            elif self.temperature > 1.5:
                instructions.append(
                    "Be highly creative and exploratory in your responses. Consider unusual and diverse approaches."
                )
            elif self.temperature > 1.0:
                instructions.append(
                    "Be creative and varied in your responses, exploring different approaches and possibilities."
                )

        if self.top_p is not None and self.top_p < 1.0:
            if self.top_p < 0.5:
                instructions.append(
                    "Focus on the most probable and mainstream solutions, avoiding less likely alternatives."
                )
            elif self.top_p < 0.9:
                instructions.append(
                    "Prefer well-established and common approaches over unusual ones."
                )

        return " ".join(instructions) if instructions else None

    def to_claude_options(self) -> Dict[str, Any]:
        """Convert OpenAI request parameters to Claude Code SDK options."""
        # Log parameter handling information
        self.log_parameter_info()

        options = {}

        # Direct mappings
        if self.model:
            options["model"] = self.model

        # Map max_tokens to max_thinking_tokens (best effort)
        max_token_value = self.max_completion_tokens or self.max_tokens
        if max_token_value is not None:
            # Claude SDK doesn't have exact token limiting, but we can try max_thinking_tokens
            # This is approximate and may not work as expected
            options["max_thinking_tokens"] = max_token_value
            logger.info(
                f"Mapped max_tokens={max_token_value} to max_thinking_tokens (approximate behavior)"
            )

        # Use user field for session identification if provided
        if self.user:
            # Could be used for analytics/logging or session tracking
            logger.info(f"Request from user: {self.user}")

        return options


class Choice(BaseModel):
    index: int
    message: Message
    finish_reason: Optional[Literal["stop", "length", "content_filter", "null"]] = None


class Usage(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class ChatCompletionResponse(BaseModel):
    id: str = Field(default_factory=lambda: f"chatcmpl-{uuid.uuid4().hex[:8]}")
    object: Literal["chat.completion"] = "chat.completion"
    created: int = Field(default_factory=lambda: int(datetime.now().timestamp()))
    model: str
    choices: List[Choice]
    usage: Optional[Usage] = None
    system_fingerprint: Optional[str] = None


class StreamChoice(BaseModel):
    index: int
    delta: Dict[str, Any]
    finish_reason: Optional[Literal["stop", "length", "content_filter", "null"]] = None


class ChatCompletionStreamResponse(BaseModel):
    id: str = Field(default_factory=lambda: f"chatcmpl-{uuid.uuid4().hex[:8]}")
    object: Literal["chat.completion.chunk"] = "chat.completion.chunk"
    created: int = Field(default_factory=lambda: int(datetime.now().timestamp()))
    model: str
    choices: List[StreamChoice]
    usage: Optional[Usage] = Field(
        default=None,
        description="Usage information (only in final chunk when stream_options.include_usage=true)",
    )
    system_fingerprint: Optional[str] = None


class ErrorDetail(BaseModel):
    message: str
    type: str
    param: Optional[str] = None
    code: Optional[str] = None


class ErrorResponse(BaseModel):
    error: ErrorDetail


class SessionInfo(BaseModel):
    session_id: str
    created_at: datetime
    last_accessed: datetime
    message_count: int
    expires_at: datetime


class SessionListResponse(BaseModel):
    sessions: List[SessionInfo]
    total: int


class ToolMetadataResponse(BaseModel):
    """Response model for tool metadata."""

    name: str
    description: str
    category: str
    parameters: Dict[str, str]
    examples: List[str]
    is_safe: bool
    requires_network: bool


class ToolListResponse(BaseModel):
    """Response model for listing all tools."""

    tools: List[ToolMetadataResponse]
    total: int


class ToolConfigurationResponse(BaseModel):
    """Response model for tool configuration."""

    allowed_tools: Optional[List[str]] = None
    disallowed_tools: Optional[List[str]] = None
    effective_tools: List[str]
    created_at: datetime
    updated_at: datetime


class ToolConfigurationRequest(BaseModel):
    """Request model for updating tool configuration."""

    allowed_tools: Optional[List[str]] = None
    disallowed_tools: Optional[List[str]] = None
    session_id: Optional[str] = Field(
        default=None, description="Optional session ID for per-session configuration"
    )


class ToolValidationResponse(BaseModel):
    """Response model for tool validation."""

    valid: Dict[str, bool]
    invalid_tools: List[str]


class MCPServerConfigRequest(BaseModel):
    """Request model for registering an MCP server."""

    name: str
    command: str
    args: List[str] = Field(default_factory=list)
    env: Optional[Dict[str, str]] = None
    description: str = ""
    enabled: bool = True

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Validate MCP server name."""
        if not v or not v.strip():
            raise ValueError("Server name cannot be empty")
        if len(v) > 100:
            raise ValueError("Server name too long (max 100 characters)")
        # Allow alphanumeric, hyphens, underscores, and dots
        if not all(c.isalnum() or c in "-_." for c in v):
            raise ValueError(
                "Server name must contain only alphanumeric characters, hyphens, underscores, and dots"
            )
        return v.strip()

    @field_validator("command")
    @classmethod
    def validate_command(cls, v: str) -> str:
        """Validate MCP server command."""
        if not v or not v.strip():
            raise ValueError("Command cannot be empty")
        if len(v) > 500:
            raise ValueError("Command path too long (max 500 characters)")
        return v.strip()


class MCPServerInfoResponse(BaseModel):
    """Response model for MCP server information."""

    name: str
    command: str
    args: List[str]
    description: str
    enabled: bool
    connected: bool
    tools_count: int = 0
    resources_count: int = 0
    prompts_count: int = 0


class MCPServersListResponse(BaseModel):
    """Response model for listing MCP servers."""

    servers: List[MCPServerInfoResponse]
    total: int


class MCPConnectionRequest(BaseModel):
    """Request model for connecting to an MCP server."""

    server_name: str

    @field_validator("server_name")
    @classmethod
    def validate_server_name(cls, v: str) -> str:
        """Validate MCP server name."""
        if not v or not v.strip():
            raise ValueError("Server name cannot be empty")
        if len(v) > 100:
            raise ValueError("Server name too long (max 100 characters)")
        return v.strip()


class MCPToolCallRequest(BaseModel):
    """Request model for calling an MCP tool."""

    server_name: str
    tool_name: str
    arguments: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("server_name")
    @classmethod
    def validate_server_name(cls, v: str) -> str:
        """Validate MCP server name."""
        if not v or not v.strip():
            raise ValueError("Server name cannot be empty")
        if len(v) > 100:
            raise ValueError("Server name too long (max 100 characters)")
        return v.strip()

    @field_validator("tool_name")
    @classmethod
    def validate_tool_name(cls, v: str) -> str:
        """Validate MCP tool name."""
        if not v or not v.strip():
            raise ValueError("Tool name cannot be empty")
        if len(v) > 200:
            raise ValueError("Tool name too long (max 200 characters)")
        return v.strip()
