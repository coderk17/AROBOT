from langchain_core.documents import Document

from arobot.rag.ingest import get_vectorstore


def get_retriever(k: int = 4):
    vs = get_vectorstore()
    return vs.as_retriever(search_kwargs={"k": k})


def search_knowledge(query: str, k: int = 4) -> list[Document]:
    retriever = get_retriever(k=k)
    return retriever.invoke(query)
