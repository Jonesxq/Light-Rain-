## 项目简介

本前端是基于 Vue 3 + Vite 的知识库/聊天控制台，用于与后端的 RAG 与工具调用服务交互。
主要包含聊天页面、知识库管理、评估展示等功能入口。

## 技术栈

- Vue 3
- Vite
- Vue Router

## 目录结构

- `src/` 前端源码
- `index.html` 入口 HTML
- `vite.config.js` Vite 配置

## 运行与构建

### 安装依赖

```bash
npm install
```

### 本地开发

```bash
npm run dev
```

### 构建生产版本

```bash
npm run build
```

### 本地预览

```bash
npm run preview
```

## 接口配置

前端默认通过本地存储的 `apiBase` 调用后端 API。
如果未设置，会使用默认的相对路径 `http://127.0.0.1:8000/api/v1`（见 `src/api/client.js`）。
你可以在登录/设置页面修改 API Base。

## 常见问题

- **页面无法访问接口**：检查后端是否启动、API Base 是否配置正确、跨域是否放行。
- **样式异常**：建议清除浏览器缓存并重新构建。

