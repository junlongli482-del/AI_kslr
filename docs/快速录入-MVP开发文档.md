# 快速录入｜MVP开发文档

> 实现后补充（2026-10-15）：本文保留为设计基线。当前代码的规则、完整提示词、阶段输入输出、数据处理与限制，见[《MVP详细设计与实现说明》](快速录入-MVP详细设计与实现说明.md)及[提示词快照](contracts/quick-entry/提示词快照.md)。

版本：v0.1｜日期：2026-10-15｜状态：工程实施基线；技术选型已确定，接口供应商信息待联调核实。

对应需求：[快速录入-MVP需求文档](快速录入-MVP需求文档.md)，验收编号Q01—Q14。本文为新功能增量，不覆盖已有阶段01账号与学校管理需求。

## 1. 技术选型与边界

沿用工作区《阶段01-开发文档》的既定技术路线，新增独立AI处理模块；不为验证功能重建完整平台，也不把数据加工脚本当成最终应用。

| 层次 | 选型 | 职责 |
|---|---|---|
| 网页 | Vue 3.5、TypeScript strict、Vite、pnpm、Node.js 22 LTS | 上传、进度、审核、题库与试卷库 |
| 组件与状态 | Element Plus、Pinia、Vue Router、Axios | 通用界面、路由、状态与请求 |
| 原卷查看 | PDF.js；图片统一页面视图；SVG叠加题框 | 物理页展示、缩放、区域交互 |
| 内容编辑 | Tiptap／ProseMirror，自定义题目节点 | 渲染及编辑结构化题目，不直接编辑Markdown或JSON |
| 公式 | MathLive可视化输入、KaTeX展示、LaTeX存储 | 可视化／源码双模式及异常保留 |
| 业务API | Java 21、Spring Boot 3.5.x、Spring Security | 上传元信息、任务调度、审核稿、题库、试卷库、入库事务 |
| 持久层 | PostgreSQL 17、MyBatis-Plus 3.5.x、Flyway | 关系数据、JSONB内容和版本管理 |
| AI处理服务 | Python 3.12、uv、FastAPI、Pydantic v2、httpx | MinerU适配、归一化、模型编排、协议校验、裁图 |
| PDF／图像 | pypdf、pypdfium2、Pillow | PDF元信息、页面渲染、区域裁图；禁止按样本写固定题号坐标 |
| Word转换 | LibreOffice headless，独立转换适配器 | DOCX／DOC转PDF；失败有明确回退建议 |
| 文件资产 | MVP本地磁盘＋Storage接口 | 原文件、原包、页面图、插图、裁图、处理清单；以后可接对象存储 |
| 运行 | Docker Compose v2；Java和Vue可本机开发 | PostgreSQL、业务API、AI服务和网页，不引入消息队列或Kubernetes |
| 契约与验证 | OpenAPI 3.1、JSON Schema、JUnit、pytest、Vitest、Playwright | 前后端及AI契约、关键单元测试、浏览器闭环验证 |

依赖在开工时锁定兼容补丁版本，提交 Maven Wrapper、pom、uv.lock、pnpm-lock.yaml，不使用浮动latest。编辑器实际支持范围用样本验证，发现兼容问题在ADR记录替代原因。

工作区目前只有文档，没有实际应用工程；上述组件尚未安装验证。MVP采用单操作员本地验证配置，默认只绑定本机；未来上线或多校使用必须接入阶段01的认证与学校隔离，不能把本地模式暴露到公网。

## 2. 工程结构

```text
apps/
  api/                         Java业务API
    .../quickentry/            任务、文件引用、阶段调度、草稿
    .../questionbank/          题目、属性、版本、来源
    .../paperbank/             试卷、题目引用、原卷模板
    .../catalog/               目录、映射、标签定义
  ai/                          Python处理服务
    src/quick_entry/
      providers/mineru/        服务适配、上传、轮询、下载
      providers/llm/           低价／高价渠道及能力探测
      normalization/           原包解析、块引用、图片布局
      pipeline/                分卷、分题、结构化、答案匹配、标签
      contracts/               Pydantic模型及导出的JSON Schema
      regions/                 坐标转换、裁图、多区域拼接
      storage/                 任务工作目录、阶段清单、缓存
    tests/
  web/
    src/features/quick-entry/  上传、任务、审核
    src/features/questionbank/
    src/features/paperbank/
    src/components/question/   内容渲染、编辑、公式、图片布局
    src/components/source/     PDF查看器、题框、坐标变换
docs/
  快速录入-MVP需求文档.md
  快速录入-MVP开发文档.md
  contracts/quick-entry/        AI协议与样例、版本记录
  03-接口契约/                  业务OpenAPI
  adr/                         实施决策
  handoff/quick-entry/          实测报告、截图、已知限制
deploy/
scripts/
data/                          本地运行资产，排除版本控制
```

Vue与Java处理正式业务；Python处理识别和AI加工，不直接写题库、试卷库业务表。JSON Schema为AI结构协议单一来源，前端类型与Java接收结构随契约同步，避免三端各自猜字段。

## 3. 处理架构

```text
Vue上传与任务页
  → Java：创建任务、保存文件元信息与任务阶段
  → Python：文件准备、MinerU调用、原包下载
  → Python：中间数据、AI分组／编排／答案／标签、坐标与裁图
  → Java：接收校验结果，创建独立审核稿
  → Vue：原卷与题目联动渲染、编辑及自动保存
  → Java：校验审核版本并事务入库
  → Vue：从题库／试卷库重新读取并展示
```

上传页面不等待长请求结束。Java持久化任务和阶段，后台工作线程执行阶段调用，页面轮询任务快照；可后续接SSE，不以SSE作为MVP前提。

首版采用数据库任务表与有限并发工作线程，不引入消息队列。Java拥有任务状态；Python在工作目录保存阶段manifest及外部任务ID。识别和编排进度来自实际阶段，不生成虚假百分比。

## 4. 文件、MinerU及资产

### 4.1 输入与格式准备

题目与答案文件都使用File记录，role为question／answer／mixed。上传保留文件哈希、原名、MIME、尺寸／页数、大小、文件用途和顺序。原始文件不覆盖；转换PDF为新的派生资产，关联原文件及转换版本。

完整PDF交给MinerU一次处理；不按页循环提交。多文件可批次提交，但每个文件保持独立身份。多张图片按实际接口支持采取批量识别或合并PDF策略，记录图片到输出页的映射，不伪造接口能力。

文档转换在限时独立进程中执行，每任务独立目录；失败返回具体原因。大文件、页数、超时等限制为可配置值，在验证实际服务限制后写入环境说明，不猜测供应商限额。

### 4.2 MinerU适配器

定义submit、query、download接口及能力描述；先核实密钥对应域名、鉴权方式、上传方式、模型版本、结果结构及额度。官方公开文档参考 https://mineru.net/apiManage/docs ，该页面可访问不代表用户密钥属于该服务或接口已联调。

保存external_task_id、外部状态、提交时间、请求配置指纹及结果包哈希。上传原文件、轮询和下载分开重试。外部任务ID存在时先查询，不盲目重新提交付费任务。

下载原包后完整留档，受控解包，校验ZIP路径在任务目录内，禁止路径穿越。识别Markdown、内容列表／布局JSON、图片等实际产物，不假定所有服务版本字段相同。适配器将差异转换为统一中间协议。

## 5. 中间数据协议

### 5.1 页面与内容块

```text
DocumentManifest
  document_id、source_file_id、role、sha256、converter_version
  pages[]：page_index（从0起）、width_pt、height_pt、rotation
           render_width_px、render_height_px、printed_page_labels[]
  blocks[]：block_id、page_index、kind、reading_order、bbox
            text／latex／table／asset_id、source_refs[]、layout
  assets[]：asset_id、mime、width_px、height_px、storage_key、sha256
  sections[]：候选卷名／答案分组、block_ids、状态
  parser_version、warnings[]
```

block_id在同一原包和解析版本下确定性生成；原始JSON字段路径保存在source_refs，便于回溯。文本、图片、表格、标题、公式都有块标识。

Markdown为内容主线，JSON负责位置、块类型与资产关系；不能只使用Markdown顺序推测坐标。Markdown与布局块无法确定对齐时记录缺口，使用对应局部原图补判，不把位置猜测当事实。

布局保留flow_group、row_group、row_order、relative_width、caption_refs、option_label等必要信息；部分信息来自原包，部分通过几何关系推断，分别记录来源。

### 5.2 坐标约定

统一bbox=[x0,y0,x1,y1]，原点在应用固定旋转后的页面左上，x向右、y向下，归一化到[0,1]，并带document_id与page_index。保存原始单位、原始坐标及转换矩阵以便核查。

供应商可能返回点、像素或0—1000坐标，必须根据返回协议和页面实测转换，不靠猜测。渲染、裁图与前端使用同一个规范页面方向，处理CropBox、旋转与缩放。

像素裁图：左上向下取整、右下向上取整，裁剪到边界内；视觉边距为配置项，保留原始逻辑框。SVG拖动先逆变换到页面坐标再归一化，不能直接保存屏幕像素。

printed_page_labels仅供检索和展示。样本一个PDF物理页上的左右两个印刷页不拆成两次OCR；必要时设置逻辑版面分区，题目区域仍引用同一物理页。

## 6. AI编排策略

### 6.1 按任务阶段控制上下文

1. **文档概览与分组**：用标题、题号分布、阅读顺序和必要缩略图识别试卷与答案分组，推断学科等上下文。
2. **题目边界规划**：输入有编号的精简内容块与布局，输出题目／小问对块的引用和顺序，识别跨栏跨页延续。
3. **题目结构化**：按题或题组输入必要Markdown、块引用与图片，输出正文、选项、小问和资源布局。
4. **答案条目提取与匹配**：先分答案所属卷，再匹配题号／小问与内容；保存匹配证据与未用条目。
5. **属性与标签**：生成题型、难度等；正式目录存在时分层检索知识点并映射章节，否则跳过目录绑定。
6. **可选补缺**：仅在开关启用时生成缺失答案解析，不覆盖提取结果。
7. **结构与区域校验**：系统计算区域、解析引用、检查资产和标签，再形成审核稿。

以上是内部阶段，用户不需要逐步点击。不要把每道题每个标签都拆成一次模型调用：可按token预算批处理，在保留上下文的前提下控制成本。

### 6.2 上下文与泛化

输入是压缩后的结构、候选目录和必要原图，绝不把全部原始JSON或几万个知识点全量塞给模型。设置token预算、题组分批及跨批衔接摘要；跨页题边界需能引用相邻块，不能机械按页截断。

分题和关联由模型做语义判断；坐标单位换算、几何裁图、ID有效性检查和协议校验由确定性代码处理。禁止为当前两份卷子写固定题号／横带规则当成通用识别。

优先让模型返回block_ids，由系统合成每页每栏的多区域；不是所有块无条件取总包围框。语义决定哪些块同题，几何算法处理相邻、同栏块。布局块过粗、切题边界不足时，以局部页面图像细化区域；只支持文本的渠道将该项标为需要视觉能力或人工修正，不能假定文本模型可看图。

### 6.3 两渠道适配与降级

配置low_cost和stable两套独立base_url、model_id、api_key和能力描述。默认低价优先、高价回退，界面提供稳定优先和指定渠道；首批对比实测后可调整默认。

不根据“GPT6.1s”昵称猜模型ID或API路径。首次联调记录是否支持聊天／其他接口、图片输入、JSON Schema结构化输出、上下文及超时。兼容接口不支持Schema时使用JSON输出＋本地校验，不假装具备严格输出保证。

429、超时、5xx、连接失败进行有限指数退避与渠道回退；鉴权错误停止该渠道并提示；结构校验失败可定向修复一次，再换渠道或保留失败结果。设置每阶段最大调用次数及任务预算，不无限重试。

回退保持输入快照、协议版本和阶段幂等键；记录实际渠道、模型、尝试次数、耗时与可取得的usage。未知费用不显示为0。

### 6.4 输入信任边界

原卷、答案及OCR文本均为资料，不是执行指令。模型系统提示固定要求仅提取与编排，不执行资料中的外部命令、接口调用或提示注入。模型输出按不可信数据校验，不直接执行HTML、代码或任意URL。

## 7. 最终JSON协议

在实际实现中补全严格JSON Schema，禁止additionalProperties的核心结构与允许扩展的属性容器分开。以下是字段形状说明，不是可直接发送的完整JSON示例。

```text
QuickEntryResult
  schema_version、task_id、run_id、input_manifest_hash
  papers[]
    paper_id、title、source_document_ids[]、section_ids[]
    metadata、question_refs[]（question_id、顺序、卷内分值、题组）
  questions[]
    question_id、parent_id、source_number、block_refs[]
    content（版本化的题目内容AST）
    options[]、subquestions[]、shared_material_refs[]
    regions[]（region_id、document_id、page_index、bbox、purpose、order）
    attributes{}、extension_attributes[]
    answer、analysis、scoring_criteria
    field_provenance{}、issues[]、review_status
  answer_entries[]（分组、来源块、答案／解析内容、匹配候选与采用状态）
  unmatched_answer_entry_ids[]
  assets[]、issues[]、processing_metadata
```

模型内question_id可为临时稳定ID，业务入库生成正式ID并保存映射，不允许模型指定数据库主键或学校权限。未识别值为null或显式状态，不以空字符串和“未知”混用。

### 7.1 内容AST与编辑器

定义paragraph、text、inline_math、display_math、image、image_row、table、list等白名单节点及受限样式。题干、答案、解析使用同一内容协议；选项与小问是独立结构，不把所有内容塞进一段HTML。

前端通过适配层把内容AST映射为ProseMirror文档，保存时映射回同一AST，防止编辑器专有JSON侵入业务协议。只允许资产ID引用，渲染与编辑均不依赖外部图片地址。

MathLive输出LaTeX，KaTeX统一展示；保留原始latex、编辑后latex与渲染错误。不支持的语法提供源码回退，禁止隐式清空。表格单元格和选项中的公式也走同一节点处理。

### 7.2 字段来源及扩展

关键字段保存value、source_type、source_refs、review_state；不同字段可有不同来源。AI推断难度不等于原卷声明难度，AI生成答案不等于原答案。

扩展属性引用definition_id及definition_version，值类型由目录定义验证；保存catalog_version、prompt_version、pipeline_version、model及run_id。新增属性不强制重跑OCR。

## 8. 题库与试卷库数据模型

| 实体 | 主要职责 |
|---|---|
| qe_task、qe_task_file | 任务、模式、文件角色及顺序、生成选项、任务上下文 |
| qe_stage_run | 阶段状态、尝试、租约、外部任务ID、输入输出哈希、错误与成本信息 |
| qe_artifact | 原包、中间稿、AI稿、manifest位置与哈希 |
| qe_review_draft | 人工审核稿、revision、基于哪个AI结果、自动保存时间 |
| asset | 文件资产、尺寸、来源、存储键及哈希 |
| question、question_revision | 题目逻辑身份、不可变内容版本、属性、审核状态 |
| question_source | 题目来源、文档块、原题号、区域引用；允许多来源，不自动合并 |
| paper、paper_revision | 试卷逻辑身份与版本、来源及上下文 |
| paper_question | 引用question_revision、顺序、题组、卷内分值及评分覆盖 |
| source_template、source_region | 教辅原卷模板、物理页、题目关联、多区域与审核状态 |
| answer_entry、answer_match | 答案分组、内容、采用／未用状态、匹配证据及来源 |
| attribute_definition、catalog、catalog_mapping | 扩展属性、知识点及章节目录、版本与映射 |

MVP固定核心筛选字段关系化，题目内容、扩展属性和处理结果可用JSONB，不把整库只有一个JSON文件作为入库完成。

尚无平台学校数据时使用明确的本地workspace上下文，不伪造真实学校ID。未来资源权限由Java统一执行；AI不能据文件内容决定资源归属。

审核入库在一个业务事务中创建题目版本、可选试卷版本及模板关联；提交幂等键为task_id＋review_revision，重复提交返回同一结果。文件写入先生成可验证资产，再提交引用，失败后可清理孤立资产，不能出现数据库引用不存在的图片。

已审核稿后续编辑产生新版本；不覆盖历史试卷引用。去重仅提示候选，不默认把不同来源、不同学校或不同版本合成同一题目。

## 9. 接口契约

实际实现前产出OpenAPI及错误响应；以下路径作为本版约定草案，实施可在契约中细化。

| 接口 | 功能 |
|---|---|
| POST /api/quick-entry/tasks | 创建任务、模式与生成开关 |
| POST /api/quick-entry/tasks/{id}/files | 上传一个或多个题目／答案文件 |
| PATCH /api/quick-entry/tasks/{id}/files | 调整用途、排序与文件分组 |
| POST /api/quick-entry/tasks/{id}/start | 幂等启动 |
| GET /api/quick-entry/tasks/{id} | 阶段、错误、产物摘要及能力缺口 |
| POST /api/quick-entry/tasks/{id}/retry | 从指定可恢复阶段重试或切换渠道 |
| GET /api/quick-entry/tasks/{id}/review | 原卷manifest、审核稿、问题与revision |
| PUT /api/quick-entry/tasks/{id}/review | 提交渲染编辑后的结构稿，携带expected_revision |
| POST /api/quick-entry/tasks/{id}/validate | 返回结构错误、告警及定位 |
| POST /api/quick-entry/tasks/{id}/commit | 指定revision及幂等键，事务入库 |
| GET /api/assets/{id}/content | 受控读取原文件／插图／裁图，支持PDF所需范围请求 |
| GET /api/questionbank/questions | 分页、属性筛选、检索 |
| GET /api/questionbank/questions/{id} | 指定版本的题目及来源 |
| GET /api/paperbank/papers | 分页与基本筛选 |
| GET /api/paperbank/papers/{id} | 试卷、题目版本引用及模板 |
| GET /api/catalogs、/api/attribute-definitions | 目录及扩展属性能力，支持未配置状态 |

Python仅提供内部阶段执行／状态／产物接口，使用task_id、run_id、stage及输入manifest引用；端口不直接对浏览器暴露。Java与Python使用内部凭证，文件通过受控存储键或服务接口传递，不接受任意系统路径。

错误包含code、message、stage、retryable、issues[]及trace_id；issue可定位question_id、document_id、page_index、block_id和field_path。前端展示可行动提示，不把所有错误压成“处理失败”。

## 10. 前端实现要点

1. PDF.js视口与SVG使用一致宽高和页面变换，题框不随缩放漂移；拖框操作保存归一化坐标。
2. 选中题目使用结构ID联动，不凭题号查找；同号题和多个试卷可共存。
3. 题目编辑、属性、图片与区域引用共享审核稿；合并／拆分时同步更新所有关联及答案匹配，记录撤销历史。
4. 自动保存采用防抖和revision乐观锁；409冲突提示处理，不用最后一次写入静默覆盖。
5. 入库前等待未提交编辑与公式弹窗提交；成功后重新从库读取，验证不是仅靠浏览器内存显示。
6. 答案对照切换到来源文件及区域，展示未采用条目；答案来源坐标用于定位，不要求建立批阅模板。
7. 告警可跳到具体题目及字段；区分结构阻断、待人工确认和目录未配置。
8. HTML表格与富文本只接受白名单结构，拒绝脚本和危险URL，LaTeX渲染不启用任意受信任指令。

## 11. 任务恢复、成本与配置

阶段幂等键由文件哈希、阶段参数、依赖产物哈希和处理版本构成。Java租约避免同阶段并发执行；超时后先查询Python manifest及外部任务，不在未知结果时直接重复付费调用。

Python阶段开始写running，成功后原子提交产物与completed manifest；失败记录可恢复状态。进程异常导致状态不明时，Java对账后恢复。AI调用超时可能已经计费，重试记录此不确定性，不承诺第三方绝对只调用一次。

```text
MINERU_BASE_URL
MINERU_API_KEY
LLM_LOW_BASE_URL
LLM_LOW_MODEL
LLM_LOW_API_KEY
LLM_STABLE_BASE_URL
LLM_STABLE_MODEL
LLM_STABLE_API_KEY
LLM_CHANNEL_POLICY
DATABASE_URL
QUICK_ENTRY_DATA_DIR
QUICK_ENTRY_MAX_CONCURRENCY
QUICK_ENTRY_STAGE_TIMEOUT_SECONDS
QUICK_ENTRY_MAX_ATTEMPTS
QUICK_ENTRY_TASK_TOKEN_BUDGET
```

真实值放本地受忽略环境文件或环境变量，.env.example只含变量名和无秘密示例。.env、data、原包、真实样本和调试输出排除版本控制；文件路径清单可记录但不打包用户资料。

日志只记录任务ID、阶段、错误类型和耗时，屏蔽Authorization、密钥、带签名下载URL及完整请求体。按任务保留受控调试产物，方便质量排查。

## 12. 开发顺序与证据积累

| 工作包 | 交付 | 通过后再推进的判据 |
|---|---|---|
| D01 样本与协议 | 样本manifest、全页检查清单、中间数据及AI协议、基础工程 | 能描述物理页、区域和题目关系，无硬编码样本坐标 |
| D02 MinerU真实适配 | 完整PDF提交、状态轮询、原包下载、保存与恢复 | 两份卷及答案真实取得产物；不能只做模拟调用 |
| D03 数据整理与切题 | 块映射、资产、跨栏跨页分题、多区域裁图 | 叠框及裁图可查，真实记录误切与漏题 |
| D04 AI结构化与匹配 | 题目JSON、属性、混合答案匹配、两渠道回退 | Schema通过、答案分卷正确、来源保留、未配条目可查 |
| D05 审核工作台 | 原卷联动、内容与公式编辑、布局、题框、修复操作、自动保存 | 实际浏览器修正错误并刷新恢复；不编辑JSON |
| D06 题库试卷库 | 事务入库、列表、详情、版本与模板 | 三模式产物正确，从数据库重读后可渲染 |
| D07 补齐与验收 | 图片／Word、答案多形态、故障恢复、运行说明与报告 | Q01—Q14逐项有真实证据；缺项如实列出 |

D03—D05尽早做一题贯穿原卷、AI结果、裁图与编辑的纵向闭环，验证不可逆信息丢失后再扩大批次；不能等所有后端功能写完才第一次看渲染效果。

知识点目录缺失时D04跳过正式知识点绑定，保留接口；不为了完成字段而临时抓取来源不明的完整知识点库。后续接目录时单独验证分层筛选与教材映射。

## 13. 验证与交付

### 13.1 必需验证

- 中间协议与坐标：供应商坐标转换、旋转页、跨栏多区域、精确裁图，检查内容截断及邻题混入。
- AI协议：非法JSON、无效块ID、缺图、越界、重复题号、嵌套小问、目录外标签、输入资料提示注入。
- 答案：共用答案的期中／期末分组、无关章节、重复题号、略／图略、多个候选、生成开关及已有答案保护。
- 交互：MathLive与LaTeX往返、图片同行布局、表格公式、题框缩放、合并拆分、刷新恢复、保存冲突。
- 持久化：提交幂等、事务回滚、旧版本引用、仅题目不建卷、普通卷不启用模板、教辅模板关联完整。
- 外部失败：超时、429、5xx、密钥错误、下载失败、模型结构异常、低价渠道失败后高价恢复，错误不丢人工稿。

使用单元／契约测试覆盖计算和状态边界；用真实PDF跑集成验证；浏览器走一次从上传到库内重读的闭环。不要写仅镜像实现的无意义测试，也不能只凭截图声称功能通过。

### 13.2 基线报告

对全部样本页逐题建立人工基准：试卷分组、题号、小问、内容块、多区域、插图布局、答案及来源。记录机器初稿与人工修正后结果，分别统计漏题、串题、截断、图文错误、答案错配／未配和修正操作量。

关键用例至少包括：期中首屏第6题跨栏、期末首屏第1题同行图形选项、第7题双图、答案页不同试卷同号题、无关章节以及图略。遍历后补充真实跨页题，不以已有参考文档描述代替本次确认。

可额外从PDF构造图片、合并题目和答案，验证其他输入形态，但标注为衍生样本；真实Word和手机拍照尚缺时列为未验证范围。

### 13.3 交付物

可启动代码、锁文件、迁移、环境示例、启动说明、OpenAPI、中间数据及AI JSON Schema、样本运行manifest、外部服务实测信息、前端验收截图、质量基线及剩余问题清单。

当前仅完成规划与本地样本初检；未发生MinerU／GPT真实调用，也没有应用代码与自动准确率证据。凭证接入待补Base URL、模型ID及服务协议，缺知识点目录可按未配置处理。
