# -*- coding: utf-8 -*-
"""括号自动识别 POC 主脚本。

用法：
    python detect.py --pdf "D:\\...\\703475_34.pdf" --out ./output

输出：
    output/page_0_annotated.png
    output/page_1_annotated.png
    output/result.json
    output/pages/page_0.png         # 原图（供 Web 端叠加/放大）
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

from bracket_core import (
    DEFAULT_DPI,
    DEFAULT_MODEL_DIR,
    DEFAULT_MODEL_NAME,
    DEFAULT_THRESHOLD,
    Detector,
    draw_annotations,
    render_pdf,
    detect_page,
)


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="括号自动识别 POC（edu_scan_pdf）")
    p.add_argument("--pdf", required=True, help="原卷 PDF 路径")
    p.add_argument("--out", default="./output", help="输出目录，默认 ./output")
    p.add_argument("--dpi", type=int, default=DEFAULT_DPI, help="渲染 DPI，默认 300")
    p.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD,
                   help="bracket 置信度阈值，默认 0.6")
    p.add_argument("--model-dir", default=os.environ.get("BRACKET_MODEL_DIR", DEFAULT_MODEL_DIR),
                   help="det 模型目录")
    p.add_argument("--model-name", default=DEFAULT_MODEL_NAME)
    p.add_argument("--device", default="cpu", help="cpu / gpu:0")
    p.add_argument("--show-all", action="store_true",
                   help="标注图里同时画出 score_box / question_number / drop 等类别")
    p.add_argument("--line-width", type=int, default=0,
                   help="框线宽度像素，0=按图高自动（约 0.16%% 图高，最小 2px）")
    p.add_argument("--no-page-images", action="store_true", help="不保存未标注原图")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    pdf_path = os.path.abspath(args.pdf)
    if not os.path.exists(pdf_path):
        print(f"[错误] PDF 不存在：{pdf_path}", file=sys.stderr)
        return 2
    if not os.path.isdir(args.model_dir):
        print(f"[错误] 模型目录不存在：{args.model_dir}", file=sys.stderr)
        return 2

    out_dir = os.path.abspath(args.out)
    os.makedirs(out_dir, exist_ok=True)
    pages_dir = os.path.join(out_dir, "pages")
    os.makedirs(pages_dir, exist_ok=True)

    print(f"[1/3] 加载模型 {args.model_name} ...")
    detector = Detector(args.model_dir, args.model_name, args.device)
    detector.model  # 触发加载
    print(f"      加载完成，耗时 {detector.load_ms} ms")

    print(f"[2/3] 渲染并识别：{os.path.basename(pdf_path)}（{args.dpi} dpi）")
    from PIL import Image

    pages_json = []
    t_all = time.perf_counter()
    for page_index, rgb in render_pdf(pdf_path, dpi=args.dpi):
        t0 = time.perf_counter()
        result = detect_page(detector, rgb, page_index, threshold=args.threshold)
        render_ms = int((time.perf_counter() - t0) * 1000) - result.detect_ms
        result.render_ms = max(render_ms, 0)

        if not args.no_page_images:
            Image.fromarray(rgb).save(os.path.join(pages_dir, f"page_{page_index}.png"))

        boxes = result.boxes
        if not args.show_all:
            boxes = [b for b in boxes if b["label"] == "bracket" and b["score"] > args.threshold]
        annotated = draw_annotations(
            rgb,
            [b for b in sorted(boxes, key=lambda b: (b["label"] != "bracket", b.get("index", 0)))],
            line_width=args.line_width or None,
        )
        Image.fromarray(annotated).save(os.path.join(out_dir, f"page_{page_index}_annotated.png"))

        pages_json.append(result.to_json())
        print(f"      page {page_index}: 检出 bracket {len(result.brackets)} 个，"
              f"推理 {result.detect_ms} ms，渲染 {result.render_ms} ms")

    total = {
        "source_file": os.path.basename(pdf_path),
        "source_path": pdf_path,
        "page_count": len(pages_json),
        "dpi": args.dpi,
        "threshold": args.threshold,
        "model": {
            "name": detector.model_name,
            "dir": detector.model_dir,
            "device": detector.device,
            "load_ms": detector.load_ms,
        },
        "elapsed_ms": int((time.perf_counter() - t_all) * 1000),
        "pages": pages_json,
    }

    result_path = os.path.join(out_dir, "result.json")
    with open(result_path, "w", encoding="utf-8") as f:
        json.dump(total, f, ensure_ascii=False, indent=2)

    n = sum(len(p["brackets"]) for p in pages_json)
    print(f"[3/3] 完成：{len(pages_json)} 页，共 {n} 个 bracket，"
          f"总耗时 {total['elapsed_ms']} ms")
    print(f"      输出：{result_path}")
    print(f"             {os.path.join(out_dir, 'page_*_annotated.png')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
