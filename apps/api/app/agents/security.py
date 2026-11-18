"""Best-effort output DLP; authorization stays outside the language model."""

import base64
import re
import unicodedata
from collections.abc import Iterable

SECURITY_REFUSAL = (
    "No puedo compartir instrucciones internas ni credenciales. "
    "Puedo ayudarte con peliculas y libros usando fuentes verificables."
)


def normalized(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


def exposes_protected_data(text: str, prompt: str, secrets: Iterable[str]) -> bool:
    # Inspect common encodings without trying to execute model-produced content.
    candidates = [text]
    for token in re.findall(r"[A-Za-z0-9+/=]{24,}", text):
        try:
            candidates.append(base64.b64decode(token, validate=True).decode("utf-8"))
        except (ValueError, UnicodeError):
            pass
    for token in re.findall(r"\b[0-9a-fA-F]{32,}\b", text):
        try:
            candidates.append(bytes.fromhex(token).decode("utf-8"))
        except (ValueError, UnicodeError):
            pass
    protected = [secret for secret in secrets if secret]
    words = normalized(prompt).split()
    # Overlapping 12-word windows detect partial disclosure, allowing public capabilities.
    fragments = [" ".join(words[i : i + 12]) for i in range(len(words) - 11)]
    for candidate in candidates:
        if any(
            secret in candidate
            if len(secret) >= 12
            else re.search(r"(?<![\w-])" + re.escape(secret) + r"(?![\w-])", candidate)
            for secret in protected
        ):
            return True
        if any(fragment in normalized(candidate) for fragment in fragments):
            return True
    return False
