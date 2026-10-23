"""Meaning of a text as 384 numbers (bge-small-en-v1.5 through fastembed), on this server's CPU: no patient
text leaves the server. The model loads once, in the background at startup; until it is ready, semantic
matching is simply skipped (regular matching and the lead still work).
"""

import asyncio
import logging
import threading
from pathlib import Path
from typing import Any

import numpy as np

from app.core.config import get_settings

log = logging.getLogger(__name__)
DIM = 384
_model: Any = None
_lock = threading.Lock()


def _load() -> Any:
    global _model
    with _lock:
        if _model is None:
            from fastembed import TextEmbedding  # heavy import, only when first needed

            settings = get_settings()
            cache = settings.embed_cache_dir or str(Path(__file__).resolve().parents[2] / ".models")
            _model = TextEmbedding(settings.embed_model, cache_dir=cache)
    return _model


async def warm() -> None:
    """Loads the model without blocking startup. A failure only turns semantic matching off."""
    try:
        await asyncio.to_thread(_load)
    except Exception:
        log.exception("embedding model could not be loaded; semantic matching is off")


def ready() -> bool:
    return _model is not None


def _vectors(texts: list[str]) -> np.ndarray:
    out = np.array(list(_load().embed(texts)), dtype=np.float32)
    return out / np.linalg.norm(out, axis=1, keepdims=True)


async def vector(text: str) -> list[float]:
    """One text, normalised (so a dot product is the cosine similarity)."""
    return [float(x) for x in (await asyncio.to_thread(_vectors, [text]))[0]]


async def vectors(texts: list[str]) -> np.ndarray:
    """Several texts at once (one row each), normalised."""
    return await asyncio.to_thread(_vectors, texts)


async def meaning(wordings: list[str]) -> list[float]:
    """One vector for a question and its other wordings: their average meaning, normalised."""
    mean = (await asyncio.to_thread(_vectors, wordings)).mean(axis=0)
    return [float(x) for x in mean / np.linalg.norm(mean)]


def as_pg(v: list[float]) -> str:
    """pgvector's text form, passed with a ::extensions.vector cast."""
    return "[" + ",".join(f"{x:.6f}" for x in v) + "]"
