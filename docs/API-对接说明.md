# 快速录入 · 对外数据接口

供批阅 / 题库系统对接使用。只读接口为主，数据来自“审核入库”后的题库与试卷库。

## 基础地址

| 环境 | 地址 |
|---|---|
| 开发 | `http://127.0.0.1:1001/api`（前端代理）或 `http://127.0.0.1:1002/api` |
| 生产 | `https://<cpolar域名>/api`（Nginx Basic Auth） |

生产环境需要 Basic Auth，开发环境不需要。所有响应均为 JSON。

## 1. 试卷库

### 列表
```
GET /paperbank/papers
```
返回试卷数组，每项含：`id`、`title`、`mode`、`content`（试卷元数据 JSON）、`created_at` 等。

### 详情（含题目与模板）
```
GET /paperbank/papers/{id}
```
返回试卷字段，并附加：
- `questions`：该卷题目数组
- `templates`：原卷模板（学生信息区、区域、答案位置等）

## 2. 题库

### 列表 / 搜索
```
GET /questionbank/questions?query=关键词
```
返回题目数组。

### 详情
```
GET /questionbank/questions/{id}
```
单题完整数据。

## 3. 导出（推荐给下游系统）

### 全部试卷
```
GET /export/papers
```
```json
{ "schema_version": "p1-export-v1", "items": [ ... ] }
```

### 单份试卷
```
GET /export/papers/{id}
```

### 单道题目
```
GET /export/questions/{id}
```

导出数据包含题目结构化字段：题号、题干、选项、小问、答案、解析、评分标准、分值、题型、知识点、图片与公式、来源块坐标等。

## 4. 资源文件

题干图片 / 裁图 / 原卷页面：
```
GET /assets?key=<storage_key>
```
`storage_key` 会出现在题目 `image_layout`、`asset_metadata` 或试卷模板中。

## 5. 建议的对接方式

1. 定时或手动触发：`GET /export/papers` 拉全量；
2. 用 `GET /export/papers/{id}` 拉单卷详情（题目 + 模板）；
3. 按 `updated_at` 做增量（当前接口返回全量，增量可按时间字段自行过滤）；
4. 图片按 `/assets?key=` 拉取并缓存到自己的存储。

## 6. 注意事项

- 题目里的公式是 LaTeX（`$...$` 行内、`$$...$$` 块级）；
- 填空用 `{{blank}}` / `{{blank:n}}` 标记，答案在题目 `blanks[].answer`；
- 题框坐标是相对页面的 0–1 归一化值，配 `page_index` 使用；
- 开发库会被清理，对接联调请用生产地址；
- 接口无写权限，不支持从外部改题。
