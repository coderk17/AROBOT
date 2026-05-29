"""LangChain tools for knowledge search."""

from langchain_core.tools import tool

from arobot.rag.retriever import search_knowledge


@tool
def search_internal_docs(query: str) -> str:
    """Search internal knowledge base (policies, manuals, multimodal docs). Use for Q&A."""
    docs = search_knowledge(query, k=5)
    if not docs:
        return "No relevant documents found in the knowledge base."
    parts = []
    for i, doc in enumerate(docs, 1):
        src = doc.metadata.get("filename") or doc.metadata.get("source", "unknown")
        parts.append(f"[{i}] ({src})\n{doc.page_content}")
    return "\n\n---\n\n".join(parts)
