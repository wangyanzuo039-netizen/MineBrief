MineBrief 工程演示版：三个独立 MCP server、一个 MCP Agent client、Markdown 日报、证据 JSON 与调用追踪。

下载 `mining-brief-offline.zip` 和同名 `.sha256`。Docker Desktop 已安装启动后，解压并双击 `start-offline.cmd`。源码包为 `mining-brief-demo.zip`，也可直接克隆仓库并运行 RUN.md 中的一条 Docker Compose 命令。

交付包在 GitHub 运行环境构建，经 50 项离线测试、真实 stdio MCP 集成、实际镜像空存储断网启动验证，再上传发布。当前包的镜像身份、阶段计时与结果在 `examples/release-startup-timing.json`，相应日报和调用追踪在 `examples/release-template-*`。该验证从本机已有 ZIP 和 Docker 开始，不包含下载和安装时间。

仓库保留 Windows 本机 53 项测试通过证据（含三项真实原文 PDF 测试）、62.51 秒首次启动证据以及 Ruff、格式、严格类型检查结果。Windows 与 GitHub 构建镜像身份分别记录，不混用计时证据；可选原文网络测试 job 未触发。

默认演示是明确标注的 2021-09-08 历史回放，采用经原文哈希核验的提取缓存。完整第三方 PDF/XLSX、账号、密钥和本地环境不进入公开包。`RUN.md` 提供启动、模型与 live 数据接入说明。

完整“今日日报”尚未验收：近期 live 新闻已实际取得，资源原文网络请求曾超时；LME 官网登录后可见最新报价，但历史回看和价格图未返回可验证序列，当前工作簿尚未接入 Agent。不将历史演示宣称为实时行情，也不虚构趋势。
