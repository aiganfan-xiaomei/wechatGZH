#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""微信公众号配图生成器 —— 10 种内置风格 + 免费 API 自动降级。

用法
----
单张：
  python gen_images.py --style cyber-tech --ratio 16:9 --subject "AI agent workflow" -o out/fig1.jpg

批量（推荐，spec 为 JSON）：
  python gen_images.py --spec images.json --outdir out

spec JSON 结构：
{
  "style": "minimal-line",                 // 可选，默认风格
  "images": [
    {"id": "cover", "role": "cover", "ratio": "2.35:1", "title": "封面大字",
     "subject": "abstract workflow diagram", "seed": 123},
    {"id": "fig1",  "role": "inline", "ratio": "16:9", "style": "cyber-tech",
     "subject": "data pipeline", "caption": "图1 数据流"}
  ]
}

输出：outdir/manifest.json + 图片文件
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import os
import random
import sys
import time
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wc_common import UA, http_request, jprint, load_config  # noqa: E402
from diagrams import PALETTES, has_cjk_font, list_recipes, render_diagram  # noqa: E402

try:
    from PIL import Image, ImageDraw, ImageFilter, ImageFont
except ImportError:
    print("[fatal] 需要 Pillow：python -m pip install Pillow")
    raise

# --------------------------------------------------------------------- 风格库
STYLES: dict[str, dict] = {
    "minimal-line": {
        "label": "极简线性插画",
        "prompt": (
            "minimalist single-line illustration, clean solid white background, "
            "thin black strokes, generous negative space, abstract geometric shapes, "
            "flat 2d vector, editorial art"
        ),
        "palette": ("#ffffff", "#111111"),
    },
    "flat-vector": {
        "label": "扁平矢量",
        "prompt": (
            "flat vector illustration, bold simple geometric shapes, limited three color palette, "
            "modern corporate style, clean composition, subtle grain"
        ),
        "palette": ("#eef3ff", "#2b4bff"),
    },
    "isometric-3d": {
        "label": "等距 3D",
        "prompt": (
            "isometric 3d illustration, soft clay-like rendering, pastel palette, "
            "clean white background, miniature diorama scene, soft ambient shadows, high detail"
        ),
        "palette": ("#f3f6fb", "#7c8cff"),
    },
    "watercolor": {
        "label": "水彩手绘",
        "prompt": (
            "delicate watercolor illustration, soft washes of translucent color, "
            "cold-press paper texture, hand painted, muted pastel tones, artistic bleed edges"
        ),
        "palette": ("#fdf8f2", "#c98b6b"),
    },
    "cyber-tech": {
        "label": "赛博科技",
        "prompt": (
            "dark cyberpunk technology illustration, deep navy background, "
            "glowing cyan and violet neon accents, circuit and grid motifs, "
            "futuristic HUD elements, volumetric light, cinematic"
        ),
        "palette": ("#080d1c", "#22d3ee"),
    },
    "editorial": {
        "label": "杂志编辑风",
        "prompt": (
            "editorial magazine illustration, swiss design influence, bold color blocks, "
            "strong grid composition, risograph print texture, sophisticated restraint"
        ),
        "palette": ("#fbf7ef", "#e0533d"),
    },
    "ink-bw": {
        "label": "水墨黑白",
        "prompt": (
            "black and white ink brush illustration, sumi-e style, high contrast, "
            "textured rice paper, dramatic brush strokes, minimalist composition"
        ),
        "palette": ("#f7f6f3", "#1a1a1a"),
    },
    "neon-gradient": {
        "label": "霓虹渐变",
        "prompt": (
            "gradient mesh background, vibrant neon gradient, smooth color transitions, "
            "abstract liquid shapes, glossy 3d blobs, modern digital art"
        ),
        "palette": ("#12122b", "#b16cff"),
    },
    "clay-3d": {
        "label": "黏土 3D",
        "prompt": (
            "3d clay render, cute soft rounded shapes, matte material, studio three-point lighting, "
            "soft pastel colors, playful mood, high fidelity octane render"
        ),
        "palette": ("#fff5f7", "#ff8fab"),
    },
    "guochao": {
        "label": "国潮国风",
        "prompt": (
            "chinese guochao style illustration, traditional ink and mineral pigment colors, "
            "gold and vermilion accents, auspicious clouds and mountain motifs, elegant oriental aesthetic"
        ),
        "palette": ("#fdf6e8", "#c8342b"),
    },
}

QUALITY_SUFFIX = (
    "high quality, professional, balanced composition, centered subject, "
    "ample headroom for text overlay, no text, no letters, no watermark, no logo"
)

RATIOS: dict[str, tuple[int, int]] = {
    "2.35:1": (1410, 600),
    "1:1": (900, 900),
    "16:9": (1280, 720),
    "4:3": (1200, 900),
    "3:2": (1200, 800),
}

FONT_CANDIDATES = [
    r"C:\Windows\Fonts\msyhbd.ttc",
    r"C:\Windows\Fonts\msyh.ttc",
    r"C:\Windows\Fonts\simhei.ttf",
    r"C:\Windows\Fonts\NotoSansSC-VF.ttf",
    "/System/Library/Fonts/PingFang.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
]


def find_font() -> str | None:
    for p in FONT_CANDIDATES:
        if Path(p).exists():
            return p
    return None


def _size_for(ratio: str) -> tuple[int, int]:
    return RATIOS.get(ratio, (1280, 720))


def _align8(n: int) -> int:
    return max(64, int(round(n / 8)) * 8)


# --------------------------------------------------------------- 各后端实现
def _gen_pollinations(prompt: str, w: int, h: int, seed: int, cfg: dict) -> bytes:
    model = cfg["image"].get("pollinations_model") or "flux"
    base = cfg["image"].get("pollinations_base") or "https://image.pollinations.ai/prompt/"
    q = urllib.parse.quote(prompt, safe="")
    url = (
        f"{base}{q}?width={_align8(w)}&height={_align8(h)}&seed={seed}"
        f"&model={model}&nologo=true&safe=true&enhance=false"
    )
    data = http_request(
        url,
        headers={"Referer": "https://pollinations.ai/", "Accept": "image/*"},
        timeout=cfg["image"].get("request_timeout", 150),
        retries=3,
        retry_sleep=8,
        raw=True,
    )
    if not data[:3] == b"\xff\xd8\xff" and not data[:8] == b"\x89PNG\r\n\x1a\n":
        raise RuntimeError(f"返回的不是图片: {data[:120]!r}")
    return data


def _gen_pollinations_alt(prompt: str, w: int, h: int, seed: int, cfg: dict) -> bytes:
    q = urllib.parse.quote(prompt.replace(" ", "_"), safe="")
    url = f"https://pollinations.ai/p/{q}?width={_align8(w)}&height={_align8(h)}&seed={seed}&nologo=true"
    data = http_request(url, headers={"Referer": "https://pollinations.ai/"}, timeout=150, retries=2, raw=True)
    if not data[:3] == b"\xff\xd8\xff" and not data[:8] == b"\x89PNG\r\n\x1a\n":
        raise RuntimeError("alt 返回非图片")
    return data


def _gen_siliconflow(prompt: str, w: int, h: int, seed: int, cfg: dict) -> bytes:
    key = cfg["image"].get("siliconflow_key")
    if not key:
        raise RuntimeError("未配置 siliconflow_key")
    model = cfg["image"].get("siliconflow_model") or "Kwai-Kolors/Kolors"
    payload = {
        "model": model,
        "prompt": prompt,
        "image_size": f"{_align8(w)}x{_align8(h)}",
        "batch_size": 1,
        "seed": seed,
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    txt = http_request(
        "https://api.siliconflow.cn/v1/images/generations",
        method="POST",
        data=body,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        timeout=150,
    )
    j = json.loads(txt)
    if "images" not in j:
        raise RuntimeError(f"siliconflow 返回异常: {txt[:220]}")
    return http_request(j["images"][0]["url"], timeout=120, raw=True)


def _gen_cloudflare(prompt: str, w: int, h: int, seed: int, cfg: dict) -> bytes:
    acct = cfg["image"].get("cf_account_id")
    tok = cfg["image"].get("cf_token")
    if not acct or not tok:
        raise RuntimeError("未配置 cf_account_id / cf_token")
    url = (
        f"https://api.cloudflare.com/client/v4/accounts/{acct}"
        "/ai/run/@cf/black-forest-labs/flux-1-schnell"
    )
    body = json.dumps({"prompt": prompt, "steps": 4, "seed": seed}).encode("utf-8")
    txt = http_request(
        url,
        method="POST",
        data=body,
        headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"},
        timeout=150,
    )
    j = json.loads(txt)
    b64 = (j.get("result") or {}).get("image")
    if not b64:
        raise RuntimeError(f"cloudflare 返回异常: {txt[:220]}")
    return base64.b64decode(b64)


def _gen_huggingface(prompt: str, w: int, h: int, seed: int, cfg: dict) -> bytes:
    tok = cfg["image"].get("hf_token")
    if not tok:
        raise RuntimeError("未配置 hf_token")
    model = cfg["image"].get("hf_model") or "black-forest-labs/FLUX.1-schnell"
    body = json.dumps({"inputs": prompt, "parameters": {"width": _align8(w), "height": _align8(h)}}).encode()
    data = http_request(
        f"https://api-inference.huggingface.co/models/{model}",
        method="POST",
        data=body,
        headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"},
        timeout=150,
        retries=2,
        raw=True,
    )
    if data[:1] == b"{":
        raise RuntimeError(f"hf 返回错误: {data[:220]!r}")
    return data


# ----------------------------------------------------- 本地 / 局域网模型
LOCAL_PORTS = (7860, 7861, 8188, 1234, 8000, 8080, 5000, 3000, 11434, 8501)


def detect_local_base(cfg: dict) -> str | None:
    """探测本机常见推理端口（A1111/Forge 7860、ComfyUI 8188、OpenAI 兼容 1234/8000…）。"""
    import socket

    explicit = (cfg["image"].get("local_base") or "").strip()
    if explicit:
        return explicit.rstrip("/")
    if not cfg["image"].get("auto_detect_local", True):
        return None
    for port in LOCAL_PORTS:
        s = socket.socket()
        s.settimeout(0.3)
        try:
            if s.connect_ex(("127.0.0.1", port)) == 0:
                return f"http://127.0.0.1:{port}"
        finally:
            s.close()
    return None


def _local_kind(cfg: dict, base: str) -> str:
    kind = (cfg["image"].get("local_kind") or "auto").strip().lower()
    if kind in ("openai", "a1111"):
        return kind
    # auto：A1111 有 /sdapi 特征；否则按 OpenAI 兼容处理
    try:
        txt = http_request(f"{base}/sdapi/v1/options", timeout=5, retries=1)
        if "sd_model_checkpoint" in txt or "{" in txt:
            return "a1111"
    except Exception:
        pass
    return "openai"


def _gen_local_a1111(prompt: str, w: int, h: int, seed: int, cfg: dict, base: str) -> bytes:
    payload = {
        "prompt": prompt,
        "negative_prompt": cfg["image"].get("negative_prompt", ""),
        "width": _align8(w),
        "height": _align8(h),
        "steps": int(cfg["image"].get("local_steps") or 26),
        "cfg_scale": float(cfg["image"].get("local_cfg") or 7.0),
        "seed": seed,
        "sampler_name": "DPM++ 2M Karras",
    }
    txt = http_request(
        f"{base}/sdapi/v1/txt2img",
        method="POST",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        timeout=cfg["image"].get("request_timeout", 150),
    )
    j = json.loads(txt)
    imgs = j.get("images") or []
    if not imgs:
        raise RuntimeError(f"a1111 返回异常: {txt[:200]}")
    raw = imgs[0].split(",", 1)[-1]
    return base64.b64decode(raw)


def _gen_local_openai(prompt: str, w: int, h: int, seed: int, cfg: dict, base: str) -> bytes:
    payload = {
        "prompt": prompt,
        "n": 1,
        "size": f"{_align8(w)}x{_align8(h)}",
        "response_format": "b64_json",
    }
    model = cfg["image"].get("local_model")
    if model:
        payload["model"] = model
    txt = http_request(
        f"{base}/v1/images/generations",
        method="POST",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        timeout=cfg["image"].get("request_timeout", 150),
    )
    j = json.loads(txt)
    item = (j.get("data") or [{}])[0]
    if item.get("b64_json"):
        return base64.b64decode(item["b64_json"])
    if item.get("url"):
        return http_request(item["url"], timeout=120, raw=True)
    raise RuntimeError(f"local openai 返回异常: {txt[:200]}")


def _make_local_backend(kind: str):
    def _fn(prompt: str, w: int, h: int, seed: int, cfg: dict) -> bytes:
        base = detect_local_base(cfg)
        if not base:
            raise RuntimeError("未发现本地模型（请在 config 里设 local_base）")
        real = _local_kind(cfg, base) if kind == "auto" else kind
        if real == "a1111":
            return _gen_local_a1111(prompt, w, h, seed, cfg, base)
        return _gen_local_openai(prompt, w, h, seed, cfg, base)

    return _fn


def _gen_local_svg(prompt: str, w: int, h: int, seed: int, cfg: dict, palette=("#ffffff", "#111111")) -> bytes:
    """离线兜底：渐变 + 几何形状卡片。"""
    bg, fg = palette
    img = Image.new("RGB", (_align8(w), _align8(h)), bg)
    d = ImageDraw.Draw(img, "RGBA")
    W, H = img.size
    rnd = random.Random(seed or 42)
    bg_rgb = tuple(int(bg.lstrip("#")[i : i + 2], 16) for i in (0, 2, 4))
    fg_rgb = tuple(int(fg.lstrip("#")[i : i + 2], 16) for i in (0, 2, 4))
    for y in range(H):  # 竖向渐变
        t = y / max(1, H - 1)
        d.line(
            [(0, y), (W, y)],
            fill=tuple(int(bg_rgb[i] + (fg_rgb[i] - bg_rgb[i]) * t * 0.35) for i in range(3)),
        )
    for _ in range(9):  # 半透明几何形状
        cx, cy = rnd.randint(0, W), rnd.randint(0, H)
        r = rnd.randint(int(min(W, H) * 0.08), int(min(W, H) * 0.30))
        col = fg_rgb + (rnd.randint(18, 55),)
        kind = rnd.choice(["ellipse", "rect", "line"])
        if kind == "ellipse":
            d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=col)
        elif kind == "rect":
            d.rectangle(
                [cx - r, cy - int(r * 0.6), cx + r, cy + int(r * 0.6)],
                fill=col,
                outline=fg_rgb + (110,),
                width=2,
            )
        else:
            d.line([cx - r, cy, cx + r, cy + rnd.randint(-r, r)], fill=fg_rgb + (120,), width=rnd.randint(2, 6))
    img = img.filter(ImageFilter.GaussianBlur(0.6))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=90)
    return buf.getvalue()


# ------------------------------------------------------------ 外置生图 API
# 想接自己的生图服务？不用改代码，在 config 里填 image.custom 就行。
#
# 设计目标：任何「发一个 HTTP 请求 → 拿回一张图」的接口都能接。
#   · URL / 请求头 / 请求体里都可以写占位符：{prompt} {width} {height} {seed} {negative_prompt}
#   · 响应可以是 JSON，也可以是图片本身（自动按魔数识别）
#   · JSON 里的图片字段可以是 URL（自动下载）或 base64（自动解码）
#   · 常见返回结构会被自动猜；猜不准就用 response_path 显式指定，如 "data.0.b64_json"
#
# 示例（OpenAI 兼容）：
#   "custom": {
#     "url": "https://api.example.com/v1/images/generations",
#     "method": "POST",
#     "headers": {"Authorization": "Bearer sk-xxx", "Content-Type": "application/json"},
#     "body": {"model": "flux-schnell", "prompt": "{prompt}",
#              "width": "{width}", "height": "{height}", "response_format": "b64_json"},
#     "response_path": "data.0.b64_json"
#   }
# 示例（GET 直出图片）：
#   "custom": {
#     "url": "https://api.example.com/render?prompt={prompt}&w={width}&h={height}",
#     "method": "GET"
#   }


def _looks_like_image(b: bytes) -> bool:
    return (
        b.startswith(b"\x89PNG")
        or b.startswith(b"\xff\xd8\xff")          # JPEG
        or b.startswith(b"GIF8")
        or (b[:4] == b"RIFF" and b[8:12] == b"WEBP")
        or b.lstrip()[:5].lower() == b"<svg "
    )


def _dig(obj, path: str):
    """按 'data.0.b64_json' 这种点号路径取值，数字段当下标用。"""
    cur = obj
    for part in str(path).split("."):
        if part == "":
            continue
        if isinstance(cur, list):
            cur = cur[int(part)]
        elif isinstance(cur, dict):
            if part not in cur:
                raise KeyError(path)
            cur = cur[part]
        else:
            raise KeyError(path)
    return cur


def _render_tpl(obj, variables: dict):
    """递归替换字符串里的 {占位符}。"""
    if isinstance(obj, str):
        out = obj
        for k, v in variables.items():
            out = out.replace("{" + k + "}", str(v))
        return out
    if isinstance(obj, dict):
        return {k: _render_tpl(v, variables) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_render_tpl(v, variables) for v in obj]
    return obj


def _expand_env(obj):
    """把 ${ENV_VAR} 换成环境变量值。

    方便把密钥放在环境变量里而不是写进 config，例如：
        "headers": {"Authorization": "Bearer ${MY_IMAGE_KEY}"}
    """
    import os

    if isinstance(obj, str):
        return os.path.expandvars(obj)
    if isinstance(obj, dict):
        return {k: _expand_env(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_expand_env(v) for v in obj]
    return obj


def _guess_response_path(j) -> str:
    """常见返回结构的兜底猜测。"""
    for p in ("data.0.b64_json", "data.0.url", "images.0.url", "images.0",
              "output.0", "result.0", "url", "image", "b64_json"):
        try:
            v = _dig(j, p)
        except Exception:
            continue
        if isinstance(v, str) and v.strip():
            return p
    raise RuntimeError(
        "拿不到图片字段，请在 config 的 image.custom.response_path 里显式指定路径"
    )


def _gen_custom(prompt: str, w: int, h: int, seed: int, cfg: dict) -> bytes:
    c = (cfg.get("image", {}) or {}).get("custom") or {}
    url = (c.get("url") or "").strip()
    if not url:
        raise RuntimeError("未配置 image.custom.url")
    if c.get("enabled") is False:
        raise RuntimeError("image.custom.enabled = false")

    variables = {
        "prompt": prompt,
        "width": _align8(w),
        "height": _align8(h),
        "seed": seed,
        "negative_prompt": cfg["image"].get("negative_prompt", "") or "",
    }
    timeout = int(c.get("timeout") or cfg["image"].get("request_timeout", 150) or 150)
    headers = _expand_env(_render_tpl(
        c.get("headers") or {"Content-Type": "application/json"}, variables))
    method = (c.get("method") or "POST").upper()

    kwargs = {"method": method, "headers": headers, "timeout": timeout, "raw": True}
    if method != "GET":
        body = _expand_env(_render_tpl(c.get("body") or {"prompt": "{prompt}"}, variables))
        kwargs["data"] = json.dumps(body, ensure_ascii=False).encode("utf-8")

    raw = http_request(_expand_env(_render_tpl(url, variables)), **kwargs)

    if _looks_like_image(raw):
        return raw

    try:
        j = json.loads(raw.decode("utf-8", errors="replace"))
    except Exception:
        raise RuntimeError(f"外置接口返回既不是图片也不是 JSON：{raw[:120]!r}") from None

    val = _dig(j, c.get("response_path") or _guess_response_path(j))
    if not isinstance(val, str):
        raise RuntimeError(f"图片字段不是字符串：{type(val).__name__}")
    if val.startswith("data:"):            # data:image/png;base64,xxxx
        val = val.split(",", 1)[-1]
    if val.startswith(("http://", "https://")):
        return http_request(val, timeout=timeout, raw=True)
    try:
        return base64.b64decode(val)
    except Exception as e:
        raise RuntimeError(f"图片字段既不是 URL 也不是合法 base64：{e}") from None


BACKENDS = {
    "custom": _gen_custom,
    "pollinations": _gen_pollinations,
    "pollinations-alt": _gen_pollinations_alt,
    "siliconflow": _gen_siliconflow,
    "cloudflare": _gen_cloudflare,
    "huggingface": _gen_huggingface,
    "local": _make_local_backend("auto"),
    "local-a1111": _make_local_backend("a1111"),
    "local-openai": _make_local_backend("openai"),
}
# 远程免费后端优先；本地模型若有则排在最前（更快、可控）；local-svg 永远兜底。
# custom 放最前：用户一旦配了自己的接口，就是明确想用它。
CHAIN_ORDER = [
    "custom", "local", "pollinations", "pollinations-alt", "siliconflow",
    "cloudflare", "huggingface", "local-svg",
]


def _available(name: str, cfg: dict) -> bool:
    """配置型后端没配就静默跳过，别在降级日志里刷存在感。"""
    if name == "custom":
        c = (cfg.get("image", {}) or {}).get("custom") or {}
        return bool((c.get("url") or "").strip()) and c.get("enabled") is not False
    return True


def generate(prompt: str, w: int, h: int, seed: int, cfg: dict, palette, style_id: str) -> tuple[bytes, str]:
    """按降级链生成，返回 (图片字节, 使用的后端)。"""
    backend = (cfg["image"].get("backend") or "auto").strip()
    chain = [backend] if backend and backend != "auto" else CHAIN_ORDER
    errors = []
    for name in chain:
        if not _available(name, cfg):
            continue
        try:
            if name == "local-svg":
                return _gen_local_svg(prompt, w, h, seed, cfg, palette), name
            fn = BACKENDS.get(name)
            if not fn:
                continue
            data = fn(prompt, w, h, seed, cfg)
            if name.startswith("pollinations"):
                time.sleep(float(cfg["image"].get("rate_limit_sleep") or 16))
            return data, name
        except Exception as e:  # noqa: BLE001
            errors.append(f"{name}: {str(e)[:160]}")
            print(f"  [fallback] {name} 失败 → {str(e)[:120]}")
    print("  [fallback] 全部远程后端失败，使用本地兜底")
    if errors:
        print("  [detail] " + " | ".join(errors[-3:]))
    return _gen_local_svg(prompt, w, h, seed, cfg, palette), "local-svg"


# ------------------------------------------------------------------ 后处理
# 免费档（Pollinations 匿名）会在右下角打 pollinations.ai 水印。
# 对策：按目标尺寸放大请求，再把右侧/底部裁掉，水印正好落在裁剪区外。
WATERMARK_TRIM = (0.165, 0.125)  # (裁掉右侧比例, 裁掉底部比例)
SUPERSAMPLE = 0.84  # 请求尺寸 = 目标 / SUPERSAMPLE


def fit_image(
    data: bytes, w: int, h: int, max_bytes: int = 900 * 1024, trim: tuple[float, float] = (0.0, 0.0)
) -> Image.Image:
    """先按 trim 比例裁掉右/下边缘（去水印），再居中裁剪到目标比例并缩放。"""
    img = Image.open(io.BytesIO(data)).convert("RGB")
    iw, ih = img.size
    tr, tb = trim
    if tr > 0 or tb > 0:
        img = img.crop((0, 0, max(8, int(iw * (1 - tr))), max(8, int(ih * (1 - tb)))))
        iw, ih = img.size
    tw, th = _align8(w), _align8(h)
    target = tw / th
    cur = iw / ih
    if abs(cur - target) > 0.01:  # 居中裁剪
        if cur > target:
            nw = int(ih * target)
            left = (iw - nw) // 2
            img = img.crop((left, 0, left + nw, ih))
        else:
            nh = int(iw / target)
            top = (ih - nh) // 2
            img = img.crop((0, top, iw, top + nh))
    if img.size != (tw, th):
        img = img.resize((tw, th), Image.LANCZOS)
    return img


def request_size(w: int, h: int) -> tuple[int, int]:
    """放大请求尺寸，留出裁掉水印的余量。"""
    return _align8(int(w / SUPERSAMPLE)), _align8(int(h / SUPERSAMPLE))


def _wrap_cjk(draw, text, font, max_w):
    """按宽度折行；标题里显式写的 \\n 强制换行（封面手动词行用得上）。"""
    lines = []
    for para in str(text).split("\n"):
        cur = ""
        for ch in para:
            if draw.textlength(cur + ch, font=font) <= max_w:
                cur += ch
            else:
                lines.append(cur)
                cur = ch
        lines.append(cur)
    lines = [l for l in lines if l]
    return lines or [""]


def decorate_cover(img: Image.Image, title: str, subtitle: str = "", accent: str = "#ffffff") -> Image.Image:
    """给封面叠一层底部渐变蒙版 + 大标题，保证可读性。"""
    font_path = find_font()
    if not font_path:
        return img
    img = img.convert("RGBA")
    W, H = img.size
    scrim = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sd = ImageDraw.Draw(scrim)
    band = int(H * 0.62)
    for i in range(band, H):  # 底部渐变黑
        t = (i - band) / max(1, H - band)
        sd.line([(0, i), (W, i)], fill=(0, 0, 0, int(215 * (t ** 0.8))))
    scrim = scrim.filter(ImageFilter.GaussianBlur(1.2))
    img = Image.alpha_composite(img, scrim)

    d = ImageDraw.Draw(img)
    fsize = max(26, int(H * 0.115))
    font = ImageFont.truetype(font_path, fsize)
    sub_font = ImageFont.truetype(font_path, max(16, int(fsize * 0.42)))
    max_w = W - int(W * 0.10)
    lines = _wrap_cjk(d, title, font, max_w)[:3]
    block_h = len(lines) * int(fsize * 1.28) + (int(fsize * 0.7) if subtitle else 0)
    y = H - int(H * 0.13) - block_h
    for ln in lines:
        d.text((int(W * 0.05) + 2, y + 2), ln, font=font, fill=(0, 0, 0, 130))
        d.text((int(W * 0.05), y), ln, font=font, fill=(255, 255, 255, 255))
        y += int(fsize * 1.28)
    if subtitle:
        d.text((int(W * 0.05) + 1, y + 1), subtitle, font=sub_font, fill=(0, 0, 0, 120))
        d.text((int(W * 0.05), y), subtitle, font=sub_font, fill=accent)
    return img.convert("RGB")


def save_jpeg(img: Image.Image, path: Path, max_bytes: int = 900 * 1024) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    for q in (92, 88, 84, 80, 74, 68, 60):
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=q, optimize=True, progressive=True)
        if buf.tell() <= max_bytes:
            path.write_bytes(buf.getvalue())
            return buf.tell()
    path.write_bytes(buf.getvalue())
    return buf.tell()


# --------------------------------------------------------------------- main
def build_prompt(style_id: str, subject: str, role: str, extra: str = "") -> str:
    """组装提示词。顺序很重要：主体描述放最前，风格前缀随后——
    实测主体在前时画面贴合度明显更高（风格词放前面会让模型只顾氛围、忽略主体）。"""
    st = STYLES.get(style_id) or STYLES["minimal-line"]
    parts = [subject.strip(), st["prompt"]]
    if extra:
        parts.append(extra.strip())
    parts.append(QUALITY_SUFFIX)
    p = ", ".join(x for x in parts if x)
    if role == "cover":
        p += ", no people, no human figures, no faces, no text, no letters, no writing, no caption"
    return p


def main() -> int:
    ap = argparse.ArgumentParser(description="微信公众号配图生成器")
    ap.add_argument("--spec", help="批量 spec JSON 路径")
    ap.add_argument("--outdir", default="images", help="输出目录（默认 images）")
    ap.add_argument("--style", default=None, help=f"风格 id，可选: {', '.join(STYLES)}")
    ap.add_argument("--ratio", default="16:9", choices=list(RATIOS))
    ap.add_argument("--subject", help="单张模式：主体描述")
    ap.add_argument("--title", default="", help="封面叠加文字")
    ap.add_argument("--subtitle", default="", help="封面副标题")
    ap.add_argument("--caption", default="", help="内文图说明")
    ap.add_argument("--role", default="auto", choices=["auto", "cover", "inline"])
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("-o", "--output", help="单张模式输出文件路径")
    ap.add_argument("--no-text", action="store_true", help="封面不叠加文字")
    ap.add_argument("--palette", default=None, help=f"图示配色，可选: {', '.join(PALETTES)}")
    ap.add_argument("--list-styles", action="store_true")
    ap.add_argument("--list-recipes", action="store_true", help="列出内置图示类型")
    args = ap.parse_args()

    if args.list_styles:
        for k, v in STYLES.items():
            print(f"  {k:16s} {v['label']}")
        return 0

    if args.list_recipes:
        print("内置图示（由代码绘制，干净可控，非 AI 生成）：")
        for k in list_recipes():
            print(f"  {k}")
        print(f"\n配色：{', '.join(PALETTES)}")
        return 0

    cfg = load_config()
    default_style = args.style or cfg.get("default_style") or "minimal-line"

    # 组装任务列表
    spec: dict = {}
    if args.spec:
        spec = json.loads(Path(args.spec).read_text(encoding="utf-8"))
        base_style = args.style or spec.get("style") or default_style
        tasks = spec.get("images") or []
        if not tasks:
            print("[error] spec 里没有 images")
            return 2
    else:
        if not args.subject:
            ap.error("单张模式需要 --subject")
        base_style = default_style
        role = args.role if args.role != "auto" else ("cover" if args.title else "inline")
        tasks = [
            {
                "id": "image",
                "role": role,
                "ratio": args.ratio,
                "subject": args.subject,
                "title": args.title,
                "subtitle": args.subtitle,
                "caption": args.caption,
                "seed": args.seed,
            }
        ]

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    manifest = []
    print(f"[gen] 共 {len(tasks)} 张，默认风格 = {base_style}")

    for i, t in enumerate(tasks, 1):
        style_id = t.get("style") or base_style
        role = t.get("role") or "inline"
        ratio = t.get("ratio") or ("2.35:1" if role == "cover" else "16:9")
        w, h = _size_for(ratio)
        seed = t.get("seed") or random.randint(1, 99999999)
        name = t.get("id") or f"img{i}"
        outfile = Path(args.output) if (args.output and len(tasks) == 1) else outdir / f"{name}.jpg"

        # —— 内置图示引擎：由代码绘制，干净可控，不走网络 ——
        recipe = t.get("render") or spec.get("render")
        if recipe:
            palette = (
                args.palette or t.get("palette") or spec.get("palette")
                or cfg["image"].get("diagram_palette") or "ink-blue"
            )
            if recipe not in list_recipes():
                print(f"[{i}/{len(tasks)}] {name} · [warn] 未知图示类型 {recipe}，跳过")
                continue
            if not has_cjk_font():
                print("  [warn] 未找到中文字体，图示文字可能显示异常")
            print(f"[{i}/{len(tasks)}] {name} · diagram:{recipe} · {ratio} · palette={palette}")
            img = render_diagram(recipe, dict(t), w, h, palette=palette)
            size = save_jpeg(img, outfile)
            manifest.append({
                "id": name, "role": role, "style": style_id, "ratio": ratio,
                "width": img.size[0], "height": img.size[1], "file": str(outfile.as_posix()),
                "bytes": size, "KB": round(size / 1024, 1), "backend": f"diagram:{recipe}",
                "palette": palette, "seed": None, "prompt": None, "caption": t.get("caption", ""),
            })
            print(f"      → {outfile}  {manifest[-1]['KB']}KB  backend=diagram:{recipe}")
            continue

        subject = t.get("subject") or t.get("title") or "abstract concept"
        prompt = t.get("prompt") or build_prompt(style_id, subject, role)

        print(f"[{i}/{len(tasks)}] {name} · {style_id} · {ratio} · seed={seed}")
        rw, rh = request_size(w, h)
        data, backend = generate(prompt, rw, rh, seed, cfg, STYLES.get(style_id, {}).get("palette", ("#fff", "#111")), style_id)
        trim = WATERMARK_TRIM if backend.startswith("pollinations") else (0.0, 0.0)
        img = fit_image(data, w, h, trim=trim)
        if role == "cover" and t.get("title") and not args.no_text:
            img = decorate_cover(img, t["title"], t.get("subtitle", ""), STYLES.get(style_id, {}).get("palette", ("#fff", "#fff"))[1])
        size = save_jpeg(img, outfile)
        item = {
            "id": name,
            "role": role,
            "style": style_id,
            "ratio": ratio,
            "width": img.size[0],
            "height": img.size[1],
            "file": str(outfile.as_posix()),
            "bytes": size,
            "KB": round(size / 1024, 1),
            "backend": backend,
            "seed": seed,
            "prompt": prompt,
            "caption": t.get("caption", ""),
        }
        manifest.append(item)
        print(f"      → {outfile}  {item['KB']}KB  backend={backend}")

    mf_path = outdir / "manifest.json"
    mf_path.write_text(json.dumps({"images": manifest}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[done] manifest: {mf_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
