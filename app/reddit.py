"""
Import a story from a Reddit post URL.

Order of attempts:
  1. Reddit's public JSON for the post (works from many networks, e.g. a home PC)
  2. The same JSON through old.reddit.com
  3. Reddit's OAuth API, if REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET are set
Reddit often blocks anonymous requests from cloud hosts, so on a server option 3 is the reliable one.
"""
import base64
import html
import json
import re
import urllib.error
import urllib.parse
import urllib.request

from . import settings as S

ALLOWED_HOSTS = {"reddit.com", "www.reddit.com", "old.reddit.com", "new.reddit.com", "m.reddit.com",
                 "np.reddit.com", "redd.it"}
POST_RE = re.compile(r"/comments/([a-z0-9]{5,10})(?:/|$)", re.I)


class RedditError(Exception):
    """Message is safe to show to the user."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


_opener = urllib.request.build_opener(_NoRedirect)


def _host_ok(url: str) -> bool:
    p = urllib.parse.urlparse(url)
    return p.scheme == "https" and (p.hostname or "").lower() in ALLOWED_HOSTS


def _get(url: str, headers: dict, hops: int = 3) -> bytes:
    """GET that follows redirects manually, refusing to leave reddit's domains."""
    for _ in range(hops + 1):
        if not _host_ok(url) and not url.startswith("https://oauth.reddit.com/"):
            raise RedditError("That link doesn't point to Reddit.")
        req = urllib.request.Request(url, headers=headers)
        try:
            with _opener.open(req, timeout=12) as resp:
                return resp.read(2_000_000)
        except urllib.error.HTTPError as exc:
            if exc.code in (301, 302, 303, 307, 308) and exc.headers.get("Location"):
                url = urllib.parse.urljoin(url, exc.headers["Location"])
                continue
            raise
    raise RedditError("Too many redirects.")


def _post_id(url: str) -> str:
    url = url.strip()
    if not re.match(r"^https?://", url, re.I):
        url = "https://" + url
    url = re.sub(r"^http://", "https://", url, flags=re.I)
    p = urllib.parse.urlparse(url)
    host = (p.hostname or "").lower()
    if host not in ALLOWED_HOSTS:
        raise RedditError("Paste a link to a Reddit post (reddit.com/r/.../comments/...).")
    if host == "redd.it":                      # short link: redd.it/abc123
        m = re.match(r"^/([a-z0-9]{5,10})/?$", p.path, re.I)
        if m:
            return m.group(1)
    m = POST_RE.search(p.path)
    if not m:
        # share links (/r/sub/s/xyz) redirect to the real post
        if re.search(r"/s/[A-Za-z0-9]+/?$", p.path):
            try:
                _get_final = _resolve_redirect(url)
                m = POST_RE.search(urllib.parse.urlparse(_get_final).path)
            except Exception:
                m = None
        if not m:
            raise RedditError("That doesn't look like a link to a Reddit post.")
    return m.group(1)


def _resolve_redirect(url: str) -> str:
    for _ in range(4):
        req = urllib.request.Request(url, headers={"User-Agent": S.REDDIT_USER_AGENT}, method="HEAD")
        try:
            _opener.open(req, timeout=10)
            return url
        except urllib.error.HTTPError as exc:
            loc = exc.headers.get("Location")
            if exc.code in (301, 302, 303, 307, 308) and loc:
                url = urllib.parse.urljoin(url, loc)
                if not _host_ok(url):
                    raise RedditError("That link doesn't point to Reddit.")
                continue
            raise
    return url


def _oauth_token() -> str | None:
    if not (S.REDDIT_CLIENT_ID and S.REDDIT_CLIENT_SECRET):
        return None
    basic = base64.b64encode(f"{S.REDDIT_CLIENT_ID}:{S.REDDIT_CLIENT_SECRET}".encode()).decode()
    req = urllib.request.Request("https://www.reddit.com/api/v1/access_token",
                                 data=b"grant_type=client_credentials", method="POST",
                                 headers={"Authorization": f"Basic {basic}", "User-Agent": S.REDDIT_USER_AGENT})
    with _opener.open(req, timeout=12) as resp:
        return json.loads(resp.read()).get("access_token")


def _fetch_post_json(post_id: str) -> dict:
    ua = {"User-Agent": S.REDDIT_USER_AGENT, "Accept": "application/json"}
    errors = []
    for base in ("https://www.reddit.com", "https://old.reddit.com"):
        try:
            data = json.loads(_get(f"{base}/comments/{post_id}.json?raw_json=1&limit=1", ua))
            return data[0]["data"]["children"][0]["data"]
        except urllib.error.HTTPError as exc:
            errors.append(exc.code)
        except (RedditError, ValueError, KeyError, IndexError):
            errors.append("parse")
        except Exception as exc:
            errors.append(type(exc).__name__)
    try:
        token = _oauth_token()
        if token:
            h = {**ua, "Authorization": f"Bearer {token}"}
            data = json.loads(_get(f"https://oauth.reddit.com/comments/{post_id}?raw_json=1&limit=1", h))
            return data[0]["data"]["children"][0]["data"]
    except Exception as exc:
        errors.append(f"oauth:{type(exc).__name__}")
    if any(e in (403, 429) for e in errors):
        raise RedditError("Reddit refused the request from this server. Open the post, copy the text "
                          "and paste it into the story box instead.")
    raise RedditError("Couldn't load that post. Check the link, or paste the text yourself.")


def clean_story(text: str) -> str:
    text = html.unescape(text or "")
    text = text.replace("​", " ").replace("&#x200B;", " ")
    text = re.sub(r"\[([^\]]+)\]\((?:https?://)?[^)\s]+\)", r"\1", text)       # [label](url) -> label
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"^\s{0,3}#{1,6}\s*", "", text, flags=re.M)                   # headings
    text = re.sub(r"(\*\*|__|~~|`)", "", text)
    text = re.sub(r"(?<!\w)[*_](\S.*?\S|\S)[*_](?!\w)", r"\1", text)           # *italic*
    text = re.sub(r"^\s*>\s?", "", text, flags=re.M)                            # quotes
    text = re.sub(r"^\s*[-*+]\s+", "", text, flags=re.M)                        # bullets
    text = re.sub(r"\n{2,}", "\n\n", text)
    return re.sub(r"[ \t]+", " ", text).strip()


def _trim(text: str, limit: int) -> tuple[str, bool]:
    if len(text) <= limit:
        return text, False
    cut = text[:limit]
    end = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "), cut.rfind(".\n"))
    return (cut[:end + 1] if end > limit * 0.6 else cut).strip(), True


def import_story(url: str) -> dict:
    post = _fetch_post_json(_post_id(url))
    if post.get("over_18"):
        raise RedditError("That post is marked NSFW, so it can't be imported.")
    if not post.get("is_self", True) and not post.get("selftext"):
        raise RedditError("That post is a link or media post with no story text.")
    title = clean_story(post.get("title", "")).strip()
    body = clean_story(post.get("selftext", ""))
    if post.get("removed_by_category") or body in ("[removed]", "[deleted]"):
        raise RedditError("That post was removed or deleted.")
    if not body:
        raise RedditError("That post has no story text to narrate.")
    # narrate the title first, as most story reels do
    story = f"{title}. {body}" if title and not title.endswith(("?", "!", ".")) else f"{title} {body}".strip()
    story, truncated = _trim(story, S.MAX_STORY_CHARS)
    return {"title": title[:120] or "Reddit story", "text": story, "truncated": truncated,
            "subreddit": post.get("subreddit", ""), "author": post.get("author", "")}
