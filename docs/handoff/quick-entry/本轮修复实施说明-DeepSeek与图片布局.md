# 快速录入本轮修复实施说明

## 范围

本轮针对 MinerU 识别后的图片布局、题框、文科作答区、资产引用、长耗时模型调用、多个模型对比、结构化入库错误和 DeepSeek 接入完成实现。

## 模型渠道

- DeepSeek 使用官方 OpenAI 兼容接口，基础地址为 `https://api.deepseek.com`，模型名为 `deepseek-flash`（对应 DeepSeek-V4.1-Flash）。密钥只从本机 `.env` 读取，不写入代码、日志和响应。
- 模型渠道策略默认为 `compare`：LOW、STABLE、DEEPSEEK 并发执行，分别保存候选结果、耗时、token 用量和估算成本，审核页可以切换候选结果。
- 读取超时默认 1800 秒，连接超时默认 25 秒。供应商网关返回 524 时仍会记录为供应商上游超时，并保留已完成阶段以便重试复用。
- DeepSeek 成本按输入/输出 token 和北京时间峰谷价格估算，结果标记为 estimated；价格变更以供应商账单为准。

## 图片数据处理

MinerU 图片信息先进入统一布局层，保留原始页码、bbox、像素尺寸、文档 ID、同行关系、caption 和布局来源。AI 编排结果中的 `image_layout` 是显示和编辑的唯一参考：

```json
{
  "url": "/api/assets?...",
  "page_index": 1,
  "bbox": [0.56, 0.55, 0.64, 0.63],
  "width_px": 235,
  "height_px": 159,
  "render_width_pct": 17.217,
  "caption": ["甲"],
  "layout_source": "original_column"
}
```

图片不再用题目区域宽度强制设为 100%。选择题图片先按选项列布局，再使用图片自身的参考宽度；左右相邻、间隙很小且属于同一题的区域会合并。图注保存在 `image_layout.caption`，编辑器从布局或 Markdown alt 回填，前端显示为图注。

资产校正只在唯一候选匹配时执行，支持历史目录缺失、文件名轻微差异等情况；无法唯一匹配的资产保留明确错误，不静默替换。

## 题框与作答区

题框重建使用同题 block 聚合和页内几何关系。文科作答区除“主观/解答/证明/计算/作图”外，增加材料分析、简答、综合探究、书面作答等关键词；入库前会区分题目内容区域和作答区域。审核页支持单题重建题框与作答区。

## 编辑器行为

- 图片支持粘贴截图、拖拽上传、选择文件上传。
- 选中图片后可用滑块或右下角手柄调整宽度；手动宽度保存为 `manual_width_pct`，重新打开仍保持；“恢复参考尺寸”回到布局计算值。
- 公式原始内容保留 LaTeX，页面用 KaTeX 渲染；编辑器同时提供 MathLive、模板和 LaTeX 源码入口。
- 编辑器回退路径也会生成图片节点，补全布局宽度和图注，不依赖已存在的 `editor_documents`。

## 错误与入库

后端返回 `code`、题号、字段、错误级别、原因和处理建议，前端以逐条可读列表展示。图片资产错误会指出具体题号和字段；重复引用会去重，避免同一问题显示多次。Java 入库前保存审核稿历史快照。

## 验证证据

- Python：`37 passed`。
- Vue TypeScript：`vue-tsc --noEmit` 通过。
- 浏览器隔离验收：图片尺寸、手动缩放持久化、选项图片、结构化错误、图注、移动端布局全部通过，无 page error。
- DeepSeek 官方接口已完成真实连通性验证，返回模型 `deepseek-flash` 和 JSON 响应。
- 物理、道法样本的资产修复、左右区域合并、图注保留、文科作答区已通过隔离 fixture 验证。

## 启动

代码修改后需要重启后端服务，Vite 前端继续热更新：

```cmd
cd /d "C:\Users\LJL\Documents\ChatGPT\只会教学平台开发"
scripts\dev.cmd ai
scripts\dev.cmd api
```

若前端未运行：

```cmd
scripts\dev.cmd web
```
