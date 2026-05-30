"""Corpus ingestion utilities for the masking documentation RAG pipeline."""

from __future__ import annotations

from dataclasses import dataclass
import re
from pathlib import Path


DEFAULT_CORPUS_DIR = Path(__file__).with_name("corpus")

HEADING_CATEGORY_HINTS = {
    "NAME_RANDOMIZE": "FULL_NAME",
    "EMAIL_MASK": "EMAIL",
    "PHONE_MASK": "PHONE",
    "SSN_MASK": "SSN",
    "CREDIT_CARD_MASK": "CREDIT_CARD",
    "ACCOUNT_MASK": "ACCOUNT_NUMBER",
    "DATE_SHIFT": "DATE_OF_BIRTH",
    "ADDRESS_RANDOMIZE": "ADDRESS",
    "IP_MASK": "IP_ADDRESS",
    "NATIONAL_ID_MASK": "NATIONAL_ID",
    "AADHAAR": "NATIONAL_ID",
    "PASSPORT": "NATIONAL_ID",
    "IPV4": "IP_ADDRESS",
    "IPV6": "IP_ADDRESS",
}


@dataclass(frozen=True)
class DocumentChunk:
    """A searchable chunk of documentation."""

    chunk_id: str
    title: str
    source_file: str
    section: str
    text: str
    pii_category: str
    pii_categories: tuple[str, ...]
    anchor: str


def load_corpus(corpus_dir: Path | str = DEFAULT_CORPUS_DIR) -> list[DocumentChunk]:
    """Load all corpus files and split them into searchable chunks."""

    corpus_path = Path(corpus_dir)
    chunks: list[DocumentChunk] = []
    for file_path in sorted(corpus_path.glob("*.md")):
        metadata, body = _parse_front_matter(file_path.read_text())
        title = metadata.get("title", file_path.stem)
        doc_categories = tuple(metadata.get("pii_categories", ["GENERAL"]))
        sections = _split_sections(body)
        for index, section in enumerate(sections, start=1):
            pii_categories = _infer_categories(section["heading"], section["content"], doc_categories)
            pii_category = pii_categories[0]
            anchor = _slugify(section["heading"])
            chunk_id = f"{file_path.name}::section-{index}"
            text = f"{title}\n{section['heading']}\n{section['content']}".strip()
            chunks.append(
                DocumentChunk(
                    chunk_id=chunk_id,
                    title=title,
                    source_file=file_path.name,
                    section=section["heading"],
                    text=text,
                    pii_category=pii_category,
                    pii_categories=pii_categories,
                    anchor=anchor,
                )
            )
    return chunks


def _parse_front_matter(text: str) -> tuple[dict[str, object], str]:
    if not text.startswith("---\n"):
        return {}, text

    lines = text.splitlines()
    metadata: dict[str, object] = {}
    index = 1
    current_key: str | None = None
    list_values: list[str] = []

    while index < len(lines):
        line = lines[index]
        if line.strip() == "---":
            if current_key is not None:
                metadata[current_key] = list_values
            body = "\n".join(lines[index + 1 :]).lstrip()
            return metadata, body

        if re.match(r"^[A-Za-z_]+:\s*", line):
            if current_key is not None:
                metadata[current_key] = list_values if list_values else metadata[current_key]
                current_key = None
                list_values = []

            key, raw_value = line.split(":", 1)
            value = raw_value.strip()
            if value:
                metadata[key] = value
            else:
                current_key = key
                metadata[key] = []
        elif current_key and line.strip().startswith("- "):
            list_values.append(line.strip()[2:].strip())

        index += 1

    return metadata, text


def _split_sections(body: str) -> list[dict[str, str]]:
    sections: list[dict[str, str]] = []
    current_heading = "Overview"
    current_lines: list[str] = []

    for line in body.splitlines():
        if line.startswith("## "):
            if current_lines:
                sections.append(
                    {
                        "heading": current_heading,
                        "content": "\n".join(current_lines).strip(),
                    }
                )
            current_heading = line[3:].strip()
            current_lines = []
            continue

        if line.startswith("# "):
            continue

        current_lines.append(line)

    if current_lines:
        sections.append({"heading": current_heading, "content": "\n".join(current_lines).strip()})

    return [section for section in sections if section["content"]]


def _infer_categories(heading: str, content: str, doc_categories: tuple[str, ...]) -> tuple[str, ...]:
    searchable_text = f"{heading} {content}".upper()
    inferred = [category for hint, category in HEADING_CATEGORY_HINTS.items() if hint in searchable_text]
    if inferred:
        ordered = []
        for category in inferred:
            if category not in ordered:
                ordered.append(category)
        return tuple(ordered)
    return doc_categories


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", text.strip().lower()).strip("-")
    return slug or "section"
