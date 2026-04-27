# DESIGN_V2_CONTRACT.md
> Single source of truth for PM DIGEST V2 visual design.
> All AI agents working on V2 UI must treat this as law.

---

## Prototype Location

```
docs/prototypes/pm_digest_v2_preview.html
```

Standalone HTML/CSS/JS. No backend dependencies. Safe to iterate freely.

---

## Production Flag

```
DASHBOARD_UI_VERSION=v2
```

V2 is NOT in production until this flag is set and `dashboard_v2.html` is production-ready.

---

## Layer Architecture (MANDATORY)

The desktop dashboard is a **full-screen layered scene**, not a card-in-card layout.

```
.v2-dashboard               ← invisible page frame (border-radius clip only)
├── LAYER 0: canvas          ← DNA spiral, full-screen background
├── LAYER 1: bg-fade         ← subtle top/bottom edge fades (opacity ≤ 0.25)
└── LAYER 2: v2-ui-layer     ← all UI floats above canvas
    ├── .top-nav             ← glass strip, z-index 5
    ├── .left-system-rail    ← absolute, left: 48px, top: 140px
    ├── .fc.fc-input         ← absolute, left: 120px, top: 330px
    ├── .fc.fc-status        ← absolute, right: 120px, top: 330px
    ├── .right-time          ← absolute, right: 64px, top: 150px
    ├── .pager-dots          ← absolute, right: 48px, top: 50%
    ├── .hero-caption        ← absolute, bottom: 245px, centered
    ├── .action-row          ← absolute, bottom: 116px, left/right: 72px
    └── .bottom-status-bar   ← absolute, bottom: 24px, left/right: 72px
```

**Forbidden patterns:**
- Canvas inside a bordered card or section
- Central rounded rectangle wrapping the DNA area
- Stacked mobile layout on desktop (≥1100px)
- Any solid-background wrapper covering the canvas

---

## Canvas Rules

- `position: absolute; inset: 0; width: 100%; height: 100%; z-index: 0`
- Helix center: `cx = W * 0.52`, `cy = H * 0.42`
- Helix visual height: `min(H * 0.92, 860px)`
- Helix radius (amplitude): `min(W * 0.22, 340px)`
- Full bleed: `yTop = cy - hH/2 - 40`, `ySpan = hH + 80` (extends past top/bottom edge)
- **First resize must be deferred via `requestAnimationFrame`** to avoid zero-dimension race condition
- `ResizeObserver` on `.v2-dashboard` for reliable live updates
- Pause when `document.hidden`; respect `prefers-reduced-motion`
- Mouse proximity: 160px radius, quadratic falloff, max 22px push, disabled on touch
- CTA click triggers 1.2s speed boost

**Particle visibility minimums:**
- Accent (lime) alpha: `Math.max(0.55, ...)`
- Muted (grey/white) alpha: `Math.max(0.50, ...)`
- Accent `shadowBlur`: min 12px (`12 + depA * 12 + gl * 24`)
- Ambient alpha: min 0.22
- Connecting rung alpha: min 0.12

---

## Theme System

Three themes, **identical DOM**, only CSS variables change.

### dark-lime (default)
```css
--bg:          #050607
--surface:     rgba(14, 18, 14, 0.42)   /* cards: translucent over spiral */
--surface-nav: rgba(12, 14, 12, 0.62)   /* nav/status: denser */
--text:        #f2f4ef
--muted:       #8b9287
--primary:     #a3e635
--primary2:    #84cc16
--glow:        rgba(163, 230, 53, 0.55)
--border:      rgba(255, 255, 255, 0.10)
--border2:     rgba(255, 255, 255, 0.22)
--c-muted:     rgba(228, 232, 226, 0.58)  /* canvas grey particles */
--c-rung:      rgba(255, 255, 255, 0.10)  /* helix rungs */
--c-glow:      rgba(163, 230, 53, 0.92)   /* canvas glow color */
```

### light-lime
```css
--bg:          #f4f7ee
--surface:     rgba(255, 255, 255, 0.50)
--surface-nav: rgba(255, 255, 255, 0.78)
--text:        #101812
--primary:     #84cc16
--primary2:    #65a30d
--c-muted:     rgba(72, 88, 72, 0.48)
```

### wave-blue
```css
--bg:          #f1f6ff
--surface:     rgba(255, 255, 255, 0.54)
--surface-nav: rgba(255, 255, 255, 0.80)
--text:        #182a44
--primary:     #2f7dff
--primary2:    #0f62fe
--c-muted:     rgba(72, 100, 156, 0.48)
```

**Theme switcher:** D / L / W buttons in nav-right. Persisted in `localStorage`.

---

## Identical Layout Rule

Dark and light themes must produce **exactly the same layout**.  
No DOM differences between themes. No conditional classes for themes.  
Only CSS variables may change appearance.

---

## Desktop Cockpit Rule (≥1100px)

- Full-screen: `min-height: 100vh; min-height: 100dvh`
- `.v2-dashboard` has **no border, no drop-shadow, no background** — it is only a `border-radius: 28px` clip frame
- `body { background: var(--bg) }` — the body color IS the stage background
- Nav floats as a glass strip with `margin: 14px`
- All metric cards, text elements, and buttons are absolutely positioned
- Three action buttons in one row (`1.15fr 1fr 1fr`), height 108px
- Bottom status strip is 72px, glass

**Desktop breakpoints:**
| Viewport | Behaviour |
|---|---|
| ≥1321px | Full layout (all elements visible) |
| 1100–1320px | Cards tighten (left:72, right:72), right-time hidden |
| 921–1099px | Nav links hidden, some decorations hidden |
| 741–920px | Left rail hidden, cards at 50% width, actions 2-col |

---

## Mobile / TWA Rule (≤740px)

- Stacked column layout is allowed on mobile
- Canvas confined to a 320px-tall top band below the nav
- All absolute-positioned desktop elements become `position: static`
- Primary CTA becomes `position: sticky; bottom: 6px`
- `env(safe-area-inset-bottom)` padding for TWA/iOS
- No horizontal overflow at any breakpoint

---

## Content Rules

| Element | Text |
|---|---|
| Brand | PM DIGEST |
| Subtitle | DELIVERY REPORTS |
| Hero caption | Turn messy updates into **structured delivery reports**. |
| Left rail | System Online / All systems operational / 98.6% Uptime 30d |
| Input card | INPUT DATA / 124 notes today / ↑ 18% |
| Status card | STRUCTURED STATUS / 91% accuracy / ↑ 7% |
| Status bar | Local-first processing / Data Sources — 12 connected / Auto Processing — Scheduled 17:30 / Last Sync — 2 min ago |
| Primary CTA | Собрать отчёт / Анализировать и структурировать |
| Secondary 1 | Загрузить данные / Импорт из файла или сервиса |
| Secondary 2 | История отчётов / Просмотр и экспорт |

---

## Forbidden Words (in all UI, copy, code comments, and docs)

```
Aidentika
Patient
Medical
Surgical
Biometrics
Neuro
Healthcare
Clinical
EHR
EMR
```

---

## Separation of Concerns

| Surface | Template | CSS | Status |
|---|---|---|---|
| V1 Dashboard | `index.html` | `app.css` | Production — do not modify |
| V2 Dashboard | `dashboard_v2.html` | inline in template | Placeholder |
| V2 Prototype | `pm_digest_v2_preview.html` | inline | Active dev |
| Admin | `admin.html` | `app.css` or inline | Do not merge with dashboard |
| Landing | `landing.html` | separate | Separate design system |
