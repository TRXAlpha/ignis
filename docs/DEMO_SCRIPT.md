# IGNIS demo video script (English)

Live site: https://ignis-flame-one.vercel.app · Code: https://github.com/TRXAlpha/ignis

Every number spoken or shown below comes from the live data files (`web/public/data/*.json`, export of 2026-11-15).
If you re-export before recording, re-check the four numbers in the table at the bottom.

---

## Main cut: 30 seconds

About 75 words of voice-over, calm and clear, roughly 2.5 words per second.

| Time | Voice-over | On screen (what to record) |
|---|---|---|
| 0:00-0:04 | "This is a real flame, burning on the International Space Station." | Hero: the BASS-II flight frame. Slow push-in on the image. |
| 0:04-0:09 | "In orbit, plastic keeps burning at oxygen levels where Earth tests say it would go out." | Scroll to the four key numbers. Hold on **13.6% O2** next to **15.4%**. |
| 0:09-0:15 | "IGNIS learned that limit from NASA's own flight data. Every point links to its page in the report." | Boundary section, click **2D boundary**, click one black X. The provenance panel opens with "PDF page 84". |
| 0:15-0:20 | "Trained on the Space Station, it predicts drop-tower tests better than the Earth rule." | Validation table: **2.0%** vs **2.7%** boundary error, held out drop tower. |
| 0:20-0:25 | "It checks every material, and even the reports' own claims." | Earth vs orbit table (silicone rows: "1g conservative"), then the red **CONFLICT** card in Consistency Checks. |
| 0:25-0:30 | "For Moon and Mars air, nobody has tested fire yet. IGNIS says so. Fire safety you can check." | Habitat cards with **INSUFFICIENT DATA**, then the IGNIS wordmark and the URL. |

**Title card (optional, 1 s before 0:00):** IGNIS: where flames stop burning in orbit.
**End card (hold 2 s after 0:30):** ignis-flame-one.vercel.app · github.com/TRXAlpha/ignis · NASA Space Apps 2026

---

## Extended cut: 75 seconds (for judges who want depth)

| Time | Voice-over | On screen |
|---|---|---|
| 0:00-0:06 | "Fire in space behaves differently. Hot air doesn't rise, so a flame only gets oxygen from fans and vents." | Hero flame frame. |
| 0:06-0:13 | "Spacecraft materials are still screened with Earth tests. We wanted to know if that is safe." | Key numbers row. |
| 0:13-0:24 | "IGNIS reads NASA's reports and raw data, checks every number against the exact page, and learns where flames go out. Here the limit is 13.6 percent oxygen. The Earth rule says 15.4." | 3D surface rotating, then 2D boundary with the band and the dashed 15.4% line. |
| 0:24-0:32 | "Click any point and you see where it came from: the report, the page, the figure, the pixel." | Click a point, provenance panel. Open "The NASA Figure These Points Were Read From". |
| 0:32-0:41 | "We test it honestly. Trained on the Space Station, it beats the Earth rule on drop-tower tests, and the other way round." | Validation section, both leave-one-campaign-out tables. |
| 0:41-0:50 | "It also uses NASA's raw tables. On Saffire-II, silicone burned on Earth but went out in orbit. So you have to check each material." | Earth vs orbit table, then BASS-II Flight Tests by Material cards. |
| 0:50-0:58 | "It re-measures flame speed from NASA's own flight photos, and tests the papers' claims. Where they disagree, it says so." | Flight imagery section (tracked front, TENSION badge), then Consistency Checks. |
| 0:58-1:06 | "It suggests the next experiments that would teach us the most, inside what the hardware can do." | Next Experiments table and the stars on the 2D boundary. |
| 1:06-1:15 | "And for Moon and Mars air, where nobody has flown fire tests, it says: not enough data. Fire safety you can check." | Habitat cards, end card. |

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
