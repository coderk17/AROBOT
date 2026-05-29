"""WeCom (企业微信) intelligent bot channel via WebSocket long connection."""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections import OrderedDict
from pathlib import Path
from typing import Any

from arobot.agent.service_agent import CustomerServiceAgent
from arobot.config import settings

logger = logging.getLogger(__name__)

REPORT_SUFFIXES = {".xlsx", ".xls", ".csv"}


class WeComChannel:
    """Enterprise WeChat AI bot channel (企信/企微智能机器人)."""

    def __init__(self, agent: CustomerServiceAgent) -> None:
        self._agent = agent
        self._client: Any = None
        self._generate_req_id: Any = None
        self._chat_frames: dict[str, Any] = {}
        self._processed_ids: OrderedDict[str, None] = OrderedDict()
        self._max_cache = 500

    def _is_allowed(self, userid: str) -> bool:
        allowed = settings.allowed_users
        return not allowed or userid in allowed

    def _remember_frame(self, frame: dict) -> str:
        body = frame.get("body", {})
        chat_id = body.get("chatid") or body.get("from", {}).get("userid", "default")
        self._chat_frames[chat_id] = frame
        return chat_id

    def _dedupe(self, msgid: str) -> bool:
        if msgid in self._processed_ids:
            return True
        self._processed_ids[msgid] = None
        if len(self._processed_ids) > self._max_cache:
            self._processed_ids.popitem(last=False)
        return False

    async def _save_uploaded_file(self, frame: dict) -> Path | None:
        body = frame.get("body", {})
        file_info = body.get("file") or {}
        url = file_info.get("url")
        filename = file_info.get("filename", f"upload_{uuid.uuid4().hex[:8]}.xlsx")
        if not url:
            return None

        upload_dir = Path(settings.upload_dir)
        upload_dir.mkdir(parents=True, exist_ok=True)
        dest = upload_dir / filename

        try:
            aes_key = file_info.get("aes_key")
            if hasattr(self._client, "download_file"):
                data, _ = await self._client.download_file(url, aes_key)
                dest.write_bytes(data)
            else:
                import httpx

                async with httpx.AsyncClient() as client:
                    resp = await client.get(url, timeout=60)
                    resp.raise_for_status()
                    dest.write_bytes(resp.content)
            return dest.resolve()
        except Exception:
            logger.exception("Failed to download file from WeCom")
            return None

    async def _reply_stream(self, frame: dict, text: str) -> None:
        stream_id = self._generate_req_id("stream")
        await self._client.reply_stream(
            frame,
            stream_id,
            "正在处理，请稍候…",
            finish=False,
        )
        chunk_size = 400
        for i in range(0, len(text), chunk_size):
            part = text[i : i + chunk_size]
            is_last = i + chunk_size >= len(text)
            await self._client.reply_stream(
                frame,
                stream_id,
                part,
                finish=is_last,
            )

    async def _on_text(self, frame: dict) -> None:
        body = frame.get("body", {})
        msgid = body.get("msgid", "")
        if msgid and self._dedupe(msgid):
            return

        userid = body.get("from", {}).get("userid", "")
        if not self._is_allowed(userid):
            await self._reply_stream(frame, "您暂无使用权限，请联系管理员。")
            return

        self._remember_frame(frame)
        content = (body.get("text") or {}).get("content", "").strip()
        if not content:
            return

        try:
            answer = await self._agent.ainvoke(content)
        except Exception as exc:
            logger.exception("Agent error on text message")
            answer = f"处理失败：{exc}"

        await self._reply_stream(frame, answer)

    async def _on_file(self, frame: dict) -> None:
        body = frame.get("body", {})
        msgid = body.get("msgid", "")
        if msgid and self._dedupe(msgid):
            return

        userid = body.get("from", {}).get("userid", "")
        if not self._is_allowed(userid):
            await self._reply_stream(frame, "您暂无使用权限，请联系管理员。")
            return

        self._remember_frame(frame)
        filename = (body.get("file") or {}).get("filename", "")
        suffix = Path(filename).suffix.lower()

        if suffix not in REPORT_SUFFIXES:
            await self._reply_stream(
                frame,
                f"暂不支持该文件类型（{suffix}）。请上传 Excel (.xlsx/.xls) 或 CSV 报表。",
            )
            return

        saved = await self._save_uploaded_file(frame)
        if not saved:
            await self._reply_stream(frame, "文件下载失败，请重试。")
            return

        prompt = (
            body.get("text", {}).get("content")
            or "请分析这份报表：给出概览、关键指标和异常点。"
        )
        try:
            answer = await self._agent.ainvoke(prompt, file_path=str(saved))
        except Exception as exc:
            logger.exception("Agent error on file message")
            answer = f"报表处理失败：{exc}"

        await self._reply_stream(frame, answer)

    async def _on_enter_chat(self, frame: dict) -> None:
        welcome = (
            "您好！我是智能客服，可以：\n"
            "1. 回答内部知识库问题\n"
            "2. 接收 Excel/CSV 报表并自动分析\n\n"
            "直接发送问题或上传文件即可。"
        )
        try:
            await self._client.reply_welcome(
                frame,
                {"msgtype": "text", "text": {"content": welcome}},
            )
        except Exception:
            logger.debug("Welcome reply skipped", exc_info=True)

    def _register_handlers(self) -> None:
        self._client.on("message.text", lambda f: asyncio.create_task(self._on_text(f)))
        self._client.on("message.file", lambda f: asyncio.create_task(self._on_file(f)))
        self._client.on(
            "event.enter_chat",
            lambda f: asyncio.create_task(self._on_enter_chat(f)),
        )

    async def start(self) -> None:
        if not settings.wecom_bot_id or not settings.wecom_bot_secret:
            raise ValueError("WECOM_BOT_ID and WECOM_BOT_SECRET are required")

        from wecom_aibot_sdk import WSClient, generate_req_id

        self._generate_req_id = generate_req_id
        self._client = WSClient(
            {
                "bot_id": settings.wecom_bot_id,
                "secret": settings.wecom_bot_secret,
                "reconnect_interval": 1000,
                "max_reconnect_attempts": -1,
                "heartbeat_interval": 30000,
            }
        )
        self._register_handlers()
        await self._client.connect_async()
        logger.info("WeCom bot connected (bot_id=%s)", settings.wecom_bot_id)

        while True:
            await asyncio.sleep(3600)
