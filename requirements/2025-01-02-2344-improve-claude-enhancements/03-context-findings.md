# Context Findings

## Current Architecture Analysis

### 1. Vision System Components

#### Vision Tool (`/mcp_tools/tools/vision/vision_tool.py`)
- Provides object detection using Coral TPU
- Operations: `analyze_image`, `describe_scene`, `count_objects`, `find_people`
- Supports both "basic" (Coral-only) and "enhanced" (GPU+TPU) servers
- Can capture from camera when no image path provided
- Returns technical detection data (confidence scores, object counts)

#### Face Recognition Tool (`/mcp_tools/tools/face_recognition/face_recognition_tool.py`)
- Separate service running at `http://192.168.1.95:8001`
- Operations: `who_is_here`, `add_person`, `list_people`, `detect_faces`, `jarvis_vision`
- Has person database management capabilities
- Supports interactive person addition
- Already has family member concept in keywords

### 2. Current Integration Points

#### Jarvis Integration (`jarvis_pure_adaptive_claude_launcher.py`)
- Face recognition keywords already include: "family member", "add person", "register person"
- Vision and face_recognition are separate tools
- Vision formatting function exists at line 7019: `format_vision_response()`
- Face recognition formatting at line 8053: `format_face_recognition_response()`
- Claude enhancement for vision already implemented (line 901)

### 3. Key Files to Modify

1. **Primary Files:**
   - `/mcp_tools/jarvis_pure_adaptive_claude_launcher.py` - Main integration point
   - `/mcp_tools/tools/vision/vision_tool.py` - Vision capabilities
   - `/mcp_tools/tools/face_recognition/face_recognition_tool.py` - Face recognition

2. **Supporting Files:**
   - `/mcp_tools/face_recognition_server.py` - Face recognition backend
   - `/mcp_tools/jarvis_vision_demo.py` - Vision demonstration code

### 4. Existing Patterns

#### Response Formatting
- Vision responses currently show technical details (61% confidence)
- Face recognition has separate response formatter
- Claude enhancement only triggers when image data present

#### Tool Selection
- Vision and face recognition are treated as separate tools
- Keywords overlap between tools (e.g., "who do you see")
- UniFi Protect integration exists but separate from vision

### 5. Technical Constraints

1. **Privacy/Storage:**
   - Face recognition server already runs locally (192.168.1.95:8001)
   - Person database exists but persistence method unclear
   - No cloud storage currently used

2. **Camera Integration:**
   - Vision tool can capture from webcam (camera ID 0)
   - UniFi Protect cameras available but not integrated with face recognition
   - Multiple camera support would need coordination

3. **Real-time Processing:**
   - Vision tool processes single frames
   - No continuous monitoring currently implemented
   - Face recognition server architecture supports real-time but not utilized

### 6. Similar Features Analyzed

#### UniFi Protect Tool
- Has camera management and snapshot capabilities
- Keywords include security-related terms
- Could be leveraged for multiple camera sources

#### Vision Enhancement with Claude
- Already implemented but only for generic vision analysis
- Could be extended to provide personalized responses
- Enhancement happens after vision tool execution

### 7. Integration Opportunities

1. **Unified Vision Pipeline:**
   - Combine vision and face recognition into single flow
   - Use vision for detection, face recognition for identification
   - Claude for natural language responses

2. **Family Member Database:**
   - Extend existing person database with relationship tags
   - Add persistent storage with SQLite (like jarvis_learning.db)
   - Include preferences and personalization data

3. **Multi-Camera Support:**
   - Leverage UniFi Protect for security cameras
   - Coordinate between webcam and security cameras
   - Unified person tracking across cameras

### 8. Implementation Patterns to Follow

1. **Tool Response Pattern:**
   ```python
   def format_vision_response(raw_response: Any) -> str:
       # Current pattern: Parse technical data, return natural language
   ```

2. **Claude Enhancement Pattern:**
   ```python
   if tool_name == "vision" and isinstance(result, dict):
       result = self.workflow_agent._enhance_vision_with_claude(result, command)
   ```

3. **Keyword Mapping Pattern:**
   ```python
   "face_recognition": [
       "family member", "add person", ...
   ]
   ```