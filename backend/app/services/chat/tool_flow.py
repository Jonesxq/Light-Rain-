"""工具聊天执行组件。"""

from __future__ import annotations

import asyncio
import json
from typing import AsyncGenerator, List, Optional

from langchain_classic.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.messages import HumanMessage, SystemMessage, BaseMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from app.constant.prompts import CHAT_SYSTEM_PROMPT
from app.core.config.settings import settings
from app.crud.chat import chat_crud
from app.services.shared.llm_runtime import llm_runtime_service
from app.services.shared.usage import UsageTimer
from app.tools.get_system_time import get_system_time
from app.tools.get_weather import get_weather
from app.tools.online_search import online_search
from app.tools.text_to_image import text_to_image
from app.utils.chat_history import history_to_payload
from app.utils.chat_intent import is_time_query


class _StreamingTokenCallback(AsyncCallbackHandler):
    def __init__(self, queue: asyncio.Queue):
        self.queue = queue

    async def on_llm_new_token(self, token: str, **kwargs):
        if token:
            await self.queue.put(token)


class ChatToolFlow:
    """执行普通工具聊天，支持同步与流式输出。"""

    def __init__(self, service):
        self.service = service

    async def _build_tool_runtime(
        self,
        db,
        user_id: int,
        input_text: str,
        chat_history: List[BaseMessage],
        model: Optional[str],
        streaming: bool,
    ):
        temp_context = await self.service._get_temp_context(db, user_id, input_text)
        system_prompt = CHAT_SYSTEM_PROMPT
        if temp_context:
            system_prompt = f"{CHAT_SYSTEM_PROMPT}\n\n【临时资料】\n{temp_context}"

        resolved = await self.service._resolve_user_llm_config(db, user_id, model)
        llm = self.service._get_llm(
            resolved["model"],
            streaming=streaming,
            api_key=resolved["api_key"],
            api_base_url=resolved["api_base_url"],
        )
        tools = [online_search, get_weather, get_system_time, text_to_image]
        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", system_prompt),
                MessagesPlaceholder(variable_name="chat_history"),
                ("human", "{input}"),
                MessagesPlaceholder(variable_name="agent_scratchpad"),
            ]
        )
        agent = create_tool_calling_agent(llm, tools, prompt)
        agent_executor = AgentExecutor(
            agent=agent,
            tools=tools,
            verbose=True,
            handle_parsing_errors=True,
        )
        usage_messages = [SystemMessage(content=system_prompt), *chat_history, HumanMessage(content=input_text)]
        return {
            "resolved": resolved,
            "llm": llm,
            "tools": tools,
            "system_prompt": system_prompt,
            "temp_context": temp_context,
            "agent_executor": agent_executor,
            "usage_messages": usage_messages,
        }

    async def run_tool_chat(
        self,
        db,
        user_id: int,
        session_id: int,
        input_text: str,
        chat_history: List[BaseMessage],
        model: Optional[str] = None,
        disclaimer_codes: Optional[list[str]] = None,
        risk_tags: Optional[list[str]] = None,
    ):
        if is_time_query(input_text):
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
                disclaimer_codes=disclaimer_codes or [],
                risk_tags=risk_tags or [],
            )
            await self.service._save_prompt_snapshot(
                db=db,
                message_id=ai_msg.id,
                user_id=user_id,
                session_id=session_id,
                mode="tool_time",
                payload={"user_input": input_text, "tool": "get_system_time"},
            )
            return ai_msg

        runtime = await self._build_tool_runtime(
            db=db,
            user_id=user_id,
            input_text=input_text,
            chat_history=chat_history,
            model=model,
            streaming=False,
        )
        timer = UsageTimer()
        try:
            result = await runtime["agent_executor"].ainvoke({"input": input_text, "chat_history": chat_history})
        except Exception as exc:
            latency_ms = timer.stop_ms()
            await llm_runtime_service.record_failure(
                db=db,
                user_id=user_id,
                event_type="chat",
                model_name=runtime["llm"].model_name,
                error=exc,
                latency_ms=latency_ms,
                metadata={"session_id": session_id},
            )
            raise

        latency_ms = timer.stop_ms()
        ai_content = result.get("output", "")
        if hasattr(ai_content, "content"):
            ai_content = ai_content.content

        usage = llm_runtime_service.finalize_usage(
            llm=runtime["llm"],
            messages=runtime["usage_messages"],
            output_text=str(ai_content),
            payload=result,
        )
        await llm_runtime_service.record_success(
            db=db,
            user_id=user_id,
            event_type="chat",
            model_name=runtime["llm"].model_name,
            usage=usage,
            latency_ms=latency_ms,
            metadata={"session_id": session_id},
        )

        ai_msg = await chat_crud.create_message(
            db,
            session_id=session_id,
            role="assistant",
            content=ai_content,
            model_name=runtime["llm"].model_name,
            token_count=usage.get("total_tokens") or 0,
            disclaimer_codes=disclaimer_codes or [],
            risk_tags=risk_tags or [],
        )
        await self.service._save_prompt_snapshot(
            db=db,
            message_id=ai_msg.id,
            user_id=user_id,
            session_id=session_id,
            mode="tool_chat",
            payload={
                "system_prompt": runtime["system_prompt"],
                "user_input": input_text,
                "chat_history": history_to_payload(chat_history),
                "tools": ["online_search", "get_weather", "get_system_time", "text_to_image"],
                "temp_context": runtime["temp_context"],
                "model_name": runtime["llm"].model_name,
            },
        )
        return ai_msg

    async def _stream_tool_chat(
        self,
        db,
        user_id: int,
        session_id: int,
        input_text: str,
        chat_history: List[BaseMessage],
        model: Optional[str] = None,
        user_message_id: Optional[int] = None,
        disclaimer_codes: Optional[list[str]] = None,
        risk_tags: Optional[list[str]] = None,
    ) -> AsyncGenerator[str, None]:
        if is_time_query(input_text):
            try:
                time_text = get_system_time.invoke({})
            except Exception:
                time_text = get_system_time.run({})
            yield f"data: {json.dumps({'content': time_text})}\n\n"

            ai_msg = await chat_crud.create_message(
                db,
                session_id=session_id,
                role="assistant",
                content=time_text,
                model_name=settings.llm.DEFAULT_MODEL,
                token_count=0,
                disclaimer_codes=disclaimer_codes or [],
                risk_tags=risk_tags or [],
            )
            await self.service._save_prompt_snapshot(
                db=db,
                message_id=ai_msg.id,
                user_id=user_id,
                session_id=session_id,
                mode="tool_time",
                payload={"user_input": input_text, "tool": "get_system_time"},
            )

            payload = {
                "event": "done",
                "message": {
                    "id": ai_msg.id,
                    "session_id": session_id,
                    "role": "assistant",
                    "content": ai_msg.content,
                    "model_name": ai_msg.model_name,
                    "token_count": ai_msg.token_count,
                    "created_at": ai_msg.created_at.isoformat(),
                    "disclaimers": ai_msg.disclaimers,
                    "risk_tags": ai_msg.risk_tags,
                },
                "user_message_id": user_message_id,
            }
            yield f"data: {json.dumps(payload)}\n\n"
            return

        runtime = await self._build_tool_runtime(
            db=db,
            user_id=user_id,
            input_text=input_text,
            chat_history=chat_history,
            model=model,
            streaming=True,
        )

        token_queue: asyncio.Queue = asyncio.Queue()
        stream_callback = _StreamingTokenCallback(token_queue)
        result_holder: dict = {"result": None, "error": None}
        full_content = ""

        async def run_agent() -> None:
            try:
                result_holder["result"] = await runtime["agent_executor"].ainvoke(
                    {"input": input_text, "chat_history": chat_history},
                    config={"callbacks": [stream_callback]},
                )
            except Exception as exc:
                result_holder["error"] = exc
            finally:
                await token_queue.put(None)

        timer = UsageTimer()
        task = asyncio.create_task(run_agent())
        while True:
            token = await token_queue.get()
            if token is None:
                break
            full_content += token
            yield f"data: {json.dumps({'content': token})}\n\n"

        await task
        latency_ms = timer.stop_ms()
        if result_holder["error"] is not None:
            await llm_runtime_service.record_failure(
                db=db,
                user_id=user_id,
                event_type="chat_stream",
                model_name=runtime["resolved"]["model"],
                error=result_holder["error"],
                latency_ms=latency_ms,
                metadata={"session_id": session_id},
            )
            raise result_holder["error"]

        if not full_content and result_holder["result"]:
            output = result_holder["result"].get("output", "")
            if hasattr(output, "content"):
                output = output.content
            token = str(output or "")
            if token:
                full_content = token
                yield f"data: {json.dumps({'content': token})}\n\n"

        usage = llm_runtime_service.finalize_usage(
            llm=runtime["llm"],
            messages=runtime["usage_messages"],
            output_text=full_content,
            payload=result_holder["result"],
        )
        await llm_runtime_service.record_success(
            db=db,
            user_id=user_id,
            event_type="chat_stream",
            model_name=runtime["resolved"]["model"],
            usage=usage,
            latency_ms=latency_ms,
            metadata={"session_id": session_id},
        )

        ai_msg = await chat_crud.create_message(
            db,
            session_id=session_id,
            role="assistant",
            content=full_content,
            model_name=runtime["resolved"]["model"],
            token_count=usage.get("total_tokens") or 0,
            disclaimer_codes=disclaimer_codes or [],
            risk_tags=risk_tags or [],
        )
        await self.service._save_prompt_snapshot(
            db=db,
            message_id=ai_msg.id,
            user_id=user_id,
            session_id=session_id,
            mode="tool_chat_stream",
            payload={
                "system_prompt": runtime["system_prompt"],
                "user_input": input_text,
                "chat_history": history_to_payload(chat_history),
                "tools": ["online_search", "get_weather", "get_system_time", "text_to_image"],
                "temp_context": runtime["temp_context"],
                "model_name": runtime["resolved"]["model"],
            },
        )

        payload = {
            "event": "done",
            "message": {
                "id": ai_msg.id,
                "session_id": session_id,
                "role": "assistant",
                "content": ai_msg.content,
                "model_name": ai_msg.model_name,
                "token_count": ai_msg.token_count,
                "created_at": ai_msg.created_at.isoformat(),
                "disclaimers": ai_msg.disclaimers,
                "risk_tags": ai_msg.risk_tags,
            },
            "user_message_id": user_message_id,
        }
        yield f"data: {json.dumps(payload)}\n\n"
