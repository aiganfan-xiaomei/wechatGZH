#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""微信公众号草稿箱发布管线。

子命令
------
  python publish.py ip                          查看本机出口 IP（填白名单用）
  python publish.py check                       校验凭证 + 白名单，定位 40164
  python publish.py token                       获取并缓存 access_token
  python publish.py upload-img <file>           上传正文图片 → 返回 mmbiz url
  python publish.py upload-thumb <file>         上传封面永久素材 → media_id
  python publish.py list [--count 20]           草稿列表
  python publish.py draft --article-json X.json 直接新增草稿
  python publish.py update --media-id ID --article-json X.json
  python publish.py delete --media-id ID
  python publish.py article article.md          一条龙：配图→排版→上传→进草稿箱
                  [--cover images/cover.jpg] [--theme X] [--style Y]
                  [--no-images] [--dry-run] [--keep-links]

配置：~/.workbuddy/wechat-article/config.json 的 appid / secret / author
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import sys
import time
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wc_common import (  # noqa: E402
    config_path,
    egress_ip,
    home_dir,
    http_request,
    jprint,
    load_config,
    multipart,
    post_json,
    wechat_egress_ip,
)

API = "https://api.weixin.qq.com"


# ------------------------------------------------------------------- token
def token_cache_path() -> Path:
    return home_dir() / "token.json"


def get_token(cfg: dict, force: bool = False) -> str:
    cp = token_cache_path()
    if not force and cp.exists():
        try:
            c = json.loads(cp.read_text(encoding="utf-8"))
            if c.get("appid") == cfg["appid"] and c.get("expire_at", 0) > time.time() + 60:
                return c["access_token"]
        except Exception:
            pass
    if not cfg.get("appid") or not cfg.get("secret"):
        raise SystemExit(
            f"[fatal] 缺少 appid/secret。请写入 {config_path()} 或设置 WECHAT_APPID/WECHAT_SECRET。"
        )
    url = (
        f"{API}/cgi-bin/token?grant_type=client_credential"
        f"&appid={urllib.parse.quote(cfg['appid'])}&secret={urllib.parse.quote(cfg['secret'])}"
    )
    txt = http_request(url, timeout=30, retries=2)
    j = json.loads(txt)
    if "access_token" not in j:
        raise SystemExit(f"[fatal] 获取 access_token 失败：{txt.strip()}\n" + explain(j))
    cp.write_text(
        json.dumps(
            {
                "appid": cfg["appid"],
                "access_token": j["access_token"],
                "expire_at": time.time() + int(j.get("expires_in", 7200)) - 200,
                "at": time.strftime("%Y-%m-%d %H:%M:%S"),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return j["access_token"]


def explain(j: dict) -> str:
    code = j.get("errcode")
    tips = {
        40164: "→ IP 不在白名单。把上面的 IP 加进 微信公众平台→开发管理→IP白名单，等 5~10 分钟再试。",
        40001: "→ access_token 无效，用 `publish.py token --force` 重新获取。",
        40125: "→ AppSecret 不正确，检查 config.json。",
        40013: "→ AppID 不正确。",
        48001: "→ 该账号类型无此接口权限（个人订阅号没有草稿箱接口）。",
        53503: "→ 草稿箱功能未开启，请在后台开启。",
        40005: "→ 图片格式不对，仅支持 jpg/png。",
        40009: "→ 图片尺寸过大，需 < 1MB。",
        45009: "→ 接口调用频率超限。",
    }
    return tips.get(code, "")


def call(path: str, cfg: dict, *, payload=None, raw_body=None, content_type=None, method="POST", query_extra=""):
    tk = get_token(cfg)
    url = f"{API}{path}?access_token={tk}{query_extra}"
    if raw_body is not None:
        txt = http_request(url, method=method, data=raw_body, headers={"Content-Type": content_type}, timeout=120)
    elif payload is not None:
        txt = http_request(
            url,
            method=method,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json; charset=utf-8"},
            timeout=120,
        )
    else:
        txt = http_request(url, method=method, timeout=120)
    try:
        j = json.loads(txt)
    except Exception:
        raise SystemExit(f"[fatal] 返回非 JSON：{txt[:400]}")
    if j.get("errcode") not in (0, None):
        raise SystemExit(f"[fatal] {path} 失败：{json.dumps(j, ensure_ascii=False)}\n{explain(j)}")
    return j


# --------------------------------------------------------------- 素材上传
def upload_content_image(path: Path, cfg: dict) -> str:
    data = path.read_bytes()
    if len(data) > 1024 * 1024:
        raise SystemExit(f"[fatal] {path.name} 为 {len(data)/1024:.0f}KB，超过 1MB 上限，先压缩。")
    mime = mimetypes.guess_type(path.name)[0] or "image/jpeg"
    body, ct = multipart({}, {"media": (path.name, data, mime)})
    j = call("/cgi-bin/media/uploadimg", cfg, raw_body=body, content_type=ct)
    return j["url"]


def upload_thumb(path: Path, cfg: dict) -> str:
    data = path.read_bytes()
    mime = mimetypes.guess_type(path.name)[0] or "image/jpeg"
    body, ct = multipart({}, {"media": (path.name, data, mime)})
    j = call("/cgi-bin/material/add_material", cfg, raw_body=body, content_type=ct, query_extra="&type=image")
    return j["media_id"]


# --------------------------------------------------------------- 一条龙
def cmd_article(args) -> int:
    cfg = load_config()
    md_path = Path(args.markdown).resolve()
    if not md_path.exists():
        raise SystemExit(f"[fatal] 找不到 {md_path}")
    workdir = md_path.parent
    build_dir = Path(args.outdir) if args.outdir else workdir / "build"
    build_dir.mkdir(parents=True, exist_ok=True)

    md_text = md_path.read_text(encoding="utf-8")
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import build_article as BA  # noqa: E402

    fm, _ = BA.split_frontmatter(md_text)
    title = args.title or fm.get("title", "")
    author = args.author or fm.get("author") or cfg.get("author", "")
    digest = args.digest or fm.get("digest", "")
    source_url = args.source_url or fm.get("source_url", "")
    theme = args.theme or fm.get("theme")
    cover = Path(args.cover).resolve() if args.cover else (
        (workdir / fm["cover"]).resolve() if fm.get("cover") else None
    )

    # 1. 配图（可选）
    if not args.no_images:
        spec = workdir / "images.json"
        if spec.exists():
            import subprocess

            print(f"[1/5] 生成配图（spec: {spec}）")
            r = subprocess.run(
                [sys.executable, str(Path(__file__).resolve().parent / "gen_images.py"),
                 "--spec", str(spec), "--outdir", str(workdir / "images"), "--style", args.style or ""],
                cwd=str(workdir),
            )
            if r.returncode != 0:
                print("[warn] 配图生成有失败项，继续用已有图片")
        else:
            print("[1/5] 未发现 images.json，跳过配图生成")

    # 2. 排版（先用本地路径）——排版内核与 build_article.py 完全一致
    print("[2/5] 排版 → 微信兼容 HTML")
    fragment, meta, theme_def = BA.build_fragment(md_text, theme, keep_h1=args.keep_h1)

    # 3. 上传正文图片（本地路径 → mmbiz url）
    img_map: dict[str, str] = {}
    if not args.dry_run:
        print("[3/5] 上传正文图片到微信")
        for src in sorted(set(__import__("re").findall(r'<img src="([^"]+)"', fragment))):
            if src.startswith("http"):
                continue
            p = (workdir / src).resolve() if not Path(src).is_absolute() else Path(src)
            if not p.exists():
                print(f"      [skip] 本地图片不存在: {src}")
                continue
            url = upload_content_image(p, cfg)
            img_map[src] = url
            print(f"      ✓ {src} → {url[:60]}…")
        if img_map:
            fragment, meta, theme_def = BA.build_fragment(
                md_text, theme, lambda s: img_map.get(s, s), keep_h1=args.keep_h1
            )
        # 4. 封面
        thumb_media_id = ""
        if cover and cover.exists():
            print("[4/5] 上传封面永久素材")
            thumb_media_id = upload_thumb(cover, cfg)
            print(f"      ✓ thumb_media_id={thumb_media_id}")
        else:
            print("[4/5] [warn] 未提供封面，thumb_media_id 为空（图文消息必填，草稿可能报错）")
    else:
        print("[3/5] --dry-run 跳过上传")
        print("[4/5] --dry-run 跳过封面上传")
        thumb_media_id = ""

    # 校验
    problems = []
    if not title:
        problems.append("缺少标题（frontmatter title 或 --title）")
    if title and len(title) > 32:
        problems.append(f"标题 {len(title)} 字 > 32")
    if author and len(author) > 16:
        problems.append(f"作者 {len(author)} 字 > 16")
    if digest and len(digest) > 120:
        problems.append(f"摘要 {len(digest)} 字 > 120")
    if meta["chars"] > 20000:
        problems.append(f"正文 {meta['chars']} 字 > 20000")

    result = {
        "title": title, "author": author, "digest": digest,
        "theme": meta["theme"], "chars": meta["chars"], "images": meta["images_count"],
        "source_url": source_url, "cover": str(cover) if cover else "",
        "problems": problems,
    }

    # 5. 进草稿箱
    if problems:
        print("[5/5] [abort] 校验不通过：")
        for p in problems:
            print(f"      - {p}")
        (build_dir / "publish-result.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        return 1

    article = {
        "article_type": "news",
        "title": title,
        "digest": digest,
        "content": fragment,
        "content_source_url": source_url,
        "need_open_comment": int(args.open_comment),
        "only_fans_can_comment": 0,
    }
    if author:
        article["author"] = author
    if thumb_media_id:
        article["thumb_media_id"] = thumb_media_id

    if args.dry_run:
        print("[5/5] --dry-run：不调用草稿接口")
        out = build_dir / "article.dryrun.json"
    else:
        print("[5/5] 写入草稿箱")
        j = call("/cgi-bin/draft/add", cfg, payload={"articles": [article]})
        result["media_id"] = j["media_id"]
        print(f"      ✓ 草稿 media_id = {j['media_id']}")
        out = build_dir / "publish-result.json"

    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    (build_dir / "article.html").write_text(fragment, encoding="utf-8")
    sub = (
        f"{author} · {meta['chars']} 字 · 主题 {meta['theme']}"
        if author
        else f"{meta['chars']} 字 · 主题 {meta['theme']}"
    )
    (build_dir / "preview.html").write_text(
        BA.preview_html(
            BA.preview_safe_fragment(fragment, workdir, build_dir), theme_def,
            title=title, subtitle=sub,
        ),
        encoding="utf-8",
    )
    print(f"[done] 产物：{out}")
    return 0


# ------------------------------------------------------------------- main
def main() -> int:
    ap = argparse.ArgumentParser(description="微信公众号草稿箱发布管线")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("ip", help="查看出口 IP")
    sub.add_parser("check", help="校验凭证与白名单")
    p = sub.add_parser("token", help="获取 access_token")
    p.add_argument("--force", action="store_true")

    p = sub.add_parser("upload-img")
    p.add_argument("file")
    p = sub.add_parser("upload-thumb")
    p.add_argument("file")

    p = sub.add_parser("list")
    p.add_argument("--count", type=int, default=20)

    p = sub.add_parser("draft")
    p.add_argument("--article-json", required=True)

    p = sub.add_parser("update")
    p.add_argument("--media-id", required=True)
    p.add_argument("--article-json", required=True)

    p = sub.add_parser("delete")
    p.add_argument("--media-id", required=True)

    p = sub.add_parser("article")
    p.add_argument("markdown")
    p.add_argument("--cover")
    p.add_argument("--theme")
    p.add_argument("--style")
    p.add_argument("--title")
    p.add_argument("--author")
    p.add_argument("--digest")
    p.add_argument("--source-url")
    p.add_argument("--outdir")
    p.add_argument("--no-images", action="store_true")
    p.add_argument("--keep-h1", action="store_true")
    p.add_argument("--open-comment", action="store_true")
    p.add_argument("--dry-run", action="store_true")

    args = ap.parse_args()
    cfg = load_config()

    if args.cmd == "ip":
        if cfg["appid"]:
            wip = wechat_egress_ip(cfg["appid"], cfg["secret"])
            if wip == "ok":
                print("[✓] 微信已能换到 access_token —— 白名单已生效，无需再改")
                return 0
            print(f"微信实际看到的出口 IP：{wip}")
            print("把它加入 微信公众平台 → 设置与开发 → 安全中心 → IP 白名单（约 5~10 分钟生效）")
            gip = egress_ip()
            if gip not in ("unknown", wip):
                print(f"（参考：通用回显服务看到的是 {gip}；不一致时以微信那个为准）")
        else:
            ip = egress_ip()
            print(f"本机出口 IP：{ip}   （仅通用回显；配置 appid 后能给出微信权威值）")
            print("把它加入 微信公众平台 → 设置与开发 → 安全中心 → IP 白名单（约 5~10 分钟生效）")
        return 0

    if args.cmd == "check":
        if cfg["appid"]:
            print(f"微信看到的出口 IP: {wechat_egress_ip(cfg['appid'], cfg['secret'])}")
        print(f"通用回显出口 IP: {egress_ip()}")
        print(f"appid : {cfg['appid'] or '(未配置)'}")
        print(f"secret: {'已配置' if cfg['secret'] else '(未配置)'}  config={config_path()}")
        if not cfg["appid"] or not cfg["secret"]:
            print("[x] 凭证不完整")
            return 1
        try:
            tk = get_token(cfg, force=True)
            print(f"[✓] access_token 获取成功：{tk[:18]}…")
            print("[✓] 凭证与白名单均正常，可以发布")
            return 0
        except SystemExit as e:
            print(str(e))
            return 1

    if args.cmd == "token":
        jprint({"access_token": get_token(cfg, force=args.force)})
        return 0

    if args.cmd == "upload-img":
        jprint({"url": upload_content_image(Path(args.file), cfg)})
        return 0

    if args.cmd == "upload-thumb":
        jprint({"media_id": upload_thumb(Path(args.file), cfg)})
        return 0

    if args.cmd == "list":
        jprint(call("/cgi-bin/draft/batchget", cfg,
                    payload={"offset": 0, "count": args.count, "no_content": 1}))
        return 0

    if args.cmd == "draft":
        payload = json.loads(Path(args.article_json).read_text(encoding="utf-8"))
        if "articles" not in payload:
            payload = {"articles": [payload]}
        jprint(call("/cgi-bin/draft/add", cfg, payload=payload))
        return 0

    if args.cmd == "update":
        payload = json.loads(Path(args.article_json).read_text(encoding="utf-8"))
        art = payload["articles"][0] if "articles" in payload else payload
        jprint(call("/cgi-bin/draft/update", cfg,
                    payload={"media_id": args.media_id, "index": 0, "articles": art}))
        return 0

    if args.cmd == "delete":
        jprint(call("/cgi-bin/draft/delete", cfg, payload={"media_id": args.media_id}))
        return 0

    if args.cmd == "article":
        return cmd_article(args)

    return 0


if __name__ == "__main__":
    sys.exit(main())
