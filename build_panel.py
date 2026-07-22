"""
BEFAS Sabah Paneli - veri toplayici ve site olusturucu.

Bu betik:
1) TEFAS'tan (pytefas kutuphanesi ile - yeni Next.js tabanli TEFAS
   API'sini kullanir) secilen BEFAS fonlarinin fiyatlarini bugun ve
   1A/3A/6A/1Y once icin ceker, getiri hesaplar.
2) yfinance ile USD/TRY, EUR/TRY, ons altin ve BIST100 verisini ceker,
   gram altini yaklasik olarak hesaplar.
3) template.html icindeki yer tutucularini doldurup index.html uretir.

Not: TCMB politika faizi PPK toplantilarinda (yilda ~8 kez) degistigi
icin asagida POLICY_RATE sabiti olarak tutuluyor - PPK karari sonrasi
bu sayiyi elle guncellemen yeterli (satirin yanindaki yorumda belirtildi).
"""
import datetime as dt
import json

import yfinance as yf
from pytefas import Crawler

# --- Ayarlar -----------------------------------------------------------

# Takip edilecek AGESA BEFAS fonlari (agesa.com.tr/fonpro/fonlarimiz/bireysel-emeklilik
# sayfasindaki tum fonlar) + karsilastirma icin bir alternatif.
FUND_CODES = [
    "AE1", "AE2", "AEK", "AVO", "KML", "EAE", "TSZ", "ENF", "TVC", "SBA",
    "MZN", "MZL", "MZP", "AEI", "AVN", "AVD", "AE3", "TVH", "AVG", "AVB",
    "AVR", "AEH", "AEB", "GFH", "GEV", "EHK", "FYL", "FYN",
]
COMPARE_PAIRS = [("AEH", "VEH")]  # (agesa_kodu, alternatif_kod)
ALL_CODES = list(dict.fromkeys(FUND_CODES + [c for pair in COMPARE_PAIRS for c in pair]))

# TCMB bir hafta vadeli repo faizi (PPK karari sonrasi elle guncelle).
POLICY_RATE = 37.00
POLICY_RATE_NOTE = "23 Temmuz 2026 PPK karari"


def fetch_funds_on(crawler, date, max_back=7):
    """Verilen tarihe en yakin islem gunu icin BEFAS (emeklilik) fonlarinin
    verisini ceker. pytefas bir pandas DataFrame doner; fund_code -> satir
    seklinde bir sozluge cevirir."""
    for delta in range(max_back):
        d = date - dt.timedelta(days=delta)
        try:
            df = crawler.fetch(d.strftime("%Y-%m-%d"), columns="info", kind="EMK")
        except Exception as exc:
            print(f"[uyari] {d} icin veri cekilemedi: {exc}")
            df = None
        if df is not None and not df.empty:
            return {row.fund_code: row for row in df.itertuples()}
    return {}


def collect_fund_data():
    crawler = Crawler()
    today = dt.date.today()
    periods = {
        "today": today,
        "1a": today - dt.timedelta(days=30),
        "3a": today - dt.timedelta(days=91),
        "6a": today - dt.timedelta(days=182),
        "1y": today - dt.timedelta(days=365),
    }
    snapshots = {k: fetch_funds_on(crawler, d) for k, d in periods.items()}

    funds = {}
    for code in ALL_CODES:
        today_row = snapshots["today"].get(code)
        if not today_row:
            print(f"[uyari] {code} icin bugune ait veri bulunamadi")
            continue
        price_today = float(today_row.price)
        returns = {}
        for label in ["1a", "3a", "6a", "1y"]:
            row = snapshots[label].get(code)
            returns[label] = (
                round((price_today / float(row.price) - 1) * 100, 2)
                if row else None
            )
        funds[code] = {
            "name": today_row.fund_name,
            "price": price_today,
            "returns": returns,
        }
    return funds


def collect_market_data():
    tickers = {
        "usdtry": "TRY=X",
        "eurtry": "EURTRY=X",
        "gold_oz": "GC=F",
        "bist100": "XU100.IS",
    }
    market = {}
    for key, sym in tickers.items():
        try:
            hist = yf.Ticker(sym).history(period="5d")
            last = float(hist["Close"].iloc[-1])
            prev = float(hist["Close"].iloc[-2])
            market[key] = {"value": last, "chg": round((last / prev - 1) * 100, 2)}
        except Exception:
            market[key] = {"value": None, "chg": None}

    if market["gold_oz"]["value"] and market["usdtry"]["value"]:
        gram = market["gold_oz"]["value"] / 31.1035 * market["usdtry"]["value"]
        market["gram_altin"] = {"value": round(gram, 2), "chg": market["gold_oz"]["chg"]}
    else:
        market["gram_altin"] = {"value": None, "chg": None}

    market["policy_rate"] = {"value": POLICY_RATE, "note": POLICY_RATE_NOTE}
    return market


def fmt_chg(chg):
    if chg is None:
        return '<span class="chg flat">veri yok</span>'
    css = "up" if chg > 0 else ("down" if chg < 0 else "flat")
    arrow = "▲" if chg > 0 else ("▼" if chg < 0 else "▶")
    return f'<span class="chg {css}">{arrow} %{abs(chg):.2f}</span>'


def render_ticker(market):
    def tick(label, val, chg_html, unit=""):
        val_str = f"{val:,.2f}{unit}".replace(",", ".") if val is not None else "—"
        return f'''<div class="tick">
          <div class="label">{label}</div>
          <div class="val">{val_str}</div>
          {chg_html}
        </div>'''

    parts = [
        tick("Dolar", market["usdtry"]["value"], fmt_chg(market["usdtry"]["chg"])),
        tick("Euro", market["eurtry"]["value"], fmt_chg(market["eurtry"]["chg"])),
        tick("Gram Altın", market["gram_altin"]["value"], fmt_chg(market["gram_altin"]["chg"])),
        tick("BİST 100", market["bist100"]["value"], fmt_chg(market["bist100"]["chg"])),
        f'''<div class="tick">
          <div class="label">TCMB Faizi</div>
          <div class="val">%{market["policy_rate"]["value"]:.2f}</div>
          <div class="chg flat">{market["policy_rate"]["note"]}</div>
        </div>''',
    ]
    return "\n".join(parts)


def render_funds(funds):
    cards = []
    for code in FUND_CODES:
        f = funds.get(code)
        if not f:
            continue
        ret_cells = []
        for label in ["1a", "3a", "6a", "1y"]:
            v = f["returns"][label]
            color = "var(--up)" if (v or 0) >= 0 else "var(--down)"
            v_str = f"{v:+.2f}" if v is not None else "—"
            ret_cells.append(
                f'<div class="ret"><div class="p">{label.upper()}</div>'
                f'<div class="v" style="color:{color}">{v_str}</div></div>'
            )
        cards.append(f'''<div class="fund-card">
          <div class="fund-top">
            <div>
              <div class="fund-code">{code}</div>
              <div class="fund-name">{f["name"].title()}</div>
            </div>
            <div class="fund-price">{f["price"]:.4f} ₺</div>
          </div>
          <div class="returns">{''.join(ret_cells)}</div>
        </div>''')
    return "\n".join(cards)


def render_compare(funds):
    rows = []
    for base, alt in COMPARE_PAIRS:
        fb, fa = funds.get(base), funds.get(alt)
        if not fb or not fa:
            continue
        rb, ra = fb["returns"]["1y"] or 0, fa["returns"]["1y"] or 0
        top = max(rb, ra, 1)
        rows.append(f'''<div class="compare-row">
          <div class="compare-name">{base}<span>AGESA</span></div>
          <div class="bar-track"><div class="bar-fill" style="width:{rb/top*100:.0f}%;background:var(--gold);"></div></div>
          <div class="compare-val">{rb:+.2f}</div>
        </div>
        <div class="compare-row">
          <div class="compare-name">{alt}<span>{fa["name"].split(" ")[0].title()}</span></div>
          <div class="bar-track"><div class="bar-fill" style="width:{ra/top*100:.0f}%;background:var(--text-muted);"></div></div>
          <div class="compare-val">{ra:+.2f}</div>
        </div>''')
    return "\n".join(rows)


def main():
    funds = collect_fund_data()
    market = collect_market_data()

    with open("data.json", "w", encoding="utf-8") as f:
        json.dump({"funds": funds, "market": market}, f, ensure_ascii=False, indent=2, default=str)

    with open("template.html", encoding="utf-8") as f:
        html = f.read()

    now = dt.datetime.now()
    date_line = now.strftime("%d.%m.%Y %A · Otomatik guncelleme")
    html = (
        html.replace("{{DATE_LINE}}", date_line)
        .replace("{{TICKER_HTML}}", render_ticker(market))
        .replace("{{FUNDS_HTML}}", render_funds(funds))
        .replace("{{COMPARE_HTML}}", render_compare(funds))
        .replace("{{GENERATED_AT}}", now.strftime("%d.%m.%Y %H:%M"))
    )

    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)


if __name__ == "__main__":
    main()
