# 选股通知系统 - Windows本地环境部署指南

## 1. 环境配置要求

### 1.1 操作系统

- **Windows 10** (64位) 或 **Windows 11** (64位)
- 推荐：Windows 11 22H2 或更高版本

### 1.2 必要软件及版本

| 软件                 | 版本            | 用途     | 下载链接                                                  |
| ------------------ | ------------- | ------ | ----------------------------------------------------- |
| Python             | 3.9+          | 后端运行环境 | [Python官网](https://www.python.org/downloads/windows/) |
| Node.js            | 16.14.0+      | 前端开发环境 | [Node.js官网](https://nodejs.org/en/download/)          |
| Git                | 2.30.0+       | 版本控制   | [Git官网](https://git-scm.com/downloads)                |
| Visual Studio Code | 最新版           | 代码编辑器  | [VS Code官网](https://code.visualstudio.com/download)   |
| Nginx              | 1.20.0+       | 反向代理   | [Nginx官网](http://nginx.org/en/download.html)          |
| Supervisor         | 最新版 (通过pip安装) | 进程管理   | -                                                     |

### 1.3 硬件配置建议

- **CPU**: 4核或以上
- **内存**: 8GB或以上
- **磁盘空间**: 50GB或以上
- **网络**: 稳定的互联网连接（用于API调用）

## 2. 完整部署步骤

### 2.1 环境准备

1. **安装Python**
   - 下载并运行Python安装程序
   - 勾选"Add Python to PATH"
   - 完成安装后，打开命令提示符验证：
     ```bash
     python --version
     pip --version
     ```
2. **安装Node.js**
   - 下载并运行Node.js安装程序
   - 完成安装后，打开命令提示符验证：
     ```bash
     node --version
     npm --version
     ```
3. **安装Git**
   - 下载并运行Git安装程序
   - 完成安装后，打开命令提示符验证：
     ```bash
     git --version
     ```
4. **安装Visual Studio Code**
   - 下载并运行VS Code安装程序
   - 完成安装后，安装推荐的扩展：
     - Python
     - Vetur (Vue.js支持)
     - ESLint

### 2.2 项目获取

1. **克隆项目**
   ```bash
   git clone [项目仓库地址] xuangu
   cd xuangu
   ```
2. **创建Python虚拟环境**
   ```bash
   python -m venv .venv
   ```
3. **激活虚拟环境**
   ```bash
   .venv\Scripts\activate
   ```

### 2.3 依赖项安装

1. **安装Python依赖**
   ```bash
   pip install -r requirements.txt
   ```
2. **安装前端依赖**
   ```bash
   cd frontend
   npm install
   cd ..
   ```

### 2.4 配置文件设置

1. **创建环境配置文件**
   - 复制 `.env.example` 文件为 `.env`
   - 编辑 `.env` 文件，填写以下配置：
     ```bash
     # Tushare API Token
     TUSHARE_TOKEN=your_token_here

     # 通达信MCP配置
     TDX_MCP_ENABLED=true
     TDX_MCP_URL=https://mcp.tdx.com.cn:3001/mcp
     TDX_MCP_API_KEY=your_api_key_here

     # 飞书 Webhook URL
     FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/xxx

     # 数据库路径
     DATABASE_URL=sqlite:///./data/xuangu.db

     # JWT 密钥
     SECRET_KEY=your_secret_key_here

     # 服务配置
     HOST=0.0.0.0
     PORT=9999
     LOG_LEVEL=INFO
     LOG_DIR=logs

     # CORS 配置
     ALLOWED_ORIGINS=http://localhost:8080,http://localhost:8081,http://localhost:3000
     ```
2. **创建必要目录**
   ```bash
   mkdir data
   mkdir logs
   ```

### 2.5 编译前端

```bash
cd frontend
npm run build
cd ..
```

### 2.6 配置Nginx

1. **安装Nginx**
   - 下载Nginx并解压到 `H:\project_development\tools\nginx`
2. **配置Nginx**
   - 编辑 `H:\project_development\tools\nginx\conf\nginx.conf` 文件，添加以下配置：
     ```nginx
     server {
         listen 80;
         server_name localhost;

         location / {
             root C:\path\to\xuangu\frontend\dist;
             try_files $uri $uri/ /index.html;
         }

         location /api/ {
             proxy_pass http://127.0.0.1:9999;
             proxy_set_header Upgrade $http_upgrade;
             proxy_set_header Connection "upgrade";
         }

         location /ws {
             proxy_pass http://127.0.0.1:9999;
             proxy_http_version 1.1;
             proxy_set_header Upgrade $http_upgrade;
             proxy_set_header Connection "upgrade";
             proxy_read_timeout 86400;
         }
     }
     ```

### 2.7 启动服务

1. **启动后端服务**
   ```bash
   .venv\Scripts\activate
   uvicorn backend.main:app --host 0.0.0.0 --port 9999 --reload
   ```
2. **启动Nginx**
   ```bash
   H:\project_development\tools\nginx\nginx.exe
   ```
3. **访问系统**
   - 打开浏览器，访问 `http://localhost`

## 3. 依赖项安装指南

### 3.1 Python依赖

**核心依赖**：

- FastAPI: Web框架
- SQLAlchemy: ORM
- Pydantic: 数据验证
- uvicorn: ASGI服务器
- python-jose: JWT认证
- passlib: 密码哈希
- tushare: 股票数据API

**安装命令**：

```bash
pip install -r requirements.txt
```

### 3.2 前端依赖

**核心依赖**：

- Vue 3: 前端框架
- Vue Router: 路由
- Axios: HTTP客户端
- WebSocket: 实时通信

**安装命令**：

```bash
cd frontend
npm install
```

### 3.3 数据库配置

- **默认数据库**: SQLite
- **数据存储路径**: `data/xuangu.db`
- **初始化**: 首次运行时自动创建表结构

## 4. 配置文件说明

### 4.1 环境变量配置 (.env)

| 配置项                  | 说明              | 生产环境推荐值                           |
| -------------------- | --------------- | --------------------------------- |
| TUSHARE\_TOKEN       | Tushare API访问令牌 | 从Tushare官网获取                      |
| TDX\_MCP\_ENABLED    | 是否启用通达信MCP      | true                              |
| TDX\_MCP\_URL        | 通达信MCP接口地址      | <https://mcp.tdx.com.cn:3001/mcp> |
| TDX\_MCP\_API\_KEY   | 通达信MCP API密钥    | 从通达信获取                            |
| FEISHU\_WEBHOOK\_URL | 飞书机器人Webhook地址  | 从飞书开发者平台获取                        |
| DATABASE\_URL        | 数据库连接字符串        | sqlite:///./data/xuangu.db        |
| SECRET\_KEY          | JWT签名密钥         | 随机生成的安全字符串                        |
| HOST                 | 服务监听地址          | 0.0.0.0                           |
| PORT                 | 服务监听端口          | 9999                              |
| LOG\_LEVEL           | 日志级别            | INFO                              |
| LOG\_DIR             | 日志目录            | logs                              |
| ALLOWED\_ORIGINS     | CORS允许的源        | 生产环境域名                            |

### 4.2 选股策略配置

| 配置项                       | 默认值  | 说明            |
| ------------------------- | ---- | ------------- |
| max\_circ\_mv             | 2000 | 最大流通市值 (亿)    |
| max\_close\_price         | 500  | 最大收盘价 (元)     |
| min\_limit\_count         | 3    | 最小涨停次数        |
| min\_seal\_rate           | 90   | 最小封板率 (%)     |
| period\_days              | 100  | 封板率计算周期 (交易日) |
| call\_auction\_ratio\_min | 4    | 竞昨比最小值 (%)    |
| call\_auction\_ratio\_max | 30   | 竞昨比最大值 (%)    |
| turnover\_rate\_min       | 0.5  | 竞价换手率最小值 (%)  |
| turnover\_rate\_max       | 10   | 竞价换手率最大值 (%)  |
| notification\_enabled     | true | 是否启用通知        |

## 5. 启动/停止服务

### 5.1 后端服务

**启动**：

```bash
.venv\Scripts\activate
uvicorn backend.main:app --host 0.0.0.0 --port 9999 --reload
```

**停止**：

- 按 `Ctrl+C` 终止进程

### 5.2 Nginx服务

**启动**：

```bash
H:\project_development\tools\nginx\nginx.exe
```

**停止**：

```bash
H:\project_development\tools\nginx\nginx.exe -s stop
```

**重启**：

```bash
H:\project_development\tools\nginx\nginx.exe -s reload
```

### 5.3 生产环境部署

**使用Supervisor管理进程**：

1. **安装Supervisor**
   ```bash
   pip install supervisor
   ```
2. **创建配置文件** (`supervisord.conf`)
   ```ini
   [program:xuangu-backend]
   command=C:\path\to\xuangu\.venv\Scripts\uvicorn.exe backend.main:app --host 0.0.0.0 --port 9999 --workers 4
   directory=C:\path\to\xuangu
   autostart=true
   autorestart=true
   stdout_logfile=C:\path\to\xuangu\logs\supervisor.log
   stderr_logfile=C:\path\to\xuangu\logs\supervisor_error.log
   ```
3. **启动Supervisor**
   ```bash
   supervisord -c supervisord.conf
   ```
4. **管理进程**
   ```bash
   supervisorctl -c supervisord.conf status
   supervisorctl -c supervisord.conf start xuangu-backend
   supervisorctl -c supervisord.conf stop xuangu-backend
   ```

## 6. 常见问题排查与解决方案

### 6.1 依赖安装问题

**问题**：pip安装依赖失败
**解决方案**：

- 确保网络连接正常
- 使用国内镜像源：
  ```bash
  pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
  ```

**问题**：npm安装依赖失败
**解决方案**：

- 确保网络连接正常
- 使用国内镜像源：
  ```bash
  npm install --registry=https://registry.npmmirror.com
  ```

### 6.2 服务启动问题

**问题**：端口被占用
**解决方案**：

- 检查端口9999是否被占用：
  ```bash
  netstat -ano | findstr :9999
  ```
- 结束占用端口的进程：
  ```bash
  taskkill /PID [进程ID] /F
  ```

**问题**：数据库连接失败
**解决方案**：

- 确保data目录存在且有写入权限
- 检查DATABASE\_URL配置是否正确

### 6.3 API调用问题

**问题**：Tushare API调用失败
**解决方案**：

- 检查TUSHARE\_TOKEN是否正确
- 检查网络连接
- 检查Tushare API积分是否足够

**问题**：通达信MCP返回0条记录
**解决方案**：

- 检查数值格式是否正确（使用整数格式，如4%而非4.0%）
- 检查API密钥是否正确

### 6.4 前端访问问题

**问题**：前端无法访问后端API
**解决方案**：

- 检查Nginx配置是否正确
- 检查后端服务是否运行
- 检查CORS配置是否包含前端域名

## 7. 项目目录结构说明

### 7.1 整体结构

```
xuangu/
├── backend/           # 后端代码
├── frontend/          # 前端代码
├── data/              # 数据存储目录
├── logs/              # 日志目录
├── scripts/           # 辅助脚本
├── docs/              # 文档
├── tests/             # 测试代码
├── requirements.txt   # Python依赖
├── .env.example       # 环境变量示例
└── WINDOWS_DEPLOYMENT_GUIDE.md  # 本部署指南
```

### 7.2 后端结构

```
backend/
├── api/              # API路由
├── services/         # 业务逻辑
│   ├── strategy/     # 选股策略
│   ├── tdx_selector.py    # 通达信选股服务
│   ├── stock_selector.py   # 三阶段选股协调
│   ├── data_collector.py   # Tushare数据收集
│   └── seal_rate_calculator.py  # 封板率计算
├── models/           # 数据库模型
├── schemas/          # 数据验证模式
├── middleware/       # 中间件
├── core/             # 核心配置
├── utils/            # 工具函数
├── auth/             # 认证系统
└── main.py           # 应用入口
```

### 7.3 前端结构

```
frontend/
├── src/
│   ├── components/   # 组件
│   ├── views/        # 页面
│   ├── api/          # API调用
│   ├── router/       # 路由
│   ├── App.vue       # 应用根组件
│   └── main.js       # 前端入口
├── public/           # 静态资源
├── package.json      # 前端依赖
└── vite.config.js    # Vite配置
```

### 7.4 关键文件功能

| 文件                        | 功能               | 位置                                         |
| ------------------------- | ---------------- | ------------------------------------------ |
| main.py                   | 后端应用入口，配置FastAPI | backend/main.py                            |
| stock\_selector.py        | 三阶段选股协调服务        | backend/services/stock\_selector.py        |
| tdx\_selector.py          | 通达信MCP选股服务       | backend/services/tdx\_selector.py          |
| data\_collector.py        | Tushare数据收集服务    | backend/services/data\_collector.py        |
| seal\_rate\_calculator.py | 封板率计算服务          | backend/services/seal\_rate\_calculator.py |
| websocket\_service.py     | WebSocket实时通信服务  | backend/services/websocket\_service.py     |
| App.vue                   | 前端应用根组件          | frontend/src/App.vue                       |
| Dashboard.vue             | 前端仪表盘页面          | frontend/src/views/Dashboard.vue           |
| StockResults.vue          | 选股结果页面           | frontend/src/views/StockResults.vue        |
| StrategyManage.vue        | 策略管理页面           | frontend/src/views/StrategyManage.vue      |

## 8. 性能优化建议

### 8.1 后端优化

- **使用生产模式运行**：移除 `--reload` 参数
- **增加workers数量**：根据CPU核心数调整
- **启用Gunicorn**：在生产环境使用Gunicorn作为WSGI服务器

### 8.2 数据库优化

- **使用PostgreSQL**：对于大数据量场景，建议迁移到PostgreSQL
- **定期清理缓存**：清理过期的封板率缓存数据

### 8.3 前端优化

- **启用CDN**：对于静态资源使用CDN加速
- **代码分割**：使用Vue的路由懒加载
- **缓存策略**：合理设置浏览器缓存

## 9. 安全建议

### 9.1 环境变量安全

- **不要提交敏感信息**：确保 `.env` 文件不被提交到版本控制
- **使用密钥管理服务**：对于生产环境，使用专业的密钥管理服务

### 9.2 API安全

- **实现API限流**：防止恶意请求
- **使用HTTPS**：在生产环境启用HTTPS
- **输入验证**：严格验证所有用户输入

### 9.3 服务器安全

- **防火墙配置**：限制不必要的端口访问
- **定期更新**：及时更新依赖包和系统补丁
- **监控系统**：部署Prometheus和Grafana监控

## 10. 维护与更新

### 10.1 代码更新

```bash
git pull
pip install -r requirements.txt
cd frontend && npm install && npm run build && cd ..
```

### 10.2 数据库迁移

- 对于结构变更，运行数据库迁移脚本
- 对于数据迁移，使用专门的迁移工具

### 10.3 日志管理

- 定期清理日志文件
- 配置日志轮转
- 集成日志分析工具

## 11. 联系方式

**维护人员**：AI Assistant
**最后更新**：2026-04-27
**版本**：v3.0

***

**注意**：本指南适用于Windows 10/11环境下的生产级开发部署。对于正式生产环境，建议使用Linux服务器并采用容器化部署方案。
