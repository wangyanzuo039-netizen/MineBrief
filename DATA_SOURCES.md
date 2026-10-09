# 数据与口径

## 可复现演示数据

所有原始文件通过 `prepare` 下载，manifest 记录 URL、资料日期、文件 SHA-256。源码包不附原文 PDF/XLSX；离线运行包的镜像包含已校验缓存。解析结果由原文计算，未在代码中写死答案。

| 用途 | 原始资料 | 日期与定位 |
| --- | --- | --- |
| Pilbara 新闻、项目资源量 | [Pilgangoora Resource Update](https://announcements.asx.com.au/asxpdf/20210906/pdf/4506cwh63z75jr.pdf) | 发布 2021-09-06；资源有效 2021-06-30；PDF 第 3 页 Table 1 |
| Pilbara 新闻 | [Full-Year Financial Results](https://www.asx.com.au/asxpdf/20210826/pdf/44zsgxgk0wzqkh.pdf) | 发布 2021-08-26；取前三页公告正文 |
| 锂价与趋势 | [LME LH closing prices](https://www.lme.com/-/media/files/data/reports-and-data/historical-data-for-cash-settled-futures/lh--closing-prices-19072021-to-08092021.xlsx) | 2021-07-19 至 2021-09-08；LH 工作表，USD/mt |
| NI 43-101 独立验收 | [Zeus Technical Report](https://noramlithiumcorp.com/site/assets/files/4051/may-15-2024-updated-mineral-resource-estimate-zeus-lithium-project.pdf) | 有效 2024-05-15；报告封面日期 2024-07-10；PDF 第 11 页 Table 1-1 |
| live 已登记项目报告 | [Pilgangoora Update 2025](https://announcements.asx.com.au/asxpdf/20250611/pdf/06kmc3l7r1bjsm.pdf) | 发布 2025-06-11；有效 2025-03-31；PDF 第 2 页 |

默认回放分析截止日 2021-09-08，新闻窗口 30 个日历日，趋势窗口 14 个日历日。资料的发布时间、资源有效日期和实际报价日分别保存；晚于截止日的项目报告不进入日报。命令执行时间会使用真实运行时间，不能与资料日期混淆。

## 资源量

Pilgangoora 原报告标准为 JORC 2012。适配器取 Table 1 的 Indicated / Inferred：矿石量、品位、含 Li2O 量、截止品位和证据页码。保留原表单位，不把 Li、Li2O 和 LCE 混用，不额外相加 Measured and Indicated。

Zeus 是独立 NI 43-101 验证：取摘要 Table 1-1 的 Total 行，排除 Upper/Lower 子区和汇总重复项；输出矿石 Mt、品位 ppm Li、含锂 kt Li。原表与结论段存在差异，工具将差异列为 warning；不悄悄选取更大数字。它不属于 Pilbara，绝不混进 Pilgangoora 资源表。

Indicated / Inferred 属于 Mineral Resources。不能改名为 Ore Reserves 或经济可采储量，也不把题目“储量”措辞当作篡改原文类别的理由。

2025 项目报告含矿体与堆存分类，适配器定位完整 Pilgangoora 合计，避免把堆存行当成矿山总资源。资源解析是特定版式 adapter，不支持任意矿山报告、扫描 PDF 或未核验版本；无法定位证据时返回错误。

## 价格

报价：LME Lithium Hydroxide CIF (Fastmarkets MB)，合约代码 LH，daily closing price，单位 USD/mt。它是期货收盘价口径，不声称是实时现货价格或锂辉石售价。

默认固定交割月份为 2021-09。工作簿 M01…M15 是相对月份列，按观察月份与交割月份的差值选列：七月取 M03，八月取 M02，九月取 M01。随后仅对同品种、同报价类型、同单位、同固定交割月份比较，避免跨月合约滚动失真。

趋势计算：`last - first`；百分比为 `(last - first) / first * 100`，Decimal 保留四位小数。未插值，也不把日历日数称为交易日数。默认窗口内 9 个实际点；价格点、起止日期和覆盖信息均返回给 client。

首值为零或少于两个点不计算百分比。窗口边界超过七天没有报价时标记 partial；该阈值用于 Demo 缺价提示，未接入完整交易所交易日历。单日报价最多回退七天并明确实际日期，不以任意旧值冒充请求日价格。

## 来源与证据处理

新闻回放包含发行人公开公告，新闻 server 的搜索按实体别名和发布时间筛选，fetch 从原始 PDF 读取正文；不是预写日报。无密钥模式截取首条公告要点，标为原文摘录；模型模式根据本次正文生成中文摘要。

live RSS 有元数据与正文两种状态。正文下载失败但已有非空 RSS 摘要时返回 partial，保留来源与失败说明；没有可用内容时明确报错。demo 和 live 中已登记原文均校验哈希；未核验内容版本不能套用报告元数据。下载只允许配置内 HTTPS 公共来源，每次重定向重新检查主机和公网 DNS，限制体积与超时。不绕过登录和来源访问控制。

原文件保存于本地缓存及本机 Docker 镜像。源码包仅含链接、哈希和少量抽取证据；离线包包含该镜像，用于本次本地演示与复验。公开分发原始文件或包含原始文件的镜像前，应另行确认来源使用条款。原文链接可能变化，失败时需人工更新 manifest 并重新验收。

## 公开演示缓存

`data/replay.json` 保存从已校验原文提取的少量资源量、行情事实与短新闻摘录，不含完整 PDF / XLSX。缓存哈希写入 manifest，每项关联原文哈希和源链接；PDF 缓存保留页码与原文证据。运行时通过 MCP 工具返回缓存，meta.evidence_origin 明确为 verified_extraction_cache。独立原文下载与解析仍可用 `prepare` 复验。

2026-10-09 新增两项 PLS 官方公告，实际下载并校验：2026-09-23 季报发布安排、2026-10-07 未上市证券通知。它们供 live 模式使用，不混入历史回放。新闻覆盖限于登记的公告；不是全网完整性承诺。
