# Detail Answers - Unified Vision Improvements

## Q1: Should the unified_vision.py automatically create database tables if they don't exist?
**Answer:** Yes
- Add auto-initialization to prevent "no such table" errors
- Improves first-run experience
- Tables created on UnifiedVisionSystem initialization

## Q2: Should we store face_recognition server person_id instead of duplicating face encodings?
**Answer:** Yes
- Store person_id reference instead of raw encoding
- Single source of truth in face_recognition server
- Cleaner architecture, less data duplication

## Q3: Should voice announcements use the person's relationship in greetings?
**Answer:** No - use person's name
- Always greet by name: "Hello, George"
- Not relationship-based like "Hello, sir"
- Direct, personal greetings preferred

## Q4: Should the system support both immediate TTS announcements AND UniFi camera speaker output?
**Answer:** Yes
- Support both output methods
- Computer speakers for immediate feedback
- Camera speakers for door/location-specific greetings
- Configurable per situation

## Q5: Should face recognition have a confidence threshold below which introductions are rejected?
**Answer:** Yes
- 60% confidence minimum for storing faces
- Reject poor quality captures
- User feedback: "I can't see you clearly enough"
- Ensures reliable recognition later