# Context Findings

## Current Architecture Analysis

### Claude Code OpenAI Wrapper (claude-code-openai-wrapper)
- **Main API:** `/v1/chat/completions` endpoint in `main.py`
- **Tool Support:** Already has `enable_tools` parameter that activates Claude Code tools
- **Session Management:** Implemented via `session_manager.py` with session continuity
- **Authentication:** Multiple methods supported (API key, browser, Bedrock, Vertex)
- **Models:** Using Claude 4 Sonnet (`claude-sonnet-4-20250514`)

### Jarvis Integration (jarvis_pure_adaptive_claude_launcher.py)
- **Current Integration:** Uses Claude for reasoning via REST API calls
- **Tool Selection:** Claude analyzes commands and selects appropriate tools
- **Workflow Management:** `WorkflowPlannerAgent` class handles multi-step operations
- **Emotion Detection:** Already has emotion-based adaptation system

## Enhancement Opportunities

### 1. Advanced Reasoning Capabilities
**Files to Modify:**
- `jarvis_pure_adaptive_claude_launcher.py` - Enhance `use_claude_reasoning()` method
- Add support for Claude's thinking tags and chain-of-thought reasoning
- Implement multi-turn reasoning for complex decisions

### 2. Claude Tools Integration
**Current State:**
- Claude wrapper supports tools: Task, Bash, Glob, Grep, LS, Read, Edit, Write, WebFetch, etc.
- Tools are disabled by default (`enable_tools: false`)

**Implementation Path:**
- Modify Jarvis requests to include `"enable_tools": true` in API calls
- Create new hybrid operations where Jarvis uses Claude tools directly
- File paths: `main.py:335-344` (tool handling logic)

### 3. Session Memory Integration
**Current State:**
- Claude wrapper has full session support via `session_manager.py`
- Sessions expire after 1 hour of inactivity
- API endpoints: `/v1/sessions/*`

**Implementation Path:**
- Add `session_id` to Jarvis's Claude API calls
- Store session IDs per user/context
- Implement session persistence across Jarvis restarts

### 4. Vision Capabilities
**Claude Vision Features:**
- Supports JPEG, PNG, GIF, WebP
- Up to 100 images per API request
- Base64 encoding or Files API
- ~1,334 tokens per 1000x1000px image

**Implementation Path:**
- Add image handling to `message_adapter.py`
- Create vision tool integration in Jarvis
- Integrate with existing vision tools in Jarvis

### 5. Performance Optimization
**Current Bottlenecks:**
- Sequential API calls
- No caching of reasoning results
- Tools disabled by default adds overhead

**Optimization Strategies:**
- Implement response caching in `jarvis_pure_adaptive_claude_launcher.py`
- Enable streaming responses (already supported in wrapper)
- Use performance cache from Jarvis's existing system

## Technical Constraints

1. **API Costs:** Vision analysis costs ~$0.004 per 1000x1000px image
2. **Rate Limits:** Need to respect Claude API rate limits
3. **Tool Availability:** Claude tools require authentication and proper permissions
4. **Memory Limits:** Session storage could grow large with images

## Similar Features Analyzed

1. **Ollama Integration (Previous):**
   - Located in: `Jarvis/core/optimized_ollama.py`
   - Used connection pooling and caching
   - Pattern to follow for Claude optimization

2. **Memory Manager:**
   - `memory_manager.py` in Jarvis
   - Could be enhanced to work with Claude sessions

3. **Phase 2 Intelligence Systems:**
   - Cross-domain intelligence already implemented
   - Can be enhanced with Claude's superior reasoning

## Integration Points

1. **API Communication:** `WorkflowPlannerAgent.use_claude_reasoning()`
2. **Tool Execution:** `MCPToolManager.execute_tool()`
3. **Session Storage:** New integration needed with Claude's session manager
4. **Vision Processing:** Integrate with existing `vision` tool
5. **Performance Cache:** Use existing `performance_cache` system