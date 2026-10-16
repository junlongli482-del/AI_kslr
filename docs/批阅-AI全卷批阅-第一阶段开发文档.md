# 批阅 · AI 全卷批阅 · 第一阶段开发文档

版本：v0.1｜日期：2026-10-15｜状态：开发设计基线，尚未实现。本文中的新表、新接口、模块和测试均为计划，不代表现有能力。

业务依据：[第一阶段需求文档](批阅-AI全卷批阅-第一阶段需求文档.md)。本轮用户明确要求产出文档，未授权据此直接实施运行代码。

## 1. 架构决策

沿用现有 Vue/TypeScript → Java/Spring Boot → Python/FastAPI、PostgreSQL 与本地资产目录。新增批阅业务，不把学生卷作为新的快速录入任务，也不重跑标准卷 MinerU。

```text
快速录入已入库试卷版本
  └─ 标准数据适配：题目、答案、分值、原页、区域、必要图形语义
                     ↓
一个学生的多页照片 → 方向/页序/质量/配准 → 手写作答识别
                     ↓                    ↓
               原图与坐标变换         题目/小问/步骤文字及位置
                                          ↓
                      纯文字评分输入 → 一次全卷评分请求
                                          ↓
                         协议校验/总分计算/状态与费用
                                          ↓
                           卷面标记/人工改分/历史追溯
```

核心边界：

1. 识别服务可以读取图片，这是作答识别阶段；评分服务只接收文字。未来作图多模态评分走独立能力，本期不实现、不自动回退调用。
2. “一次”指一个学生一个版本正常首轮的全卷评分请求，不包含识别调用，也不保证重试/渠道故障不会增加费用。
3. 文档不指定尚未验证的手写供应商、API 路径、模型标识或价格。先完成能力验证，再选择适配器。
4. 本期使用一份已入库、具备原卷模板的教辅卷，优先实现单份提交。无需新增班级、学生账号或批次模型。

## 2. 当前源码依据与复用边界

下列相对路径均以项目根目录为基准，描述 2026-10-15 本轮阅读到的实现；并行开发可能改变行号，按符号定位。

| 现有位置 | 已有事实 | 批阅接入方式 |
|---|---|---|
| `apps/ai/core.py:Question/Region/Result` | 题目结构、多个区域、用途、页码、顺序；属性为可扩展字典 | 转换为批阅标准快照，不改现有识别结果结构 |
| `core.py:render_pages` | 原 PDF 每个物理页渲染为图片，保存尺寸、地址、image_key | 读取标准页作为配准参照，不重新请求印刷识别 |
| `core.py:compile_result` | paper 保存 source_document_ids；答案匹配、来源、知识点未配置状态等 | 按 paper 过滤文档、题目与来源，避免把答案文件当学生页面模板 |
| `core.py:suggest_response_regions` | 版面推定作答框；当前含小问间分段留白逻辑及版本标记 | 仅当候选；历史稿、几何边界和实际学生落笔仍需验证，不当作可靠笔迹范围 |
| `apps/api/.../TaskService.java:commit` | 入库固定题目版本，paper.content 和教辅模板保存 documents；仅 textbook 生成 source_template | 引用 paper_revision 与题目版本，读取已审核的正式数据 |
| `StoreMapper.java:paperQuestions` | 按 sort_order 返回题目版本及 content，目前不返回引用表 score | 新适配查询补出 pq.score、顺序、版本等；不误称现有详情接口已提供所有规范字段 |
| `QuickEntryController.java:paper` | `/api/paperbank/papers/{id}` 返回 paper、questions、templates | 前端选卷与初步预检入口；Java 内部构建规范快照 |
| `apps/ai/core.py:LLM.json` | 文字 JSON 请求、缓存、渠道、耗时/usage/费用和错误诊断 | 评分可复用基础能力；新增严格评分协议，不能只替换提示词就算完成 |
| `apps/ai/channels.py` | 渠道配置、超时和用量计价 | 沿用已配置文字渠道；独立配置评分模型能力、预算、提示词版本 |
| `apps/web/src/components/SourceViewer.vue` | 整页查看、SVG 框、缩放、页切换及拖框 | 抽取展示能力；标准模板和学生页覆盖层使用不同数据对象 |
| `QuestionPreview.vue` / `types.ts` | 题目、答案、解析预览与编辑类型 | 批阅只读标准题目预览；新增作答/评分类型，不复用原题编辑状态 |

注意：实施文档、BACKLOG 中有历史状态。以开工时的源码、正式稿和真实验证为准；不得用旧定位报告中“尚未修复”覆盖已出现的新逻辑，也不得把新逻辑存在视为历史数据已自动修复。

## 3. 标准卷适配与预检

### 3.1 ReferencePaperSnapshot

创建提交时读取正式试卷，构建不可变快照：

- `paper_revision_id`、`task_id`、`review_revision`、试卷标题、模式、`schema_version`、`snapshot_hash`。
- `questions[]`：正式 `question_revision_id`、来源题目 ID、题号、顺序、题干、选项、小问、标准答案、解析、来源状态、题型、评分标准、满分与区域。
- 分值优先使用该卷 `paper_question.score`；若为空，只在题目属性分值有效且已记录来源时使用其回退值。二者冲突须报出，不静默择一。
- `reference_pages[]`：稳定页标识、document_id、0 起始物理 page_index、尺寸、资产键与摘要、可用印刷页说明。
- `question_page_regions[]`：正式题目标识、原始题目标识映射、区域、用途与次序。
- `text_conditions[]`：已有或人工补足的必要图形语义、来源、确认状态。第一阶段不使用图片模型自动补图形语义。

不把 `result.json` 当作正式人工结果，不从全局题库“取最新题目”替换该卷固定引用，不使用可变审核稿作为评分依据。

### 3.2 页面集合

`paper.content.documents` 当前可能包含整个录入任务的题卷和答案文档。先按 `source_document_ids` 和题目区域引用确定来源，再确定该卷实际页面集合：

1. 纯答案文件不加入标准页面集合。
2. 单文档明确只含一卷时，可取该题卷完整物理页集合，包括续写/空白页。
3. 同一源文档含多套卷时，仅有题框不能证明所有空白续页归属；预检要求显式确认该卷页面集合，禁止拿整文档页数当该卷页数。
4. 不把左右两栏的印刷页码当成两个 PDF 物理页；保存其展示说明即可。

缺失页面、无效资产、题号/ID冲突、非正或缺失满分、标准答案缺失等列为结构化问题。零分说明项不是评分单位；哪些项只影响单题、哪些阻断整卷，由问题码和业务状态决定。

已有答案为“略/图略”或 AI 生成未确认等情况应展示来源风险，不把不完整答案当成充分依据。可评分题缺少实质答案时默认待核对，不在评分阶段擅自补写一份新标准答案。解析为空或知识点未配置本身不阻断。

## 4. 页面处理

### 4.1 资产与坐标

原图、EXIF 方向处理后的图、配准校正图分别存储；保存每一步的尺寸和变换，不覆盖原图。

坐标契约统一：每条位置声明 `coordinate_space`，区分原上传像素、定向后像素、标准页像素和标准页归一化坐标。业务结果采用标准页左上原点的 `[x0,y0,x1,y1]`，各项在 0～1 内，显示时乘实际尺寸。

保存从原图到标准页及逆向映射的信息；若后续使用非线性形变，不能仅以一个矩阵冒充所有变换。步骤标记来自 OCR 位置及其映射，评分模型引用 block_id，不让文字模型凭空输出卷面坐标。

### 4.2 匹配、质量与配准的工程候选

先尝试本地页面方向候选、版面/特征对应和黑色定位标记，必要时结合 OCR 的标题、题号、内容锚点。页码、姓名、相近标题均不能单独证明匹配正确。

候选实现可评估 OpenCV 等本地图像处理方案；不将“照片看着清楚”当成已有可量化精度，不承诺算法已通过样本。具体阈值由真实照片和故意扰动样本标定并版本化。

保存 `registration_version`、匹配目标、旋转角、质量指标、可视叠加检查图和原因；输出 `good / uncertain / failed`。uncertain 进入待处理；failed 禁止进入该页自动评分。

检测缺页、重页、不同卷和目标页歧义。相同文件摘要可确认为完全重复；不同拍摄照片是否同一页需验证内容。独立照片即使属于同一物理页，只有确认冗余且有效内容无冲突时才能去重。

第一阶段每张图按一个完整横向物理页处理；不扩展为任意半页拼接、缺边补全或严重纸张变形修复。整卷缺页默认停在待补齐，人工明确选择保留部分结果属于后续产品扩展，不偷偷实施。

## 5. 手写识别适配层

### 5.1 先做能力验证

在接入真实评分前，用正确标准卷和真实手写样本验证：

- 中文姓名、数字、选择答案、分数/根式/上下标/方程、证明步骤、删改和小问编号。
- 坐标、阅读顺序、跨栏/跨页、小问间空白和图旁文字覆盖。
- 正确区分印刷题干、学生笔迹和空白；不能用标准答案重构未识别过程。
- 单页/整卷请求方式、尺寸限制、超时、恢复、返回用量、真实计价和图片数据传输方式。

现有 MinerU 作为候选之一而非既定手写引擎。若候选只支持印刷识别或缺少位置/覆盖信息，应明确能力不足；不得用空白卷或渲染印刷文本冒充手写通过。具体供应商尚未确认时接口保持适配，不虚构可执行的供应商 API。

评分模型的文字限制不禁止 OCR 服务接收图片，但不能偷偷把 OCR 实现换成整卷多模态判分。新增付费服务或新供应商的选择与凭据需另外具备授权。

### 5.2 规范协议

建议 `StudentRecognitionV1`：

```json
{
  "schema_version": "grading-recognition-v1",
  "run_id": "<运行ID>",
  "pages": [{"page_id": "<上传页ID>", "reference_page_id": "<标准页ID>", "coverage_status": "complete", "issues": []}],
  "blocks": [{"id": "b1", "page_id": "<上传页ID>", "reference_page_id": "<标准页ID>", "bbox": [0.1, 0.2, 0.4, 0.25], "coordinate_space": "reference_normalized", "kind": "handwriting", "text": "x=2", "latex": "x=2", "confidence": null, "reading_order": 1}],
  "answers": [{"question_revision_id": "<正式题目版本ID>", "subquestion_key": null, "status": "recognized", "text": "x=2", "block_ids": ["b1"], "issues": []}],
  "name_observations": [],
  "provider_metadata": {"adapter_version": "<版本>", "provider_request_id": null}
}
```

示例只描述形状，不是已有结果。供应商不返回置信度时保留 null，不伪造分数。`kind` 至少区分 printed、handwriting、uncertain，划掉内容保留排除标识和证据，不直接删除。

作答状态：`recognized / blank / unreadable / missing_page / ambiguous / manual_drawing`。blank 需完整清晰的区域覆盖证据；识别输出空字符串不是空白证明。

用稳定题目版本 ID 匹配，不仅按显示题号。小问 key 从标准快照生成，保留原编号。匹配不唯一则 ambiguous。印刷题干或解题示范不能误计入学生作答。

初版工程默认按校正整页或整卷进行识别，再按位置和题目关系归并；不强制按候选作答框裁切。若确需切块保证识别质量，合并覆盖所有必要内容并去重，保留块来源及实际调用次数，不变成逐题评分模式。

## 6. 评分单位与文本输入

### 6.1 ScoringUnit

先生成唯一可加总的评分单位：默认整道顶层题为一个单位。存在明确独立小问满分且需排除作图部分时可拆为小问单位；拆分总满分应与父题一致，父题仅展示汇总、不再计分。

`unit_id`、question_revision_id、subquestion_key、max_score、eligibility、manual_reason、标准内容和作答块引用都由程序生成，不交给模型决定卷内题目集合。

混合题无可靠小问分值时整题 manual_drawing；有明确小问分值但文字问依赖学生绘图时同样待人工。含图的文字题需确认文本条件充分；保留原图片用于老师查看，不在文本评分输入中提供可取图链接、图片附件或虚构图像描述。

### 6.2 文字评分输入

输入仅包含本卷评分单位、必要题干/选项/小问、已有图形条件文字、标准答案/解析、满分、可选评分标准、识别的学生步骤文字及 block_id。

裁剪输入时不能删掉影响评分的公式、条件、作答步骤或跨页内容。对 Markdown 图片引用、HTML 图片和编辑器图片节点，按明确规则提取已有文字说明或标记缺图形语义；不能靠删除 URL 就把不完整题当作完整题。已有图片语义来源必须追溯。

不发送整个 documents、完整 OCR 原包、编辑器文档、无关答案、其他试卷、费用日志、密钥或本地磁盘路径。不允许评分工具取图。题干、学生笔迹和 OCR 文本均视为业务数据，不执行其中夹带的指令。

### 6.3 评分输出

```json
{
  "schema_version": "grading-score-v1",
  "items": [{
    "unit_id": "<程序提供的评分单位ID>",
    "status": "scored",
    "score": 3,
    "reason": "说明实际给分、扣分依据",
    "evidence_block_ids": ["b1"],
    "comments": [{"block_ids": ["b1"], "text": "此步骤正确", "kind": "correct"}]
  }]
}
```

模型输出状态仅允许 `scored / needs_review`；needs_review 的 score 必须为 null。满分从快照读取，模型不能修改；reason 为面向老师的简明评分依据，不要求输出内部推理过程。标准答案、评分标准与学生作答分字段传输，防止混淆。

提示词规则：遵循已有评分标准；无标准允许合理评分且说明依据；不要求答案逐字一致；识别不确定、参考条件不足不猜分；只返回给定单位 ID；不生成总分；不声称看过图片。

### 6.4 调用与完整性

正常首轮一个 `grading_run` 最多一次全卷评分请求。没有任何可评分单位时不调用，直接显示待人工及原因。输入/输出预算不足时明确报错，不静默改为逐题调用；本期不做逐题费用对比模式。

保存请求摘要、完整响应、模型/渠道/提示词/协议版本、finish_reason、usage、调用耗时和费用。先判断输出是否结束，再解析和校验；即使 JSON 合法但 finish_reason 表示截断，也不能当作完整成功。

评分缓存键至少含：标准快照摘要、学生图片内容摘要及识别结果摘要、评分模型标识、渠道配置标识（不含密钥）、提示词完整摘要、协议版本和策略版本。不能只含题号、文件名或模型外的文本摘要。

重试/备用渠道每次均记 attempt，不隐藏成本。对可能已被供应商接收但本地超时的请求标记费用未知，禁止无界重试。自动重试次数及同渠道/备用渠道政策在接入时配置并验证；不得沿用现有自动回退而不计实际请求数。

## 7. 结果校验和金额/分数精度

- 严格核对全部预期 unit_id：未知、重复、缺失分别记录问题，缺失不补 0。
- 得分用精确十进制，禁止 NaN、Infinity、字符串冒充数值；范围为 0 至快照 max_score。
- 无理由、状态/分数矛盾、无效 evidence_block_id 或跨题引用进入 needs_review；不能直接展示为有效机器分。
- 越界分保留 raw_score，派生 bounded_score 建议值并告警；有效 machine_score 先为 null，人工接受或重评后再有效，避免静默修分。
- evidence 只允许引用本单位实际识别块。空白题可以无笔迹块，但必须关联覆盖证据及题目区域；无可靠步骤位置仅显示题目级标记。
- 分数合计只对叶子评分单位求和，父题汇总不重复计入；max_score 合计与标准卷一致性提前检查。
- `machine_subtotal`、`effective_subtotal`、`unscored_unit_ids`、`total_status=partial/complete` 分开。机器分被人工分替代只影响有效合计，不改机器分。
- 完整总分与人工复核状态分开；所有单位有分也不代表老师已审核。非零小数不擅自四舍五入到整数。
- 费用保留计价依据与精度，用量未知不填 0；供应商账单与本地估算不能混称。

## 8. 持久化设计（拟新增）

沿用 `jinban` schema，以开工时现有最高迁移号之后的新 Flyway 迁移创建，不回改 V1、不重建既有表。以下是逻辑表设计，实施时补完整 DDL、索引、外键、CHECK 和集成测试。

| 表 | 主要字段/职责 |
|---|---|
| `grading_submission` | id、paper_revision_id 外键、reference_snapshot JSONB/hash、可选显示姓名、status、current_run_id、revision、created_at/updated_at |
| `grading_page` | id、submission_id、upload_asset_key/hash、文件类型/尺寸、display_order、active、supersedes_page_id；保存历次上传，不覆盖 |
| `grading_run` | id、submission_id、generation、page_manifest/hash、recognition/score/prompt版本、status、阶段错误、recognition_result、raw_score_response、validated_result、创建/完成时间 |
| `grading_run_page` | run_id/page_id、reference_page_id、方向、变换/逆映射、校正图键、质量指标、匹配和配准状态；历史运行互不覆盖 |
| `grading_unit_result` | run_id、unit_id、question_revision_id、subquestion_key、max_score、识别文字/块引用、状态、raw_score、machine_score、machine_reason、机器标注；唯一(run_id,unit_id) |
| `grading_manual_revision` | id、run_id/unit_id、revision、人工分/理由、操作者上下文（本期可为本地操作员）、时间；追加记录，不覆盖机器结果 |
| `grading_attempt` | id、run_id、stage、attempt_no、provider/model/version、request摘要/请求标识、状态、耗时、usage、费用/币种/依据/未知原因、错误诊断 |

金额 numeric、分数 numeric，语义上 null=未评分，0=有效零分。人工分必须符合该单位分值范围且有原因。可通过独立 current pointer 或最新 revision 查询人工有效分，保持追加历史。

标准快照内保留正式 question_revision_id；原内容中的 q.id 可能是来源题目 ID，必须显式映射，不能混用。snapshot、page_manifest 和 model_version 为审计输入，不随当前标准卷或配置自动改变。

资产目录建议：

```text
data/grading/<submission_id>/
  uploads/<page_id>.<ext>
  runs/<run_id>/
    reference-manifest.json
    pages/<page_id>/oriented.png
    pages/<page_id>/aligned.png
    pages/<page_id>/registration.json
    ocr/raw-<attempt_id>.json
    recognition.json
    scoring/request.json
    scoring/response-<attempt_id>.json
    result.json
```

数据库管理当前业务状态；磁盘缓存不是人工结果唯一来源。原卷资产只读，必要时复制/固定依赖并校验摘要，不能因源文件变化使历史坐标和题意漂移。路径只在受控根目录内解析。

## 9. 新接口契约（拟定）

沿用 `/api` 前缀，以下均未实现；错误返回结构化问题，不把整段 JSON 当红色错误文本。

| 接口 | 行为 |
|---|---|
| `GET /grading/reference-papers/{paperRevisionId}/preflight` | 读取并检查标准卷，返回题数、满分、页面集合、资料问题和是否可开始；只读 |
| `POST /grading/submissions` | `{paper_revision_id, student_label?}`；生成快照和提交记录 |
| `POST /grading/submissions/{id}/pages` | multipart files，多图上传；校验内容/尺寸/大小，不只看后缀 |
| `POST /grading/submissions/{id}/pages/{pageId}/replacement` | 上传替换页；记录 supersedes，不覆盖旧页，带 expected_revision |
| `GET /grading/submissions` | 本地提交列表、阶段、费用摘要 |
| `GET /grading/submissions/{id}` | 当前状态、版本、页面、异常、运行和费用摘要 |
| `POST /grading/submissions/{id}/start` | 带 expected_revision、客户端幂等键；异步生成/启动运行，返回 202 和 run_id |
| `POST /grading/submissions/{id}/retry` | 明确复用阶段及 expected_run_id，生成新运行引用，所有重试可追溯 |
| `GET /grading/submissions/{id}/runs/{runId}/result` | 原机器结果、人工有效分、原因、标记和合计；支持历史运行 |
| `PUT /grading/submissions/{id}/runs/{runId}/units/{unitId}/manual-score` | `{expected_revision, score, reason}`，写追加人工修订，不更新 machine_score |
| `PUT /grading/submissions/{id}/page-mappings` | 可选补救：人工指定页对应或区域修正，仅写学生提交，含 expected_revision |

预检阻断或参数错误返回对应 4xx 和 `issues[{code, severity, stage, page_id?, unit_id?, message, action}]`；版本冲突 409；异步失败保存在运行状态中而非长期占用 HTTP 连接。

Python 内部建议新增 `/grading/process`、`/grading/runs/{runId}`、`/grading/runs/{runId}/result`，不复用快速录入 `/process` 的 payload。Java 只接收短启动确认、轮询或回调同步，不在数据库事务持锁期间等待 OCR/评分完成。内部接口仍绑定本机，不新增公共部署入口。

图片资产读取复用受控资产服务，不能把文件系统绝对路径暴露为客户端可任意读取参数。

## 10. 状态、并发与恢复

业务主状态建议：

```text
draft → queued → preparing → recognizing → grading → validating
                                                    ├→ ready
                                                    └→ needs_review
任意处理阶段 → action_required / failed / interrupted
人工处理完未评分单位 → ready（review_status 独立记录）
```

- action_required：缺页、差图、页面歧义等，给明确补救入口；不自动等同于模型失败。
- needs_review：已有可用部分结果，但作图、识别不确定或校验问题仍需人工；显示 partial 合计。
- run 不可变输入，以 generation 和 current_run_id 检查晚到结果；旧运行不能覆盖补拍后的新运行。
- 一个 submission 同时只允许一个当前活动运行；重复 start 幂等。旧 worker 需要检查版本后才能提交状态。
- 补拍失效匹配、识别、评分的相关派生产物；整卷评分输入变化后不得复用旧全卷评分。人工分保留在原 run，跨运行不得自动复制为新有效分。
- OCR 成功、评分失败时复用识别；程序重启恢复前核对状态和已完成资产。供应商是否已接收的不确定请求单独提示，防止盲目重复收费。
- 本期沿用单机可恢复任务思路，但新增阶段的状态文件和调度命名隔离。并发上限可配置，不把快速录入的“无限本地并发”直接当外部供应商允许值；不引入分布式队列作为前置。

## 11. 前端与卷面标记

建议在试卷详情增加“发起批阅”，侧栏增加“批阅任务”，保持现有快速录入和资源库入口。新页面分为提交、处理进度、结果复核三个状态。

复核建议：左侧校正整页、原图切换和 SVG 标记；右侧题目导航、只读标准内容、识别作答、AI 分/满分、理由、人工改分与异常。题目点击定位卷面。显示 AI 未复核、人工已调整等真实状态。

批注锚点优先 OCR block_id；多块跨页保留多位置，不能把两页包成一个矩形。缺少可靠步骤锚点时只给题目级标记，不在学生笔迹上伪造精确错误定位。

修改学生页框或匹配不会直接 mutate SourceViewer 的标准题目对象，应使用独立的 submission mapping 数据。未保存改分或旧 run 页面提交请求须做版本检查。

## 12. 模块落点与实施顺序

建议新增：

- Java：`cn.jinban.grading` 的 Controller、Service、Mapper、协议 DTO、费用/运行同步逻辑；快照适配器从快速录入只读获取正式数据。
- Python：`apps/ai/grading/` 下 reference、registration、recognition、scoring、validation、pipeline、schemas；识别供应商适配独立文件。复用 diagnostics/channels 的通用能力，不复制包含隐式回退的业务状态。
- Vue：`GradingUpload.vue`、`GradingProgress.vue`、`GradingReview.vue`、`GradingPageViewer.vue` 与独立类型；现有 App 只做入口接线和必要抽取。
- 新数据库迁移、新评分/OCR Schema 与接口契约，以及独立验收记录。

按依赖推进，每阶段保留真实证据：

| 里程碑 | 内容 | 通过条件 |
|---|---|---|
| M0 样本及识别验证 | 正确标准卷、真实手写样本、识别候选测评、费用能力 | 公式/步骤/位置可用，限制明确；若无可用候选先解决识别，不伪造成功 |
| M1 标准卷及页面 | 快照、单份上传、转正、页匹配、质量与配准 | 倒置/乱序/缺页/错卷/差图用真实和扰动样本可验证 |
| M2 作答归并 | 逐题/小问匹配、跨页和空白状态 | 不串题，不用标准答案补写学生内容 |
| M3 一次文字评分 | 文本准备、协议、校验、费用及恢复 | 正常首轮单次请求，无图片输入，结果覆盖和合计可靠 |
| M4 复核及回归 | 标记、人工修订、补拍版本隔离、快速录入回归 | 机器分/人工分均保留，刷新恢复及旧结果保护通过 |

## 13. 测试与交付证据

### 13.1 契约和逻辑测试

- 正式题目 ID 与来源 ID 映射、引用分值优先级、无效分值、单文档多卷页面归属。
- 坐标往返、旋转 180°/90°、上下界、跨栏及跨页块顺序；图形语义缺失和作图分类。
- handwritten/printed/blank/unreadable 不混用；缺页不产生零分。
- 评分漏项/重复/未知 ID、负分/超分/无理由、合法 JSON 但截断、父子题重复加总。
- 无图片附件/图片节点/取图工具的评分请求审查；全卷首轮调用次数断言。
- 幂等启动、乐观锁、补拍旧 run 晚到、缓存失效、人工改分不改机器分、恢复不重复计费。

### 13.2 真实样本验收

使用需求文档中最终九年级 PDF 和对应扫描照片先验证版面；再用真实手写样本覆盖正确、错误、空白、删改、复杂公式、跨页、姓名及作图/文字混合题。

固定人工检查基准，报告识别错误、漏步骤、串题、评分差异、待人工原因、各阶段耗时、请求次数和完整费用；不宣称只有空白扫描照片就已验证手写批阅。

对每项需求 A01～A16 提供通过/失败/阻断证据。可以使用隔离的供应商模拟验证异常，但模拟不得替代真实 OCR/评分效果或费用证据。

### 13.3 运行与回归约束

开工时按变更范围运行 Python 测试、Java 集成测试、TypeScript/前端构建及必要浏览器验证；不为本轮文档产出运行构建或收费识别。

遵循根目录 AGENTS.md：日常启动用 `scripts\dev.cmd`；Vue 正常 HMR，无需为普通界面修改重启；Python reload 前先确认无活动识别任务；Java 修改后需 Ctrl+C 再 `scripts\dev.cmd api`，不宣称 Java 已自动热更新。不结束无关进程，不泄露 .env。

实施交付时提供适用的 CMD 命令，例如：

```cmd
cd /d "C:\Users\LJL\Documents\ChatGPT\只会教学平台开发"
scripts\dev.cmd
```

本轮仅创建两份 Markdown 文档，无服务需要重启，上述命令为后续实施说明，不代表已经启动或部署批阅。

## 14. 尚未确定及风险

| 项目 | 当前结论/处理 |
|---|---|
| 手写识别供应商/计费/坐标能力 | 未验证，是 M0 的关键依赖；不得用已有印刷 OCR 结论替代 |
| 题干图片的文字化条件 | 快速录入尚不保证完整；条件不足的题待核对，不能偷偷调用图片评分 |
| 作答区域 | 当前已有候选生成改进，但历史稿和图旁/小问/续页覆盖需验证；整页识别避免只依赖候选框 |
| 小问满分 | 现有 subquestions 是宽松字典，未保证逐小问分值；无法拆分时不自动批混合作图题部分 |
| 费用和速度 | 暂无单卷阈值；记录真实数据后再决定指标与优化，不能假定一次请求一定更便宜 |
| 配准指标与供应商限制 | 技术实测项，版本化配置；低质量图宁愿重拍，不强修 |
| 结果布局和步骤级痕迹 | 当前为工程建议；先保证题目级正确定位，不冒充已确认精确到每个步骤的产品承诺 |
| 现有系统持续迭代 | 实施前复核源码及依赖，避免覆盖其他任务的改动；只扩展必要接口和通用模块 |

第一阶段完成条件：真实单份多页手写卷可以通过识别、纯文字全卷评分、校验与人工复核闭环；差图、识别失败、作图待人工和部分总分均显式呈现；费用可追踪，原有快速录入回归通过。
