#!/usr/bin/env python3
"""
fetch_tools.py — Veille quotidienne outils IA (uneiaparjour.fr)

Sources et stratégies :
  ✓ Product Hunt       — RSS officiel (fiable)
  ✓ Hacker News        — API Algolia (pas d'auth, pas de rate limit strict)
  ✓ Aixploria          — WP REST API
  ✓ aiapp.fr           — WP REST API
  ✓ iaweb.fr           — WP REST API
  ✓ WikiAI Tools       — WP REST API
  ✓ Notable AI         — WP REST API
  ✓ AI Tool Guru       — WP REST API
  ✓ HD Robots          — WP REST API
  ✓ Tools Story        — WP REST API
  ✓ Free AI Tools Dir. — WP REST API
  ✓ Mad Genius         — WP REST API
  ✓ AI Tools LOL       — WP REST API
  ✓ AI Finder          — WP REST API
  ✓ AI Tool Hunt       — WP REST API
  ✓ AI Tool Board      — WP REST API
  ✓ Fastpedia          — WP REST API
  ✓ BetaList           — RSS lancements produits filtrés IA
  ✓ GitHub AI Topics   — Atom feed public (repositories IA récents)
  ✓ Reddit r/aitools   — JSON API public

  ✗ AI Secret          — 403 depuis IPs GitHub Actions (Cloudflare)
  ✗ AI Top Tools       — 403 depuis IPs GitHub Actions (Cloudflare)
  ✗ There's an AI      — 403 depuis IPs GitHub Actions
  ✗ The Rundown AI     — 403 depuis IPs GitHub Actions (Beehiiv)
  ✗ Best Free AI       — 403 depuis IPs GitHub Actions
  ✗ Best of AI         — 403 depuis IPs GitHub Actions
  ✗ futuretools.io     — Cloudflare IP block
  ✗ powerfulai.tools   — Cloudflare IP block
  ✗ toolify.ai         — Cloudflare IP block
  ✗ aitoolsdirectory   — Cloudflare IP block
  ✗ aitools.sh         — Cloudflare IP block
"""
import json, re, time, sys
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FuturesTimeout
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin, urlparse

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
    "reddit.com","redd.it","github.com",
}

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

def make_tool(name, url, desc, source, date_iso=None):
    return {
        "name":        name[:100].strip(),
        "tool_url":    norm_url(url),
        "description": re.sub(r"\s+", " ", (desc or "")[:400]).strip(),
        "source":      source,
        "date_iso":    date_iso or datetime.now(timezone.utc).isoformat(),
        "categories":  guess_categories(name + " " + (desc or "")),
    }

def get_html(url, referer=None):
    hdrs = dict(HEADERS)
    if referer:
        hdrs["Referer"] = referer
    r = requests.get(url, headers=hdrs, timeout=6)
    r.raise_for_status()
    return BeautifulSoup(r.text, "html.parser")

def get_json(url, referer=None):
    hdrs = dict(HEADERS)
    hdrs["Accept"] = "application/json, */*"
    if referer:
        hdrs["Referer"] = referer
    r = requests.get(url, headers=hdrs, timeout=6)
    r.raise_for_status()
    return r.json()

def fetch_rss(source_name, rss_url, ai_filter=False, max_items=30):
    """Fetch RSS — accepte les feeds bozo (malformés mais parsables)."""
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

# ── Helpers WP REST API et scraping ───────────────────────────────────────────

def _wp_api_tools(source_name, base_url, per_page=20):
    """Helper générique WP REST API : extrait l'URL réelle de l'outil depuis le content."""
    results = []
    try:
        data = get_json(
            f"{base_url}/wp-json/wp/v2/posts"
            f"?per_page={per_page}&orderby=date&_fields=title,link,content,excerpt,date",
            referer=base_url + "/"
        )
        if not isinstance(data, list):
            raise Exception("Réponse non-liste")
        for post in data:
            title    = BeautifulSoup(post.get("title",{}).get("rendered",""), "html.parser").get_text().strip()
            date_iso = parse_date(post.get("date",""))
            if not title or not is_recent(date_iso):
                continue
            content_html = post.get("content",{}).get("rendered","")
            soup2        = BeautifulSoup(content_html, "html.parser")
            tool_url     = None
            for a in soup2.find_all("a", href=True):
                href = a["href"].strip()
                if href.startswith("http") and is_external(href):
                    tool_url = href; break
            if not tool_url:
                tool_url = post.get("link","")
            excerpt = BeautifulSoup(
                post.get("excerpt",{}).get("rendered",""), "html.parser"
            ).get_text(" ", strip=True)
            if not excerpt:
                excerpt = soup2.get_text(" ", strip=True)[:300]
            results.append(make_tool(title, tool_url, excerpt, source_name, date_iso))
        print(f"  {source_name} (WP API): {len(results)}")
    except Exception as e:
        print(f"  {source_name} WP API erreur: {e}", file=sys.stderr)
        results = fetch_rss(source_name, f"{base_url}/feed/")
    return results

def _scrape_cards_simple(source_name, url, base, card_sel, name_sel, desc_sel, max_items=20):
    """Helper scraping générique."""
    results, seen = [], set()
    try:
        page = get_html(url, referer=base)
        for card in page.select(card_sel)[:max_items * 3]:
            ne   = card.select_one(name_sel) if name_sel else card
            name = ne.get_text(strip=True)[:80] if ne else ""
            if not name or len(name) < 3:
                continue
            ext_url = int_url = None
            a_tags  = ([card] if card.name == "a" else []) + card.find_all("a", href=True)
            for a in a_tags:
                full = urljoin(base, a.get("href",""))
                if full and is_external(full) and not ext_url:
                    ext_url = full
                elif full and not int_url:
                    int_url = full
            tool_url = ext_url or int_url or url
            if tool_url in seen:
                continue
            seen.add(tool_url)
            desc = ""
            if desc_sel:
                de = card.select_one(desc_sel)
                desc = de.get_text(" ", strip=True)[:300] if de else ""
            results.append(make_tool(name, tool_url, desc, source_name))
            if len(results) >= max_items:
                break
        print(f"  {source_name} (HTML): {len(results)}")
    except Exception as e:
        print(f"  {source_name} HTML erreur: {e}", file=sys.stderr)
    return results

def _multi_strategy(source_name, base_url, scrape_url=None, api_paths=None):
    """Helper universel : essaie WP API, puis RSS /feed/, puis API JSON, puis scraping HTML."""
    res = _wp_api_tools(source_name, base_url)
    if res: return res
    res = fetch_rss(source_name, base_url.rstrip("/") + "/feed/")
    if res: return res
    for path in (api_paths or []):
        try:
            data  = get_json(base_url.rstrip("/") + path)
            items = data if isinstance(data, list) else (
                data.get("tools") or data.get("data") or data.get("results") or []
            )
            results = []
            for item in items[:20]:
                name = (item.get("name") or item.get("title") or "").strip()
                url  = item.get("url") or item.get("website") or item.get("link","")
                desc = item.get("description") or ""
                date_iso = parse_date(item.get("createdAt") or item.get("date",""))
                if name and url:
                    results.append(make_tool(name, url, desc, source_name, date_iso))
            if results:
                print(f"  {source_name} (API): {len(results)}")
                return results
        except Exception: pass
    return _scrape_cards_simple(
        source_name,
        scrape_url or (base_url.rstrip("/") + "/"),
        base_url,
        "article,.tool,.card,[class*='tool'],[class*='card'],[class*='item'],[class*='post']",
        "h2,h3,h4,.title,.name,strong",
        "p,.desc,.description,.excerpt,.summary"
    )

# ── Sources actives ────────────────────────────────────────────────────────────

def fetch_producthunt():
    """Product Hunt AI — RSS officiel.
    Le lien dans le flux RSS pointe vers producthunt.com/products/xxx.
    On parse le HTML de la description pour extraire l'URL réelle du produit."""
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
    """Hacker News — tag show_hn uniquement via API Algolia."""
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
    """Aixploria — WP REST API avec content pour extraire l'URL réelle de l'outil."""
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
                    tool_url = href
                    break
            if not tool_url:
                tool_url = post.get("link","")
                if not tool_url:
                    continue
            excerpt = BeautifulSoup(post.get("excerpt",{}).get("rendered",""), "html.parser").get_text(" ", strip=True)
            if not excerpt.strip():
                excerpt = content_soup.get_text(" ", strip=True)[:300]
            results.append(make_tool(title, tool_url, excerpt, "Aixploria", date_iso))
        print(f"  Aixploria (WP API): {len(results)}")
    except Exception as e:
        print(f"  Aixploria WP API erreur: {e}", file=sys.stderr)
        results = fetch_rss("Aixploria", "https://www.aixploria.com/feed/")
    return results

# ── Sources WP REST API (même logique qu'Aixploria) ───────────────────────────

def fetch_aiapp_fr():
    return _wp_api_tools("aiapp.fr", "https://aiapp.fr")

def fetch_iaweb_fr():
    return _wp_api_tools("iaweb.fr", "https://iaweb.fr")

def fetch_wikiaitools():
    return _wp_api_tools("WikiAI Tools", "https://wikiaitools.com")

def fetch_notableai():
    return _wp_api_tools("Notable AI", "https://noteableai.com")

def fetch_aitoolguru():
    return _wp_api_tools("AI Tool Guru", "https://aitoolguru.com")

def fetch_hdrobots():
    return _wp_api_tools("HD Robots", "https://hdrobots.com")

def fetch_toolsstory():
    return _wp_api_tools("Tools Story", "https://toolsstory.net")

def fetch_freeaitools():
    return _wp_api_tools("Free AI Tools Dir.", "https://free-ai-tools-directory.com")

def fetch_madgenius():
    return _wp_api_tools("Mad Genius", "https://madgenius.co")

def fetch_aitoolslol():
    return _wp_api_tools("AI Tools LOL", "https://aitools.lol")

def fetch_aifinder():
    return _wp_api_tools("AI Finder", "https://ai-finder.net")

def fetch_aitoolhunt():
    return _wp_api_tools("AI Tool Hunt", "https://aitoolhunt.com")

def fetch_aitoolboard():
    return _wp_api_tools("AI Tool Board", "https://aitoolboard.com")

def fetch_fastpedia():
    return _wp_api_tools("Fastpedia", "https://fastpedia.io")

# ── Sources RSS / API publiques ────────────────────────────────────────────────

def fetch_betalist():
    """BetaList — RSS lancements produits, filtré IA."""
    return fetch_rss("BetaList", "https://betalist.com/feed.xml", ai_filter=True, max_items=20)

def fetch_github_ai():
    """GitHub Topics AI — Atom feed public des repos récents taggés AI."""
    return fetch_rss("GitHub Topics AI", "https://github.com/topics/artificial-intelligence.atom",
                     ai_filter=False, max_items=15)

def fetch_reddit_aitools():
    """Reddit r/aitools — JSON API public, liens externes uniquement."""
    results = []
    try:
        data = get_json(
            "https://www.reddit.com/r/aitools.json?limit=25&sort=new",
            referer="https://www.reddit.com/"
        )
        posts = data.get("data", {}).get("children", [])
        for post in posts:
            d        = post.get("data", {})
            title    = d.get("title", "").strip()
            url      = d.get("url", "")
            created  = d.get("created_utc", 0)
            date_iso = datetime.fromtimestamp(created, tz=timezone.utc).isoformat() if created else None
            if not title or not url or not is_external(url) or not is_recent(date_iso):
                continue
            desc = d.get("selftext", "")[:300]
            results.append(make_tool(title, url, desc, "Reddit r/aitools", date_iso))
        print(f"  Reddit r/aitools: {len(results)}")
    except Exception as e:
        print(f"  Reddit r/aitools erreur: {e}", file=sys.stderr)
    return results

# ── Sources bloquées depuis IPs GitHub Actions (conservées, non appelées) ──────

# def fetch_aisecret():      # 403 Cloudflare
# def fetch_aitoptools():    # 403 Cloudflare
# def fetch_taaift():        # 403
# def fetch_therundown():    # 403 Beehiiv
# def fetch_bestfreeai():    # 403
# def fetch_bestofai():      # 403

# ── Main ───────────────────────────────────────────────────────────────────────

FETCHERS = [
    # ── Confirmées fonctionnelles ────────────────────────────
    fetch_producthunt,
    fetch_hackernews,
    fetch_aixploria,

    # ── WP REST API — même logique qu'Aixploria ──────────────
    fetch_aiapp_fr,
    fetch_iaweb_fr,
    fetch_wikiaitools,
    fetch_notableai,
    fetch_aitoolguru,
    fetch_hdrobots,
    fetch_toolsstory,
    fetch_freeaitools,
    fetch_madgenius,
    fetch_aitoolslol,
    fetch_aifinder,
    fetch_aitoolhunt,
    fetch_aitoolboard,
    fetch_fastpedia,

    # ── RSS / API publiques ──────────────────────────────────
    fetch_betalist,
    fetch_github_ai,
    fetch_reddit_aitools,
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
                _name, results = future.result(timeout=45)
                all_tools.extend(results)
            except FuturesTimeout:
                print(f"  Timeout: {futures[future]}", file=sys.stderr)
            except Exception as e:
                print(f"  Erreur future {futures[future]}: {e}", file=sys.stderr)

    all_tools = deduplicate(all_tools)
    all_tools.sort(key=lambda t: t.get("date_iso",""), reverse=True)
    all_tools = [t for t in all_tools if len(t["name"].strip()) >= 3]

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
