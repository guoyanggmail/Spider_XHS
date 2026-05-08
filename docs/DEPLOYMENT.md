# 部署文档

## 技术栈

- 后端：Python 3.10、FastAPI、Uvicorn、Pydantic、PyExecJS
- 前端：React、TypeScript、Vite、Tailwind CSS、shadcn/ui 配置体系、lucide-react
- 数据库：PostgreSQL 16
- 容器：Docker、Docker Compose，运行镜像内包含 Node.js 和根目录 npm 依赖，供 PyExecJS 执行小红书签名 JS

## 当前部署定位

当前项目部署的是：

- Web 管理后台
- App 对接后端
- PostgreSQL 数据库存储

当前项目不负责部署 Android 自动化执行端。Android App 会在独立项目中实现，并通过本项目提供的接口通信。

## 本地开发运行

后端：

```bash
uvicorn server.main:app --host 127.0.0.1 --port 8000 --reload
```

前端：

```bash
cd frontend
npm install
npm run dev
```

访问：

```text
http://127.0.0.1:5173/
```

手机局域网访问：

```bash
cd frontend
npm run dev:lan
```

然后确认手机和电脑在同一个 Wi-Fi，用手机浏览器访问：

```text
http://电脑局域网IP:5173/
```

示例：

```text
http://192.168.1.23:5173/
```

开发模式下，手机访问前端仍会通过 Vite 把 `/api` 代理到电脑本机的后端 `127.0.0.1:8000`，所以后端可以继续只监听本机地址。

## 自动化检查

```bash
sh scripts/check.sh
```

该脚本会执行后端 pytest 和前端构建检查。

## Docker 一键部署

`docker-compose.yml` 会同时启动：

| 服务 | 端口 | 说明 |
|---|---:|---|
| `postgres` | `5432` | PostgreSQL 16，使用 `postgres-data` 数据卷 |
| `xhs-web` | `8000` | FastAPI 后端和已构建的 Web 管理台 |

构建并启动：

```bash
docker compose up --build -d
```

或使用脚本：

```bash
sh scripts/docker-up.sh
```

访问：

```text
http://127.0.0.1:8000/
```

停止：

```bash
docker compose down
```

或使用脚本：

```bash
sh scripts/docker-down.sh
```

查看服务状态：

```bash
docker compose ps
```

查看后端日志：

```bash
docker compose logs -f xhs-web
```

执行数据库迁移：

```bash
docker compose exec xhs-web alembic upgrade head
```

当前后端启动时也会自动创建缺失表；生产环境变更表结构时仍建议显式执行 Alembic 迁移。

## Docker 国内源

Dockerfile 默认使用国内依赖源加速构建：

| 类型 | 默认源 |
|---|---|
| apt | 清华 Debian 镜像 |
| pip | `https://pypi.tuna.tsinghua.edu.cn/simple` |
| npm | `https://registry.npmmirror.com` |

如需改回官方源：

```bash
ENABLE_CHINA_MIRRORS=0 \
PIP_INDEX_URL=https://pypi.org/simple \
NPM_REGISTRY=https://registry.npmjs.org \
docker compose build
```

基础镜像 `python:3.10-slim` 和 `node:20-bookworm-slim` 的拉取速度由 Docker Desktop 的 registry mirror 决定，项目内无法直接替代。可在 Docker Desktop 的 Docker Engine 配置里增加镜像加速地址后重启 Docker。

## 数据持久化

Docker 部署默认使用 PostgreSQL 数据卷持久化数据库文件。

```text
postgres-data -> /var/lib/postgresql/data
```

迁移完成后：

- `datas/accounts.json` 不再作为主存储。
- `datas/operations.json` 不再作为主存储。
- `datas/` 可仅保留导入导出或临时调试用途。

如需导入旧 JSON 数据：

```bash
docker compose exec xhs-web python scripts/import_json_to_db.py
```

## 环境变量

- `XHS_WEB_HOST`：服务监听地址，Docker 默认 `0.0.0.0`。
- `XHS_WEB_PORT`：服务端口，Docker 默认 `8000`。
- `XHS_USE_PROXY`：是否保留系统代理。默认 `0`，后端会清理代理环境变量。
- `POSTGRES_HOST`：PostgreSQL 主机。
- `POSTGRES_PORT`：PostgreSQL 端口。
- `POSTGRES_DB`：数据库名。
- `POSTGRES_USER`：数据库用户。
- `POSTGRES_PASSWORD`：数据库密码。
- `DATABASE_URL`：完整数据库连接串。设置后优先级高于 `POSTGRES_*`。

## 注意

Docker 部署仍建议只在本机或可信内网使用，不建议暴露到公网。Cookie 是敏感信息，数据库中的 Cookie 字段不能向前端透出。
