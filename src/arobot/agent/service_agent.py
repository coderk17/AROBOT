"""LangChain agent combining RAG and MCP report tools."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from langchain.agents import create_agent
from langchain_core.messages import HumanMessage
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_openai import ChatOpenAI

from arobot.agent.tools import search_internal_docs
from arobot.config import settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """你是企业内部智能客服助手，通过企业微信为用户服务。

能力：
1. 回答政策、流程、产品等内部知识问题 — 优先调用 search_internal_docs 检索文档后再回答。
2. 处理用户上传的 Excel/CSV 报表 — 使用报表 MCP 工具（summary、filter、aggregate、top_n）。
3. 回答要简洁专业，引用文档来源；不确定时明确说明。

规则：
- 涉及报表文件时，file_path 使用用户提供的绝对路径。
- 不要编造数据；工具无结果时如实告知。
"""


class CustomerServiceAgent:
    def __init__(self) -> None:
        self._llm = ChatOpenAI(
            model=settings.llm_model,
            openai_api_key=settings.openai_api_key,
            openai_api_base=settings.openai_api_base,
            temperature=0.2,
        )
        self._mcp_client: MultiServerMCPClient | None = None
        self._agent = None

    def _report_mcp_connection(self) -> dict:
        if settings.mcp_report_url.strip():
            return {
                "report": {
                    "transport": "http",
                    "url": settings.mcp_report_url.strip(),
                }
            }
        mcp_path = settings.mcp_report_server_abs
        if not mcp_path.exists():
            raise FileNotFoundError(f"MCP report server not found: {mcp_path}")
        return {
            "report": {
                "transport": "stdio",
                "command": sys.executable,
                "args": [str(mcp_path)],
            }
        }

    async def setup(self) -> None:
        self._mcp_client = MultiServerMCPClient(self._report_mcp_connection())
        mcp_tools = await self._mcp_client.get_tools()
        tools = [search_internal_docs, *mcp_tools]
        self._agent = create_agent(
            self._llm,
            tools,
            system_prompt=SYSTEM_PROMPT,
        )
        logger.info("Agent ready with %d tools", len(tools))

    async def ainvoke(self, user_message: str, *, file_path: str | None = None) -> str:
        if self._agent is None:
            await self.setup()

        content = user_message
        if file_path:
            content = (
                f"{user_message}\n\n"
                f"[用户上传了报表文件，绝对路径: {file_path}。"
                f"请使用报表 MCP 工具分析。]"
            )

        result = await self._agent.ainvoke({"messages": [HumanMessage(content=content)]})
        messages = result.get("messages", [])
        if messages:
            return str(messages[-1].content)
        return "抱歉，暂时无法处理您的请求。"

    async def aclose(self) -> None:
        self._mcp_client = None
        self._agent = None
