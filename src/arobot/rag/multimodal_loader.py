"""Load text, PDF, Office, and image documents for RAG."""

from __future__ import annotations

import base64
from pathlib import Path

from langchain_core.documents import Document
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI

from arobot.config import settings

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}
TEXT_SUFFIXES = {".txt", ".md", ".csv", ".json", ".html", ".htm"}
OFFICE_SUFFIXES = {".pdf", ".docx", ".doc", ".pptx", ".xlsx", ".xls"}


def _vision_describe_image(path: Path) -> str:
    """Use vision LLM to describe image content for embedding."""
    llm = ChatOpenAI(
        model=settings.vision_model,
        openai_api_key=settings.openai_api_key,
        openai_api_base=settings.openai_api_base,
        temperature=0,
    )
    data = base64.b64encode(path.read_bytes()).decode()
    suffix = path.suffix.lower().lstrip(".")
    mime = "jpeg" if suffix in ("jpg", "jpeg") else suffix
    message = HumanMessage(
        content=[
            {
                "type": "text",
                "text": (
                    "Describe this image in detail for a knowledge base. "
                    "Include visible text, charts, tables, and key facts."
                ),
            },
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/{mime};base64,{data}"},
            },
        ]
    )
    response = llm.invoke([message])
    return str(response.content)


def load_file(path: Path) -> list[Document]:
    suffix = path.suffix.lower()
    source = str(path.resolve())

    if suffix in IMAGE_SUFFIXES:
        description = _vision_describe_image(path)
        return [
            Document(
                page_content=description,
                metadata={"source": source, "type": "image", "filename": path.name},
            )
        ]

    if suffix in TEXT_SUFFIXES:
        text = path.read_text(encoding="utf-8", errors="replace")
        return [
            Document(
                page_content=text,
                metadata={"source": source, "type": "text", "filename": path.name},
            )
        ]

    if suffix in OFFICE_SUFFIXES:
        from langchain_community.document_loaders import UnstructuredLoader

        loader = UnstructuredLoader(str(path))
        docs = loader.load()
        for doc in docs:
            doc.metadata.setdefault("source", source)
            doc.metadata.setdefault("filename", path.name)
            doc.metadata.setdefault("type", "document")
        return docs

    return []


def load_directory(directory: Path) -> list[Document]:
    if not directory.exists():
        return []

    all_docs: list[Document] = []
    patterns = ["**/*"]
    for pattern in patterns:
        for path in directory.glob(pattern):
            if not path.is_file():
                continue
            if path.name.startswith("."):
                continue
            try:
                all_docs.extend(load_file(path))
            except Exception as exc:
                all_docs.append(
                    Document(
                        page_content=f"[Failed to load {path.name}: {exc}]",
                        metadata={"source": str(path), "type": "error"},
                    )
                )
    return all_docs
