---
title: World Paywall — lock 2 of 3 worlds, unlock on purchase
type: architecture / monetization
related: [productification, IRIS_PROJECT_STATE_OF_THE_UNION, entitlement, grid-creator-tool-plan]
last_updated: 2026-06-07
sources:
  - Licensing/entitlement.py
  - Launcher/app_engine.py (Desktop-Mode gate)
  - UI/demo_overlay.py (show_locked_upsell)
  - Scripts/license_cli.py, Scripts/validation/sim_entitlement.py
---

# World Paywall

The simplest honest paywall for a local app: **one on/off "Pro" flag** per device
(`~/.iris/licensing.json`). Earth + grid_room are free; **Gem + The Watcher are locked
until Pro**. Buying Pro flips one flag and unlocks **both at once** (single-unlock model).

> **"Genuinely lock" reality:** worlds ship as JSON+textures inside the .app, so this is
> an *honest gate* (normal users pay), not uncrackable DRM. That's the correct, proportionate
> choice for an indie Mac app — do not build DRM.

## How it behaves (the UX)

- **Preview is always free.** Every world renders in the demo/showroom so a buyer sees
  what they're getting. The gate bites only when a non-Pro user tries to **set a locked
  world as their live wallpaper** (Enable Desktop Mode) → they get an upsell toast instead.
- **Fail-open:** if licensing ever fails to import, nothing is blocked — a paywall bug must
  never brick the engine.

## Dev Mode + the World Builder "Coming soon" gate (2026-06-07)

Two device flags in `~/.iris/licensing.json`:

- **`dev_mode`** — the **developer master switch**. ON = unlock every world **and** reveal
  the in-progress **World Builder** tab. OFF = the shipped experience.
- **`premium_subscription`** — the **customer paywall** (set by a real purchase). Unlocks
  the locked worlds but **not** World Builder.

World unlocked = free **or** premium **or** dev_mode. **World Builder tab is live only in
Dev Mode** (until `WORLD_BUILDER_RELEASED` flips True at launch) — otherwise its tab renders
**"Coming soon"** and its controls are inert (so a paying customer still sees "Coming soon").
Toggle with `/dev-mode` (`on`/`off`); flipping it updates a running app live.

## Code map (what's already built — Claude)

| Piece | Where |
|---|---|
| Free/locked sets, `is_world_unlocked()`, `set_premium()`, `activate(code)` | `Licensing/entitlement.py` |
| The store call (one HTTPS POST, stdlib-only) | `entitlement._verify_gumroad()` |
| Desktop-Mode gate (locked + not Pro → upsell, not wallpaper) | `Launcher/app_engine.py` |
| Upsell toast | `UI/demo_overlay.show_locked_upsell()` |
| Dev Mode + WB availability rule | `entitlement.is_dev_mode()` / `world_builder_available()` |
| WB tab "Coming soon" gate | `UI/demo_overlay._wb_available()` + the world_builder draw branch |
| Dev/test switch + status | `Scripts/license_cli.py` (`status`/`on`/`off`/`unlock`/`lock`/`activate`), skill `/dev-mode` |
| Headless guard (15 checks, sim #14) | `Scripts/validation/sim_entitlement.py` |

Test the whole flow today, no store needed:
`.venv/bin/python Scripts/license_cli.py lock|unlock|status`

## What YOU still have to do (real-world — no code can do these)

1. Create a **Gumroad** (or Lemon Squeezy) account → this is where money lands in your bank.
2. Add a **$7.99 product**, turn on **license keys**, connect **bank/PayPal** payout.
3. Paste **three values** into `Licensing/entitlement.py`:
   - `STORE_URL` — your checkout page (the in-app "Buy" button opens it)
   - `GUMROAD_PRODUCT_ID` — your product permalink/id (this makes `activate(code)` verify real codes)
   - (if Lemon Squeezy instead: swap the URL/fields in `_verify_gumroad` only)
4. Notarize (already in progress).

Until step 3, `activate()` returns False by design (no backdoor). After step 3, a customer
pastes their emailed code → one verify call → Pro flips on → both worlds unlock.

## Still UI polish (next step, best verified in a GUI `/verify`)

- A visible **"PRO" badge** on locked worlds in the Worlds tab.
- An in-app **"Buy / Enter code"** panel (today the unlock path is `activate()` + the CLI).
