"""
BEFAS Sabah Paneli - veri toplayici ve site olusturucu.

Bu betik:
1) TEFAS'tan (pytefas kutuphanesi ile) AGESA'nin BEFAS fonlarinin
   fiyatlarini bugun ve 1A/6A/1Y/3Y/5Y once icin ceker, getiri hesaplar.
2) yfinance ile USD/TRY, EUR/TRY, ons altin ve BIST100 verisini ceker,
   gram altini yaklasik olarak hesaplar.
3) template.html icindeki yer tutucularini doldurup index.html uretir.
   Fon kartlari kategoriye gore gruplanir; sayfada bir kategori
   filtresi (dropdown) ile istenen kategori tek basina goruntulenebilir.

Not: TCMB politika faizi PPK toplantilarinda (yilda ~8 kez) degistigi
icin asagida POLICY_RATE sabiti olarak tutuluyor - PPK karari sonrasi
bu sayiyi elle guncellemen yeterli (satirin yanindaki yorumda belirtildi).
"""
import datetime as dt
import json
import os
from collections import OrderedDict

import yfinance as yf
from pytefas import Crawler
from anthropic import Anthropic

# --- Ayarlar -----------------------------------------------------------

# AGESA'nin kendi BEFAS fonlari, kategorilere ayrilmis (kart gorunumu icin).
# Karsilastirma araci bunlarla sinirli degil - TEFAS'taki TUM fonlar secilebilir.
CATEGORIES = OrderedDict([
    ("Para Piyasası", ["AE1"]),
    ("Borçlanma Araçları", ["AE2", "AEK", "AVO", "AVB", "AVG"]),
    ("Hisse Senedi", ["AEH", "AEB", "GFH", "TVH"]),
    ("Altın ve Kıymetli Maden", ["KML", "EAE", "GEV"]),
    ("Sektörel / Tematik Değişken", ["TSZ", "ENF", "TVC", "AVR", "SBA"]),
    ("Standart / Karma / Katkı", ["AEI", "AVN", "AVD", "AE3"]),
    ("Fon Sepetleri", ["MZN", "MZL", "MZP"]),
    ("Katılım (Faizsiz)", ["FYL", "FYN", "EHK"]),
])
AGESA_CODES = [c for codes in CATEGORIES.values() for c in codes]

PERIODS = {
    "today": 0,
    "1a": 30,
    "6a": 182,
    "1y": 365,
    "3y": 365 * 3,
    "5y": 365 * 5 - 20,  # TEFAS "5 yildan eski olamaz" sinirina karsi guvenlik payi
}
PERIOD_LABELS = ["1a", "6a", "1y", "3y", "5y"]

# TCMB bir hafta vadeli repo faizi (PPK karari sonrasi elle guncelle).
POLICY_RATE = 37.00
POLICY_RATE_NOTE = "23 Temmuz 2026 PPK kararı"


def fetch_funds_on(crawler, date, max_back=7, forward=False):
    """Verilen tarihe en yakin islem gunu icin TEFAS'in dondugu tum BEFAS
    (emeklilik) fonlarinin verisini ceker. fund_code -> satir sozlugu doner.
    forward=True ise (gecmis donem hesaplamalarinda kullanilir) veri
    bulunamadiginca tarihi ILERIYE (bugune dogru) kaydirir - boylece TEFAS'in
    "5 yildan eski olamaz" gibi sinirlarina geriye giderek yaklasmayiz."""
    for delta in range(max_back):
        d = date + dt.timedelta(days=delta) if forward else date - dt.timedelta(days=delta)
        try:
            df = crawler.fetch(d.strftime("%Y-%m-%d"), columns="info", kind="EMK")
        except Exception as exc:
            print(f"[uyarı] {d} için veri çekilemedi: {exc}")
            df = None
        if df is not None and not df.empty:
            return {row.fund_code: row for row in df.itertuples()}
    print(f"[uyarı] {date} civarinda hic veri bulunamadi ({max_back} gun tarandi)")
    return {}


def collect_all_funds():
    crawler = Crawler()
    today = dt.date.today()
    snapshots = {
        label: fetch_funds_on(
            crawler,
            today - dt.timedelta(days=days),
            forward=(days > 0),  # bugun haricinde ileri yonde ara
        )
        for label, days in PERIODS.items()
    }

    all_funds = {}
    for code, today_row in snapshots["today"].items():
        price_today = float(today_row.price)
        returns = {}
        for label in PERIOD_LABELS:
            row = snapshots[label].get(code)
            returns[label] = (
                round((price_today / float(row.price) - 1) * 100, 2)
                if row else None
            )
        all_funds[code] = {
            "code": code,
            "name": today_row.fund_name.strip(),
            "price": price_today,
            "returns": returns,
        }

    missing = [c for c in AGESA_CODES if c not in all_funds]
    if missing:
        print(f"[uyarı] Şu AGESA fonları bugün TEFAS'ta bulunamadı: {missing}")

    return all_funds


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
        except Exception as exc:
            print(f"[uyarı] {sym} çekilemedi: {exc}")
            market[key] = {"value": None, "chg": None}

    if market["gold_oz"]["value"] and market["usdtry"]["value"]:
        gram = market["gold_oz"]["value"] / 31.1035 * market["usdtry"]["value"]
        market["gram_altin"] = {"value": round(gram, 2), "chg": market["gold_oz"]["chg"]}
    else:
        market["gram_altin"] = {"value": None, "chg": None}

    market["policy_rate"] = {"value": POLICY_RATE, "note": POLICY_RATE_NOTE}
    return market


def fetch_news():
    """Anthropic API'yi (web arama araciyla) kullanarak BES/emeklilik/sigorta/
    faiz-doviz gundemiyle ilgili 5-6 guncel haberi ceker ve ozetletir.
    ANTHROPIC_API_KEY tanimli degilse veya bir hata olursa bos liste doner
    (site o zaman haber bolumunu atlar, geri kalan her sey calismaya devam eder)."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("[uyarı] ANTHROPIC_API_KEY tanımlı değil, haber bölümü atlanıyor")
        return []

    prompt = (
        "Türkiye'deki bireysel emeklilik sistemi (BES/BEFAS), emeklilik "
        "yatırım fonları, hayat sigortası ve emeklilik şirketleri sektörü, "
        "TCMB faiz kararları/politikası ve döviz-altın piyasası ile ilgili "
        "BUGÜNE ait en önemli 5-6 haberi bul. Her biri için kısa bir başlık "
        "(en fazla 12 kelime), 1-2 cümlelik özet ve kaynağın adını ver. "
        "SADECE geçerli bir JSON dizisi olarak cevap ver, başka hiçbir "
        "açıklama veya metin ekleme. Format: "
        '[{"title": "...", "summary": "...", "source": "..."}]'
    )
    try:
        client = Anthropic(api_key=api_key)
        response = client.messages.create(
            model="claude-sonnet-5",
            max_tokens=4096,
            tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 6}],
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(b.text for b in response.content if b.type == "text").strip()
        if response.stop_reason == "max_tokens":
            print("[uyarı] Haber yanıtı max_tokens sınırında kesildi, JSON eksik olabilir")
        if text.startswith("```"):
            text = text.strip("`")
            if text.startswith("json"):
                text = text[4:]
        # Modelin JSON dizisinden once/sonra fazladan metin eklemesi ihtimaline karsi
        start, end = text.find("["), text.rfind("]")
        if start != -1 and end != -1:
            text = text[start:end + 1]
        news = json.loads(text)
        return news[:6]
    except Exception as exc:
        print(f"[uyarı] Haber çekilemedi: {exc}")
        return []


def render_news(news):
    if not news:
        return '<div class="hint">Gündem haberleri şu an alınamadı.</div>'
    cards = []
    for item in news:
        cards.append(f'''<div class="news-card">
          <div class="news-title">{item.get("title", "")}</div>
          <div class="news-summary">{item.get("summary", "")}</div>
          <div class="news-source">{item.get("source", "")}</div>
        </div>''')
    return "\n".join(cards)


def fmt_chg(chg):
    if chg is None:
        return '<span class="chg flat">veri yok</span>'
    css = "up" if chg > 0 else ("down" if chg < 0 else "flat")
    arrow = "▲" if chg > 0 else ("▼" if chg < 0 else "▶")
    return f'<span class="chg {css}">{arrow} %{abs(chg):.2f}</span>'


def render_ticker(market):
    def tick(label, val, chg_html):
        val_str = f"{val:,.2f}".replace(",", ".") if val is not None else "—"
        return f'''<div class="tick">
          <div class="label">{label}</div>
          <div class="val">{val_str}</div>
          {chg_html}
        </div>'''

    return "\n".join([
        tick("Dolar", market["usdtry"]["value"], fmt_chg(market["usdtry"]["chg"])),
        tick("Euro", market["eurtry"]["value"], fmt_chg(market["eurtry"]["chg"])),
        tick("Gram Altın", market["gram_altin"]["value"], fmt_chg(market["gram_altin"]["chg"])),
        tick("BİST 100", market["bist100"]["value"], fmt_chg(market["bist100"]["chg"])),
        f'''<div class="tick">
          <div class="label">TCMB Faizi</div>
          <div class="val">%{market["policy_rate"]["value"]:.2f}</div>
          <div class="chg flat">{market["policy_rate"]["note"]}</div>
        </div>''',
    ])


def render_fund_card(f):
    ret_cells = []
    for label in PERIOD_LABELS:
        v = f["returns"][label]
        color = "var(--up)" if (v or 0) >= 0 else "var(--down)"
        v_str = f"{v:+.2f}" if v is not None else "—"
        ret_cells.append(
            f'<div class="ret"><div class="p">{label.upper()}</div>'
            f'<div class="v" style="color:{color}">{v_str}</div></div>'
        )
    return f'''<div class="fund-card">
      <div class="fund-top">
        <div>
          <div class="fund-code">{f["code"]}</div>
          <div class="fund-name">{f["name"]}</div>
        </div>
        <div class="fund-price">{f["price"]:.4f} ₺</div>
      </div>
      <div class="returns returns-5">{''.join(ret_cells)}</div>
    </div>'''


def render_category_options():
    opts = ['<option value="all">Tüm Kategoriler</option>']
    for category in CATEGORIES:
        opts.append(f'<option value="{category}">{category}</option>')
    return "\n".join(opts)


def render_categorized_funds(all_funds):
    blocks = []
    for category, codes in CATEGORIES.items():
        cards = [render_fund_card(all_funds[c]) for c in codes if c in all_funds]
        if not cards:
            continue
        blocks.append(f'''<div class="category-block" data-category="{category}">
          <div class="category-title">{category}</div>
          <div class="fund-grid">{''.join(cards)}</div>
        </div>''')
    return "\n".join(blocks)


def main():
    all_funds = collect_all_funds()
    market = collect_market_data()
    news = fetch_news()

    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(
            {"funds": all_funds, "market": market, "news": news},
            f, ensure_ascii=False, indent=2, default=str,
        )

    with open("template.html", encoding="utf-8") as f:
        html = f.read()

    now = dt.datetime.now()
    date_line = now.strftime("%d.%m.%Y %H:%M") + " · Otomatik güncelleme"

    html = (
        html.replace("{{DATE_LINE}}", date_line)
        .replace("{{TICKER_HTML}}", render_ticker(market))
        .replace("{{CATEGORIZED_FUNDS_HTML}}", render_categorized_funds(all_funds))
        .replace("{{CATEGORY_OPTIONS_HTML}}", render_category_options())
        .replace("{{NEWS_HTML}}", render_news(news))
        .replace("{{GENERATED_AT}}", now.strftime("%d.%m.%Y %H:%M"))
    )

    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)


if __name__ == "__main__":
    main()
