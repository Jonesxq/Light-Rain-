# RAG 系统 10 PDF 测评与优化报告

- 生成时间：2026-06-03
- 知识库 ID：1
- 测评集：10 个 PDF，每个 PDF 20 个问题，共 200 条问答
- 检索参数：top_k=4，query rewrite=true
- 回答模型：qwen3.7-max
- 裁判模型：qwen3.7-max

## 一、入库结果

本次知识库已完成 10 个 PDF 的入库，其中后 6 个 PDF 是本轮补充上传。所有 PDF 文档均处于完成状态；超大文档已通过“大文档跳过逐 chunk LLM 摘要”的保护逻辑完成入库，避免长时间卡在 `processing`。

| 序号 | PDF | Chunk 数 | 文件大小 |
|---:|---|---:|---:|
| 1 | `01_nist_ai_risk_management_framework_1_0.pdf` | 59 | 1.86 MB |
| 2 | `02_nist_generative_ai_profile.pdf` | 365 | 1.12 MB |
| 3 | `03_nist_cybersecurity_framework_2_0.pdf` | 124 | 1.45 MB |
| 4 | `04_retrieval_augmented_generation_for_knowledge_intensive_nlp.pdf` | 129 | 0.84 MB |
| 5 | `05_attention_is_all_you_need.pdf` | 70 | 2.11 MB |
| 6 | `06_nasa_systems_engineering_handbook.pdf` | 1407 | 3.60 MB |
| 7 | `07_who_ethics_governance_ai_for_health.pdf` | 862 | 1.88 MB |
| 8 | `08_world_bank_wdr_2021_data_for_better_lives.pdf` | 2614 | 33.69 MB |
| 9 | `09_ipcc_ar6_synthesis_report_spm.pdf` | 259 | 5.29 MB |
| 10 | `10_cisa_secure_by_design_principles.pdf` | 69 | 0.75 MB |

## 二、总体 RAGas 结果

| 指标 | 得分 | 解读 |
|---|---:|---|
| 忠实度 faithfulness | 0.967 | 回答基本能被检索上下文支撑，幻觉控制较好。 |
| 答案相关性 answer_relevancy | 0.817 | 当前最明显短板，部分回答没有完全贴合问题粒度。 |
| 上下文精确率 context_precision | 0.847 | 大部分命中文档相关，但仍有跨文档噪声。 |
| 上下文召回率 context_recall | 0.853 | 多数问题能拿到依据，但复杂、目录、表格类问题仍会漏召回。 |

补充说明：本轮 RAGas 对 200 条样本进行了评分，出现 1 条 `faithfulness` 缺失值，评估日志中有一次裁判任务超时；RAGas 以 `raise_exceptions=False` 继续完成整体统计。

低分样本数量：

- 答案相关性 < 0.7：32 条
- 上下文精确率 < 0.5：25 条
- 上下文召回率 < 0.5：29 条
- 忠实度 < 0.8：9 条
- 忠实度缺失：1 条

## 三、按文档拆分

| PDF | QA 数 | 源文档命中率 | 忠实度 | 答案相关性 | 上下文精确率 | 上下文召回率 |
|---|---:|---:|---:|---:|---:|---:|
| `01_nist_ai_risk_management_framework_1_0.pdf` | 20 | 95% | 1.000 | 0.771 | 0.883 | 0.850 |
| `02_nist_generative_ai_profile.pdf` | 20 | 95% | 0.959 | 0.856 | 0.854 | 0.825 |
| `03_nist_cybersecurity_framework_2_0.pdf` | 20 | 85% | 0.982 | 0.708 | 0.658 | 0.700 |
| `04_retrieval_augmented_generation_for_knowledge_intensive_nlp.pdf` | 20 | 100% | 0.938 | 0.914 | 0.933 | 0.950 |
| `05_attention_is_all_you_need.pdf` | 20 | 100% | 0.995 | 0.847 | 0.867 | 0.950 |
| `06_nasa_systems_engineering_handbook.pdf` | 20 | 75% | 0.958 | 0.816 | 0.832 | 0.850 |
| `07_who_ethics_governance_ai_for_health.pdf` | 20 | 100% | 0.986 | 0.748 | 0.696 | 0.750 |
| `08_world_bank_wdr_2021_data_for_better_lives.pdf` | 20 | 100% | 0.942 | 0.747 | 0.833 | 0.800 |
| `09_ipcc_ar6_synthesis_report_spm.pdf` | 20 | 100% | 0.975 | 0.917 | 0.987 | 1.000 |
| `10_cisa_secure_by_design_principles.pdf` | 20 | 100% | 0.932 | 0.845 | 0.921 | 0.850 |

观察：

- `09_ipcc_ar6_synthesis_report_spm.pdf` 表现最好，四项指标都很高，说明短而结构清晰的报告更适合当前检索配置。
- `03_nist_cybersecurity_framework_2_0.pdf`、`07_who_ethics_governance_ai_for_health.pdf` 和 `08_world_bank_wdr_2021_data_for_better_lives.pdf` 的相关性/召回偏低，主要和术语相近、问题粒度较细、跨文档噪声有关。
- `06_nasa_systems_engineering_handbook.pdf` 和 `08_world_bank_wdr_2021_data_for_better_lives.pdf` chunk 数非常多，检索空间变大后，单纯 top_k=4 更容易漏掉精确依据。

## 四、噪声来源

测评集中每条问题都绑定一个目标 PDF。源文档命中率表示 top_k 检索结果里是否至少出现该目标 PDF。整体看，多数问题都能命中目标 PDF，但有明显跨文档混入：

| 目标 PDF | 混入来源 | 次数 |
|---|---|---:|
| `01_nist_ai_risk_management_framework_1_0.pdf` | `02_nist_generative_ai_profile.pdf` | 21 |
| `07_who_ethics_governance_ai_for_health.pdf` | `08_world_bank_wdr_2021_data_for_better_lives.pdf` | 5 |
| `03_nist_cybersecurity_framework_2_0.pdf` | `07_who_ethics_governance_ai_for_health.pdf` | 4 |
| `07_who_ethics_governance_ai_for_health.pdf` | `01_nist_ai_risk_management_framework_1_0.pdf` | 4 |
| `03_nist_cybersecurity_framework_2_0.pdf` | `10_cisa_secure_by_design_principles.pdf` | 3 |
| `04_retrieval_augmented_generation_for_knowledge_intensive_nlp.pdf` | `02_nist_generative_ai_profile.pdf` | 2 |
| `07_who_ethics_governance_ai_for_health.pdf` | `02_nist_generative_ai_profile.pdf` | 2 |
| `10_cisa_secure_by_design_principles.pdf` | `02_nist_generative_ai_profile.pdf` | 2 |
| `01_nist_ai_risk_management_framework_1_0.pdf` | `03_nist_cybersecurity_framework_2_0.pdf` | 1 |
| `01_nist_ai_risk_management_framework_1_0.pdf` | `05_attention_is_all_you_need.pdf` | 1 |

其中 `01_nist_ai_risk_management_framework_1_0.pdf` 和 `02_nist_generative_ai_profile.pdf` 互相混入较多，这是合理但会影响评测的现象：两份文档主题高度相近，都围绕 NIST AI RMF/生成式 AI 风险管理。另有少量旧 `.md` 文档被召回，说明当前知识库里仍混有之前上传的中文法规 Markdown 文档；如果测评目标是 10 个 PDF，应在评测阶段加入文档过滤，或把 PDF 单独放入一个专用知识库。

## 五、典型低分样本

| 序号 | PDF | 问题 | 忠实度 | 相关性 | 精确率 | 召回率 | 主要检索来源 |
|---:|---|---|---:|---:|---:|---:|---|
| 159 | `08_world_bank_wdr_2021_data_for_better_lives.pdf` | 根据提供的参考文献列表，估计挖掘潜在需求可能使行业规模每年增加0.5%的作者是谁？ | 0.000 | 0.000 | 0.000 | 0.000 | `08_world_bank_wdr_2021_data_for_better_lives.pdf` |
| 41 | `03_nist_cybersecurity_framework_2_0.pdf` | 在该文档片段中，长横线表格分隔符上方显示的英文字母是什么？ | N/A | 0.000 | 0.000 | 0.000 | 无 |
| 181 | `10_cisa_secure_by_design_principles.pdf` | 根据文档目录，“免责声明”（Disclaimer）和“资源”（Resources）这两个部分位于第几页？ | 0.000 | 0.000 | 1.000 | 0.000 | `10_cisa_secure_by_design_principles.pdf` |
| 148 | `08_world_bank_wdr_2021_data_for_better_lives.pdf` | 以告知公共政策为目的收集的数据，应当如何促进政府、公民和商业之间的互动？ | 1.000 | 0.000 | 0.000 | 0.000 | `08_world_bank_wdr_2021_data_for_better_lives.pdf`, `中华人民共和国数据安全法.md` |
| 137 | `07_who_ethics_governance_ai_for_health.pdf` | 为什么数据持有者的保密义务在保护AI健康技术相关数据的患者隐私方面存在局限性？ | 1.000 | 0.000 | 0.000 | 0.000 | `07_who_ethics_governance_ai_for_health.pdf` |
| 132 | `07_who_ethics_governance_ai_for_health.pdf` | 在AI技术的开发和部署中，如何通过“人类保证”机制来确保责任？ | 1.000 | 0.000 | 0.000 | 0.000 | `01_nist_ai_risk_management_framework_1_0.pdf`, `07_who_ethics_governance_ai_for_health.pdf` |
| 121 | `07_who_ethics_governance_ai_for_health.pdf` | 在AI应用的可持续性方面，政府和公司需要采取哪些措施来应对工作场所的预期中断？ | 1.000 | 0.000 | 0.000 | 0.000 | `07_who_ethics_governance_ai_for_health.pdf`, `02_nist_generative_ai_profile.pdf`, `01_nist_ai_risk_management_framework_1_0.pdf` |
| 103 | `06_nasa_systems_engineering_handbook.pdf` | 根据文档内容，“验证和确认结果”（Verification and validation results）经历了哪些状态或阶段？ | 1.000 | 0.000 | 0.000 | 0.000 | `06_nasa_systems_engineering_handbook.pdf` |

低分问题里有三类需要区分：

- 真实系统问题：检索到了目标文档，但没有命中精确段落，导致召回/精确率为 0。
- 测评集问题：有些问题来自表格分隔符、参考文献列表、目录页码等非常细碎的文本，作为 RAG 压测可以保留，但不代表典型用户问题。
- 评分超时/缺失：少量裁判任务超时会让单条指标缺失，不影响总体趋势，但后续自动化测评应记录并重试。

## 六、优化建议

### 1. 给评测和问答都加文档级过滤

当前问答接口以知识库为整体检索范围。对于“针对某个 PDF 的问题”或“测评某批 PDF”这类场景，应支持 `doc_id` / `file_name` 过滤。这样可以把跨文档主题相近造成的噪声先降下来，尤其是 NIST AI RMF 与 NIST GenAI Profile 这种高度相近的文档。

### 2. 将旧 Markdown 文档与 PDF 测评集隔离

本次知识库中仍存在之前上传的中文法规 `.md` 文档，评测日志也显示它们偶尔被召回。建议二选一：

- 若当前目标是评估 10 个 PDF，把 10 个 PDF 放入独立知识库；
- 若必须共用知识库，在评测脚本和问答请求里传入候选 doc_id 列表，只评估目标文档集合。

### 3. 对长文档做分层检索

`06_nasa_systems_engineering_handbook.pdf` 和 `08_world_bank_wdr_2021_data_for_better_lives.pdf` 的 chunk 数分别达到 1407 和 2614。建议把检索改成两级：先按标题/章节/页码粗召回，再在候选章节内做 chunk 级精排。这样既减少检索空间，又能提升上下文召回。

### 4. 加强结构化元数据

Docling 已经能解析 Markdown、标题和页面结构，应把 `page_number`、`section_path`、`heading`、`table_caption`、`doc_id` 写入向量 metadata，并在回答引用里展示。对目录、表格、列表、图注类问题，metadata 往往比纯文本相似度更关键。

### 5. 调整 query rewrite 与 top_k 策略

本轮使用 query rewrite。它能扩展中文问题，但也可能把问题改得过泛。建议下一轮做 A/B：

- A 组：`use_query_rewrite=true, top_k=4`，沿用本轮设置；
- B 组：`use_query_rewrite=false, top_k=4`；
- C 组：`use_query_rewrite=true, top_k=8`，再用 reranker 压回 4 条上下文。

### 6. 大文档摘要策略改成“章节摘要”，不要逐 chunk 摘要

本轮新增了大文档保护：超过阈值后跳过逐 chunk LLM 摘要，避免入库卡死。这对稳定性很必要。后续可以升级为“章节级摘要”：只对标题树/章节首页/高信息密度段落生成摘要，而不是对几千个 chunk 全量调用 LLM。

### 7. 固化自动化测评流水线

建议把本次 200 条 QA 作为第一版固定回归集。每次修改检索、chunk、rerank 或 prompt 后，都运行同一份数据集，并把 summary、per-doc 明细、低分样本自动输出为报告。重点跟踪：

- 总体四项指标；
- 每篇文档四项指标；
- 目标文档命中率；
- 低于阈值的问题数量；
- 旧文档/非目标文档混入次数。

## 七、复现实验命令

以下命令不包含真实密码，运行时请把 `<你的密码>` 替换成你的本地账户密码。

```powershell
Set-Location 'E:\code\official_proj2.0\backend'
$env:LR_USERNAME='xqwd'
$env:LR_PASSWORD='<你的密码>'
.venv\Scripts\python.exe scripts\generate_doc_eval_dataset.py --kb-id 1 --expected-docs 10 --questions-per-doc 20 --batch-size 5 --output E:\code\official_proj2.0\backend\ragas_doc10_qa_dataset_20260603.json
Remove-Item Env:\LR_USERNAME, Env:\LR_PASSWORD

.venv\Scripts\python.exe scripts\evaluate_current_kb_ragas.py --kb-id 1 --dataset E:\code\official_proj2.0\backend\ragas_doc10_qa_dataset_20260603.json --top-k 4 --output-dir scripts\ragas_reports
```

## 八、结论

这次迭代后的系统已经能稳定完成 10 个 PDF 的入库和 200 条 QA 的自动化 RAGas 测评。当前系统的强项是忠实度，说明回答基本站在检索证据上；主要优化方向是提升文档级检索约束、减少跨文档噪声、增强长文档的章节级召回，并把固定测评集纳入每次迭代的回归流程。
