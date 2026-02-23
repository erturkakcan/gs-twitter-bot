import os
import json
import re
from difflib import SequenceMatcher

import feedparser
import requests
from requests_oauthlib import OAuth1

# --- X API Keys (KODA YAZMA: env'den al) ---
API_KEY = os.getenv("X_API_KEY")
API_SECRET = os.getenv("X_API_SECRET")
ACCESS_TOKEN = os.getenv("X_ACCESS_TOKEN")
ACCESS_TOKEN_SECRET = os.getenv("X_ACCESS_TOKEN_SECRET")

if not all([API_KEY, API_SECRET, ACCESS_TOKEN, ACCESS_TOKEN_SECRET]):
    raise SystemExit(
        "Eksik environment variable: X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, X_ACCESS_TOKEN_SECRET"
    )

auth = OAuth1(API_KEY, API_SECRET, ACCESS_TOKEN, ACCESS_TOKEN_SECRET)

STATE_FILE = "posted.json"

# RSS kaynakları
FEEDS = [
    # Resmi
    "https://www.galatasaray.org/rss",
    # Fotomaç GS
    "https://www.fotomac.com.tr/rss/Galatasaray.xml",
    # NTV Spor Futbol (GS haberleri düşer)
    "https://www.ntvspor.net/rss/kategori/futbol",
    # A Spor Anasayfa (GS haberleri düşer)
    "https://www.aspor.com.tr/rss/anasayfa.xml",
]

KEYWORDS = [
    "galatasaray", "g.saray", "g saray", "gs", "cimbom", "sarı-kırmızılı", "sari-kirmizili"
]

SIMILARITY_THRESHOLD = 0.85  # benzer başlıkları eleme eşiği


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"titles": []}


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def normalize_title(t: str) -> str:
    t = t.lower().strip()
    t = re.sub(r"\s+", " ", t)
    t = re.sub(r"[“”\"'’`]", "", t)
    return t


def is_gs_related(title: str) -> bool:
    t = normalize_title(title)
    return any(k in t for k in KEYWORDS)


def is_similar(a: str, b: str) -> bool:
    return SequenceMatcher(None, normalize_title(a), normalize_title(b)).ratio() >= SIMILARITY_THRESHOLD


def already_shared(title: str, state) -> bool:
    for old in state["titles"]:
        if is_similar(title, old):
            return True
    return False


def source_from_feed(feed_url: str) -> str:
    if "galatasaray.org" in feed_url:
        return "Galatasaray.org"
    if "fotomac.com.tr" in feed_url:
        return "Fotomaç"
    if "ntvspor.net" in feed_url:
        return "NTV Spor"
    if "aspor.com.tr" in feed_url:
        return "A Spor"
    return "Kaynak"


def pick_news(state):
    for feed_url in FEEDS:
        d = feedparser.parse(feed_url)
        for e in getattr(d, "entries", [])[:30]:
            title = getattr(e, "title", "").strip()
            if not title:
                continue
            if not is_gs_related(title):
                continue
            if already_shared(title, state):
                continue
            return title, source_from_feed(feed_url)
    return None, None


def compose_post(title: str, source: str) -> str:
    # Linksiz / hashtagsiz / tarihsiz
    title = title.strip()
    if len(title) > 240:
        title = title[:237] + "..."
    text = f"{title}\nKaynak: {source}"
    if len(text) > 280:
        # nadir; yine kısalt
        overflow = len(text) - 280
        title2 = (title[:-overflow-3] + "...") if overflow + 3 < len(title) else title[:200]
        text = f"{title2}\nKaynak: {source}"
    return text


def post_to_x(text: str):
    url = "https://api.x.com/2/tweets"
    r = requests.post(url, auth=auth, json={"text": text}, timeout=30)
    if r.status_code >= 300:
        raise RuntimeError(f"X API error {r.status_code}: {r.text}")
    return r.json()


def main():
    state = load_state()

    title, source = pick_news(state)
    if not title:
        print("Yeni GS haberi yok.")
        return

    text = compose_post(title, source)
    out = post_to_x(text)
    print("Paylaşıldı:", out)

    state["titles"].append(title)
    state["titles"] = state["titles"][-250:]  # şişmesin
    save_state(state)


if __name__ == "__main__":
    main()
