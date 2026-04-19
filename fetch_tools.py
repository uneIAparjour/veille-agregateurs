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

CUTOFF_HOURS = 168   # 7 jours — large pour ne rien rater, dédoublonnage côté JSON
OUTPUT_FILE  = "tools.json"

# Headers complets imitant un vrai navigateur Chrome — évite la plupart des 403
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
    "Sec-Fetch-User":  "?1",
    "Cache-Control":   "max-age=0",
    "DNT":             "1",
}

# ── Catégories ─────────────────────────────────────────────────────────────────

CATEGORIES_KW = {
    "images":            ["image","photo","illustration","visual","artwork","dall-e","midjourney","stable diffusion","flux","generate image","picture"],
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

# Domaines des répertoires — leurs URLs internes ne sont pas des outils réels
DIRECTORY_DOMAINS = {
    "theresanaiforthat.com", "futurepedia.io", "futuretools.io",
    "aixploria.com", "aisecret.us", "aitoolsdirectory.com",
    "powerfulai.tools", "aitoptools.com", "aitools.sh",
    "toolify.ai", "producthunt.com", "therundown.ai",
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
    """True si l'URL pointe vers un vrai outil (pas une page interne d'un répertoire)."""
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

def get(url, session=None, referer=None, timeout=20):
    """HTTP GET avec headers complets et referer optionnel."""
    hdrs = dict(HEADERS)
    if referer:
        hdrs["Referer"] = referer
    requester = session or requests
    r = requester.get(url, headers=hdrs, timeout=timeout)
    r.raise_for_status()
    return r

def soup_get(url, session=None, referer=None):
    return BeautifulSoup(get(url, session, referer).text, "html.parser")

# ── Fetchers génériques ────────────────────────────────────────────────────────

def fetch_rss(source_name, rss_url, ai_filter=False, max_items=30):
    results = []
    try:
        # feedparser respecte les headers
        feed = feedparser.parse(rss_url, request_headers={
            "User-Agent": HEADERS["User-Agent"],
            "Accept": "application/rss+xml, application/xml, text/xml",
        })
        if feed.bozo and not feed.entries:
            raise Exception(f"Feed invalide: {feed.bozo_exception}")
        for entry in feed.entries[:max_items]:
            title    = entry.get("title", "").strip()
            url      = entry.get("link", "")
            desc     = BeautifulSoup(entry.get("summary","") or "", "html.parser").get_text(" ", strip=True)
            date_iso = parse_date(entry.get("published") or entry.get("updated",""))
            if not title or not url or not is_recent(date_iso):
                continue
            if ai_filter:
                combined = (title+" "+desc).lower()
                ai_kw = ["ai","artificial intelligence","machine learning","llm","gpt","generative",
                         "automation","chatbot","image generation","voice","neural","deep learning"]
                if not any(kw in combined for kw in ai_kw):
                    continue
            t = make_tool(title, url, desc, source_name, date_iso)
            results.append(t)
        print(f"  {source_name} (RSS): {len(results)}")
    except Exception as e:
        print(f"  {source_name} RSS erreur: {e}", file=sys.stderr)
    return results

def scrape_cards(source_name, url, base, card_sel, name_sel=None, desc_sel=None,
                 max_items=20, session=None):
    """Scraper générique — préfère les URLs externes pour chaque carte."""
    results, seen = [], set()
    try:
        page = soup_get(url, session=session, referer=base)
        for card in page.select(card_sel)[:max_items * 4]:
            ne   = card.select_one(name_sel) if name_sel else card
            name = ne.get_text(strip=True)[:80] if ne else card.get_text(strip=True)[:60]
            if not name or len(name) < 3:
                continue
            # Priorité URL externe, fallback URL interne
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

# ── Sources ─────────────────────────────────────────────────────────────────────

def fetch_aixploria():
    """WordPress FR — RSS très fiable."""
    # Essai RSS
    res = fetch_rss("Aixploria", "https://www.aixploria.com/fr/feed/")
    if res:
        return res
    # Fallback HTML si le RSS est vide
    return scrape_cards(
        "Aixploria", "https://www.aixploria.com/fr/derniers-ajouts/",
        "https://www.aixploria.com",
        "article,.post,.entry,[class*='post']",
        "h2,h3,.entry-title,.post-title", "p,.excerpt,.entry-summary"
    )

def fetch_taaift():
    """There's an AI for That — plusieurs endpoints RSS tentés."""
    for rss in [
        "https://theresanaiforthat.com/feed/",
        "https://theresanaiforthat.com/rss.xml",
        "https://theresanaiforthat.com/rss/",
    ]:
        res = fetch_rss("There's an AI for That", rss)
        if res:
            return res
    # HTML avec session pour contourner le 403
    try:
        session = requests.Session()
        session.headers.update(HEADERS)
        # Visite la page d'accueil d'abord pour obtenir des cookies
        session.get("https://theresanaiforthat.com/", timeout=15)
        time.sleep(1)
        return scrape_cards(
            "There's an AI for That",
            "https://theresanaiforthat.com/newest/",
            "https://theresanaiforthat.com",
            "a[href*='/ai/']", "h2,h3,.name,strong", "p,.description",
            session=session
        )
    except Exception as e:
        print(f"  There's an AI for That session erreur: {e}", file=sys.stderr)
        return []

def fetch_futurepedia():
    """Futurepedia — RSS puis API JSON puis HTML avec session."""
    for rss in [
        "https://www.futurepedia.io/rss.xml",
        "https://www.futurepedia.io/feed.xml",
        "https://www.futurepedia.io/feed",
    ]:
        res = fetch_rss("Futurepedia", rss)
        if res:
            return res
    # Essai API JSON (Next.js)
    try:
        r = get("https://www.futurepedia.io/api/tools?sort=newest&page=1&limit=20")
        data = r.json()
        tools_data = data.get("tools") or data.get("data") or (data if isinstance(data, list) else [])
        results = []
        for t in tools_data[:20]:
            name = t.get("name","").strip()
            url  = t.get("url") or t.get("website") or t.get("link","")
            desc = t.get("description","")
            if name and url:
                results.append(make_tool(name, url, desc, "Futurepedia"))
        if results:
            print(f"  Futurepedia (API): {len(results)}")
            return results
    except Exception:
        pass
    # HTML avec session
    try:
        session = requests.Session()
        session.headers.update(HEADERS)
        session.get("https://www.futurepedia.io/", timeout=15)
        time.sleep(1)
        return scrape_cards(
            "Futurepedia",
            "https://www.futurepedia.io/ai-tools?sort=newest",
            "https://www.futurepedia.io",
            "[class*='tool'],[class*='card'],[class*='item']",
            "h2,h3,h4,[class*='name'],[class*='title']",
            "p,[class*='desc'],[class*='summary']",
            session=session
        )
    except Exception as e:
        print(f"  Futurepedia session erreur: {e}", file=sys.stderr)
        return []

def fetch_futuretools():
    """Future Tools — RSS puis HTML."""
    for rss in [
        "https://futuretools.io/feed",
        "https://futuretools.io/rss.xml",
        "https://futuretools.io/rss",
    ]:
        res = fetch_rss("Future Tools", rss)
        if res:
            return res
    return scrape_cards(
        "Future Tools", "https://futuretools.io/",
        "https://futuretools.io",
        "a[href*='/tools/']", "h2,h3,.name,strong", "p,.desc"
    )

def fetch_aisecret():
    """AI Secret — section DAILY TL;DR uniquement.
    Seuls les liens externes dans ce bloc sont retenus."""
    results, seen = [], set()
    try:
        page = soup_get("https://aisecret.us/")
        # Localise le bloc DAILY TL;DR
        tldr_container = None
        for el in page.find_all(["h1","h2","h3","h4","h5","div","section","article"]):
            txt = el.get_text(strip=True).lower()
            if "daily tl;dr" in txt or "daily tldr" in txt or "tl;dr" in txt:
                tldr_container = el.find_parent(["section","article","div"]) or el
                break
        if not tldr_container:
            print("  AI Secret : section DAILY TL;DR introuvable", file=sys.stderr)
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
    """aitoolsdirectory.com — RSS puis HTML filtré Free+Freemium."""
    for rss in [
        "https://aitoolsdirectory.com/rss",
        "https://aitoolsdirectory.com/feed",
        "https://aitoolsdirectory.com/rss.xml",
    ]:
        res = fetch_rss("AI Tools Directory", rss)
        if res:
            return res
    return scrape_cards(
        "AI Tools Directory",
        "https://aitoolsdirectory.com/?filter=Price-%3AFree,Freemium",
        "https://aitoolsdirectory.com",
        "a[href],article,.tool,.card,[class*='tool'],[class*='card']",
        "h2,h3,h4,.name,.title,strong",
        "p,.desc,.description"
    )

def fetch_powerfulai():
    """powerfulai.tools — session avec cookies pour contourner le 403."""
    results = []
    try:
        session = requests.Session()
        session.headers.update(HEADERS)
        # Visite la page d'accueil pour obtenir des cookies
        session.get("https://www.powerfulai.tools/", timeout=15)
        time.sleep(1.5)
        seen = set()
        for label, url in [
            ("Free",    "https://www.powerfulai.tools/?filter=Free"),
            ("Freemium","https://www.powerfulai.tools/?filter=Freemium"),
        ]:
            try:
                page = soup_get(url, session=session, referer="https://www.powerfulai.tools/")
                for card in page.select("a[href],article,.tool,.card,[class*='tool'],[class*='card']")[:60]:
                    href = card.get("href","") if card.name=="a" else ""
                    if not href:
                        a = card.find("a"); href = a.get("href","") if a else ""
                    ne   = card.select_one("h2,h3,h4,.name,.title,strong") or card
                    name = ne.get_text(strip=True)[:80]
                    de   = card.select_one("p,.desc,.description,.summary")
                    desc = de.get_text(" ",strip=True)[:300] if de else ""
                    # Préfère URL externe
                    ext_url = int_url = None
                    for a in card.find_all("a", href=True):
                        full = urljoin("https://www.powerfulai.tools", a["href"])
                        if is_external(full) and not ext_url:
                            ext_url = full
                        elif not int_url:
                            int_url = full
                    tool_url = ext_url or int_url or url
                    if not name or len(name)<3 or tool_url in seen:
                        continue
                    seen.add(tool_url)
                    results.append(make_tool(name, tool_url, desc, "Powerful AI Tools"))
                    if len(results) >= 20:
                        break
                print(f"  Powerful AI Tools ({label}): ok")
            except Exception as e:
                print(f"  Powerful AI Tools ({label}) erreur: {e}", file=sys.stderr)
            time.sleep(1.5)
    except Exception as e:
        print(f"  Powerful AI Tools session erreur: {e}", file=sys.stderr)
    return results

def fetch_aitoptools():
    """aitoptools.com/free-ai-tools/ — scraping 2 niveaux, URLs externes uniquement."""
    BASE  = "https://aitoptools.com"
    INDEX = f"{BASE}/free-ai-tools/"
    results, seen_urls, seen_names = [], set(), set()

    def extract_from(page_soup, max_tools=8):
        found = []
        for card in page_soup.select("article,.tool,.card,[class*='tool'],[class*='card'],[class*='item']")[:40]:
            ne   = card.select_one("h2,h3,h4,.name,.title,strong")
            name = ne.get_text(strip=True)[:80] if ne else ""
            if not name or len(name) < 3:
                continue
            ext_url = None
            for a in card.find_all("a", href=True):
                full = urljoin(BASE, a["href"])
                if is_external(full):
                    ext_url = full; break
            if not ext_url:
                for attr in ["data-url","data-href","data-link","data-website"]:
                    val = card.get(attr,"")
                    if val and is_external(val):
                        ext_url = val; break
            if not ext_url:
                continue
            de   = card.select_one("p,.desc,.description,.summary")
            desc = de.get_text(" ",strip=True)[:300] if de else ""
            nk   = name.lower().replace(" ","")
            if ext_url in seen_urls or nk in seen_names:
                continue
            seen_urls.add(ext_url); seen_names.add(nk)
            found.append(make_tool(name, ext_url, desc, "AI Top Tools"))
            if len(found) >= max_tools:
                break
        return found

    try:
        index_page = soup_get(INDEX)
        cat_links  = []
        for a in index_page.select("a[href*='/free-ai-tools/']"):
            full = urljoin(BASE, a.get("href",""))
            if full != INDEX and full not in cat_links and len(full) > len(INDEX):
                cat_links.append(full)
        cat_links = cat_links[:6]
        print(f"  AI Top Tools — {len(cat_links)} catégories")
        results.extend(extract_from(index_page, max_tools=5))
        for cat_url in cat_links:
            try:
                results.extend(extract_from(soup_get(cat_url, referer=INDEX), max_tools=5))
            except Exception as e:
                print(f"    Cat {cat_url} erreur: {e}", file=sys.stderr)
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
        "a[href*='/tools/'],a[href*='/ai/'],article,.tool,[class*='tool'],[class*='card']",
        "h2,h3,h4,.name,.title,strong", "p,.desc,.description"
    )

def fetch_toolify():
    """Toolify.ai — RSS puis session HTML pour les 403."""
    for rss in [
        "https://www.toolify.ai/rss",
        "https://www.toolify.ai/feed",
        "https://www.toolify.ai/rss.xml",
        "https://www.toolify.ai/sitemap-tools.xml",
    ]:
        res = fetch_rss("Toolify.ai", rss)
        if res:
            return res
    try:
        session = requests.Session()
        session.headers.update(HEADERS)
        session.get("https://www.toolify.ai/", timeout=15)
        time.sleep(1.5)
        return scrape_cards(
            "Toolify.ai", "https://www.toolify.ai/new",
            "https://www.toolify.ai",
            "a[href*='/tool/'],a[href*='/ai/'],article,.tool,[class*='tool']",
            "h2,h3,h4,.name,.title,strong", "p,.desc,.description",
            session=session
        )
    except Exception as e:
        print(f"  Toolify.ai session erreur: {e}", file=sys.stderr)
        return []

def fetch_producthunt():
    """Product Hunt — RSS officiel filtré IA, très fiable."""
    for rss in [
        "https://www.producthunt.com/feed?category=artificial-intelligence",
        "https://www.producthunt.com/feed",
    ]:
        res = fetch_rss("Product Hunt", rss, ai_filter=True)
        if res:
            return res
    return []

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
        nk = re.sub(r"[\s\-_]", "", t["name"].lower())
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
