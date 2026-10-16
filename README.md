# 金版 · 快速录入工作台

本地单操作员MVP。识别真实资料，AI生成结构化题目，原卷对照审核、公式可视化编辑、区域切割并保存至题库和试卷库。

## 启动

开发环境：Java 21、Node.js 22、pnpm 11.25、Python 3.12、Docker。已有配置和构建时：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/start.ps1
```

打开 http://127.0.0.1:5173 。Java API为8090，内部AI服务为8091，PostgreSQL为55436。所有应用仅绑定本机。

首次安装：

```powershell
Copy-Item .env.example .env
# 编辑.env，填入MinerU、两个GPT渠道密钥；真实值不提交。
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r apps/ai/requirements.lock.txt
docker compose -f deploy/compose.yaml up -d
Set-Location apps/web
pnpm install --frozen-lockfile
Set-Location ../..
powershell -ExecutionPolicy Bypass -File scripts/start.ps1 -Build
```

### 日常开发：从 CMD 启动

停止同端口的旧服务、确认 Docker 数据库已运行后，在 CMD 中执行：

```cmd
cd /d "C:\Users\LJL\Documents\ChatGPT\只会教学平台开发"
scripts\dev.cmd
```

它打开三个有日志的 CMD 窗口：Vue 使用 Vite HMR，Python 使用 Uvicorn reload，Java 使用 `spring-boot:run` 从源码编译并运行，**不打包 jar、不跑完整测试**。

- 改 Vue / CSS：通常自动更新，无需重启前端。前端固定5173，端口占用时明确报错，不静默切换到另一个端口。
- 改 Python：自动重载。**不要在实际识别任务执行中重载处理服务**；线程任务会被中断，完成的缓存保留，可在页面恢复任务。
- 改 Java：当前没有 DevTools 和持续编译器，需要在 Java 窗口 Ctrl+C 后执行 `scripts\dev.cmd api`。无需 package，但 Java 源码仍需编译。
- 改 `.env`：重启读取该配置的 Python / Java 服务；不是文件修改后所有进程都立即生效。

也可在单个 CMD 窗口按需运行 `scripts\dev.cmd web`、`scripts\dev.cmd ai`、`scripts\dev.cmd api`。关闭时在各窗口 Ctrl+C；若 CMD 询问是否终止批处理，输入 Y。启动前数据库若未运行，已有容器用 `docker start quick-entry-postgres`；首次用 `docker compose -f deploy/compose.yaml up -d`。

`scripts/start.ps1 -Build`保留给需要jar产物的交付验证；生产构建、完整测试不作为日常启动前置步骤。测试和 `pnpm build` 仍在相关变更的验收阶段运行，它们不等于启动开发服务器。

仓库内 Maven Wrapper 首次需联网下载Maven与依赖。当前环境已有成功构建产物。Word转换使用本机LibreOffice，可通过SOFFICE_PATH设置执行文件路径。

## 使用

1. 新建录入，选择教辅／普通整卷／仅题目。
2. 上传题目，可另传答案；答案在原卷中时无需重复上传。
3. 选择是否为缺失内容生成答案解析，默认关闭。
4. 等待MinerU与AI处理；可离开页面，任务保存到数据库。
5. 点击对照审核：左侧原卷拖框，中间选题，右侧直接编辑题目、公式、答案与标签。
6. 确认题目，规则检查后审核入库；从题库／试卷库重新查看保存结果。

生成稿保留来源；知识点目录尚未配置，不伪造正式知识点。教辅保存原卷区域模板，但学生扫描配准和实际批阅不在本版范围。

## 配置

`.env.example`列出接口和渠道配置；Python加载根目录`.env`。Java启动脚本设置数据目录；数据库默认值与Compose一致。变更数据库口令需同时设置Java的DB_PASSWORD。

真实试卷、识别原包、AI缓存、裁图与日志保存在`data/`，不纳入版本控制。用户提供的源文件保持原位，不修改原文件。示范任务复用已经完成的真实MinerU结果，避免重复识别费用。

## 验证

```powershell
.venv/Scripts/python.exe -m pytest apps/ai/tests -q
apps/api/mvnw.cmd -f apps/api/pom.xml test
Set-Location apps/web
pnpm build
Set-Location ../..
node scripts/browser-check.mjs
```

Java集成测试使用真实本地PostgreSQL并回滚测试事务；AI验证接口在该测试中隔离，不替代真实服务样本联调。浏览器检查需安装Playwright Chromium，可通过`pnpm exec playwright install chromium`安装。

详细设计见`docs/快速录入-MVP需求文档.md`和`docs/快速录入-MVP开发文档.md`；实施记录与验收证据在`docs/handoff/quick-entry/`。未验证能力须以最终验收报告为准。

## 本次交付

实际结果、逐题结构清单、测试证据与未接入范围详见 `docs/handoff/quick-entry/验收报告.md`；实现相对设计基线的差异见 `IMPLEMENTATION-NOTES.md`。真实任务已存入题库与试卷库，全部仍待人工最终核对。

## 规则与实现详解

[快速录入 MVP 详细设计与实现说明](docs/快速录入-MVP详细设计与实现说明.md)说明当前代码的输入输出、MinerU 数据处理、题框算法、答案匹配、标签、编辑与版本逻辑；[完整提示词快照](docs/contracts/quick-entry/提示词快照.md)逐字列出实际运行指令。原开发文档保留为设计基线，当前差异和未实现边界以详细说明为准。
