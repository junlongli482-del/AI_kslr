"""Refresh prompt documentation from the actual source, without configuration or secrets."""
import ast
import hashlib
from pathlib import Path

root=Path(__file__).resolve().parents[1]
source=root/'apps/ai/core.py'
tree=ast.parse(source.read_text(encoding='utf-8'))
prompts=[]
suffix=''
for node in ast.walk(tree):
    if isinstance(node,ast.Assign) and isinstance(node.value,ast.Constant) and isinstance(node.value.value,str):
        for target in node.targets:
            if isinstance(target,ast.Name) and target.id.endswith('_PROMPT'):
                prompts.append((target.id,node.value.value,node.lineno))
    if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and node.func.attr=='json' and len(node.args)>1:
        instruction=node.args[1]
        if isinstance(instruction,ast.Constant) and isinstance(instruction.value,str):
            label='GENERATE_PROMPT' if instruction.value.startswith('根据题目所属学科') else 'EXPAND_ANSWER_RANGES_PROMPT'
            prompts.append((label,instruction.value,node.lineno))
    if isinstance(node,ast.Constant) and isinstance(node.value,str) and '只输出一个有效JSON对象' in node.value:
        suffix=node.value

lines=['# 快速录入：当前完整提示词快照','','日期：2026-10-15。由 `scripts/export-prompts.py` 从 `apps/ai/core.py` 的 AST 提取，内容为实际执行的指令。',
       '','System.content = 当前阶段指令 + 公共后缀；User.content = json.dumps(payload, ensure_ascii=False)。阶段指令不能代替结构校验、来源检查或人工内容审核。',
       '','当前适配层未设置 response_format、temperature 或 seed。生成请求使用文本 JSON，其中的本地图片 URL 不是已发送给模型的视觉输入；没有图像理解依据时不能宣称答案已被图形验证。','']
for label,instruction,line in sorted(prompts,key=lambda item:item[2]):
    lines.extend([f'## {label}','',f'来源：`apps/ai/core.py:{line}`；SHA-256：`{hashlib.sha256(instruction.encode()).hexdigest()}`。',
                  '','```text',instruction,'```',''])
lines.extend(['## 公共后缀','','```text',suffix.strip(),'```','',
              '## 输入、输出与规则边界','',
              '| 阶段 | 输入 | 后置规则 |','|---|---|---|',
              '| 结构化 | 文档名、完整 Markdown、块 ID/页码/bbox/kind/140 字符 anchor、图片 URL/坐标/像素尺寸 | 题号及 ID 规范化、块引用检查、题框生成、图片引用补齐 |',
              '| 答案提取 | 同样的紧凑文档，可含其他试卷答案 | 每个顶层题号一条、保留无关候选、必要时二次拆分范围 |',
              '| 答案匹配 | 试卷、题号、题干、选项、小问、候选答案 | 有效 ID、题目与条目一对一、保留未采用答案 |',
              '| AI 补缺 | 每批最多 8 道缺少答案或解析的题目，含已有内容 | 仅填写空字段、标记 ai_generated 与待核对、统一公式分隔符 |',
              '','结构化、答案提取、匹配、补缺的输出 token 上限分别为 60000、16000、12000、14000。超过任务预算或输入安全预算会报错，不截去原文后伪装成功。',
              '','四种 LaTeX 分隔符由程序兼容，提示词统一使用美元分隔符。图片完整性由已有块坐标和 URL 检查补足，不能仅依赖模型承诺。',''])
(root/'docs/contracts/quick-entry/提示词快照.md').write_text('\n'.join(lines),encoding='utf-8')
print(f'Exported {len(prompts)} actual prompts and common suffix.')
