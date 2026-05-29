from pathlib import Path

from langchain_chroma import Chroma
from langchain_text_splitters import RecursiveCharacterTextSplitter

from arobot.config import settings
from arobot.rag.embeddings import get_embeddings
from arobot.rag.multimodal_loader import load_directory, load_file


def ingest_documents(
    source: str | Path | None = None,
    *,
    chunk_size: int = 800,
    chunk_overlap: int = 120,
) -> int:
    """Ingest documents into Chroma. Returns number of chunks stored."""
    source_path = Path(source) if source else Path(settings.documents_dir)
    if source_path.is_file():
        documents = load_file(source_path)
    else:
        documents = load_directory(source_path)

    if not documents:
        return 0

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", "。", "；", ". ", " ", ""],
    )
    chunks = splitter.split_documents(documents)

    persist_dir = Path(settings.chroma_persist_dir)
    persist_dir.mkdir(parents=True, exist_ok=True)

    Chroma.from_documents(
        documents=chunks,
        embedding=get_embeddings(),
        persist_directory=str(persist_dir),
        collection_name="knowledge_base",
    )
    return len(chunks)


def get_vectorstore() -> Chroma:
    persist_dir = Path(settings.chroma_persist_dir)
    persist_dir.mkdir(parents=True, exist_ok=True)
    return Chroma(
        collection_name="knowledge_base",
        embedding_function=get_embeddings(),
        persist_directory=str(persist_dir),
    )
