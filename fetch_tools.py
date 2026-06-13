#!/usr/bin/env python3
"""
fetch_tools.py — Veille quotidienne outils IA (uneiaparjour.fr)

Sources actives :
  ✓ Product Hunt       — RSS officiel (fiable)
  ✓ Hacker News        — API Algolia show_hn (fiable)
  ✓ Aixploria          — WP REST API (fiable depuis GitHub Actions)
  ✓ FutureTools        — Scraping RSC Next.js (4000+ outils, pricing_tier)
  ✓ There's an AI      — Scraping HTML /?sort=new (pricing)
  ✓ AI Secret          — RSS Ghost + scraping articles (newsletter IA)
  ✓ Ben's Bites        — RSS Beehiiv (newsletter IA)
  ✓ The Rundown AI     — RSS newsletter (newsletter IA)
  ✓ TLDR AI            — RSS newsletter (newsletter IA)
  ✓ TechCrunch AI      — RSS catégorie AI
  ✓ GitHub Trending    — RSS tiers (repos trending, filtrés IA)
  ✓ Lobsters AI        — RSS tag AI
"""
import json, re, sys
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FuturesTimeout
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

import requests
import feedparser
from bs4 import BeautifulSoup

# ── Config ─────────────────────────────────────────────────────────────────────

CUTOFF_HOURS = 168   # 7 jours
OUTPUT_FILE  = "tools.json"

HEADERS = {
    "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection":      "keep-alive",
    "DNT":             "1",
}

# ── Catégories ─────────────────────────────────────────────────────────────────

CATEGORIES_KW = {
    "images":            ["image","photo","illustration","visual","artwork","dall-e","midjourney","stable diffusion","flux","picture","generate image"],
    "vidéo":             ["video","vidéo","clip","film","animation","cinematic","reel","short"],
    "voix":              ["voice","speech","tts","text-to-speech","narration","speak","clone","podcast"],
    "musique":           ["music","musique","audio","melody","song","beat","compose","suno","udio"],
    "chatbot":           ["chat","chatbot","conversation","assistant","dialogue","bot"],
    "texte":             ["text","texte","writing","copywriting","article","blog","content","paraphrase","rewrite"],
    "documents":         ["document","pdf","file","report","contract","extract","summarize"],
    "éducation":         ["education","learning","teaching","student","teacher","quiz","flashcard","cours","tuteur","e-learning"],
    "automatisation":    ["automation","workflow","integration","pipeline","no-code","zapier","make","n8n","agentic","agent"],
    "présentation":      ["presentation","slides","powerpoint","deck","pitch"],
    "recherche":         ["search","research","veille","academic","papers","arxiv","perplexity"],
    "données":           ["data","analytics","chart","csv","excel","visualization","statistics","dataset","spreadsheet"],
    "LLM":               ["llm","language model","llama","mistral","open weights","fine-tun","rag"],
    "open source":       ["open source","open-source","github","hugging face","local model","self-host"],
    "site web":          ["website","landing page","web app","builder","no-code site","html","portfolio"],
    "images 3D":         ["3d","three-dimensional","blender","render","3d model","texture"],
    "mindmap":           ["mindmap","mind map","brainstorm","diagram","concept map"],
    "infographie":       ["infographic","infographie","design","poster","banner","canva","flyer"],
    "langues":           ["translation","traduction","multilingual","language","subtitle","caption"],
    "bande dessinée":    ["comic","manga","bd","strip","graphic novel"],
    "histoires enfants": ["kids","children","enfant","story","conte","jeunesse"],
    "navigateur":        ["browser","extension","chrome","firefox","plugin browsing"],
    "jeu vidéo":         ["game","gaming","rpg","level","character","asset","npc"],
    "youtube":           ["youtube","yt","channel","transcript","video summary"],
    "qr code":           ["qr","qr code","qrcode"],
    "quiz et flashcards":["quiz","flashcard","revision","memorization","anki","mcq"],
    "application":       ["mobile app","ios","android","app store"],
    "sans compte":       ["no login","no signup","no account","without account"],
    "usage illimité":    ["unlimited","illimité","no limit","infinite"],
    "actualités":        ["news","actualités","fact-check","journalism"],
}

DIRECTORY_DOMAINS = {
    "theresanaiforthat.com","free.theresanaiforthat.com","futurepedia.io","aiscout.net",
    "aiapp.fr","iaweb.fr","openfuture.ai","ailibrary.io","wikiaitools.com","toolscout.ai",
    "hdrobots.com","toolspedia.io","madgenius.co","aioftheday.com","aitoolboard.com",
    "aitools.lol","aitools.fyi","ai-finder.net","aitoolhunt.com","aitoolnet.com","dang.ai",
    "toolsstory.net","free-ai-tools-directory.com","aitoolguru.com","noteableai.com",
    "faind.ai","aicenter.ai","bestfreeaiwebsites.com","fastpedia.io","bestofai.com",
    "futuretools.io","aixploria.com","aisecret.us","aitoolsdirectory.com",
    "powerfulai.tools","aitoptools.com","aitools.sh","toolify.ai",
    "producthunt.com","therundown.ai","beehiiv.com","substack.com",
    "bensbites.com","tldr.tech","ycombinator.com","algolia.com",
    "reddit.com","redd.it","github.com","lobste.rs","dev.to",
    "techcrunch.com","venturebeat.com",
    "futuretools.link",
}

# ── Pricing ────────────────────────────────────────────────────────────────────

FREE_KW = [
    "free","gratuit","no cost","open source","open-source",
    "100% free","completely free","always free",
]
FREEMIUM_KW = [
    "freemium","free plan","free tier","free trial","free version",
    "free +","basic free","starter free",
]

def guess_pricing(text):
    low = text.lower()
    if any(kw in low for kw in FREEMIUM_KW):
        return "freemium"
    if any(kw in low for kw in FREE_KW):
        return "free"
    return "unknown"

# ── Utilitaires ────────────────────────────────────────────────────────────────

def guess_categories(text):
    low = text.lower()
    seen, hits = set(), []
    for cat, kws in CATEGORIES_KW.items():
        if cat not in seen and any(kw in low for kw in kws):
            hits.append(cat); seen.add(cat)
    return hits[:3]

def norm_url(url):
    url = url.strip()
    return url if url.startswith("http") else "https://" + url

def parse_date(s):
    if not s:
        return None
    for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%Y-%m-%dT%H:%M:%S%z",
                "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d"):
        try:
            return datetime.strptime(s.strip(), fmt).isoformat()
        except Exception:
            pass
    return None

def is_recent(date_iso):
    if not date_iso:
        return True
    try:
        dt = datetime.fromisoformat(date_iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt >= datetime.now(timezone.utc) - timedelta(hours=CUTOFF_HOURS)
    except Exception:
        return True

def is_external(url):
    if not url or not url.startswith("http"):
        return False
    domain = urlparse(url).netloc.lower().lstrip("www.")
    return not any(d in domain for d in DIRECTORY_DOMAINS)

def make_tool(name, url, desc, source, date_iso=None, pricing=None):
    combined = name + " " + (desc or "")
    return {
        "name":        name[:100].strip(),
        "tool_url":    norm_url(url),
        "description": re.sub(r"\s+", " ", (desc or "")[:400]).strip(),
        "source":      source,
        "date_iso":    date_iso or datetime.now(timezone.utc).isoformat(),
        "categories":  guess_categories(combined),
        "pricing":     pricing or guess_pricing(combined),
    }

def get_json(url, referer=None, timeout=12):
    hdrs = dict(HEADERS)
    hdrs["Accept"] = "application/json, */*"
    if referer:
        hdrs["Referer"] = referer
    r = requests.get(url, headers=hdrs, timeout=timeout)
    r.raise_for_status()
    return r.json()

def fetch_rss(source_name, rss_url, ai_filter=False, max_items=30):
    results = []
    try:
        feed = feedparser.parse(rss_url, request_headers={
            "User-Agent": HEADERS["User-Agent"],
            "Accept": "application/rss+xml, application/xml, text/xml, */*",
        })
        if not feed.entries:
            raise Exception(f"0 entrées (bozo={feed.bozo})")
        for entry in feed.entries[:max_items]:
            title    = entry.get("title","").strip()
            url      = entry.get("link","")
            summary  = entry.get("summary","") or entry.get("description","")
            desc     = BeautifulSoup(summary, "html.parser").get_text(" ", strip=True)
            date_iso = parse_date(entry.get("published") or entry.get("updated",""))
            if not title or not url or not is_recent(date_iso):
                continue
            if ai_filter:
                combined = (title + " " + desc).lower()
                ai_kw = ["ai","artificial intelligence","machine learning","llm","gpt",
                         "generative","automation","chatbot","image generation","voice","neural"]
                if not any(kw in combined for kw in ai_kw):
                    continue
            results.append(make_tool(title, url, desc, source_name, date_iso))
        print(f"  {source_name} (RSS): {len(results)}")
    except Exception as e:
        print(f"  {source_name} RSS erreur: {e}", file=sys.stderr)
    return results

# ── Sources actives ────────────────────────────────────────────────────────────

def fetch_producthunt():
    """Product Hunt AI — RSS officiel."""
    results = []
    try:
        feed = feedparser.parse(
            "https://www.producthunt.com/feed?category=artificial-intelligence",
            request_headers={
                "User-Agent": HEADERS["User-Agent"],
                "Accept": "application/rss+xml, application/xml, text/xml, */*",
            }
        )
        if not feed.entries:
            raise Exception(f"0 entrées (bozo={feed.bozo})")

        for entry in feed.entries[:30]:
            title    = entry.get("title","").strip()
            ph_url   = entry.get("link","")
            summary  = entry.get("summary","") or entry.get("description","")
            date_iso = parse_date(entry.get("published") or entry.get("updated",""))

            if not title or not is_recent(date_iso):
                continue

            combined = (title + " " + BeautifulSoup(summary,"html.parser").get_text()).lower()
            ai_kw = ["ai","artificial intelligence","machine learning","llm","gpt",
                     "generative","automation","chatbot","image","voice","neural","agent"]
            if not any(kw in combined for kw in ai_kw):
                continue

            tool_url = None
            if summary:
                desc_soup = BeautifulSoup(summary, "html.parser")
                for a in desc_soup.find_all("a", href=True):
                    href = a["href"].strip()
                    if href.startswith("http") and is_external(href):
                        tool_url = href
                        break

            if not tool_url:
                tool_url = ph_url

            desc = BeautifulSoup(summary, "html.parser").get_text(" ", strip=True)
            desc = re.sub(r"Discussion\s*\|\s*Link", "", desc).strip()

            results.append(make_tool(title, tool_url, desc, "Product Hunt", date_iso))

        print(f"  Product Hunt (RSS): {len(results)}")
    except Exception as e:
        print(f"  Product Hunt erreur: {e}", file=sys.stderr)
    return results


def fetch_hackernews():
    """Hacker News — show_hn via API Algolia."""
    results = []
    AI_TITLE_KW = [
        "ai","gpt","llm","llama","claude","gemini","generative","neural",
        "image","voice","speech","chatbot","agent","automat","ml",
        "machine learning","diffusion","embedding","rag","copilot",
        "openai","anthropic","mistral","model","assistant","bot",
    ]
    ARTICLE_KW = ["the case for","my experience","deep dive","state of the"]
    try:
        cutoff_ts = int((datetime.now(timezone.utc) - timedelta(hours=CUTOFF_HOURS)).timestamp())
        data = get_json(
            "https://hn.algolia.com/api/v1/search_by_date"
            f"?tags=show_hn"
            f"&numericFilters=created_at_i>{cutoff_ts}"
            f"&hitsPerPage=50"
        )
        seen = set()
        for hit in data.get("hits", []):
            title = hit.get("title","").strip()
            url   = hit.get("url","")
            if not title or not url:
                continue
            if "ycombinator.com" in url:
                continue
            url_low = url.lower()
            if any(x in url_low for x in ["/blog/","/posts/","/post/","/article/","/news/",".md","/wiki/"]):
                continue
            title_low = title.lower()
            if not any(kw in title_low for kw in AI_TITLE_KW):
                continue
            if any(kw in title_low for kw in ARTICLE_KW):
                continue
            if url in seen:
                continue
            seen.add(url)
            date_iso = datetime.fromtimestamp(hit.get("created_at_i",0), tz=timezone.utc).isoformat()
            name = re.sub(r"^show hn\s*[:\-–]\s*", "", title, flags=re.I)[:80]
            results.append(make_tool(name, url, "", "Hacker News", date_iso))
        results = results[:20]
        print(f"  Hacker News Show HN: {len(results)}")
    except Exception as e:
        print(f"  Hacker News erreur: {e}", file=sys.stderr)
    return results


def fetch_aixploria():
    """Aixploria — WP REST API avec extraction URL réelle."""
    results = []
    try:
        data = get_json(
            "https://www.aixploria.com/wp-json/wp/v2/posts"
            "?per_page=20&orderby=date&_fields=title,link,content,excerpt,date",
            referer="https://www.aixploria.com/"
        )
        for post in data:
            title    = BeautifulSoup(post.get("title",{}).get("rendered",""), "html.parser").get_text().strip()
            date_iso = parse_date(post.get("date",""))
            if not title or not is_recent(date_iso):
                continue
            content_html = post.get("content",{}).get("rendered","")
            content_soup = BeautifulSoup(content_html, "html.parser")
            tool_url = None
            for a in content_soup.find_all("a", href=True):
                href = a["href"].strip()
                if href.startswith("http") and is_external(href):
                    tool_url = href; break
            if not tool_url:
                tool_url = post.get("link","")
                if not tool_url:
                    continue
            excerpt = BeautifulSoup(
                post.get("excerpt",{}).get("rendered",""), "html.parser"
            ).get_text(" ", strip=True)
            if not excerpt.strip():
                excerpt = content_soup.get_text(" ", strip=True)[:300]
            results.append(make_tool(title, tool_url, excerpt, "Aixploria", date_iso))
        print(f"  Aixploria (WP API): {len(results)}")
    except Exception as e:
        print(f"  Aixploria WP API erreur: {e}", file=sys.stderr)
        results = fetch_rss("Aixploria", "https://www.aixploria.com/feed/")
    return results


def fetch_futuretools():
    """FutureTools — extraction des données embarquées dans le RSC payload Next.js."""
    results = []
    try:
        r = requests.get("https://futuretools.io/tools", headers=HEADERS, timeout=30)
        r.raise_for_status()

        scripts = re.findall(r"<script>(self\.__next_f\.push.*?)</script>", r.text, re.S)
        big_script = ""
        for s in scripts:
            if len(s) > 100000:
                big_script = s
                break

        if not big_script:
            raise Exception(f"Payload RSC non trouvé ({len(scripts)} scripts, page {len(r.text)} chars)")

        tool_pattern = (
            r'\\"slug\\":\\"([^\\]+)\\",'
            r'\\"name\\":\\"([^\\]+)\\",'
            r'\\"description_short\\":\\"([^\\]*?)\\",'
            r'\\"website_url\\":\\"([^\\]*?)\\"'
        )
        tools_raw = re.findall(tool_pattern, big_script)

        pricing_map = {}
        for m in re.finditer(r'\\"slug\\":\\"([^\\]+)\\".*?\\"pricing_tier\\":\\"([^\\]+)\\"', big_script):
            pricing_map[m.group(1)] = m.group(2)

        dates_map = {}
        for m in re.finditer(r'\\"slug\\":\\"([^\\]+)\\".*?\\"published_at\\":\\"([^\\]+)\\"', big_script):
            dates_map[m.group(1)] = m.group(2)

        for slug, name, desc, website_url in tools_raw:
            date_iso = dates_map.get(slug, "")
            if not is_recent(date_iso):
                continue
            pricing_raw = pricing_map.get(slug, "unknown")
            pricing = {"free": "free", "freemium": "freemium", "paid": "paid"}.get(pricing_raw, "unknown")
            clean_url = website_url.replace("\\/", "/")
            results.append(make_tool(
                name.replace('\\"', '"'),
                clean_url,
                desc.replace('\\"', '"'),
                "FutureTools",
                date_iso,
                pricing=pricing,
            ))

        print(f"  FutureTools (RSC): {len(results)}")
    except Exception as e:
        print(f"  FutureTools erreur: {e}", file=sys.stderr)
    return results


def fetch_taaft():
    """There's an AI for That — scraping HTML de la page d'accueil /?sort=new."""
    results = []
    try:
        hdrs = dict(HEADERS)
        hdrs["Referer"] = "https://theresanaiforthat.com/"
        r = requests.get(
            "https://theresanaiforthat.com/?sort=new",
            headers=hdrs, timeout=20
        )
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        link_wraps = soup.find_all(class_="ai_link_wrap")
        avail_starts = soup.find_all(class_="available_starting")

        if not link_wraps:
            print(f"  There's an AI: 0 éléments HTML trouvés (page {len(r.text)} chars)", file=sys.stderr)

        for i in range(min(len(link_wraps), len(avail_starts))):
            lw = link_wraps[i]
            av = avail_starts[i]

            name_el = lw.find(class_="ai_link")
            if not name_el:
                continue
            name = name_el.get_text(strip=True)
            if not name or len(name) < 3:
                continue

            ext_link = lw.find(class_="external_ai_link")
            tool_url = ext_link.get("href", "") if ext_link else ""
            if not tool_url:
                tool_url = name_el.get("href", "")
            if not tool_url:
                continue

            price_el = av.find(class_="ai_launch_date")
            price_text = price_el.get_text(strip=True) if price_el else ""

            if "free +" in price_text.lower() or "free+" in price_text.lower():
                pricing = "freemium"
            elif price_text.lower().startswith("free") or price_text.lower() == "free":
                pricing = "free"
            elif "$" in price_text or "€" in price_text or price_text.lower().startswith("from"):
                pricing = "paid"
            else:
                pricing = "unknown"

            rel_date_el = av.find(class_="relative")
            rel_text = rel_date_el.get_text(strip=True) if rel_date_el else ""
            date_iso = _relative_to_iso(rel_text)

            tool_url_clean = re.sub(r"[?&](?:ref|utm_\w+)=[^&]*", "", tool_url).rstrip("?&")

            results.append(make_tool(name, tool_url_clean, "", "There's an AI", date_iso, pricing=pricing))

        print(f"  There's an AI (HTML): {len(results)}")
    except Exception as e:
        print(f"  There's an AI erreur: {e}", file=sys.stderr)
    return results


def _relative_to_iso(text):
    """Convertit '5h ago', '2d ago', '20h ago' en ISO."""
    now = datetime.now(timezone.utc)
    m = re.match(r"(\d+)\s*([mhdw])", text.lower())
    if not m:
        return now.isoformat()
    val, unit = int(m.group(1)), m.group(2)
    delta = {"m": timedelta(minutes=val), "h": timedelta(hours=val),
             "d": timedelta(days=val), "w": timedelta(weeks=val)}.get(unit, timedelta())
    return (now - delta).isoformat()


def fetch_aisecret():
    """AI Secret — RSS Ghost pour les URLs puis scraping des articles."""
    results = []
    SOCIAL = ["twitter.com","x.com","linkedin.com","youtube.com",
              "facebook.com","instagram.com","threads.net"]
    try:
        feed = feedparser.parse("https://aisecret.us/rss/", request_headers={
            "User-Agent": HEADERS["User-Agent"],
        })
        if not feed.entries:
            raise Exception("0 entrées RSS")

        for entry in feed.entries[:5]:
            date_iso = parse_date(entry.get("published") or entry.get("updated",""))
            if not is_recent(date_iso):
                continue
            article_url = entry.get("link", "")
            if not article_url:
                continue

            try:
                r = requests.get(article_url, headers=HEADERS, timeout=15)
                r.raise_for_status()
                soup = BeautifulSoup(r.text, "html.parser")
                content = soup.find(class_="gh-content")
                if not content:
                    continue

                for a in content.find_all("a", href=True):
                    href = a["href"].strip()
                    text = a.get_text(strip=True)
                    if not href.startswith("http") or len(text) < 4:
                        continue
                    low = href.lower()
                    if any(s in low for s in SOCIAL):
                        continue
                    domain = urlparse(href).netloc.lower()
                    if "aisecret" in domain or "ghost" in domain:
                        continue
                    results.append(make_tool(text, href, "", "AI Secret", date_iso))
            except Exception:
                continue

        print(f"  AI Secret (scraping): {len(results)}")
    except Exception as e:
        print(f"  AI Secret erreur: {e}", file=sys.stderr)
    return results


def fetch_bensbites():
    """Ben's Bites — RSS Beehiiv, filtré IA."""
    return fetch_rss("Ben's Bites", "https://www.bensbites.com/feed", ai_filter=True, max_items=20)


def fetch_rundown():
    """The Rundown AI — RSS newsletter."""
    return fetch_rss("The Rundown AI", "https://www.therundown.ai/feed", ai_filter=False, max_items=20)


def fetch_tldr_ai():
    """TLDR AI — RSS newsletter."""
    return fetch_rss("TLDR AI", "https://tldr.tech/ai/rss", ai_filter=False, max_items=20)


def fetch_techcrunch_ai():
    """TechCrunch AI — RSS catégorie AI, filtré lancements/outils."""
    results = []
    try:
        feed = feedparser.parse(
            "https://techcrunch.com/category/artificial-intelligence/feed/",
            request_headers={"User-Agent": HEADERS["User-Agent"]}
        )
        TOOL_KW = ["launch","release","introduces","unveils","announces","rolls out",
                    "new tool","new app","now available","open source","startup"]
        for entry in feed.entries[:20]:
            title    = entry.get("title","").strip()
            url      = entry.get("link","")
            summary  = entry.get("summary","") or ""
            desc     = BeautifulSoup(summary, "html.parser").get_text(" ", strip=True)
            date_iso = parse_date(entry.get("published") or entry.get("updated",""))
            if not title or not is_recent(date_iso):
                continue
            combined = (title + " " + desc).lower()
            if not any(kw in combined for kw in TOOL_KW):
                continue
            results.append(make_tool(title, url, desc, "TechCrunch AI", date_iso))
        print(f"  TechCrunch AI (RSS): {len(results)}")
    except Exception as e:
        print(f"  TechCrunch AI erreur: {e}", file=sys.stderr)
    return results


def fetch_github_trending():
    """GitHub Trending — RSS tiers, filtrés IA."""
    return fetch_rss("GitHub Trending", "https://mshibanami.github.io/GitHubTrendingRSS/daily/all.xml",
                     ai_filter=True, max_items=15)


def fetch_lobsters():
    """Lobsters — RSS tag AI."""
    results = []
    try:
        feed = feedparser.parse("https://lobste.rs/t/ai.rss", request_headers={
            "User-Agent": HEADERS["User-Agent"],
        })
        TOOL_KW = ["launch","release","introducing","built","show","open source",
                    "tool","app","library","framework","model","demo"]
        for entry in feed.entries[:25]:
            title    = entry.get("title","").strip()
            url      = entry.get("link","")
            date_iso = parse_date(entry.get("published") or entry.get("updated",""))
            if not title or not url or not is_recent(date_iso):
                continue
            if not any(kw in title.lower() for kw in TOOL_KW):
                continue
            results.append(make_tool(title, url, "", "Lobsters", date_iso))
        print(f"  Lobsters AI (RSS): {len(results)}")
    except Exception as e:
        print(f"  Lobsters erreur: {e}", file=sys.stderr)
    return results


# ── Main ───────────────────────────────────────────────────────────────────────

FETCHERS = [
    fetch_producthunt,
    fetch_hackernews,
    fetch_aixploria,
    fetch_futuretools,
    fetch_taaft,
    fetch_aisecret,
    fetch_bensbites,
    fetch_rundown,
    fetch_tldr_ai,
    fetch_techcrunch_ai,
    fetch_github_trending,
    fetch_lobsters,
]

def deduplicate(tools):
    seen_urls, seen_names, out = set(), set(), []
    for t in tools:
        uk = t["tool_url"].rstrip("/").lower()
        nk = re.sub(r"[\s\-_]","", t["name"].lower())
        if uk in seen_urls or nk in seen_names:
            continue
        seen_urls.add(uk); seen_names.add(nk)
        out.append(t)
    return out

def run_fetcher(fn):
    try:
        return fn.__name__, fn()
    except Exception as e:
        print(f"  Erreur {fn.__name__}: {e}", file=sys.stderr)
        return fn.__name__, []

def main():
    print(f"Veille IA — {datetime.now().strftime('%Y-%m-%d %H:%M')} — {len(FETCHERS)} sources\n")
    all_tools = []
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(run_fetcher, fn): fn.__name__ for fn in FETCHERS}
        for future in as_completed(futures):
            try:
                _name, results = future.result(timeout=90)
                all_tools.extend(results)
            except FuturesTimeout:
                print(f"  Timeout: {futures[future]}", file=sys.stderr)
            except Exception as e:
                print(f"  Erreur future {futures[future]}: {e}", file=sys.stderr)

    all_tools = deduplicate(all_tools)
    all_tools.sort(key=lambda t: t.get("date_iso",""), reverse=True)
    all_tools = [t for t in all_tools if len(t["name"].strip()) >= 3]

    stats = {}
    for t in all_tools:
        stats[t["source"]] = stats.get(t["source"], 0) + 1
    print("\nPar source :")
    for src, count in sorted(stats.items(), key=lambda x: -x[1]):
        print(f"  {src:25s}: {count}")

    pricing_stats = {}
    for t in all_tools:
        p = t.get("pricing", "unknown")
        pricing_stats[p] = pricing_stats.get(p, 0) + 1
    print(f"\nPricing : {pricing_stats}")

    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "count":        len(all_tools),
        "tools":        all_tools,
    }
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\nTotal : {len(all_tools)} outils — {OUTPUT_FILE} mis à jour")

if __name__ == "__main__":
    main()
