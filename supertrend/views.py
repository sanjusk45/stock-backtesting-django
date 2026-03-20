from django.shortcuts import render
from django.http import HttpResponse, JsonResponse
from django.core.cache import cache
from .analysis import SYMBOLS, run_backtest, fetch_live_data


SYMBOLS_INFO = [
    {"ticker": "RELIANCE.NS",  "name": "RELIANCE",  "title": "Reliance Industries",   "desc": "Large-cap energy & retail conglomerate"},
    {"ticker": "NIFTYBEES.NS", "name": "NIFTYBEES", "title": "Nippon Nifty BeES ETF", "desc": "Tracks Nifty 50 — passive index fund"},
    {"ticker": "ITC.NS",       "name": "ITC",        "title": "ITC Limited",           "desc": "FMCG, hotels, agribusiness, paperboards"},
    {"ticker": "TCS.NS",       "name": "TCS",        "title": "Tata Consultancy Svc",  "desc": "India's largest IT services company"},
    {"ticker": "HDFCBANK.NS",  "name": "HDFCBANK",   "title": "HDFC Bank",             "desc": "India's largest private sector bank"},
    {"ticker": "INFY.NS",      "name": "INFY",       "title": "Infosys",               "desc": "Global IT consulting & services"},
]


def index(request):
    return render(request, "supertrend/index.html", {
        "symbols":      list(SYMBOLS.keys()),
        "symbols_info": SYMBOLS_INFO,
    })


def run(request):
    if request.method != "POST":
        return HttpResponse("Method not allowed", status=405)

    stock = request.POST.get("stock", "RELIANCE")
    if stock not in SYMBOLS:
        return HttpResponse("Invalid stock", status=400)

    try:
        years_back = int(request.POST.get("years_back", 3))
        years_back = max(1, min(5, years_back))
    except ValueError:
        years_back = 3

    # Cache key — reuse if same stock+years requested within 30 min
    cache_key = f"backtest_{stock}_{years_back}"
    ctx = cache.get(cache_key)
    if ctx is None:
        ctx = run_backtest(stock, years_back=years_back)
        cache.set(cache_key, ctx, timeout=1800)  # 30 minutes

    ctx["symbols"]        = list(SYMBOLS.keys())
    ctx["selected_stock"] = stock
    ctx["years_back"]     = years_back
    return render(request, "supertrend/results.html", ctx)


def live_quote(request):
    stock  = request.GET.get("stock", "RELIANCE")
    ticker = SYMBOLS.get(stock)
    if not ticker:
        return JsonResponse({"status": "error", "msg": "Invalid stock"})
    # Cache live quote for 5 minutes
    cache_key = f"live_{stock}"
    data = cache.get(cache_key)
    if data is None:
        data = fetch_live_data(ticker)
        cache.set(cache_key, data, timeout=300)
    return JsonResponse(data)


def compare(request):
    """Compare two stocks side by side."""
    if request.method == "GET":
        return render(request, "supertrend/compare.html", {
            "symbols": list(SYMBOLS.keys()),
            "ctx1": None, "ctx2": None,
        })
    if request.method != "POST":
        return HttpResponse("Method not allowed", status=405)

    stock1 = request.POST.get("stock1", "RELIANCE")
    stock2 = request.POST.get("stock2", "ITC")
    try:
        years_back = int(request.POST.get("years_back", 3))
        years_back = max(1, min(5, years_back))
    except ValueError:
        years_back = 3

    if stock1 not in SYMBOLS or stock2 not in SYMBOLS:
        return HttpResponse("Invalid stock", status=400)

    cache_key1 = f"backtest_{stock1}_{years_back}"
    cache_key2 = f"backtest_{stock2}_{years_back}"
    ctx1 = cache.get(cache_key1) or run_backtest(stock1, years_back=years_back)
    ctx2 = cache.get(cache_key2) or run_backtest(stock2, years_back=years_back)
    cache.set(cache_key1, ctx1, timeout=1800)
    cache.set(cache_key2, ctx2, timeout=1800)

    return render(request, "supertrend/compare.html", {
        "symbols":      list(SYMBOLS.keys()),
        "symbols_info": SYMBOLS_INFO,
        "ctx1": ctx1, "ctx2": ctx2,
        "stock1": stock1, "stock2": stock2,
        "years_back": years_back,
    })


def download_csv(request):
    stock = request.GET.get("stock", "RELIANCE")
    side  = request.GET.get("side", "long")
    if stock not in SYMBOLS:
        return HttpResponse("Invalid stock", status=400)

    cache_key = f"backtest_{stock}_3"
    ctx  = cache.get(cache_key) or run_backtest(stock)
    data = ctx["csv_long"] if side == "long" else ctx["csv_short"]

    response = HttpResponse(data, content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{stock}_{side}_trades.csv"'
    return response
