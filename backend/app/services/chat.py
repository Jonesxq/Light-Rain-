"""聊天服务：对话、知识库问答、工具调用与流式输出"""
import asyncio
import json
import re
from typing import AsyncGenerator, List, Optional

from langchain_classic.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.prompts import MessagesPlaceholder, ChatPromptTemplate
from sqlalchemy.ext.asyncio import AsyncSession

# LangChain Imports
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, BaseMessage
from langgraph.checkpoint.memory import InMemorySaver


from app.core.config.settings import settings
from app.core.logger import logger_manager
from app.crud.chat import chat_crud
from app.crud.llm_settings import llm_settings_crud
from app.models.chat import ChatRole, ChatSession, ChatMessage
from app.schemas.chat import ChatRequest, KnowledgeChatRequest
from app.services.knowledge import kb_service
from app.services.query_rewrite import query_rewrite_service
from app.tools.online_search import online_search
from app.tools.get_weather import get_weather
from app.tools.get_system_time import get_system_time
from app.tools.text_to_image import text_to_image
from app.constant.prompts import CHAT_SYSTEM_PROMPT, RAG_SYSTEM_PROMPT
from app.utils.crypto import decrypt_text

logger = logger_manager.get_logger(__name__)


class _StreamingTokenCallback(AsyncCallbackHandler):
    def __init__(self, queue: asyncio.Queue):
        self.queue = queue

    async def on_llm_new_token(self, token: str, **kwargs):  # type: ignore[override]
        if token:
            await self.queue.put(token)


class ChatService:
    """聊天业务入口，封装常规聊天与知识库问答流程"""

    def __init__(self):
        # LLM 在请求时动态创建，便于切换模型
        pass

    def _get_llm(
        self,
        model_name: Optional[str] = None,
        streaming: bool = False,
        api_key: Optional[str] = None,
        api_base_url: Optional[str] = None,
    ) -> ChatOpenAI:
        """获取配置好的 LangChain ChatModel 实例"""
        model = model_name if model_name else settings.llm.DEFAULT_MODEL

        return ChatOpenAI(
            model=model,
            openai_api_key=api_key if api_key is not None else settings.llm.QWEN_API_KEY,
            openai_api_base=api_base_url if api_base_url is not None else settings.llm.QWEN_BASE_URL,
            temperature=0.3,
            streaming=streaming,
        )

    async def _resolve_user_llm_config(
        self,
        db: AsyncSession,
        user_id: int,
        request_model: Optional[str],
    ) -> dict:
        """Resolve LLM config using user settings with fallback to system config."""
        model_override = (request_model or "").strip() or None

        settings_row = await llm_settings_crud.get_by_user_id(db, user_id)
        if not settings_row or not settings_row.enabled:
            return {
                "model": model_override or settings.llm.DEFAULT_MODEL,
                "api_key": settings.llm.QWEN_API_KEY,
                "api_base_url": settings.llm.QWEN_BASE_URL,
            }

        if not settings_row.api_key_encrypted:
            logger.warning("User LLM settings enabled but API key missing, fallback to system config.")
            return {
                "model": model_override or settings.llm.DEFAULT_MODEL,
                "api_key": settings.llm.QWEN_API_KEY,
                "api_base_url": settings.llm.QWEN_BASE_URL,
            }

        try:
            api_key = decrypt_text(settings_row.api_key_encrypted)
        except Exception as exc:
            logger.error(f"User LLM key decrypt failed: {exc}")
            raise ValueError("用户模型配置解密失败")

        model_name = model_override or settings_row.model or settings.llm.DEFAULT_MODEL
        api_base_url = settings_row.api_base_url or settings.llm.QWEN_BASE_URL
        return {
            "model": model_name,
            "api_key": api_key,
            "api_base_url": api_base_url,
        }

    def _is_time_query(self, text: str) -> bool:
        """判断是否为“当前时间/日期”类问题（避免误判天气）"""
        if not text:
            return False
        normalized = text.strip()
        # 避免“今天天气”这类问题被误判为时间查询
        weather_keywords = [
            "天气", "气温", "温度", "下雨", "雨", "晴", "阴", "风",
            "空气质量", "AQI", "湿度", "降雨"
        ]
        if any(k in normalized for k in weather_keywords):
            return False

        time_keywords = [
            "时间", "日期", "几点", "几时", "几号", "星期", "周几",
            "现在", "当前", "现在时间", "当前时间", "今天日期", "今日日期"
        ]
        if any(k in normalized for k in time_keywords):
            return True

        # 只出现“今天”时不触发，需搭配“几号/日期/星期”等关键词
        if "今天" in normalized and any(k in normalized for k in ["几号", "几月", "几日", "日期", "星期", "周几"]):
            return True

        return False

    def _is_weather_query(self, text: str) -> bool:
        """判断是否为天气问题"""
        if not text:
            return False
        normalized = text.strip()
        weather_keywords = [
            "天气", "气温", "温度", "下雨", "雨", "晴", "阴", "风",
            "空气质量", "AQI", "湿度", "降雨"
        ]
        return any(k in normalized for k in weather_keywords)

    def _extract_location(self, text: str) -> str | None:
        """尽量从问题中提取城市/地区名称"""
        if not text:
            return None
        normalized = text.strip()
        # 常见格式：'永州天气怎么样' / '北京天气' / '上海今天的天气'
        match = re.search(r"([\u4e00-\u9fffA-Za-z]+?)天气", normalized)
        if match:
            loc = match.group(1).strip()
            # 去掉可能的时间修饰
            for suffix in ["今天", "今日", "现在", "当前", "明天", "后天"]:
                if loc.endswith(suffix):
                    loc = loc[: -len(suffix)]
            for prefix in ["今天", "今日", "现在", "当前", "明天", "后天"]:
                if loc.startswith(prefix):
                    loc = loc[len(prefix):]
            return loc or None
        return None

    async def process_chat(
            self,
            db: AsyncSession,
            user_id: int,
            session_id: int,
            chat_request: ChatRequest
    ):
        # 1) 基础验证与用户消息持久化
        session = await chat_crud.get_session(db, session_id)
        await chat_crud.create_message(db, session_id=session_id, role="user", content=chat_request.message)
        if session:
            await self._auto_rename_session(db, session, chat_request.message)

        # 2) 构建历史对话（LangChain Message 结构）
        chat_history = await self._build_langchain_history(db, session_id, limit=10)

        try:
            # 3) 当前时间/日期问题，直接用本地时间工具返回
            if self._is_time_query(chat_request.message):
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
                    token_count=0
                )
                return ai_msg

            # 4) 其他问题走 LLM + 工具路由（天气问题也交给 agent 强制调用工具）
            resolved = await self._resolve_user_llm_config(db, user_id, chat_request.model)
            llm = self._get_llm(
                resolved["model"],
                api_key=resolved["api_key"],
                api_base_url=resolved["api_base_url"],
            )
            tools = [online_search, get_weather, get_system_time, text_to_image]

            # 6) 按 agent 规范构建 Prompt
            prompt = ChatPromptTemplate.from_messages([
                ("system", CHAT_SYSTEM_PROMPT),
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
            result = await agent_executor.ainvoke({
                "input": chat_request.message,
                "chat_history": chat_history
            })

            # 10) 提取输出内容（兼容 AIMessage）
            ai_content = result.get("output", "")

            # 如果输出是 AIMessage 对象（某些极端配置下），提取文本
            if hasattr(ai_content, "content"):
                ai_content = ai_content.content

            # 11) 统计 Token
            total_tokens = result.get("usage_metadata", {}).get("total_tokens", 0)

            # 12) 持久化 AI 回复
            ai_msg = await chat_crud.create_message(
                db,
                session_id=session_id,
                role="assistant",
                content=ai_content,
                model_name=llm.model_name,
                token_count=total_tokens
            )

            return ai_msg

        except Exception as e:
            logger.exception(f"Agent Execution Error: {str(e)}")
            raise ValueError(f"智能体执行失败: {str(e)}")


    async def _build_langchain_history(self, db: AsyncSession, session_id: int, limit: int = 10) -> List[BaseMessage]:
        """将数据库消息转换为 LangChain Message 列表"""
        # 1) 获取历史消息
        db_messages = await chat_crud.get_session_messages(db, session_id)

        # 2) 排除最后一条（当前用户输入已在流程中单独处理）
        if db_messages and db_messages[-1].role == ChatRole.USER:
             db_messages = db_messages[:-1]

        # 3) 截取最近 N 条
        recent_db_msgs = db_messages[-limit:]

        langchain_msgs = []

        # 4) 映射为 LangChain Message 对象
        for msg in recent_db_msgs:
            if msg.role == ChatRole.USER:
                langchain_msgs.append(HumanMessage(content=msg.content))
            elif msg.role == ChatRole.ASSISTANT:
                langchain_msgs.append(AIMessage(content=msg.content))
            elif msg.role == ChatRole.SYSTEM:
                langchain_msgs.append(SystemMessage(content=msg.content))

        return langchain_msgs

    async def _auto_rename_session(self, db: AsyncSession, session: ChatSession, user_msg: str):
        """自动重命名会话（用首条提问作为标题）"""
        if session.title in {"New Chat", "新对话"}:
            new_title = user_msg[:15]
            session.title = new_title
            db.add(session)
            await db.commit()

    # ====== RAG 知识库问答 ======
    async def handle_rag_chat(
            self,
            db: AsyncSession,
            user_id: int,
            req: KnowledgeChatRequest
    ):
        # 1) 获取或创建会话
        session_id = req.session_id
        if not session_id:
            # 创建一个新会话，标题取用户提问的前 15 个字
            session = await chat_crud.create_session(
                db,
                user_id=user_id,
                title=req.message[:15]
            )
            session_id = session.id

        # 2) 保存用户问题
        session = await chat_crud.get_session(db, session_id)
        await chat_crud.create_message(
            db,
            session_id=session_id,
            role="user",
            content=req.message,
            kb_id=req.kb_id
        )
        if session:
            await self._auto_rename_session(db, session, req.message)

        # 3) 检索知识库内容
        # 3) 查询改写：提升检索与问答效果
        rewritten_query = await query_rewrite_service.rewrite_query(req.message)

        # 4) 检索知识库内容（使用改写后的查询）
        context, sources = await kb_service.search_knowledge(
            kb_id=req.kb_id,
            query=req.message,
            top_k=3,
            rewritten_query=rewritten_query
        )

        # 5) 构建 Prompt 并调用 LLM
        rewrite_hint = ""
        if rewritten_query and rewritten_query.strip() and rewritten_query != req.message:
            rewrite_hint = f"\n【问题改写】：{rewritten_query}"

        system_prompt = (
            f"{RAG_SYSTEM_PROMPT}"
            f"{rewrite_hint}\n"
            f"【已知信息】：\n{context if context else '未找到相关参考资料。'}"
        )

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=req.message)
        ]

        # 6) 调用大模型
        resolved = await self._resolve_user_llm_config(db, user_id, req.model)
        llm = self._get_llm(
            resolved["model"],
            api_key=resolved["api_key"],
            api_base_url=resolved["api_base_url"],
        )
        response = await llm.ainvoke(messages)
        ai_content = response.content

        # 7) 提取 Token 消耗信息
        # 对于 DashScope/OpenAI 兼容接口，通常在 response_metadata 中
        token_usage = response.response_metadata.get("token_usage", {})
        # 如果 token_usage 结构不存在，尝试从 usage_metadata 获取 (LangChain 新版常用)
        if not token_usage and hasattr(response, "usage_metadata"):
            token_usage = response.usage_metadata

        total_tokens = token_usage.get("total_tokens", 0)
        # -------------------------------

        # 8) 保存 AI 回复
        ai_msg_db = await chat_crud.create_message(
            db,
            session_id=session_id,
            role="assistant",
            content=ai_content,
            kb_id=req.kb_id,
            model_name=resolved["model"],  # 保存使用的模型名称
            token_count=total_tokens,  # 保存实际消耗的 Token
            sources=sources
        )

        # 9) 返回接口响应
        return {
            "id": ai_msg_db.id,
            "session_id": session_id,
            "role": "assistant",
            "content": ai_content,
            "model_name": resolved["model"],
            "token_count": total_tokens,
            "created_at": ai_msg_db.created_at,
            "sources": sources
        }

    async def stream_chat(
            self,
            db: AsyncSession,
            user_id: int,
            session_id: int,
            chat_request: ChatRequest
    ) -> AsyncGenerator[str, None]:
        """SSE 流式聊天（工具调用 + 真流式输出）"""
        session = await chat_crud.get_session(db, session_id)
        await chat_crud.create_message(db, session_id=session_id, role="user", content=chat_request.message)
        if session:
            await self._auto_rename_session(db, session, chat_request.message)
        chat_history = await self._build_langchain_history(db, session_id, limit=10)

        # 直接处理“当前时间/日期”类问题，避免模型输出 tool_call 文本
        if self._is_time_query(chat_request.message):
            try:
                time_text = get_system_time.invoke({})
            except Exception:
                # 兼容旧版 tool 接口
                time_text = get_system_time.run({})
            yield f"data: {json.dumps({'content': time_text})}\n\n"

            ai_msg = await chat_crud.create_message(
                db,
                session_id=session_id,
                role="assistant",
                content=time_text,
                model_name=settings.llm.DEFAULT_MODEL,
                token_count=0
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
                    "created_at": ai_msg.created_at.isoformat()
                }
            }
            yield f"data: {json.dumps(payload)}\n\n"
            return

        # 进入工具调用的流式输出（天气问题也走 agent）
        resolved = await self._resolve_user_llm_config(db, user_id, chat_request.model)
        llm = self._get_llm(
            resolved["model"],
            streaming=True,
            api_key=resolved["api_key"],
            api_base_url=resolved["api_base_url"],
        )
        tools = [online_search, get_weather, get_system_time, text_to_image]

        prompt = ChatPromptTemplate.from_messages([
            ("system", CHAT_SYSTEM_PROMPT),
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
            try:
                result_holder["result"] = await agent_executor.ainvoke(
                    {"input": chat_request.message, "chat_history": chat_history},
                    config={"callbacks": [stream_callback]},
                )
            except Exception as exc:
                result_holder["error"] = exc
            finally:
                await token_queue.put(None)

        task = asyncio.create_task(_run_agent())

        while True:
            token = await token_queue.get()
            if token is None:
                break
            full_content += token
            yield f"data: {json.dumps({'content': token})}\n\n"

        await task
        if result_holder["error"] is not None:
            raise result_holder["error"]

        if not full_content and result_holder["result"]:
            output = result_holder["result"].get("output", "")
            if hasattr(output, "content"):
                output = output.content
            token = str(output or "")
            if token:
                full_content = token
                yield f"data: {json.dumps({'content': token})}\n\n"

        ai_msg = await chat_crud.create_message(
            db,
            session_id=session_id,
            role="assistant",
            content=full_content,
            model_name=resolved["model"],
            token_count=0
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
                "created_at": ai_msg.created_at.isoformat()
            }
        }
        yield f"data: {json.dumps(payload)}\n\n"

    async def stream_rag_chat(
            self,
            db: AsyncSession,
            user_id: int,
            req: KnowledgeChatRequest
    ) -> AsyncGenerator[str, None]:
        """SSE 流式知识库问答（当前前端默认未使用）"""
        session_id = req.session_id
        if not session_id:
            session = await chat_crud.create_session(
                db,
                user_id=user_id,
                title=req.message[:15]
            )
            session_id = session.id

        session = await chat_crud.get_session(db, session_id)
        await chat_crud.create_message(
            db,
            session_id=session_id,
            role="user",
            content=req.message,
            kb_id=req.kb_id
        )
        if session:
            await self._auto_rename_session(db, session, req.message)

        # 查询改写：提升检索与问答效果
        rewritten_query = await query_rewrite_service.rewrite_query(req.message)

        context, sources = await kb_service.search_knowledge(
            kb_id=req.kb_id,
            query=req.message,
            top_k=4,
            rewritten_query=rewritten_query
        )

        rewrite_hint = ""
        if rewritten_query and rewritten_query.strip() and rewritten_query != req.message:
            rewrite_hint = f"\n【问题改写】：{rewritten_query}"

        system_prompt = (
            f"{RAG_SYSTEM_PROMPT}"
            f"{rewrite_hint}\n"
            f"【已知信息】：\n{context if context else '未找到相关参考资料。'}"
        )

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=req.message)
        ]

        resolved = await self._resolve_user_llm_config(db, user_id, req.model)
        llm = self._get_llm(
            resolved["model"],
            streaming=True,
            api_key=resolved["api_key"],
            api_base_url=resolved["api_base_url"],
        )
        full_content = ""

        async for chunk in llm.astream(messages):
            token = getattr(chunk, "content", "")
            if not token:
                continue
            full_content += token
            yield f"data: {json.dumps({'content': token})}\n\n"

        ai_msg_db = await chat_crud.create_message(
            db,
            session_id=session_id,
            role="assistant",
            content=full_content,
            kb_id=req.kb_id,
            model_name=resolved["model"],
            token_count=0,
            sources=sources
        )

        payload = {
            "event": "done",
            "message": {
                "id": ai_msg_db.id,
                "session_id": session_id,
                "role": "assistant",
                "content": ai_msg_db.content,
                    "model_name": resolved["model"],
                    "token_count": ai_msg_db.token_count,
                    "created_at": ai_msg_db.created_at.isoformat(),
                    "sources": sources
                }
            }
        yield f"data: {json.dumps(payload)}\n\n"

chat_service = ChatService()
