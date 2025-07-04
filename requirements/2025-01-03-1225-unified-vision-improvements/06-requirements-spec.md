# Requirements Specification - Unified Vision Improvements

## Problem Statement

The unified vision system for Jarvis has been integrated but has several critical issues preventing it from working properly:

1. **Database initialization failure** - "no such table: family_members" error
2. **Face encoding storage** - Using placeholder encodings instead of real data
3. **No voice announcements** - System doesn't greet recognized people
4. **Missing management features** - No way to update/remove family members

## Solution Overview

Enhance the unified vision system to:
- Auto-initialize database tables on first run
- Properly integrate with face_recognition server using person_id references
- Add voice announcements when recognizing people
- Provide management commands for family members
- Ensure reliable face quality for introductions

## Functional Requirements

### FR1: Database Auto-Initialization
- System MUST create database tables automatically if they don't exist
- Tables created on UnifiedVisionSystem class initialization
- No manual database setup required

### FR2: Face Recognition Integration
- System MUST use face_recognition server's person_id instead of storing encodings
- When introducing someone:
  1. Call face_recognition tool's `add_person` operation
  2. Store returned person_id in family_members table
  3. Link family relationship data to face recognition records

### FR3: Voice Announcements
- System MUST announce recognized people by name
- Format: "Hello, [name]" (e.g., "Hello, George")
- Support both:
  - Immediate TTS through computer speakers
  - UniFi camera speaker output for location-specific greetings
- 30-second cooldown between same-person announcements

### FR4: Introduction Commands
- Support patterns:
  - "This is my [relationship] [name]"
  - "I am [name]"
  - "It's me [name]"
  - "[name] is my [relationship]"
- Detect creator context: "I created you" → relationship = "creator"

### FR5: Management Commands
- List family members: "Who do you know?"
- Remove person: "Forget [name]"
- Update relationship: "[name] is now my [new relationship]"

### FR6: Quality Control
- Minimum 60% face detection confidence for introductions
- Reject poor quality: "I can't see you clearly enough to remember your face"
- Ensure reliable recognition by storing only high-quality captures

## Technical Requirements

### TR1: Database Schema Updates
```sql
-- Modify family_members table
ALTER TABLE family_members ADD COLUMN person_id INTEGER;
ALTER TABLE family_members ADD COLUMN confidence REAL;

-- person_id links to face_recognition server's database
-- confidence stores the detection confidence at introduction time
```

### TR2: Code Structure
1. **unified_vision.py**:
   - Add `_ensure_tables_exist()` method
   - Modify `add_family_member()` to use person_id
   - Add voice announcement triggers
   - Implement management command handlers

2. **jarvis_pure_adaptive_claude_launcher.py**:
   - Update face recognition integration
   - Add management command patterns
   - Ensure proper error handling

### TR3: Voice Integration
```python
# Import TTS functionality
from Jarvis.core.assist_local import TTS

# For camera speakers
from tools.unifi_protect.audio_integration import speak_through_camera
```

### TR4: Face Recognition API Calls
- Use `POST /add_person` when introducing
- Store returned person_id
- Use `DELETE /remove_person/{person_id}` when forgetting

## Implementation Details

### File Modifications

1. **unified_vision.py** (Priority 1)
   - Add database initialization in `__init__`
   - Change face_encoding storage to person_id
   - Add TTS announcement methods
   - Implement management commands

2. **jarvis_pure_adaptive_claude_launcher.py** (Priority 2)
   - Update unified vision handler
   - Add command patterns for management
   - Improve error handling

3. **create_family_members_db.py** (Priority 3)
   - Update schema to include person_id
   - Add confidence column

### Patterns to Follow

1. **Database Access**: Direct SQLite queries (no ORM)
2. **Error Handling**: Try-except blocks with user-friendly messages
3. **Logging**: Use existing logging infrastructure
4. **Response Format**: Natural language with unified_vision flag

## Acceptance Criteria

1. ✓ "hi i am George" successfully stores George as creator
2. ✓ System says "Hello, George" when recognizing him
3. ✓ No database errors on first run
4. ✓ "Who do you know?" lists all family members
5. ✓ "Forget Sarah" removes Sarah from database
6. ✓ Low confidence faces are rejected with helpful message
7. ✓ Voice works through both speakers and cameras
8. ✓ 30-second cooldown prevents announcement spam

## Assumptions

1. Face recognition server is running and accessible
2. TTS systems (ElevenLabs/AllTalk) are configured
3. User has at least one camera (webcam or UniFi)
4. SQLite database permissions allow table creation
5. Audio output devices are properly configured

## Future Enhancements (Out of Scope)

1. Multi-face simultaneous introductions
2. Automatic face learning without introduction
3. Face recognition on mobile devices
4. Export/import of family database
5. Photo album integration for batch face learning

## Success Metrics

- Zero database errors in first 100 uses
- 95%+ successful face introductions (when confidence > 60%)
- Voice announcements within 2 seconds of recognition
- All management commands work reliably
- User satisfaction with natural interactions