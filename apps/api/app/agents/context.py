"""Deterministic LLM projections. Full validated evidence stays in backend memory."""

from __future__ import annotations

import json
import re
from typing import Any

from groq.types.chat import ChatCompletionMessageParam, ChatCompletionToolParam

from app.tools.models import INPUTS, Movie, ToolResult


def cache_key(name: str, arguments: str) -> str:
    model = INPUTS[name].model_validate_json(arguments)
    data = model.model_dump()
    for field in ("query", "title", "author"):
        if isinstance(data.get(field), str):
            data[field] = " ".join(data[field].split()).casefold()
    return name + ":" + json.dumps(data, sort_keys=True, ensure_ascii=False)


def project_result(result: ToolResult, *, excerpt_chars: int = 350) -> dict[str, Any]:
    items = []
    for item in result.items:
        data = item.model_dump(exclude_none=True)
        data.pop("poster_url", None)  # Visual asset remains available in the full artifact.
        data.pop("imdb_url", None)
        truncated = []
        for field in ("overview", "description"):
            text = data.get(field)
            if isinstance(text, str) and len(text) > excerpt_chars:
                match = re.search(
                    r"adapt\w*|pel[ií]cula|\bfilm\w*|\bmovie\w*|cinema\w*",
                    text,
                    flags=re.IGNORECASE,
                )
                if match and match.start() > excerpt_chars:
                    start = max(0, match.start() - 80)
                    half = (excerpt_chars - 5) // 2
                    data[field] = text[:half] + "\n[…]\n" + text[start : start + half]
                else:
                    data[field] = text[:excerpt_chars]
                truncated.append(field)
        # Never summarize identities, authors, credits, keywords, ratings or source links.
        data = {key: value for key, value in data.items() if value not in ([], "")}
        if truncated:
            data["truncated_fields"] = truncated
        items.append(data)
    return {
        "source": result.source,
        "items": items,
        **({"error": result.error} if result.error else {}),
    }


def evidence_json(results: list[ToolResult], *, excerpt_chars: int = 350) -> str:
    facts: dict[tuple[str, str | int], dict[str, Any]] = {}
    errors = []
    movies = [item for result in results for item in result.items if isinstance(item, Movie)]

    def priority(book: dict[str, Any]) -> int:
        # Ranking excerpts is not proof of adaptation; all candidates retain identities.
        return max(
            (
                2 * int(movie.title.casefold() == book["title"].casefold())
                + int(
                    any(
                        c.job == "Novel"
                        and c.name.casefold() in {a.casefold() for a in book.get("authors", [])}
                        for c in movie.writing_credits
                    )
                )
                for movie in movies
            ),
            default=0,
        )

    for result in results:
        if result.error:
            errors.append({"source": result.source, "error": result.error})
        items = project_result(result, excerpt_chars=excerpt_chars)["items"]
        if result.source == "google_books" and items:
            best = max(range(len(items)), key=lambda index: priority(items[index]))
            for index, item in enumerate(items):
                if index != best and item.pop("description", None) is not None:
                    item["omitted_fields"] = ["description"]
        for item in items:
            key = (item["kind"], item["id"])
            facts[key] = {**facts.get(key, {}), **item}
    return json.dumps(
        {"items": list(facts.values()), "errors": errors[-2:]},
        ensure_ascii=False,
        separators=(",", ":"),
    )


def dialogue(messages: list[ChatCompletionMessageParam]) -> list[ChatCompletionMessageParam]:
    result: list[ChatCompletionMessageParam] = []
    for index, message in enumerate(messages):
        content = message.get("content")
        if message["role"] in {"user", "assistant"} and not message.get("tool_calls"):
            if isinstance(content, str):
                # Keep the latest full dialogue: "which of those three" needs all recommendations.
                text = content if index >= len(messages) - 2 else content[:1000]
                if message["role"] == "user":
                    result.append({"role": "user", "content": text})
                else:
                    result.append({"role": "assistant", "content": text})
    return result[-12:]


def compact_tools(tools: list[ChatCompletionToolParam]) -> list[ChatCompletionToolParam]:
    def clean(value: Any, properties: bool = False) -> Any:
        if isinstance(value, dict):
            return {
                key: clean(item, key in {"properties", "$defs"})
                for key, item in value.items()
                if properties or key != "title"
            }
        if isinstance(value, list):
            return [clean(item) for item in value]
        return value

    return [clean(tool) for tool in tools]
