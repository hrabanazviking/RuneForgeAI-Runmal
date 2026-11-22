# R-15 — Appearance & Doctrine Pass (desktop definition)

Date: 2026-11-22. Slice R-15 of the Interface Redo plan
(Part 3): "Appearance & doctrine pass. Appendix-B-token
QSS theme (+ light variant), chamfered corner language,
ornament density, text scaling, reduced motion; Book XIV
removal battery on the real app (grayscale, no-glow,
no-art screenshots; 3-second silhouette read).
*Verification:* launch proof on F15 + purpleraider with
screenshot set reviewed against the battery; contrast AA
spot-checked." (The F15 + purpleraider legs are deferred
with the campaign's other owed proofs to R-17; the battery
ran on the VM seat — see the venue record.)

## Ground truth (doctrine, read from source 2026-11-22)

- **Appendix B tokens** (`Volmarr_Cyber_Viking_Master_
  Visual_Design_Lawbook.md`, repo root): void-000 #05080D,
  void-100 #081019, panel #0B1620, panel-raised #101F2A,
  iron #24313A, silver #CCD6DF, muted #8CA0AE, bifrost
  #42DDF5, rune #5AA8FF, seidr #9B70FF, forge #E3B75B,
  aurora #59DFAE, ember #F36A62; spacing 4–96; motion
  100/180/320/600 ms.
- **§2.3.16**: theme generated from the tokens (void
  darkness ladder, Bifröst/Seiðr/Forge accents at 5–12%
  coverage, chamfered corner language, ≥4 dark surfaces);
  light variant; text scaling to 200%; ornament-density
  setting; reduced motion; shell prefs persist via
  QSettings, engine-owned data via the engine; status is
  always icon + words.
- **Book XIV**: the removal battery — the theme must
  survive rune/glow/art removal; a strong implementation
  remains coherent in grayscale, at 125–200% text
  scaling, with long real content, and with atmospheric
  effects disabled; the primary task and primary action
  are obvious within roughly three seconds (the
  silhouette read).

## The slice

- **`desktop/theme.py`** (Qt-free by construction; a test
  asserts no PySide6 import): `DARK_TOKENS` (Appendix B
  verbatim + named derived roles — text, text-muted,
  text-disabled, border, border-strong, selection,
  focus, link, the five accent roles), `LIGHT_TOKENS`
  (the same roles on a pale-iron/paper ladder from the
  same family; accent hues kept where they hold AA on
  light surfaces and deepened where they do not — raw
  bifrost is ~1.6:1 on paper, so light bifrost is
  #067089; every choice is commented in the module),
  `build_qss(variant, ornament, text_scale)` (the full
  widget surface; ornament quiet = a single iron border,
  standard adds the stepped double-border frame-strength
  system, ceremonial adds accent-tipped frames at low
  coverage; text_scale clamps 1.0–2.0 and multiplies
  every font size off the 13px base), `contrast_ratio`
  (WCAG luminance) + `AA_PAIRS` (the 20 fg/bg pairs the
  app relies on), `SPACING`, `MOTION_TOKENS` +
  `motion_duration` (0 under reduced motion), and
  `AppearancePrefs` with dict (de)serialisation — the
  QSettings read/write lives in window glue, keeping the
  module Qt-free.
- **Appearance dialog** (View ▸ Appearance…, replacing
  the three R-15 placeholders): variant, ornament,
  scaling slider+spin (100–200%), reduced-motion switch,
  Apply (live + persisted), and words naming what each
  control does — including that shell prefs persist on
  this machine via QSettings while engine data is
  untouched. `MainWindow.apply_appearance` sets the
  stylesheet + scaled base font and records
  `reduced_motion` on the window; startup loads saved
  prefs and applies them before first show, so the app
  is themed out of the box (defaults: dark / standard /
  100% / motion on).

**Translations, stated plainly (not literal
implementations):** QSS has no clip-path, so the
doctrine's chamfered corners are expressed as squared
primary frames (border-radius 0) whose strength is
carried by the stepped double-border system; small
controls keep ≤4px radii. These are not true chamfers
and the module docstring says so. QSS also cannot drive
animation, so the motion tokens live as data +
`motion_duration()` for shell code to consult; the
reduced-motion switch is recorded truthfully on the
window — the shell has no animation engine yet to gate.

## The battery (Book XIV, run at the launch proof)

`scripts/desktop_r15_proof.py` — **18/18 checks PASS**
(VM, Qt 6.8.0 offscreen): themed out of the box
(stylesheet identical to `build_qss("dark","standard",
1.0)`), a real turn on stage before any shot (the
battery judges the app dressed, not empty), variant /
ornament / 200% scaling / reduced motion each applied
through the dialog and verified against the running app
(stylesheet identity, base font 13→26px, the window's
reduced-motion flag), contrast spot-checked mechanically
(**every AA pair ≥ 4.5 in both variants; worst pair
4.92 dark / 5.34 light**), restart with the kept look
(light/ceremonial/150%/reduced) in force again, clean
quit.

Screenshot set (7): dark-standard, dark-quiet (ornament
removed), dark-ceremonial, light-standard, dark-200, and
grayscale conversions of dark-standard and
light-standard. **Coordinator's read:** the silhouette
holds in every variant — the chat title, the transcript,
and the composer/Send dominate within seconds; the
grayscale legs lose nothing structural (selection and
hierarchy are luminance-carried, never hue-carried);
the light variant reads as the same civilization on
pale iron; at 200% the layout crowds (docks squeeze,
the transcript compresses) but nothing overlaps, clips,
or becomes unreachable. The dark shot's first-run banner
text is the proof's seeding order (the snapshot predates
the API seeding; the light shot, taken after a refresh,
shows the configured truth) — a proof cosmetic, not a
theme defect.

**Gates (VM seat, swift standard):** theme tests 11/11
(Qt-free, incl. the no-PySide6 assertion and the AA
table); window tests R-15 6/6 with R-14/R-13/R-12
neighbours = 33/33 under real PySide6 offscreen;
neighbour batch (R-13 logic, P-207 census, P-232 file)
71 passed with only the known pre-existing P-232 H1
failure; full-suite collection 6,722 (was 6,711); ruff
clean. Census unchanged (365/455) — no engine routes.
README.md untouched.

**Venue record:** the plan names F15 + purpleraider for
this proof; purpleraider is paused by Volmarr's order
and the F15 road runs through it, so both legs are
**deferred to R-17** with the owed R-09…R-14 Windows
proofs. The battery ran in full on the VM seat.
purplelongship + Mimir proofs remain deferred as
recorded for R-13/R-14.
