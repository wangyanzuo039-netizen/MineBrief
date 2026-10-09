# 五分钟运行指南

## 推荐：离线交付包

从 [GitHub Release](https://github.com/wangyanzuo039-netizen/MineBrief/releases/tag/v0.1.0-demo) 下载 `mining-brief-offline.zip` 及其 `.sha256`，完整解压。该包包含源码、运行镜像、依赖及核验提取缓存；演示时无需联网、模型密钥或付费数据账号。Git 仓库提供源码、配置和核验提取缓存；Release 提供离线运行包。完整第三方原文不进入仓库或公开镜像。

前提：Docker Desktop 已安装、启动，使用 Linux containers；电脑为 x86-64 Windows / Linux。五分钟计时从本地已有压缩包开始，包含解压、校验、首次导入镜像和生成日报；不包含安装 Docker 或传输交付包。

**Windows：进入解压后的文件夹，双击 `start-offline.cmd`。** 脚本自动检查 Docker、校验镜像 SHA-256、导入运行环境并调用 Compose，最后显示日报完整路径。不会修改系统执行策略或清理其他 Docker 数据。

也可手动执行。首次先导入随包镜像：

```powershell
docker load --input mining-brief-image.tar.gz
```

随后一条 Docker Compose 命令生成日报：

```powershell
docker compose -f compose.offline.yaml run --rm agent
```

默认输入：“给我生成一份关于 Pilbara 锂矿的今日简报”。默认采用 **2021-09-08 真实历史回放**，报告明确标注日期。离线 Compose 禁止网络，不会现场构建或拉取镜像。

Linux 用户在 Compose 命令前创建可写目录：

```bash
mkdir -p outputs
MINING_CONTAINER_UID="$(id -u)" MINING_CONTAINER_GID="$(id -g)" docker compose -f compose.offline.yaml run --rm agent
```

## 成功标志与验收

终端显示 `overall_status: complete`，退出码为 0。打开 `outputs/<run_id>/brief.md`；同目录的 `brief.json` 保存结构化证据，`trace.jsonl` 保存三个 MCP 服务的握手与工具调用，`*.stderr.log` 保存诊断日志。

Windows 一键脚本还生成 `outputs/offline-startup.json`，分别记录校验、导入和生成耗时；它不会把已有缓存测量冒充首次空环境测试。独立空镜像、空依赖层且断网的首次验收证据见 `examples/startup-timing.json` 和 `docs/验收记录.md`。本机实测通过五分钟目标，其他硬件仍可能有性能差异。

```powershell
docker compose -f compose.offline.yaml run --rm agent check
docker compose -f compose.offline.yaml run --rm agent extract-ni
```

`check` 实际调用题目五个工具并校验 NI 43-101 的 Indicated / Inferred，成功输出 `passed: true`。独立 NI 示例使用 Zeus 报告，不会混入 Pilbara 日报。

## Cursor / Claude Desktop

先通过上述步骤导入镜像并保持 Docker 运行。根目录 `mcp-config.json` 提供三个独立 Docker stdio 服务，无个人路径和模型密钥。

- Cursor：打开项目，启用随包的 `.cursor/mcp.json`，应看到 2 + 1 + 2 个工具。
- Claude Desktop（Windows）：设置中打开开发者配置，将 `mcp-config.json` 的三项 `mcpServers` 合并到 `%APPDATA%\Claude\claude_desktop_config.json`，保留原有配置，然后完全退出并重启。

配置参考：[Cursor MCP](https://cursor.com/docs/mcp)、[MCP 本地服务指南](https://modelcontextprotocol.io/docs/develop/connect-local-servers)。配置中的实际命令已通过 SDK 握手和五工具调用，GUI 显示尚未实测。

开发环境可执行 `uv run --frozen --no-editable python scripts/verify_mcp_config.py` 复验。需要本机 Python 配置时，先准备原文，再运行 `uv run --no-editable mining-brief mcp-config --transport local`；生成文件含本机路径，移动项目后须重新生成，不要提交。

## 源码开发与联网构建

源码包体积较小，含核验提取缓存，不含镜像或完整原文；首次构建需要网络下载基础镜像和依赖，不再下载第三方 PDF。离线 Release 是五分钟演示的推荐入口。

```powershell
docker compose run --build --rm agent --strict
```

不用 Docker 时，安装 Python 3.11 和 [uv](https://docs.astral.sh/uv/getting-started/installation/)：

```powershell
uv sync --frozen --python 3.11 --no-editable
uv run --frozen --no-editable mining-brief --strict
```

中文路径使用 `--no-editable`；修改源码后执行 `uv sync --frozen --no-editable --reinstall-package mining-brief`。全局参数放在子命令前，例如 `mining-brief --output outputs/checks check`。原文变化导致哈希不符时，人工核对并更新 manifest 和提取缓存，不能跳过校验。

## 可选：模型与当前日期模式

复制 `.env.example` 为 `.env`，仅在本地配置兼容 Chat Completions 的模型服务。模型模式需要网络，使用普通 Compose：

```powershell
docker compose run --rm agent --generation llm --strict
```

默认无需模型。显式选择 llm 后若服务失败或输出约束不满足，返回说明并降级模板；查看 `generation_mode` 与 trace。`--strict` 检查数据完整性，不把模型降级等同于数据失败。

```powershell
uv run --frozen --no-editable mining-brief --mode live --strict
```

live 采用上海时区当天日期，优先使用登记的近期发行人公告，无匹配公告时查询 Google News RSS。当前价格需配置 `MINING_PRICE_URL`（可访问的官方 LME LH 工作簿 URL）或 `MINING_PRICE_FILE`（LME LH 原始工作簿绝对路径）、`MINING_PRICE_CONTRACT`（YYYY-MM）和 `MINING_PRICE_SOURCE_URL`。格式要求 LH 工作表、USD/mt、M01…M15；其他格式需新增 adapter。已登记的项目报告为 2025 年披露，需维护 manifest 更新版本。**完整当前日期行情尚未验收**；缺失时明确 partial，不以历史报价补成“今日”。

## 质量检查与打包

```powershell
uv run --frozen --no-editable ruff check src tests scripts
uv run --frozen --no-editable ruff format --check src tests scripts
uv run --frozen --no-editable mypy src
uv run --frozen --no-editable pytest -m "not live"
uv run --frozen --no-editable python scripts/verify_tool_contract.py
uv run --frozen --no-editable python scripts/verify_image_revision.py
uv run --frozen --no-editable python scripts/package_delivery.py
uv run --frozen --no-editable python scripts/package_offline.py
```

默认检查在无原文缓存、无来源网络的环境运行，包含三服务 stdio 集成与自编 PDF 测试。原文复验单独执行 `uv run mining-brief prepare` 和 `uv run pytest -m live`；下载失败不能标成已验证。CI 的原文复验通过 Actions 手动勾选 fetch_originals 触发，默认 CI 不掩盖外部网络可用性。源码包与离线包均有 SHA-256 文件；按白名单打包，不含密钥、虚拟环境或个人输出。离线包的镜像包含演示原文缓存，使用范围见 DATA_SOURCES.md。

维护者复验空缓存首次启动：`powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify_offline_cold.ps1`。该脚本使用固定版本 Docker-in-Docker 辅助镜像（须提前获取），创建隔离、断网且没有宿主机 Docker socket 的临时测试引擎，结束后只移除本次辅助容器及其临时卷，不清理用户镜像。这不是 HR 启动步骤。

| 问题 | 处理 |
| --- | --- |
| Docker 不可用 | 启动 Docker Desktop，切换 Linux containers |
| 找不到离线 manifest / 镜像 | 完整解压离线包，在其目录运行 |
| 镜像校验失败 | 重新复制完整交付包，不关闭校验 |
| 模型降级为 template | 检查本地配置及 trace 错误类型，不展示密钥 |
| 价格 empty / 趋势 partial | 查看实际报价日及缺价说明，不插值补造 |
| PDF unsupported_format / needs_ocr | 仅支持已核验版式；新版本需 adapter / OCR |
