# light-rain

一个包含后端（FastAPI + RAG + 工具调用）与前端（Vue 3 + Vite）的知识库/对话系统项目。

## 项目概述

Light Rain 是一个完整的智能对话与知识库系统，包含 FastAPI 后端与 Vue3 前端。支持文档入库、RAG 检索、工具调用与深度搜索，提供多会话历史、消息级操作、临时资料、免责声明与可视化调试等能力，开箱即可落地企业知识助手。

**核心亮点**
- 多会话聊天：搜索、置顶、归档、标签、导出 Markdown/JSON  
- 消息操作：编辑重发、重新生成、引用、复制、收藏、表情包  
- 深度模式：深度思考 + 联网搜索（含引用来源）  
- 临时资料：拖拽上传文件/图片，支持 OCR  
- 知识库：文档上传、分块、向量检索、引用来源  
- 安全合规：医疗/法律/金融场景免责声明  
- 我的界面：自定义助手/用户头像  
- 可观测：用量看板 + AI 资讯聚合  

登录界面
<img width="1533" height="732" alt="image" src="https://github.com/user-attachments/assets/208f792f-7285-40a8-bb47-a0bf6a4eaf62" />
聊天主界面
<img width="1571" height="872" alt="image" src="https://github.com/user-attachments/assets/24c4c582-caac-4800-ad8b-2b902fc06c15" />
点击知识库问答后，会让用户选择使用哪个知识库。
<img width="1533" height="856" alt="image" src="https://github.com/user-attachments/assets/91fe5de5-5bd3-4cdf-a978-d9f91fbdb654" />
知识库问答时助手回复，会带引用来源。
<img width="1509" height="842" alt="image" src="https://github.com/user-attachments/assets/2c1df7b5-16e6-4bd8-b267-fd6be61d845b" />
知识库界面，可以上传文件。
<img width="1503" height="854" alt="image" src="https://github.com/user-attachments/assets/38b87b42-9eb1-463b-848a-f6b20e49847d" />



## 项目结构

- `backend/` 后端服务（FastAPI）
- `frontend/` 前端控制台（Vue 3）

## 功能一览

- **会话与历史**：搜索、置顶、归档、标签、导出 Markdown/JSON
- **消息操作**：编辑重发、重新生成、复制、引用、收藏、表情包生成
- **深度模式**：深度思考（推理）与联网搜索（带引用）
- **临时资料**：拖拽上传文件/图片（支持 OCR）
- **安全提示**：医疗/法律/金融场景免责声明
- **我的界面**：自定义助手/用户头像
- **知识库**：文档上传、向量检索、来源引用
- **用量与资讯**：使用量看板、AI 资讯页

## 快速开始

### 1) 后端

进入后端目录并安装依赖：

```bash
cd backend
uv pip install -e .
```

准备环境变量：

```bash
cp secret/.env.example secret/.env.development
```

> 请在 `secret/.env.development` 中填写数据库、邮箱、模型和工具等配置。

数据库迁移：

```bash
alembic upgrade head
```

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

> 前端默认请求 `/api/v1`。生产环境请配置反向代理将 `/api/v1` 指向后端服务。

## 部署建议

- 后端建议使用 `gunicorn + uvicorn workers` 或 `uvicorn` 直接运行。
- 前端使用 `npm run build` 生成静态资源，使用 Nginx/静态服务托管。
- 生产环境务必使用 `secret/.env.production`，并确保密钥不提交到仓库。

## 常见问题

- **接口 404**：确认反向代理已将 `/api/v1` 转发到后端服务。
- **天气/搜索工具不可用**：检查 `WEATHER_API_KEY`、`SERPER_API_KEY` 是否配置。
- **模型调用失败**：检查 `QWEN_API_KEY` 与 `QWEN_BASE_URL`。
- **OCR 不可用**：确认已安装 Tesseract，并包含 `chi_sim`/`eng` 语言包。

