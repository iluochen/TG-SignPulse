# TG-SignPulse

> Telegram 多账号自动签到、消息动作编排与关键词监听面板。

[English README](README_EN.md) · [健康检查](#健康检查) · [更新日志](#更新日志)

TG-SignPulse 是一个 Telegram 自动化管理面板。你可以在网页里管理多个账号，配置自动签到任务，并让任务按固定规则每天自动执行。

> AI 驱动：项目已集成 AI 能力（识图、计算题），可直接用于自动任务流程。

## 这个项目是做什么的？

- 统一管理多个 Telegram 账号（手机号验证码登录或二维码扫码登录）
- 自动签到、定时发消息、点击按钮，支持固定时间和随机时间段两种调度模式
- 8 种动作类型，含 AI 识图、AI 计算题、关键词监听
- 支持指定群组话题（Thread/Topic）执行签到
- 实时 WebSocket 日志流，可直接在网页查看执行过程和机器人最后回复
- 支持任务剪贴板批量导入导出、全局代理、失败通知和关键词监听
- 适合 VPS 长期运行

## 项目亮点

- **多账号管理**：手机号 / 二维码两种方式登录，账号支持独立代理
- **8 种动作类型**：发送文本、发送骰子、点击按钮、AI 识图后点按钮、AI 识图后发文本、AI 计算后发文本、AI 计算后点按钮、关键词监听通知
- **两种调度模式**：固定 CRON 时间 或 时间窗口内随机执行
- **话题签到**：支持 Telegram Forum 群组指定 Thread/Topic 内执行
- **通知推送**：Telegram Bot 推送任务失败/账号失效/登录通知；关键词命中支持 Telegram Bot、Bark、自定义 URL 三种渠道
- **实时日志**：WebSocket 实时推送执行日志，历史记录自动保留 3 天
- **任务迁移**：全部任务导出到剪贴板，粘贴导入自动跳过重复任务
- **面板安全**：JWT 认证 + TOTP 两步验证，支持单独关闭每个任务的失败通知
- **容器化部署**：Docker / Docker Compose 开箱即用，自动适配挂载目录的 UID/GID

## 功能概览

| 模块 | 能力 |
| --- | --- |
| 账号管理 | 多账号登录（手机号/二维码）、独立代理、状态检测、重新登录、TOTP 2FA |
| 任务编排 | 固定 CRON / 时间窗口随机执行，8 种动作类型，动作间隔与自动删消息 |
| 话题支持 | 群组 `Thread ID` 级别的发送与回复过滤 |
| 关键词监听 | 包含/正则两种匹配，命中后推送通知或继续执行后续动作序列 |
| 推送通知 | 全局：Telegram Bot（任务失败/账号失效/登录）；关键词命中：Telegram Bot / Bark / 自定义 URL |
| 运维能力 | Docker 部署、持久化数据目录、健康检查、配置版本自动迁移、导入导出 |

## 小白 3 步部署（推荐）

1. 安装 Docker（服务器和本机都可）
2. 执行下面命令启动容器
3. 浏览器打开 `http://服务器IP:8080`，用默认账号登录

默认凭据：
- 账号：`admin`
- 密码：`admin123`

### 一条命令启动

```bash
docker run -d \
  --name tg-signpulse \
  --restart unless-stopped \
  -p 8080:8080 \
  -v $(pwd)/data:/data \
  -e TZ=Asia/Shanghai \
  -e APP_SECRET_KEY=your_secret_key \
  ghcr.io/akasls/tg-signpulse:latest
```

如果你走反代（如 Nginx），可改成仅本机监听：

```bash
-p 127.0.0.1:8080:8080
```

### Docker Compose（可选）

```yaml
services:
  app:
    image: ghcr.io/akasls/tg-signpulse:latest
    container_name: tg-signpulse
    restart: unless-stopped
    ports:
      - "8080:8080"
    volumes:
      - ./data:/data
    environment:
      - TZ=Asia/Shanghai
      - APP_SECRET_KEY=your_secret_key
```

## 数据目录与权限说明

- 默认数据目录：`/data`
- 当 `/data` 不可写时，会自动降级到 `/tmp/tg-signpulse`（非持久化）
- 新镜像已支持根据 `/data` 挂载目录属主 UID/GID 自动适配运行身份，通常无需 `chmod 777`

容器内排查命令：

```bash
id
ls -ld /data
touch /data/.probe && rm /data/.probe
```

## 常用环境变量（简版）

- `APP_SECRET_KEY`: 面板密钥，强烈建议设置
- `ADMIN_PASSWORD`: 初次安装时 admin 账户的默认密码（安全起见强烈建议设置，未设置则默认 admin123）
- `APP_HOST`: FastAPI 容器监听 IP，防暴露默认 `127.0.0.1`（如需用公网直连或宿主机反代端口请设为 `0.0.0.0`）
- `APP_DATA_DIR`: 自定义数据目录（优先级高于面板配置）
- `TG_PROXY`: Telegram 连接代理；也可在面板设置全局代理
- `TG_SESSION_MODE`: `file`（默认）或 `string`（arm64 推荐）
- `TG_SESSION_NO_UPDATES`: `1` 启用 `no_updates`（仅 `string` 模式）
- `TG_GLOBAL_CONCURRENCY`: 全局并发（默认 `1`）
- `APP_TOTP_VALID_WINDOW`: 面板 2FA 容错窗口

## 自定义数据目录

你可以通过两种方式设置数据目录：

1. 面板设置：`系统设置 -> 全局签到设置 -> 数据目录`
2. 环境变量：`APP_DATA_DIR=/your/path`

说明：
- 修改后建议重启后端服务生效
- 该目录请务必可写，并挂载持久化卷

## 本地开发

- 推荐使用 Python 3.12；项目支持 Python `>=3.10,<3.14`
- 不建议使用 Python 3.14 及以上版本，本项目依赖的 Telegram/Pydantic 运行时组件暂未完全兼容
- 前端使用 Node.js 20，进入 `frontend/` 后执行 `npm ci`

## 常用面板设置

在 `系统设置 -> 全局签到设置` 中可以配置：

- 全局代理：账号未单独配置代理时，登录、刷新会话和执行任务会默认使用该代理
- Telegram机器人通知：填写 Bot Token 和通知 Chat ID 后，任务失败、账号登录失效或关键词命中会自动发送通知
- 数据目录：用于保存 sessions、logs、数据库和任务数据

在账号任务页可以：

- 为目标群组填写 `话题 / Thread ID`，让签到只在指定话题内执行
- 在有序动作序列中添加 `关键词监听`，并在 `推送方式` 下拉框中选择 Telegram机器人、转发、Bark 或自定义 URL
- 仅当选择 `转发`、`Bark` 或 `自定义推送 URL` 时，页面才显示对应参数输入框，减少无关配置干扰
- 点击右上角导出图标，将当前账号全部任务复制到剪贴板
- 点击右上角"粘贴导入任务"，从剪贴板批量导入任务并跳过已存在的重复任务

## 健康检查

- `GET /healthz`：快速健康检查
- `GET /readyz`：服务就绪检查

## 项目结构

```text
backend/      FastAPI 后端与调度器
tg_signer/    Telegram 自动化核心
frontend/     Next.js 管理面板
```

## 更新日志

### 2026-05-12

- **修复任务执行 500 错误**：`run_task_with_logs` 中 `except` 块的局部 `logger` 赋值导致整个函数内 `logger` 变为未绑定局部变量，触发 `UnboundLocalError`，已移除该多余赋值。
- **编辑/新建任务后自动补执行**：创建、编辑或启用 range 模式任务时，若当前时间已在执行窗口内且今日未执行，会立即安排一次性补执行，不再等到第二天。

## 致谢

本项目 fork 自 [akasls/TG-SignPulse](https://github.com/akasls/TG-SignPulse)，其上游为 [amchii/tg-signer](https://github.com/amchii/tg-signer)，感谢两位作者的开源工作。

技术栈：FastAPI、Uvicorn、APScheduler、Pyrogram/Kurigram、Next.js、Tailwind CSS、OpenAI SDK。
