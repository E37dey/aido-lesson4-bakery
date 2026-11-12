# -*- coding: utf-8 -*-
"""Upload the clean bakery data to Airtable as summary tables. Safe to run twice.

The free plan holds 1,000 records per base, and the clean file has 29,115 lines,
so we upload summaries: 4 branches, ~19 products, one row per week per branch,
one row per month per product, and one Import runs row per run (the log).

Every summary row has a stable Key (e.g. "2025-09-07|Herzliya") and is written with
Airtable's upsert (performUpsert on Key): if the key exists the row is updated, if not
it is created. Run it twice and you still get each row exactly once.

Needs .env (never committed): AIRTABLE_TOKEN=pat...  AIRTABLE_BASE_ID=app...
Token scopes: data.records:read, data.records:write, schema.bases:read, this base only.
Usage: python clean.py && python upload_airtable.py
"""
import csv, json, os, sys, time, collections, urllib.request, urllib.error, urllib.parse
from datetime import datetime, timedelta

API = "https://api.airtable.com/v0"
HE_BRANCH = {"Tel Aviv - Florentin": "פלורנטין, ת\"א", "Tel Aviv - Dizengoff": "דיזנגוף, ת\"א", "Ramat Gan": "רמת גן", "Herzliya": "הרצליה"}
HE_PROD = {"Challah": "חלה", "Croissant": "קרואסון", "Cheese bourekas": "בורקס גבינה", "Cappuccino": "קפוצ'ינו", "Pita (pack of 6)": "פיתות (6)",
           "Potato bourekas": "בורקס תפוחי אדמה", "Cinnamon roll": "שנקי קינמון", "Baguette": "באגט", "Sourdough loaf": "לחם מחמצת", "Espresso": "אספרסו",
           "Rugelach (box)": "רוגלך (קופסה)", "Spinach pastry": "מאפה תרד", "Cheesecake slice": "פרוסת עוגת גבינה", "Whole wheat loaf": "לחם מלא",
           "Cookies (bag)": "עוגיות (שקית)", "Babka": "בבקה", "Fresh orange juice": "מיץ תפוזים סחוט", "Sufganiyah": "סופגנייה", "Hamantaschen (box)": "אוזני המן (קופסה)"}


def load_env(path=".env"):
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


load_env()
TOKEN, BASE = os.environ.get("AIRTABLE_TOKEN", ""), os.environ.get("AIRTABLE_BASE_ID", "")
if not TOKEN.startswith("pat") or not BASE.startswith("app"):
    sys.exit("Missing AIRTABLE_TOKEN / AIRTABLE_BASE_ID in .env (copy .env.example to .env and fill it in)")


def call(method, path, body=None, tries=4):
    """One API request. Waits between calls (5 requests/second limit) and retries on 429/5xx."""
    for attempt in range(tries):
        time.sleep(0.22)
        req = urllib.request.Request(API + path, method=method, data=json.dumps(body).encode() if body else None,
                                     headers={"Authorization": "Bearer " + TOKEN, "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            msg = e.read().decode(errors="replace")
            if e.code in (429, 500, 502, 503) and attempt < tries - 1:
                time.sleep(2 ** attempt)
                continue
            sys.exit("Airtable %s %s -> %s %s" % (method, path, e.code, msg[:300]))


def upsert(table, rows, key="Key"):
    """PATCH with performUpsert, 10 records per request. Returns {key: record id}."""
    ids, created, updated = {}, 0, 0
    for i in range(0, len(rows), 10):
        chunk = rows[i:i + 10]
        res = call("PATCH", "/%s/%s" % (BASE, urllib.parse.quote(table)),
                   {"performUpsert": {"fieldsToMergeOn": [key]}, "typecast": True, "records": [{"fields": f} for f in chunk]})
        created += len(res.get("createdRecords", []))
        updated += len(res.get("updatedRecords", []))
        for rec in res["records"]:
            ids[rec["fields"][key]] = rec["id"]
    print("  %-22s %4d rows  (%d created, %d updated)" % (table, len(rows), created, updated))
    return ids


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    rows = list(csv.DictReader(open("data/bakery_sales_clean.csv", encoding="utf-8")))
    log = json.load(open("data/cleaning_log.json", encoding="utf-8"))
    if not log.get("adds_up"):
        sys.exit("cleaning_log says count in != count out: run clean.py and fix it first")

    # 1) the things other tables point at
    branch_ids = upsert("Branches", [{"Name": b, "Hebrew name": h} for b, h in HE_BRANCH.items()], key="Name")
    price, cat = {}, {}
    for r in rows:
        price.setdefault(r["product"], collections.Counter())[float(r["unit_price"])] += 1
        cat[r["product"]] = r["category"]
    prods = [{"Name": p, "Hebrew name": HE_PROD.get(p, p), "Category": cat[p], "Unit price": c.most_common(1)[0][0]} for p, c in sorted(price.items())]
    product_ids = upsert("Products", prods, key="Name")

    # 2) weekly sales per branch (week starts on Sunday)
    wk = collections.defaultdict(lambda: {"rev": 0.0, "orders": set(), "items": 0, "ref": 0.0})
    mp = collections.defaultdict(lambda: {"units": 0, "rev": 0.0})
    for r in rows:
        d = datetime.strptime(r["order_datetime"], "%Y-%m-%d %H:%M")
        start = (d - timedelta(days=(d.weekday() + 1) % 7)).strftime("%Y-%m-%d")
        w = wk[(start, r["branch"])]
        if r["status"] == "completed":
            w["rev"] += float(r["line_total"])
            w["orders"].add(r["order_id"])
            w["items"] += int(r["quantity"])
            m = mp[(d.strftime("%Y-%m-01"), r["product"])]
            m["units"] += int(r["quantity"])
            m["rev"] += float(r["line_total"])
        else:
            w["ref"] += float(r["line_total"])
    weekly = [{"Key": "%s|%s" % k, "Week start": k[0], "Branch": [branch_ids[k[1]]], "Revenue": round(v["rev"]),
               "Orders": len(v["orders"]), "Items": v["items"], "Refunded": round(v["ref"])} for k, v in sorted(wk.items())]
    monthly = [{"Key": "%s|%s" % (k[0][:7], k[1]), "Month": k[0], "Product": [product_ids[k[1]]], "Units": v["units"],
                "Revenue": round(v["rev"])} for k, v in sorted(mp.items())]
    total = len(branch_ids) + len(product_ids) + len(weekly) + len(monthly)
    print("  records in base after upload: ~%d of 1,000 (free plan)" % (total + 1))
    upsert("Weekly sales", weekly)
    upsert("Monthly product sales", monthly)

    # 3) check: what is in Airtable must equal what is in the clean file
    uploaded = round(sum(w["Revenue"] for w in weekly))
    expected = round(log["revenue_completed"])
    assert abs(uploaded - expected) <= len(weekly), "revenue mismatch: %s vs %s" % (uploaded, expected)

    # 4) the log row: count in, count out
    upsert("Import runs", [{"Run": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "Rows in": log["rows_in"],
                            "Duplicates removed": log["duplicates_removed"], "Rejected": log["rejected"],
                            "Rows written": log["rows_written"], "Revenue completed": log["revenue_completed"],
                            "Adds up": bool(log["adds_up"])}], key="Run")
    print("done. weekly revenue sum %s = clean file %s" % (uploaded, expected))


if __name__ == "__main__":
    main()
