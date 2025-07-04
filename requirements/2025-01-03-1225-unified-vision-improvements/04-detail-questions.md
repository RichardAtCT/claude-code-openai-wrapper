# Detail Questions - Unified Vision Improvements

## Q1: Should the unified_vision.py automatically create database tables if they don't exist?
**Default if unknown:** Yes (prevents the "no such table" error and improves user experience)

## Q2: Should we store face_recognition server person_id instead of duplicating face encodings?
**Default if unknown:** Yes (cleaner architecture, single source of truth for face data)

## Q3: Should voice announcements use the person's relationship in greetings (e.g., "Hello, sir" for creator vs "Welcome back, Sarah")?
**Default if unknown:** Yes (more personalized and contextual greetings)

## Q4: Should the system support both immediate TTS announcements AND UniFi camera speaker output?
**Default if unknown:** Yes (flexibility for different deployment scenarios)

## Q5: Should face recognition have a confidence threshold below which introductions are rejected?
**Default if unknown:** Yes (60% confidence minimum to ensure quality matches)