
# 📈 Stock Market Strategy Backtesting Web Application

## 🚀 Overview
This is a Django-based web application for stock market analysis and strategy backtesting using the Supertrend indicator. It allows users to analyze historical data, generate buy/sell signals, and evaluate trading performance.
---
## 🛠️ Tech Stack
- Python
- Django
- Pandas, NumPy
- yFinance API
- Matplotlib
- HTML, CSS, Bootstrap

---

## ⚙️ Setup & Run

```bash
pip install -r requirements.txt
python manage.py runserver

## Project Structure

```
nifty_django/
├── manage.py
├── requirements.txt
├── nifty_django/
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
└── supertrend/
    ├── analysis.py          ← core logic (Heikin Ashi, Supertrend, backtest)
    ├── views.py             ← Django views
    ├── urls.py              ← URL routing
    ├── templatetags/
    │   └── dict_extras.py  ← custom template filter
    └── templates/supertrend/
        ├── base.html        ← sidebar + CSS + JS tabs
        ├── index.html       ← landing page
        └── results.html     ← 5-tab results page
```

# stock-backtesting-django
Django-based web application for stock market analysis and strategy backtesting using Supertrend indicator,
 Pandas, and yFinance API with data visualization..

