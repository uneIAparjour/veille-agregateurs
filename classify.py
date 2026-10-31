#!/usr/bin/env python3
"""
classify.py — Tri automatique des entrées de la veille (uneiaparjour.fr)

Pour chaque entrée, calcule :
  kind     : "outil" | "article" | "expert"
  pricing  : "free" | "freemium" | "paid" | "unknown"  (affiné par le texte)
  verdict  : "keep" (retenu) | "review" (à vérifier) | "drop" (écarté)
  why      : liste de raisons courtes, affichées dans l'interface

Principe : un mot-clé « fort » suffit à trancher ; un mot-clé « faible »
(ex. "api", "open source") ne fait que renvoyer l'entrée dans « à vérifier ».
Rien n'est supprimé : tout reste consultable, avec la raison du classement.

Tous les motifs sont bornés par \\b (mot entier) pour éviter les faux positifs
("cli" dans "client", "api" dans "capital", "free" dans "carefree").
"""
import re
from urllib.parse import urlparse

def _rx(words):
    return re.compile(r"(?<![\w-])(?:" + "|".join(words) + r")(?![\w-])", re.IGNORECASE)

# ── Articles / actualité (pas un outil) ────────────────────────────────────────

# Sources qui publient de l'actualité, pas des fiches d'outils.
NEWS_SOURCES = {"TechCrunch AI", "The Rundown AI", "Ben's Bites", "TLDR AI", "Lobsters",
                "ActuIA", "Siècle Digital", "The Verge AI", "AI Secret",
                "MTD Technologies", "The Tool Nerd"}

ARTICLE_TITLE = _rx([
    r"raises?\s+\$?[\d.,]+\s*[mbk]?", r"raises?\s+(?:a\s+)?(?:seed|series|pre-seed)",
    r"series\s+[a-e]\b", r"seed\s+round", r"pre-seed", r"funding(?:\s+round)?", r"valuation",
    r"acquires?", r"acquired\s+by", r"acquisition", r"buys?\s+\w+", r"merger",
    r"ipo", r"layoffs?", r"lawsuit", r"sues?", r"sued", r"fined", r"antitrust",
    r"regulat(?:ion|ors?|ory)", r"ban(?:s|ned)?\s+(?:ai|chatgpt)",
    r"investors?", r"invests?\s+\$?[\d.,]+", r"billions?", r"millions?", r"\$[\d.,]+\s*[mbk]\b",
    r"opinion", r"podcast", r"interview", r"weekly\s+(?:digest|recap|roundup)",
    r"newsletter", r"roundup", r"recap", r"this\s+week", r"digest",
    r"why\s+\w+", r"what\s+(?:is|are|happens|you\s+need)", r"how\s+(?:to|i|we|does|do)\b",
    r"guide\s+to", r"tutorial", r"explained", r"vs\.?", r"versus", r"review\s*:",
    r"(?:honest|full|my)\s+review", r"best\s+.{0,40}\s+(?:in\s+)?20\d\d", r"alternatives?\s+to",
    r"announces?", r"unveils?", r"reports?\s+(?:says|shows)", r"according\s+to", r"says\b",
    r"ceo", r"cto", r"founder\s+of", r"hires?", r"appoints?", r"partners?\s+with",
    r"nvidia\s+stock", r"stocks?\b", r"data\s*cent(?:er|re)s?", r"electricity", r"jobs?\s+report",
    r"^\W*\d+\s+(?:\w+\s+){0,2}(?:ways|ideas|things|tips|reasons|lessons|mistakes|tricks|hacks|apps|websites|sites)",
    r"make\s+money", r"money\s+with", r"side\s+hustles?", r"passive\s+income", r"how\s+much\s+to\s+charge",
    r"\(part\s+\d+\)", r"as\s+you\s+know\s+it", r"is\s+(?:basically|now|finally)\s+\w+",
    r"élections?", r"gouvernement", r"levée\s+de\s+fonds", r"rachète", r"milliards?",
])

# Un titre se terminant par « ? » est presque toujours un article.
QUESTION_TITLE = re.compile(r"\?\s*$")

# Lancement explicite : à vérifier plutôt qu'à écarter, même depuis une source news.
LAUNCH_TITLE = _rx([r"launch(?:es|ed)?", r"introduc(?:es|ing)", r"releases?", r"debuts?", r"now\s+available",
                    r"lance", r"dévoile"])

# ── Contenu adulte : jamais pour le site ───────────────────────────────────────

NSFW = _rx([r"porn\w*", r"nsfw", r"nudes?", r"undress(?:ing)?", r"deepnude", r"hentai", r"erotic\w*", r"xxx",
            r"sex(?:ual|y|ting|bot)?", r"adult\s+content", r"onlyfans", r"waifu", r"girlfriend\s+(?:ai|bot|simulator)",
            r"ai\s+girlfriend", r"face\s*swap\s+porn", r"18\+", r"uncensored"])

# ── Trop technique (expert) ────────────────────────────────────────────────────

# Fort : un seul suffit. Vocabulaire développeur / infra qui n'a pas sa place
# dans « Une IA par jour » (grand public / enseignants).
EXPERT_STRONG = _rx([
    r"mcp", r"model\s+context\s+protocol", r"sdk", r"cli", r"command[\s-]line", r"terminal",
    r"docker(?:file)?", r"kubernetes", r"k8s", r"helm", r"terraform", r"devops", r"ci/cd",
    r"npm", r"pnpm", r"yarn", r"pypi", r"pip\s+install", r"cargo", r"crates\.io", r"homebrew",
    r"self[\s-]?host(?:ed|ing)?", r"on[\s-]prem(?:ise)?", r"open[\s-]weights?",
    r"fine[\s-]?tun(?:e|ing|ed)", r"quantiz(?:ed|ation)", r"inference\s+(?:engine|server|api)",
    r"vector\s+(?:database|db|store)", r"embeddings?", r"rag\s+(?:pipeline|framework)",
    r"llm\s+(?:gateway|proxy|observability|router|routing|ops|eval(?:uation)?s?)",
    r"observability", r"orchestrat(?:or|ion)\s+(?:framework|layer)", r"agent\s+(?:framework|sdk|runtime|harness|swarm)",
    r"langchain", r"llamaindex", r"langgraph", r"ollama", r"vllm", r"llama\.cpp", r"gguf",
    r"for\s+developers", r"developer[\s-](?:tool|platform|first|experience)", r"dev\s?tools?",
    r"vs\s?code", r"vscode", r"neovim", r"jetbrains", r"ide\s+(?:plugin|extension)",
    r"pull\s+requests?", r"code\s+review", r"compiler", r"linter", r"refactor(?:ing)?",
    r"backend", r"back-end", r"microservices?", r"serverless", r"postgres(?:ql)?", r"sqlite",
    r"kernel", r"rust", r"golang", r"typescript\s+(?:library|package|sdk)", r"python\s+(?:library|package|sdk)",
    r"webhooks?", r"graphql", r"rest\s+api", r"json\s+schema", r"yaml", r"regex",
    r"github\s+(?:action|actions|copilot|repo|repository)", r"gitlab", r"git\s+(?:commit|workflow)",
    r"jailbreak", r"red[\s-]team(?:ing)?", r"prompt\s+injection", r"cve-\d+",
])

# Faible : à lui seul, ne tranche pas (beaucoup d'outils grand public ont une « API »).
EXPERT_WEAK = _rx([
    r"api", r"apis", r"open[\s-]source", r"library", r"framework", r"agents?", r"agentic",
    r"rag", r"llms?", r"install(?:ation)?", r"plugin", r"extension", r"automation", r"workflow",
    r"integration", r"benchmark", r"model\s+weights", r"hugging\s?face", r"repo",
])

# Domaines qui signalent un projet de développeur plutôt qu'un outil grand public.
EXPERT_HOSTS = ("github.com", "gitlab.com", "bitbucket.org", "npmjs.com", "pypi.org",
                "crates.io", "pkg.go.dev", "docs.rs", "readthedocs.io", "sourceforge.net",
                "huggingface.co/models", "huggingface.co/datasets", "arxiv.org", "dev.to")

# ── Prix ───────────────────────────────────────────────────────────────────────

# Gratuit explicite. « free » seul est volontairement absent : trop ambigu
# (« free up », « ad-free », « hands-free », « risk-free », « free-form »).
FREE_STRICT = _rx([
    r"100\s?%\s*free", r"completely\s+free", r"totally\s+free", r"entirely\s+free", r"always\s+free",
    r"free\s+forever", r"forever\s+free", r"free\s+to\s+use", r"free\s+of\s+charge", r"free\s+for\s+everyone",
    r"free\s+online(?:\s+tool)?", r"free\s+ai\s+(?:tool|generator|app|assistant|writer|chatbot)",
    r"no\s+(?:credit\s+card|signup|sign-up|login|account|payment)\s+(?:needed|required)",
    r"without\s+(?:signing\s+up|an?\s+account|registration)", r"gratuit(?:e|ement|s)?", r"sans\s+(?:inscription|compte|carte)",
    r"no\s+cost",
])
FREEMIUM = _rx([
    r"freemium", r"free\s+(?:plan|tier|version|forever\s+plan|starter\s+plan)", r"generous\s+free",
    r"free\s+(?:credits?|monthly\s+credits?|generations?|quota)", r"free\s+with\s+(?:limits|ads|premium)",
    r"basic\s+(?:plan\s+)?is\s+free", r"offre\s+gratuite", r"version\s+gratuite", r"plan\s+gratuit",
    r"free\s+\+\s*(?:paid|premium|pro)", r"free\s+and\s+(?:paid|premium|pro)\s+plans?", r"free,\s+(?:pro|premium|paid)",
])
# Essai gratuit ≠ gratuit : ce n'est pas un free/freemium pour le site.
TRIAL = _rx([r"free\s+trial", r"\d+[\s-]day\s+(?:free\s+)?trial", r"try\s+(?:it\s+)?free\s+for", r"essai\s+gratuit",
             r"money[\s-]back\s+guarantee", r"free\s+demo", r"book\s+a\s+demo", r"request\s+a\s+demo"])
PAID = _rx([
    r"paid\s+(?:only|tool|plan\s+only|subscription)", r"subscription\s+(?:only|required)", r"no\s+free\s+(?:plan|tier|version)",
    r"starting\s+(?:at|from)\s+\$\s?\d+", r"from\s+\$\s?\d+(?:\.\d+)?\s*/\s*(?:mo|month|user|seat|year|yr)",
    r"\$\s?\d+(?:\.\d+)?\s*/\s*(?:mo|month|user|seat|year|yr)", r"\$\s?\d+(?:\.\d+)?\s*per\s+(?:month|user|seat|year)",
    r"€\s?\d+(?:[.,]\d+)?\s*/\s*(?:mois|an|mo|month)", r"à\s+partir\s+de\s+\d+\s?€", r"enterprise[\s-]grade",
    r"for\s+(?:teams|enterprises?)\b", r"contact\s+(?:sales|us\s+for\s+pricing)", r"custom\s+pricing", r"premium\s+only",
    r"payant", r"abonnement\s+obligatoire",
])

# Sources dont le champ prix est structuré (fiable) et non déduit du texte.
STRUCTURED_PRICING_SOURCES = {"FutureTools", "There's an AI"}

# Sources mixtes : produit ou discussion, outil ou projet de développeur ?
MIXED_SOURCES = {"Hacker News", "Product Hunt", "GitHub Trending"}

# ── Utilitaires ────────────────────────────────────────────────────────────────

def _host(url):
    try:
        return urlparse(url or "").netloc.lower().removeprefix("www.")
    except Exception:
        return ""

def _is_expert_host(url):
    u = (url or "").lower()
    return any(h in u.split("//", 1)[-1].removeprefix("www.") for h in EXPERT_HOSTS)

def _hits(rx, text, limit=3):
    seen, out = set(), []
    for m in rx.finditer(text):
        w = re.sub(r"\s+", " ", m.group(0).lower())
        if w not in seen:
            seen.add(w); out.append(w)
        if len(out) >= limit:
            break
    return out

def detect_pricing(tool, text):
    """Retourne (pricing, raison|None). Respecte le prix structuré de la source."""
    src = tool.get("source", "")
    current = tool.get("pricing", "unknown")
    if src in STRUCTURED_PRICING_SOURCES and current in ("free", "freemium", "paid"):
        return current, f"prix {current} (source {src})"
    if (h := _hits(FREEMIUM, text)):
        return "freemium", f"freemium : « {h[0]} »"
    if (h := _hits(FREE_STRICT, text)):
        return "free", f"gratuit : « {h[0]} »"
    if (h := _hits(PAID, text)):
        return "paid", f"payant : « {h[0]} »"
    if (h := _hits(TRIAL, text)):
        return "unknown", f"essai gratuit seulement : « {h[0]} »"
    return "unknown", None

# ── Classement ─────────────────────────────────────────────────────────────────

def classify(tool):
    title = (tool.get("name") or "").strip()
    desc  = (tool.get("description") or "").strip()
    text  = f"{title}. {desc}"
    src   = tool.get("source", "")
    url   = tool.get("tool_url", "")
    why, review = [], []

    pricing, price_reason = detect_pricing(tool, text)

    # 0. Contenu adulte
    nsfw = _hits(NSFW, text, limit=1)
    if nsfw:
        return {"kind": "outil", "pricing": pricing, "verdict": "drop", "why": [f"contenu adulte : « {nsfw[0]} »"]}

    # 1. Article ?
    art_hits = _hits(ARTICLE_TITLE, title)
    is_question = bool(QUESTION_TITLE.search(title))
    launch = bool(LAUNCH_TITLE.search(title))
    if art_hits or is_question:
        kind = "article"
        why.append("article : « " + (art_hits[0] if art_hits else "titre en question") + " »")
    elif src in NEWS_SOURCES:
        kind = "article"
        why.append(f"source d'actualité ({src})")
    else:
        kind = "outil"

    # Un lancement explicite depuis une source news ou un titre ambigu : à vérifier.
    if kind == "article" and launch and not art_hits:
        kind = "outil"; review.append("lancement dans une source d'actualité")

    # 2. Expert ?
    strong = _hits(EXPERT_STRONG, text, limit=3)
    weak   = _hits(EXPERT_WEAK, text, limit=3)
    expert_host = _is_expert_host(url)
    if kind != "article":
        if expert_host:
            kind = "expert"; why.append(f"expert : lien {_host(url)}")
        elif strong:
            kind = "expert"; why.append("expert : « " + ", ".join(strong[:2]) + " »")
        elif len(weak) >= 3:
            review.append("vocabulaire technique : " + ", ".join(weak))

    # 3. Prix
    if price_reason:
        why.append(price_reason)

    # 4. Verdict
    if kind in ("article", "expert"):
        verdict = "drop"
    elif pricing == "paid":
        verdict = "drop"
    else:
        # Ambiguïtés → à vérifier
        if pricing == "unknown":
            review.append("prix inconnu")
        # Un titre-phrase (≥ 7 mots, sans séparateur « | – : ») est plus souvent un
        # article qu'un nom d'outil avec son slogan.
        if len(title.split()) >= 7 and not re.search(r"\s[|–—:·-]\s|:\s", title):
            review.append("titre en phrase : article ?")
        if len(desc) < 40:
            review.append("description absente ou trop courte")
        if src in MIXED_SOURCES:
            review.append(f"source mixte ({src})")
        if weak and len(weak) < 3 and "api" in [w.lower() for w in weak]:
            review.append("mentionne une API")
        if _host(url) in ("producthunt.com", "ycombinator.com", "news.ycombinator.com"):
            review.append("lien vers l'annuaire, pas vers l'outil")
        verdict = "review" if review else "keep"
        if verdict == "keep" and pricing in ("free", "freemium"):
            pass
        why.extend(review)

    return {"kind": kind, "pricing": pricing, "verdict": verdict, "why": why[:5]}

def apply(tool):
    tool.update(classify(tool))
    return tool

if __name__ == "__main__":
    # python3 classify.py [tools.json] [--write] : statistiques (et réécriture)
    import json, sys, collections
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    path = args[0] if args else "tools.json"
    d = json.load(open(path, encoding="utf-8"))
    ts = [apply(dict(t)) for t in d["tools"]]
    if "--write" in sys.argv:
        d["tools"] = ts
        d["verdicts"] = dict(collections.Counter(t["verdict"] for t in ts))
        json.dump(d, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(collections.Counter(t["verdict"] for t in ts))
    print(collections.Counter(t["kind"] for t in ts))
    print(collections.Counter(t["pricing"] for t in ts))
