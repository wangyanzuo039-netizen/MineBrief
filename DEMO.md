# 演示脚本（约三至五分钟）

## 演示前

启动 Docker Desktop，解压离线交付包并双击 `start-offline.cmd`，确认镜像导入与报告生成成功。打开 `examples/brief.md` 备用。无需在演示屏幕上展示 `.env` 或模型密钥。

## 1 介绍（约 30 秒）

“我使用 Python 和官方 MCP SDK 实现了三个独立 server、五个规定工具和一个固定流程 Agent client。为了让演示不依赖付费数据账号，默认回放真实公开历史资料；报告中明确标注截止日期，所有数字都有原文来源。”

展示 README 中服务表和 ARCHITECTURE 流程图。

## 2 生成日报（约 60 秒）

```powershell
docker compose -f compose.offline.yaml run --rm agent --query "给我生成一份关于 Pilbara 锂矿的今日简报" --strict
```

打开最新 `outputs/<run_id>/brief.md`，展示四个主要部分与原文链接。说明无密钥使用原文要点摘录；若已配好模型且允许联网，运行 `docker compose run --rm agent --generation llm --strict` 展示中文摘要，或打开实测模型样例。离线 Compose 不连接模型服务。

演示要点：日历窗口、项目实体、数据截止日、JORC 标准、资源量类别、固定交割月份及真实报价日。点击原文资源报告，定位 PDF 第 3 页比对数据。

## 3 证明真实 MCP（约 30 秒）

打开本次 `trace.jsonl`：三个 `initialize+tools/list`，随后 `search`、`fetch_article`、`extract_resources`、`get_price`、`get_trend`。指出业务层没有绕过 MCP 直接调用 provider。

桌面接入时展示 `.cursor/mcp.json` 与三个服务工具列表；若桌面客户端尚未登录，使用配置协议验证记录说明启动命令已实测，不把 SDK 验证说成 GUI 验证。

## 4 NI 43-101 独立验证（约 30 秒）

```powershell
docker compose -f compose.offline.yaml run --rm agent extract-ni
```

打开结果 JSON 或 `examples/ni-resources.json`，展示 NI 43-101、Indicated/Inferred、页码、原文片段和单位。说明 Pilbara 是 JORC，Zeus 的 NI 报告仅用来验证题目 PDF 工具要求，不混入 Pilbara 日报。可打开原报告第 11 页看 Total 两行。

## 5 工程质量与边界（约 30 秒）

展示 `docs/验收记录.md`：代码规范、类型检查、自动化测试、容器运行与配置命令验证。说明完整 live 今日模式需要当前行情和持续维护来源，数据缺失有明确状态，不自动替换成模拟价。

完整离线资料：`dist/mining-brief-offline.zip`，包含代码、运行说明、MCP 配置、锁文件、数据说明、实测样例、验收记录及运行镜像；小体积源码包为 `dist/mining-brief-demo.zip`。演示录像可按这个脚本自行录制；项目包不声称包含录像。
