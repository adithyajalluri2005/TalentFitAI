"""Source search for study plans and interview questions.

- Web pages: LangSearch (LANGSEARCH_API_KEY, free tier 1,000 queries/day),
  then Tavily (TAVILY_API_KEY) when LangSearch fails or finds nothing. Free
  metasearch (ddgs) was removed: search engines block it from servers, so it
  mostly cost seconds before falling through to these anyway.
- Pages with their text (``pages``): LangSearch, then Tavily. Used for
  interview questions, so the coach never has to fetch the sites itself.
- YouTube videos: yt-dlp search (no key).
- GitHub repositories: GitHub's REST search API (no key needed; set
  GITHUB_TOKEN to raise the rate limit from 10 to 30 searches/minute).

Results are *candidates*: the curator LLM in nodes.py picks the best ones.
Each candidate is a dict with title, url, type, source, meta and snippet;
`meta` is a short quality signal shown to the curator and the candidate
("13:42 · 142K views", "★ 32.5k").
"""
import json
import logging
import os
import re
import threading
import time
import urllib.parse
import urllib.request
from typing import Callable, List, Optional

logger = logging.getLogger(__name__)

# Job boards, news, social, aggregators and document mirrors: never study material.
BLOCKED_DOMAINS = (
    "indeed.com", "linkedin.com", "glassdoor.com", "naukri.com", "monster.com", "ziprecruiter.com",
    "businessinsider.com", "forbes.com", "cnbc.com", "reuters.com", "bloomberg.com", "techcrunch.com",
    "quora.com", "reddit.com", "facebook.com", "x.com", "twitter.com", "pinterest.com", "instagram.com",
    "classcentral.com", "coursereport.com", "careerkarma.com", "scribd.com", "slideshare.net", "studocu.com",
    "coursehero.com", "chegg.com",
)
# "Top 10 resources to learn X" roundups rank well but are never the best source.
LISTICLE = re.compile(r"\b(top|best)\s+\d+\b|\b\d+\s+(best|top|free)\b|\bbest (free )?(resources|courses|tutorials|books)\b", re.I)
COURSE_HOSTS = (
    "coursera.org", "edx.org", "khanacademy.org", "nptel.ac.in", "onlinecourses.nptel.ac.in", "swayam.gov.in",
    "freecodecamp.org/learn", "kaggle.com/learn", "ocw.mit.edu", "cs50.harvard.edu", "course.fast.ai",
    "developers.google.com/machine-learning", "learn.microsoft.com/en-us/training", "theodinproject.com",
    "fullstackopen.com", "udacity.com/course", "codecademy.com/learn", "w3schools.com", "huggingface.co/learn",
)
MIN_VIDEO_SECONDS = 4 * 60      # shorter clips rarely teach a topic properly
FULL_COURSE_SECONDS = 60 * 60   # a video this long counts as a course
MIN_REPO_STARS = 200


def _blocked(url: str, title: str = "") -> bool:
    u = url.lower()
    return any(d in u for d in BLOCKED_DOMAINS) or bool(LISTICLE.search(title or ""))


# Well-known free learning sites. Used only when the curator LLM is unavailable:
# then only these (and metadata-backed YouTube/GitHub results) are shown.
TRUSTED_HOSTS = (
    "docs.python.org", "python.org", "pytorch.org", "tensorflow.org", "pandas.pydata.org", "numpy.org",
    "scikit-learn.org", "developer.mozilla.org", "docs.oracle.com", "spring.io", "kubernetes.io", "docker.com",
    "postgresql.org", "sqlite.org", "mysql.com", "learn.microsoft.com", "cloud.google.com", "aws.amazon.com",
    "fastapi.tiangolo.com", "djangoproject.com", "flask.palletsprojects.com", "react.dev", "nodejs.org",
    "git-scm.com", "realpython.com", "geeksforgeeks.org", "baeldung.com", "freecodecamp.org", "khanacademy.org",
    "w3schools.com", "kaggle.com", "coursera.org", "edx.org", "ocw.mit.edu", "cs50.harvard.edu", "nptel.ac.in",
    "cp-algorithms.com", "programiz.com", "tutorialspoint.com", "huggingface.co", "fast.ai", "openintro.org",
    "libretexts.org", "online.stat.psu.edu", "swagger.io", "restfulapi.net", "martinfowler.com",
)


def is_trusted(resource) -> bool:
    """A source that is safe to show without LLM vetting."""
    url = (getattr(resource, "url", None) or resource.get("url", "")).lower()
    rtype = getattr(resource, "type", None) or resource.get("type", "")
    meta = getattr(resource, "meta", None) if not isinstance(resource, dict) else resource.get("meta", "")
    if rtype in ("video", "github") or (rtype == "course" and "youtube.com" in url):
        return bool(meta)  # came from yt-dlp / GitHub API with real metadata
    host = _domain(url)
    return any(host == h or host.endswith("." + h) for h in TRUSTED_HOSTS)


_TITLE_SUFFIX = re.compile(r"\s*[-|–—]\s*(YouTube|GeeksforGeeks|W3Schools|Medium|DEV Community)\s*$", re.I)


def clean_title(title: str, url: str = "") -> str:
    """Search engines sometimes return junk titles: several result titles
    glued together, a trailing "- YouTube", or a bare URL. Keep the first
    real title and trim site suffixes."""
    t = " ".join((title or "").split())
    # Glued titles are separated by "..." / "…" runs; the first one is the page's own.
    t = re.split(r"\s*(?:\.\.\.|…)\s+(?=[A-Z0-9])", t)[0]
    t = re.split(r"\s+[-|–—]\s+(?:YouTube|GeeksforGeeks|W3Schools|Medium|DEV Community)\b\s+(?=\S)", t)[0]
    t = _TITLE_SUFFIX.sub("", t).strip(" -|·…")
    if len(t) > 110:
        t = t[:107].rsplit(" ", 1)[0] + "…"
    if not t or t.lower().startswith(("http", "www.")) or "/" in t.split(" ")[0]:
        path = urllib.parse.urlparse(url).path.rstrip("/").rsplit("/", 1)[-1]
        t = re.sub(r"[-_]+", " ", re.sub(r"\.\w+$", "", path)).strip().title() or _domain(url)
    return t


# Regional mirrors of official docs -> the official site.
_MIRRORS = {"developers.google.cn": "developers.google.com", "tensorflow.google.cn": "www.tensorflow.org",
            "cloud.google.cn": "cloud.google.com", "pytorch.apachecn.org": "pytorch.org"}
# Pinned old doc versions -> the current ("stable") docs of the same page.
_VERSIONED_DOCS = (
    (re.compile(r"^(https?://docs\.python\.org)/(?:release/)?[23](?:\.\d+)+/"), r"\1/3/"),
    (re.compile(r"^(https?://pandas\.pydata\.org)/pandas-docs/(?:version/[\d.]+|stable)/"), r"\1/docs/"),
    (re.compile(r"^(https?://numpy\.org/doc)/\d+(?:\.\d+)+/"), r"\1/stable/"),
    (re.compile(r"^(https?://scikit-learn\.org)/\d+(?:\.\d+)+/"), r"\1/stable/"),
    (re.compile(r"^(https?://docs\.djangoproject\.com/en)/\d+(?:\.\d+)+/"), r"\1/stable/"),
    (re.compile(r"^(https?://matplotlib\.org)/\d+(?:\.\d+)+/"), r"\1/stable/"),
)


def canonical_url(url: str) -> str:
    """Official, current docs instead of a regional mirror or a pinned old
    version (e.g. developers.google.cn, docs.python.org/release/3.9.16/)."""
    parts = urllib.parse.urlsplit(url)
    host = parts.netloc.lower()
    if host in _MIRRORS:
        url = urllib.parse.urlunsplit(parts._replace(netloc=_MIRRORS[host]))
    for pattern, repl in _VERSIONED_DOCS:
        url = pattern.sub(repl, url)
    return url


def _domain(url: str) -> str:
    return urllib.parse.urlparse(url).netloc.lower().removeprefix("www.")


def resource_type(url: str) -> str:
    u = url.lower()
    if "youtube.com" in u or "youtu.be" in u:
        return "video"
    if "github.com" in u:
        return "github"
    if any(h in u for h in COURSE_HOSTS):
        return "course"
    if "docs." in u or "/docs" in u or "readthedocs" in u or "/tutorials" in u or "/reference" in u or "/library/" in u:
        return "docs"
    return "article"


def _compact(n) -> str:
    try:
        n = int(n)
    except (TypeError, ValueError):
        return ""
    for unit, size in (("M", 1_000_000), ("K", 1_000)):
        if n >= size:
            return f"{n / size:.1f}".rstrip("0").rstrip(".") + unit
    return str(n)


class _Breaker:
    """Skips a provider for a while after repeated failures (e.g. a search
    engine blocking a cloud server's IP), so every search doesn't first
    waste seconds retrying it."""

    def __init__(self, threshold: int = 3, cooldown: float = 600):
        self.threshold, self.cooldown = threshold, cooldown
        self._fails, self._open_until = 0, 0.0
        self._lock = threading.Lock()

    def available(self) -> bool:
        return time.time() >= self._open_until

    def record(self, ok: bool, name: str) -> None:
        with self._lock:
            if ok:
                self._fails = 0
                return
            self._fails += 1
            if self._fails >= self.threshold and self.available():
                self._open_until = time.time() + self.cooldown
                logger.warning("%s search failing repeatedly; using backup providers for %ds", name, self.cooldown)


def _http_json(url: str, headers: dict, body: Optional[dict] = None, timeout: int = 15) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers={"Accept": "application/json", **headers},
                                 method="POST" if body is not None else "GET")
    if body is not None:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)



class SourceSearch:
    """Web + video search:

        web:    LangSearch API -> Tavily API
        pages:  LangSearch API -> Tavily API (results with page text)
        videos: yt-dlp (free, no key)

    Each API is used only when its key is set; Tavily only when LangSearch
    fails or returns nothing, which keeps its free quota for when it's needed.
    """

    def __init__(self, github_token: Optional[str] = None, tavily_key: Optional[str] = None,
                 langsearch_key: Optional[str] = None):
        self._github_token = github_token if github_token is not None else os.getenv("GITHUB_TOKEN", "")
        self._tavily_key = (tavily_key if tavily_key is not None else os.getenv("TAVILY_API_KEY", "")).strip()
        self._langsearch_key = (langsearch_key if langsearch_key is not None
                                else os.getenv("LANGSEARCH_API_KEY", "")).strip()
        self._langsearch_breaker = _Breaker()
        self._ytdlp_breaker = _Breaker()

    @property
    def providers(self) -> dict:
        keyed = (["langsearch"] if self._langsearch_key else []) + (["tavily"] if self._tavily_key else [])
        return {"web": keyed, "pages": keyed,
                "videos": ["yt-dlp"],
                "github": ["github-api" + (" (token)" if self._github_token else "")]}

    # ---------------- raw web providers: -> [{title, url, body}] ---------------- #

    def _langsearch(self, q: str, domains: List[str], n: int, text_chars: int = 0) -> List[dict]:
        """Raw LangSearch call -> [{title, url, body}]; body is the page text
        when ``text_chars`` is set, else the snippet."""
        if not self._langsearch_key or not self._langsearch_breaker.available():
            return []
        body = {"query": q, "count": max(1, min(n, 50))}
        # An include list already rules out blocked sites; sending both can return nothing.
        if domains:
            body["includeDomains"] = domains
        else:
            body["excludeDomains"] = list(BLOCKED_DOMAINS)
        if text_chars:
            body["contents"] = {"text": {"maxCharacters": text_chars}}
        try:
            data = _http_json("https://api.langsearch.com/v1/web-search",
                              {"Authorization": f"Bearer {self._langsearch_key}"}, body, timeout=25)
            if data.get("code") not in (None, 200):
                raise RuntimeError(f"code {data.get('code')}: {data.get('msg')}")
        except Exception as e:
            self._langsearch_breaker.record(False, "langsearch")
            logger.warning("langsearch failed for %r: %s", q, e)
            return []
        self._langsearch_breaker.record(True, "langsearch")
        hits = ((data.get("data") or {}).get("webPages") or {}).get("value") or []
        return [{"title": r.get("name", ""), "url": r.get("url", ""),
                 "body": (r.get("text") if text_chars else r.get("snippet")) or ""} for r in hits]

    def _web_langsearch(self, q: str, site: str, n: int) -> List[dict]:
        return self._langsearch(q, [site] if site else [], n)

    def _web_tavily(self, q: str, site: str, n: int) -> List[dict]:
        if not self._tavily_key:
            return []
        body = {"query": q, "max_results": min(n, 10), "search_depth": "basic", "api_key": self._tavily_key,
                "exclude_domains": list(BLOCKED_DOMAINS)}
        if site:
            body["include_domains"] = [site]
        try:
            data = _http_json("https://api.tavily.com/search", {"Authorization": f"Bearer {self._tavily_key}"}, body)
        except Exception as e:
            logger.warning("tavily search failed for %r: %s", q, e)
            return []
        return [{"title": r.get("title", ""), "url": r.get("url", ""), "body": r.get("content", "")}
                for r in data.get("results", [])]

    def web(self, query: str, site: str = "", n: int = 6) -> List[dict]:
        out = []
        for name, provider in (("langsearch", self._web_langsearch), ("tavily", self._web_tavily)):
            raw = provider(query, site, n)
            for r in raw:
                url, title = canonical_url(r.get("url") or ""), (r.get("title") or "").strip()
                if not url or _blocked(url, title) or (site and site not in _domain(url)):
                    continue
                if "youtube.com" in url or "youtu.be" in url:
                    continue  # videos come from videos(), which has channel/length/views
                out.append({"title": clean_title(title, url), "url": url, "type": resource_type(url),
                            "source": _domain(url), "meta": "",
                            "snippet": " ".join((r.get("body") or "").split())[:200]})
            if out:
                if name != "langsearch":
                    logger.info("web search for %r served by %s", query, name)
                break
        return out

    def _pages_tavily(self, q: str, domains: List[str], n: int, text_chars: int) -> List[dict]:
        if not self._tavily_key:
            return []
        body = {"query": q, "max_results": min(n, 10), "search_depth": "basic", "include_raw_content": "text"}
        # Tavily returns no results when include_domains and exclude_domains are both set.
        if domains:
            body["include_domains"] = domains
        else:
            body["exclude_domains"] = list(BLOCKED_DOMAINS)
        try:
            data = _http_json("https://api.tavily.com/search", {"Authorization": f"Bearer {self._tavily_key}"}, body,
                              timeout=30)
        except Exception as e:
            logger.warning("tavily page search failed for %r: %s", q, e)
            return []
        return [{"title": r.get("title", ""), "url": r.get("url", ""), "body": (r.get("raw_content") or "")[:text_chars]}
                for r in data.get("results", [])]

    def pages(self, query: str, domains: List[str], n: int = 3, text_chars: int = 9000,
              keep: Optional[Callable[[List[dict]], List[dict]]] = None) -> List[dict]:
        """Search results with each page's text: [{title, url, text}].
        LangSearch first, Tavily as backup; [] when neither key is set or
        both fail (callers then search and fetch pages themselves). ``keep``
        filters a provider's results; if it leaves nothing, the next
        provider is tried."""
        for name, provider in (("langsearch", lambda: self._langsearch(query, domains, n, text_chars)),
                               ("tavily", lambda: self._pages_tavily(query, domains, n, text_chars))):
            out = [{"title": clean_title(r["title"], r["url"]), "url": r["url"], "text": r["body"]}
                   for r in provider() if r.get("url") and r.get("body") and not _blocked(r["url"])]
            if keep:
                out = keep(out)
            if out:
                if name != "langsearch":
                    logger.info("page search for %r served by %s", query, name)
                return out
        return []

    # ---------------- videos ---------------- #

    def _video_entry(self, title: str, url: str, secs: int, views: int, channel: str, description: str) -> dict:
        length = f"{secs // 3600}h {secs % 3600 // 60}m" if secs >= 3600 else f"{secs // 60} min"
        meta = " · ".join(x for x in (channel, length if secs else "", f"{_compact(views)} views" if views else "") if x)
        return {"title": clean_title(title or "", url), "url": url,
                "type": "course" if secs >= FULL_COURSE_SECONDS else "video",
                "source": "youtube.com", "meta": meta,
                "snippet": " ".join((description or "").split())[:160], "_views": views, "_secs": secs}

    def _videos_ytdlp(self, query: str, n: int) -> List[dict]:
        if not self._ytdlp_breaker.available():
            return []
        import yt_dlp
        try:
            with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True, "extract_flat": True, "skip_download": True}) as y:
                entries = (y.extract_info(f"ytsearch{n}:{query}", download=False) or {}).get("entries") or []
        except Exception as e:
            self._ytdlp_breaker.record(False, "yt-dlp")
            logger.info("youtube search failed for %r: %s", query, e)
            return []
        self._ytdlp_breaker.record(True, "yt-dlp")
        return [self._video_entry(e.get("title"), e.get("url") or "", int(e.get("duration") or 0),
                                  int(e.get("view_count") or 0), e.get("channel") or "", e.get("description"))
                for e in entries]

    def videos(self, query: str, n: int = 8, min_seconds: int = MIN_VIDEO_SECONDS) -> List[dict]:
        """YouTube results (metadata only; nothing is downloaded)."""
        out = [v for v in self._videos_ytdlp(query, n)
               if v["url"].startswith("https://www.youtube.com/watch") and not (v["_secs"] and v["_secs"] < min_seconds)]
        # Popularity is a decent proxy for a clear, accurate video.
        out.sort(key=lambda v: v["_views"], reverse=True)
        for v in out:
            v.pop("_views"), v.pop("_secs")
        return out

    def github(self, query: str, n: int = 5, language: str = "") -> List[dict]:
        q = f"{query} in:name,description"
        if language:
            q += f' language:"{language}"'
        url = "https://api.github.com/search/repositories?" + urllib.parse.urlencode(
            {"q": q, "sort": "stars", "order": "desc", "per_page": n * 2})
        req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "talentfitai-coach"})
        if self._github_token:
            req.add_header("Authorization", f"Bearer {self._github_token}")
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                items = json.load(resp).get("items", [])
        except Exception as e:
            logger.warning("github search failed for %r: %s", query, e)
            return []
        out = []
        for r in items:
            if r.get("archived") or r.get("stargazers_count", 0) < MIN_REPO_STARS:
                continue
            out.append({"title": r["full_name"], "url": r["html_url"], "type": "github", "source": "github.com",
                        "meta": " · ".join(x for x in (f"★ {_compact(r['stargazers_count'])}", r.get("language") or "") if x),
                        "snippet": (r.get("description") or "")[:200]})
        return out[:n]

    # ---------------- what the planner calls ---------------- #

    def topic(self, query: str, official_site: str = "") -> List[dict]:
        """Candidates for one topic: official docs, web tutorials, videos."""
        site = (official_site or "").strip().lower().removeprefix("https://").removeprefix("http://").strip("/")
        found = []
        if site and "." in site:
            found += self.web(query, site=site, n=3)
        found += self.web(query, n=6)
        found += self.videos(f"{query}", n=8)[:4]
        return _dedupe(found)[:10]

    def skill(self, skill: str, github_query: str, language: str = "") -> List[dict]:
        """Skill-wide candidates: free full courses and GitHub repos. With a
        language, repos are restricted to it (a Python role gets Python repos);
        if that finds nothing, fall back to any language and let the curator judge."""
        found = [r for r in self.web(f"{skill} free online course", n=8) if r["type"] == "course"]
        found += [v for v in self.videos(f"{skill} full course for beginners", n=8, min_seconds=FULL_COURSE_SECONDS)][:3]
        repos = self.github(github_query or skill, n=4, language=language) if language else []
        found += repos or self.github(github_query or skill, n=4)
        return _dedupe(found)[:10]


def _dedupe(items: List[dict]) -> List[dict]:
    seen, out = set(), []
    for r in items:
        key = r["url"].lower().split("#")[0].rstrip("/")
        if key not in seen:
            seen.add(key)
            out.append(r)
    return out
