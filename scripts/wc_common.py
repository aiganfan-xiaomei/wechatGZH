#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""wechat-article 共享工具：配置、HTTP、路径。"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

# ---------------------------------------------------------------- 控制台编码
try:  # Windows 控制台默认 GBK，会炸中文
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

SKILL_DIR = Path(__file__).resolve().parent.parent

API_BASE = "https://api.weixin.qq.com"

DEFAULT_HOME = Path.home() / ".workbuddy" / "wechat-article"


def home_dir() -> Path:
    h = os.environ.get("WECHAT_ARTICLE_HOME")
    p = Path(h).expanduser() if h else DEFAULT_HOME
    p.mkdir(parents=True, exist_ok=True)
    return p


def config_path() -> Path:
    return home_dir() / "config.json"


DEFAULT_CONFIG = {
    "appid": "",
    "secret": "",
    "author": "",
    "default_theme": "professional-clean",
    "default_style": "minimal-line",
    "image": {
        "backend": "auto",
        "pollinations_model": "flux",
        "pollinations_base": "https://image.pollinations.ai/prompt/",
        "siliconflow_key": "",
        "siliconflow_model": "Kwai-Kolors/Kolors",
        "cf_account_id": "",
        "cf_token": "",
        "hf_token": "",
        "hf_model": "black-forest-labs/FLUX.1-schnell",
        "request_timeout": 150,
        "rate_limit_sleep": 16,
        # 通用负向提示词（本地模型/A1111 会真正生效）
        "negative_prompt": (
            "text, letters, words, captions, watermark, signature, logo, "
            "low quality, blurry, jpeg artifacts, cluttered"
        ),
        # 本地/局域网模型（OpenAI 兼容 /v1/images/generations 或 A1111 SD-WebUI/Forge）
        "local_kind": "auto",       # auto | openai | a1111
        "local_base": "",           # 例如 http://127.0.0.1:7860
        "local_model": "",          # openai 兼容端点的 model 名，可留空
        "local_steps": 26,
        "local_cfg": 7.0,
        "auto_detect_local": True,  # 自动探测常见本地端口
        # 外置生图 API（通用接口，见 docs/images.md）
        # 任何「发请求 → 拿回图片」的服务都能接：URL/请求头/请求体里可写
        # {prompt} {width} {height} {seed}，密钥可写成 ${ENV_VAR} 走环境变量。
        "custom": {
            "enabled": True,        # url 填了才真正生效
            "url": "",             # 例如 https://api.example.com/v1/images/generations
            "method": "POST",      # GET | POST
            "headers": {},         # 例如 {"Authorization": "Bearer ${MY_IMAGE_KEY}"}
            "body": {},            # 例如 {"model": "flux-schnell", "prompt": "{prompt}"}
            "response_path": "",   # 例如 data.0.b64_json；留空自动猜
            "timeout": 150,
        },
        # 内置极简图示引擎的默认配色
        "diagram_palette": "ink-blue",
    },
}


def _deep_merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_config() -> dict:
    """读取 ~/.workbuddy/wechat-article/config.json，缺失字段用默认值补全。"""
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))  # deep copy
    p = config_path()
    if p.exists():
        try:
            cfg = _deep_merge(cfg, json.loads(p.read_text(encoding="utf-8")))
        except Exception as e:
            print(f"[warn] config.json 解析失败，使用默认配置: {e}")
    # 环境变量兜底
    env_map = {
        ("appid",): "WECHAT_APPID",
        ("secret",): "WECHAT_SECRET",
        ("author",): "WECHAT_AUTHOR",
    }
    for path, env in env_map.items():
        if not cfg.get(path[0]) and os.environ.get(env):
            cfg[path[0]] = os.environ[env]
    img_env = {
        "siliconflow_key": "SILICONFLOW_API_KEY",
        "cf_account_id": "CF_ACCOUNT_ID",
        "cf_token": "CF_API_TOKEN",
        "hf_token": "HF_TOKEN",
    }
    for k, env in img_env.items():
        if not cfg["image"].get(k) and os.environ.get(env):
            cfg["image"][k] = os.environ[env]
    return cfg


def save_config(cfg: dict) -> None:
    config_path().write_text(
        json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def http_request(
    url: str,
    *,
    method: str = "GET",
    data: bytes | None = None,
    headers: dict | None = None,
    timeout: int = 60,
    retries: int = 3,
    retry_sleep: float = 3.0,
    raw: bool = False,
):
    """带重试的 HTTP 请求。raw=True 时返回 bytes，否则返回解码后的文本。"""
    hdrs = {"User-Agent": UA}
    if headers:
        hdrs.update(headers)
    last = None
    for attempt in range(retries):
        req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                body = r.read()
                if raw:
                    return body
                return body.decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            body = b""
            try:
                body = e.read()
            except Exception:
                pass
            last = f"HTTP {e.code}: {body[:300].decode('utf-8', errors='replace') or e.reason}"
            # 4xx（非 429）不重试
            if e.code not in (408, 429, 500, 502, 503, 504):
                break
        except Exception as e:  # noqa: BLE001
            last = f"{type(e).__name__}: {e}"
        if attempt < retries - 1:
            time.sleep(retry_sleep * (attempt + 1))
    raise RuntimeError(f"请求失败 {url[:90]} … → {last}")


def post_json(url: str, payload, *, headers: dict | None = None, timeout: int = 60):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    hdrs = {"Content-Type": "application/json; charset=utf-8"}
    if headers:
        hdrs.update(headers)
    txt = http_request(url, method="POST", data=body, headers=hdrs, timeout=timeout)
    return json.loads(txt)


def multipart(fields: dict, files: dict) -> tuple[bytes, str]:
    """构造 multipart/form-data。files: {field: (filename, bytes, mime)}"""
    boundary = "----WCArticleBoundary" + str(int(time.time() * 1000))
    buf = bytearray()
    for k, v in (fields or {}).items():
        buf += f"--{boundary}\r\n".encode()
        buf += f'Content-Disposition: form-data; name="{k}"\r\n\r\n'.encode()
        buf += f"{v}\r\n".encode("utf-8")
    for k, (fn, content, mime) in (files or {}).items():
        buf += f"--{boundary}\r\n".encode()
        buf += (
            f'Content-Disposition: form-data; name="{k}"; filename="{fn}"\r\n'
        ).encode()
        buf += f"Content-Type: {mime}\r\n\r\n".encode()
        buf += content
        buf += b"\r\n"
    buf += f"--{boundary}--\r\n".encode()
    return bytes(buf), f"multipart/form-data; boundary={boundary}"


def jprint(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def egress_ip() -> str:
    """通用回显服务看到的出口 IP。

    注意：这只是"某个网站看到的地址"，**不等于微信看到的地址**。本机同时有
    IPv4/IPv6 出口时，回显服务可能给出另一个地址族。要填 IP 白名单请用
    `wechat_egress_ip()`。
    """
    for url in (
        "https://api.ipify.org",
        "https://ifconfig.me/ip",
        "https://icanhazip.com",
    ):
        try:
            return http_request(url, timeout=15, retries=1).strip()
        except Exception:
            continue
    return "unknown"


def wechat_egress_ip(appid: str, secret: str = "") -> str:
    """问微信本身「这个请求是从哪个 IP 进来的」——IP 白名单要填的正是这个值。

    为什么不能直接用 egress_ip()：那种回显服务返回的是它们各自看到的结果，
    本机同时具备 IPv4/IPv6 出口时可能给出与微信不同的地址族，照着填白名单会
    一直报 40164（"invalid ip ... not in whitelist"）。

    做法：故意发一个错 secret 的 token 请求。微信在 40164 的 errmsg 里会把实际
    来源 IP 回显出来，于是我们拿到的是**权威值**。
    若凭证是对的、请求成功，说明白名单已经生效，这时返回 "ok"。
    """
    if not appid:
        return "unknown"
    import re

    qs = urllib.parse.urlencode({
        "grant_type": "client_credential",
        "appid": appid,
        "secret": secret or "__ip_probe__",
    })
    try:
        body = http_request(f"{API_BASE}/cgi-bin/token?{qs}", timeout=20, retries=1)
    except Exception:
        return "unknown"
    if '"access_token"' in body:
        return "ok"
    m = re.search(r"invalid ip ([0-9a-fA-F:.]+)", body)
    return m.group(1) if m else "unknown"
