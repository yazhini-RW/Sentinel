"""Load source documents and split them into overlapping chunks."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Chunk:
    chunk_id: int
    doc_name: str
    text: str


def _split_sentences(text: str) -> list[str]:
    # Split on sentence-ending punctuation followed by whitespace + capital/digit.
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(])", text.strip())
    return [p.strip() for p in parts if p.strip()]


def _strip_markdown(text: str) -> str:
    """Remove markdown decoration that would pollute chunks (headings, bullets,
    emphasis markers, inline code ticks). Content words are kept."""
    lines = []
    for line in text.splitlines():
        line = re.sub(r"^\s*#{1,6}\s+", "", line)  # headings
        line = re.sub(r"^\s*[-*+]\s+", "", line)  # bullets
        lines.append(line)
    text = "\n".join(lines)
    text = re.sub(r"\*{1,3}([^*]+)\*{1,3}", r"\1", text)  # bold/italic
    text = re.sub(r"`([^`]+)`", r"\1", text)  # inline code
    return text


def load_documents(folder: str | Path) -> dict[str, str]:
    """Read all .txt and .md files in a folder. Returns {filename: content}."""
    folder = Path(folder)
    if not folder.is_dir():
        raise FileNotFoundError(f"Source folder not found: {folder}")
    docs: dict[str, str] = {}
    for path in sorted(folder.iterdir()):
        if path.suffix.lower() in {".txt", ".md"} and path.is_file():
            content = path.read_text(encoding="utf-8", errors="replace").strip()
            if content:
                docs[path.name] = content
    if not docs:
        raise FileNotFoundError(f"No non-empty .txt/.md files found in {folder}")
    return docs


def chunk_documents(
    docs: dict[str, str],
    max_words: int = 120,
    overlap_sentences: int = 1,
) -> list[Chunk]:
    """Sentence-aware chunking: pack sentences into chunks up to ~max_words,
    carrying `overlap_sentences` sentences of overlap between consecutive chunks."""
    chunks: list[Chunk] = []
    for doc_name, content in docs.items():
        content = _strip_markdown(content)
        # Treat paragraphs as hard boundaries so chunks never straddle them.
        paragraphs = [p for p in re.split(r"\n\s*\n", content) if p.strip()]
        for para in _merge_title_paragraphs(paragraphs):
            sentences = _split_long(_split_sentences(re.sub(r"\s+", " ", para)), max_words)
            for text in _pack_sentences(sentences, max_words, overlap_sentences):
                # Skip a flush that is pure overlap already inside the previous chunk.
                if chunks and chunks[-1].doc_name == doc_name and text in chunks[-1].text:
                    continue
                chunks.append(Chunk(len(chunks), doc_name, text))
    return chunks


def _pack_sentences(sentences: list[str], max_words: int, overlap_sentences: int) -> list[str]:
    """Pack sentences into chunk texts up to ~max_words with sentence overlap."""
    texts: list[str] = []
    current: list[str] = []
    count = 0
    for sent in sentences:
        words = len(sent.split())
        if current and count + words > max_words:
            texts.append(" ".join(current))
            # Restart from overlap — unless the overlap alone would blow the
            # budget (that produces oversize, strict-subset chunks).
            keep = current[-overlap_sentences:] if overlap_sentences else []
            keep_count = sum(len(s.split()) for s in keep)
            if keep_count + words > max_words:
                keep, keep_count = [], 0
            current, count = list(keep), keep_count
        current.append(sent)
        count += words
    if current:
        texts.append(" ".join(current))
    return texts


def _merge_title_paragraphs(paragraphs: list[str]) -> list[str]:
    """A short heading-like paragraph (no sentence punctuation) is glued onto
    the following paragraph — a bare title makes a useless evidence chunk."""
    merged: list[str] = []
    pending = ""
    for para in paragraphs:
        if len(para.split()) < 8 and not para.rstrip().endswith((".", "!", "?")):
            pending = f"{pending} {para}".strip()
            continue
        merged.append(f"{pending}: {para}" if pending else para)
        pending = ""
    if pending:
        merged.append(pending)
    return merged


def _split_long(sentences: list[str], max_words: int) -> list[str]:
    """Hard-split any 'sentence' longer than max_words (lowercase-styled text
    may never match the sentence regex and would become one giant chunk)."""
    out: list[str] = []
    for sent in sentences:
        words = sent.split()
        if len(words) <= max_words:
            out.append(sent)
        else:
            out.extend(
                " ".join(words[i : i + max_words]) for i in range(0, len(words), max_words)
            )
    return out
