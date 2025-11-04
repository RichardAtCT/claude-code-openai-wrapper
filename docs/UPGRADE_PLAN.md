# Claude Code OpenAI Wrapper - Upgrade Plan

**Date:** 2025-11-02
**Current Version:** claude-code-sdk 0.0.14
**Target Version:** claude-agent-sdk 0.1.6

## Executive Summary

This document outlines a comprehensive plan to upgrade the Claude Code OpenAI Wrapper to use the latest Claude Agent SDK (v0.1.6) and implement the latest OpenAI API standards as of 2025. The upgrade involves a critical SDK migration and implementation of new OpenAI API features.

---

## 1. Claude Agent SDK Migration

### 1.1 Current State Analysis

**Current Implementation:**
- **SDK:** `claude-code-sdk` version 0.0.14 (deprecated)
- **Import:** `from claude_code_sdk import query, ClaudeCodeOptions, Message`
- **Main File:** `claude_cli.py` (lines 11, 114-131)
- **Usage Pattern:** Direct SDK `query()` function with `ClaudeCodeOptions`

**Issues with Current Version:**
- The `claude-code-sdk` package is deprecated (last version 0.0.25)
- Missing latest features and improvements
- No longer maintained or supported
- Security and performance improvements not available

### 1.2 Target State

**Target SDK:** `claude-agent-sdk` version 0.1.6
- **Released:** October 31, 2025
- **Python Requirements:** Python >=3.10
- **Additional Requirements:**
  - Node.js
  - Claude Code 2.0.0+ (`npm install -g @anthropic-ai/claude-code`)

### 1.3 Breaking Changes & Migration Steps

#### 1.3.1 Package Installation Changes

**Before:**
```bash
pip install claude-code-sdk
```

**After:**
```bash
pip uninstall claude-code-sdk
pip install claude-agent-sdk
```

**pyproject.toml Update:**
```toml
# Before:
claude-code-sdk = "^0.0.14"

# After:
claude-agent-sdk = "^0.1.6"
```

#### 1.3.2 Import Statement Changes

**Before (claude_cli.py:11):**
```python
from claude_code_sdk import query, ClaudeCodeOptions, Message
```

**After:**
```python
from claude_agent_sdk import query, ClaudeAgentOptions, Message
```

#### 1.3.3 Options Class Rename

**Breaking Change:** `ClaudeCodeOptions` → `ClaudeAgentOptions`

**Files to Update:**
- `claude_cli.py` (lines 11, 63, 114)

**Before:**
```python
options = ClaudeCodeOptions(
    max_turns=max_turns,
    cwd=self.cwd
)
```

**After:**
```python
options = ClaudeAgentOptions(
    max_turns=max_turns,
    cwd=self.cwd
)
```

#### 1.3.4 System Prompt Configuration Changes

**Critical Breaking Change:** System prompt no longer defaults to Claude Code preset.

**Current Implementation (claude_cli.py:124-125):**
```python
if system_prompt:
    options.system_prompt = system_prompt
```

**New Implementation:**
```python
if system_prompt:
    # New structured system prompt format
    options.system_prompt = {
        "type": "text",
        "text": system_prompt
    }
else:
    # Restore Claude Code default behavior (RECOMMENDED)
    options.system_prompt = {
        "type": "preset",
        "preset": "claude_code"
    }
```

**Alternative Approaches:**
1. **Keep current behavior:** Set `type: "text"` with custom system prompts
2. **Use Claude Code preset:** Set `type: "preset", preset: "claude_code"`
3. **No system prompt:** Omit the field entirely for vanilla Claude behavior

#### 1.3.5 Settings Sources Configuration

**Breaking Change:** SDK no longer reads filesystem settings by default.

**Current Behavior:** Automatically loads from:
- `CLAUDE.md`
- `settings.json`
- Slash commands
- User/project settings

**New Behavior:** Must explicitly enable:
```python
options = ClaudeAgentOptions(
    max_turns=max_turns,
    cwd=self.cwd,
    setting_sources=['user', 'project', 'local']  # Add if needed
)
```

**Recommendation:** Only add if the wrapper needs to load filesystem settings.

#### 1.3.6 New Features Available

The Claude Agent SDK provides several new capabilities:

**1. In-Process MCP Servers (Custom Tools)**
```python
from claude_agent_sdk import tool, create_sdk_mcp_server

@tool("custom_tool", "Description", {"arg": str})
async def custom_tool(args):
    return {"content": [{"type": "text", "text": "Result"}]}

server = create_sdk_mcp_server(
    name="wrapper-tools",
    version="1.0.0",
    tools=[custom_tool]
)
```

**Benefits:**
- No subprocess overhead
- Better performance than external MCP servers
- Easier debugging
- Simplified deployment

**2. Hooks for Deterministic Processing**
```python
async def validate_tool(input_data, tool_use_id, context):
    # Validate before execution
    pass

options = ClaudeAgentOptions(
    hooks={
        "PreToolUse": [
            HookMatcher(matcher="Bash", hooks=[validate_tool])
        ]
    }
)
```

**3. ClaudeSDKClient for Bidirectional Conversations**
```python
from claude_agent_sdk import ClaudeSDKClient

async with ClaudeSDKClient(options=options) as client:
    await client.query("Your prompt")
    async for msg in client.receive_response():
        print(msg)
```

### 1.4 Migration Implementation Plan

#### Phase 1: Dependency Update
- [ ] Update `pyproject.toml` with `claude-agent-sdk = "^0.1.6"`
- [ ] Remove `claude-code-sdk` from dependencies
- [ ] Run `poetry lock` and `poetry install`
- [ ] Verify installation: `poetry show claude-agent-sdk`

#### Phase 2: Code Updates
- [ ] Update imports in `claude_cli.py`
- [ ] Rename `ClaudeCodeOptions` to `ClaudeAgentOptions`
- [ ] Update system prompt handling with new structured format
- [ ] Add Claude Code preset as default system prompt
- [ ] Review and update authentication flow (if needed)

#### Phase 3: Testing
- [ ] Update verification tests in `verify_cli()` method
- [ ] Test all existing functionality:
  - Basic completions
  - Streaming responses
  - Session continuity
  - Tool usage (enable/disable)
  - Authentication methods
- [ ] Run existing test suite: `test_endpoints.py`, `test_basic.py`
- [ ] Test with different authentication methods
- [ ] Verify Docker deployment still works

#### Phase 4: Documentation Updates
- [ ] Update README.md with new SDK version
- [ ] Update installation instructions
- [ ] Document breaking changes for users
- [ ] Update Docker image with new dependencies
- [ ] Update example files if needed

---

## 2. OpenAI API Standards Update (2025)

### 2.1 Current OpenAI API Compliance Status

**Currently Supported:**
- ✅ Chat completions endpoint (`/v1/chat/completions`)
- ✅ Basic streaming with `stream: true`
- ✅ Message roles (system, user, assistant)
- ✅ Model selection
- ✅ Session management (custom extension)

**Currently Not Supported:**
- ❌ `temperature` parameter (0-2)
- ❌ `max_tokens` / `max_completion_tokens` parameter
- ❌ `top_p` parameter (nucleus sampling)
- ❌ `frequency_penalty` parameter
- ❌ `presence_penalty` parameter
- ❌ `logit_bias` parameter
- ❌ `n` parameter (multiple completions)
- ❌ `stop` sequences
- ❌ `stream_options` for usage data in streaming
- ❌ Image content in messages (currently converted to placeholders)
- ❌ Function calling / tools (OpenAI format)

### 2.2 New OpenAI API Features (2025)

#### 2.2.1 Max Tokens Evolution

**Breaking Change:** `max_tokens` deprecated in favor of `max_completion_tokens` for certain models.

**Current Parameter:** `max_tokens`
**New Parameter:** `max_completion_tokens` (for o1-series models)

**Reason:** Support for "hidden tokens" in reasoning models (o1-preview, o1-mini)

**Implementation Strategy:**
```python
# In models.py ChatCompletionRequest
max_tokens: Optional[int] = None  # Legacy support
max_completion_tokens: Optional[int] = None  # New standard

# Map to Claude options
def to_claude_options(self):
    options = {}
    # Prefer max_completion_tokens if available
    max_tok = self.max_completion_tokens or self.max_tokens
    if max_tok:
        options['max_thinking_tokens'] = max_tok  # Map to Claude
    return options
```

#### 2.2.2 Stream Options Enhancement

**New Feature:** `stream_options` parameter for usage data in streaming responses.

**Current Implementation:** No usage data in streaming
**New Implementation:**
```python
# Request:
{
    "stream": true,
    "stream_options": {
        "include_usage": true
    }
}

# Response: Additional final chunk with usage data
{
    "id": "chatcmpl-...",
    "usage": {
        "prompt_tokens": 100,
        "completion_tokens": 50,
        "total_tokens": 150
    }
}
```

**Files to Update:**
- `models.py`: Add `stream_options` field to `ChatCompletionRequest`
- `main.py`: Update `generate_streaming_response()` to emit usage chunk

#### 2.2.3 GPT-5 New Parameters (Optional)

If targeting cutting-edge compatibility:

**1. Verbosity Parameter:**
```python
verbosity: Optional[Literal["low", "medium", "high"]] = None
# Controls response length/detail
```

**2. Reasoning Effort Parameter:**
```python
reasoning_effort: Optional[Literal["minimal", "low", "medium", "high"]] = None
# For reasoning models - control depth of reasoning
```

**Note:** These are GPT-5 specific. Implementation is optional for Claude wrapper.

### 2.3 Priority Parameter Implementation

Based on user demand and compatibility, prioritize:

#### Priority 1 (High Impact):
1. **`temperature`** - Most commonly used parameter
2. **`max_tokens` / `max_completion_tokens`** - Essential for output control
3. **`stream_options.include_usage`** - Better streaming experience

#### Priority 2 (Medium Impact):
4. **`top_p`** - Alternative to temperature
5. **`stop`** - Stop sequences for generation control
6. **`presence_penalty` / `frequency_penalty`** - Fine-tuning repetition

#### Priority 3 (Low Impact):
7. **`n`** - Multiple completions (complex to implement with Claude)
8. **`logit_bias`** - Advanced use case
9. **GPT-5 specific parameters** - Future-proofing

### 2.4 Parameter Mapping Strategy

**Challenge:** Map OpenAI parameters to Claude SDK parameters.

**Temperature Mapping:**
```python
# OpenAI: 0-2 (default 1)
# Claude: No direct equivalent in SDK

# Options:
# 1. Include in system prompt
# 2. Use custom headers if SDK supports
# 3. Document as unsupported with warning
```

**Max Tokens Mapping:**
```python
# OpenAI: max_tokens / max_completion_tokens
# Claude: max_thinking_tokens (for extended thinking)

# Map in to_claude_options():
if self.max_completion_tokens or self.max_tokens:
    options['max_thinking_tokens'] = self.max_completion_tokens or self.max_tokens
```

**Top-P Mapping:**
```python
# Similar to temperature - no direct Claude SDK equivalent
# Could combine with temperature in system prompt instruction
```

### 2.5 OpenAI API Implementation Plan

#### Phase 1: Core Parameters
- [ ] Add `max_completion_tokens` to request model
- [ ] Add backward compatibility for `max_tokens`
- [ ] Implement parameter mapping to Claude options
- [ ] Add validation for parameter ranges

#### Phase 2: Streaming Enhancements
- [ ] Add `stream_options` to request model
- [ ] Implement usage tracking in streaming responses
- [ ] Emit final usage chunk when `include_usage: true`

#### Phase 3: Advanced Parameters
- [ ] Add `temperature` (document limitations)
- [ ] Add `top_p` (document limitations)
- [ ] Add `stop` sequences
- [ ] Add `presence_penalty` / `frequency_penalty`
- [ ] Document which parameters are best-effort vs full support

#### Phase 4: Testing & Documentation
- [ ] Test parameter validation
- [ ] Test parameter mapping
- [ ] Create compatibility matrix in README
- [ ] Update API documentation
- [ ] Add examples for new parameters

---

## 3. Implementation Priorities & Timeline

### 3.1 Recommended Approach

**Option A: Sequential Migration** (Lower Risk)
1. Complete Claude Agent SDK migration first
2. Test thoroughly
3. Then implement OpenAI API updates

**Option B: Parallel Development** (Faster but Higher Risk)
1. Create feature branches for each workstream
2. Develop simultaneously
3. Integrate and test together

**Recommendation:** Option A for stability, Option B if timeline is critical.

### 3.2 Estimated Timeline

**Phase 1: Claude Agent SDK Migration**
- Dependency updates: 1-2 hours
- Code updates: 2-4 hours
- Testing: 2-3 hours
- **Total: 1 day**

**Phase 2: OpenAI API Core Parameters**
- Model updates: 2-3 hours
- Implementation: 3-4 hours
- Testing: 2-3 hours
- **Total: 1 day**

**Phase 3: Streaming & Advanced Features**
- Implementation: 4-6 hours
- Testing: 2-3 hours
- **Total: 1 day**

**Phase 4: Documentation & Polish**
- Documentation: 3-4 hours
- Final testing: 2-3 hours
- **Total: 0.5 day**

**Total Estimated Time:** 3.5-4 days

### 3.3 Risk Assessment

**High Risk Items:**
1. ⚠️ System prompt migration (breaking change)
2. ⚠️ Behavior changes from SDK defaults
3. ⚠️ Authentication flow changes

**Medium Risk Items:**
1. ⚠️ Parameter mapping accuracy
2. ⚠️ Streaming usage data implementation
3. ⚠️ Backward compatibility

**Low Risk Items:**
1. Dependency updates
2. Import statement changes
3. Documentation updates

### 3.4 Rollback Strategy

**If Migration Fails:**
1. Revert `pyproject.toml` changes
2. Run `poetry lock && poetry install`
3. Restore original code from git

**Recommended:**
- Create migration branch: `feature/sdk-migration`
- Test thoroughly before merging to main
- Tag current version before migration: `git tag v1.0.0-pre-migration`

---

## 4. Compatibility Matrix (Post-Upgrade)

### 4.1 Claude SDK Features

| Feature | Current (0.0.14) | Target (0.1.6) | Status |
|---------|-----------------|----------------|--------|
| Basic completions | ✅ | ✅ | Maintained |
| Streaming | ✅ | ✅ | Maintained |
| System prompts | ✅ | ✅ | Breaking change |
| Tool control | ✅ | ✅ | Maintained |
| Session continuity | ✅ | ✅ | Maintained |
| In-process MCP | ❌ | ✅ | **New** |
| Hooks | ❌ | ✅ | **New** |
| Settings sources | Auto | Manual | Breaking change |

### 4.2 OpenAI API Compliance

| Feature | Pre-Upgrade | Post-Upgrade | Notes |
|---------|------------|--------------|-------|
| Chat completions | ✅ | ✅ | Core feature |
| Streaming | ✅ | ✅ | Enhanced with usage |
| `model` | ✅ | ✅ | Maintained |
| `messages` | ✅ | ✅ | Maintained |
| `temperature` | ❌ | ⚠️ | Best-effort |
| `max_tokens` | ❌ | ✅ | **New** |
| `max_completion_tokens` | ❌ | ✅ | **New** |
| `stream_options` | ❌ | ✅ | **New** |
| `top_p` | ❌ | ⚠️ | Best-effort |
| `stop` | ❌ | 🔄 | Planned |
| `n` | ❌ | ❌ | Not supported |
| Function calling | ❌ | ❌ | Not supported |

**Legend:**
- ✅ Fully supported
- ⚠️ Partial/best-effort support
- 🔄 Planned for implementation
- ❌ Not supported

---

## 5. Testing Strategy

### 5.1 Test Coverage Requirements

**Unit Tests:**
- [ ] SDK initialization with new `ClaudeAgentOptions`
- [ ] System prompt configuration variations
- [ ] Parameter validation for new OpenAI params
- [ ] Parameter mapping to Claude options

**Integration Tests:**
- [ ] End-to-end completion request
- [ ] Streaming with usage data
- [ ] Session continuity across SDK version
- [ ] Authentication methods (API key, Bedrock, Vertex)

**Regression Tests:**
- [ ] All existing `test_endpoints.py` tests pass
- [ ] All existing `test_basic.py` tests pass
- [ ] Session tests still functional
- [ ] Docker deployment works

### 5.2 Test Files to Update

1. **`test_endpoints.py`**
   - Update expected behaviors
   - Add tests for new parameters

2. **`test_basic.py`**
   - Verify SDK migration doesn't break basics
   - Add streaming usage tests

3. **`test_session_continuity.py`**
   - Ensure sessions work with new SDK
   - Test session persistence

4. **New Test Files Needed:**
   - `test_parameter_mapping.py` - Test OpenAI → Claude parameter mapping
   - `test_sdk_migration.py` - Verify SDK upgrade behaviors

### 5.3 Manual Testing Checklist

- [ ] Basic chat completion works
- [ ] Streaming works with usage data
- [ ] Temperature parameter accepted (even if best-effort)
- [ ] Max tokens limiting works
- [ ] Session continuity maintained
- [ ] All authentication methods work
- [ ] Docker container builds and runs
- [ ] Example files work (`examples/openai_sdk.py`, etc.)

---

## 6. Documentation Updates Required

### 6.1 README.md Updates

**Sections to Update:**
1. **Status section** - Update SDK version to 0.1.6
2. **Features section** - Add new OpenAI parameter support
3. **Prerequisites** - Update Claude Code version requirement (2.0.0+)
4. **Installation** - Update dependency instructions
5. **Limitations & Roadmap** - Update with implemented features
6. **Supported Models** - Verify model list is current

**New Sections to Add:**
- **Parameter Support Matrix** - Document OpenAI parameter compatibility
- **Migration Guide** - For users upgrading from older versions

### 6.2 Code Documentation

- [ ] Update docstrings in `claude_cli.py`
- [ ] Update comments explaining new SDK behavior
- [ ] Document system prompt configuration options
- [ ] Add examples for new parameters

### 6.3 Example Files

Files to review/update:
- `examples/openai_sdk.py` - Add parameter examples
- `examples/streaming.py` - Add stream_options example
- `examples/session_continuity.py` - Verify compatibility

---

## 7. Rollout Plan

### 7.1 Pre-Release Steps

1. **Create feature branch:** `feature/upgrade-sdk-and-api`
2. **Tag current version:** `git tag v1.0.0-stable`
3. **Update dependencies** in branch
4. **Implement changes** following this plan
5. **Test thoroughly** with all test suites
6. **Update documentation** completely
7. **Test Docker build** and deployment

### 7.2 Release Steps

1. **Merge to main** after all tests pass
2. **Tag new version:** `git tag v2.0.0` (major version due to breaking changes)
3. **Update GitHub release notes** with:
   - Breaking changes
   - New features
   - Migration instructions
4. **Update Docker Hub** with new image
5. **Notify users** via GitHub discussions/issues

### 7.3 Post-Release Monitoring

- Monitor GitHub issues for migration problems
- Be ready to provide support for breaking changes
- Consider creating a `v1.x` maintenance branch for critical fixes

---

## 8. Breaking Changes for End Users

### 8.1 System Prompt Behavior

**Breaking Change:** Default system prompt behavior changes.

**Impact:** Users relying on Claude Code default system prompt may see different behavior.

**Migration:**
- No action needed if using custom system prompts
- Default now restored via `preset: "claude_code"` in SDK options

### 8.2 Settings Files

**Breaking Change:** Settings files no longer auto-loaded.

**Impact:** Users with `CLAUDE.md`, custom settings.json may see different behavior.

**Migration:**
- Explicitly enable via `setting_sources` if needed
- Most users won't be affected (wrapper doesn't rely on these)

### 8.3 Dependency Requirements

**Change:** New package name and version requirements.

**Impact:** Users building from source need to update dependencies.

**Migration:**
```bash
poetry lock --no-update
poetry install
# Or for Docker:
docker build --no-cache -t claude-wrapper:v2 .
```

---

## 9. Success Criteria

The upgrade is considered successful when:

✅ **Functional Requirements:**
- [ ] All existing tests pass with new SDK
- [ ] Streaming responses work correctly
- [ ] Session continuity maintained
- [ ] Authentication methods all functional
- [ ] Docker deployment successful
- [ ] At least 3 new OpenAI parameters implemented (`max_tokens`, `temperature`, `stream_options`)

✅ **Quality Requirements:**
- [ ] No regressions in existing functionality
- [ ] Response times similar or better than before
- [ ] Error handling maintains quality
- [ ] Documentation complete and accurate

✅ **User Experience:**
- [ ] Clear migration guide available
- [ ] Breaking changes well documented
- [ ] Examples updated and working
- [ ] GitHub issues addressed proactively

---

## 10. Additional Recommendations

### 10.1 Consider Future Enhancements

**After migration is stable:**
1. **Implement In-Process MCP Tools** - Leverage new SDK capability for custom tools
2. **Add Hooks for Validation** - Use SDK hooks for tool usage validation
3. **Explore ClaudeSDKClient** - For more interactive conversation patterns
4. **Function Calling Translation** - Map OpenAI function calls to Claude tools

### 10.2 Monitoring & Observability

Consider adding:
- **Metrics collection** - Track SDK performance, error rates
- **Usage analytics** - Understand which parameters are most used
- **Error reporting** - Better error tracking for debugging

### 10.3 Community Engagement

- Share migration experience in GitHub discussions
- Contribute back to Claude Agent SDK if bugs found
- Update examples and share best practices

---

## Appendix A: Quick Reference

### Key Code Changes

**Import Change:**
```python
# Before
from claude_code_sdk import query, ClaudeCodeOptions, Message

# After
from claude_agent_sdk import query, ClaudeAgentOptions, Message
```

**Options Change:**
```python
# Before
options = ClaudeCodeOptions(max_turns=1, cwd="/path")

# After
options = ClaudeAgentOptions(
    max_turns=1,
    cwd="/path",
    system_prompt={"type": "preset", "preset": "claude_code"}
)
```

**Dependency Change:**
```toml
# Before
claude-code-sdk = "^0.0.14"

# After
claude-agent-sdk = "^0.1.6"
```

### Key Commands

```bash
# Update dependencies
poetry remove claude-code-sdk
poetry add claude-agent-sdk@^0.1.6
poetry lock
poetry install

# Test changes
poetry run python test_endpoints.py
poetry run python test_basic.py

# Build Docker
docker build -t claude-wrapper:v2 .

# Tag for release
git tag v2.0.0
git push origin v2.0.0
```

---

## Appendix B: Reference Links

### Official Documentation
- [Claude Agent SDK PyPI](https://pypi.org/project/claude-agent-sdk/)
- [Claude Agent SDK GitHub](https://github.com/anthropics/claude-agent-sdk-python)
- [Migration Guide](https://docs.claude.com/en/docs/claude-code/sdk/migration-guide)
- [OpenAI API Reference](https://platform.openai.com/docs/api-reference)

### Related Issues
- [System prompt defaults issue #289](https://github.com/anthropics/claude-agent-sdk-python/issues/289)

### Community Resources
- [Claude Agent SDK Migration Guide Blog](https://kane.mx/posts/2025/claude-agent-sdk-update/)

---

**Document Version:** 1.0
**Last Updated:** 2025-11-02
**Next Review:** After Phase 1 completion
