#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build authorized SMZDM app links and Feishu multi-platform buttons."""

import json
from urllib.parse import quote, urlsplit, urlunsplit


SMZDM_ROOT_DOMAIN = "smzdm.com"
SMZDM_HOME = "https://www.smzdm.com/"
WAF_PRONE_HOSTS = frozenset({"go.smzdm.com", "m.smzdm.com"})


class InvalidSmzdmUrl(ValueError):
    """Raised when a URL is outside the SMZDM HTTPS allowlist."""


def normalize_smzdm_url(url):
    """Return a canonical SMZDM URL or raise InvalidSmzdmUrl."""
    raw = (url or "").strip()
    parsed = urlsplit(raw)
    scheme = parsed.scheme.lower()
    host = (parsed.hostname or "").lower().rstrip(".")
    if scheme not in ("http", "https") or not host:
        raise InvalidSmzdmUrl("only absolute HTTP(S) SMZDM URLs are allowed")
    if parsed.username or parsed.password:
        raise InvalidSmzdmUrl("credentials are not allowed in SMZDM URLs")
    if host != SMZDM_ROOT_DOMAIN and not host.endswith("." + SMZDM_ROOT_DOMAIN):
        raise InvalidSmzdmUrl(f"untrusted host: {host}")
    return urlunsplit(("https", host, parsed.path or "/", parsed.query, ""))


def is_smzdm_url(url):
    try:
        normalize_smzdm_url(url)
        return True
    except InvalidSmzdmUrl:
        return False


def is_waf_prone_url(url):
    try:
        host = urlsplit(normalize_smzdm_url(url)).hostname
    except InvalidSmzdmUrl:
        return False
    return host in WAF_PRONE_HOSTS


def build_android_deeplink(url):
    """Build the official Android app deep link from a trusted SMZDM URL."""
    target = normalize_smzdm_url(url)
    payload = json.dumps(
        {"url": target},
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return "smzdm://open?json=" + quote(payload, safe="")


def build_open_url_behaviors(url, web_fallback=None):
    """Return Feishu button behaviors with an Android app-first handoff."""
    target = normalize_smzdm_url(url)
    fallback = normalize_smzdm_url(web_fallback) if web_fallback else target

    # go.smzdm.com and m.smzdm.com frequently return the mobile WAF challenge.
    # Never select them as the generic web destination when a safe article URL
    # was supplied.
    if is_waf_prone_url(fallback):
        fallback = target if not is_waf_prone_url(target) else SMZDM_HOME

    return {
        "type": "open_url",
        "default_url": fallback,
        "android_url": build_android_deeplink(target),
        "ios_url": fallback,
        "pc_url": fallback,
    }


def build_smzdm_button(label, url, web_fallback=None, button_type="default", size="small"):
    """Build a Feishu card button that prefers the authorized SMZDM app."""
    return {
        "tag": "button",
        "text": {"tag": "plain_text", "content": label},
        "type": button_type,
        "size": size,
        "behaviors": [build_open_url_behaviors(url, web_fallback=web_fallback)],
    }
