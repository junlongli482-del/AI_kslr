# 括号检测 worker

独立于主 Python 服务的括号检测模块，使用翰林 `PicoDet_layout_1x` 权重。

## 运行

```powershell
python apps/bracket/detect.py --pdf "path/to/paper.pdf" --out "tmp/bracket"
```

生产建议使用独立虚拟环境，避免 Paddle 进入 FastAPI 主进程：

```powershell
python -m venv apps/bracket/.venv
apps/bracket/.venv/Scripts/pip install -r apps/bracket/requirements.txt
```

模型权重已放在 `apps/bracket/models/edu_scan_pdf`，可用 `BRACKET_MODEL_DIR` 覆盖。

## 约束

- 300dpi 渲染原 PDF；
- 模型路径必须能转成 ASCII 缓存路径；
- `HOME`/`USERPROFILE` 指向模块内 `.home`；
- 模型只加载一次；
- 阈值默认 0.6，低分框保留供人工复核。

`detect.py` 输出 JSON 契约：每页 `boxes`（全类别）+ `brackets`（过滤后）+ `elapsed_ms`。
