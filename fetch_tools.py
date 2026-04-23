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
  ✓ BetaList           — RSS lancements produits filtrés IA
  ✓ GitHub AI Topics   — Atom feed public (repositories IA récents)
  ✓ Futurepedia        — API /api/tools (Next.js interne)
  ✓ The Rundown AI     — RSS newsletter (liens outils extraits)

  ✗ futuretools.io     — Cloudflare IP block, pas d'API publique
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
    "theresanaiforthat.com","free.theresanaiforthat.com","futurepedia.io","aiscout.net","aiapp.fr","iaweb.fr","openfuture.ai","ailibrary.io","wikiaitools.com","toolscout.ai","hdrobots.com","toolspedia.io","madgenius.co","aioftheday.com","aitoolboard.com","aitools.lol","aitools.fyi","ai-finder.net","aitoolhunt.com","aitoolnet.com","dang.ai","toolsstory.net","free-ai-tools-directory.com","aitoolguru.com","noteableai.com","faind.ai","aicenter.ai","bestfreeaiwebsites.com","fastpedia.io","bestofai.com",
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
    """Product Hunt AI — RSS officiel.
    Le lien dans le flux RSS pointe vers producthunt.com/products/xxx.
    On parse le HTML de la description pour extraire l'URL réelle du produit
    (le lien texte "Link" dans chaque entrée RSS)."""
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
            ph_url   = entry.get("link","")           # URL producthunt.com
            summary  = entry.get("summary","") or entry.get("description","")
            date_iso = parse_date(entry.get("published") or entry.get("updated",""))

            if not title or not is_recent(date_iso):
                continue

            # Filtre IA
            combined = (title + " " + BeautifulSoup(summary,"html.parser").get_text()).lower()
            ai_kw = ["ai","artificial intelligence","machine learning","llm","gpt",
                     "generative","automation","chatbot","image","voice","neural","agent"]
            if not any(kw in combined for kw in ai_kw):
                continue

            # Cherche l'URL réelle dans le HTML de la description
            # PH RSS : <a href="https://reel-product.com">Link</a> à la fin de chaque entrée
            tool_url = None
            if summary:
                desc_soup = BeautifulSoup(summary, "html.parser")
                for a in desc_soup.find_all("a", href=True):
                    href = a["href"].strip()
                    if href.startswith("http") and is_external(href):
                        tool_url = href
                        break

            if not tool_url:
                tool_url = ph_url   # fallback page PH

            desc = BeautifulSoup(summary, "html.parser").get_text(" ", strip=True)
            # Nettoie le texte "Discussion | Link" résiduel
            desc = re.sub(r"Discussion\s*\|\s*Link", "", desc).strip()

            results.append(make_tool(title, tool_url, desc, "Product Hunt", date_iso))

        print(f"  Product Hunt (RSS): {len(results)}")
    except Exception as e:
        print(f"  Product Hunt erreur: {e}", file=sys.stderr)
    return results

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
                    full.rstrip("/") != INDEX.rstrip("/") and
                    full not in cat_links and
                    full != BASE and
                    full != BASE + "/"):
                cat_links.append(full)
        cat_links = list(dict.fromkeys(cat_links))[:10]
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
    """Aixploria — WP REST API avec content pour extraire l'URL réelle de l'outil.
    Chaque article Aixploria présente un outil : le premier lien externe dans le
    contenu est l'URL du vrai site de l'outil."""
    results = []
    try:
        # On demande le content pour pouvoir extraire l'URL réelle de l'outil
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

            # Extrait le premier lien externe depuis le contenu HTML de l'article
            content_html = post.get("content",{}).get("rendered","")
            content_soup = BeautifulSoup(content_html, "html.parser")
            tool_url = None
            for a in content_soup.find_all("a", href=True):
                href = a["href"].strip()
                if href.startswith("http") and is_external(href):
                    tool_url = href
                    break

            if not tool_url:
                # Fallback : URL de la fiche Aixploria elle-même
                tool_url = post.get("link","")
                if not tool_url:
                    continue

            # Description : excerpt texte brut
            excerpt = BeautifulSoup(post.get("excerpt",{}).get("rendered",""), "html.parser").get_text(" ", strip=True)
            # Si pas d'excerpt, prend les 300 premiers caractères du contenu
            if not excerpt.strip():
                excerpt = content_soup.get_text(" ", strip=True)[:300]

            results.append(make_tool(title, tool_url, excerpt, "Aixploria", date_iso))

        print(f"  Aixploria (WP API): {len(results)}")
    except Exception as e:
        print(f"  Aixploria WP API erreur: {e}", file=sys.stderr)
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

def fetch_therundown():
    """The Rundown AI — newsletter IA sur Beehiiv.
    Extrait les liens vers des outils dans le contenu de chaque issue."""
    results = []
    rss_urls = [
        "https://www.therundown.ai/rss",
        "https://www.therundown.ai/feed",
        "https://therundown.beehiiv.com/feed",
    ]
    for rss_url in rss_urls:
        try:
            feed = feedparser.parse(rss_url, request_headers={"User-Agent": HEADERS["User-Agent"]})
            if not feed.entries:
                continue
            # Chaque entrée = une issue de newsletter
            # On extrait les liens externes mentionnés dans le contenu
            seen = set()
            for entry in feed.entries[:5]:  # max 5 issues récentes
                content = entry.get("content",[{}])[0].get("value","") or entry.get("summary","")
                if not content:
                    continue
                soup = BeautifulSoup(content, "html.parser")
                date_iso = parse_date(entry.get("published") or entry.get("updated",""))
                for a in soup.find_all("a", href=True):
                    href = a["href"].strip()
                    if not is_external(href) or href in seen:
                        continue
                    name = a.get_text(strip=True)[:80]
                    if not name or len(name) < 4:
                        continue
                    parent = a.find_parent(["li","p"])
                    desc = parent.get_text(" ", strip=True)[:300] if parent else ""
                    # Filtre : le lien doit ressembler à un outil (pas un article de presse)
                    url_low = href.lower()
                    if any(x in url_low for x in ["/blog/","/news/","/article/","twitter.com","x.com","linkedin.com","youtube.com"]):
                        continue
                    seen.add(href)
                    results.append(make_tool(name, href, desc, "The Rundown AI", date_iso))
            if results:
                print(f"  The Rundown AI: {len(results)}")
                return results
        except Exception as e:
            print(f"  The Rundown AI {rss_url}: {e}", file=sys.stderr)
    if not results:
        print(f"  The Rundown AI: 0")
    return results

def fetch_hackernews():
    """Hacker News — tag show_hn uniquement via API Algolia.
    Aucune restriction IP. Filtre sur les titres mentionnant l'IA pour éliminer
    les Show HN non-IA (hardware, finance, etc.)."""
    results = []
    AI_TITLE_KW = [
        "ai","gpt","llm","llama","claude","gemini","generative","neural",
        "image","voice","speech","chatbot","agent","automat","ml",
        "machine learning","diffusion","embedding","rag","copilot",
        "openai","anthropic","mistral","model","assistant","bot",
    ]
    # Mots indiquant clairement un article/opinion — filtre minimal
    ARTICLE_KW = [
        "the case for","my experience","deep dive","state of the",
    ]
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
            # Exclure les URLs HN (discussions sans lien externe)
            if "ycombinator.com" in url:
                continue
            # Exclure les URLs qui semblent être des articles/blogs
            url_low = url.lower()
            if any(x in url_low for x in ["/blog/","/posts/","/post/","/article/","/news/",".md","/wiki/"]):
                continue
            title_low = title.lower()
            # Doit mentionner l'IA
            if not any(kw in title_low for kw in AI_TITLE_KW):
                continue
            # Ne doit pas ressembler à un article
            if any(kw in title_low for kw in ARTICLE_KW):
                continue
            if url in seen:
                continue
            seen.add(url)
            date_iso = datetime.fromtimestamp(hit.get("created_at_i",0), tz=timezone.utc).isoformat()
            # Nom = titre sans préfixe "Show HN:"
            name = re.sub(r"^show hn\s*[:\-–]\s*", "", title, flags=re.I)[:80]
            # Description = premier commentaire si disponible (souvent l'auteur qui décrit l'outil)
            results.append(make_tool(name, url, "", "Hacker News", date_iso))

        results = results[:20]
        print(f"  Hacker News Show HN: {len(results)}")
    except Exception as e:
        print(f"  Hacker News erreur: {e}", file=sys.stderr)
    return results

def _multi_strategy(source_name, base_url, scrape_url=None, api_paths=None):
    """Helper universel : essaie WP API, puis RSS /feed/, puis API JSON, puis scraping HTML."""
    # 1. WP REST API
    res = _wp_api_tools(source_name, base_url)
    if res: return res
    # 2. RSS — une seule tentative sur /feed/
    res = fetch_rss(source_name, base_url.rstrip("/") + "/feed/")
    if res: return res
    # 3. API JSON custom
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
    # 4. Scraping HTML générique
    return _scrape_cards_simple(
        source_name,
        scrape_url or (base_url.rstrip("/") + "/"),
        base_url,
        "article,.tool,.card,[class*=\'tool\'],[class*=\'card\'],[class*=\'item\'],[class*=\'post\']",
        "h2,h3,h4,.title,.name,strong",
        "p,.desc,.description,.excerpt,.summary"
    )

# ── 22 nouvelles sources ───────────────────────────────────────────────────────

# Tier 1 — qualité / pertinence élevée

def fetch_bestofai():
    """bestofai.com — sélection curative de qualité."""
    return _multi_strategy(
        "Best of AI", "https://bestofai.com",
        api_paths=["/api/tools?sort=newest&limit=20"]
    )

def fetch_bestfreeai():
    return _multi_strategy("Best Free AI", "https://bestfreeaiwebsites.com")

def _wp_api_tools(source_name, base_url, per_page=20):
    """Helper generique WP REST API : extrait l'URL reelle de l'outil depuis le content."""
    results = []
    try:
        data = get_json(
            f"{base_url}/wp-json/wp/v2/posts"
            f"?per_page={per_page}&orderby=date&_fields=title,link,content,excerpt,date",
            referer=base_url + "/"
        )
        if not isinstance(data, list):
            raise Exception("Reponse non-liste")
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
    """Helper scraping generique."""
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

# ── Main ───────────────────────────────────────────────────────────────────────

FETCHERS = [
    fetch_producthunt,   # RSS — URL réelle extraite du HTML desc
    fetch_aisecret,      # HTML scraping DAILY TL;DR
    fetch_aitoptools,    # HTML /free-ai-tools/ 2 niveaux
    fetch_aixploria,     # WP API + RSS fallback
    fetch_taaift,        # API JSON officielle
    fetch_therundown,    # RSS newsletter — liens outils extraits
    fetch_hackernews,    # API Algolia show_hn filtré IA
    fetch_bestfreeai,    # RSS — 9 résultats confirmés
    fetch_bestofai,      # HTML — 2 résultats confirmés
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
    """Exécute un fetcher et retourne (nom, résultats)."""
    try:
        return fn.__name__, fn()
    except Exception as e:
        print(f"  Erreur {fn.__name__}: {e}", file=sys.stderr)
        return fn.__name__, []

def main():
    print(f"Veille IA — {datetime.now().strftime('%Y-%m-%d %H:%M')} — {len(FETCHERS)} sources\n")
    all_tools = []
    # Exécution parallèle — max 8 workers, timeout 45s par fetcher
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
