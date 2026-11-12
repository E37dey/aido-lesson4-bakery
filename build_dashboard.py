# -*- coding: utf-8 -*-
"""Aggregate the clean CSV and inject it into index.html (between the DATA markers).
Usage: python clean.py && python build_dashboard.py"""
import csv, json, re, collections
from datetime import datetime

rows = list(csv.DictReader(open("data/bakery_sales_clean.csv", encoding="utf-8")))
log = json.load(open("data/cleaning_log.json", encoding="utf-8"))
BR = ["Tel Aviv - Florentin", "Tel Aviv - Dizengoff", "Ramat Gan", "Herzliya"]
DAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]


def agg(rs):
    done = [r for r in rs if r["status"] == "completed"]
    orders = {}
    for r in rs:
        orders.setdefault(r["order_id"], r)
    ref_orders = {r["order_id"] for r in rs if r["status"] == "refunded"}
    rev = lambda xs: round(sum(float(r["line_total"]) for r in xs))
    months, prod, prodq, cat, chan, pay, cust, friday = (collections.Counter() for _ in range(8))
    heat = [[0] * 24 for _ in range(7)]
    seasonal = collections.defaultdict(collections.Counter)
    for r in done:
        v = float(r["line_total"])
        d = datetime.strptime(r["order_datetime"], "%Y-%m-%d %H:%M")
        months[d.strftime("%Y-%m")] += v
        prod[r["product"]] += v
        prodq[r["product"]] += int(r["quantity"])
        cat[r["category"]] += v
        if d.weekday() == 4:
            friday[r["branch"]] += v
        if r["product"] in ("Sufganiyah", "Hamantaschen (box)"):
            seasonal[r["product"]][d.strftime("%Y-%m")] += int(r["quantity"])
    seen = set()
    for r in done:
        if r["order_id"] in seen:
            continue
        seen.add(r["order_id"])
        d = datetime.strptime(r["order_datetime"], "%Y-%m-%d %H:%M")
        heat[(d.weekday() + 1) % 7][d.hour] += 1  # row 0 = Sunday
        chan[r["channel"]] += 1
        pay[r["payment_method"]] += 1
        cust[r["customer_type"]] += 1
    n_done = len(seen)
    revenue = rev(done)
    return {
        "revenue": revenue,
        "orders": n_done,
        "aov": round(revenue / n_done, 1) if n_done else 0,
        "items": sum(int(r["quantity"]) for r in done),
        "refund_rate": round(100 * len(ref_orders) / len(orders), 2) if orders else 0,
        "refunded_amount": rev([r for r in rs if r["status"] == "refunded"]),
        "months": dict(sorted((k, round(v)) for k, v in months.items())),
        "products": [[k, round(v), prodq[k]] for k, v in prod.most_common()],
        "categories": {k: round(v) for k, v in cat.most_common()},
        "channels": dict(chan.most_common()),
        "payments": dict(pay.most_common()),
        "customers": dict(cust.most_common()),
        "friday": {k: round(v) for k, v in friday.most_common()},
        "heat": heat,
        "seasonal": {k: dict(sorted(v.items())) for k, v in seasonal.items()},
    }


data = {"all": agg(rows)}
for b in BR:
    data[b] = agg([r for r in rows if r["branch"] == b])
data["by_branch"] = {b: data[b]["revenue"] for b in BR}
data["branch_months"] = {b: data[b]["months"] for b in BR}
data["log"] = log
daily = collections.Counter()
for r in rows:
    if r["status"] == "completed":
        daily[r["order_datetime"][:10]] += float(r["line_total"])
data["daily"] = {k: round(v) for k, v in sorted(daily.items())}
data["range"] = [min(r["order_datetime"] for r in rows)[:10], max(r["order_datetime"] for r in rows)[:10]]

def inject(page, payload):
    html = open(page, encoding="utf-8").read()
    blob = "/*DATA*/const DATA = " + json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + ";/*END*/"
    html, n = re.subn(r"/\*DATA\*/.*?/\*END\*/", lambda m: blob, html, flags=re.S)
    assert n == 1, "DATA marker not found in " + page
    open(page, "w", encoding="utf-8").write(html)


inject("index.html", data)
inject("holidays.html", {"daily": data["daily"], "range": data["range"]})
print("revenue", data["all"]["revenue"], "orders", data["all"]["orders"], "friday", data["all"]["friday"])
