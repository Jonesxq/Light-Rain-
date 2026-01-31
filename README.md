# light-rain

一个包含后端（FastAPI + RAG + 工具调用）与前端（Vue 3 + Vite）的知识库/对话系统项目。

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

