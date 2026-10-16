---
name: 智慧教学平台 · 快速录入
description: 以绿色与鼠尾草色构成的编辑校样台，支持原卷对照与题目审核。
colors:
  primary: "#235f4b"
  primary-light: "#527e6c"
  primary-soft: "#edf3ed"
  ink: "#243d36"
  body-text: "#263e38"
  muted: "#697971"
  background: "#f6f7f5"
  surface: "#ffffff"
  sidebar: "#f0f2ed"
  source-ground: "#e9ece6"
  line: "#e2e7e2"
  navigation-active: "#dce8da"
  question-active: "#e8f0e1"
  review-pending: "#98752c"
  review-pending-bg: "#faf2df"
  processing: "#4e7c85"
  processing-bg: "#eaf1f3"
  saved: "#457340"
  saved-bg: "#eaf2e8"
  failure: "#a4614d"
  failure-bg: "#f8ebe7"
  focus: "#3f826a"
typography:
  headline:
    fontFamily: "Noto Sans SC, Microsoft YaHei, sans-serif"
    fontSize: "29px"
    fontWeight: 600
    letterSpacing: "-0.025em"
  title:
    fontFamily: "Noto Sans SC, Microsoft YaHei, sans-serif"
    fontSize: "18px"
    fontWeight: 600
  body:
    fontFamily: "Noto Sans SC, Microsoft YaHei, sans-serif"
    fontSize: "14px"
    lineHeight: 1.8
  question:
    fontFamily: "Noto Sans SC, Microsoft YaHei, sans-serif"
    fontSize: "14px"
    lineHeight: 1.9
  label:
    fontFamily: "Noto Sans SC, Microsoft YaHei, sans-serif"
    fontSize: "12px"
    fontWeight: 500
  metadata:
    fontFamily: "Noto Sans SC, Microsoft YaHei, sans-serif"
    fontSize: "11px"
rounded:
  badge: "4px"
  editor: "5px"
  control: "6px"
  navigation: "7px"
  table: "8px"
  surface: "9px"
  dialog: "10px"
spacing:
  compact: "4px"
  small: "8px"
  gap: "12px"
  field: "16px"
  pane: "22px"
  page: "42px"
components:
  text-button:
    textColor: "#386845"
    padding: "4px 0"
  status-pending:
    backgroundColor: "{colors.review-pending-bg}"
    textColor: "{colors.review-pending}"
    rounded: "{rounded.badge}"
    padding: "4px 8px"
  navigation-active:
    backgroundColor: "{colors.navigation-active}"
    textColor: "#214d39"
    rounded: "{rounded.navigation}"
    padding: "13px 15px"
  rich-editor:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.editor}"
---

# Design System: 智慧教学平台 · 快速录入

## Overview

**Creative North Star:「编辑校样台」**

保留既有绿色与鼠尾草色的 Operate 工作台身份：原始资料是核对依据，连续题目导航连接原卷与可视化编辑器。视觉表达来自纸张、浅色桌面、清晰边界与克制的状态色，支持录入人员和教师持续审核资料。

正文保持易读，工具、来源与审核状态退居次级；颜色表达动作和状态，避免把待审核推断呈现为已确认事实。产品名称与能力边界以 PRODUCT.md 为准。

**Key Characteristics:**
- 绿色行动色、鼠尾草背景、白色编辑面。
- 原卷、题目索引与编辑器建立稳定的对照关系。
- 细边框与轻微色差组织区域，阴影只承担局部层次。
- 可视化编辑公式和图文，保留原始资料与人工修改。

## Colors

前置 tokens 为颜色值的规范来源，提取自 `apps/web/src/style.css`。

### Primary
- **校样绿（primary）**：主要操作、Element Plus 主题、文本光标的基准。
- **浅校样绿（primary-light / primary-soft）**：主题状态与柔和辅助底色。
- **鼠尾草选中面（navigation-active / question-active）**：分别用于主导航与题目导航。

### Neutral
- **纸白（surface）**：编辑区、顶栏、表格和对话框主体。
- **日间桌面（background / sidebar / source-ground）**：分别用于页面、固定导航与原卷画布；原卷本身保持白色。
- **深绿墨色（ink / body-text）**：控件与正文；**次级墨色（muted）**承载说明与元数据。
- **浅灰绿线（line）**：分隔栏、表格与容器边界。

### Semantic States
- **赭色（review-pending / review-pending-bg）**：待审核和提醒。
- **灰蓝（processing / processing-bg）**：处理中。
- **审核绿（saved / saved-bg）**：已入库。
- **红褐（failure / failure-bg）**：失败与中断；保存失败另有明确文本反馈。

**状态证据规则。** 状态词、图标与颜色共同传达结果；规则检查通过不等于识别内容准确。

## Typography

使用前置 tokens 中的 Noto Sans SC 字体栈，回退 Microsoft YaHei 与 sans-serif；当前通过 Google Fonts 引入该字体。中文操作界面采用同一无衬线家族。

- **Headline**：页面主标题使用 headline token；800px 及以下页面标题降为 24px。
- **Title**：分区标题使用 title token；较小标题为 15px、600。
- **Body / Question**：普通段落用 body，富文本用 question；1700px 及以上题干增为 15px。
- **Label / Metadata**：状态、文件副说明、保存状态、区域说明和原卷提示最终覆盖为 metadata。工具仍有 9—10px 辅助字号，不把 metadata 描述为全局下限。
- 题号使用等宽数字。公式采用 KaTeX，尺寸为周围文本的 1.04 倍。

## Layout

以下为快速录入表面的已实现布局；新表面沿用视觉语言，按自身任务选择组成方式。

- **常规页面**：固定侧栏 208px；顶栏 72px；内容上限 1600px，左右内边距 42px；表格与资源列表使用连续行。
- **桌面审核**：侧栏 74px；顶栏 53px，审核工具栏最小 77px；工作区高度 `calc(100vh - 130px)`。三栏为 `minmax(380px, 1.1fr) 150px minmax(420px, 1fr)`，依次为原卷、题目导航、编辑器，各自滚动。
- **不超过 1100px**：常规侧栏 170px；审核三栏改为 `minmax(300px, 1fr) 115px minmax(340px, 1fr)`，编辑区内边距 16px。
- **不超过 800px**：常规侧栏 64px，审核侧栏 54px。审核默认显示编辑器及 75px 题号导航，原卷隐藏；「对照原卷」在上方展开 420px 高原卷行，「收起原卷」恢复默认。展开后题目导航与编辑器仍在下方，并非独占原卷视图。题目导航隐藏预览文字与筛选项，保留题号入口。
- **至少 1700px**：三栏扩大为 `minmax(530px, 1.15fr) 172px minmax(500px, 1fr)`；编辑区内边距 27px 32px，原卷画布内边距 27px。

间距以 4px、8px、12px、16px 和 22px 编辑面内边距形成实际节奏，并非强制所有距离为 8 的倍数。窄屏属性表仍为两列；创建表单中的渠道配置改为纵向排列。

## Elevation & Depth

以纸白、灰绿底面与细线建立层次。原卷纸面使用 `0 2px 10px #344b2920` 轻投影；导航分段控件活动项使用 `0 1px 3px #354c2720`，其他分段控件使用 `0 1px 3px #34551c18`。富文本聚焦环为 `0 0 0 2px #e7f1de`，表达编辑焦点。完整值保存在 sidecar 扩展项，不放进前置 schema 不支持的组。

## Shapes

轻微圆角矩形为主，层级见前置 tokens：状态徽标紧凑，编辑器与控件居中，表格和上传容器略柔和，对话框稍大。主要边界为 1px；上传入口与待配置目录采用虚线。

品牌标记保留不对称四角 `10px 3px 10px 3px`；头像和状态点为圆形。原卷保留纸张比例，SVG 题框紧贴页面并以归一化坐标存储。

## Components

### Buttons

主要操作沿用 Element Plus 绿色主题。文本按钮无底色，hover 加深并加下划线；图标按钮 hover 使用浅绿底。键盘焦点为 2px 绿色轮廓、4px 偏移；非禁用按钮按下时下移 1px，禁用不透明度为 0.45。题框工具保留紧凑尺寸。

### Cards / Containers

表格、资源列表和编辑器以白色、细边框、轻圆角表达连续工作面；上传入口使用浅鼠尾草色及虚线。处理中、空态、失败可重试与完成是独立内容状态。

### Inputs / Fields

select 为白底细线轻圆角。富文本 focus-within 为绿色边界与柔和外环；工具栏为浅色条带。选项编辑器聚焦时展开工具栏；图片保留同行和列关系，空间不足可换行。公式可点击编辑，显示公式可横向滚动。

### Navigation

主导航激活项有鼠尾草底，审核模式收为图标栏。题目活动行同时改变底色、边框与题号底色；内容、答案解析、属性页签用绿色文字和底线表示当前页。移动端用题号保持连续导航，并由原卷显隐按钮控制对照区域。

### Source Viewer

原卷画布可双向滚动；手动缩放范围为 60%—300%，步长为 20 个百分点。选题时切至该题首个区域所在文档与物理页。「定位」按首个区域宽度计算 100%—300% 缩放；DOM 更新后滚动到区域左上方，保留 24px 边距，当前采用 smooth 滚动。

SVG 显示同页题框；活动题框加强描边，支持选择、移动、右下角缩放、补框和删框。跨栏、跨页题保留多个区域；定位当前使用首个区域，不承诺所有区域自动适配。页码按 PDF 物理页显示，页边界按钮禁用。

### Motion and Feedback

加载图标为 1.7s 线性旋转；保存中、已保存与保存失败有明确文本。`prefers-reduced-motion` 将 CSS 动画缩为 0.01ms、关闭过渡并设置自动滚动；定位函数显式请求 smooth，因此 CSS 不能保证取消该程序滚动。

## Do's and Don'ts

### Do:
- **Do** 保留绿色／鼠尾草编辑校样台身份，让原卷与可编辑内容承担视觉重心。
- **Do** 保留来源、状态文字与人工审核边界。
- **Do** 按实际断点处理桌面三栏、移动题号导航和原卷显隐。
- **Do** 以源码为准同步本文件 tokens 与 sidecar 扩展。

### Don't:
- **Don't** 用装饰渐变或大面积悬浮卡片替代连续工作面。
- **Don't** 把待审核、生成或未配置内容显示为已验证事实。
- **Don't** 用 JSON 输入替代既有可视化编辑。
- **Don't** 将当前行为描述误作未经实现的功能承诺。
