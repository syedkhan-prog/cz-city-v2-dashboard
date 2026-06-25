# CZ City V2 Discount Setup — Impact Monitor

Weekly dashboard for the CZ City V2 discount-setup migration across 37 cities.

## Architecture

```
syedkhan-prog/cz-city-v2-dashboard     ← source of truth (you edit here)
  ├── data.json                          ← Databricks refresh (Actions)
  ├── docs/index.html                    ← GitHub Pages (full dashboard + definitions)
  ├── boltable/index.html                ← team build (definitions hidden)
  └── .github/workflows/
        refresh.yml                      ← Mon 12:00 Prague Databricks pull
        deploy-boltable.yml              ← mirror to boltable on every push

boltable/cz-city-v2-dashboard            ← read-only mirror (auto-synced)
        ↓
https://cz-city-v2-dashboard.boltable.eu   ← team URL (NetBird VPN)
```

**GitHub Pages (full version):** https://syedkhan-prog.github.io/cz-city-v2-dashboard/

## Local dev

```bash
cd cz_city_v2_dashboard
pip install -r requirements.txt
python fetch.py          # OAuth locally, or set DATABRICKS_TOKEN
python build.py          # also writes ../CZ_City_V2_Setup_Dashboard.html
python app.py            # http://localhost:8082 — serves docs/ (with definitions)
```

## Personal repo secrets (Settings → Secrets → Actions)

| Secret | Purpose |
|--------|---------|
| `DATABRICKS_TOKEN` | Weekly refresh workflow |
| `BOLTABLE_PUSH_TOKEN` | PAT with write access to `boltable/cz-city-v2-dashboard` |

Manual refresh: **Actions → Refresh CZ City V2 Dashboard → Run workflow**.

## Refresh schedule

Every **Monday at 12:00 Europe/Prague** (subtitle on the dashboard matches this).
