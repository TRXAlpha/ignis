# IGNIS demo video script (English)

Live site: https://ignis-flame-one.vercel.app · Code: https://github.com/TRXAlpha/ignis

Every number spoken or shown below comes from the live data files (`web/public/data/*.json`, export of 2026-11-15).
If you re-export before recording, re-check the four numbers in the table at the bottom.

---

## Main cut: 30 seconds

Challenge: **Flame in Freefall: SI-Powered Fire Safety Insights from Microgravity Combustion Data.** The AI leads.
About 75 words of voice-over, calm and clear, roughly 2.5 words per second.

| Time | Voice-over | On screen (what to record) |
|---|---|---|
| 0:00-0:04 | "This is a real flame, burning on the International Space Station." | Hero: the BASS-II flight frame, headline "An AI That Learns Where Flames Stop Burning in Orbit." |
| 0:04-0:10 | "IGNIS is an AI that learns from NASA's fire experiments. AI agents read the reports, raw data and flight photos." | Scroll through "How the AI Works", the eight stages. |
| 0:10-0:15 | "Every number is checked against its source page, so the AI can't make anything up." | Click **2D boundary**, click one black X, the provenance panel opens with "PDF page 84". |
| 0:15-0:21 | "Machine learning finds the limit: plastic keeps burning at 13.6 percent oxygen. Earth tests assume 15.4." | Key numbers row, then the 2D boundary with the dashed 15.4% line. |
| 0:21-0:26 | "Ask it anything. It answers only from the data, and blocks any number it can't back up." | "Ask the AI Analyst": a recorded run with its tool calls. |
| 0:26-0:30 | "For Moon and Mars air, it says: not enough data yet. Fire safety insight you can check." | Habitat cards with **INSUFFICIENT DATA**, then the URL. |

**Title card (optional, 1 s before 0:00):** IGNIS: SI-powered fire safety insights.
**End card (hold 2 s after 0:30):** ignis-flame-one.vercel.app · github.com/TRXAlpha/ignis · NASA Space Apps 2026

---

## Extended cut: 75 seconds (for judges who want depth)

| Time | Voice-over | On screen |
|---|---|---|
| 0:00-0:06 | "Fire in space behaves differently. Hot air doesn't rise, so a flame only gets oxygen from fans and vents." | Hero flame frame. |
| 0:06-0:13 | "Spacecraft materials are still screened with Earth tests. IGNIS is an AI built to check whether that is safe." | "How the AI Works" section. |
| 0:13-0:24 | "AI agents read NASA's reports and raw data, a verification gate checks every number against the exact page, and machine learning learns where flames go out. Here the limit is 13.6 percent oxygen. The Earth rule says 15.4." | 3D surface rotating, then 2D boundary with the band and the dashed 15.4% line. |
| 0:24-0:32 | "Click any point and you see where it came from: the report, the page, the figure, the pixel." | Click a point, provenance panel. Open "The NASA Figure These Points Were Read From". |
| 0:32-0:41 | "We test it honestly. Trained on the Space Station, it beats the Earth rule on drop-tower tests, and the other way round." | Validation section, both leave-one-campaign-out tables. |
| 0:41-0:50 | "It also uses NASA's raw tables. On Saffire-II, silicone burned on Earth but went out in orbit. So you have to check each material." | Earth vs orbit table, then BASS-II Flight Tests by Material cards. |
| 0:50-0:58 | "It re-measures flame speed from NASA's own flight photos, and tests the papers' claims. Where they disagree, it says so." | Flight imagery section (tracked front, TENSION badge), then Consistency Checks. |
| 0:58-1:06 | "It suggests the next experiments that would teach us the most, inside what the hardware can do." | Next Experiments table and the stars on the 2D boundary. |
| 1:06-1:11 | "You can ask the AI analyst questions. It answers only through its tools, and any number it can't back up is blocked." | "Ask the AI Analyst" recorded runs. |
| 1:11-1:15 | "And for Moon and Mars air, where nobody has flown fire tests, it says: not enough data. SI-powered insight you can check." | Habitat cards, end card. |

---

## Recording checklist

1. Browser at 1440 x 900, dark system theme, zoom 100 %, bookmarks bar hidden.
2. Open the live site, wait for the 3D surface to finish loading before you start.
3. Use smooth scrolling (trackpad or the nav links). The nav links jump to each section.
4. For the provenance click: switch to **2D boundary** first, then click a black X near the bottom of the U.
5. Record the voice-over separately and lay it on top; keep music very low (or none).
6. Export 1080p, 30 fps, H.264. Add burned-in subtitles from the voice-over column.

## Numbers used, and where they come from

| Number | Meaning | File / field |
|---|---|---|
| 13.6 % O2 (band 13.4-13.9 %) | fitted lowest oxygen where PMMA keeps burning | `model.json` → `min_o2` |
| 15.4 % O2 | normal-gravity upward-spread limit | BASS-II report p84 (verbatim-checked) |
| 2.0 % vs 2.7 % | boundary error, held-out drop tower, IGNIS vs Earth rule | `validation.json` → fold `loco-bass-ii-zgrf` |
| 24 flames below 15.4 % | stable flames burning below the Earth limit | `contradictions.json` → `1g-limit-vs-flight` |
| 3 of 4 silicone samples | burned at 1g, not in orbit | `material_screen.json` (PSI-99) |
| 158 observations, 13 sources | dataset size | `bundle.json` |
