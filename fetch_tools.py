#!/usr/bin/env python3
"""
fetch_tools.py — Veille quotidienne outils IA (uneiaparjour.fr)
11 sources — génère tools.json pour GitHub Pages
"""
import json, re, time, sys
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin

import requests
import feedparser
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/123.0 Safari/537.36"
}
CUTOFF_HOURS = 72
OUTPUT_FILE  = "tools.json"

CATEGORIES_KW = {
    "images":            ["image","photo","illustration","visual","artwork","dall-e","midjourney","stable diffusion","flux","generate image"],
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

def guess_categories(text):
    low = text.lower()
    seen, hits = set(), []
    for cat, kws in CATEGORIES_KW.items():
        if cat not in seen and any(kw in low for kw in kws):
            hits.append(cat)
            seen.add(cat)
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

def soup(url):
    r = requests.get(url, headers=HEADERS, timeout=18)
    r.raise_for_status()
    return BeautifulSoup(r.text, "html.parser")

def make_tool(name, url, desc, source):
    return {
        "name": name[:100].strip(),
        "tool_url": norm_url(url),
        "description": re.sub(r'\s+', ' ', desc[:400]).strip(),
        "source": source,
        "date_iso": datetime.now(timezone.utc).isoformat(),
        "categories": guess_categories(name + " " + desc),
    }

# ── Fetchers ───────────────────────────────────────────────────────────────────

def fetch_rss(source_name, rss_url, ai_filter=False, max_items=20):
    results = []
    try:
        feed = feedparser.parse(rss_url)
        for entry in feed.entries[:max_items]:
            title = entry.get("title","").strip()
            url   = entry.get("link","")
            desc  = BeautifulSoup(entry.get("summary","") or "", "html.parser").get_text(" ", strip=True)
            date_iso = parse_date(entry.get("published") or entry.get("updated",""))
            if not title or not url or not is_recent(date_iso):
                continue
            if ai_filter:
                combined = (title+" "+desc).lower()
                ai_kw = ["ai","artificial intelligence","machine learning","llm","gpt","generative","automation","chatbot","image generation","voice"]
                if not any(kw in combined for kw in ai_kw):
                    continue
            t = make_tool(title, url, desc, source_name)
            t["date_iso"] = date_iso or t["date_iso"]
            results.append(t)
        print(f"  {source_name} (RSS): {len(results)}")
    except Exception as e:
        print(f"  {source_name} RSS erreur: {e}", file=sys.stderr)
    return results

def scrape_cards(source_name, url, base, card_sel, name_sel=None, desc_sel=None, max_items=18):
    results, seen = [], set()
    try:
        page = soup(url)
        for card in page.select(card_sel)[:max_items*3]:
            ne = card.select_one(name_sel) if name_sel else card
            name = ne.get_text(strip=True)[:80] if ne else card.get_text(strip=True)[:60]
            if not name or len(name) < 3:
                continue
            a = card if card.name == "a" else card.find("a")
            href = a.get("href","") if a else ""
            tool_url = urljoin(base, href) if href else url
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

# ── 11 sources ─────────────────────────────────────────────────────────────────

def fetch_aixploria():
    return fetch_rss("Aixploria", "https://www.aixploria.com/fr/feed/")

def fetch_taaift():
    res = fetch_rss("There's an AI for That", "https://theresanaiforthat.com/rss/")
    return res or scrape_cards(
        "There's an AI for That", "https://theresanaiforthat.com/newest/",
        "https://theresanaiforthat.com",
        "a[href*='/ai/']", "h2,h3,.name,strong", "p,.description"
    )

def fetch_futurepedia():
    res = fetch_rss("Futurepedia", "https://www.futurepedia.io/rss.xml")
    return res or scrape_cards(
        "Futurepedia", "https://www.futurepedia.io/ai-tools?sort=newest",
        "https://www.futurepedia.io",
        "[class*='tool'],[class*='card']", "h2,h3,h4,[class*='name']", "p,[class*='desc']"
    )

def fetch_futuretools():
    res = fetch_rss("Future Tools", "https://futuretools.io/feed")
    return res or scrape_cards(
        "Future Tools", "https://futuretools.io/",
        "https://futuretools.io",
        "a[href*='/tools/']", "h2,h3,.name,strong", "p,.desc"
    )

def fetch_aisecret():
    return scrape_cards(
        "AI Secret", "https://aisecret.us/",
        "https://aisecret.us",
        "a[href*='/tool/'],a[href*='/ai/'],article,.tool-card", "h2,h3,.name", "p,.description"
    )

def fetch_aitoolsdirectory():
    """aitoolsdirectory.com — filtrée Free+Freemium."""
    results, seen = [], set()
    try:
        page = soup("https://aitoolsdirectory.com/?filter=Price-%3AFree,Freemium")
        # Essai RSS d'abord
        rss = fetch_rss("AI Tools Directory", "https://aitoolsdirectory.com/rss", max_items=20)
        if rss:
            return rss
        for card in page.select("a[href],article,.tool,.card,[class*='tool'],[class*='card']")[:60]:
            href = card.get("href","") if card.name=="a" else ""
            if not href:
                a = card.find("a"); href = a.get("href","") if a else ""
            ne = card.select_one("h2,h3,h4,.name,.title,strong") or card
            name = ne.get_text(strip=True)[:80]
            de = card.select_one("p,.desc,.description")
            desc = de.get_text(" ",strip=True)[:300] if de else ""
            tool_url = urljoin("https://aitoolsdirectory.com", href) if href else "https://aitoolsdirectory.com"
            if not name or len(name)<3 or tool_url in seen: continue
            seen.add(tool_url)
            results.append(make_tool(name, tool_url, desc, "AI Tools Directory"))
            if len(results)>=15: break
        print(f"  AI Tools Directory (HTML): {len(results)}")
    except Exception as e:
        print(f"  AI Tools Directory erreur: {e}", file=sys.stderr)
    return results

def fetch_powerfulai():
    """powerfulai.tools — Free et Freemium."""
    results = []
    for label, url in [("Free","https://www.powerfulai.tools/?filter=Free"),
                        ("Freemium","https://www.powerfulai.tools/?filter=Freemium")]:
        seen = set()
        try:
            page = soup(url)
            for card in page.select("a[href],article,.tool,.card,[class*='tool']")[:60]:
                href = card.get("href","") if card.name=="a" else ""
                if not href:
                    a = card.find("a"); href = a.get("href","") if a else ""
                ne = card.select_one("h2,h3,h4,.name,.title,strong") or card
                name = ne.get_text(strip=True)[:80]
                de = card.select_one("p,.desc,.description,.summary")
                desc = de.get_text(" ",strip=True)[:300] if de else ""
                tool_url = urljoin("https://www.powerfulai.tools", href) if href else url
                if not name or len(name)<3 or tool_url in seen: continue
                seen.add(tool_url)
                results.append(make_tool(name, tool_url, desc, "Powerful AI Tools"))
                if len(results)>=15: break
            print(f"  Powerful AI Tools ({label}): {len(seen)}")
        except Exception as e:
            print(f"  Powerful AI Tools ({label}) erreur: {e}", file=sys.stderr)
        time.sleep(1)
    return results

def fetch_aitoptools():
    """aitoptools.com — hash-based filters, on scrape la page et filtre Free/Freemium."""
    results, seen = [], set()
    try:
        page = soup("https://aitoptools.com/")
        for card in page.select("article,.tool,.card,[class*='tool'],[class*='item'],a[href]")[:80]:
            text = card.get_text(" ", strip=True)
            if "free" not in text.lower() and "freemium" not in text.lower():
                continue
            href = card.get("href","") if card.name=="a" else ""
            if not href:
                a = card.find("a"); href = a.get("href","") if a else ""
            ne = card.select_one("h2,h3,h4,.name,.title,strong") or card
            name = ne.get_text(strip=True)[:80]
            de = card.select_one("p,.desc,.description")
            desc = de.get_text(" ",strip=True)[:300] if de else ""
            tool_url = urljoin("https://aitoptools.com", href) if href else "https://aitoptools.com"
            if not name or len(name)<3 or tool_url in seen: continue
            seen.add(tool_url)
            results.append(make_tool(name, tool_url, desc, "AI Top Tools"))
            if len(results)>=15: break
        print(f"  AI Top Tools (HTML): {len(results)}")
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
    """Toolify.ai/new — nouveaux outils."""
    res = fetch_rss("Toolify.ai", "https://www.toolify.ai/rss")
    return res or scrape_cards(
        "Toolify.ai", "https://www.toolify.ai/new",
        "https://www.toolify.ai",
        "a[href*='/tool/'],a[href*='/ai/'],article,.tool,[class*='tool']",
        "h2,h3,h4,.name,.title,strong", "p,.desc,.description"
    )

def fetch_producthunt():
    """Product Hunt — RSS officiel filtré IA."""
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
        nk = re.sub(r'[\s\-]','', t["name"].lower())
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
        time.sleep(1.5)

    all_tools = deduplicate(all_tools)
    all_tools.sort(key=lambda t: t.get("date_iso",""), reverse=True)
    all_tools = [t for t in all_tools if len(t["name"].strip()) >= 3]

    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "count": len(all_tools),
        "tools": all_tools,
    }
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\nTotal : {len(all_tools)} outils — {OUTPUT_FILE} mis à jour")

if __name__ == "__main__":
    main()
