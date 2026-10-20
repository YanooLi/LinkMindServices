"""Topic classification of a link into a fixed label set.

Provider order: OpenAI (if OPENAI_API_KEY) -> Hugging Face zero-shot Inference API (if HUGGINGFACE_TOKEN) ->
keyword rules. The source used is stored on the link (category_source) so results stay explainable.
"""
import json
import re

import httpx

LABELS = ["news", "shopping", "social", "video", "education", "developer", "finance", "travel", "spam", "other"]
KEYWORDS = {
    "developer": r"github|gitlab|stackoverflow|docs\.|developer|api|npm|pypi",
    "video": r"youtube|youtu\.be|vimeo|twitch|tiktok",
    "social": r"twitter|x\.com|facebook|instagram|linkedin|reddit|threads",
    "shopping": r"amazon|ebay|etsy|shop|store|cart|walmart|target\.com",
    "news": r"news|nytimes|bbc|cnn|reuters|bloomberg|wsj|guardian",
    "education": r"\.edu|coursera|edx|khanacademy|wikipedia|udemy",
    "finance": r"bank|finance|invest|stock|crypto|coinbase|robinhood",
    "travel": r"airbnb|booking|expedia|airline|hotel|flight|tripadvisor",
    "spam": r"free-?money|win-?prize|casino|viagra|crypto-?giveaway",
}


def keyword_category(url: str, title: str | None) -> str:
    text = f"{url} {title or ''}".lower()
    for label, pattern in KEYWORDS.items():
        if re.search(pattern, text):
            return label
    return "other"


async def openai_category(url: str, title: str | None, api_key: str, model: str) -> str | None:
    prompt = (f"Classify this link into exactly one of: {', '.join(LABELS)}.\nURL: {url}\nPage title: {title or '(none)'}\n"
              'Answer as JSON: {"label": "<one label>"}')
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post("https://api.openai.com/v1/chat/completions",
                                     headers={"Authorization": f"Bearer {api_key}"},
                                     json={"model": model, "temperature": 0,
                                           "response_format": {"type": "json_object"},
                                           "messages": [{"role": "user", "content": prompt}]})
            resp.raise_for_status()
            label = json.loads(resp.json()["choices"][0]["message"]["content"]).get("label", "").lower()
            return label if label in LABELS else None
    except (httpx.HTTPError, KeyError, ValueError):
        return None


async def huggingface_category(url: str, title: str | None, token: str, model: str) -> str | None:
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(f"https://api-inference.huggingface.co/models/{model}",
                                     headers={"Authorization": f"Bearer {token}"},
                                     json={"inputs": f"{title or ''} {url}",
                                           "parameters": {"candidate_labels": LABELS}})
            resp.raise_for_status()
            data = resp.json()
            return data["labels"][0] if data.get("labels") else None
    except (httpx.HTTPError, KeyError, ValueError, IndexError):
        return None


async def classify(url: str, title: str | None, settings) -> tuple[str, str]:
    if settings.openai_api_key:
        label = await openai_category(url, title, settings.openai_api_key, settings.openai_model)
        if label:
            return label, "openai"
    if settings.huggingface_token:
        label = await huggingface_category(url, title, settings.huggingface_token, settings.huggingface_model)
        if label:
            return label, "huggingface"
    return keyword_category(url, title), "rules"
