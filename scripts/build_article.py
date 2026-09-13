#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Markdown → 微信公众号 HTML 构建（排版内核 = wewrite 移植版）。

用法
----
  python build_article.py article.md --outdir build --theme professional-clean
  python build_article.py article.md --outdir build --validate
  python build_article.py article.md --paste-safe        # 生成可直接粘贴编辑器的版本
  python build_article.py --list-themes

输入 Markdown 支持 YAML frontmatter：
---
title: 文章标题
author: 作者名
digest: 摘要（≤120字，留空自动截取）
cover: images/cover.jpg
theme: professional-clean
source_url: https://github.com/...
---

产出
----
  <outdir>/article.html          # 正文片段（全内联样式，可直接作为 draft content）
  <outdir>/preview.html          # 独立预览页（浏览器打开，手机宽度卡片）
  <outdir>/meta.json             # title/author/digest/theme/外链脚注/字数/校验结果
  <outdir>/article.paste.html    # 仅当 --paste-safe：文本节点加 <span leaf="">
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wc_common import jprint  # noqa: E402
from wc_converter import WeChatConverter, make_paste_safe, preview_html  # noqa: E402
from wc_theme import Theme, list_themes, load_theme, theme_meta  # noqa: E402

DEFAULT_THEME = "professional-clean"


def split_frontmatter(text: str) -> tuple[dict, str]:
    """解析 `---` 包裹的 frontmatter（仅支持扁平的 key: value）。"""
    if text.lstrip().startswith("---"):
        lines = text.lstrip().splitlines()
        if lines[0].strip() == "---":
            for i in range(1, len(lines)):
                if lines[i].strip() == "---":
                    fm: dict[str, str] = {}
                    for ln in lines[1:i]:
                        if ":" in ln:
                            k, v = ln.split(":", 1)
                            fm[k.strip()] = v.strip().strip("'\"")
                    return fm, "\n".join(lines[i + 1 :])
    return {}, text


def truncate_digest(text: str, max_chars: int = 120) -> str:
    """微信摘要上限约 120 字（是**字**，不是字节）。超长按字符截断，多余换行压平。

    注意别按 UTF-8 字节算：一个中文字 3 字节，按 120 字节截只能留 40 字左右。
    """
    s = " ".join(str(text).split())
    return s if len(s) <= max_chars else s[: max_chars - 3].rstrip() + "..."


def build_fragment(
    md_text: str,
    theme_name: str | None = None,
    image_resolver=None,
    keep_h1: bool = False,
) -> tuple[str, dict, Theme]:
    """把整篇 Markdown（含 frontmatter）转成微信正文片段。

    返回 (fragment, meta, theme)。供 CLI 与 publish.py 共用，保证排版一致。
    """
    fm, body = split_frontmatter(md_text)
    resolved = theme_name or fm.get("theme") or DEFAULT_THEME
    if resolved not in list_themes():
        resolved = DEFAULT_THEME
    theme = load_theme(resolved)

    if image_resolver:
        # 仅替换图片路径：Markdown 的 ![alt](path) 与已存在的 <img src="path">
        # （普通外链 [text](url) 不动——resolver 对未命中项应原样返回）
        body = re.sub(
            r"(!\[[^\]]*\]\()([^)\s]+)(\))",
            lambda m: f"{m.group(1)}{image_resolver(m.group(2))}{m.group(3)}",
            body,
        )
        body = re.sub(
            r"(<img[^>]*?\bsrc=\")([^\"]+)(\")",
            lambda m: f"{m.group(1)}{image_resolver(m.group(2))}{m.group(3)}",
            body,
        )

    conv = WeChatConverter(theme=theme)
    res = conv.convert(body, keep_h1=keep_h1)

    title = fm.get("title") or res.title
    author = fm.get("author", "")
    digest = truncate_digest(fm.get("digest") or res.digest)

    plain = re.sub(r"<[^>]+>", "", res.html)
    chars = len(re.sub(r"\s+", "", plain))

    meta = {
        "title": title,
        "author": author,
        "digest": digest,
        "cover": fm.get("cover", ""),
        "theme": resolved,
        "source_url": fm.get("source_url", ""),
        "chars": chars,
        "images_count": len(res.images),
        "images": res.images,
        "html_bytes": len(res.html.encode("utf-8")),
    }
    return res.html, meta, theme


def preview_safe_fragment(fragment: str, base_dir: Path, outdir: Path) -> str:
    """把正文里相对图片路径改写为「相对 outdir」的路径，供本地预览页正确加载。

    发布产物（article.html）保持原样：上传时按 base_dir 解析；预览页位于
    outdir，若仍是 images/xxx.jpg 会 404。http(s)/data URI 不动。
    """
    def repl(m: re.Match) -> str:
        src = m.group(2)
        if src.startswith(("http://", "https://", "//", "data:")):
            return m.group(0)
        target = (base_dir / src).resolve()
        try:
            rel = os.path.relpath(target, outdir.resolve())
        except ValueError:  # 跨盘符
            rel = target.as_posix()
        return f"{m.group(1)}{Path(rel).as_posix()}{m.group(3)}"

    return re.sub(r"(<img[^>]*?\bsrc=\")([^\"]+)(\")", repl, fragment)


def validate(meta: dict, fragment: str) -> list[str]:
    problems: list[str] = []
    if meta.get("title") and len(meta["title"]) > 32:
        problems.append(f"标题 {len(meta['title'])} 字 > 32")
    if meta.get("author") and len(meta["author"]) > 16:
        problems.append(f"作者 {len(meta['author'])} 字 > 16")
    if meta.get("digest") and len(meta["digest"]) > 120:
        problems.append(f"摘要 {len(meta['digest'])} 字 > 120")
    if meta.get("chars", 0) > 20000:
        problems.append(f"正文 {meta['chars']} 字 > 20000")
    if meta.get("images_count", 0) > 10:
        problems.append(f"图片 {meta['images_count']} 张 > 10")
    if "<style" in fragment.lower() or "<script" in fragment.lower():
        problems.append("产物含 <style> 或 <script>（微信不允许）")
    if re.search(r'src="(?!https?://|//|data:)', fragment):
        problems.append("存在未上传的本地图片路径（发布前需先上传素材）")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description="Markdown → 微信公众号 HTML（wewrite 排版内核）")
    ap.add_argument("markdown", nargs="?", help="Markdown 文件路径")
    ap.add_argument("--outdir", default="build")
    ap.add_argument("--theme", default=None, help=f"主题名，可选: {', '.join(list_themes())}")
    ap.add_argument("--keep-h1", action="store_true", help="保留正文中的 H1（默认剥离）")
    ap.add_argument("--paste-safe", action="store_true", help="额外输出可粘贴编辑器的版本")
    ap.add_argument("--validate", action="store_true", help="只做发布前校验，不写文件")
    ap.add_argument("--json", action="store_true", help="输出 meta JSON")
    ap.add_argument("--list-themes", action="store_true", help="列出所有可用主题")
    args = ap.parse_args()

    if args.list_themes:
        for n in list_themes():
            m = theme_meta(n)
            print(f"  {n:20s} {m['primary']:9s} {m['description']}")
        return 0

    if not args.markdown:
        ap.error("需要提供 Markdown 文件路径")

    md_path = Path(args.markdown)
    if not md_path.exists():
        print(f"[error] 找不到 Markdown 文件: {md_path}")
        return 2

    md_text = md_path.read_text(encoding="utf-8")
    fragment, meta, theme = build_fragment(md_text, args.theme, keep_h1=args.keep_h1)
    problems = validate(meta, fragment)
    meta["problems"] = problems
    meta["ok"] = not problems

    if args.validate:
        jprint(meta)
        return 1 if problems else 0

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "article.html").write_text(fragment, encoding="utf-8")
    sub = (
        f"{meta['author']} · {meta['chars']} 字 · 主题 {meta['theme']}"
        if meta["author"]
        else f"{meta['chars']} 字 · 主题 {meta['theme']}"
    )
    (outdir / "preview.html").write_text(
        preview_html(
            preview_safe_fragment(fragment, md_path.parent, outdir), theme,
            title=meta["title"], subtitle=sub,
        ),
        encoding="utf-8",
    )
    if args.paste_safe:
        (outdir / "article.paste.html").write_text(make_paste_safe(fragment), encoding="utf-8")
    (outdir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.json:
        jprint(meta)
    else:
        print(
            f"[ok] {outdir / 'article.html'}  ({meta['chars']} 字, {meta['images_count']} 图, "
            f"主题 {meta['theme']}, {meta['html_bytes']} 字节)"
        )
        print(f"[ok] {outdir / 'preview.html'}")
        if args.paste_safe:
            print(f"[ok] {outdir / 'article.paste.html'}")
        if problems:
            for p in problems:
                print(f"  [warn] {p}")
        else:
            print("  [check] 发布前校验通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
