#!/usr/bin/env python3
"""
fetch_tools.py — Veille quotidienne outils IA (uneiaparjour.fr)

Sources et stratégies :
  ✓ Product Hunt       — RSS officiel (fiable)
  ✓ AI Secret          — HTML scraping section DAILY TL;DR
  ✓ AI Top Tools       — HTML scraping /free-ai-tools/
  ✓ Hacker News        — API Algolia (pas d'auth, pas de rate limit strict)
  ✓ Reddit r/artificial — JSON API public
  ✓ Aixploria          — WP REST API (contourne le RSS bloqué)
  ✓ There's an AI      — API JSON officielle (https://theresanaiforthat.com/api/)
  ✓ Ben's Bites        — RSS Beehiiv (newsletter IA très suivie)
  ✓ TLDR AI            — RSS newsletter
  ✓ Futurepedia        — API /api/tools (Next.js interne)
  ✓ The Rundown AI     — RSS Beehiiv

  ✗ futuretools.io     — Cloudflare IP block, pas d'API publique
  ✗ powerfulai.tools   — Cloudflare IP block
  ✗ toolify.ai         — Cloudflare IP block
  ✗ aitoolsdirectory   — Cloudflare IP block
  ✗ aitools.sh         — Cloudflare IP block
"""
import json, re, time, sys
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
    "theresanaiforthat.com","free.theresanaiforthat.com","futurepedia.io",
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
    r = requests.get(url, headers=hdrs, timeout=20)
    r.raise_for_status()
    return BeautifulSoup(r.text, "html.parser")

def get_json(url, referer=None):
    hdrs = dict(HEADERS)
    hdrs["Accept"] = "application/json, */*"
    if referer:
        hdrs["Referer"] = referer
    r = requests.get(url, headers=hdrs, timeout=20)
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
        # Ne rejette pas sur bozo — feedparser extrait quand même les entrées
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

# ── Sources ────────────────────────────────────────────────────────────────────

def fetch_producthunt():
    """Product Hunt AI — RSS officiel, très fiable, pas de Cloudflare sur le feed."""
    return fetch_rss(
        "Product Hunt",
        "https://www.producthunt.com/feed?category=artificial-intelligence",
        ai_filter=True
    )

def fetch_aisecret():
    """AI Secret — section DAILY TL;DR (rendu côté serveur, pas de Cloudflare)."""
    results, seen = [], set()
    try:
        page = get_html("https://aisecret.us/")

        tldr_container = None

        # Stratégie 1 : heading court contenant "tl;dr" ou "daily"
        for el in page.find_all(["h1","h2","h3","h4","h5","h6","strong","b"]):
            txt = el.get_text(strip=True).lower()
            if ("tl;dr" in txt or "tldr" in txt or "daily" in txt) and len(txt) < 80:
                # Cherche le conteneur parent avec des liens
                for ancestor in el.parents:
                    if ancestor.name in ("section","article","div","main","aside"):
                        if ancestor.find("a", href=True):
                            tldr_container = ancestor
                            break
                if tldr_container:
                    break

        # Stratégie 2 : id/class contenant "tldr" ou "daily"
        if not tldr_container:
            for attr in ["id","class"]:
                for el in page.find_all(attrs={attr: re.compile(r"tl.?dr|daily", re.I)}):
                    if el.find("a", href=True):
                        tldr_container = el; break
                if tldr_container:
                    break

        # Stratégie 3 : balise <section> ou <article> dont le premier texte contient "tl;dr"
        if not tldr_container:
            for el in page.find_all(["section","article"]):
                first_text = el.get_text(strip=True)[:100].lower()
                if "tl;dr" in first_text or "tldr" in first_text:
                    tldr_container = el; break

        if not tldr_container:
            # Affiche la structure de la page pour diagnostic
            headings = [(h.name, h.get_text(strip=True)[:60]) for h in page.find_all(["h1","h2","h3","h4"])]
            print(f"  AI Secret : DAILY TL;DR introuvable. Headings: {headings[:8]}", file=sys.stderr)
            return []

        for a in tldr_container.find_all("a", href=True):
            full = urljoin("https://aisecret.us", a["href"])
            if not is_external(full) or full in seen:
                continue
            name = a.get_text(strip=True)[:80]
            if not name or len(name) < 3:
                name = urlparse(full).netloc
            parent = a.find_parent(["li","p","div","span"])
            desc   = parent.get_text(" ", strip=True)[:300] if parent else ""
            seen.add(full)
            results.append(make_tool(name, full, desc, "AI Secret"))

        print(f"  AI Secret (DAILY TL;DR): {len(results)}")
    except Exception as e:
        print(f"  AI Secret erreur: {e}", file=sys.stderr)
    return results

def fetch_aitoptools():
    """AI Top Tools /free-ai-tools/ — scraping 2 niveaux, URLs externes uniquement."""
    BASE  = "https://aitoptools.com"
    INDEX = f"{BASE}/free-ai-tools/"
    results, seen_urls, seen_names = [], set(), set()

    def extract_tools(page_soup, max_tools=8):
        found = []
        # Sélecteurs très larges pour couvrir la structure réelle
        candidates = page_soup.select(
            "article, li, "
            "div[class*='tool'], div[class*='card'], div[class*='item'], div[class*='post'], "
            "div[class*='grid'] > div, ul[class*='tool'] > li, ul[class*='list'] > li"
        )
        if not candidates:
            # Fallback : tous les liens avec du texte
            candidates = [a.find_parent(["li","div"]) or a
                          for a in page_soup.find_all("a", href=True)
                          if len(a.get_text(strip=True)) > 3]
        for card in candidates[:80]:
            if card is None:
                continue
            ne   = card.select_one("h1,h2,h3,h4,h5,strong,b,span[class*='name'],span[class*='title'],p[class*='name']")
            name = ne.get_text(strip=True)[:80] if ne else card.get_text(strip=True)[:60]
            name = re.sub(r"\s+", " ", name).strip()
            if not name or len(name) < 3:
                continue
            # URL externe (le vrai site de l'outil)
            ext_url = None
            for a in card.find_all("a", href=True):
                full = urljoin(BASE, a["href"])
                if is_external(full):
                    ext_url = full; break
            # Cherche aussi dans les attributs data-*
            if not ext_url:
                for attr in ["data-url","data-href","data-link","data-website","data-external","data-tool-url"]:
                    val = card.get(attr,"")
                    if val and is_external(val):
                        ext_url = val; break
            if not ext_url:
                continue
            de   = card.select_one("p, span[class*='desc'], div[class*='desc'], div[class*='summary']")
            desc = de.get_text(" ", strip=True)[:300] if de else ""
            nk   = re.sub(r"[\s\-_]","", name.lower())
            if ext_url in seen_urls or nk in seen_names:
                continue
            seen_urls.add(ext_url); seen_names.add(nk)
            found.append(make_tool(name, ext_url, desc, "AI Top Tools"))
            if len(found) >= max_tools:
                break
        return found

    try:
        index_page = get_html(INDEX)

        # Collecte les liens de catégories
        cat_links = []
        for a in index_page.find_all("a", href=True):
            full = urljoin(BASE, a["href"])
            if (full.startswith(BASE) and
                    "/free-ai-tools/" in full and
                    full.rstrip("/") != INDEX.rstrip("/") and
                    full not in cat_links):
                cat_links.append(full)
        cat_links = list(dict.fromkeys(cat_links))[:8]
        print(f"  AI Top Tools — {len(cat_links)} catégories trouvées")

        # Page index
        r0 = extract_tools(index_page, max_tools=8)
        results.extend(r0)

        # Pages catégories
        for cat_url in cat_links:
            try:
                cat_page = get_html(cat_url, referer=INDEX)
                results.extend(extract_tools(cat_page, max_tools=5))
            except Exception as e:
                print(f"    Catégorie {cat_url}: {e}", file=sys.stderr)
            time.sleep(1)

        print(f"  AI Top Tools total: {len(results)}")
    except Exception as e:
        print(f"  AI Top Tools erreur: {e}", file=sys.stderr)
    return results

def fetch_aixploria():
    """Aixploria — WP REST API (contourne le RSS malformé et le HTML bloqué).
    Retourne les 20 derniers articles avec catégories et lien de l'outil."""
    results = []
    try:
        data = get_json(
            "https://www.aixploria.com/wp-json/wp/v2/posts?per_page=20&orderby=date&_fields=title,link,excerpt,date,categories",
            referer="https://www.aixploria.com/"
        )
        for post in data:
            title    = post.get("title",{}).get("rendered","").strip()
            title    = BeautifulSoup(title, "html.parser").get_text()
            url      = post.get("link","")
            excerpt  = BeautifulSoup(post.get("excerpt",{}).get("rendered",""), "html.parser").get_text(" ", strip=True)
            date_str = post.get("date","")
            date_iso = parse_date(date_str)
            if not title or not url or not is_recent(date_iso):
                continue
            results.append(make_tool(title, url, excerpt, "Aixploria", date_iso))
        print(f"  Aixploria (WP API): {len(results)}")
    except Exception as e:
        print(f"  Aixploria WP API erreur: {e}", file=sys.stderr)
        # Fallback RSS (peut marcher selon les IPs GitHub)
        results = fetch_rss("Aixploria", "https://www.aixploria.com/feed/")
    return results

def fetch_taaift():
    """There's an AI for That — API JSON officielle.
    L'API publique /api/ ne requiert pas d'authentification pour la liste."""
    results = []
    # Essai 1 : API officielle
    for api_url in [
        "https://theresanaiforthat.com/api/?order=date&limit=30",
        "https://theresanaiforthat.com/api/featured/?order=date&limit=30",
        "https://theresanaiforthat.com/api/new/?limit=30",
    ]:
        try:
            data = get_json(api_url)
            items = data if isinstance(data, list) else data.get("results", data.get("tools", data.get("data", [])))
            if not isinstance(items, list):
                continue
            for item in items[:30]:
                name = (item.get("name") or item.get("title") or "").strip()
                url  = item.get("url") or item.get("website") or item.get("link") or item.get("href","")
                desc = item.get("description") or item.get("summary","")
                date_iso = parse_date(item.get("created_at") or item.get("date",""))
                if name and url and is_recent(date_iso):
                    results.append(make_tool(name, url, desc, "There's an AI for That", date_iso))
            if results:
                print(f"  There's an AI for That (API): {len(results)}")
                return results
        except Exception:
            pass
    # Essai 2 : RSS feed (avec bozo toléré)
    results = fetch_rss("There's an AI for That", "https://theresanaiforthat.com/rss/")
    return results

def fetch_futurepedia():
    """Futurepedia — API Next.js interne /api/tools."""
    results = []
    api_urls = [
        "https://www.futurepedia.io/api/tools?sort=newest&page=1&limit=20",
        "https://www.futurepedia.io/api/tools?sort=new&page=1&limit=20",
        "https://www.futurepedia.io/api/tools/newest?limit=20",
    ]
    for api_url in api_urls:
        try:
            data = get_json(api_url, referer="https://www.futurepedia.io/")
            items = (data if isinstance(data, list)
                     else data.get("tools") or data.get("data") or data.get("results") or [])
            if not isinstance(items, list) or not items:
                continue
            for item in items[:20]:
                name = (item.get("name") or item.get("title") or "").strip()
                url  = item.get("url") or item.get("website") or item.get("link","")
                desc = item.get("description") or item.get("summary","")
                date_iso = parse_date(item.get("createdAt") or item.get("date") or item.get("created_at",""))
                if name and url:
                    results.append(make_tool(name, url, desc, "Futurepedia", date_iso))
            if results:
                print(f"  Futurepedia (API): {len(results)}")
                return results
        except Exception as e:
            print(f"  Futurepedia {api_url}: {e}", file=sys.stderr)
    # Fallback RSS
    results = fetch_rss("Futurepedia", "https://www.futurepedia.io/rss.xml")
    return results

def fetch_bensbites():
    """Ben's Bites — newsletter IA très suivie, RSS Beehiiv fiable depuis n'importe quel serveur."""
    results = []
    for rss in [
        "https://bensbites.beehiiv.com/feed",
        "https://www.bensbites.co/feed",
    ]:
        res = fetch_rss("Ben's Bites", rss, ai_filter=False)
        if res:
            return res
    return results

def fetch_tldrai():
    """TLDR AI — newsletter quotidienne, RSS public."""
    return fetch_rss("TLDR AI", "https://tldr.tech/ai/rss")

def fetch_therundown():
    """The Rundown AI — newsletter Beehiiv, RSS public."""
    results = []
    for rss in [
        "https://www.therundown.ai/rss",
        "https://www.therundown.ai/feed",
        "https://api.beehiiv.com/v2/publications/pub_3d14cfcd-e57a-4fb3-af96-7d90c3bbe03c/posts?limit=10&status=confirmed",
    ]:
        res = fetch_rss("The Rundown AI", rss, ai_filter=False)
        if res:
            return res
    return results

def fetch_hackernews():
    """Hacker News — API Algolia, aucune restriction IP, très fiable.
    Cherche les posts récents mentionnant des outils IA (Show HN, Ask HN, lancements)."""
    results = []
    try:
        # Show HN posts récents avec mention d'IA
        for query in [
            "Show HN AI tool",
            "Show HN generative AI",
            "Show HN LLM",
        ]:
            try:
                data = get_json(
                    f"https://hn.algolia.com/api/v1/search_by_date"
                    f"?query={requests.utils.quote(query)}"
                    f"&tags=story"
                    f"&numericFilters=created_at_i>{int((datetime.now(timezone.utc) - timedelta(hours=CUTOFF_HOURS)).timestamp())}"
                    f"&hitsPerPage=10"
                )
                for hit in data.get("hits", []):
                    title = hit.get("title","").strip()
                    url   = hit.get("url","") or f"https://news.ycombinator.com/item?id={hit.get('objectID','')}"
                    if not title or not url:
                        continue
                    # Filtre : Show HN seulement ou mention d'outil IA
                    title_low = title.lower()
                    if not any(kw in title_low for kw in ["show hn","launch","ai tool","ai app","built","made a","created"]):
                        continue
                    date_iso = datetime.fromtimestamp(hit.get("created_at_i",0), tz=timezone.utc).isoformat()
                    # Nom = titre sans "Show HN:" prefix
                    name = re.sub(r"^show hn\s*[:\-–]\s*", "", title, flags=re.I)[:80]
                    results.append(make_tool(name, url, "", "Hacker News", date_iso))
                time.sleep(0.3)
            except Exception as e:
                print(f"  HN query '{query}': {e}", file=sys.stderr)

        # Dédoublonnage interne
        seen = set()
        deduped = []
        for t in results:
            if t["tool_url"] not in seen:
                seen.add(t["tool_url"]); deduped.append(t)
        results = deduped[:20]
        print(f"  Hacker News (API): {len(results)}")
    except Exception as e:
        print(f"  Hacker News erreur: {e}", file=sys.stderr)
    return results

def fetch_reddit():
    """Reddit r/ArtificialIntelligence + r/AITools — JSON API public.
    Reddit accepte les requêtes sans auth depuis des IPs serveur."""
    results = []
    reddit_ua = "veille-ia-bot/1.0 (https://uneiaparjour.fr; contact@uneiaparjour.fr)"
    for sub in ["ArtificialIntelligence","aitools","ChatGPT","StableDiffusion"]:
        try:
            r = requests.get(
                f"https://www.reddit.com/r/{sub}/new.json?limit=15",
                headers={"User-Agent": reddit_ua},
                timeout=15
            )
            r.raise_for_status()
            posts = r.json().get("data",{}).get("children",[])
            count = 0
            for post in posts:
                d = post.get("data",{})
                title    = d.get("title","").strip()
                url      = d.get("url","")
                selftext = d.get("selftext","")[:300]
                created  = d.get("created_utc", 0)
                date_iso = datetime.fromtimestamp(created, tz=timezone.utc).isoformat()
                if not title or not url or not is_recent(date_iso):
                    continue
                # Filtre : liens externes seulement (pas de self posts sans lien)
                if not is_external(url):
                    continue
                # Filtre : pertinence IA
                combined = (title + " " + selftext).lower()
                ai_kw = ["ai","tool","app","generate","model","llm","gpt","image","voice","chat","automate"]
                if not any(kw in combined for kw in ai_kw):
                    continue
                results.append(make_tool(title[:80], url, selftext, f"Reddit r/{sub}", date_iso))
                count += 1
                if count >= 5:
                    break
            print(f"  Reddit r/{sub}: {count}")
            time.sleep(0.5)
        except Exception as e:
            print(f"  Reddit r/{sub} erreur: {e}", file=sys.stderr)
    return results

# ── Main ───────────────────────────────────────────────────────────────────────

FETCHERS = [
    fetch_producthunt,
    fetch_aisecret,
    fetch_aitoptools,
    fetch_aixploria,
    fetch_taaift,
    fetch_futurepedia,
    fetch_bensbites,
    fetch_tldrai,
    fetch_therundown,
    fetch_hackernews,
    fetch_reddit,
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

def main():
    print(f"Veille IA — {datetime.now().strftime('%Y-%m-%d %H:%M')} — {len(FETCHERS)} sources\n")
    all_tools = []
    for fn in FETCHERS:
        try:
            all_tools.extend(fn())
        except Exception as e:
            print(f"  Erreur {fn.__name__}: {e}", file=sys.stderr)
        time.sleep(2)

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
