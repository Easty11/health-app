"""RAW prod `user_knowledge` lines for user 1 — the G1 "before" fixture (operator read, 2026-09-27).

Rows 2 (Injury History, 66 lines), 3 (Training Background, 13 lines) and 5 (Other, 58 lines).
The S0(c) prod regex `hamstring|semimembranosus|striding|sprint` matches 15 of those lines:
13 in row 2, 1 in row 3, 1 in row 5. Every one of the 15 is carried here VERBATIM at its REAL
line index, so a sweep hit's (row_id, line_index) can be checked against prod directly.

Also carried, verbatim, as controls: lines the sweep's derived terms reach but the prod regex
does not (row 3 lines 10 and 12, via "stretch"), and near-miss negatives (row 2 lines 54, 57, 63).

MINIMUM NECESSARY. Every other line is replaced by `OMITTED` — none of them matches any sweep term,
and rows 3 and 5 carry personal and medication detail (date of birth, suburb, prescriptions, blood
panels) that a test fixture has no need of. Line positions are preserved; content is not.
"""

OMITTED = "[omitted: not a sweep hit]"

ROW_LENGTHS = {2: 66, 3: 13, 5: 58}

ROW_CATEGORIES = {2: "Injury History", 3: "Training Background", 5: "Other"}

LINES = {
    # ── row 2 · Injury History ────────────────────────────────────────────────
    (2, 0): "Tweaked hamstring during a sprint at rugby training on 04 June 2026",
    (2, 8): "- Right semimembranosus — full-thickness partial-width proximal rupture 3.3 x 1.6cm "
            "(Aug 2025, rugby, played through)",
    (2, 34): "Hamstring tweak (04 Jun 2026 at training) — played through game on 06 Jun 2026 without "
             "further injury. Right shoulder (upper trap tear ~May 2026) — setback during game on 06 "
             "Jun 2026.",
    (2, 36): "Hamstring tweak (04 Jun 2026 at training) — played through game on 06 Jun 2026 without "
             "further injury. Sore with running and heel drags at certain angles but otherwise moving "
             "well. Consistent with minor grade 1 strain.",
    (2, 47): "Single-leg RDL introduced 10 Jul 2026 as hamstring lane Tier-1 rehab item — graded "
             "exposure to long-lever hamstring load, symptom-gated. Controlled eccentric focus. Askling "
             "extender used as optional primer. Key data point: how long-lever RDL load feels vs seated "
             "curl — feeds neural-vs-capacity question on right hamstring. Slump test remains "
             "adjudicator.",
    (2, 48): "Single-leg RDL introduced 10 Jul 2026 as hamstring lane Tier-1 rehab item — graded "
             "exposure to long-lever hamstring load, symptom-gated. Controlled eccentric focus. Askling "
             "extender used as optional primer. Key data point: how long-lever RDL load feels vs seated "
             "curl — feeds neural-vs-capacity question on right hamstring. Slump test remains "
             "adjudicator. Right SLRDL: discomfort behind knee at 32kg RPE 9, dropped to 28kg RPE "
             "7.5-8. Left SLRDL: 32kg RPE 7.5-8 clean. 12.5% load gap documented. Left knee click "
             "noted during BSS — painless but 'feels loose', monitoring.",
    (2, 52): "RIGHT HAMSTRING REHAB SYNTHESIS (as of 11 Jul 2026): Bottom line — sprint limitation is "
             "substantially neural (sensitised right S1 tract), not the proximal semimembranosus tear. "
             "Slump test positive right side, behind knee → calf = S1 pattern → central L5-S1 "
             "herniation irritating traversing S1 root (not L5 foraminal narrowing). TWO LANES: A — "
             "Neural (confirmed): sensitised right sciatic/tibial tract, caps sprinting at max tract "
             "tension. Use neural sliders not tensioners, drop static end-range stretching (tensions "
             "sensitised tract). Keep graded lengthened-load (SLRDL) reframed as desensitisation, gated "
             "on calf/behind-knee symptom not tear site. Askling glider only after slider base. Don't "
             "force sprinting while slump frankly positive — gate is tract calming not willpower. B — "
             "Lumbopelvic (distinct): stretch + rotation → top-of-hip/obliques/glute-med, not "
             "slump-provoked. Myofascial/facet (L4-5 facet, L5 pars). Co-locates with motor deficit "
             "(right BSS failure + step-up valgus) = right-side frontal-plane dysfunction. Avoid loaded "
             "spinal-rotation stretch. Standing cable twist 25kg ran clean — keep it. EVIDENCE-RANKED "
             "LOADING: 1. Hip-extension eccentrics (semimembranosus-specific, Askling L-protocol) — "
             "proximal free-tendon = months not weeks. 2. Nordic-family eccentric — cuts incidence "
             "57-70%, reduces limb asymmetry. 3. Trunk stabilisation + agility. 4. Progressive "
             "pain-free high-speed running = terminal RTS gate. OPEN ITEMS: MRI lumbar spine (CT can't "
             "resolve root-level compromise) — flag right positive slump, S1-pattern referral, ask "
             "whether central L5-S1 herniation contacts traversing S1 root. No chiro manipulation "
             "without current neural imaging — positive neurodynamic finding + central herniation is a "
             "hard rule. Cross-domain: right lumbosacral neural apparatus live across >1 presentation "
             "(hamstring + voiding dysfunction hypothesis). Left knee medial soreness post-10 Jul "
             "session now attributed possibly to pes anserine from Copenhagen lever jump (not purely "
             "meniscal) — reassess cold.",
    (2, 53): "RIGHT HAMSTRING NEURAL CONTRAINDICATION (13 Jul 2026): Static end-range hamstring "
             "stretching CONTRAINDICATED. Right slump test positive — S1 distribution, behind-knee into "
             "calf. Mechanism: sensitised right S1 tract from central L5-S1 herniation, not proximal "
             "semimembranosus tear. Neural sliders replace static stretching. Do not prescribe static "
             "end-range hamstring stretching in any context.",
    # negative control: gracilis + semitendinosus, no hamstring/sprint/stride/stretch term
    (2, 54): "LEFT PES ANSERINE INSERTIONAL IRRITATION (onset 10 Jul 2026): Caused by Copenhagen lever "
             "jumping from short to mid/high shin, converging gracilis + semitendinosus + deep-flexion "
             "load. Symptom-gated (point tenderness), NOT date-gated. Still symptomatic at day 3 (13 "
             "Jul). Avoid: adductor tension beyond short-lever Copenhagen, deep-flexion unilateral "
             "(Bulgarian split squat, deep step-ups). Reassess Wednesday 15 Jul before programming "
             "Copenhagens or deep-flexion unilateral.",
    (2, 55): "RIGHT PROXIMAL SEMIMEMBRANOSUS RUPTURE — full-thickness partial-width 3.3 x 1.6cm (Aug "
             "2025, rugby, played through). Confirmed entry — was missing from injury store as of 13 "
             "Jul 2026 audit.",
    (2, 56): "LEFT CALF INJURY — 14 Jul 2026. Site: left mid-belly medial gastrocnemius. Onset: sudden, "
             "'felt like I got shot by a sniper.' Load at failure: near-zero. Stationary/near-stationary "
             "during seniors training, catching a ball. Limp post-injury. Pain not severe. Knee flexion "
             "pain-free when unresisted (gastroc-slackened position non-provocative). Thompson test "
             "PASSED (negative) 15 Jul — complete Achilles rupture EXCLUDED. No imaging yet — ultrasound "
             "is the sole blocking item. UNRESOLVED: mechanism inconsistency — 'propped on other leg, "
             "wasn't even taking off' vs 'foot touched the ground' implies opposite loading states at "
             "failure. Catapult SPT3 data: 1,214m total, 72.5% standing, 3.3% above jogging pace (84 "
             "seconds total), peak speed 6.0 m/s once at min 18, zero sprints, PlayerLoad 126au. Injury "
             "timestamp min 21. The load does not explain the injury. Interim management: heel wedges "
             "both shoes (highest priority), compression, elevation, isometric plantarflexion bent-knee "
             "first. No heel raises for reps, no stretching, no velocity work until graded by "
             "ultrasound. DVT flag active: Hct 0.47 and rising, acute calf injury, reduced mobility — if "
             "swelling builds rather than settles, scan immediately. Return to play note: scrummaging "
             "requires its own graded exposure (isometric wall drives before live scrum) — running "
             "progression does not clear for scrums.",
    # negative control: calf history, no sweep term
    (2, 57): "LEFT CALF — TRAINING HISTORY CONTEXT. Verified calf block Apr–Jun 2026 (~9 sessions): Calf "
             "Extension Machine 60×12 (24 Apr) → 61.5×15 RPE 8.5 (1 Jun). Standing Calf Raise Machine "
             "45-55kg. Single-leg calf raise: once (29 Apr). Gap: 1 Jun → 14 Jul = ZERO calf work, 43 "
             "days. Certain — verified by full session content read. Velocity/SSC/plyometric/RFD "
             "exposure: ZERO across entire record. Every calf entry slow, machine-based, high-rep. Cause "
             "of gap: programme-generation churn, muscle group silently dropped. Gastroc vs soleus "
             "attribution unrecoverable due to template mislabelling.",
    (2, 58): "LATERALITY PARADOX — documented 15 Jul 2026. Every structural and neurological finding is "
             "RIGHT. Every tissue failure is LEFT (left hamstring velocity gate, left pes anserine, left "
             "gastrocnemius 14 Jul). Right = compromised side (CT: right L5 root compromise, right "
             "foraminal narrowing; slump positive right, negative left; right BSS/SLRDL/step-up all "
             "weaker). Left = where things break. Left-side observations: 22 Jun suitcase carry — left "
             "foot less controlled than right under fatigue. 10 Jul — left knee click in trailing leg "
             "BSS, 4 days pre-calf injury. No unifying explanation in current data. Five models built "
             "and failed (S1 myotome cluster, cramp/hyperexcitability, magnesium depletion, "
             "fatigue-plus-capacity, untrained tissue). No sixth model generated — cause may be "
             "unmeasured or coincidental. Model graveyard is a hard stop — do not generate explanatory "
             "hypotheses without new data.",
    # negative control: leg curl / left knee, no sweep term
    (2, 63): "Lying leg curl contraindicated for left knee — full knee flexion at end range provocative "
             "(left knee inflammation). Switched to kneeling leg curl during 27 Jul session. Seated or "
             "kneeling variants only until left knee settles.",
    (2, 64): "Kneeling leg curl asymmetry noted 03 Aug 2026 — left hamstring does not reach full "
             "contraction (top range) compared to right at 40kg. Not painful or uncomfortable, just a "
             "contraction deficit at end range. Possibly pes anserine guarding or residual left "
             "calf/posterior chain inhibition post gastrocnemius injury (14 Jul). Monitor for "
             "persistence once pes anserine settles.",
    (2, 65): "LUMBAR SPINE — L4-5/L5-S1 RECURRENT SLIP (PARS-DEFICIENT SEGMENT). Structure: L5-S1 "
             "bilateral pars defects, anterolisthesis ~2.3mm, central disc herniation indenting thecal "
             "sac, right foraminal narrowing. L4-5 retrolisthesis. Right L5 nerve root possibly "
             "compromised. Positive slump test right, S1 distribution. Bilateral hamstring tightness is "
             "dural/central not muscular. Mechanism: pars defects = discontinuous bony arch, segment can "
             "translate. Injury vector = loaded end-range lumbar shear with loss of neutral (sumo squat "
             "at depth, deep conventional squat where neutral lost). Position-and-shear problem NOT load "
             "magnitude. Low load does not protect. Relief zone: neutral to gentle flexion. Extension "
             "provocative. Scrummaging is protective (braced, co-contracted, neutral trunk). "
             "Presentation: painless at slip, sore hours later as inflammation builds. Paraspinals/QL "
             "splint segment → lateral list. Recurrent, frequency declining. Management: 90/90 "
             "constructive rest, heat then gentle movement, neural glides, down-regulation breathing, "
             "NSAIDs if tolerated. No forced end-range extension (cobra/press-ups contraindicated), no "
             "deep static stretching, no aggressive trigger point work. Permanent constraints: loaded "
             "end-range lumbar shear gated permanently (sumo, wide/deep loaded squat where neutral "
             "slips), static hamstring stretching contraindicated. Hard stops: right-leg radicular signs "
             "past knee → escalate. Cauda equina signs → ED immediately. Trajectory: anti-shear + "
             "anti-rotation programme fortifying segment, recurrence declining. Goal: earn back bottom "
             "of squat via graded re-exposure.",
    # ── row 3 · Training Background ───────────────────────────────────────────
    (3, 2): "Graduated return to play — seniors training and games. Week 1 (w/c 16 Jun 2026): "
            "demonstrations only. Week 2: some running, no contact. Week 4: contact clearance target. No "
            "games for 4 weeks from 16 Jun 2026. Shoulder is primary limiting factor, not hamstring. "
            "Saturday games unavailable for 4 weeks — Saturday becomes available gym day.",
    # control: reached by the derived term "stretch", not by the prod regex
    (3, 10): "Decompression block swim sessions (Sep-Oct 2026) are rehab/stretch only — 30min, no laps, "
             "no intervals, no push-offs. Hydrotherapy movement, water walking, buoyancy-assisted ROM, "
             "neural glides, shoulder range work in water. Not aerobic lap swimming. Three sessions per "
             "week, flexible days Tue/Thu/Fri.",
    (3, 12): "Decompression block weekly structure (from Sep 2026): Monday — gym fortify; Tuesday — swim "
             "rehab; Wednesday — gym fortify; Thursday — swim rehab; Friday — gym or 3rd swim (read the "
             "week); Saturday — Clinical Pilates (morning); Sunday — active recovery (walk, easy "
             "movement). Swim sessions are rehab/stretch only — 30min, no laps, no intervals, no "
             "push-offs. Hydrotherapy movement, water walking, buoyancy-assisted ROM, neural glides, "
             "shoulder range work in water. Not aerobic lap swimming. Three sessions per week, flexible "
             "days Tue/Thu/Fri. Gym is 1 Million Strong. No clinical Pilates available locally — general "
             "class Saturday.",
    # ── row 5 · Other ─────────────────────────────────────────────────────────
    (5, 37): "- Tuesday 4:30pm: Optional — rehab now, rehab/sprint work once hamstring functional. "
             "Pre-seniors buffer. Seniors training 6-8pm (coach + player when fit)",
}

# The 15 lines the S0(c) prod regex matches — the operator's diagnosis count.
PROD_REGEX_HITS = {
    (2, 0), (2, 8), (2, 34), (2, 36), (2, 47), (2, 48), (2, 52), (2, 53), (2, 55), (2, 56),
    (2, 58), (2, 64), (2, 65), (3, 2), (5, 37),
}


def row_content(row_id: int) -> str:
    return "\n".join(LINES.get((row_id, i), OMITTED) for i in range(ROW_LENGTHS[row_id]))
