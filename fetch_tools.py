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
  ✓ 16 répertoires WP  — même WP REST API que Aixploria (cf. WP_DIRECTORIES)

tools.json est cumulatif : chaque run fusionne les nouveaux résultats avec le
fichier existant (dédupliqué) au lieu de l'écraser, pour qu'un outil non
trié ne disparaisse jamais silencieusement.
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
    # Pas de "br" : requests/urllib3 ne décodent le Brotli que si le paquet
    # `brotli` est installé, ce qui n'est pas le cas ici (cf. requirements).
    # Sans ça, un serveur qui répond en br renvoie des octets illisibles que
    # BeautifulSoup/feedparser parsent silencieusement comme vides — plusieurs
    # sources (Aixploria, FutureTools, AI Secret, TLDR AI...) étaient dans ce cas.
    "Accept-Encoding": "gzip, deflate",
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


def fetch_wp_directory(source_name, domain):
    """Répertoire générique bâti sur WordPress — WP REST API avec extraction URL réelle."""
    results = []
    data = get_json(
        f"https://{domain}/wp-json/wp/v2/posts"
        "?per_page=20&orderby=date&_fields=title,link,content,excerpt,date",
        referer=f"https://{domain}/"
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
        results.append(make_tool(title, tool_url, excerpt, source_name, date_iso))
    return results


def fetch_aixploria():
    """Aixploria — WP REST API avec fallback RSS si l'API échoue."""
    try:
        results = fetch_wp_directory("Aixploria", "www.aixploria.com")
        print(f"  Aixploria (WP API): {len(results)}")
    except Exception as e:
        print(f"  Aixploria WP API erreur: {e}", file=sys.stderr)
        results = fetch_rss("Aixploria", "https://www.aixploria.com/feed/")
    return results


# Répertoires WP listés dans le README mais jamais câblés jusqu'ici — même API
# que Aixploria, donc même fetcher générique. (nom affiché, domaine)
#
# Retirés de cette liste (vérifié le 11/08) :
#   - Best of AI (bestofai.com) : pas du WP, pas de /feed — a son propre
#     fetcher basé sur son sitemap (cf. fetch_bestofai ci-dessous).
#   - Tools Story (toolsstory.net) et AI Finder (ai-finder.net) : domaines
#     revendus / parkés (« this domain may be for sale »), plus les répertoires
#     décrits dans le README — à retirer aussi du README si confirmé durable.
WP_DIRECTORIES = [
    ("aiapp.fr",                "aiapp.fr"),
    ("iaweb.fr",                "iaweb.fr"),
    ("WikiAI Tools",            "wikiaitools.com"),
    ("Notable AI",              "noteableai.com"),
    ("AI Tool Guru",            "aitoolguru.com"),
    ("Best Free AI",            "bestfreeaiwebsites.com"),
    ("HD Robots",               "hdrobots.com"),
    ("Free AI Tools Directory", "free-ai-tools-directory.com"),
    ("Mad Genius",              "madgenius.co"),
    ("AI Tools LOL",            "aitools.lol"),
    ("AI Tool Hunt",            "aitoolhunt.com"),
    ("AI Tool Board",           "aitoolboard.com"),
    ("Fastpedia",               "fastpedia.io"),
]

def make_wp_fetcher(source_name, domain):
    """REST API d'abord ; si elle échoue ou est bloquée, tente le flux RSS
    du même site (souvent accessible même quand /wp-json/ est protégé)."""
    def fetcher():
        try:
            results = fetch_wp_directory(source_name, domain)
            print(f"  {source_name} (WP API): {len(results)}")
            return results
        except Exception as e:
            print(f"  {source_name} WP API erreur: {e}", file=sys.stderr)
        results = fetch_rss(source_name, f"https://{domain}/feed/")
        return results
    fetcher.__name__ = f"fetch_wp_{domain.replace('.', '_').replace('-', '_')}"
    return fetcher


def fetch_bestofai():
    """Best of AI — pas de WP/RSS ; utilise sitemap-tools.xml (lastmod par outil)
    puis récupère les balises OG de chaque page récente pour nom/description."""
    results = []
    try:
        r = requests.get("https://bestofai.com/sitemap-tools.xml", headers=HEADERS, timeout=30)
        r.raise_for_status()
        soup = BeautifulSoup(r.content, "xml")
        recent_urls = []
        for u in soup.find_all("url"):
            loc_el, lastmod_el = u.find("loc"), u.find("lastmod")
            if not loc_el or not lastmod_el:
                continue
            date_iso = parse_date(lastmod_el.get_text(strip=True))
            if date_iso and is_recent(date_iso):
                recent_urls.append((loc_el.get_text(strip=True), date_iso))

        # lastmod peut aussi correspondre à une simple mise à jour de contenu,
        # pas forcément un nouvel outil : on limite le volume par prudence.
        for tool_url, date_iso in recent_urls[:25]:
            try:
                pr = requests.get(tool_url, headers=HEADERS, timeout=12)
                pr.raise_for_status()
                psoup = BeautifulSoup(pr.text, "html.parser")
                og_title = psoup.find("meta", property="og:title")
                og_desc  = psoup.find("meta", property="og:description")
                title = (og_title["content"].strip() if og_title and og_title.get("content")
                         else tool_url.rstrip("/").rsplit("/", 1)[-1].replace("-", " ").title())
                desc = og_desc["content"].strip() if og_desc and og_desc.get("content") else ""
                results.append(make_tool(title, tool_url, desc, "Best of AI", date_iso))
            except Exception:
                continue
        print(f"  Best of AI (sitemap): {len(results)}")
    except Exception as e:
        print(f"  Best of AI erreur: {e}", file=sys.stderr)
    return results


def fetch_futuretools():
    """FutureTools — extraction des données embarquées dans le RSC payload Next.js."""
    results = []
    try:
        r = requests.get("https://futuretools.io/tools", headers=HEADERS, timeout=30)
        r.raise_for_status()

        # Le payload RSC était autrefois un seul <script> > 100k caractères ;
        # il est désormais streamé en ~25 chunks plus petits qu'il faut
        # recoller avant d'y chercher les outils.
        scripts = re.findall(r"<script>(self\.__next_f\.push.*?)</script>", r.text, re.S)
        big_script = "".join(scripts)

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
    """There's an AI for That — scraping HTML de la page d'accueil /?sort=new.

    Site refondu (11/08) : les anciens sélecteurs (ai_link_wrap, external_ai_link...)
    n'existent plus. La liste "Today" expose désormais name/date/lien interne
    directement sur des attributs data-* de chaque ligne, ce qui évite le
    scraping de texte fragile d'avant. Limite connue : le lien pointe vers la
    fiche TAAFT de l'outil, pas son site externe — la fiche détail est
    protégée par un challenge Cloudflare (Turnstile) qu'on ne cherche pas à
    contourner, donc ni l'URL externe ni la description ne sont récupérables
    sans navigateur headless.
    """
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

        rows = soup.find_all(class_="home-today-row")
        if not rows:
            print(f"  There's an AI: 0 lignes trouvées (page {len(r.text)} chars)", file=sys.stderr)

        for row in rows:
            ts = row.get("data-release-ts")
            tool_url = row.get("data-href", "")
            if not ts or not tool_url:
                continue
            date_iso = datetime.fromtimestamp(int(ts), tz=timezone.utc).isoformat()
            if not is_recent(date_iso):
                continue

            name_el = row.find(class_="home-today-name-text")
            name = name_el.get_text(strip=True) if name_el else ""
            if not name or len(name) < 3:
                continue

            results.append(make_tool(name, tool_url, "", "There's an AI", date_iso))

        print(f"  There's an AI (HTML): {len(results)}")
    except Exception as e:
        print(f"  There's an AI erreur: {e}", file=sys.stderr)
    return results


def fetch_aisecret():
    """AI Secret — RSS Ghost pour les URLs puis scraping des articles."""
    results = []
    SOCIAL = ["twitter.com","x.com","linkedin.com","youtube.com",
              "facebook.com","instagram.com","threads.net"]
    # Domaines de presse / référence / académiques cités en source dans les
    # articles mais qui ne sont jamais des outils IA — sans ça, le scraping
    # remonte autant de citations arXiv ou d'articles de presse que d'outils.
    NON_TOOL_DOMAINS = [
        "arxiv.org","apnews.com","reuters.com","bloomberg.com","nytimes.com",
        "wsj.com","ft.com","forbes.com","techcrunch.com","theverge.com",
        "wired.com","axios.com","cnbc.com","businessinsider.com",
        "wikipedia.org","finance.yahoo.com","yahoo.com","semafor.com",
        "theinformation.com","arstechnica.com","engadget.com",
        "venturebeat.com","washingtonpost.com","cnn.com","bbc.com",
        "aisecret.us","ghost.io",
    ]
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

                seen_in_article = set()
                for a in content.find_all("a", href=True):
                    href = a["href"].strip()
                    text = a.get_text(strip=True)
                    if not href.startswith("http") or len(text) < 4:
                        continue
                    low = href.lower()
                    if any(s in low for s in SOCIAL):
                        continue
                    domain = urlparse(href).netloc.lower()
                    if any(d in domain for d in NON_TOOL_DOMAINS):
                        continue
                    href_key = href.rstrip("/").lower()
                    if href_key in seen_in_article:
                        continue
                    seen_in_article.add(href_key)
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
    fetch_bestofai,
] + [make_wp_fetcher(name, domain) for name, domain in WP_DIRECTORIES]

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

def load_previous_tools():
    """Charge le tools.json du run précédent pour accumuler au lieu d'écraser.

    Les outils non triés (ni « déjà publié » ni « ignoré » côté interface) ne
    doivent jamais disparaître silencieusement simplement parce qu'ils sont
    sortis de la fenêtre « récent » d'une source — ils restent tant qu'ils ne
    sont pas explicitement retirés.
    """
    try:
        with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
            return json.load(f).get("tools", [])
    except (FileNotFoundError, json.JSONDecodeError):
        return []

def main():
    print(f"Veille IA — {datetime.now().strftime('%Y-%m-%d %H:%M')} — {len(FETCHERS)} sources\n")
    all_tools = []
    with ThreadPoolExecutor(max_workers=12) as executor:
        futures = {executor.submit(run_fetcher, fn): fn.__name__ for fn in FETCHERS}
        for future in as_completed(futures):
            try:
                _name, results = future.result(timeout=90)
                all_tools.extend(results)
            except FuturesTimeout:
                print(f"  Timeout: {futures[future]}", file=sys.stderr)
            except Exception as e:
                print(f"  Erreur future {futures[future]}: {e}", file=sys.stderr)

    new_count = len(deduplicate(all_tools))
    previous_tools = load_previous_tools()
    # Nouveaux en premier : en cas de doublon entre les deux runs, ce sont
    # leurs métadonnées (plus fraîches) qui l'emportent dans deduplicate().
    all_tools = deduplicate(all_tools + previous_tools)
    all_tools.sort(key=lambda t: t.get("date_iso",""), reverse=True)
    all_tools = [t for t in all_tools if len(t["name"].strip()) >= 3]
    print(f"\nNouveaux ce run : {new_count} — Total cumulé : {len(all_tools)}")

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
