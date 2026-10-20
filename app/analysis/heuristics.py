"""Deterministic URL risk signals: cheap, explainable checks that run on every link before any API call."""
import ipaddress
import re
from urllib.parse import urlsplit

SUSPICIOUS_TLDS = {"zip", "mov", "xyz", "top", "click", "gq", "tk", "ml", "cf", "ga", "work", "rest", "country"}
SHORTENERS = {"bit.ly", "tinyurl.com", "t.co", "goo.gl", "is.gd", "ow.ly", "cutt.ly", "rebrand.ly"}
PHISH_WORDS = re.compile(r"(login|log-in|signin|verify|account|update|secure|banking|wallet|password|"
                         r"confirm|unlock|suspend)", re.I)
BRANDS = ("paypal", "apple", "microsoft", "google", "amazon", "netflix", "facebook", "instagram", "chase",
          "wellsfargo", "bankofamerica", "coinbase", "binance")


def url_signals(url: str) -> list[str]:
    """Return human-readable reasons this URL looks risky (empty list = nothing found)."""
    reasons: list[str] = []
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    if not host:
        return ["URL has no host"]
    try:
        ipaddress.ip_address(host)
        reasons.append("uses a raw IP address instead of a domain name")
    except ValueError:
        pass
    if "xn--" in host:
        reasons.append("internationalized (punycode) domain that can imitate another domain")
    if "@" in parts.netloc:
        reasons.append("contains '@' in the host part, which hides the real destination")
    tld = host.rsplit(".", 1)[-1]
    if tld in SUSPICIOUS_TLDS:
        reasons.append(f"top-level domain .{tld} is common in abuse reports")
    if host.count(".") >= 4:
        reasons.append("unusually deep subdomain nesting")
    if host in SHORTENERS:
        reasons.append("points to another URL shortener (destination hidden)")
    if len(url) > 200:
        reasons.append("very long URL")
    if parts.scheme == "http":
        reasons.append("not encrypted (http)")
    for brand in BRANDS:
        if brand in host and not (host == f"{brand}.com" or host.endswith(f".{brand}.com")):
            reasons.append(f"mentions '{brand}' but is not {brand}.com")
            break
    if PHISH_WORDS.search(parts.path + "?" + parts.query) and len(reasons) >= 1:
        reasons.append("credential-related words in the path")
    return reasons


# Threat tags stored in ai_analyses.threat_types, and how much each signal lowers the 0–1 safety score.
SIGNAL_TAGS = [
    # one strong signal alone pushes a link below the 0.5 threshold
    ("uses a raw IP", "raw_ip_host", 0.55),
    ("contains '@'", "obfuscated_host", 0.55),
    ("punycode", "homograph_domain", 0.55),
    ("mentions '", "brand_impersonation", 0.6),
    ("top-level domain", "suspicious_tld", 0.15),
    ("deep subdomain", "deep_subdomains", 0.15),
    ("another URL shortener", "nested_shortener", 0.15),
    ("credential-related", "credential_phishing_pattern", 0.2),
    ("very long URL", "long_url", 0.05),
    ("not encrypted", "no_https", 0.05),
]


def score_signals(reasons: list[str]) -> tuple[float, list[str]]:
    """Composite safety score (1.0 = no risk signal) and threat tags for the heuristic reasons."""
    score, tags = 1.0, []
    for reason in reasons:
        for needle, tag, penalty in SIGNAL_TAGS:
            if needle in reason:
                score -= penalty
                tags.append(tag)
                break
    return max(0.0, round(score, 2)), tags
