# מאפייה · דשבורד מכירות (AiDO מטלה 4)

ניקוי של `data/bakery_sales_raw.csv` ודשבורד בעברית שמציג את הנתונים הנקיים.

קובץ הנתונים הוא חומר של הקורס ולכן לא נמצא בריפו. כדי להריץ, שמים אותו ב-`data/bakery_sales_raw.csv`. הדשבורד (`index.html`) מכיל רק סיכומים, ו-`data/cleaning_log.json` מראה את הספירות.

צפייה: [הדשבורד](https://e37dey.github.io/aido-lesson4-bakery/) · [הגרסה החיה מ-Airtable](https://e37dey.github.io/aido-lesson4-bakery/airtable.html) (צריך טוקן קריאה משלך)

## הרצה
```
python clean.py            # raw -> clean + rejects + log, עוצר אם החשבון לא נסגר
python build_dashboard.py  # מסכם ומטמיע את הנתונים ב-index.html
python -m http.server 8765 # ופותחים http://localhost:8765
```

## מה הניקוי עושה
- מסיר 15 שורות כפולות מדויקות
- מאחד שמות סניפים, מוצרים וסטטוסים (רווחים, אותיות גדולות, מקפים)
- ממיר כמויות במילים (one, two) למספרים, ומסיר ₪ ממחירים
- מאחד 4 פורמטים של תאריך (dd/mm/yyyy לפי הפורמט הישראלי)
- משלים line_total חסר מכמות כפול מחיר
- דוחה 12 שורות שאי אפשר לנקות ל-`data/rejects.csv`, כל אחת עם סיבה

## בדיקת החשבון
29,142 שורות = 29,115 שנכתבו + 15 כפילויות + 12 נדחו.
14,421 הזמנות, ‏647,065 ₪ הכנסות מהזמנות שהושלמו, ‏4 סניפים. תואם למספרים שבשיעור.

## חיבור ל-Airtable (שאלה 5)
בסיס: "מאפייה - מכירות (AiDO מטלה 4)", ‏Base ID ‏appoBEQVNkMFcKm1K. חמש טבלאות מקושרות:
Branches, ‏Products, ‏Weekly sales (מקושר ל-Branches), ‏Monthly product sales (מקושר ל-Products), ‏Import runs.
בתוכנית החינמית יש עד 1,000 רשומות לבסיס, לכן עולים סיכומים (כ-443 רשומות) ולא 29,115 שורות.

1. טוקן כתיבה לסקריפט: data.records:read, ‏data.records:write, ‏schema.bases:read, רק לבסיס הזה.
2. מעתיקים `.env.example` ל-`.env` וממלאים. הקובץ ב-.gitignore.
3. `python upload_airtable.py`. אפשר להריץ פעמיים: upsert לפי Key, אין כפילויות.
4. טוקן קריאה בלבד לדשבורד: data.records:read, ‏schema.bases:read. מדביקים ב-`airtable.html`.

`tests/airtable_mock.html` מריץ את הדשבורד החי על נתוני דמה בלי טוקן.

## מקור חיצוני: Hebcal API (בונוס)
פאנל "חגים מול יום רגיל" ב-`index.html` מושך בזמן אמת את חגי ישראל מ-`hebcal.com` (בקשת GET, בלי מפתח, CORS פתוח), ומשווה את ההכנסה היומית הממוצעת בכל חג להכנסה ביום פתיחה רגיל.
