# official_proj2.0

一个包含后端（FastAPI + RAG + 工具调用）与前端（Vue 3 + Vite）的知识库/对话系统项目。

## 项目结构

- `backend/` 后端服务（FastAPI）
- `frontend/` 前端控制台（Vue 3）

## 快速开始

### 1) 后端

进入后端目录并安装依赖：

```bash
cd backend
uv pip install -r requirements.txt
```

准备环境变量：

```bash
cp secret/.env.example secret/.env.development
```

> 请在 `secret/.env.development` 中填写数据库、邮箱、模型和工具等配置。

启动后端：

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 2) 前端

进入前端目录并安装依赖：

```bash
cd frontend
npm install
```

启动前端：

```bash
npm run dev
```

## 部署建议

- 后端建议使用 `gunicorn + uvicorn workers` 或 `uvicorn` 直接运行。
- 前端使用 `npm run build` 生成静态资源，使用 Nginx/静态服务托管。
- 生产环境务必使用 `secret/.env.production`，并确保密钥不提交到仓库。

## 常见问题

- **接口 404**：检查前端 API Base 是否配置正确。
- **天气/搜索工具不可用**：检查 `WEATHER_API_KEY`、`SERPER_API_KEY` 是否配置。
- **模型调用失败**：检查 `QWEN_API_KEY` 与 `QWEN_BASE_URL`。

