"""Google Safe Browsing Lookup API v4 (https://developers.google.com/safe-browsing/v4/lookup-api)."""
import httpx

ENDPOINT = "https://safebrowsing.googleapis.com/v4/threatMatches:find"
THREATS = ["MALWARE", "SOCIAL_ENGINEERING", "UNWANTED_SOFTWARE", "POTENTIALLY_HARMFUL_APPLICATION"]


async def check(url: str, api_key: str, client: httpx.AsyncClient | None = None) -> list[str] | None:
    """Threat types Google reports for this URL; [] = clean, None = not checked (no key or API error)."""
    if not api_key:
        return None
    body = {"client": {"clientId": "linkmind", "clientVersion": "1.0"},
            "threatInfo": {"threatTypes": THREATS, "platformTypes": ["ANY_PLATFORM"],
                           "threatEntryTypes": ["URL"], "threatEntries": [{"url": url}]}}
    own = client is None
    client = client or httpx.AsyncClient(timeout=5.0)
    try:
        resp = await client.post(ENDPOINT, params={"key": api_key}, json=body)
        resp.raise_for_status()
        return sorted({m["threatType"] for m in resp.json().get("matches", [])})
    except httpx.HTTPError:
        return None
    finally:
        if own:
            await client.aclose()
