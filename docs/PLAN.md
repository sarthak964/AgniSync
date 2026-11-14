# Prototype build plan

1. Use Python 3.12 and Streamlit, with a verified Almora boundary and a FIRMS CSV import that works without a key.
2. Keep the two satellite streams separate and reduce detections to occupied 1 km grid cells per UTC day. Use archived deliveries to distinguish zeros, incomplete months and unknown intervals.
3. Compare the streams on common months. Fit one coefficient on 2013–2021 and evaluate it on 2022–2025 before deciding whether to use adjusted VIIRS in the calendar.
4. Connect the selected month to a historical comparison, NASA POWER weather evidence and filtered downloads. Verify the real-data path and synthetic UI separately.
