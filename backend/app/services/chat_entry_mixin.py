"""Chat entrypoints (process/stream/resend/regenerate)."""

import json
from typing import AsyncGenerator, Optional

from langchain_classic.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.prompts import MessagesPlaceholder, ChatPromptTemplate
from sqlalchemy.ext.asyncio import AsyncSession

from app.constant.prompts import CHAT_SYSTEM_PROMPT
from app.core.config.settings import settings
from app.core.logger import logger_manager
from app.crud.chat import chat_crud
from app.models.chat import ChatRole
from app.schemas.chat import ChatRequest
from app.services.usage import usage_service, UsageTimer
from app.tools.online_search import online_search
from app.tools.get_weather import get_weather
from app.tools.get_system_time import get_system_time
from app.tools.text_to_image import text_to_image
from app.utils.chat_history import history_to_payload
from app.utils.chat_intent import is_time_query, is_weather_query
from app.utils.llm_usage import estimate_usage

logger = logger_manager.get_logger(__name__)


class ChatEntryMixin:
    """Public entrypoints for chat."""

    async def process_chat(
            self,
            db: AsyncSession,
            user_id: int,
            session_id: int,
            chat_request: ChatRequest
    ):
        # 1) 基础验证与用户消息持久化
        """process_chat ?????"""
        session = await chat_crud.get_session(db, session_id)
        await chat_crud.create_message(db, session_id=session_id, role="user", content=chat_request.message)
        if session:
            await self._auto_rename_session(db, session, chat_request.message)

        # 2) 构建历史对话（LangChain Message 结构）
        chat_history = await self._build_langchain_history(db, session_id, limit=10)
        disclaimer_codes, risk_tags = await self._get_risk_info(
            db=db,
            user_id=user_id,
            text=chat_request.message,
            model=None,
        )

        try:
            # 3) 当前时间/日期问题，直接用本地时间工具返回
            if is_time_query(chat_request.message):
                try:
                    time_text = get_system_time.invoke({})
                except Exception:
                    time_text = get_system_time.run({})

                ai_msg = await chat_crud.create_message(
                    db,
                    session_id=session_id,
                    role="assistant",
                    content=time_text,
                    model_name=settings.llm.DEFAULT_MODEL,
                    token_count=0,
                    disclaimer_codes=disclaimer_codes,
                    risk_tags=risk_tags,
                )
                await self._save_prompt_snapshot(
                    db=db,
                    message_id=ai_msg.id,
                    user_id=user_id,
                    session_id=session_id,
                    mode="tool_time",
                    payload={
                        "user_input": chat_request.message,
                        "tool": "get_system_time",
                    },
                )
                return ai_msg

            is_weather = is_weather_query(chat_request.message)

            # 4) 深度研究（联网搜索）
            if chat_request.deep_search and not is_weather:
                if not settings.llm.SERPER_API_KEY:
                    raise ValueError("搜索不可用：未配置 SERPER_API_KEY")
                ai_msg = await self._deep_search_answer(
                    db=db,
                    user_id=user_id,
                    session_id=session_id,
                    question=chat_request.message,
                    chat_history=chat_history,
                    deep_think=chat_request.deep_think,
                    disclaimer_codes=disclaimer_codes,
                    risk_tags=risk_tags,
                )
                return ai_msg

            # 5) 深度思考（推理，不联网）
            if chat_request.deep_think and not is_weather:
                ai_msg = await self._deep_think_answer(
                    db=db,
                    user_id=user_id,
                    session_id=session_id,
                    question=chat_request.message,
                    chat_history=chat_history,
                    model=None,
                    disclaimer_codes=disclaimer_codes,
                    risk_tags=risk_tags,
                )
                return ai_msg

            # 6) 其他问题走 LLM + 工具路由（天气问题也交给 agent 强制调用工具）
            resolved = await self._resolve_user_llm_config(db, user_id, None)
            llm = self._get_llm(
                resolved["model"],
                api_key=resolved["api_key"],
                api_base_url=resolved["api_base_url"],
            )
            tools = [online_search, get_weather, get_system_time, text_to_image]

            # 6) 按 agent 规范构建 Prompt
            temp_context = await self._get_temp_context(db, user_id, chat_request.message)
            system_prompt = CHAT_SYSTEM_PROMPT
            if temp_context:
                system_prompt = f"{CHAT_SYSTEM_PROMPT}\n\n【临时资料】\n{temp_context}"
            prompt = ChatPromptTemplate.from_messages([
                ("system", system_prompt),
                MessagesPlaceholder(variable_name="chat_history"),
                ("human", "{input}"),
                MessagesPlaceholder(variable_name="agent_scratchpad"),
            ])

            # 7) 创建 Tool Calling Agent
            agent = create_tool_calling_agent(llm, tools, prompt)

            # 8) 构建执行器
            agent_executor = AgentExecutor(
                agent=agent,
                tools=tools,
                verbose=True,
                handle_parsing_errors=True
            )

            # 9) 执行调用
            timer = UsageTimer()
            try:
                result = await agent_executor.ainvoke({
                    "input": chat_request.message,
                    "chat_history": chat_history
                })
            except Exception as exc:
                latency_ms = timer.stop_ms()
                await usage_service.record_event(
                    db,
                    user_id=user_id,
                    event_type="chat",
                    model_name=llm.model_name,
                    prompt_tokens=None,
                    completion_tokens=None,
                    total_tokens=None,
                    token_missing=True,
                    latency_ms=latency_ms,
                    cost_usd=0.0,
                    success=False,
                    error_message=str(exc),
                    metadata={"session_id": session_id},
                )
                raise

            latency_ms = timer.stop_ms()

            # 10) 提取输出内容（兼容 AIMessage）
            ai_content = result.get("output", "")

            # 如果输出是 AIMessage 对象（某些极端配置下），提取文本
            if hasattr(ai_content, "content"):
                ai_content = ai_content.content

            usage = usage_service.extract_usage(result)
            if usage.get("token_missing") or usage.get("total_tokens") is None:
                token_messages = [
                    SystemMessage(content=system_prompt),
                    *chat_history,
                    HumanMessage(content=chat_request.message),
                ]
                usage = estimate_usage(llm, token_messages, str(ai_content))
            elif usage.get("total_tokens") is None:
                usage["total_tokens"] = (usage.get("prompt_tokens") or 0) + (usage.get("completion_tokens") or 0)

            # 11) 统计 Token
            total_tokens = usage.get("total_tokens") or 0
            cost_usd = usage_service.compute_cost(
                llm.model_name,
                usage.get("prompt_tokens"),
                usage.get("completion_tokens"),
            )
            await usage_service.record_event(
                db,
                user_id=user_id,
                event_type="chat",
                model_name=llm.model_name,
                prompt_tokens=usage.get("prompt_tokens"),
                completion_tokens=usage.get("completion_tokens"),
                total_tokens=usage.get("total_tokens"),
                token_missing=bool(usage.get("token_missing")),
                latency_ms=latency_ms,
                cost_usd=cost_usd,
                success=True,
                metadata={"session_id": session_id},
            )

            # 12) 持久化 AI 回复
            ai_msg = await chat_crud.create_message(
                db,
                session_id=session_id,
                role="assistant",
                content=ai_content,
                model_name=llm.model_name,
                token_count=total_tokens,
                disclaimer_codes=disclaimer_codes,
                risk_tags=risk_tags,
            )
            await self._save_prompt_snapshot(
                db=db,
                message_id=ai_msg.id,
                user_id=user_id,
                session_id=session_id,
                mode="tool_chat",
                payload={
                    "system_prompt": system_prompt,
                    "user_input": chat_request.message,
                    "chat_history": history_to_payload(chat_history),
                    "tools": ["online_search", "get_weather", "get_system_time", "text_to_image"],
                    "temp_context": temp_context,
                    "model_name": llm.model_name,
                },
            )

            return ai_msg

        except Exception as e:
            logger.exception(f"Agent Execution Error: {str(e)}")
            raise ValueError(f"智能体执行失败: {str(e)}")

    async def stream_chat(
            self,
            db: AsyncSession,
            user_id: int,
            session_id: int,
            chat_request: ChatRequest
    ) -> AsyncGenerator[str, None]:
        """stream_chat ?????"""
        session = await chat_crud.get_session(db, session_id)
        user_msg = await chat_crud.create_message(db, session_id=session_id, role="user", content=chat_request.message)
        if session:
            await self._auto_rename_session(db, session, chat_request.message)
        chat_history = await self._build_langchain_history(db, session_id, limit=10)
        disclaimer_codes, risk_tags = await self._get_risk_info(
            db=db,
            user_id=user_id,
            text=chat_request.message,
            model=None,
        )
        is_time = is_time_query(chat_request.message)
        is_weather = is_weather_query(chat_request.message)
        if is_time or is_weather:
            async for payload in self._stream_tool_chat(
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
                error_payload = {"event": "error", "message": "搜索不可用：未配置 SERPER_API_KEY"}
                yield f"data: {json.dumps(error_payload)}\n\n"
                return
            async for payload in self._stream_deep_search(
                db=db,
                user_id=user_id,
                session_id=session_id,
                input_text=chat_request.message,
                chat_history=chat_history,
                user_message_id=user_msg.id,
                deep_think=chat_request.deep_think,
                disclaimer_codes=disclaimer_codes,
                risk_tags=risk_tags,
            ):
                yield payload
            return
        if chat_request.deep_think:
            async for payload in self._stream_deep_think(
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

        async for payload in self._stream_tool_chat(
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
        db: AsyncSession,
        user_id: int,
        message_id: int,
        new_message: str,
        deep_search: bool = False,
        deep_think: bool = False,
    ) -> AsyncGenerator[str, None]:
        """stream_resend ?????"""
        message, session = await self._get_message_and_session_for_user(db, user_id, message_id)
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
            await self._auto_rename_session(db, session, content)

        chat_history = await self._build_langchain_history(db, session.id, limit=10)
        disclaimer_codes, risk_tags = await self._get_risk_info(
            db=db,
            user_id=user_id,
            text=updated.content,
            model=None,
        )
        if updated.kb_id is not None:
            async for payload in self._stream_rag_with_context(
                db=db,
                user_id=user_id,
                session_id=session.id,
                kb_id=updated.kb_id,
                input_text=updated.content,
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
                error_payload = {"event": "error", "message": "搜索不可用：未配置 SERPER_API_KEY"}
                yield f"data: {json.dumps(error_payload)}\n\n"
                return
            async for payload in self._stream_deep_search(
                db=db,
                user_id=user_id,
                session_id=session.id,
                input_text=updated.content,
                chat_history=chat_history,
                user_message_id=updated.id,
                deep_think=deep_think,
                disclaimer_codes=disclaimer_codes,
                risk_tags=risk_tags,
            ):
                yield payload
            return
        if deep_think:
            async for payload in self._stream_deep_think(
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

        async for payload in self._stream_tool_chat(
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
        db: AsyncSession,
        user_id: int,
        message_id: int,
        deep_search: bool = False,
        deep_think: bool = False,
    ) -> AsyncGenerator[str, None]:
        """stream_regenerate ?????"""
        message, session = await self._get_message_and_session_for_user(db, user_id, message_id)

        messages = await chat_crud.get_session_messages(db, session.id)
        target_index = next((idx for idx, msg in enumerate(messages) if msg.id == message.id), None)
        if target_index is None:
            raise ValueError("消息不存在")

        user_message = None
        if message.role == ChatRole.USER:
            user_message = message
        else:
            for idx in range(target_index - 1, -1, -1):
                if messages[idx].role == ChatRole.USER:
                    user_message = messages[idx]
                    break

        if not user_message:
            raise ValueError("未找到对应的用户消息")

        await chat_crud.delete_messages_after(db, session.id, user_message.id)
        await chat_crud.update_session_time(db, session.id)

        chat_history = await self._build_langchain_history(db, session.id, limit=10)
        disclaimer_codes, risk_tags = await self._get_risk_info(
            db=db,
            user_id=user_id,
            text=user_message.content,
            model=None,
        )
        if user_message.kb_id is not None:
            async for payload in self._stream_rag_with_context(
                db=db,
                user_id=user_id,
                session_id=session.id,
                kb_id=user_message.kb_id,
                input_text=user_message.content,
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
                error_payload = {"event": "error", "message": "搜索不可用：未配置 SERPER_API_KEY"}
                yield f"data: {json.dumps(error_payload)}\n\n"
                return
            async for payload in self._stream_deep_search(
                db=db,
                user_id=user_id,
                session_id=session.id,
                input_text=user_message.content,
                chat_history=chat_history,
                user_message_id=user_message.id,
                deep_think=deep_think,
                disclaimer_codes=disclaimer_codes,
                risk_tags=risk_tags,
            ):
                yield payload
            return

        if deep_think:
            async for payload in self._stream_deep_think(
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

        async for payload in self._stream_tool_chat(
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
