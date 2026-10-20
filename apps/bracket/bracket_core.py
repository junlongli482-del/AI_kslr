# -*- coding: utf-8 -*-
"""括号识别 POC 核心库：PDF 渲染 -> 分带推理 -> 坐标还原 -> 标注绘制。

只依赖 pypdfium2 / numpy / opencv / Pillow；模型推理走 paddlex。
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import time
from dataclasses import dataclass, field
from typing import Iterable

import numpy as np

# Windows 控制台默认不是 UTF-8，中文日志会乱码
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

# paddle 首次 import 会往 ~/.cache/paddle 写东西。把 HOME 指到项目内，
# 既能避免无权限目录（沙箱 / 只读用户目录），也让缓存跟着项目走。
_HOME = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".home")
os.makedirs(_HOME, exist_ok=True)
os.environ["HOME"] = _HOME
os.environ["USERPROFILE"] = _HOME
os.environ.setdefault("HF_HOME", os.path.join(_HOME, ".cache", "huggingface"))
os.environ.setdefault("MODELSCOPE_CACHE", os.path.join(_HOME, ".cache", "modelscope"))

DEFAULT_MODEL_DIR = os.getenv('BRACKET_MODEL_DIR') or os.path.join(os.path.dirname(os.path.abspath(__file__)), 'models', 'edu_scan_pdf')
DEFAULT_MODEL_NAME = "PicoDet_layout_1x"
DEFAULT_DPI = 300
DEFAULT_THRESHOLD = 0.6
MIN_SCORE = 0.3  # 模型 NMS 的 score_threshold，低于此值模型不会再吐出框

CLASS_LABELS = ["bracket", "score_box", "question_number", "question_tag", "qr", "drop"]

# 画框配色：bracket 按置信度分色，其余类别固定色
CLASS_COLORS = {
    "score_box": (59, 130, 246),       # 蓝
    "question_number": (168, 85, 247), # 紫
    "question_tag": (20, 184, 166),    # 青
    "qr": (236, 72, 153),              # 粉
    "drop": (6, 182, 212),             # 天蓝
}
BRACKET_HIGH = (34, 197, 94)    # >=0.8 绿
BRACKET_MID = (245, 158, 11)    # 0.6~0.8 黄
BRACKET_LOW = (156, 163, 175)   # <0.6 灰


def bracket_color(score: float) -> tuple[int, int, int]:
    if score >= 0.8:
        return BRACKET_HIGH
    if score >= 0.6:
        return BRACKET_MID
    return BRACKET_LOW


# --------------------------------------------------------------------------- #
# PDF 渲染
# --------------------------------------------------------------------------- #
def pdf_page_count(pdf_path: str) -> int:
    import pypdfium2 as pdfium

    return len(pdfium.PdfDocument(pdf_path))


def render_pdf(pdf_path: str, dpi: int = DEFAULT_DPI):
    """逐页渲染，yield (page_index, RGB ndarray)。"""
    import pypdfium2 as pdfium

    doc = pdfium.PdfDocument(pdf_path)
    scale = dpi / 72.0
    for i in range(len(doc)):
        bitmap = doc[i].render(scale=scale)
        arr = bitmap.to_numpy()  # RGB, uint8
        yield i, arr


def rgb_to_bgr(img_rgb: np.ndarray) -> np.ndarray:
    return np.ascontiguousarray(img_rgb[:, :, ::-1])


# --------------------------------------------------------------------------- #
# 分带策略（与线上 teaching_pos3.1 get_edu_cursors 完全一致）
# --------------------------------------------------------------------------- #
def get_edu_cursors(w: int, h: int) -> list[tuple[int, int]]:
    if h > w:                       # 竖版 A4：整页一条
        return [(0, w)]
    if h / w > 0.68:                # A3 横向：左右两半
        return [(0, w // 2), (w // 2, w)]
    cursors, left = [], 0           # 超宽：滑窗
    cw = int(h * 0.7)
    move = int(cw * 0.75)
    while True:
        cursors.append((min(left, w - cw), left + cw))
        if left + cw >= w:
            break
        left += move
    return cursors


def _iou(a, b) -> float:
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    ix0, iy0 = max(ax0, bx0), max(ay0, by0)
    ix1, iy1 = min(ax1, bx1), min(ay1, by1)
    iw, ih = max(0.0, ix1 - ix0), max(0.0, iy1 - iy0)
    inter = iw * ih
    if inter <= 0:
        return 0.0
    ua = (ax1 - ax0) * (ay1 - ay0) + (bx1 - bx0) * (by1 - by0) - inter
    return inter / ua if ua > 0 else 0.0


# --------------------------------------------------------------------------- #
# 模型
# --------------------------------------------------------------------------- #
def _is_ascii(path: str) -> bool:
    try:
        path.encode("ascii")
        return True
    except UnicodeEncodeError:
        return False


def ascii_model_dir(model_dir: str) -> str:
    """Paddle 的 C++ 推理引擎读不了含中文的模型路径（会报 json parse empty input），
    这里把模型复制到纯英文的缓存目录再用。"""
    model_dir = os.path.abspath(model_dir)
    if _is_ascii(model_dir):
        return model_dir

    cache_root = os.environ.get("BRACKET_MODEL_CACHE")
    if not cache_root:
        base = os.environ.get("LOCALAPPDATA") or tempfile.gettempdir()
        cache_root = os.path.join(base, "bracket_poc", "models")
    os.makedirs(cache_root, exist_ok=True)
    if not _is_ascii(os.path.abspath(cache_root)):
        cache_root = os.path.join("C:\\ProgramData", "bracket_poc", "models")
        os.makedirs(cache_root, exist_ok=True)

    dst = os.path.join(cache_root, os.path.basename(model_dir.rstrip("\\/")))
    src_json = os.path.join(model_dir, "inference.json")
    dst_json = os.path.join(dst, "inference.json")
    need_copy = (
        not os.path.isfile(dst_json)
        or os.path.getsize(dst_json) != os.path.getsize(src_json)
    )
    if need_copy:
        tmp = dst + ".tmp"
        if os.path.isdir(tmp):
            shutil.rmtree(tmp, ignore_errors=True)
        shutil.copytree(model_dir, tmp)
        if os.path.isdir(dst):
            shutil.rmtree(dst)
        os.replace(tmp, dst)
        print(f"[model] 模型路径含中文，已复制到英文缓存目录：{dst}")
    return dst


class Detector:
    def __init__(self, model_dir: str = DEFAULT_MODEL_DIR,
                 model_name: str = DEFAULT_MODEL_NAME, device: str = "cpu",
                 run_mode: str | None = None):
        self.original_model_dir = model_dir
        self.model_dir = ascii_model_dir(model_dir)
        self.model_name = model_name
        self.device = device
        # None = 交给 PaddleX 选默认（CPU 上即 mkldnn，最快）；
        # "paddle" = 关掉 mkldnn。paddlepaddle 3.3.x 的 CPU oneDNN 对 PIR 模型
        # 有 bug（ConvertPirAttribute2RuntimeAttribute not support），会自动回退。
        self.run_mode = run_mode or os.environ.get("BRACKET_RUN_MODE") or None
        self.load_ms = 0
        self._model = None

    @property
    def model(self):
        if self._model is None:
            t0 = time.perf_counter()
            from paddlex import create_model

            kwargs = {}
            if self.run_mode:
                kwargs["engine_config"] = {"run_mode": self.run_mode}
            self._model = create_model(
                model_name=self.model_name,
                model_dir=self.model_dir,
                device=self.device,
                **kwargs,
            )
            self.load_ms = int((time.perf_counter() - t0) * 1000)
        return self._model

    def predict(self, img_bgr: np.ndarray) -> list[dict]:
        try:
            return self._predict(self.model, img_bgr)
        except NotImplementedError as exc:
            # paddlepaddle 3.3.x + CPU mkldnn 的已知 bug，退回纯 CPU 路径重试一次
            if "ConvertPirAttribute2RuntimeAttribute" in str(exc) and self.run_mode != "paddle":
                print("[model] 检测到 oneDNN/PIR 兼容问题，改用 run_mode=paddle 重试（会慢一些）")
                self.run_mode = "paddle"
                self._model = None
                return self._predict(self.model, img_bgr)
            raise

    @staticmethod
    def _predict(model, img_bgr: np.ndarray) -> list[dict]:
        out = model.predict(img_bgr)
        results = list(out)
        if not results:
            return []
        res = results[0].json
        res = res.get("res", res)
        boxes = []
        for b in res.get("boxes", []):
            label = str(b.get("label", ""))
            score = float(b.get("score", 0.0))
            if score < MIN_SCORE:
                continue
            x0, y0, x1, y1 = [float(v) for v in b["coordinate"]]
            boxes.append({"label": label, "score": score, "bbox": [x0, y0, x1, y1]})
        return boxes


@dataclass
class PageResult:
    page_index: int
    width: int
    height: int
    render_ms: int
    detect_ms: int
    cursors: list[tuple[int, int]]
    boxes: list[dict] = field(default_factory=list)      # 全部类别
    brackets: list[dict] = field(default_factory=list)   # 仅 bracket（按阅读顺序编号）

    def to_json(self) -> dict:
        return {
            "page_index": self.page_index,
            "image_width": self.width,
            "image_height": self.height,
            "render_ms": self.render_ms,
            "elapsed_ms": self.detect_ms,
            "bands": [{"left": int(l), "right": int(r)} for l, r in self.cursors],
            "bracket_count": len(self.brackets),
            "brackets": self.brackets,
            "boxes": self.boxes,
        }


def detect_page(det: Detector, img_rgb: np.ndarray, page_index: int,
                threshold: float = DEFAULT_THRESHOLD,
                cursors: list[tuple[int, int]] | None = None) -> PageResult:
    img_bgr = rgb_to_bgr(img_rgb)
    h, w = img_bgr.shape[:2]
    if cursors is None:
        cursors = get_edu_cursors(w, h)

    t0 = time.perf_counter()
    collected: list[dict] = []
    for band_idx, (left, right) in enumerate(cursors):
        sub = img_bgr[:, left:right]
        for b in det.predict(sub):
            x0, y0, x1, y1 = b["bbox"]
            box = {
                "label": b["label"],
                "score": b["score"],
                "bbox": [x0 + left, y0, x1 + left, y1],
                "band": band_idx,
            }
            collected.append(box)

    # 重叠滑窗去重
    dedup: list[dict] = []
    for box in collected:
        if any(b["label"] == box["label"] and _iou(b["bbox"], box["bbox"]) > 0.7
               for b in dedup):
            continue
        dedup.append(box)
    detect_ms = int((time.perf_counter() - t0) * 1000)

    brackets = [b for b in dedup if b["label"] == "bracket" and b["score"] > threshold]
    brackets.sort(key=lambda b: (b["band"], b["bbox"][1], b["bbox"][0]))
    for i, b in enumerate(brackets):
        b["index"] = i + 1
        b["bbox_norm"] = [round(b["bbox"][0] / w, 6), round(b["bbox"][1] / h, 6),
                          round(b["bbox"][2] / w, 6), round(b["bbox"][3] / h, 6)]
    for b in dedup:
        if "index" not in b:
            b["bbox_norm"] = [round(b["bbox"][0] / w, 6), round(b["bbox"][1] / h, 6),
                              round(b["bbox"][2] / w, 6), round(b["bbox"][3] / h, 6)]

    return PageResult(page_index=page_index, width=w, height=h, render_ms=0,
                      detect_ms=detect_ms, cursors=cursors, boxes=dedup, brackets=brackets)


# --------------------------------------------------------------------------- #
# 标注绘制
# --------------------------------------------------------------------------- #
def _load_font(size: int):
    from PIL import ImageFont

    for name in ("msyhbd.ttc", "msyh.ttc", "arialbd.ttf", "arial.ttf"):
        p = os.path.join(r"C:\Windows\Fonts", name)
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except OSError:
                continue
    return ImageFont.load_default()


def draw_annotations(img_rgb: np.ndarray, boxes: Iterable[dict],
                     line_width: int | None = None,
                     show_labels: bool = True) -> "np.ndarray":
    """把框画到整页图上。boxes 需含 label/score/bbox。bracket 的 index 会作为序号。"""
    from PIL import Image, ImageDraw

    im = Image.fromarray(img_rgb)
    draw = ImageDraw.Draw(im)
    h = img_rgb.shape[0]
    if line_width is None:
        line_width = max(2, round(h * 0.0016))
    font = _load_font(max(14, round(h * 0.011))) if show_labels else None

    for b in boxes:
        label = b["label"]
        score = float(b["score"])
        x0, y0, x1, y1 = [int(round(v)) for v in b["bbox"]]
        color = bracket_color(score) if label == "bracket" else CLASS_COLORS.get(label, (120, 120, 120))
        draw.rectangle([x0, y0, x1, y1], outline=color, width=line_width)
        if not show_labels or font is None:
            continue
        if label == "bracket":
            text = f"#{b.get('index', '?')} {score:.2f}"
        else:
            text = f"{label} {score:.2f}"
        tb = draw.textbbox((0, 0), text, font=font)
        tw, th = tb[2] - tb[0], tb[3] - tb[1]
        pad = max(2, line_width)
        ly = y0 - th - pad * 2
        if ly < 0:
            ly = y1 + 1
        lx = min(max(0, x0), max(0, im.width - tw - pad * 2))
        draw.rectangle([lx, ly, lx + tw + pad * 2, ly + th + pad * 2], fill=color)
        draw.text((lx + pad, ly + pad - tb[1]), text, font=font, fill=(255, 255, 255))

    return np.asarray(im)


# --------------------------------------------------------------------------- #
# 整份 PDF 跑一遍
# --------------------------------------------------------------------------- #
def run_pdf(pdf_path: str, out_dir: str, detector: Detector,
            dpi: int = DEFAULT_DPI, threshold: float = DEFAULT_THRESHOLD,
            progress=None, save_page_images: bool = True) -> dict:
    from PIL import Image

    os.makedirs(out_dir, exist_ok=True)
    pages_dir = os.path.join(out_dir, "pages")
    os.makedirs(pages_dir, exist_ok=True)

    t_all = time.perf_counter()
    pages = []
    for i, arr in render_pdf(pdf_path, dpi=dpi):
        t0 = time.perf_counter()
        result = detect_page(detector, arr, i, threshold=threshold)
        result.render_ms = int((time.perf_counter() - t0) * 1000) - result.detect_ms
        if save_page_images:
            Image.fromarray(arr).save(os.path.join(pages_dir, f"page_{i}.png"))
        pages.append(result)
        if progress:
            progress(i, result)

    total = {
        "source_file": os.path.basename(pdf_path),
        "source_path": os.path.abspath(pdf_path),
        "page_count": len(pages),
        "dpi": dpi,
        "threshold": threshold,
        "model": {"name": detector.model_name, "dir": detector.model_dir,
                  "device": detector.device, "load_ms": detector.load_ms},
        "elapsed_ms": int((time.perf_counter() - t_all) * 1000),
        "pages": [p.to_json() for p in pages],
    }
    return total
