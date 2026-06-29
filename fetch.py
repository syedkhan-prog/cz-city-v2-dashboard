"""Pull City V2 discount-setup monitoring data from Databricks (CZ + SK).

Sources (all real, verified):
  - ng_delivery_spark.dim_order_delivery        order-level orders/GMV/discount/campaign spend/Bolt+
  - ng_delivery_spark.dim_user_delivery         signup -> food activation -> Bolt+ subscription
  - ng_delivery_spark.dim_provider_v2           provider master (city, segment, AM)
  - ng_public_spark.etl_delivery_campaign_order_metrics  campaign spend by objective / provider

Metrics are computed at city x ISO-week (Monday-anchored). The dashboard front-end
derives WoW / trailing-4-week baseline / RYG from these weekly rows.
"""
from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta
from pathlib import Path

from db import DBX

COUNTRIES = {
    "cz": {"code": "cz", "label": "CZ", "name": "Czech Republic"},
    "sk": {"code": "sk", "label": "SK", "name": "Slovakia"},
}

# ---- City roster + V2 lifecycle stage (city_name verified against dim_order_delivery) -
CZ_ROSTER = {
    "Uherske Hradiste": "Ready to BAU",
    "Most": "Good CVP & Good Pen",
    "Zlin": "Good CVP & Good Pen",
    "Teplice": "Good CVP & Good Pen",
    "Pisek": "Good CVP & Good Pen",
    "Chomutov": "Good CVP & Good Pen",
    "Frydek-Mistek": "Good CVP & Good Pen",
    "Havirov": "Good CVP & Good Pen",
    "Karlovy Vary": "Good CVP & Good Pen",
    "Prerov": "Good CVP & Good Pen",
    "Prostejov": "Good CVP & Good Pen",
    "Ceska Lipa": "Good CVP & Good Pen",
    "Znojmo": "Good CVP & Good Pen",
    "Decin": "Good CVP & Good Pen",
    "Klatovy": "Good CVP & Good Pen",
    "Mlada Boleslav": "Good CVP Low Pen",
    "Opava": "Good CVP Low Pen",
    "Kolín": "Good CVP Low Pen",
    "Pardubice": "Good CVP Low Pen",
    "Kladno": "Good CVP Low Pen",
    "Jihlava + Vysocina": "Poor CVP - Selection",
    "Pribram": "Poor CVP - Selection",
    "Karvina": "Poor CVP - Selection",
    "Usti nad Labem": "Poor CVP - Selection + Service",
    "Trebic": "Poor CVP - Service",
    "Liberec": "Re-launch",
    "Litvinov": "Launch",
    "Jablonec nad Nisou": "Launch",
    "Trutnov": "Closed",
    "Ricany": "Closed",
    "Cheb": "Closed",
    "Tabor": "Closed",
    "Brandys nad Labem": "Closed",
    "Beroun": "Closed",
    "Kralupy nad Vltavou": "Closed",
    "Litomerice": "Closed",
    "Strakonice": "Closed",
}

# Slovakia — city names match dim_order_delivery (verified 2026-06-27)
SK_ROSTER = {
    "Spišská Nová Ves": "Good CVP & Good Pen",
    "Humenne": "Good CVP & Good Pen",
    "Povazska Bystrica": "Good CVP & Good Pen",
    "Michalovce": "Poor CVP - Selection",
    "Liptovsky Mikulas": "Good CVP & Good Pen",
    "Piestany": "Good CVP & Good Pen",
    "Trencin": "Good CVP & Good Pen",
    "Topolcany": "Good CVP Low Pen",
    "Dunajska Streda": "Good CVP Low Pen",
    "Komarno": "Dormant",
    "Hlohovec": "Good CVP & Good Pen",
    "Senica": "Good CVP & Good Pen",
    "Bardejov": "Good CVP & Good Pen",
    "Cadca": "Launch",
    "Ruzomberok": "Good CVP & Good Pen",
    "Levice": "Launch",
    "Dubnica nad Vahom": "Launch",
    "Rimavska Sobota": "Launch",
    "Senec": "Launch",
}

ROSTER = {
    **{k: {"country": "cz", "stage": v} for k, v in CZ_ROSTER.items()},
    **{k: {"country": "sk", "stage": v} for k, v in SK_ROSTER.items()},
}

N_WEEKS = 13  # complete ISO weeks of history to pull


def _esc(s: str) -> str:
    return s.replace("'", "''")


def _roster_union_sql() -> str:
    parts = []
    for city, meta in ROSTER.items():
        cname = COUNTRIES[meta["country"]]["name"]
        parts.append(
            f"SELECT '{_esc(cname)}' AS country_name, '{_esc(city)}' AS city_name, "
            f"'{meta['country']}' AS country_code"
        )
    return "\n          UNION ALL ".join(parts)


def _city_map_cte() -> str:
    return f"""
        roster AS (
          {_roster_union_sql()}
        ),
        city_map AS (
          SELECT DISTINCT o.country_name, o.city_id, o.city_name, r.country_code
          FROM ng_delivery_spark.dim_order_delivery o
          INNER JOIN roster r
            ON o.country_name = r.country_name AND o.city_name = r.city_name
        )"""


def _records(df):
    rows = []
    for _, r in df.iterrows():
        row = {}
        for k, v in r.items():
            if v != v:  # NaN
                row[k] = None
            elif isinstance(v, bool):
                row[k] = v
            elif hasattr(v, "isoformat"):
                row[k] = str(v)[:10]
            elif hasattr(v, "__float__") and not isinstance(v, (str, bool, int)):
                row[k] = float(v)
            else:
                row[k] = v
        rows.append(row)
    return rows


def _run_query(name: str, sql: str):
    t0 = time.time()
    with DBX() as dbx:
        df = dbx.query(sql)
    print(f"  {name}: {time.time() - t0:.0f}s ({len(df)} rows)", flush=True)
    return name, df


def pull() -> dict:
    city_cte = _city_map_cte()
    queries = {
        "city_weekly": f"""
        WITH {city_cte},
        base AS (
          SELECT
            o.city_name,
            cm.country_code,
            CAST(date_trunc('WEEK', o.order_created_date) AS DATE) AS week_start,
            o.order_id, o.user_id, o.order_state,
            o.order_gmv_eur,
            COALESCE(o.campaign_discount_eur, 0)       AS di_discount,
            COALESCE(o.campaign_spend_bolt_eur, 0)     AS di_bolt,
            COALESCE(o.campaign_spend_provider_eur, 0) AS di_provider,
            CASE WHEN o.is_bolt_plus_order THEN o.order_gmv_eur ELSE 0 END AS bp_gmv,
            o.is_bolt_plus_order, o.is_first_food_order,
            o.has_food_order_in_next_30days_same_city  AS repeat30
          FROM ng_delivery_spark.dim_order_delivery o
          INNER JOIN city_map cm
            ON o.city_name = cm.city_name AND o.country_name = cm.country_name
          WHERE o.delivery_vertical = 'food'
            AND o.order_created_date >= date_sub(date_trunc('WEEK', current_date()), 7*{N_WEEKS})
            AND o.order_created_date <= current_date()
        )
        SELECT city_name, country_code, week_start,
          COUNT(DISTINCT CASE WHEN order_state='delivered' THEN order_id END) AS orders,
          COUNT(DISTINCT CASE WHEN order_state='delivered' THEN user_id END)  AS active_users,
          ROUND(SUM(CASE WHEN order_state='delivered' THEN order_gmv_eur ELSE 0 END), 2) AS gmv_eur,
          ROUND(SUM(CASE WHEN order_state='delivered' THEN di_discount ELSE 0 END), 2)   AS di_discount_eur,
          ROUND(SUM(CASE WHEN order_state='delivered' THEN di_bolt ELSE 0 END), 2)       AS di_bolt_eur,
          ROUND(SUM(CASE WHEN order_state='delivered' THEN di_provider ELSE 0 END), 2)   AS di_provider_eur,
          COUNT(DISTINCT CASE WHEN order_state='delivered' AND is_bolt_plus_order THEN order_id END) AS bolt_plus_orders,
          COUNT(DISTINCT CASE WHEN order_state='delivered' AND is_bolt_plus_order THEN user_id END)  AS bolt_plus_users,
          ROUND(SUM(CASE WHEN order_state='delivered' THEN bp_gmv ELSE 0 END), 2) AS bolt_plus_gmv_eur,
          COUNT(DISTINCT CASE WHEN order_state='delivered' AND is_first_food_order THEN user_id END) AS new_activated_users,
          COUNT(DISTINCT CASE WHEN order_state='delivered' AND repeat30 THEN user_id END) AS users_repeat_30d
        FROM base
        GROUP BY 1, 2, 3
        ORDER BY 1, 2, 3
        """,
        "activation_weekly": f"""
        WITH {city_cte},
        u AS (
          SELECT cm.city_name, cm.country_code,
            CAST(date_trunc('WEEK', d.user_sign_up_authorised_ts) AS DATE) AS signup_week,
            d.user_sign_up_authorised_ts AS su_ts,
            d.food_activation_ts AS act_ts
          FROM ng_delivery_spark.dim_user_delivery d
          INNER JOIN city_map cm ON d.city_id = cm.city_id
          WHERE d.user_sign_up_authorised_ts IS NOT NULL
            AND COALESCE(d.user_is_bot,false)=false
            AND COALESCE(d.is_user_test,false)=false
            AND COALESCE(d.user_is_employee,false)=false
            AND COALESCE(d.is_user_blocked,false)=false
            AND date_trunc('WEEK', d.user_sign_up_authorised_ts) >= date_sub(date_trunc('WEEK', current_date()), 7*{N_WEEKS})
            AND date_trunc('WEEK', d.user_sign_up_authorised_ts) <= current_date()
        )
        SELECT city_name, country_code, signup_week,
          COUNT(*) AS signup_users,
          COUNT(act_ts) AS activated_users,
          COUNT(CASE WHEN act_ts IS NOT NULL AND datediff(to_date(act_ts), to_date(su_ts))=0  THEN 1 END) AS activated_d0,
          COUNT(CASE WHEN act_ts IS NOT NULL AND datediff(to_date(act_ts), to_date(su_ts))<=7 THEN 1 END) AS activated_d7,
          COUNT(CASE WHEN act_ts IS NOT NULL AND datediff(to_date(act_ts), to_date(su_ts))<=14 THEN 1 END) AS activated_d14
        FROM u
        GROUP BY 1, 2, 3
        ORDER BY 1, 2, 3
        """,
        "cohort_depth": f"""
        WITH {city_cte},
        su AS (
          SELECT d.user_id, cm.city_name, cm.country_code,
            to_date(d.user_sign_up_authorised_ts) AS sd,
            CAST(date_trunc('WEEK', d.user_sign_up_authorised_ts) AS DATE) AS signup_week
          FROM ng_delivery_spark.dim_user_delivery d
          INNER JOIN city_map cm ON d.city_id = cm.city_id
          WHERE d.user_sign_up_authorised_ts IS NOT NULL
            AND COALESCE(d.user_is_bot,false)=false
            AND COALESCE(d.is_user_test,false)=false
            AND COALESCE(d.user_is_employee,false)=false
            AND COALESCE(d.is_user_blocked,false)=false
            AND date_trunc('WEEK', d.user_sign_up_authorised_ts) >= date_sub(date_trunc('WEEK', current_date()), 7*{N_WEEKS})
            AND date_trunc('WEEK', d.user_sign_up_authorised_ts) <= current_date()
        ),
        ord AS (
          SELECT o.user_id, o.order_created_date
          FROM ng_delivery_spark.dim_order_delivery o
          INNER JOIN city_map cm
            ON o.city_name = cm.city_name AND o.country_name = cm.country_name
          WHERE o.delivery_vertical='food' AND o.order_state='delivered'
            AND o.order_created_date >= date_sub(date_trunc('WEEK', current_date()), 7*{N_WEEKS})
        ),
        ucnt AS (
          SELECT s.city_name, s.country_code, s.signup_week, s.user_id,
            SUM(CASE WHEN o.order_created_date BETWEEN s.sd AND date_add(s.sd,6)  THEN 1 ELSE 0 END) AS d7,
            SUM(CASE WHEN o.order_created_date BETWEEN s.sd AND date_add(s.sd,13) THEN 1 ELSE 0 END) AS d14,
            SUM(CASE WHEN o.order_created_date BETWEEN s.sd AND date_add(s.sd,27) THEN 1 ELSE 0 END) AS d28
          FROM su s
          LEFT JOIN ord o ON o.user_id = s.user_id AND o.order_created_date BETWEEN s.sd AND date_add(s.sd,27)
          GROUP BY 1, 2, 3, 4
        )
        SELECT city_name, country_code, signup_week, COUNT(*) AS signups,
          SUM(CASE WHEN d28>=1 THEN 1 ELSE 0 END)  AS d28_ge1,
          SUM(CASE WHEN d28>=2 THEN 1 ELSE 0 END)  AS d28_ge2,
          SUM(CASE WHEN d28>=3 THEN 1 ELSE 0 END)  AS d28_ge3,
          SUM(CASE WHEN d28>=4 THEN 1 ELSE 0 END)  AS d28_ge4,
          SUM(CASE WHEN d28>=5 THEN 1 ELSE 0 END)  AS d28_ge5,
          SUM(CASE WHEN d28>=6 THEN 1 ELSE 0 END)  AS d28_ge6,
          SUM(CASE WHEN d28>=7 THEN 1 ELSE 0 END)  AS d28_ge7,
          SUM(CASE WHEN d28>=8 THEN 1 ELSE 0 END)  AS d28_ge8,
          SUM(CASE WHEN d28>=9 THEN 1 ELSE 0 END)  AS d28_ge9,
          SUM(CASE WHEN d28>=10 THEN 1 ELSE 0 END) AS d28_ge10,
          SUM(CASE WHEN d7>=2  THEN 1 ELSE 0 END)  AS d7_repeat,
          SUM(CASE WHEN d14>=2 THEN 1 ELSE 0 END)  AS d14_repeat,
          SUM(CASE WHEN d28>=2 THEN 1 ELSE 0 END)  AS d28_repeat,
          SUM(d7)  AS orders_d7,
          SUM(d28) AS orders_d28
        FROM ucnt
        GROUP BY 1, 2, 3
        ORDER BY 1, 2, 3
        """,
        "subs_weekly": f"""
        WITH {city_cte}
        SELECT cm.city_name, cm.country_code,
          CAST(date_trunc('WEEK', d.bolt_plus_first_subscribed_ts) AS DATE) AS sub_week,
          COUNT(*) AS new_subscribers
        FROM ng_delivery_spark.dim_user_delivery d
        INNER JOIN city_map cm ON d.city_id = cm.city_id
        WHERE d.bolt_plus_first_subscribed_ts IS NOT NULL
          AND COALESCE(d.user_is_bot,false)=false
          AND COALESCE(d.is_user_test,false)=false
          AND COALESCE(d.is_user_employee,false)=false
          AND date_trunc('WEEK', d.bolt_plus_first_subscribed_ts) >= date_sub(date_trunc('WEEK', current_date()), 7*{N_WEEKS})
          AND date_trunc('WEEK', d.bolt_plus_first_subscribed_ts) <= current_date()
        GROUP BY 1, 2, 3
        ORDER BY 1, 2, 3
        """,
        "provider_top": f"""
        WITH {city_cte},
        prov AS (
          SELECT p.provider_id, p.provider_name, p.brand_name, p.city_name, cm.country_code,
                 COALESCE(NULLIF(TRIM(p.business_segment_v2),''),'Missing Segment') AS segment,
                 COALESCE(NULLIF(TRIM(p.account_manager_name),''),'Unassigned') AS am
          FROM ng_delivery_spark.dim_provider_v2 p
          INNER JOIN city_map cm
            ON p.city_name = cm.city_name AND p.country_name = cm.country_name
        ),
        spend AS (
          SELECT c.provider_id, lower(c.country) AS country_code,
            COUNT(DISTINCT c.order_id) AS orders,
            ROUND(SUM(COALESCE(c.bolt_spend,0)),2)     AS bolt_spend,
            ROUND(SUM(COALESCE(c.provider_spend,0)),2) AS provider_spend
          FROM ng_public_spark.etl_delivery_campaign_order_metrics c
          WHERE lower(c.country) IN ('cz', 'sk')
            AND c.order_created_date >= date_sub(date_trunc('WEEK', current_date()), 7*4)
            AND c.order_created_date <  date_trunc('WEEK', current_date())
          GROUP BY 1, 2
        )
        SELECT p.provider_id, p.provider_name, p.brand_name, p.city_name, p.country_code,
          p.segment, p.am,
          COALESCE(s.orders,0) AS campaign_orders,
          COALESCE(s.bolt_spend,0) AS bolt_spend,
          COALESCE(s.provider_spend,0) AS provider_spend
        FROM prov p
        LEFT JOIN spend s ON p.provider_id = s.provider_id AND p.country_code = s.country_code
        WHERE COALESCE(s.orders,0) > 0
        ORDER BY bolt_spend + provider_spend DESC
        """,
        "objective_weekly": f"""
        WITH {city_cte},
        prov AS (
          SELECT p.provider_id, p.city_name, cm.country_code
          FROM ng_delivery_spark.dim_provider_v2 p
          INNER JOIN city_map cm
            ON p.city_name = cm.city_name AND p.country_name = cm.country_name
        )
        SELECT p.city_name, p.country_code,
          CAST(date_trunc('WEEK', c.order_created_date) AS DATE) AS week_start,
          COALESCE(NULLIF(TRIM(c.spend_objective),''),'unknown') AS spend_objective,
          ROUND(SUM(COALESCE(c.bolt_spend,0)),2)     AS bolt_spend,
          ROUND(SUM(COALESCE(c.provider_spend,0)),2) AS provider_spend,
          COUNT(DISTINCT c.order_id) AS orders
        FROM ng_public_spark.etl_delivery_campaign_order_metrics c
        INNER JOIN prov p ON c.provider_id = p.provider_id AND lower(c.country) = p.country_code
        WHERE lower(c.country) IN ('cz', 'sk')
          AND c.order_created_date >= date_sub(date_trunc('WEEK', current_date()), 7*{N_WEEKS})
          AND c.order_created_date <= current_date()
        GROUP BY 1, 2, 3, 4
        ORDER BY 1, 2, 3, 5 DESC
        """,
        "cohort_freq": f"""
        WITH {city_cte},
        coh AS (
          SELECT m.week_date, m.user_id, c.city_name, c.country_code, m.user_cohort
          FROM mart_models_spark.mart_user_cohort_campaigns_lcp_weekly m
          INNER JOIN city_map c
            ON m.city_id = c.city_id AND lower(m.country_code) = c.country_code
          WHERE lower(m.country_code) IN ('cz', 'sk')
            AND m.week_date >= date_sub(date_trunc('WEEK', current_date()), 7*{N_WEEKS})
            AND m.week_date <= current_date()
        ),
        ord AS (
          SELECT o.user_id, CAST(date_trunc('WEEK', o.order_created_date) AS DATE) AS wk,
            cm.city_name, cm.country_code,
            COUNT(DISTINCT o.order_id) AS orders, SUM(o.order_gmv_eur) AS gmv
          FROM ng_delivery_spark.dim_order_delivery o
          INNER JOIN city_map cm
            ON o.city_name = cm.city_name AND o.country_name = cm.country_name
          WHERE o.delivery_vertical='food' AND o.order_state='delivered'
            AND o.order_created_date >= date_sub(date_trunc('WEEK', current_date()), 7*{N_WEEKS})
          GROUP BY 1, 2, 3, 4
        )
        SELECT coh.week_date AS week_start, coh.city_name, coh.country_code, coh.user_cohort,
          COUNT(DISTINCT coh.user_id) AS users,
          COUNT(DISTINCT CASE WHEN o.orders>0 THEN coh.user_id END) AS active_users,
          SUM(COALESCE(o.orders,0)) AS orders,
          ROUND(SUM(COALESCE(o.gmv,0)),2) AS gmv
        FROM coh
        LEFT JOIN ord o
          ON o.user_id = coh.user_id AND o.wk = coh.week_date
         AND o.city_name = coh.city_name AND o.country_code = coh.country_code
        GROUP BY 1, 2, 3, 4
        ORDER BY 1, 2, 3, 4
        """,
    }

    print(f"Pulling {len(queries)} queries in parallel ({len(ROSTER)} cities)…", flush=True)
    t0 = time.time()
    frames: dict = {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(_run_query, name, sql) for name, sql in queries.items()]
        for fut in as_completed(futures):
            name, df = fut.result()
            frames[name] = df
    print(f"All queries done in {time.time() - t0:.0f}s", flush=True)

    city_weekly = frames["city_weekly"]
    activation_weekly = frames["activation_weekly"]
    cohort_depth = frames["cohort_depth"]
    subs_weekly = frames["subs_weekly"]
    provider_top = frames["provider_top"]
    objective_weekly = frames["objective_weekly"]
    cohort_freq = frames["cohort_freq"]

    weeks = sorted({r["week_start"] for r in _records(city_weekly)})
    today = date.today()

    def iso_label(dstr):
        y, w, _ = date.fromisoformat(dstr).isocalendar()
        return f"{y}W{w:02d}"

    def is_complete(dstr):
        return (date.fromisoformat(dstr) + timedelta(days=6)) < today

    weeks_meta = [{"start": w, "label": iso_label(w), "complete": is_complete(w)} for w in weeks]
    complete_weeks = [w["start"] for w in weeks_meta if w["complete"]]
    latest_complete = complete_weeks[-1] if complete_weeks else None
    return {
        "meta": {
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "countries": COUNTRIES,
            "default_country": "cz",
            "country": "Czech Republic & Slovakia",
            "vertical": "food",
            "n_weeks": N_WEEKS,
            "weeks": weeks,
            "weeks_meta": weeks_meta,
            "latest_week": weeks[-1] if weeks else None,
            "latest_complete_week": latest_complete,
            "order_status_finished": "delivered",
            "comparison": "Week-over-week (selected ISO week vs the prior week). Default selected week = latest complete week.",
            "di_pct_def": "DI% = campaign discount (campaign_spend_bolt_eur + campaign_spend_provider_eur) / gross GMV (order_gmv_eur). Matches Looker 'campaign_discount_gmv_share'.",
            "roster": ROSTER,
            "sources": {
                "orders_gmv_di": "ng_delivery_spark.dim_order_delivery (delivery_vertical='food')",
                "activation_subs": "ng_delivery_spark.dim_user_delivery",
                "cohort_lcp": "mart_models_spark.mart_user_cohort_campaigns_lcp_weekly",
                "provider": "ng_delivery_spark.dim_provider_v2",
                "campaign_spend": "ng_public_spark.etl_delivery_campaign_order_metrics (country in cz, sk)",
            },
            "notes": [
                "DI spend = campaign_spend_bolt_eur + campaign_spend_provider_eur (= campaign_discount_eur, order-attributed).",
                "DI% = DI spend / gross GMV (order_gmv_eur). Cross-checked vs Looker 26798 (campaign_discount_gmv_share).",
                "Latest ISO week is partial (incomplete) -> dashboard defaults to the latest COMPLETE week; comparison is WoW.",
                "Order-depth & D7/D14/D28 repeat are measured on FIXED windows from signup so cohorts are comparable; a cohort shows only once mature for the window.",
                "Bolt+ subscription = dim_user_delivery.bolt_plus_first_subscribed_ts (first subscription).",
                "'Bolt+ Ready' (Plus-Ready) audience denominator is NOT in these tables -> conversion% needs SP/targeting source (open item).",
                "IC vs non-IC merchant split has no confirmed flag in dim_provider_v2 -> omitted (open item).",
            ],
        },
        "city_weekly": _records(city_weekly),
        "activation_weekly": _records(activation_weekly),
        "cohort_depth": _records(cohort_depth),
        "cohort_freq": _records(cohort_freq),
        "subs_weekly": _records(subs_weekly),
        "provider_top": _records(provider_top),
        "objective_weekly": _records(objective_weekly),
    }


if __name__ == "__main__":
    data = pull()
    out = Path(__file__).resolve().parent / "data.json"
    out.write_text(json.dumps(data, ensure_ascii=False))
    cw = data["city_weekly"]
    print(f"Wrote {out}")
    wm = data["meta"]["weeks_meta"]
    print("weeks:", ", ".join(f"{w['label']}{'' if w['complete'] else '(partial)'}" for w in wm))
    print(f"latest complete = {data['meta']['latest_complete_week']}")
    cz_n = sum(1 for m in ROSTER.values() if m["country"] == "cz")
    sk_n = sum(1 for m in ROSTER.values() if m["country"] == "sk")
    print(f"roster: {cz_n} CZ + {sk_n} SK cities")
    print(f"city_weekly: {len(cw)} | activation: {len(data['activation_weekly'])} | cohort_depth: {len(data['cohort_depth'])} | "
          f"cohort_freq: {len(data['cohort_freq'])} | subs: {len(data['subs_weekly'])} | providers: {len(data['provider_top'])} | objective: {len(data['objective_weekly'])}")
