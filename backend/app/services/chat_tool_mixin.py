"""工具聊天流式输出辅助模块"""

import asyncio
import json
from typing import AsyncGenerator, List, Optional

from langchain_classic.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.messages import HumanMessage, SystemMessage, BaseMessage
from langchain_core.prompts import MessagesPlaceholder, ChatPromptTemplate
from sqlalchemy.ext.asyncio import AsyncSession

from app.constant.prompts import CHAT_SYSTEM_PROMPT
from app.core.config.settings import settings
from app.crud.chat import chat_crud
from app.services.usage import usage_service, UsageTimer
from app.tools.online_search import online_search
from app.tools.get_weather import get_weather
from app.tools.get_system_time import get_system_time
from app.tools.text_to_image import text_to_image
from app.utils.chat_history import history_to_payload
from app.utils.chat_intent import is_time_query
from app.utils.llm_usage import estimate_usage

class _StreamingTokenCallback(AsyncCallbackHandler):
    """流式令牌回调：用于捕获LLM流式输出并放入队列"""
    def __init__(self, queue: asyncio.Queue):
        """初始化流式令牌回调
        
        Args:
            queue: 用于存储令牌的异步队列
        """
        self.queue = queue

    async def on_llm_new_token(self, token: str, **kwargs):  # type: ignore[override]
        """当LLM生成新令牌时的回调
        
        Args:
            token: 生成的新令牌
        """
        if token:
            await self.queue.put(token)


class ChatToolMixin:
    """工具聊天流式输出Mixin：提供工具调用的流式聊天功能"""

    async def _stream_tool_chat(
        self,
        db: AsyncSession,
        user_id: int,
        session_id: int,
        input_text: str,
        chat_history: List[BaseMessage],
        model: Optional[str] = None,
        user_message_id: Optional[int] = None,
        disclaimer_codes: Optional[list[str]] = None,
        risk_tags: Optional[list[str]] = None,
    ) -> AsyncGenerator[str, None]:
        """流式工具聊天（内部方法）
        
        Args:
            db: 数据库会话
            user_id: 用户ID
            session_id: 会话ID
            input_text: 用户输入
            chat_history: 对话历史
            model: 使用的模型名称
            user_message_id: 用户消息ID
            disclaimer_codes: 免责声明代码列表
            risk_tags: 风险标签列表
            
        Yields:
            SSE格式的数据流
        """
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
            await self._save_prompt_snapshot(
                db=db,
                message_id=ai_msg.id,
                user_id=user_id,
                session_id=session_id,
                mode="tool_time",
                payload={
                    "user_input": input_text,
                    "tool": "get_system_time",
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
            return

        temp_context = await self._get_temp_context(db, user_id, input_text)
        system_prompt = CHAT_SYSTEM_PROMPT
        if temp_context:
            system_prompt = f"{CHAT_SYSTEM_PROMPT}\n\n【临时资料】\n{temp_context}"
        resolved = await self._resolve_user_llm_config(db, user_id, model)
        llm = self._get_llm(
            resolved["model"],
            streaming=True,
            api_key=resolved["api_key"],
            api_base_url=resolved["api_base_url"],
        )
        tools = [online_search, get_weather, get_system_time, text_to_image]

        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            MessagesPlaceholder(variable_name="chat_history"),
            ("human", "{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad"),
        ])

        agent = create_tool_calling_agent(llm, tools, prompt)
        agent_executor = AgentExecutor(
            agent=agent,
            tools=tools,
            verbose=True,
            handle_parsing_errors=True,
        )

        full_content = ""
        token_queue: asyncio.Queue = asyncio.Queue()
        stream_callback = _StreamingTokenCallback(token_queue)
        result_holder: dict = {"result": None, "error": None}

        async def _run_agent() -> None:
            """异步运行智能体的内部函数"""
            try:
                result_holder["result"] = await agent_executor.ainvoke(
                    {"input": input_text, "chat_history": chat_history},
                    config={"callbacks": [stream_callback]},
                )
            except Exception as exc:
                result_holder["error"] = exc
            finally:
                await token_queue.put(None)

        timer = UsageTimer()
        task = asyncio.create_task(_run_agent())

        while True:
            token = await token_queue.get()
            if token is None:
                break
            full_content += token
            yield f"data: {json.dumps({'content': token})}\n\n"

        await task
        latency_ms = timer.stop_ms()
        if result_holder["error"] is not None:
            await usage_service.record_event(
                db,
                user_id=user_id,
                event_type="chat_stream",
                model_name=resolved["model"],
                prompt_tokens=None,
                completion_tokens=None,
                total_tokens=None,
                token_missing=True,
                latency_ms=latency_ms,
                cost_usd=0.0,
                success=False,
                error_message=str(result_holder["error"]),
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

        usage = usage_service.extract_usage(result_holder["result"])
        if usage.get("token_missing") or usage.get("total_tokens") is None:
            token_messages = [
                SystemMessage(content=system_prompt),
                *chat_history,
                HumanMessage(content=input_text),
            ]
            usage = estimate_usage(llm, token_messages, full_content)
        elif usage.get("total_tokens") is None:
            usage["total_tokens"] = (usage.get("prompt_tokens") or 0) + (usage.get("completion_tokens") or 0)

        total_tokens = usage.get("total_tokens") or 0
        cost_usd = usage_service.compute_cost(
            resolved["model"],
            usage.get("prompt_tokens"),
            usage.get("completion_tokens"),
        )
        await usage_service.record_event(
            db,
            user_id=user_id,
            event_type="chat_stream",
            model_name=resolved["model"],
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            total_tokens=usage.get("total_tokens"),
            token_missing=bool(usage.get("token_missing")),
            latency_ms=latency_ms,
            cost_usd=cost_usd,
            success=True,
            metadata={"session_id": session_id},
        )

        ai_msg = await chat_crud.create_message(
            db,
            session_id=session_id,
            role="assistant",
            content=full_content,
            model_name=resolved["model"],
            token_count=total_tokens,
            disclaimer_codes=disclaimer_codes or [],
            risk_tags=risk_tags or [],
        )
        await self._save_prompt_snapshot(
            db=db,
            message_id=ai_msg.id,
            user_id=user_id,
            session_id=session_id,
            mode="tool_chat_stream",
            payload={
                "system_prompt": system_prompt,
                "user_input": input_text,
                "chat_history": history_to_payload(chat_history),
                "tools": ["online_search", "get_weather", "get_system_time", "text_to_image"],
                "temp_context": temp_context,
                "model_name": resolved["model"],
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
