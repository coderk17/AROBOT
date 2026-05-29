"""CLI: ingest internal documents into the vector store."""

import argparse
import logging

from arobot.rag.ingest import ingest_documents

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest documents into Chroma knowledge base")
    parser.add_argument(
        "source",
        nargs="?",
        default=None,
        help="File or directory path (default: DOCUMENTS_DIR from .env)",
    )
    args = parser.parse_args()
    count = ingest_documents(args.source)
    logger.info("Ingested %d chunks", count)


if __name__ == "__main__":
    main()
