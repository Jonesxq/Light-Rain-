<div align="center">
  <h1>Official Proj 2.0 Backend</h1>
  <p>基于 FastAPI 的 RAG + 多工具智能体后端服务</p>
</div>

---

## ✨ 项目简介
这是一个面向对话与知识库问答的后端服务，核心能力包括：文档入库（解析+分块+向量化）、混合检索（BM25 + 语义召回 + 重排）、RAG 生成回答、工具调用（天气/时间/联网搜索）以及 RAGas 自动评估。

---

## ✅ 功能特性
- **用户系统**：注册 / 登录 / 邮箱验证 / JWT 鉴权  
- **会话与聊天**：多会话历史、自动重命名会话  
- **知识库管理**：创建、删除、上传文档、删除文档  
- **文档解析与分块**：支持 `pdf/docx/md/txt/ppt/pptx`  
- **结构化元数据**：页码/段落/标题路径/分块信息等  
- **混合检索**：BM25 + 语义向量召回（Milvus）+ RRF 融合 + gte-rerank-v2  
- **查询改写**：qwen-max 自动改写/扩展专业术语  
- **评估**：RAGas 自动生成评测集并评分  
- **缓存**：Redis 缓存分块内容、降低 MySQL 压力  
- **工具调用**：天气 / 时间 / 日历 / 联网搜索  

---

## 🧱 技术栈
- **FastAPI** + **SQLModel**
- **MySQL**（结构化数据）
- **Milvus**（向量检索）
- **Redis**（缓存）
- **DashScope/Qwen**（LLM + Embedding + Rerank）
- **RAGas**（自动评估）
- **LangChain**（Agent / Tool 调用）
- **Alembic**（数据库迁移）

---

## 📁 项目结构
```
backend/
├── app/
│   ├── core/           # 配置 / 日志 / 数据库 / Redis
│   ├── crud/           # 数据库操作
│   ├── models/         # SQLModel 模型
│   ├── routers/        # API 路由
│   ├── schemas/        # Pydantic 模型
│   ├── services/       # 业务逻辑（RAG / 分块 / 评估 / 聊天）
│   ├── tools/          # 工具（天气/时间/搜索）
│   ├── tasks/          # 后台任务
│   └── constant/       # 常量与提示词（prompts）
├── alembic/            # 迁移脚本
├── scripts/            # 脚本（如重建索引）
├── secret/             # 环境变量示例
└── README.md
```

---

## ⚙️ 环境准备
**依赖**
- Python 3.10+
- MySQL
- Redis
- Milvus
- DashScope/Qwen API Key
- Tesseract OCR（图片临时资料解析所需）

**OCR（图片临时资料）**
- 安装 Tesseract OCR，并确保 `tesseract` 在 PATH 中可用
- 需要语言包：`chi_sim` + `eng`

**安装**
```bash
cd backend
uv pip install -e .
```

> 没有 uv 的话，也可以使用 `pip install -e .`

---

## 🔐 环境变量
示例文件：
```
backend/secret/.env.example
```
建议复制为 `.env.development`：
```bash
cp secret/.env.example secret/.env.development
```

主要配置项（示例）：
```
QWEN_API_KEY=your_key
QWEN_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
MILVUS_URI=http://localhost:19530
DB_HOST=...
DB_USER=...
DB_PASSWORD=...
REDIS_HOST=...
```

---

## 🧪 数据库迁移
```bash
alembic upgrade head
```

若命令不可用：
```bash
.\.venv\Scripts\alembic.exe upgrade head
```

---

## ▶️ 启动服务
```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

健康检查：
```
GET /health
```

---

## 🔌 主要 API
| 模块 | 接口 | 说明 |
|------|------|------|
| Auth | `/api/v1/auth/*` | 登录注册相关 |
| Chat | `/api/v1/chat/*` | 会话与聊天 |
| KB   | `/api/v1/knowledge/*` | 知识库与文档管理 |
| Eval | `/api/v1/knowledge/{kb_id}/evaluate` | RAGas 自动评估 |

---

## 📦 文档入库流程
1. 上传文档  
2. 后台解析并分块  
3. 向量化写入 Milvus  
4. 结构化元数据写入 MySQL  

---

## 🧭 RAG 检索流程
1. 查询改写（可选）  
2. BM25 召回  
3. 语义检索补充  
4. RRF 融合  
5. gte-rerank-v2 重排  

---

## 🧪 RAGas 自动评估
示例请求体：
```json
{
  "sample_size": 3,
  "top_k": 2,
  "generate_model": "qwen-max",
  "answer_model": "qwen-max",
  "judge_model": "qwen-max",
  "max_chunk_chars": 300
}
```

返回包含：
- `ragas_scores`：整体评分
- `results`：逐条样本详情

> 注意：评估会调用 LLM，可能消耗较多 Token。

---

## 📌 重要提示
- `get_weather` 使用 WeatherAPI（需要 API Key）
- 评估/检索默认会调用 DashScope
- 如果出现连接问题，请检查网络/代理/Key 是否正确

---

## 📝 License
本项目默认使用 MIT License（如需替换请自行调整）。
