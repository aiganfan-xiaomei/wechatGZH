#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""内置极简图示引擎 —— 用代码画出干净、可控、可读的中文配图。

为什么需要它
------------
免费文生图模型（Pollinations / FLUX 等）画「示意图」极不稳定：
  · 会往图里塞假的英文字母（看起来像乱码）；
  · 深色背景 + 大量噪点，信息密度低、发暗；
  · 无法保证把我们要的中文标签画对。
结果是配图「丑」且不可控。而公众号配图真正需要的是**把概念讲清楚**，
所以这里用确定性绘图替代——

  · 纯代码渲染，永远干净、可复现；
  · 真实中文文字用系统字体绘制，标签一定正确；
  · 统一 2 色（底色 + 强调色），符合克制审美；
  · 对齐、留白、描边宽度统一，不会出现「AI 感」的脏乱。

设计取向：白底 / 大留白 / 圆角卡片 / 单一强调色 / 一点几何装饰。

与 gen_images.py 的接口
----------------------
    render_diagram(recipe, spec, w, h, palette="ink-blue") -> PIL.Image
recipe 可选：pipeline / tree / layers / compare / timeline / hero / matrix

spec 字段（各 recipe 取用不同字段）：
    {"title": "顶部小标题", "items": ["A","B","C"],
     "left": {...}, "right": {...}, "note": "底部注释"}
"""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# ------------------------------------------------------------------ 配色
# 每种＝白底 + 一个强调色；其余灰阶自动生成，避免「多色打架」。
PALETTES: dict[str, dict[str, str]] = {
    "ink-blue":   {"bg": "#FFFFFF", "ink": "#111827", "soft": "#6B7280",
                   "line": "#E5E7EB", "fill": "#F8FAFC", "accent": "#2563EB", "accent_soft": "#EFF6FF"},
    "ink-purple": {"bg": "#FFFFFF", "ink": "#111827", "soft": "#6B7280",
                   "line": "#E9E5F5", "fill": "#FAF9FE", "accent": "#7C3AED", "accent_soft": "#F3EEFF"},
    "ink-teal":   {"bg": "#FFFFFF", "ink": "#111827", "soft": "#6B7280",
                   "line": "#DDEBE7", "fill": "#F7FBFA", "accent": "#0D9488", "accent_soft": "#E6F5F2"},
    "ink-red":    {"bg": "#FFFFFF", "ink": "#111827", "soft": "#6B7280",
                   "line": "#F0E1DE", "fill": "#FDFAF9", "accent": "#D93B30", "accent_soft": "#FCEDEB"},
    "ink-gold":   {"bg": "#FFFFFF", "ink": "#111827", "soft": "#6B7280",
                   "line": "#EFE6D3", "fill": "#FDFBF5", "accent": "#B8860B", "accent_soft": "#FBF3DF"},
    "ink-slate":  {"bg": "#FFFFFF", "ink": "#111827", "soft": "#6B7280",
                   "line": "#E2E6EA", "fill": "#F8F9FA", "accent": "#334155", "accent_soft": "#EEF1F4"},
    # 深色（用于科技/夜间题材，仍然保持克制、干净）
    "dark-cyan":   {"bg": "#0B1220", "ink": "#EAF0F8", "soft": "#8FA1BA",
                    "line": "#26344B", "fill": "#121B2B", "accent": "#22D3EE", "accent_soft": "#0E2A34"},
    "dark-violet": {"bg": "#0C0B18", "ink": "#EDEBF7", "soft": "#9A95B8",
                    "line": "#2A2740", "fill": "#151329", "accent": "#A78BFA", "accent_soft": "#241C3F"},
}

FONT_CANDIDATES_BOLD = [
    r"C:\Windows\Fonts\msyhbd.ttc",
    r"C:\Windows\Fonts\msyh.ttc",
    r"C:\Windows\Fonts\simhei.ttf",
    "/System/Library/Fonts/PingFang.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
]
FONT_CANDIDATES_REG = [
    r"C:\Windows\Fonts\msyh.ttc",
    r"C:\Windows\Fonts\simhei.ttf",
    r"C:\Windows\Fonts\msyhbd.ttc",
    "/System/Library/Fonts/PingFang.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
]


def _first_existing(paths: list[str]) -> str | None:
    for p in paths:
        if Path(p).exists():
            return p
    return None


_FONT_BOLD = _first_existing(FONT_CANDIDATES_BOLD)
_FONT_REG = _first_existing(FONT_CANDIDATES_REG)
_font_cache: dict[tuple[str, int], ImageFont.FreeTypeFont] = {}


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    path = (_FONT_BOLD if bold else _FONT_REG) or _FONT_BOLD or _FONT_REG
    key = (path or "", size)
    if key not in _font_cache:
        if path:
            _font_cache[key] = ImageFont.truetype(path, size)
        else:
            _font_cache[key] = ImageFont.load_default()
    return _font_cache[key]


def has_cjk_font() -> bool:
    return bool(_FONT_BOLD or _FONT_REG)


# ------------------------------------------------------------------ 绘图基元
def _hex(c: str) -> tuple[int, int, int]:
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def _rgba(c: str, a: int = 255) -> tuple[int, int, int, int]:
    r, g, b = _hex(c)
    return (r, g, b, a)


def _readable_on(color: str) -> str:
    """根据底色亮度选深/浅文字色，保证对比度。"""
    r, g, b = _hex(color)
    lum = (0.299 * r + 0.587 * g + 0.114 * b) / 255
    return "#111827" if lum > 0.6 else "#FFFFFF"


def _text_w(draw: ImageDraw.ImageDraw, text: str, font) -> float:
    return draw.textlength(text, font=font)


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_w: float) -> list[str]:
    lines, cur = [], ""
    for ch in text:
        if ch == "\n":
            lines.append(cur)
            cur = ""
            continue
        if _text_w(draw, cur + ch, font) <= max_w or not cur:
            cur += ch
        else:
            lines.append(cur)
            cur = ch
    if cur:
        lines.append(cur)
    return lines


def _draw_wrapped(
    draw: ImageDraw.ImageDraw,
    xy: tuple[float, float],
    text: str,
    font,
    fill,
    max_w: float,
    line_h: float,
    align: str = "center",
    max_lines: int = 4,
) -> float:
    """在 (x, y) 处绘制可换行文本，返回占用高度。align: left/center/right。"""
    lines = _wrap(draw, text, font, max_w)[:max_lines]
    x, y = xy
    for i, ln in enumerate(lines):
        lw = _text_w(draw, ln, font)
        if align == "center":
            draw.text((x - lw / 2, y + i * line_h), ln, font=font, fill=fill)
        elif align == "right":
            draw.text((x - lw, y + i * line_h), ln, font=font, fill=fill)
        else:
            draw.text((x, y + i * line_h), ln, font=font, fill=fill)
    return len(lines) * line_h


def _wrap_balanced(draw: ImageDraw.ImageDraw, text: str, font, max_w: float,
                   max_lines: int = 2) -> list[str]:
    """均衡断行：需要多行时按字数均分，避免出现「并行构 / 建」这种尾字挂单。

    若文本里写了显式换行符 \\n，则优先按它断行（作者可直接控制断句）。
    """
    if "\n" in text:
        return [ln for ln in text.split("\n") if ln][:max_lines]
    if _text_w(draw, text, font) <= max_w:
        return [text]
    k = min(max_lines, max(2, math.ceil(_text_w(draw, text, font) / max_w)))
    per = math.ceil(len(text) / k)
    return [text[i:i + per] for i in range(0, len(text), per)]


def _draw_lines(draw: ImageDraw.ImageDraw, xy: tuple[float, float], lines: list[str], font,
                fill, line_h: float, align: str = "center", center_block: bool = True) -> None:
    x, y = xy
    if center_block:
        y -= len(lines) * line_h / 2
    for i, ln in enumerate(lines):
        lw = _text_w(draw, ln, font)
        if align == "center":
            draw.text((x - lw / 2, y + i * line_h), ln, font=font, fill=fill)
        elif align == "right":
            draw.text((x - lw, y + i * line_h), ln, font=font, fill=fill)
        else:
            draw.text((x, y + i * line_h), ln, font=font, fill=fill)


def _arrow(draw: ImageDraw.ImageDraw, x1: float, x2: float, y: float, color, width: int = 3) -> None:
    """水平箭头（含实心三角头）。"""
    head = width * 3
    draw.line([(x1, y), (x2 - head, y)], fill=color, width=width)
    draw.polygon(
        [(x2, y), (x2 - head, y - head * 0.55), (x2 - head, y + head * 0.55)], fill=color
    )


def _card(
    draw: ImageDraw.ImageDraw,
    box: tuple[float, float, float, float],
    pal: dict,
    accent_bar: bool = False,
    radius: int = 14,
    fill: str | None = None,
) -> None:
    draw.rounded_rectangle(
        box, radius=radius, fill=_hex(fill or pal["fill"]), outline=_hex(pal["line"]), width=2
    )
    if accent_bar:
        x0, y0, x1, y1 = box
        draw.rounded_rectangle(
            (x0, y0, x0 + 6, y1), radius=3, fill=_hex(pal["accent"])
        )


def _badge(draw: ImageDraw.ImageDraw, cx: float, cy: float, r: float, text: str, pal: dict, font) -> None:
    draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=_hex(pal["accent"]))
    lw = _text_w(draw, text, font)
    bb = draw.textbbox((0, 0), text, font=font)
    th = bb[3] - bb[1]
    draw.text((cx - lw / 2, cy - th / 2 - bb[1]), text, font=font, fill=_hex(_readable_on(pal["accent"])))


def _header(draw: ImageDraw.ImageDraw, W: float, title: str, pal: dict, pad: float, font) -> float:
    """左上角强调色小标题 + 短竖条。返回内容起始 y。"""
    if not title:
        return pad
    size = font.size
    y = pad
    draw.rounded_rectangle((pad, y + 2, pad + 7, y + size + 4), radius=3, fill=_hex(pal["accent"]))
    draw.text((pad + 16, y), title, font=font, fill=_hex(pal["ink"]))
    return y + size + 22


def _note(draw: ImageDraw.ImageDraw, W: float, H: float, note: str, pal: dict, pad: float, size: int) -> None:
    if not note:
        return
    font = _font(size)
    lines = _wrap(draw, note, font, W - 2 * pad)
    y = H - pad - len(lines) * (size + 6)
    for i, ln in enumerate(lines):
        draw.text((pad, y + i * (size + 6)), ln, font=font, fill=_hex(pal["soft"]))


# ------------------------------------------------------------------ Recipes
def _fit_font(draw: ImageDraw.ImageDraw, text: str, max_w: float, max_lines: int,
              size: int, bold: bool = False, min_size: int = 11):
    """在不超过 max_lines 行的前提下，返回尽量大的字体（避免难看的断行）。"""
    f = _font(size, bold)
    guard = 0
    while size > min_size and guard < 40:
        if len(_wrap(draw, text, f, max_w)) <= max_lines:
            break
        size -= 2
        f = _font(size, bold)
        guard += 1
    return f


def _draw_hero(draw, W, H, spec, pal, fonts):
    """封面卡：大标题 + 副标题 + 右侧几何装饰（不依赖 AI 的封面）。"""
    pad = W * 0.07
    title = spec.get("title", "")
    subtitle = spec.get("subtitle", spec.get("note", ""))
    tfont = fonts["hero_title"]
    sfont = fonts["hero_sub"]

    # 右侧装饰：同心圆 + 点阵（半径/位置随画幅自适应，避免被裁切或压到标题）
    max_r = min(W, H) * 0.26
    cx = W - pad - max_r * 1.02
    cy = H * 0.5
    for i, r in enumerate((max_r, max_r * 0.70, max_r * 0.40)):
        draw.ellipse(
            (cx - r, cy - r, cx + r, cy + r),
            outline=_rgba(pal["accent"], 90 if i else 150), width=3 if i == 0 else 2,
        )
    dr = max_r * 0.20
    draw.ellipse((cx - dr, cy - dr, cx + dr, cy + dr), fill=_hex(pal["accent"]))
    dot_x0 = cx - max_r * 0.62
    dot_y0 = cy - max_r * 1.16
    for gx in range(4):
        for gy in range(3):
            px = dot_x0 + gx * (max_r * 0.34)
            py = dot_y0 + gy * (max_r * 0.30)
            draw.ellipse((px, py, px + 3, py + 3), fill=_rgba(pal["accent"], 80))

    max_w = min(W * 0.50, max(W * 0.32, (cx - max_r) - pad - 16))
    base_size = int(min(W, H) * 0.115)
    tfont = _fit_font(draw, title, max_w, 2, base_size, bold=True,
                      min_size=max(18, int(base_size * 0.55)))
    lines = _wrap_balanced(draw, title, tfont, max_w, 2)
    line_h = tfont.size * 1.30
    total = len(lines) * line_h + (sfont.size + 16 if subtitle else 0)
    y = (H - total) / 2
    draw.rounded_rectangle((pad, y - H * 0.10, pad + 60, y - H * 0.10 + 8),
                           radius=4, fill=_hex(pal["accent"]))
    y += H * 0.02
    for ln in lines:
        draw.text((pad, y), ln, font=tfont, fill=_hex(pal["ink"]))
        y += line_h
    if subtitle:
        draw.text((pad, y + 6), subtitle, font=sfont, fill=_hex(pal["accent"]))


def _draw_pipeline(draw, W, H, spec, pal, fonts):
    """横向流程：N 个阶段卡 + 箭头。"""
    pad = W * 0.06
    items = spec.get("items", []) or []
    n = max(1, len(items))
    top = _header(draw, W, spec.get("title", ""), pal, pad, fonts["h"])
    bot = H - pad - (fonts["cap"].size + 14 if spec.get("note") else 0)
    gap = W * 0.035
    cw = (W - 2 * pad - gap * (n - 1)) / n
    ch = min(bot - top, cw * 1.05)
    cy = top + (bot - top) / 2
    for i, it in enumerate(items):
        x0 = pad + i * (cw + gap)
        y0 = cy - ch / 2
        _card(draw, (x0, y0, x0 + cw, y0 + ch), pal, accent_bar=(i == 0))
        _badge(draw, x0 + cw / 2, y0 + ch * 0.24, min(cw, ch) * 0.11, str(i + 1), pal, fonts["badge"])
        lf = _fit_font(draw, it, cw - 22, 2, fonts["label"].size, bold=True,
                       min_size=max(12, int(fonts["label"].size * 0.68)))
        lines = _wrap_balanced(draw, it, lf, cw - 22, 2)
        _draw_lines(draw, (x0 + cw / 2, y0 + ch * 0.62), lines, lf, _hex(pal["ink"]), lf.size * 1.35,
                    align="center")
        if i < n - 1:
            _arrow(draw, x0 + cw + 4, x0 + cw + gap - 4, cy, _hex(pal["accent"]), max(2, int(W * 0.004)))
    _note(draw, W, H, spec.get("note", ""), pal, pad, fonts["cap"].size)


def _draw_tree(draw, W, H, spec, pal, fonts):
    """扇出树：左侧一个根节点，向右分叉到多个子节点。"""
    pad = W * 0.06
    items = spec.get("items", []) or []
    n = max(1, len(items))
    top = _header(draw, W, spec.get("title", ""), pal, pad, fonts["h"])
    bot = H - pad - (fonts["cap"].size + 14 if spec.get("note") else 0)

    root_w, child_w = W * 0.22, W * 0.34
    root_x = pad
    child_x = W - pad - child_w
    root_h = min(bot - top, H * 0.20)
    rcy = (top + bot) / 2
    _card(draw, (root_x, rcy - root_h / 2, root_x + root_w, rcy + root_h / 2), pal, accent_bar=True)
    _draw_wrapped(draw, (root_x + root_w / 2, rcy - fonts["label"].size * 0.8),
                  spec.get("root", "根"), fonts["label"], _hex(pal["ink"]),
                  root_w - 24, fonts["label"].size * 1.4, align="center", max_lines=2)

    ch = min((bot - top) / n * 0.66, H * 0.13)
    span = bot - top
    for i, it in enumerate(items):
        ccy = top + span * (i + 0.5) / n
        y0 = ccy - ch / 2
        x0 = child_x
        _card(draw, (x0, y0, x0 + child_w, y0 + ch), pal)
        draw.ellipse((x0 + 16, ccy - 5, x0 + 26, ccy + 5), fill=_hex(pal["accent"]))
        _draw_wrapped(draw, (x0 + 38, ccy - fonts["label"].size * 0.8), it, fonts["label"],
                      _hex(pal["ink"]), child_w - 58, fonts["label"].size * 1.4, align="left", max_lines=2)
        # 连线：根右缘中点 → 子左缘中点（折线）
        mx = (root_x + root_w + x0) / 2
        draw.line([(root_x + root_w, rcy), (mx, rcy)], fill=_hex(pal["line"]), width=3)
        draw.line([(mx, rcy), (mx, ccy)], fill=_hex(pal["line"]), width=3)
        draw.line([(mx, ccy), (x0, ccy)], fill=_hex(pal["line"]), width=3)
    _note(draw, W, H, spec.get("note", ""), pal, pad, fonts["cap"].size)


def _draw_layers(draw, W, H, spec, pal, fonts):
    """层叠：自上而下的层，强调层用实色。"""
    pad = W * 0.06
    items = spec.get("items", []) or []
    n = max(1, len(items))
    top = _header(draw, W, spec.get("title", ""), pal, pad, fonts["h"])
    bot = H - pad - (fonts["cap"].size + 14 if spec.get("note") else 0)
    gap = (bot - top) * 0.06
    bh = ((bot - top) - gap * (n - 1)) / n
    hi = spec.get("highlight", 0)
    for i, it in enumerate(items):
        y0 = top + i * (bh + gap)
        accent = i == hi
        box = (pad + (0 if accent else W * 0.035), y0, W - pad, y0 + bh)
        draw.rounded_rectangle(
            box, radius=12,
            fill=_hex(pal["accent"] if accent else pal["fill"]),
            outline=_hex(pal["accent"] if accent else pal["line"]), width=2,
        )
        col = _readable_on(pal["accent"]) if accent else pal["ink"]
        draw.rounded_rectangle((box[0] + 14, y0 + bh * 0.28, box[0] + 19, y0 + bh * 0.72),
                               radius=2, fill=_hex(_readable_on(pal["accent"]) if accent else pal["accent"]))
        _draw_wrapped(draw, (box[0] + 32, y0 + bh / 2 - fonts["label"].size * 0.8), it,
                      fonts["label"], _hex(col), W - 2 * pad - 60,
                      fonts["label"].size * 1.4, align="left", max_lines=2)
    _note(draw, W, H, spec.get("note", ""), pal, pad, fonts["cap"].size)


def _draw_compare(draw, W, H, spec, pal, fonts):
    """左右对照：两张卡，各含标题 + 要点（卡片按内容自适应高度并垂直居中）。"""
    pad = W * 0.06
    top = _header(draw, W, spec.get("title", ""), pal, pad, fonts["h"])
    bot = H - pad - (fonts["cap"].size + 14 if spec.get("note") else 0)
    gap = W * 0.045
    cw = (W - 2 * pad - gap) / 2
    body_font = fonts["body"]
    line_h = body_font.size * 1.45

    def col_height(data: dict) -> float:
        h = 76.0  # 标题带 + 间距
        for b in data.get("bullets", []) or []:
            nl = min(3, max(1, len(_wrap(draw, b, body_font, cw - 60))))
            h += nl * line_h + 12
        return h + 20

    left = spec.get("left", {}) or {}
    right = spec.get("right", {}) or {}
    ch = min(bot - top, max(170.0, max(col_height(left), col_height(right))))
    y_top = top + (bot - top - ch) / 2

    for i, data in enumerate((left, right)):
        x0 = pad + i * (cw + gap)
        draw.rounded_rectangle((x0, y_top, x0 + cw, y_top + ch), radius=14,
                               fill=_hex(pal["fill"]), outline=_hex(pal["line"]), width=2)
        band = _hex(pal["accent"] if i == 0 else pal["accent_soft"])
        draw.rounded_rectangle((x0, y_top, x0 + cw, y_top + 54), radius=14, fill=band)
        draw.rectangle((x0, y_top + 40, x0 + cw, y_top + 54), fill=band)
        hcol = _readable_on(pal["accent"]) if i == 0 else pal["accent"]
        hf = _fit_font(draw, data.get("title", ""), cw - 30, 1, fonts["label"].size, bold=True)
        hw = _text_w(draw, data.get("title", ""), hf)
        draw.text((x0 + cw / 2 - hw / 2, y_top + 27 - hf.size * 0.55),
                  data.get("title", ""), font=hf, fill=_hex(hcol))
        y = y_top + 76
        for bullet in data.get("bullets", []) or []:
            draw.ellipse((x0 + 20, y + 8, x0 + 28, y + 16), fill=_hex(pal["accent"]))
            used = _draw_wrapped(draw, (x0 + 40, y), bullet, body_font, _hex(pal["ink"]),
                                 cw - 60, line_h, align="left", max_lines=3)
            y += used + 12
    _note(draw, W, H, spec.get("note", ""), pal, pad, fonts["cap"].size)


def _draw_timeline(draw, W, H, spec, pal, fonts):
    """水平时间轴：一条主线 + N 个节点，标签上下交错。"""
    pad = W * 0.08
    items = spec.get("items", []) or []
    n = max(1, len(items))
    top = _header(draw, W, spec.get("title", ""), pal, pad, fonts["h"])
    bot = H - pad - (fonts["cap"].size + 14 if spec.get("note") else 0)
    cy = (top + bot) / 2
    x0, x1 = pad, W - pad
    draw.line([(x0, cy), (x1, cy)], fill=_hex(pal["line"]), width=3)
    step = (x1 - x0) / max(1, n - 1) if n > 1 else 0
    for i, it in enumerate(items):
        cx = x0 + i * step if n > 1 else (x0 + x1) / 2
        draw.ellipse((cx - 9, cy - 9, cx + 9, cy + 9), fill=_hex(pal["bg"]),
                     outline=_hex(pal["accent"]), width=3)
        draw.ellipse((cx - 4, cy - 4, cx + 4, cy + 4), fill=_hex(pal["accent"]))
        above = i % 2 == 0
        max_w = step * 0.92 if n > 1 else (x1 - x0) * 0.6
        if above:
            _draw_wrapped(draw, (cx, cy - 28 - fonts["body"].size * 1.4), it, fonts["body"],
                          _hex(pal["ink"]), max_w, fonts["body"].size * 1.4,
                          align="center", max_lines=3)
        else:
            _draw_wrapped(draw, (cx, cy + 28), it, fonts["body"], _hex(pal["ink"]),
                          max_w, fonts["body"].size * 1.4, align="center", max_lines=3)
    _note(draw, W, H, spec.get("note", ""), pal, pad, fonts["cap"].size)


def _draw_matrix(draw, W, H, spec, pal, fonts):
    """矩阵：把固定规格画成网格（如 1280×720 / 30fps / H.264 的规格卡）。"""
    pad = W * 0.06
    top = _header(draw, W, spec.get("title", ""), pal, pad, fonts["h"])
    bot = H - pad - (fonts["cap"].size + 14 if spec.get("note") else 0)
    cells = spec.get("cells", spec.get("items", [])) or []
    n = max(1, len(cells))
    cols = spec.get("cols", 2)
    rows = (n + cols - 1) // cols
    gap = W * 0.03
    cw = (W - 2 * pad - gap * (cols - 1)) / cols
    ch = ((bot - top) - gap * (rows - 1)) / rows
    for i, cell in enumerate(cells):
        r, c = divmod(i, cols)
        x0 = pad + c * (cw + gap)
        y0 = top + r * (ch + gap)
        _card(draw, (x0, y0, x0 + cw, y0 + ch), pal)
        label = cell.get("label", "") if isinstance(cell, dict) else str(cell)
        value = cell.get("value", "") if isinstance(cell, dict) else ""
        vfont = fonts["value"]
        lfont = fonts["cap"]
        vw = _text_w(draw, value, vfont)
        draw.text((x0 + cw / 2 - vw / 2, y0 + ch * 0.24), value, font=vfont, fill=_hex(pal["accent"]))
        lw = _text_w(draw, label, lfont)
        draw.text((x0 + cw / 2 - lw / 2, y0 + ch * 0.62), label, font=lfont, fill=_hex(pal["soft"]))
    _note(draw, W, H, spec.get("note", ""), pal, pad, fonts["cap"].size)


RECIPES = {
    "hero": _draw_hero,
    "pipeline": _draw_pipeline,
    "tree": _draw_tree,
    "layers": _draw_layers,
    "compare": _draw_compare,
    "timeline": _draw_timeline,
    "matrix": _draw_matrix,
}


def render_diagram(recipe: str, spec: dict, w: int, h: int, palette: str = "ink-blue") -> Image.Image:
    """按 recipe 渲染一张极简图示。"""
    if recipe not in RECIPES:
        raise ValueError(f"未知图示类型: {recipe}（可选: {', '.join(RECIPES)}）")
    pal = PALETTES.get(palette) or PALETTES["ink-blue"]
    img = Image.new("RGB", (int(w), int(h)), _hex(pal["bg"]))
    draw = ImageDraw.Draw(img)

    s = min(w, h)
    fonts = {
        "hero_title": _font(int(s * 0.135), bold=True),
        "hero_sub": _font(int(s * 0.045)),
        "h": _font(int(s * 0.042), bold=True),
        "label": _font(int(s * 0.040), bold=True),
        "body": _font(int(s * 0.036)),
        "cap": _font(int(s * 0.032)),
        "value": _font(int(s * 0.085), bold=True),
        "badge": _font(int(s * 0.038), bold=True),
    }
    RECIPES[recipe](draw, w, h, spec, pal, fonts)
    return img


def list_recipes() -> list[str]:
    return list(RECIPES)
