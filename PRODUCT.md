# 智慧教学平台 · 快速录入

<!-- impeccable:product-schema 1 -->

## Platform
web

## Stack
用户已确认文档方案：Vue、TypeScript、Java 21 / Spring Boot、PostgreSQL 17、Python AI处理服务。实施细节由开发决定。

## Users
教辅录入人员与教师，对照原卷审核机器识别结果，减少逐题输入。

## Product Purpose
上传PDF、图片或Word，经MinerU与AI生成可编辑题目、试卷、答案解析和原卷区域模板。

## Operating Context
桌面浏览器，主要操作上传和最终审核。教辅纸张已印刷，原卷保持原貌。题目与答案可以分文件，答案包含无关章节也需匹配。

## Capabilities and Constraints
真实样本验证优先。知识点目录缺失可跳过，不伪造正式标签。需要公式可视化编辑、图片同行布局、多区域切题、持久化及两渠道回退。当前不做实际批阅。

## Evidence on Hand
两份4页九上数学试卷与一份1页共用答案，文件路径见需求文档。没有已验证自动准确率或知识点目录。

## Product Principles
用户编辑渲染结果而非JSON；保留来源和人工修改；错误明确可修复；不把待审核推断显示为事实。

## Design Delegation
用户明确要求自主开发、减少中途打扰，视觉与常规技术选择已授权由开发决定。默认采用桌面审核工作台。
