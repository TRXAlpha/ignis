# IGNIS presentation video (30 s, talking + live site)

Challenge: **Flame in Freefall: SI-Powered Fire Safety Insights from Microgravity Combustion Data**
Live site: https://ignis-ai.study · Code: https://github.com/TRXAlpha/ignis

Format: you on camera in a corner, the live website in the middle, scrolling while you talk.
Structure follows the official Space Apps tips (intro, challenge + why, name + tagline, how it works + key insight,
impact + future). One tweak: the challenge beat states the problem in plain words, so "why it matters" lands fast.

---

## 1. What you say, and what you press

Open **https://ignis-ai.study/?demo=1**. In demo mode the number keys glide the page to each talking point
(and key 4 switches the chart to the 2D view). Nothing about demo mode is visible on screen.

Speak at a natural, slightly brisk pace and smile at the start.

| Time | Beat | You say | Press | On screen |
|---|---|---|---|---|
| 0:00-0:02 | Intro | "Hi, I'm **[your name]**, from team **[team name]**." | (start on the hero) | Hero: the real flame from the Space Station |
| 0:02-0:06 | Challenge + why | "Our challenge is Flame in Freefall: fire acts differently in space, yet spacecraft materials are tested on Earth." | | Hero headline |
| 0:06-0:10 | Name + tagline | "We built **IGNIS**, an AI that learns where flames stop burning in orbit." | **2** | How the AI Works, eight stages |
| 0:10-0:15 | How it works | "AI agents read NASA's space station experiments and verify every number against its source." | **3** | Key numbers row |
| 0:15-0:22 | Key insight | "Key insight: plastic keeps burning at **13.6 percent** oxygen. On Earth, the limit is **15.4**." | **4** | 2D boundary with the dashed 15.4 % line |
| 0:22-0:26 | Impact | "So Earth tests aren't always safe." | **6** | Habitat cards: Moon and Mars air, INSUFFICIENT DATA |
| 0:26-0:30 | Future vision | "Next: fly the experiments IGNIS suggests, for the Moon and Mars." | **7** | Next Experiments table |

About 80 words. If you run short, after "aren't always safe" add: "And you can ask it questions; it can't make numbers
up," pressing **5** (Ask the AI Analyst) before **6**.

### Teleprompter version (read this)

> Hi, I'm [your name], from team [team name].
>
> Our challenge is Flame in Freefall: fire acts differently in space, yet spacecraft materials are tested on Earth.
>
> We built IGNIS, an AI that learns where flames stop burning in orbit. [2]
>
> AI agents read NASA's space station experiments and verify every number against its source. [3]
>
> Key insight: plastic keeps burning at 13.6 percent oxygen. On Earth, the limit is 15.4. [4]
>
> So Earth tests aren't always safe. [6]
>
> Next: fly the experiments IGNIS suggests, for the Moon and Mars. [7]

---

## 2. OBS setup (camera in the corner, site in the middle)

**Canvas.** Settings > Video: Base and Output resolution 1920 x 1080, 30 fps.

**Scene "IGNIS demo"**, sources from bottom to top:
1. **Window Capture** of the browser (or Display Capture). Fit to the full canvas.
   The site's content column is centred (1180 px wide), so at 1920 px there is about 370 px of empty margin on each side.
   That margin is where the camera goes, so it never covers the numbers or the chart.
2. **Video Capture Device** (your webcam), about 360 x 360 px, placed bottom-right, 40 px from the edges.
   Right-click > Filters > add **Image Mask/Blend** with a circle or rounded-square PNG for a round camera, or
   **Crop/Pad** for a tidy square. A thin border reads well on the dark site: add a Color Source slightly larger behind it.
3. Optional **Text** source in the top-left for 2 seconds: "IGNIS · NASA Space Apps 2026" (then hide it).

**Audio** (Mic/Aux > Filters, in this order): Noise Suppression (RNNoise), Noise Gate (open -32 dB, close -40 dB),
Compressor (ratio 3:1, threshold -18 dB), Limiter (-1 dB). Peaks should sit around -10 dB on the meter.
Mute Desktop Audio so notification sounds can't leak in.

**Recording.** Settings > Output > Recording: format MKV (safe if OBS crashes), then File > Remux to MP4.
Encoder: NVIDIA NVENC if available, rate control CQP 18-20; otherwise x264, CRF 18.

**Browser.**
- Use the live site with `?demo=1`, press **F11** for full screen, zoom 100 % (or 110 % if text looks small on video).
- Load it once before recording so the 3D chart and fonts are cached; start recording on the hero.
- Turn on Do Not Disturb (Windows Focus Assist) so no pop-ups appear.

**Camera and light.** Camera at eye level, a light or window in front of you (not behind), look into the lens on the
intro line, then glance at the screen while it scrolls. That looks natural.

---

## 3. Rehearsal and take

1. Read the teleprompter version out loud twice with a timer. Aim for 28-30 s.
2. Do a dry run pressing the keys, so the scrolls land on the beats.
3. Record 3 takes, keep the best. No need to edit if a take is clean; otherwise trim the start and end only.
4. Add subtitles (YouTube auto-captions, or CapCut) from the teleprompter text: many judges watch muted.
5. Export 1080p, 30 fps, MP4 (H.264). Check the first and last second are not cut off.

---

## 4. Longer cut (75 s, optional, for judges who want depth)

| Time | Voice-over | Press / on screen |
|---|---|---|
| 0:00-0:06 | "Fire in space behaves differently. Hot air doesn't rise, so a flame only gets oxygen from fans and vents." | 1, hero flame |
| 0:06-0:13 | "Spacecraft materials are still screened with Earth tests. IGNIS is an AI built to check whether that is safe." | 2, How the AI Works |
| 0:13-0:24 | "AI agents read NASA's reports and raw data, a verification gate checks every number against the exact page, and machine learning learns where flames go out. Here the limit is 13.6 percent oxygen. The Earth rule says 15.4." | 4, 2D boundary |
| 0:24-0:32 | "Click any point and you see where it came from: the report, the page, the figure, the pixel." | Click a black X, provenance panel |
| 0:32-0:41 | "We test it honestly. Trained on the Space Station, it beats the Earth rule on drop-tower tests, and the other way round." | Validation (nav link) |
| 0:41-0:50 | "It also uses NASA's raw tables. On Saffire-II, silicone burned on Earth but went out in orbit. So you have to check each material." | Earth vs orbit (nav link) |
| 0:50-0:58 | "It re-measures flame speed from NASA's own flight photos, and tests the papers' claims. Where they disagree, it says so." | Flight video, then Checks (nav links) |
| 0:58-1:06 | "You can ask the AI analyst questions. It answers only through its tools, and any number it can't back up is blocked." | 5, Ask the AI Analyst |
| 1:06-1:15 | "For Moon and Mars air, where nobody has flown fire tests, it says: not enough data. And it tells NASA which experiments to fly next." | 6, then 7 |

---

## 5. Numbers used, and where they come from

| Number | Meaning | File / field |
|---|---|---|
| 13.6 % O2 (band 13.4-13.9 %) | fitted lowest oxygen where PMMA keeps burning | `model.json` → `min_o2` |
| 15.4 % O2 | normal-gravity upward-spread limit | BASS-II report p84 (verbatim-checked) |
| 2.0 % vs 2.7 % | boundary error, held-out drop tower, IGNIS vs Earth rule | `validation.json` → fold `loco-bass-ii-zgrf` |
| 24 flames below 15.4 % | stable flames burning below the Earth limit | `contradictions.json` → `1g-limit-vs-flight` |
| 3 of 4 silicone samples | burned at 1g, not in orbit | `material_screen.json` (PSI-99) |
| 158 observations, 13 sources | dataset size | `bundle.json` |
