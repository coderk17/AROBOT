from langchain_openai import OpenAIEmbeddings

from arobot.config import settings


def get_embeddings() -> OpenAIEmbeddings:
    return OpenAIEmbeddings(
        model=settings.embedding_model,
        openai_api_key=settings.openai_api_key,
        openai_api_base=settings.openai_api_base,
    )
