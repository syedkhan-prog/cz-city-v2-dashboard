# New Cities Launch Tracker

Weekly dashboard for CZ + SK City V2 discount-setup migration cities.

## Architecture

```
syedkhan-prog/cz-city-v2-dashboard     ← source of truth (you edit here)
  ├── data.json                          ← Databricks refresh (local Monday job)
  ├── docs/index.html                    ← GitHub Pages (full dashboard + definitions)
  ├── boltable/index.html                ← team build (definitions hidden)
  └── .github/workflows/
        deploy-boltable.yml              ← mirror to boltable on every push
        refresh.yml                      ← manual CI fallback only

boltable/cz-city-v2-dashboard            ← read-only mirror (auto-synced)
        ↓
https://cz-city-v2-dashboard.boltable.eu   ← team URL (NetBird VPN)
```

**GitHub Pages (full version):** https://syedkhan-prog.github.io/cz-city-v2-dashboard/

## Weekly refresh (recommended — ~6 min)

Databricks pull runs **locally** (VPN + OAuth). Push to GitHub deploys Boltable automatically.

### One-time setup (Monday 11:00 Europe/Prague)

```bash
cd cz_city_v2_dashboard
bash scripts/install_monday_refresh.sh
```

Requires Mac **awake and on VPN** at 11:00 Monday. Logs: `~/Library/Logs/new-cities-launch-tracker-refresh.log`

### Manual refresh anytime

Double-click **`New Cities Launch Tracker Refresh.command`** in Downloads, or:

```bash
bash cz_city_v2_dashboard/scripts/refresh_and_push.sh
```

### n8n (optional)

Import `n8n/New_Cities_Launch_Tracker_Refresh.n8n.json` into n8n. Uses SSH to your Mac — only if the Mac is reachable. **launchd is simpler** for most setups.

## Local dev

```bash
cd cz_city_v2_dashboard
pip install -r requirements.txt
python fetch.py          # OAuth locally, or set DATABRICKS_TOKEN
python build.py          # also writes ../CZ_City_V2_Setup_Dashboard.html
LOCAL_DEV=1 python app.py   # http://localhost:8082 — serves docs/ (with definitions)
```

## GitHub secrets (optional — CI fallback only)

| Secret | Purpose |
|--------|---------|
| `DATABRICKS_TOKEN` | Manual Actions refresh fallback |
| `BOLTABLE_DEPLOY_KEY` | Auto-deploy to Boltable on push (already configured) |

Manual CI refresh: **Actions → Refresh CZ City V2 Dashboard → Run workflow** (slow from GitHub runners).
