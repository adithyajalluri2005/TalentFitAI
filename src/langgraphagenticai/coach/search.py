"""Source search for study plans, free providers first.

- Web pages: `ddgs` (metasearch, no API key), falling back to Tavily when
  TAVILY_API_KEY is set. Free metasearch is often blocked from cloud servers;
  the fallback covers that.
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
from typing import List, Optional

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
    """Web + video search, free providers first:

        web:    ddgs (free, no key) -> Tavily API
        videos: yt-dlp (free, no key)

    Tavily is used only when TAVILY_API_KEY is set and ddgs fails or returns
    nothing, which keeps its monthly free quota for when it's needed.
    """

    def __init__(self, github_token: Optional[str] = None, tavily_key: Optional[str] = None):
        from ddgs import DDGS
        self._ddgs = DDGS(timeout=15)
        self._github_token = github_token if github_token is not None else os.getenv("GITHUB_TOKEN", "")
        self._tavily_key = (tavily_key if tavily_key is not None else os.getenv("TAVILY_API_KEY", "")).strip()
        self._ddgs_breaker = _Breaker()
        self._ytdlp_breaker = _Breaker()

    @property
    def providers(self) -> dict:
        return {"web": ["ddgs"] + (["tavily"] if self._tavily_key else []),
                "videos": ["yt-dlp"],
                "github": ["github-api" + (" (token)" if self._github_token else "")]}

    # ---------------- raw web providers: -> [{title, url, body}] ---------------- #

    def _web_ddgs(self, q: str, site: str, n: int) -> List[dict]:
        if not self._ddgs_breaker.available():
            return []
        query = f"{q} site:{site}" if site else q
        for wait in (0, 2):  # metasearch engines rate-limit bursts; one short pause usually clears it
            if wait:
                time.sleep(wait)
            try:
                hits = list(self._ddgs.text(query, max_results=n) or [])
                self._ddgs_breaker.record(True, "ddgs")
                return [{"title": r.get("title", ""), "url": r.get("href", ""), "body": r.get("body", "")} for r in hits]
            except Exception as e:
                last = e
        self._ddgs_breaker.record(False, "ddgs")
        logger.info("ddgs failed for %r: %s", query, last)
        return []

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
        for name, provider in (("ddgs", self._web_ddgs), ("tavily", self._web_tavily)):
            raw = provider(query, site, n)
            for r in raw:
                url, title = r.get("url") or "", (r.get("title") or "").strip()
                if not url or _blocked(url, title) or (site and site not in _domain(url)):
                    continue
                if "youtube.com" in url or "youtu.be" in url:
                    continue  # videos come from videos(), which has channel/length/views
                out.append({"title": clean_title(title, url), "url": url, "type": resource_type(url),
                            "source": _domain(url), "meta": "",
                            "snippet": " ".join((r.get("body") or "").split())[:200]})
            if out:
                if name != "ddgs":
                    logger.info("web search for %r served by %s", query, name)
                break
        return out

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
