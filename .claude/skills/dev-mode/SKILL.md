---
name: dev-mode
description: Toggle between what YOU see (every world unlocked, World Builder live) and what a CUSTOMER sees (Gem + The Watcher locked, World Builder "Coming soon"). One command switches; no args = toggle. Use when the user wants to flip between their developer view and the customer view, check which view is active, or verify the paywall works as a real buyer would see it.
---

# Dev Mode — switch between your view and the customer's view

There are exactly two states this device can be in:

| State | Worlds | World Builder tab |
|---|---|---|
| **DEVELOPER VIEW** (your machine) | All unlocked | Live |
| **CUSTOMER VIEW** (new buyer) | Gem + Watcher locked | Coming soon |

**One command switches between them. No args = toggle.**

```
.venv/bin/python Scripts/license_cli.py          # toggle (no args)
.venv/bin/python Scripts/license_cli.py toggle   # same
.venv/bin/python Scripts/license_cli.py status   # which view am I in?
```

A running app picks up the switch **live** — no restart needed.

## Named views

```
.venv/bin/python Scripts/license_cli.py dev       # → DEVELOPER VIEW
.venv/bin/python Scripts/license_cli.py customer  # → CUSTOMER VIEW
```

`customer` resets both Dev Mode and any hand-granted premium to give you a
perfectly clean slate — exactly what a brand-new buyer experiences on first
install: Earth free, Gem + Watcher locked, World Builder "Coming soon."

## Verify it's working

Typical flow:
1. `customer` → switch to customer view
2. Run the app (`/run` or `/verify`)
3. Browse to Gem or The Watcher → see the **"PRO · Unlock"** amber badge
4. Try Enable Desktop Mode → see the upsell toast
5. Go to Settings → see "Unlock Pro · $7.99 USD" + "Redeem key" flow
6. `dev` → switch back to developer view → both worlds unlock live

## Activate a real purchase key (production)

```
.venv/bin/python Scripts/license_cli.py activate <license_key>
```

Calls the Lemon Squeezy License API. A successful activation sets premium
permanently on this device (via `~/.iris/licensing.json`). Only works with a
real purchased key — there is no backdoor.

## What the toggle actually flips

`~/.iris/licensing.json` — two flags, one file, no app restart needed:
- `dev_mode: true/false` — master switch (Dev Mode)
- `premium_subscription: true/false` — customer paywall (reset to false on `customer`)

The frozen camera/physics/render core is never touched.

## Related
- `Licensing/entitlement.py` — `LS_STORE_URL`, `LOCKED_WORLDS`, `activate()`
- `Scripts/validation/sim_entitlement.py` — the 24-check headless guard
- `/verify`, `/run` — see the two views in a real GUI session
