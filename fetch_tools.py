#!/usr/bin/env python3
"""
fetch_tools.py — Veille quotidienne outils IA (uneiaparjour.fr)
11 sources — génère tools.json pour GitHub Pages
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
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest":  "document",
    "Sec-Fetch-Mode":  "navigate",
    "Sec-Fetch-Site":  "none",
    "Cache-Control":   "max-age=0",
    "DNT":             "1",
}

RSS_HEADERS = {
    "User-Agent": HEADERS["User-Agent"],
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
}

# ── Catégories ─────────────────────────────────────────────────────────────────

CATEGORIES_KW = {
    "images":            ["image","photo","illustration","visual","artwork","dall-e","midjourney","stable diffusion","flux","picture"],
    "vidéo":             ["video","vidéo","clip","film","animation","cinematic","reel"],
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
    "theresanaiforthat.com","futurepedia.io","futuretools.io",
    "aixploria.com","aisecret.us","aitoolsdirectory.com",
    "powerfulai.tools","aitoptools.com","aitools.sh",
    "toolify.ai","producthunt.com","therundown.ai",
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
        "description": re.sub(r"\s+", " ", desc[:400]).strip(),
        "source":      source,
        "date_iso":    date_iso or datetime.now(timezone.utc).isoformat(),
        "categories":  guess_categories(name + " " + desc),
    }

def get_soup(url, referer=None):
    hdrs = dict(HEADERS)
    if referer:
        hdrs["Referer"] = referer
    r = requests.get(url, headers=hdrs, timeout=20)
    r.raise_for_status()
    return BeautifulSoup(r.text, "html.parser")

# ── fetch_rss : ne pas rejeter les feeds bozo ─────────────────────────────────
# feedparser est conçu pour gérer les XML malformés et extrait quand même les
# entrées. Le flag bozo signale juste une anomalie, il ne doit pas bloquer.

def fetch_rss(source_name, rss_url, ai_filter=False, max_items=30):
    results = []
    try:
        feed = feedparser.parse(rss_url, request_headers=RSS_HEADERS)
        if not feed.entries:
            # Feed vide ou URL invalide (retourne du HTML par ex.)
            media_type = getattr(feed, "headers", {}).get("content-type","")
            if "html" in media_type:
                raise Exception(f"URL renvoie du HTML, pas un RSS")
            raise Exception(f"Feed vide (bozo={feed.bozo})")
        for entry in feed.entries[:max_items]:
            title    = entry.get("title","").strip()
            url      = entry.get("link","")
            desc     = BeautifulSoup(entry.get("summary","") or "", "html.parser").get_text(" ", strip=True)
            date_iso = parse_date(entry.get("published") or entry.get("updated",""))
            if not title or not url or not is_recent(date_iso):
                continue
            if ai_filter:
                combined = (title + " " + desc).lower()
                ai_kw = ["ai","artificial intelligence","machine learning","llm","gpt",
                         "generative","automation","chatbot","image generation","voice","neural"]
                if not any(kw in combined for kw in ai_kw):
                    continue
            t = make_tool(title, url, desc, source_name, date_iso)
            results.append(t)
        print(f"  {source_name} (RSS): {len(results)}")
    except Exception as e:
        print(f"  {source_name} RSS erreur: {e}", file=sys.stderr)
    return results

def scrape_cards(source_name, url, base, card_sel, name_sel=None, desc_sel=None,
                 max_items=20, referer=None):
    results, seen = [], set()
    try:
        page = get_soup(url, referer=referer or base)
        for card in page.select(card_sel)[:max_items * 4]:
            ne   = card.select_one(name_sel) if name_sel else card
            name = ne.get_text(strip=True)[:80] if ne else card.get_text(strip=True)[:60]
            if not name or len(name) < 3:
                continue
            ext_url = int_url = None
            a_tags = [card] if card.name == "a" else card.find_all("a", href=True)
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

# ── Sources ────────────────────────────────────────────────────────────────────

def fetch_aixploria():
    """WordPress FR — le RSS est légèrement malformé mais feedparser extrait les entrées."""
    return fetch_rss("Aixploria", "https://www.aixploria.com/fr/feed/")

def fetch_taaift():
    """There's an AI for That — RSS malformé mais parseable ; HTML bloqué par Cloudflare."""
    for rss in [
        "https://theresanaiforthat.com/feed/",
        "https://theresanaiforthat.com/rss.xml",
        "https://theresanaiforthat.com/rss/",
    ]:
        res = fetch_rss("There's an AI for That", rss)
        if res:
            return res
    return []

def fetch_futurepedia():
    """Futurepedia — RSS malformé mais parseable ; HTML derrière Cloudflare."""
    for rss in [
        "https://www.futurepedia.io/rss.xml",
        "https://www.futurepedia.io/feed.xml",
        "https://www.futurepedia.io/feed",
    ]:
        res = fetch_rss("Futurepedia", rss)
        if res:
            return res
    # Essai API Next.js (sans authentification)
    try:
        r = requests.get(
            "https://www.futurepedia.io/api/tools?sort=newest&page=1&limit=20",
            headers=HEADERS, timeout=15
        )
        data = r.json()
        tools_raw = data.get("tools") or data.get("data") or (data if isinstance(data,list) else [])
        results = []
        for t in tools_raw[:20]:
            name = (t.get("name") or "").strip()
            url  = t.get("url") or t.get("website") or t.get("link","")
            desc = t.get("description","")
            if name and url:
                results.append(make_tool(name, url, desc, "Futurepedia"))
        if results:
            print(f"  Futurepedia (API): {len(results)}")
            return results
    except Exception:
        pass
    return []

def fetch_futuretools():
    """Future Tools — le feed RSS renvoie du HTML, utiliser l'HTML directement."""
    # Pas de RSS valide — scraping HTML
    return scrape_cards(
        "Future Tools", "https://futuretools.io/",
        "https://futuretools.io",
        # Sélecteurs larges pour couvrir différentes structures
        "div[class*='tool'],div[class*='card'],article,li[class*='tool']",
        "h2,h3,h4,p[class*='name'],p[class*='title'],strong,b",
        "p,span[class*='desc'],div[class*='desc']"
    )

def fetch_aisecret():
    """AI Secret — section DAILY TL;DR.
    Cette section est rendue côté serveur sur la page d'accueil.
    Recherche flexible par texte pour trouver le conteneur."""
    results, seen = [], set()
    try:
        page = get_soup("https://aisecret.us/")

        # Stratégie 1 : cherche un élément dont le texte contient "tl;dr" ou "tldr"
        tldr_container = None
        for el in page.find_all(True):
            txt = el.get_text(strip=True).lower()
            # Cherche l'élément le plus précis (heading ou label de section)
            if el.name in ("h1","h2","h3","h4","h5","h6","strong","b","span","p","div") and (
                "tl;dr" in txt or "tldr" in txt or "daily" in txt
            ) and len(txt) < 60:  # évite les gros blocs de texte
                # Remonte au conteneur parent qui englobe le contenu associé
                for ancestor in el.parents:
                    if ancestor.name in ("section","article","div","main"):
                        # Vérifie que ce conteneur a des liens
                        if ancestor.find("a", href=True):
                            tldr_container = ancestor
                            break
                if tldr_container:
                    break

        # Stratégie 2 : cherche par attribut id ou class contenant "tldr" ou "daily"
        if not tldr_container:
            for el in page.find_all(True, attrs={"id": re.compile(r"tl.?dr|daily", re.I)}):
                tldr_container = el; break
        if not tldr_container:
            for el in page.find_all(True, attrs={"class": re.compile(r"tl.?dr|daily", re.I)}):
                tldr_container = el; break

        if not tldr_container:
            print("  AI Secret : DAILY TL;DR introuvable (section probablement JS)", file=sys.stderr)
            return []

        for a in tldr_container.find_all("a", href=True):
            full = urljoin("https://aisecret.us", a["href"])
            if not is_external(full) or full in seen:
                continue
            name = a.get_text(strip=True)[:80]
            if not name or len(name) < 3:
                name = full
            parent = a.find_parent(["li","p","div"])
            desc   = parent.get_text(" ", strip=True)[:300] if parent else ""
            seen.add(full)
            results.append(make_tool(name, full, desc, "AI Secret"))

        print(f"  AI Secret (DAILY TL;DR): {len(results)}")
    except Exception as e:
        print(f"  AI Secret erreur: {e}", file=sys.stderr)
    return results

def fetch_aitoolsdirectory():
    """aitoolsdirectory.com — essai RSS puis HTML."""
    for rss in [
        "https://aitoolsdirectory.com/rss",
        "https://aitoolsdirectory.com/feed",
    ]:
        res = fetch_rss("AI Tools Directory", rss)
        if res:
            return res
    return scrape_cards(
        "AI Tools Directory",
        "https://aitoolsdirectory.com/?filter=Price-%3AFree,Freemium",
        "https://aitoolsdirectory.com",
        "article,div[class*='tool'],div[class*='card'],li[class*='tool']",
        "h2,h3,h4,p[class*='name'],strong",
        "p,div[class*='desc'],span[class*='desc']"
    )

def fetch_powerfulai():
    """powerfulai.tools — derrière Cloudflare, 403 inévitable depuis GitHub Actions."""
    # Ces URLs sont bloquées au niveau IP par Cloudflare — on tente quand même
    # mais sans session (overhead inutile)
    results = []
    for label, url in [
        ("Free",    "https://www.powerfulai.tools/?filter=Free"),
        ("Freemium","https://www.powerfulai.tools/?filter=Freemium"),
    ]:
        res = scrape_cards(
            "Powerful AI Tools", url, "https://www.powerfulai.tools",
            "article,div[class*='tool'],div[class*='card'],li[class*='tool']",
            "h2,h3,h4,p[class*='name'],strong",
            "p,div[class*='desc']"
        )
        results.extend(res)
    return results

def fetch_aitoptools():
    """aitoptools.com — scrape la page /free-ai-tools/ et ses sous-pages catégorie.
    Seules les URLs externes (sites réels des outils) sont conservées."""
    BASE  = "https://aitoptools.com"
    INDEX = f"{BASE}/free-ai-tools/"
    results, seen_urls, seen_names = [], set(), set()

    def extract_external_tools(page_soup, label, max_tools=8):
        found = []
        # Sélecteurs larges : articles, cartes, items de liste
        candidates = page_soup.select(
            "article, li, div[class*='tool'], div[class*='card'], "
            "div[class*='item'], div[class*='post']"
        )
        for card in candidates[:60]:
            ne   = card.select_one("h1,h2,h3,h4,h5,strong,b,.name,.title")
            name = ne.get_text(strip=True)[:80] if ne else ""
            if not name or len(name) < 3:
                continue
            # Cherche un lien externe dans la carte
            ext_url = None
            for a in card.find_all("a", href=True):
                full = urljoin(BASE, a["href"])
                if is_external(full):
                    ext_url = full; break
            # Cherche aussi dans les attributs data-*
            if not ext_url:
                for attr in ["data-url","data-href","data-link","data-website","data-external"]:
                    val = card.get(attr,"")
                    if val and is_external(val):
                        ext_url = val; break
            if not ext_url:
                continue
            de   = card.select_one("p,.desc,.description,.summary,span[class*='desc']")
            desc = de.get_text(" ",strip=True)[:300] if de else ""
            nk   = re.sub(r"[\s\-_]","", name.lower())
            if ext_url in seen_urls or nk in seen_names:
                continue
            seen_urls.add(ext_url); seen_names.add(nk)
            found.append(make_tool(name, ext_url, desc, "AI Top Tools"))
            if len(found) >= max_tools:
                break
        return found

    try:
        index_page = soup_obj = get_soup(INDEX)

        # Collecte liens de catégories : hrefs internes qui approfondissent /free-ai-tools/
        cat_links = []
        for a in index_page.find_all("a", href=True):
            full = urljoin(BASE, a["href"])
            # Lien interne, sous /free-ai-tools/, différent de la page index
            if (full.startswith(BASE) and
                    "/free-ai-tools/" in full and
                    full != INDEX and
                    full not in cat_links):
                cat_links.append(full)
        cat_links = list(dict.fromkeys(cat_links))[:8]  # dédoublonnage + max 8
        print(f"  AI Top Tools — {len(cat_links)} catégories")

        # Page index elle-même
        results.extend(extract_external_tools(index_page, "index", max_tools=6))

        # Pages de catégories
        for cat_url in cat_links:
            try:
                cat_page = get_soup(cat_url, referer=INDEX)
                results.extend(extract_external_tools(cat_page, cat_url, max_tools=5))
            except Exception as e:
                print(f"    Cat {cat_url}: {e}", file=sys.stderr)
            time.sleep(1)

        print(f"  AI Top Tools total: {len(results)}")
    except Exception as e:
        print(f"  AI Top Tools erreur: {e}", file=sys.stderr)
    return results

def fetch_aitoolssh():
    """aitools.sh/free — outils gratuits."""
    return scrape_cards(
        "AI Tools .sh", "https://aitools.sh/free",
        "https://aitools.sh",
        # Sélecteurs larges
        "article,div[class*='tool'],div[class*='card'],li[class*='tool'],a[href*='/tools/']",
        "h1,h2,h3,h4,h5,strong,.name,.title",
        "p,.desc,.description,.summary"
    )

def fetch_toolify():
    """Toolify.ai — RSS malformé mais parseable ; HTML derrière Cloudflare."""
    for rss in [
        "https://www.toolify.ai/rss",
        "https://www.toolify.ai/feed",
        "https://www.toolify.ai/rss.xml",
    ]:
        res = fetch_rss("Toolify.ai", rss)
        if res:
            return res
    return []

def fetch_producthunt():
    """Product Hunt — RSS fiable, filtré IA."""
    return fetch_rss(
        "Product Hunt",
        "https://www.producthunt.com/feed?category=artificial-intelligence",
        ai_filter=True
    )

# ── Main ───────────────────────────────────────────────────────────────────────

FETCHERS = [
    fetch_aixploria, fetch_taaift, fetch_futurepedia, fetch_futuretools,
    fetch_aisecret, fetch_aitoolsdirectory, fetch_powerfulai, fetch_aitoptools,
    fetch_aitoolssh, fetch_toolify, fetch_producthunt,
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
