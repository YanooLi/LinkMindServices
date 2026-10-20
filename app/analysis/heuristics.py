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


HIGH_SIGNAL = ("uses a raw IP", "contains '@'", "punycode", "mentions '")
WEAK_SIGNAL = ("not encrypted", "very long URL")


def risk_from_signals(reasons: list[str]) -> str:
    """One high-signal reason, or two other non-weak reasons, make a link suspicious."""
    if any(any(h in r for h in HIGH_SIGNAL) for r in reasons):
        return "suspicious"
    strong = [r for r in reasons if not any(w in r for w in WEAK_SIGNAL)]
    return "suspicious" if len(strong) >= 2 else "safe"
