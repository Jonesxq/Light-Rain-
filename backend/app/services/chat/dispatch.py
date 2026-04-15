"""Public chat entrypoint dispatchers."""

from __future__ import annotations

from typing import AsyncGenerator

from app.core.config.settings import settings
from app.crud.chat import chat_crud
from app.models.chat import ChatRole
from app.schemas.chat import ChatRequest
from app.utils.chat_intent import is_time_query, is_weather_query


class ChatDispatch:
    """Routes chat requests into tool, reasoning, or RAG flows."""

    def __init__(self, service):
        self.service = service

    async def process_chat(self, db, user_id: int, session_id: int, chat_request: ChatRequest):
        session = await chat_crud.get_session(db, session_id)
        await chat_crud.create_message(db, session_id=session_id, role="user", content=chat_request.message)
        if session:
            await self.service._auto_rename_session(db, session, chat_request.message)

        chat_history = await self.service._build_langchain_history(db, session_id, limit=10)
        disclaimer_codes, risk_tags = await self.service._get_risk_info(
            db=db,
            user_id=user_id,
            text=chat_request.message,
            model=None,
        )

        is_weather = is_weather_query(chat_request.message)
        if chat_request.deep_search and not is_weather:
            if not settings.llm.SERPER_API_KEY:
                raise ValueError("搜索不可用：未配置 SERPER_API_KEY")
            return await self.service._deep_search_answer(
                db=db,
                user_id=user_id,
                session_id=session_id,
                question=chat_request.message,
                chat_history=chat_history,
                model=None,
                deep_think=chat_request.deep_think,
                disclaimer_codes=disclaimer_codes,
                risk_tags=risk_tags,
            )

        if chat_request.deep_think and not is_weather:
            return await self.service._deep_think_answer(
                db=db,
                user_id=user_id,
                session_id=session_id,
                question=chat_request.message,
                chat_history=chat_history,
                model=None,
                disclaimer_codes=disclaimer_codes,
                risk_tags=risk_tags,
            )

        return await self.service.run_tool_chat(
            db=db,
            user_id=user_id,
            session_id=session_id,
            input_text=chat_request.message,
            chat_history=chat_history,
            disclaimer_codes=disclaimer_codes,
            risk_tags=risk_tags,
        )

    async def stream_chat(self, db, user_id: int, session_id: int, chat_request: ChatRequest) -> AsyncGenerator[str, None]:
        session = await chat_crud.get_session(db, session_id)
        user_msg = await chat_crud.create_message(db, session_id=session_id, role="user", content=chat_request.message)
        if session:
            await self.service._auto_rename_session(db, session, chat_request.message)
        chat_history = await self.service._build_langchain_history(db, session_id, limit=10)
        disclaimer_codes, risk_tags = await self.service._get_risk_info(
            db=db,
            user_id=user_id,
            text=chat_request.message,
            model=None,
        )

        is_time = is_time_query(chat_request.message)
        is_weather = is_weather_query(chat_request.message)
        if is_time or is_weather:
            async for payload in self.service._stream_tool_chat(
                db=db,
                user_id=user_id,
                session_id=session_id,
                input_text=chat_request.message,
                chat_history=chat_history,
                user_message_id=user_msg.id,
                disclaimer_codes=disclaimer_codes,
                risk_tags=risk_tags,
            ):
                yield payload
            return

        if chat_request.deep_search:
            if not settings.llm.SERPER_API_KEY:
                yield 'data: {"event":"error","message":"搜索不可用：未配置 SERPER_API_KEY"}\n\n'
                return
            async for payload in self.service._stream_deep_search(
                db=db,
                user_id=user_id,
                session_id=session_id,
                input_text=chat_request.message,
                model=None,
                chat_history=chat_history,
                user_message_id=user_msg.id,
                deep_think=chat_request.deep_think,
                disclaimer_codes=disclaimer_codes,
                risk_tags=risk_tags,
            ):
                yield payload
            return

        if chat_request.deep_think:
            async for payload in self.service._stream_deep_think(
                db=db,
                user_id=user_id,
                session_id=session_id,
                input_text=chat_request.message,
                model=None,
                chat_history=chat_history,
                user_message_id=user_msg.id,
                disclaimer_codes=disclaimer_codes,
                risk_tags=risk_tags,
            ):
                yield payload
            return

        async for payload in self.service._stream_tool_chat(
            db=db,
            user_id=user_id,
            session_id=session_id,
            input_text=chat_request.message,
            chat_history=chat_history,
            user_message_id=user_msg.id,
            disclaimer_codes=disclaimer_codes,
            risk_tags=risk_tags,
        ):
            yield payload

    async def stream_resend(
        self,
        db,
        user_id: int,
        message_id: int,
        new_message: str,
        deep_search: bool = False,
        deep_think: bool = False,
    ) -> AsyncGenerator[str, None]:
        message, session = await self.service._get_message_and_session_for_user(db, user_id, message_id)
        if message.role != ChatRole.USER:
            raise ValueError("只能编辑用户消息")
        content = (new_message or "").strip()
        if not content:
            raise ValueError("消息不能为空")

        updated = await chat_crud.update_message_content(db, message_id, content)
        if not updated:
            raise ValueError("消息更新失败")
        await chat_crud.delete_messages_after(db, session.id, message_id)
        await chat_crud.update_session_time(db, session.id)
        if session:
            await self.service._auto_rename_session(db, session, content)

        chat_history = await self.service._build_langchain_history(db, session.id, limit=10)
        disclaimer_codes, risk_tags = await self.service._get_risk_info(
            db=db,
            user_id=user_id,
            text=updated.content,
            model=None,
        )
        if updated.kb_id is not None:
            async for payload in self.service._stream_rag_with_context(
                db=db,
                user_id=user_id,
                session_id=session.id,
                kb_id=updated.kb_id,
                input_text=updated.content,
                model=None,
                user_message_id=updated.id,
                disclaimer_codes=disclaimer_codes,
                risk_tags=risk_tags,
                chat_history=chat_history,
            ):
                yield payload
            return

        is_time = is_time_query(updated.content)
        is_weather = is_weather_query(updated.content)
        if deep_search and (is_time or is_weather):
            deep_search = False
        if deep_think and (is_time or is_weather):
            deep_think = False

        if deep_search:
            if not settings.llm.SERPER_API_KEY:
                yield 'data: {"event":"error","message":"搜索不可用：未配置 SERPER_API_KEY"}\n\n'
                return
            async for payload in self.service._stream_deep_search(
                db=db,
                user_id=user_id,
                session_id=session.id,
                input_text=updated.content,
                model=None,
                chat_history=chat_history,
                user_message_id=updated.id,
                deep_think=deep_think,
                disclaimer_codes=disclaimer_codes,
                risk_tags=risk_tags,
            ):
                yield payload
            return

        if deep_think:
            async for payload in self.service._stream_deep_think(
                db=db,
                user_id=user_id,
                session_id=session.id,
                input_text=updated.content,
                model=None,
                chat_history=chat_history,
                user_message_id=updated.id,
                disclaimer_codes=disclaimer_codes,
                risk_tags=risk_tags,
            ):
                yield payload
            return

        async for payload in self.service._stream_tool_chat(
            db=db,
            user_id=user_id,
            session_id=session.id,
            input_text=updated.content,
            chat_history=chat_history,
            user_message_id=updated.id,
            disclaimer_codes=disclaimer_codes,
            risk_tags=risk_tags,
        ):
            yield payload

    async def stream_regenerate(
        self,
        db,
        user_id: int,
        message_id: int,
        deep_search: bool = False,
        deep_think: bool = False,
    ) -> AsyncGenerator[str, None]:
        message, session = await self.service._get_message_and_session_for_user(db, user_id, message_id)
        messages = await chat_crud.get_session_messages(db, session.id)
        target_index = next((index for index, msg in enumerate(messages) if msg.id == message.id), None)
        if target_index is None:
            raise ValueError("消息不存在")

        user_message = message if message.role == ChatRole.USER else None
        if user_message is None:
            for index in range(target_index - 1, -1, -1):
                if messages[index].role == ChatRole.USER:
                    user_message = messages[index]
                    break
        if not user_message:
            raise ValueError("未找到对应的用户消息")

        await chat_crud.delete_messages_after(db, session.id, user_message.id)
        await chat_crud.update_session_time(db, session.id)

        chat_history = await self.service._build_langchain_history(db, session.id, limit=10)
        disclaimer_codes, risk_tags = await self.service._get_risk_info(
            db=db,
            user_id=user_id,
            text=user_message.content,
            model=None,
        )
        if user_message.kb_id is not None:
            async for payload in self.service._stream_rag_with_context(
                db=db,
                user_id=user_id,
                session_id=session.id,
                kb_id=user_message.kb_id,
                input_text=user_message.content,
                model=None,
                user_message_id=user_message.id,
                disclaimer_codes=disclaimer_codes,
                risk_tags=risk_tags,
                chat_history=chat_history,
            ):
                yield payload
            return

        is_time = is_time_query(user_message.content)
        is_weather = is_weather_query(user_message.content)
        if deep_search and (is_time or is_weather):
            deep_search = False
        if deep_think and (is_time or is_weather):
            deep_think = False

        if deep_search:
            if not settings.llm.SERPER_API_KEY:
                yield 'data: {"event":"error","message":"搜索不可用：未配置 SERPER_API_KEY"}\n\n'
                return
            async for payload in self.service._stream_deep_search(
                db=db,
                user_id=user_id,
                session_id=session.id,
                input_text=user_message.content,
                model=None,
                chat_history=chat_history,
                user_message_id=user_message.id,
                deep_think=deep_think,
                disclaimer_codes=disclaimer_codes,
                risk_tags=risk_tags,
            ):
                yield payload
            return

        if deep_think:
            async for payload in self.service._stream_deep_think(
                db=db,
                user_id=user_id,
                session_id=session.id,
                input_text=user_message.content,
                model=None,
                chat_history=chat_history,
                user_message_id=user_message.id,
                disclaimer_codes=disclaimer_codes,
                risk_tags=risk_tags,
            ):
                yield payload
            return

        async for payload in self.service._stream_tool_chat(
            db=db,
            user_id=user_id,
            session_id=session.id,
            input_text=user_message.content,
            chat_history=chat_history,
            user_message_id=user_message.id,
            disclaimer_codes=disclaimer_codes,
            risk_tags=risk_tags,
        ):
            yield payload
