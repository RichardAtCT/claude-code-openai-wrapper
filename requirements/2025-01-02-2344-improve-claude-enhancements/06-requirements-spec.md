# Vision and Face Recognition Enhancement Requirements Specification

## Problem Statement
The current Jarvis vision system provides technical, robotic responses ("I can see 2 people, with 61% confidence") and lacks the ability to recognize and remember family members. Users want a more natural, personalized vision experience that can identify family members and provide contextual responses.

## Solution Overview
Create a unified vision system that seamlessly combines object detection with face recognition, allowing Jarvis to recognize family members, remember them persistently, and provide natural, personalized responses. The system will support natural voice introductions and work across multiple camera sources.

## Functional Requirements

### FR1: Unified Vision Experience
- **FR1.1:** Merge vision and face_recognition tools into a single intelligent vision pipeline
- **FR1.2:** Automatically use face recognition when people are detected
- **FR1.3:** Provide seamless responses without users needing to choose specific tools
- **FR1.4:** Handle commands like "who is that?", "do you see me?", "who's here?" with unified logic

### FR2: Family Member Recognition
- **FR2.1:** Identify and name recognized family members in responses
- **FR2.2:** Distinguish between known family members and unknown people
- **FR2.3:** Track relationships (wife, husband, son, daughter, parent, etc.)
- **FR2.4:** Provide natural responses like "I see your wife Sarah" instead of "I see 1 person"

### FR3: Natural Voice Introduction
- **FR3.1:** Support voice commands like "This is my wife Sarah" during live camera view
- **FR3.2:** Capture face automatically when introduction is made
- **FR3.3:** Parse relationship and name from natural language
- **FR3.4:** Confirm successful addition with natural response

### FR4: Persistent Storage
- **FR4.1:** Store family member data in jarvis_learning.db
- **FR4.2:** Include face encodings, names, relationships, and metadata
- **FR4.3:** Survive system restarts and updates
- **FR4.4:** Support updating and removing family members

### FR5: Multi-Camera Support
- **FR5.1:** Work with webcam (camera ID 0) by default
- **FR5.2:** Integrate with UniFi Protect cameras when available
- **FR5.3:** Maintain consistent recognition across all camera sources
- **FR5.4:** Allow camera selection for specific operations

### FR6: Natural Language Responses
- **FR6.1:** Replace technical confidence scores with natural language
- **FR6.2:** Prioritize people identification over object detection
- **FR6.3:** Use Claude enhancement for contextual responses
- **FR6.4:** Include relationship context in responses

## Technical Requirements

### TR1: Database Schema
- **TR1.1:** Add family_members table to jarvis_learning.db:
  ```sql
  CREATE TABLE family_members (
      id INTEGER PRIMARY KEY,
      name TEXT NOT NULL,
      relationship TEXT,
      face_encoding BLOB,
      added_date TIMESTAMP,
      last_seen TIMESTAMP,
      camera_source TEXT,
      metadata JSON
  );
  ```
- **TR1.2:** Add face_recognition_history table for tracking
- **TR1.3:** Implement proper indexes for fast lookups

### TR2: Tool Integration Changes
- **TR2.1:** Modify `jarvis_pure_adaptive_claude_launcher.py`:
  - Create unified vision handler that calls both tools
  - Add voice introduction parser
  - Enhance response formatting
- **TR2.2:** Update vision tool to return face regions for recognition
- **TR2.3:** Extend face_recognition tool with family member APIs
- **TR2.4:** Add relationship parsing to command processing

### TR3: Natural Introduction Flow
- **TR3.1:** Detect introduction patterns: "This is my [relationship] [name]"
- **TR3.2:** Capture current camera frame when introduction detected
- **TR3.3:** Extract face from frame and generate encoding
- **TR3.4:** Store in database with relationship metadata

### TR4: Response Enhancement
- **TR4.1:** Modify `format_vision_response()` to check for recognized faces first
- **TR4.2:** Update Claude vision enhancement to include family context
- **TR4.3:** Create natural language templates for different scenarios
- **TR4.4:** Remove technical details from user-facing responses

### TR5: Privacy & Security
- **TR5.1:** All face data stored locally only (no cloud)
- **TR5.2:** Face encodings encrypted in database
- **TR5.3:** Access control for family member management
- **TR5.4:** Audit trail for additions/modifications

## Implementation Hints

### Unified Vision Pipeline Pattern
```python
async def unified_vision_analysis(image_or_camera):
    # Step 1: Get basic vision detection
    vision_result = await vision_tool.describe_scene()
    
    # Step 2: If people detected, run face recognition
    if vision_result.get('people_count', 0) > 0:
        face_result = await face_recognition_tool.detect_faces()
        
        # Step 3: Merge results intelligently
        for person in face_result.get('recognized', []):
            # Look up family member data
            family_info = get_family_member(person['name'])
            if family_info:
                person['relationship'] = family_info['relationship']
    
    # Step 4: Generate natural response
    return format_unified_vision_response(vision_result, face_result)
```

### Voice Introduction Pattern
```python
def parse_introduction(command):
    # Pattern: "This is my [relationship] [name]"
    patterns = [
        r"this is my (\w+) (\w+)",
        r"meet my (\w+) (\w+)",
        r"(\w+) is my (\w+)"
    ]
    
    for pattern in patterns:
        match = re.search(pattern, command.lower())
        if match:
            return {
                'relationship': match.group(1),
                'name': match.group(2).capitalize()
            }
```

### Natural Response Templates
```python
RESPONSE_TEMPLATES = {
    'family_single': "I see your {relationship} {name}",
    'family_multiple': "I see {names}",
    'family_with_unknown': "I see {family_names} and {unknown_count} other person(s)",
    'no_one': "I don't see anyone right now",
    'unknown_only': "I see {count} person(s) I don't recognize"
}
```

## Acceptance Criteria

### AC1: Unified Vision
- [ ] Single command "who do you see?" works without specifying tool
- [ ] Vision and face recognition happen automatically
- [ ] No technical tool selection required from user

### AC2: Family Recognition
- [ ] Recognized family members are named in responses
- [ ] Relationships are included naturally
- [ ] Unknown people are distinguished from family

### AC3: Voice Introduction
- [ ] "This is my wife Sarah" successfully adds Sarah
- [ ] Natural confirmation provided
- [ ] Face captured and stored correctly

### AC4: Persistence
- [ ] Family members remembered after restart
- [ ] Database properly stores all information
- [ ] Can list all family members

### AC5: Natural Responses
- [ ] No confidence percentages in responses
- [ ] Relationship context included
- [ ] Responses sound conversational

## Assumptions
1. Face recognition server (192.168.1.95:8001) is running and accessible
2. Users have working webcam for primary interactions
3. jarvis_learning.db is writable and backed up
4. Face recognition model is accurate enough for family members
5. Users will introduce family members one at a time

## Out of Scope
- Security alerts for unknown people (future feature)
- Facial expression or emotion recognition
- Age or gender detection
- Cloud backup of face data
- Mobile app integration