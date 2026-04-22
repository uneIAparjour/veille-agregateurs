# Veille agrégateurs — uneiaparjour.fr

Outil de veille quotidienne pour [uneiaparjour.fr](https://www.uneiaparjour.fr). Agrège les nouveaux outils IA publiés sur une trentaine de répertoires sources, génère un fichier `tools.json` mis à jour chaque soir, et expose une interface de triage via GitHub Pages.

**Interface** → [uneiaparjour.github.io/veille-agregateurs](https://uneiaparjour.github.io/veille-agregateurs)

---

## Fonctionnement

```
GitHub Actions (20h chaque soir)
    ↓
fetch_tools.py
    ↓ interroge ~39 sources (RSS, WP API, JSON API, scraping HTML)
tools.json  ←  commit automatique si changement
    ↓
index.html  ←  lit tools.json via fetch(), affiche les cartes
```

Le script Python tourne côté serveur (GitHub Actions), sans contrainte de CORS ni de restriction IP. L'interface HTML est statique et ne fait qu'une seule requête : lire `tools.json`.

---

## Structure du dépôt

```
📄 index.html              ← Interface GitHub Pages (lecture tools.json)
📄 fetch_tools.py          ← Script de collecte (39 sources)
📄 tools.json              ← Données générées automatiquement
📄 README.md               ← Ce fichier
📁 .github/workflows/
    fetch-tools.yml        ← Déclenchement nightly 20h + manuel
```

---

## Sources (39)

Les sources sont classées par stratégie d'accès. Certaines sont bloquées par Cloudflare depuis les IPs GitHub Actions et retournent 0 résultats — elles sont conservées car les IPs peuvent changer.

### Sources fiables (RSS / API officielle)

| Source | Méthode |
|--------|---------|
| Product Hunt AI | RSS officiel — URL réelle extraite du HTML de la description |
| Hacker News | API Algolia `tags=show_hn` — filtrée sur titres IA |
| BetaList | RSS public — filtrée sur contenu IA |
| GitHub Topics AI | Atom feed public `topics/artificial-intelligence` |
| Reddit r/aitools | JSON API public — liens externes uniquement |
| The Rundown AI | RSS newsletter — liens outils extraits du contenu |

### Répertoires — WP REST API

| Source | URL |
|--------|-----|
| Aixploria | aixploria.com |
| aiapp.fr | aiapp.fr |
| iaweb.fr | iaweb.fr |
| WikiAI Tools | wikiaitools.com |
| Best of AI | bestofai.com |
| Notable AI | noteableai.com |
| AI Tool Guru | aitoolguru.com |
| Best Free AI | bestfreeaiwebsites.com |
| HD Robots | hdrobots.com |
| Tools Story | toolsstory.net |
| Free AI Tools Directory | free-ai-tools-directory.com |
| Mad Genius | madgenius.co |
| AI Tools LOL | aitools.lol |
| AI Finder | ai-finder.net |
| AI Tool Hunt | aitoolhunt.com |
| AI Tool Board | aitoolboard.com |
| Fastpedia | fastpedia.io |

### Répertoires — API JSON / Next.js

| Source | URL |
|--------|-----|
| There's an AI for That | theresanaiforthat.com |
| Futurepedia | futurepedia.io |
| OpenFuture AI | openfuture.ai/fr |
| AI Tool Net | aitoolnet.com |
| dang.ai | dang.ai |
| AI Tools FYI | aitools.fyi |
| AI Scout | aiscout.net |
| AI Library | ailibrary.io |
| AI Center | aicenter.ai |
| ToolScout | toolscout.ai |
| Toolspedia | toolspedia.io |
| Faind.ai | faind.ai |

### Répertoires — scraping HTML

| Source | URL |
|--------|-----|
| AI Top Tools | aitoptools.com/free-ai-tools/ |
| AI Secret (DAILY TL;DR) | aisecret.us |
| AI of the Day | aioftheday.com |

### Sources bloquées Cloudflare (0 résultats depuis GitHub Actions)

futuretools.io · powerfulai.tools · toolify.ai · aitoolsdirectory.com · aitools.sh

---

## Format de tools.json

```json
{
  "generated_at": "2026-04-22T18:00:00+00:00",
  "count": 87,
  "tools": [
    {
      "name": "Nom de l'outil",
      "tool_url": "https://site-de-loutil.com",
      "description": "Description courte.",
      "source": "Nom du répertoire source",
      "date_iso": "2026-04-22T10:30:00+00:00",
      "categories": ["images", "texte"]
    }
  ]
}
```

Les catégories sont assignées automatiquement par correspondance de mots-clés sur le nom et la description. Elles correspondent aux 32 catégories WordPress du site.

---

## Interface

`index.html` charge `tools.json` et affiche les outils sous forme de cartes. Chaque carte propose trois actions dont l'état est persisté dans `localStorage` (7 jours) :

- **À publier** — l'outil est ajouté à la sélection du jour
- **Déjà publié** — masqué dans le filtre "Non traités"
- **Ignorer** — écarté jusqu'à réinitialisation

Un bouton **Exporter la sélection** génère un bloc texte copier-coller pour amorcer la rédaction d'un article (nom, URL, description, catégories suggérées, source).

---

## Déclenchement

Le workflow `fetch-tools.yml` s'exécute :
- **Automatiquement** chaque soir à **20h (heure française d'été)** — `cron: '0 18 * * *'`
- **Manuellement** depuis l'onglet Actions → Run workflow

Le commit n'est effectué que si `tools.json` a changé (`git diff --quiet`).

---

## Dépendances Python

```
requests
feedparser
beautifulsoup4
lxml
```

Installées automatiquement par le workflow via `pip install`.

---

## Licence

**Code** (`fetch_tools.py`, `index.html`) — [MIT License](https://opensource.org/licenses/MIT)

Copyright (c) 2026 Bertrand Formet — uneiaparjour.fr

Permission is hereby granted, free of charge, to any person obtaining a copy of this software to deal in the Software without restriction, including the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, subject to the condition that the above copyright notice is included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND.

---

**Données** (`tools.json`) — [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)

Librement réutilisables et adaptables, y compris à des fins commerciales, avec mention de la source : **Bertrand Formet — uneiaparjour.fr**. Les contenus originaux des répertoires sources restent soumis à leurs propres droits.
