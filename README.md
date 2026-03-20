# YRS Innovations — Supertrend Strategy Backtester (Django)

## Setup & Run

```bash
pip install -r requirements.txt
python manage.py runserver
```

Then open: http://127.0.0.1:8000/

## URL Routes

| URL              | Description                          |
|------------------|--------------------------------------|
| `/`              | Landing page with instrument cards   |
| `/run/`          | POST — run full backtest             |
| `/live/?stock=X` | GET — live quote JSON (AJAX)         |
| `/download/?stock=X&side=long` | Download trades CSV   |

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
