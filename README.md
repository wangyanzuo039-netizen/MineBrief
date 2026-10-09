# MineBrief — 矿权日报 Agent

通过三个独立 MCP server 生成可追溯的 Pilbara / Pilgangoora 矿业日报，包含新闻摘要、资源量、价格走势、风险提示和原文引用。Python 3.11 + 官方 MCP SDK v1，固定流程 Agent；所有业务工具调用经过 MCP stdio 会话。

## 从 GitHub 运行

先安装并启动 Docker（Linux containers），再运行：

```powershell
git clone --branch dev https://github.com/wangyanzuo039-netizen/MineBrief.git
cd MineBrief
docker compose run --build --rm agent --strict
```

首次源码构建只需联网下载基础镜像与依赖；演示证据缓存随源码提供，不依赖第三方网站。成功后打开 `outputs/<run_id>/brief.md`。不需要模型密钥或付费数据账号。

## 离线演示

从 [GitHub Release](https://github.com/wangyanzuo039-netizen/MineBrief/releases/tag/v0.1.0-demo) 下载 `mining-brief-offline.zip` 和 SHA-256 文件。解压后启动 Docker Desktop，再双击 `start-offline.cmd`。脚本校验并导入随包运行环境，然后生成日报；不依赖现场下载 Python 包或原始资料。镜像只带核验提取缓存，不打包完整第三方 PDF / XLSX。

手动运行（在已解压的离线包目录中）：

```powershell
docker load --input mining-brief-image.tar.gz
docker compose -f compose.offline.yaml run --rm agent
```

前提为已收到交付包，Docker Desktop 已安装、启动并使用 Linux containers。离线包面向 x86-64 Windows / Linux；应用不需要模型密钥，结果写入 `outputs/<run_id>/brief.md`。首次无项目缓存验收、源码构建和模型模式见 [RUN.md](RUN.md)。

## 演示与交付

- [实际模型生成日报](examples/brief.md)：完整新闻、资源量、9 个同合约价格点及引用。
- [实际 MCP 调用轨迹](examples/trace.jsonl)：三个服务的握手、工具发现及调用记录。
- [NI 43-101 验证结果](examples/ni-resources.json)：从 Zeus 原始报告抽取 Indicated / Inferred，保留页码与原文证据。
- [演示脚本](DEMO.md)、[数据说明](DATA_SOURCES.md)、[架构与工程规范](ARCHITECTURE.md)、[验收记录](docs/验收记录.md)。

| 服务 | 工具 | 数据实现 |
| --- | --- | --- |
| mining-news-mcp | `search(query, days)`、`fetch_article(url)` | ASX 发行人公告回放；live 模式近期登记公告 / Google News RSS |
| mineral-pdf-mcp | `extract_resources(pdf_url)` | PyMuPDF 原文/表格解析；NI 43-101 和 JORC 专用 adapter |
| lme-price-mcp | `get_price(commodity, date)`、`get_trend(commodity, days)` | LME 原始历史工作簿；Decimal 计算固定合约趋势 |

## 数据边界

默认是 **2021-09-08 历史回放**，并非当前日期实时行情。核验提取缓存由发行人、交易所原文解析生成，关联原文与缓存 SHA-256，没有伪造新闻、资源数字或价格序列。`prepare` 可另行下载原文复验；默认演示读取提取缓存并明确标注，不宣称每次现场解析 PDF。模板模式抽取新闻原文要点；配置模型后生成中文摘要，失败时明确降级。

Pilgangoora 按 JORC 2012 披露；题目要求的 NI 43-101 功能用 Zeus 技术报告单独验证。两者不混入同一矿山日报。Indicated / Inferred 为资源量类别，保留题目工具名 `extract_resources`；资源量与 Ore Reserve 储量分别报告。

LME 氢氧化锂为相关下游商品指标，不等于项目锂辉石精矿销售价格。使用固定 2021-09 交割月份，避免跨月直接拼接 M01 产生失真。

`--mode live` 使用运行当日（上海时区），但完整在线日报仍需配置当前 LME 数据，且新闻全文可能受来源限制。缺失时输出 `partial` 和原因；不会用历史数据冒充当天数据。此版本的验收基线是可复现 Demo。

## 工程结构

```text
src/mining_brief/
  agent.py, mcp_client.py      # Agent 编排、真实 MCP client
  servers/                    # 三个独立 MCP server
  providers/                  # 新闻、PDF、价格数据适配器
  schemas.py, network.py      # 结构校验、受限网络读取
  model.py, render.py          # 模型生成与确定性 Markdown 渲染
  cli.py, config.py, data.py   # 入口、配置、数据准备
tests/                        # 单元与真实 stdio 集成测试
scripts/                      # 桌面配置验证、交付打包
data/manifest.json            # 原文 URL、日期、哈希（不包含原文文件）
examples/                     # 实测演示结果
.github/workflows/ci.yml       # 质量检查与原始证据/容器验证
```

依赖由 `uv.lock` 锁定，提供类型检查、代码规范、自动化测试、非 root 容器、结构化调用日志、模型密钥隔离和可重复构建步骤。具体实现边界见 [ARCHITECTURE.md](ARCHITECTURE.md)。

协议实现依据 [官方 MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk/tree/v1.30.0)；本项目锁定 v1 API，不跟随主分支更换大版本。
