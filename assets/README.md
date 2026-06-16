# Branding assets (optional)

Place bumper clips here; compose.py prepends/appends them per language if present:

- `intro_bg.mp4`, `intro_en.mp4`  — prepended
- `outro_bg.mp4`, `outro_en.mp4`  — appended

compose normalizes each segment to 1920x1080@fps h264/aac before concat, so exact codec
match isn't required (a silent audio track is added if a bumper has none). If absent, the
recorded body is the final video.
