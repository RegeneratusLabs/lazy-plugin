"""Search the same catalog the marketplace ships, but by token instead of by phrase.

`hermes plugins search <q>` substring-matches the whole query against name/description/tools, so
"daily brief news provider" matches nothing while every word in it matches something. This scores
each token against weighted fields with an inverse-document-frequency weight, which is what makes
"news" count for a news plugin and "provider" count for little.

Every hit carries the marketplace URL and the install command, so a recommendation can link to the
thing it is recommending instead of naming a category.
"""

from __future__ import annotations

import importlib.util
import math
import re
from pathlib import Path
from typing import Optional

_HERE = Path(__file__).resolve().parent


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(f"pluginscout_{name}", _HERE / filename)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


_CORE = _load("core", "core.py")

# name earns most: "marketplace-watch" should win for "marketplace" over a description that mentions it.
FIELD_WEIGHT = {"name": 6.0, "tools": 4.0, "title": 3.0, "category": 2.0, "description": 1.0}

# How much a hit's field is worth. Prose is nearly free to match — a chatty description says
# "gateway", "restart", "port", "repo", "sync" and will absorb any query thrown at it. Identity
# fields are the only ones that show a plugin is ABOUT the need, so they carry the credit.
FIELD_CREDIT = {"name": 1.0, "tools": 0.9, "title": 0.8, "category": 0.55, "description": 0.45}
# Evidence is measured in "effective matched tokens": each token's idf divided by the catalog's
# maximum idf, so a hit is worth the same in a 4-entry fixture as in a 976-plugin catalog. It is not
# a fraction of the QUERY, because a recommendation's search terms are a shotgun of near-synonyms and
# words absent from the whole catalog ("supervisor", "registry") would dilute a real match to nothing.
# The prose gate below keeps precision; these decide how strongly to say it.
STRONG_EVIDENCE = 1.0
POSSIBLE_EVIDENCE = 0.6

# Words that appear in half the catalog and therefore say nothing about which plugin someone needs.
GENERIC = {
    "plugin", "tool", "provider", "service", "integration", "hermes", "agent", "support",
    "manage", "manager", "ability", "allow", "help", "handle", "feature", "capability",
    "workflow", "system", "simple", "easy", "anything", "everything", "various",
}

STOP = {
    "the", "and", "for", "with", "from", "that", "this", "into", "your", "you", "our", "its",
    "use", "used", "using", "when", "then", "than", "have", "has", "had", "not", "but", "all",
    "any", "can", "could", "would", "should", "will", "would", "one", "two", "how", "what",
    "which", "who", "why", "are", "was", "were", "been", "being", "does", "did", "doing",
    "get", "got", "make", "made", "work", "works", "need", "needs", "want", "wants", "like",
}

# Hyphens separate: "market-watch" must match the words market and watch.
WORD = re.compile(r"[a-z0-9][a-z0-9_+]+")


def tokens(text: str) -> list:
    """Lowercase words, 3+ chars, no stopwords, crude singular. Duplicates collapse at scoring."""
    out = []
    for raw in WORD.findall((text or "").lower()):
        if len(raw) < 3 or raw in STOP:
            continue
        if raw.endswith("ies") and len(raw) > 4:
            raw = raw[:-3] + "y"
        elif raw.endswith("s") and not raw.endswith("ss") and len(raw) > 4:
            raw = raw[:-1]
        out.append(raw)
    return out


def _fields(entry: dict) -> dict:
    caps = entry.get("capabilities") or {}
    return {
        "name": tokens(str(entry.get("name") or "")),
        "title": tokens(str(entry.get("title") or "")),
        "category": tokens(str(entry.get("category") or "")),
        "tools": tokens(" ".join(str(t) for t in (caps.get("provides_tools") or []))),
        "description": tokens(str(entry.get("description") or "")),
    }


MARKETPLACE = "https://hermes-agent.nousresearch.com/marketplace"


def market_url(name: str) -> Optional[str]:
    """The official Nous marketplace page for one plugin — not the upstream GitHub repo."""
    return f"{MARKETPLACE}/{name}" if name else None


def install_url(name: str) -> Optional[str]:
    """The marketplace's own install handoff; the desktop app handles the hermes:// scheme."""
    return f"hermes://plugin/install?catalog={name}" if name else None


def _url(entry: dict) -> Optional[str]:
    for key in ("docs_url", "repo"):
        value = entry.get(key)
        if isinstance(value, str) and value.startswith("http"):
            return value
    return None


def index(entries: list) -> tuple[list, dict]:
    """(docs, document-frequency) — df is what makes a rare word outweigh a common one."""
    docs, df = [], {}
    for entry in entries:
        fields = _fields(entry)
        seen = set()
        for values in fields.values():
            for token in values:
                if token not in seen:
                    seen.add(token)
                    df[token] = df.get(token, 0) + 1
        docs.append((entry, fields))
    return docs, df


def search(query: str, limit: int = 5, min_score: float = POSSIBLE_EVIDENCE,
           entries: Optional[list] = None) -> list:
    """Rank catalog entries for a free-text query. Returns [] rather than a bad guess."""
    wanted = tokens(query)
    if not wanted:
        return []
    if entries is None:
        try:
            entries = _CORE.load_catalog()["entries"]
        except Exception:
            return []
    docs, df = index(entries)
    total = max(1, len(docs))
    installed = set()
    try:
        installed = set(_CORE.installed_plugins() or ())
    except Exception:
        pass

    informative = [t for t in dict.fromkeys(wanted) if t not in GENERIC]
    if not informative:
        return []
    unknown_idf = math.log(1 + total)
    scale = unknown_idf or 1.0  # maximum possible idf in this catalog
    total_idf = sum(math.log(1 + total / (1 + df[t])) if t in df else unknown_idf
                    for t in informative) or 1.0

    hits = []
    for entry, fields in docs:
        credit, matched = 0.0, []
        for token in informative:
            idf = math.log(1 + total / (1 + df[token])) if token in df else unknown_idf
            best_field, best_weight = None, 0.0
            for field, weight in FIELD_WEIGHT.items():
                if token in fields[field] and weight > best_weight:
                    best_field, best_weight = field, weight
            if best_field is None:
                continue
            credit += (idf / scale) * FIELD_CREDIT.get(best_field, 0.45)
            matched.append({"token": token, "field": best_field})
        # Prose alone is not evidence: if nothing matched a name, title, tool or category, the
        # entry is just talking about the same domain. Drop it rather than ranking it.
        if not any(m["field"] != "description" for m in matched):
            continue
        if credit < min_score:
            continue
        relevance = min(1.0, credit / total_idf)  # kept for display, not for the threshold
        name = str(entry.get("name") or "")
        hits.append({
            "name": name,
            "title": entry.get("title") or name,
            "score": round(relevance, 2),
            "credit": round(credit, 1),
            # An install line needs identity-level evidence: a plugin earns "strong" only if the
            # wording of the NEED shows up in its name, title or tool names — not just its prose.
            "strength": ("strong" if credit >= STRONG_EVIDENCE
                         and any(m["field"] in ("name", "title", "tools") for m in matched)
                         else "possible"),
            "matched": matched[:6],
            "why": ", ".join(f"{m['token']}→{m['field']}" for m in matched[:4]),
            "url": market_url(name),
            "source_url": _url(entry),
            "install_url": install_url(name),
            "install": f"hermes plugins install {name}" if name else None,
            "category": entry.get("category"),
            "tier": entry.get("tier"),
            "maintainer": entry.get("maintainer"),
            "description": (entry.get("description") or "")[:280],
            "requires_env": list((entry.get("capabilities") or {}).get("requires_env") or []),
            "installed": name in installed,
        })
    hits.sort(key=lambda h: (-h["score"], h["name"]))
    return hits[:max(1, limit)]


BROWSE_URL = f"{MARKETPLACE}?kind=plugins"
CATALOG_REPO = "https://github.com/NousResearch/hermes-agent/tree/main/plugin-catalog"


def search_for_recommendation(rec: dict, limit: int = 3) -> dict:
    """One recommendation → the marketplace answer for it."""
    query = " ".join([str(rec.get("title") or "")] + [str(t) for t in (rec.get("search_terms") or [])])
    hits = search(query, limit=limit)
    best = hits[0] if hits else None
    clean = " ".join(query.split())
    return {
        "query": clean,
        "best": best,
        "hits": hits,
        "strength": best["strength"] if best else "none",
        "browse_url": BROWSE_URL,
        "cli_search": f'hermes plugins search "{clean[:60]}"',
    }
