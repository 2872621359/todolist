# 四象限待办 - Vercel 部署指南

## 已添加的 Vercel 配置文件

### ✅ 文件清单

1. **vercel.json** - Vercel 构建和路由配置
2. **requirements.txt** - Python 依赖（Werkzeug）
3. **api/handler.py** - WSGI 应用处理器，兼容 Vercel 无服务器环境
4. **index.html** - 静态前端页面
5. **.gitignore** - Git 忽略规则

## 部署步骤

### 1. 初始化 Git 仓库（如果还未初始化）

```bash
cd "Desktop/vibe coding/todo"
git init
git add .
git commit -m "Initial commit: Add Vercel configs"
```

### 2. 推送到 GitHub

```bash
git remote add origin https://github.com/YOUR_USERNAME/todo-quadrant.git
git branch -M main
git push -u origin main
```

### 3. 在 Vercel 控制台部署

1. 访问 [https://vercel.com](https://vercel.com)
2. 登录你的 Vercel 账户
3. 点击 "Add New..." → "Project"
4. 选择 "Import Git Repository"
5. 搜索并选择你的仓库
6. 点击 "Deploy"

### ⚙️ 关键配置说明

#### vercel.json

- **runtime**: Python 3.11
- **API 路由**: `/api/sync` 由 `api/handler.py` 处理
- **静态文件**: 自动服务 CSS、JS、HTML 等
- **SPA 支持**: 非 API 请求重定向到 `index.html`

#### api/handler.py

WSGI 应用程序，处理：
- `POST /api/sync` - 同步端点
- `OPTIONS` - CORS 预检请求
- 自动读写 `todo_data.json` 持久化数据

#### 环境变量

已配置 `PYTHONUNBUFFERED=1` 以确保日志实时输出。

## 关键信息

⚠️ **数据持久化**: 
- Vercel 的无服务器函数是无状态的，每次部署数据会重置
- 建议将 `todo_data.json` 上传到 Git（或在 `.gitignore` 中移除该文件）
- 或将数据迁移到 Vercel KV、MongoDB 等持久化服务

## 调试

部署后检查日志：

```bash
vercel logs
```

查看实时构建日志和运行时错误。

## 使用 Vercel CLI 本地测试（可选）

```bash
npm install -g vercel
vercel dev
```

然后访问 `http://localhost:3000`

---

部署完成！您的待办应用现在运行在 Vercel 上。📱✨
