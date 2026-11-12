# -*- coding: utf-8 -*-
"""Clean bakery_sales_raw.csv at the door, once.

raw file -> rules -> data/bakery_sales_clean.csv + data/rejects.csv + data/cleaning_log.json
Every row is written, removed as an exact duplicate, or rejected with a reason,
and the three counts must add up to the raw row count (count in, count out).
Usage: python clean.py
"""
import csv, json, re, sys, collections
from datetime import datetime

RAW, CLEAN, REJ, LOG = "data/bakery_sales_raw.csv", "data/bakery_sales_clean.csv", "data/rejects.csv", "data/cleaning_log.json"

BRANCHES = ["Tel Aviv - Florentin", "Tel Aviv - Dizengoff", "Ramat Gan", "Herzliya"]
BRANCH_ALIASES = {"taflorentin": "Tel Aviv - Florentin", "tadizengoff": "Tel Aviv - Dizengoff"}


def bkey(s):
    """branch match key: letters only, so dashes, en-dashes, spaces and case do not matter"""
    return re.sub(r"[^a-z]", "", s.lower())
WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6}
STATUSES = {"completed", "refunded"}
DATE_FORMATS = ["%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S", "%d/%m/%Y %H:%M", "%d %b %Y %H:%M"]

fixes = collections.Counter()


def norm_space(s):
    return re.sub(r"\s+", " ", s.strip())


def fix(field, raw, new):
    if raw != new:
        fixes[field] += 1
    return new


def parse_date(s):
    for f in DATE_FORMATS:
        try:
            return datetime.strptime(s, f)
        except ValueError:
            pass
    return None


def main():
    with open(RAW, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    fields = list(rows[0].keys())
    n_in = len(rows)

    # canonical product names = the most common spelling of each case-insensitive name
    spell = collections.defaultdict(collections.Counter)
    for r in rows:
        p = norm_space(r["product"])
        if p:
            spell[p.lower()][p] += 1
    canon_product = {k: c.most_common(1)[0][0] for k, c in spell.items()}
    canon_branch = {bkey(b): b for b in BRANCHES}
    canon_branch.update(BRANCH_ALIASES)

    seen, clean, rejects, dups = set(), [], [], 0
    for r in rows:
        key = tuple(r[k] for k in fields)
        if key in seen:
            dups += 1
            continue
        seen.add(key)

        reasons, out = [], {}
        out["order_id"] = norm_space(r["order_id"])

        d = parse_date(norm_space(r["order_datetime"]))
        if d is None:
            reasons.append("bad date: %r" % r["order_datetime"])
        else:
            out["order_datetime"] = fix("order_datetime", r["order_datetime"], d.strftime("%Y-%m-%d %H:%M"))

        b = canon_branch.get(bkey(r["branch"]))
        if b is None:
            reasons.append("unknown branch: %r" % r["branch"])
        else:
            out["branch"] = fix("branch", r["branch"], b)

        for c in ("channel", "payment_method", "customer_type", "category"):
            out[c] = fix(c, r[c], norm_space(r[c]).lower() if c != "category" else norm_space(r[c]))

        p = canon_product.get(norm_space(r["product"]).lower())
        if not p:
            reasons.append("missing product")
        else:
            out["product"] = fix("product", r["product"], p)

        q = norm_space(r["quantity"]).lower()
        q = WORDS.get(q, q)
        if isinstance(q, int):
            fixes["quantity"] += 1
        elif re.fullmatch(r"-?\d+", q):
            q = int(q)
        else:
            q = None
        if q is None:
            reasons.append("quantity not a number: %r" % r["quantity"])
        elif q <= 0:
            reasons.append("quantity not above zero: %r" % r["quantity"])
        else:
            out["quantity"] = q

        up = norm_space(r["unit_price"]).replace("₪", "")
        if re.fullmatch(r"\d+(\.\d+)?", up):
            out["unit_price"] = float(up)
            if up != r["unit_price"]:
                fixes["unit_price"] += 1
        else:
            reasons.append("unit_price not a number: %r" % r["unit_price"])

        s = norm_space(r["status"]).lower()
        if s not in STATUSES:
            reasons.append("status not completed/refunded: %r" % r["status"])
        else:
            out["status"] = fix("status", r["status"], s)

        if reasons:
            rejects.append(dict(r, reason="; ".join(reasons)))
            continue

        total = out["quantity"] * out["unit_price"]
        lt = norm_space(r["line_total"]).replace("₪", "")
        if not lt:
            fixes["line_total (filled from qty x price)"] += 1
        elif abs(float(lt) - total) > 0.01:
            fixes["line_total (recomputed, mismatch)"] += 1
        out["line_total"] = total
        for k in ("unit_price", "line_total"):
            out[k] = int(out[k]) if out[k] == int(out[k]) else round(out[k], 2)
        clean.append({k: out[k] for k in fields})

    with open(CLEAN, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(clean)
    with open(REJ, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields + ["reason"])
        w.writeheader()
        w.writerows(rejects)

    done = [r for r in clean if r["status"] == "completed"]
    log = {
        "rows_in": n_in,
        "duplicates_removed": dups,
        "rejected": len(rejects),
        "rows_written": len(clean),
        "adds_up": n_in == dups + len(rejects) + len(clean),
        "distinct_orders": len({r["order_id"] for r in clean}),
        "revenue_completed": round(sum(r["line_total"] for r in done), 2),
        "branches": sorted({r["branch"] for r in clean}),
        "fixes": dict(fixes.most_common()),
    }
    with open(LOG, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(log, ensure_ascii=False, indent=2))
    if not log["adds_up"]:
        sys.exit("count in != count out: stop")


if __name__ == "__main__":
    main()
