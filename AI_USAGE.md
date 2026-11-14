# Team contributions and use of Super Intelligence (SI)

Our team, Antariksh Guru, worked together to plan AgniSync and gather the data for our Almora case study. We shaped the project around a shared fire activity calendar and a way to investigate where MODIS and VIIRS observations agree. We gathered historical hotspot records from NASA FIRMS and weather data from NASA POWER.

We used OpenAI Codex to turn that plan into a working prototype. Codex helped us research data sources, work through the analysis, build and debug the Python processing and dashboards, design the Flask interface, and prepare tests, documentation, and submission text.

AgniSync uses scikit-learn linear regression to express VIIRS activity on the Aqua MODIS scale. It generates explanations from calculated values using fixed rules. The separately labeled synthetic mode uses a fixed-seed Python generator developed with Codex. Evidence downloads record the data sources and Codex assistance in `provenance.json`.

Codex also produced the captioned demo from screenshots of the running Flask dashboard. The watermarked submission copy identifies Codex's role on screen and uses English captions.
