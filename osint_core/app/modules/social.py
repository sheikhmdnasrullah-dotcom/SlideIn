"""Target discovery & profile pinpointing — Maigret/Holehe methodology.

Two probe classes:

  1. Username enumeration (`SocialEnumerator`) — for each registered platform we
     issue one cheap HTTP probe against the profile URL / public API and classify
     the response (status code, or body-marker presence/absence). Active hits are
     re-fetched and parsed with socid-extractor-style regex schemas to recover
     real name tokens, internal account IDs, avatars, and bio text.

  2. Gravatar probe — email-keyed (MD5 of the address), zero guessing: returns
     the display name, bio, location, and every linked account the user exposed.

The registry format is intentionally compatible with Maigret's `data.json`
export — drop a full Maigret export in as `SiteDef` entries to scale from the
default high-signal set to thousands of platforms with no code changes.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import re
from dataclasses import dataclass, field

from ..config import settings
from ..core.http import HttpProbe, ProbeError
from ..schemas import SocialFootprint, SocialProfile

# check strategies:
#   status        — HTTP 200 => exists, 404 => absent
#   marker_absent — body lacks `absent` marker => exists (authwalled sites)
#   marker_present— body contains `present` marker => exists
#   api_json      — 200 + JSON body parse; extraction via `parse` regexes
@dataclass(frozen=True)
class SiteDef:
    name: str
    url: str                       # profile URL; {u} = username
    check: str = "status"
    absent_marker: str | None = None
    present_marker: str | None = None
    parse: dict = field(default_factory=dict)   # field -> regex with one capture group
    weight: float = 0.6            # confidence floor when a hit is found


# High-signal default registry. Authwalled platforms (Instagram, TikTok,
# LinkedIn, Facebook) use marker-based checks and yield lower confidence —
# exactly how Maigret/Holehe treat them.
DEFAULT_SITES: list[SiteDef] = [
    SiteDef("GitHub", "https://api.github.com/users/{u}", "api_json",
            parse={"full_name": r'"name":\s*"([^"]+)"',
                   "avatar_url": r'"avatar_url":\s*"([^"]+)"',
                   "bio": r'"bio":\s*"([^"]+)"',
                   "location": r'"location":\s*"([^"]+)"',
                   "user_id": r'"id":\s*(\d+)'}, weight=0.95),
    SiteDef("Reddit", "https://www.reddit.com/user/{u}/about.json", "api_json",
            parse={"full_name": r'"name":\s*"([^"]+)"',
                   "avatar_url": r'"icon_img":\s*"([^"]+)"',
                   "bio": r'"public_description":\s*"([^"]*)"'}, weight=0.9),
    SiteDef("Gravatar-handle", "https://www.gravatar.com/{u}.json", "api_json",
            parse={"full_name": r'"displayName":\s*"([^"]+)"'}, weight=0.7),
    SiteDef("GitLab", "https://gitlab.com/api/v4/users?username={u}", "api_json",
            parse={"user_id": r'"id":\s*(\d+)', "full_name": r'"name":\s*"([^"]+)"',
                   "avatar_url": r'"avatar_url":\s*"([^"]+)"'}, weight=0.9),
    SiteDef("DockerHub", "https://hub.docker.com/v2/users/{u}/", "api_json",
            parse={"full_name": r'"full_name":\s*"([^"]+)"'}, weight=0.85),
    SiteDef("Keybase", "https://keybase.io/_/api/1.0/user/lookup.json?username={u}", "api_json",
            parse={"full_name": r'"full_name":\s*"([^"]+)"'}, weight=0.9),
    SiteDef("Medium", "https://medium.com/@{u}", "status", weight=0.75),
    SiteDef("Dev.to", "https://dev.to/api/users/by_username?url={u}", "api_json",
            parse={"full_name": r'"name":\s*"([^"]+)"',
                   "bio": r'"summary":\s*"([^"]*)"',
                   "avatar_url": r'"profile_image":\s*"([^"]+)"'}, weight=0.85),
    SiteDef("HackerNews", "https://hacker-news.firebaseio.com/v0/user/{u}.json", "api_json",
            parse={"user_id": r'"id":\s*"([^"]+)"'}, weight=0.85),
    SiteDef("Behance", "https://www.behance.net/{u}", "status", weight=0.7),
    SiteDef("Dribbble", "https://dribbble.com/{u}", "status", weight=0.7),
    SiteDef("Tumblr", "https://{u}.tumblr.com", "status", weight=0.6),
    SiteDef("Vimeo", "https://vimeo.com/{u}", "status", weight=0.7),
    SiteDef("Flickr", "https://www.flickr.com/photos/{u}", "status", weight=0.65),
    SiteDef("Pinterest", "https://www.pinterest.com/{u}/", "marker_absent",
            absent_marker="User not found", weight=0.6),
    SiteDef("Spotify", "https://open.spotify.com/user/{u}", "status", weight=0.6),
    SiteDef("Steam", "https://steamcommunity.com/id/{u}", "status", weight=0.7),
    SiteDef("Twitch", "https://www.twitch.tv/{u}", "marker_absent",
            absent_marker="Sorry. Unless you've got a time machine", weight=0.6),
    SiteDef("Telegram", "https://t.me/{u}", "marker_absent",
            absent_marker='<div class="tgme_page_extra">',  # absence of this == no profile... see note
            weight=0.55),
    SiteDef("About.me", "https://about.me/{u}", "status", weight=0.6),
    SiteDef("npm", "https://www.npmjs.com/~{u}", "status", weight=0.65),
    SiteDef("PyPI", "https://pypi.org/user/{u}/", "status", weight=0.65),
    SiteDef("Mastodon", "https://mastodon.social/@{u}", "status", weight=0.5),
    SiteDef("Instagram", "https://www.instagram.com/{u}/", "marker_absent",
            absent_marker='"page_not_found"', weight=0.45),
    SiteDef("TikTok", "https://www.tiktok.com/@{u}", "marker_absent",
            absent_marker="Couldn't find this account", weight=0.45),
    SiteDef("YouTube", "https://www.youtube.com/@{u}", "marker_absent",
            absent_marker='"status":"LOGIN_REQUIRED"', weight=0.5),
    SiteDef("SoundCloud", "https://soundcloud.com/{u}", "marker_absent",
            absent_marker="404 - Not Found", weight=0.6),
    SiteDef("Quora", "https://www.quora.com/profile/{u}", "status", weight=0.55),
    SiteDef("ProductHunt", "https://www.producthunt.com/@{u}", "status", weight=0.55),
]

_GRAVATAR_PROFILE = "https://www.gravatar.com/{md5}.json"


class SocialEnumerator:
    def __init__(self, probe: HttpProbe, sites: list[SiteDef] | None = None):
        self._probe = probe
        self._sites = sites or DEFAULT_SITES

    @property
    def site_count(self) -> int:
        return len(self._sites)

    async def enumerate(
        self,
        handle: str,
        max_sites: int | None = None,
        on_result=None,
    ) -> SocialFootprint:
        sites = self._sites[: max_sites or settings.default_site_count]
        sem = asyncio.Semaphore(settings.platform_concurrency)

        async def _bounded(site: SiteDef) -> SocialProfile | None:
            async with sem:
                try:
                    profile = await asyncio.wait_for(
                        self._check(site, handle), timeout=settings.request_timeout * 2
                    )
                except (asyncio.TimeoutError, ProbeError, Exception):
                    profile = None  # one broken platform node must not stall the batch
                if on_result is not None:
                    await on_result(
                        site.name,
                        profile.model_dump() if profile is not None else {"exists": False},
                    )
                return profile

        results = await asyncio.gather(*[_bounded(s) for s in sites])
        found = [r for r in results if r is not None and r.exists]

        # Merge name tokens from the highest-confidence profiles.
        name_tokens: list[str] = []
        for p in sorted(found, key=lambda x: -x.confidence):
            if p.full_name:
                for tok in re.split(r"\s+", p.full_name.strip()):
                    if tok and tok.lower() not in [t.lower() for t in name_tokens]:
                        name_tokens.append(tok)

        return SocialFootprint(
            username_handle=handle,
            platforms_checked=len(sites),
            profiles_found=found,
            name_tokens=name_tokens,
        )

    async def _check(self, site: SiteDef, handle: str) -> SocialProfile | None:
        url = site.url.format(u=handle)
        found = False
        body = ""

        if site.check == "api_json":
            resp = await self._probe.get(url, accept_statuses={200, 404})
            found = resp.status_code == 200 and resp.text.strip() not in ("", "null")
            body = resp.text
        else:
            resp = await self._probe.get(url, accept_statuses={200, 404})
            if site.check == "status":
                found = resp.status_code == 200
            elif site.check == "marker_absent":
                found = resp.status_code == 200 and (
                    site.absent_marker is None or site.absent_marker not in resp.text
                )
            elif site.check == "marker_present":
                found = site.present_marker is not None and site.present_marker in resp.text
            body = resp.text

        if not found:
            return SocialProfile(platform=site.name, url=url, exists=False, confidence=0.0)

        fields: dict = {}
        for fld, pattern in site.parse.items():
            m = re.search(pattern, body or "")
            if m:
                fields[fld] = m.group(1).replace("\\u002F", "/")

        return SocialProfile(
            platform=site.name,
            url=url,
            exists=True,
            confidence=site.weight,
            username=handle,
            user_id=fields.get("user_id"),
            full_name=fields.get("full_name"),
            avatar_url=fields.get("avatar_url"),
            bio=fields.get("bio"),
            location=fields.get("location"),
            raw={"check": site.check, "bytes": len(body)},
        )


async def gravatar_probe(probe: HttpProbe, email: str) -> dict | None:
    """Email-keyed Gravatar lookup — strongest single identity signal available."""
    md5 = hashlib.md5(email.strip().lower().encode()).hexdigest()
    try:
        resp = await probe.get(_GRAVATAR_PROFILE.format(md5=md5), accept_statuses={200, 404})
        if resp.status_code != 200:
            return None
        data = json.loads(resp.text)
        entry = (data.get("entry") or [{}])[0]
        return {
            "profile_url": entry.get("profileUrl"),
            "display_name": entry.get("displayName"),
            "about_me": entry.get("aboutMe"),
            "location": (entry.get("currentLocation") or ""),
            "avatar_url": (entry.get("thumbnailUrl") or "").replace("?s=80", "?s=400"),
            "linked_accounts": [
                {"platform": a.get("shortname"), "username": a.get("username"),
                 "url": a.get("url")}
                for a in entry.get("accounts", [])
            ],
        }
    except (ProbeError, ValueError, json.JSONDecodeError):
        return None
