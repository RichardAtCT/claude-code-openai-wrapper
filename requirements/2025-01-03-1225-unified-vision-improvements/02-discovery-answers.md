# Discovery Answers - Unified Vision Improvements

## Q1: Will the system need to handle multiple simultaneous users introducing themselves?
**Answer:** No
- One person introduces themselves at a time
- Simplifies voice-to-face matching

## Q2: Should the system remember faces across different camera sources?
**Answer:** Yes
- Consistent recognition across webcam, UniFi Protect, etc.
- Single identity database for all camera sources

## Q3: Will users need to modify or remove previously introduced family members?
**Answer:** Yes
- Need commands to update relationships
- Need ability to remove people from database
- Critical finding: Database table is currently missing!

## Q4: Should the system provide voice announcements when recognizing known people?
**Answer:** Yes
- Natural voice greetings when recognizing people
- Enhances the interactive experience

## Q5: Do you want the system to learn faces automatically without explicit introduction?
**Answer:** No
- Privacy-first approach
- Only learn faces when explicitly introduced
- User maintains control over who is remembered

## Critical Issue Discovered:
During testing with "hi i am George", the system correctly detected the introduction but failed with:
```
Error adding family member: no such table: family_members
```
This indicates the database is not properly initialized in the expected location.