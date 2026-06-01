---
title: Productification Roadmap
type: strategy
related: [design-decisions, version-history, distribution-checklist, world-system, worlds-index, dmg-build-process, current-focus, constraints, known_issues, system-interactions]
last_updated: 2026-05-31
sources: [Docs/IRIS_OVERVIEW.txt, Docs/FIRST_LAUNCH_AND_DMG_DESIGN.md, obsidian-docs/releases/version-history.md, obsidian-docs/architecture/design-decisions.md, obsidian-docs/architecture/constraints.md, obsidian-docs/releases/distribution-checklist.md]
---

# Productification Roadmap

> **Purpose.** A structured analysis of what would be required to transform IRIS from a personal project into a commercial product. Written as a realistic progression from current state — not a hypothetical moonshot. Optimized for future LLM handoff.

---

## 1. Current State

### 1.1 What Exists (v1.5, 2026-05-31)

**Engine (frozen — do not touch):**
- Kooima off-axis "window" projection — geometrically correct parallax
- Three-component head-to-camera blend (translation, distance scaling, rotation)
- MediaPipe face tracking ~30 fps, ~34 ms mean latency, VIDEO mode
- Bloom post-process pipeline
- Retina-native GL at 60 fps on M1/M2

**Product surface:**
- Two worlds: [[earth]] (flagship), [[the-watcher]] (giant eye, horror)
- Liquid-glass demo HUD — three states: floating preview → live tracked → desktop mode
- Click-through wallpaper daemon
- `parallaxctl` CLI
- Self-contained arm64 DMG (~128 MB); working camera permission flow (TCC, ad-hoc signed)
- JSON-driven, live-switchable [[world-system]]
- Scripted idle motion in floating preview (no camera required — demo sells itself)

**Infrastructure:**
- `build_dmg.sh` → PyInstaller → sign → DMG
- Six headless validation sims protecting frozen physics ([[headless-simulation]])
- Obsidian wiki (this vault — the only persistent project record; **no git**)

### 1.2 What Is Missing

**Distribution:**

| Gap | Severity |
|---|---|
| No Developer ID signing | Critical |
| No notarization | Critical (Gatekeeper blocks on other Macs) |
| arm64-only binary | High (excludes Intel Mac users) |
| No distribution channel (website, App Store, GitHub Releases) | High |

**Core product:**

| Gap | Severity |
|---|---|
| Third world (Gem renderer exists; no `world.json`) | High |
| No LaunchAgent (launch at login) | Medium |
| No crash reporting | Medium |
| No anonymous telemetry | Medium |
| No privacy policy | Medium (required for App Store) |
| Settings panel (only flag files today) | Low |

**Platform / infrastructure:**

| Gap | Severity |
|---|---|
| No version control / git | **Catastrophic risk** — wiki is the only record |
| No analytics or usage insight | High |
| No marketing assets (screenshots, demo video, press kit) | Medium |

### 1.3 Assumptions Already Made

| Assumption | Source |
|---|---|
| Price: $4.99 one-time or $1.99/month | `IRIS_OVERVIEW.txt` |
| Target: creative professionals, productivity enthusiasts | `IRIS_OVERVIEW.txt` |
| World system scales to 100+ worlds without recompiling | [[design-decisions]] |
| Worlds are content (JSON), not code | [[design-decisions]] |
| Physics is frozen; all future iteration in UI / worlds / packaging | [[design-decisions]] |
| macOS-first; cross-platform later | `IRIS_OVERVIEW.txt` |
| Privacy: all processing is local; no video stored or transmitted | `FIRST_LAUNCH_AND_DMG_DESIGN.md` |

### 1.4 Technical Readiness

| Area | Status |
|---|---|
| Core engine | ✅ Frozen, validated by 6 headless sims |
| Rendering + Retina | ✅ Correct (pixelation bug resolved 2026-05-31) |
| Camera permission (TCC) | ✅ Fixed, live-verified 2026-05-31 — see [[known_issues]] |
| World system | ✅ Live-switchable JSON worlds |
| Demo UX / onboarding | ✅ Three-state machine, liquid-glass HUD |
| Build pipeline | ✅ `build_dmg.sh` → ~128 MB DMG |
| Code signing | ⚠️ Ad-hoc only; Gatekeeper warns on other Macs |
| Notarization | ❌ Not configured |
| Telemetry | ❌ None |
| Crash reporting | ❌ None (`~/.iris/iris.log` is minimal) |
| Version control | ❌ None — wiki is the only persistent record |
| Settings UI | ⚠️ Works via flag files; no user-facing panel |

### 1.5 Product Readiness

| Area | Status |
|---|---|
| First-run onboarding | ✅ Camera permission primer → live tracking |
| Desktop mode | ✅ Click-through wallpaper daemon |
| World selector | ✅ "Browse Worlds" picker in HUD |
| Multiple worlds | ⚠️ Two ship; `Gem` renderer exists but no `world.json` |
| Public install (Gatekeeper-clean) | ❌ Right-click → Open workaround required |
| Privacy policy | ❌ None |
| App Store assets | ❌ No screenshots, description, or preview video |
| Landing page / website | ❌ None |
| Feedback loop | ❌ None |

---

## 2. Productification Path

Smallest logical progression from current state. Each step is a dependency for the next.

```
Personal Project (v1.5, arm64 DMG, ad-hoc signed)
   │
   ▼  Developer ID signing + notarization
Distributable Product  (any Mac can install cleanly)
   │
   ▼  Third world (Gem) + landing page + GitHub Releases
Usable MVP  (shareable; feels like a product, not a tech demo)
   │
   ▼  Telemetry + crash reporting + invite 10–100 beta users
Private Beta  (structured feedback; hardware diversity)
   │
   ▼  Privacy policy + App Store submission + marketing assets
Public Launch  (App Store or direct-download, discoverable)
   │
   ▼  Freemium gating + payment mechanism (IAP or Gumroad)
Revenue-Generating Product
   │
   ▼  World creator tools + community pipeline + Windows/web
Scalable Platform
```

---

## 3. Milestones

### Milestone 1: Distribution-Ready Foundation

**Objective.** Any Mac user can install and run IRIS without Gatekeeper friction.

**Success criteria:**
- `codesign --verify` passes with a real Developer ID certificate
- `xcrun notarytool` → notarized — drag-to-Applications, no right-click workaround
- arm64 OR universal binary with clear architecture labeling

**Dependencies:**
- Apple Developer Program account ($99/yr)
- Dedicated signing identity (Keychain entry)
- `build_dmg.sh` updated: Developer ID `codesign` → `xcrun notarytool` → `xcrun stapler`

**Risks:**
- Apple Developer enrollment takes ~24h to activate
- Universal binary may surface new compatibility issues on Intel hardware
- TCC grants may re-prompt after each notarized rebuild until a stable provisioning profile is used

**Must complete before:** any distribution to real users.

---

### Milestone 2: Usable MVP

**Objective.** A three-world experience with a real download channel, enough to share publicly and gather meaningful feedback.

**Success criteria:**
- Three worlds ship: [[earth]] + [[the-watcher]] + Gem (renderer already supports Gem; needs `world.json` + textures)
- LaunchAgent integrated in Settings → "Launch at login"
- GitHub Releases page with versioned DMG links
- A one-page landing page: 15-second demo GIF / video, download button, privacy statement
- Anonymous telemetry: launch count, world selected, session length (no PII)

**Dependencies:**
- Milestone 1 (signed + notarized)
- `Worlds/gem/world.json` (low effort — `renderer.Gem` + `shaders/gem.*` already exist; see [[worlds-index]])
- A domain name and static hosting (GitHub Pages is sufficient)

**Risks:**
- Gem shader needs one live GL compile run to confirm (same caveat as eye shader; see [[constraints]])
- Telemetry must be opt-out or fully anonymous to avoid App Store privacy flags
- Landing page GIF/video capture requires a live run in the GUI session

**Order:** Gem world first (lowest effort). Landing page can come in parallel with signing work.

---

### Milestone 3: Private Beta

**Objective.** 10–100 real users on diverse hardware; structured feedback; production-quality stability.

**Success criteria:**
- 10+ testers across M1, M2, Intel Macs, different webcams, different macOS versions
- Crash reporting in place (anonymous, opt-in — e.g. Sentry or Bugsnag, PyInstaller-compatible)
- Telemetry shows sessions > 5 min on ≥ 70% of installs
- All six `sim_*.py` still pass; no regressions
- **Git initialized and source pushed to a private remote** (catastrophic risk mitigation)

**Dependencies:**
- Milestone 2 + GitHub Releases as distribution
- A community channel (Discord or mailing list for invites + feedback)
- Crash reporting library vetted for PyInstaller freeze compatibility

**Risks:**
- Intel Mac users will surface GPU and webcam bugs not seen on Apple Silicon
- Real users break assumptions about webcam quality, viewing distance, and office lighting
- PyInstaller + crash reporting integration can be fragile (hidden-import requirements similar to pyobjc)

**Order:** Initialize git **before** inviting any testers. A source loss during beta with open bug reports would be unrecoverable.

---

### Milestone 4: Public Launch

**Objective.** Mac App Store listing OR direct-download public release with a stable acquisition channel.

**Success criteria:**
- App Store: submitted, approved, listed — OR — direct download with notarized DMG publicly available
- Privacy policy published (camera use, local processing, no data stored/transmitted)
- App Store metadata complete: screenshots (5+), description, keywords, 30-second preview video
- 100+ downloads in the first two weeks (soft baseline; not a hard gate)

**Dependencies:**
- Milestone 3 validation (no known crashes, stable across hardware)
- Privacy policy (also required for any camera app distributed publicly)
- App Store Connect account + app record configured

**Risks:**
- App Store review rejection: Apple scrutinizes camera apps. Privacy copy must be precise and the use-case (head tracking for parallax) must be unambiguous. A well-written rejection appeal + direct-download fallback mitigates this.
- Discovery on macOS App Store is low without external marketing. ProductHunt, Reddit, Twitter, and niche communities (Motion, VFX, productivity) are likely to outperform organic App Store discovery at launch.
- Intel Mac compatibility gap may still surface at public scale even after beta

**Order:** Privacy policy before any public listing. App Store and direct-download are parallel paths; both require Milestone 1.

---

### Milestone 5: Monetization

**Objective.** Sustainable revenue with minimal friction.

**Recommended model: Freemium + one-time Pro unlock.**

| Tier | Content | Price |
|---|---|---|
| Free | [[earth]] world, full desktop mode, all parallax features | $0 |
| Iris Pro | All worlds (current + all future releases) | $7.99 one-time |

**Rationale:**
- One-time purchase aligns with the ambient/wallpaper use case (no subscription fatigue for a background app)
- Free tier delivers the full core illusion — users experience value before paying
- "All future worlds" is the natural upgrade motivator as the catalog grows
- $7.99 is within impulse-buy range; competitive with similar Mac utilities

**Subscription model ($1.99/month):** only viable if new worlds ship monthly. That commitment requires creator tooling or dedicated author bandwidth. Not recommended at solo-creator scale.

**World marketplace (individual world purchases):** adds per-purchase friction. Not recommended — the Pro tier should unlock the full catalog.

**Implementation options:**
- App Store in-app purchase (cleanest UX; Apple takes 30%)
- Gumroad / Paddle license key (avoids commission; more developer control; adds install friction)
- Hybrid: App Store as primary; direct as secondary

**Dependencies:**
- Milestone 4 (public listing)
- World-gating logic in the engine (license check → unlock world) — must be additive, not a physics change
- Payment infrastructure integration

**Risks:**
- License/entitlement system adds complexity near the frozen engine (keep it in `world_runtime.py` or the overlay — never in camera math)
- App Store IAP review adds latency to new purchasable world releases

---

### Milestone 6: Platform Expansion

**Objective.** A creator ecosystem and multi-platform reach.

**Success criteria:**
- World creator tool: a GUI or validated schema editor producing compliant `world.json` files without touching engine code
- Community submission pipeline: GitHub PR template or hosted upload portal
- 10+ community-contributed worlds available
- Windows support OR browser-based version (WebGL + WebRTC webcam)

**Dependencies:**
- Milestone 5 (stable revenue funds platform investment)
- A published, versioned `world.json` schema with a renderer capability matrix (what JSON fields produce what visual effects)
- An engaged community channel with active contributors

**Risks:**
- Windows: requires a full renderer rewrite (DirectX 11 / Vulkan vs. OpenGL 2.1 + macOS APIs). High engineering cost.
- Browser-based (WebGL + WebRTC): more portable but loses the always-on desktop daemon model — a different product category.
- Creator tool quality bar: community worlds will vary; a review process adds maintenance overhead.

**Order:** World creator documentation first (derived from existing [[world-system]] and [[worlds-index]] schema). Community submission before Windows; Windows before major cross-platform monetization.

---

## 4. Business Model Analysis

### Revenue Stream Evaluation

| Stream | Viability | Risk | Notes |
|---|---|---|---|
| One-time purchase (Iris Pro) | ✅ High | Low | Best fit for ambient wallpaper; no subscription fatigue |
| Freemium (free Earth; paid worlds) | ✅ High | Low | Delivers full core value free; lowers trial friction |
| Subscription ($1.99/mo) | ⚠️ Medium | Medium | Only justified with monthly world releases |
| World marketplace (per-world purchase) | ⚠️ Low | Medium | Per-purchase friction; Pro tier is cleaner |
| Team / Enterprise plan | ❌ Low | Medium | Single-monitor, single-user product; team use unclear |
| AI-generated world content | ⚠️ Medium | High | Could accelerate world catalog; needs LLM→texture pipeline |
| Demo/kiosk licensing (corporate) | ⚠️ Low | Low | Floating preview (scripted idle, no camera) is a strong conference demo |

### Prioritized Recommendation

1. **Freemium + one-time Pro ($7.99)** — deliver at Milestone 5.
2. **Subscription only after** a regular world release cadence is proven.
3. **World marketplace** only after a creator community produces sufficient volume.

### World-as-Moat

The [[world-system]] is the natural product moat. Each world is:
- Differentiated in mood and audience (cinematic Earth vs. horror Watcher vs. crystalline Gem)
- Low marginal cost to create (JSON + textures, no engine code)
- A reason to return and upgrade

Worlds should not be individual purchases. A Pro tier unlocking all of them creates a bundle effect that increases perceived value.

### Privacy as Differentiator

IRIS's local-processing model (no video stored, no cloud, no PII) is a genuine differentiator against future cloud-based spatial computing products. This should be front-and-center in marketing, not buried in a privacy policy footer.

---

## 5. Success Factors

### What Must Be True for IRIS to Succeed

1. **First impression is magical.** The floating preview (scripted idle) already delivers this before any camera grant. This is the most important UX asset — protect it.
2. **Installation is frictionless.** Any Gatekeeper friction → abandonment. Notarization is non-negotiable before real distribution.
3. **Camera works on first try.** One failed camera grant on a new user → uninstall. The 2026-05-31 TCC fix resolved this in principle; Intel and older macOS must be verified in beta.
4. **Content grows.** A single-world product is a demo. Three to five worlds make it a product. Ten make it a platform.
5. **Privacy is trusted.** A product that puts a camera on your face requires explicit, credible, simple privacy communication.

### Biggest Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Source loss (no git) | Medium | Catastrophic | `git init` + private GitHub remote — do this now |
| App Store rejection (camera use) | Medium | High | Clear privacy copy; direct-download as fallback channel |
| Intel Mac camera/GPU bugs | High | Medium | Label arm64-only clearly; validate Intel in M3 beta |
| User can't grant camera (IT policy, no webcam) | Medium | Medium | Floating preview works without camera; honest UI already in place |
| Physics regression after a content change | Low | High | Six headless sims enforce invariants — never modify frozen modules |
| Creator community doesn't materialize | Medium | Medium | Build creator tools only after paid user base justifies it |
| Single developer bus factor | High | High | Thorough documentation (this wiki) is the primary mitigation |

### Biggest Opportunities

1. **Virality via screen recording.** Head-tracked parallax demos itself in any screen recording or GIF. A one-click "record 10-second demo" export is a free acquisition channel.
2. **Gem world.** `renderer.Gem` already exists. One `world.json` + textures → three-world product. The single highest-leverage content action.
3. **Corporate / conference demo.** The floating preview (scripted idle, no camera needed) is a compelling ambient display for trade shows, investor presentations, and open offices. A "kiosk mode" (no UI chrome, locked to scripted idle) could target this with minimal work.
4. **Creator ecosystem.** The world system (JSON, no engine code) is already designed for external creators. A published schema + community channel = a content flywheel that grows the catalog without author time.
5. **Privacy narrative.** As spatial computing (Vision Pro, etc.) normalizes always-on cameras, a local-processing, no-cloud, no-PII alternative has a genuine positioning advantage.

### Most Likely Failure Points

1. Gatekeeper friction causes abandonment before users experience the core product → fix with Milestone 1.
2. Camera fails on Intel or older macOS → users assume the app is broken → fix in M3 beta.
3. One-world (Earth-only) experience doesn't feel complete enough for a $7.99 purchase → fix with Gem world before monetization.
4. Source is lost before shipping (no git, no backup) → existential risk; fix immediately.

### Highest-Leverage Improvements (ordered)

| # | Action | Why |
|---|---|---|
| 1 | `git init` + push to private GitHub | Catastrophic risk mitigation; 5 minutes |
| 2 | Developer ID signing + notarization | Enables all real distribution |
| 3 | `Worlds/gem/world.json` | Third world for near-zero effort; product feels complete |
| 4 | Landing page + GitHub Releases | Real acquisition channel |
| 5 | Anonymous telemetry | Without data, every subsequent decision is a guess |
| 6 | LaunchAgent ("launch at login") | Final step from app to ambient OS feature |
| 7 | Privacy policy | Required for App Store; builds user trust |
| 8 | Crash reporting | Blind without it in the field |
| 9 | 15-second demo video | Most effective acquisition asset for a visual product |
| 10 | Freemium world-gating | Revenue begins here |

---

## 6. Immediate Next Actions

Ordered strictly by dependency and leverage:

| # | Action | Effort | Unblocks |
|---|---|---|---|
| 1 | `git init` + push to private remote | 5 min | Risk mitigation for everything |
| 2 | Apple Developer Program ($99) | 1 day (approval) | M1: signing + notarization |
| 3 | Integrate Developer ID `codesign` into `build_dmg.sh` | 2 h | Gatekeeper-clean distribution |
| 4 | Add `notarytool` + `stapler` steps to `build_dmg.sh` | 2 h | App Store; clean install on other Macs |
| 5 | Create `Worlds/gem/world.json` + gen/validate Gem textures | 2–4 h | Third world; M2 product feel |
| 6 | Write privacy policy (camera use, local processing) | 1 h | App Store; user trust |
| 7 | GitHub Releases page + versioned DMG links | 1 h | Real download channel |
| 8 | One-page landing page (GitHub Pages) | 4 h | Shareable acquisition link |
| 9 | Anonymous telemetry (on-device event log, opt-out) | 1 day | Feedback loop for all future decisions |
| 10 | LaunchAgent: wire "Launch at login" into Settings | 2 h | Always-on ambient experience |

---

## Related

[[design-decisions]] · [[version-history]] · [[distribution-checklist]] · [[world-system]] · [[worlds-index]] · [[dmg-build-process]] · [[current-focus]] · [[constraints]] · [[known_issues]] · [[system-interactions]]
