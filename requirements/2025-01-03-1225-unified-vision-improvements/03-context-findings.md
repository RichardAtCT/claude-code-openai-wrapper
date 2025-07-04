# Context Findings - Unified Vision Improvements

## Critical Issues Found

### 1. Database Initialization Problem
**Issue**: "Error adding family member: no such table: family_members"
- The unified vision system expects tables to exist but doesn't create them
- Database initialization script exists but wasn't run: `create_family_members_db.py`
- Database location: `jarvis_learning.db` in the mcp_tools directory

### 2. Face Encoding Storage Issue
**Current Implementation**:
- Using placeholder encoding: `b"placeholder_encoding"`
- Face recognition server doesn't return actual face encodings in API responses
- Encodings are 128-dimensional numpy arrays stored server-side only

**Solution Options**:
1. Modify face_recognition server to return encodings
2. Use face_recognition tool's existing `add_person` operation
3. **Recommended**: Store person_id references instead of duplicate encodings

## Architecture Analysis

### File Structure
```
mcp_tools/
├── unified_vision.py              # Core unified vision system
├── create_family_members_db.py    # Database initialization script
├── jarvis_learning.db            # SQLite database (needs tables created)
├── jarvis_pure_adaptive_claude_launcher.py  # Main launcher with integration
└── tools/
    ├── vision/
    │   └── vision_tool.py        # Object detection with Coral TPU
    └── face_recognition/
        └── face_recognition_tool.py  # Face detection and recognition
```

### Key Components

#### 1. Unified Vision System (`unified_vision.py`)
- Parses introduction patterns: "This is my wife Sarah", "I am George"
- Manages family member database
- Formats natural language responses
- **Issue**: Expects database tables to exist

#### 2. Database Schema
```sql
family_members:
- id (PRIMARY KEY)
- name (TEXT)
- relationship (TEXT)
- face_encoding (BLOB) -- Currently using placeholder
- added_date, last_seen (TIMESTAMP)
- camera_source (TEXT)
- metadata (JSON)

face_recognition_history:
- id (PRIMARY KEY)  
- family_member_id (FOREIGN KEY)
- seen_date, camera_source, confidence
```

#### 3. Integration Points
- **Tool Override**: Introduction patterns force vision tool selection
- **Handler Location**: Lines 831-908 in jarvis_pure_adaptive_claude_launcher.py
- **Response Formatter**: Lines 6038-6040 handle unified vision responses

### Voice Announcement Infrastructure

#### TTS Systems Available:
1. **ElevenLabs**: High-quality cloud TTS (requires credits)
2. **AllTalk**: Local TTS server at 192.168.1.78:7851
3. **Local Speech**: Offline fallback

#### Voice Output Methods:
- Direct speaker output via `TTS()` function
- UniFi camera speakers via `speak_through_camera()`
- Face recognition server has built-in announcements

#### Announcement Flow:
1. Face detected → Recognition match
2. Name retrieved from database
3. TTS generates greeting: "Hello George"
4. Audio plays through speakers/camera
5. 30-second cooldown prevents spam

### Current Working Flow

When user says "hi i am George":
1. ✅ Introduction pattern detected
2. ✅ Tool redirected to vision
3. ✅ Camera captures image
4. ✅ Face detected (1 face found)
5. ❌ Database save fails (table missing)
6. ❌ No voice announcement (due to failure)

### Implementation Gaps

1. **Database Not Initialized**: Tables don't exist
2. **Face Encoding Integration**: Need to link with face_recognition person_id
3. **Voice Announcement**: Not triggered on successful recognition
4. **Management Commands**: No way to list/update/remove family members

## Files That Need Modification

### Priority 1: Database Fix
- Run: `create_family_members_db.py`
- Or add auto-initialization to unified_vision.py

### Priority 2: Face Encoding Integration
- **unified_vision.py**: Modify to use person_id instead of raw encoding
- **jarvis_pure_adaptive_claude_launcher.py**: Update face recognition integration

### Priority 3: Voice Announcements
- **unified_vision.py**: Add TTS announcement triggers
- Import and use existing TTS functions from assist_local.py

### Priority 4: Management Commands
- Add new command patterns for:
  - "List family members"
  - "Forget [name]"
  - "Update [name] relationship"

## Similar Features Analyzed

### Face Recognition Server
- Already handles person management
- Has announcement system built-in
- Stores encodings internally
- Returns person_id for reference

### Enhanced Jarvis Vision
- Shows TTS integration patterns
- Contextual greeting examples
- Camera speaker integration

## Technical Constraints

1. **Face Encodings**: 128-dimensional numpy arrays, not easily transferable
2. **Database Location**: Must be in mcp_tools directory
3. **Voice Cooldown**: 30-second minimum between same-person greetings
4. **Camera Warmup**: Needs time to initialize before capture

## Integration Points Identified

1. **Face Recognition API**:
   - POST /add_person - Add new person with image
   - GET /people - List all known people
   - DELETE /remove_person/{person_id} - Remove person

2. **TTS Integration**:
   - Import: `from Jarvis.core.assist_local import TTS`
   - Usage: `TTS(f"Hello {name}, nice to see you")`

3. **Database Access**:
   - All tools use sqlite3 directly
   - No ORM layer
   - Direct SQL queries