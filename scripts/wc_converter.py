#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Markdown → 微信公众号兼容 HTML 转换器。

**移植自 imraywang/wewrite 的 toolkit/converter.py**（MIT），排版行为以
wewrite 为基准；对上游两处明确缺陷做了修正（见 _fix_cjk_spacing、
_process_callout 的注释）。

核心管线（顺序不可随意更改）：
    frontmatter → 剥离 H1 → ::: 容器预处理 → CJK 间距 → markdown 解析
    → 代码块增强 → H2 章节编号 → 图片处理 → 加粗标点修正
    → ul/ol 转 section → 外链转脚注 → 主题内联样式 → 微信兼容修复
    → 净化 div/class → 暗色模式注入 → AIGC 页脚 → 生成摘要

对外接口：
    WeChatConverter(theme_name=...).convert(md_text) -> ConvertResult
    make_paste_safe(html)      # 复制粘贴路径加固
    preview_html(body, theme)  # 生成浏览器预览整页
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import markdown
from bs4 import BeautifulSoup

from wc_theme import Theme, load_theme, get_inline_css_rules


@dataclass
class ConvertResult:
    """Markdown → 微信 HTML 的转换结果。"""

    html: str  # 微信兼容的内联样式 HTML（仅正文片段，无 <html>/<head> 包裹）
    title: str  # 抽取出的 H1 标题
    digest: str  # 自动摘要（前 120 字）
    images: list[str] = field(default_factory=list)  # 正文里引用到的图片 src


class WeChatConverter:
    """把 Markdown 转成微信公众号可用的内联样式 HTML。"""

    def __init__(self, theme: Optional[Theme] = None, theme_name: str = "professional-clean"):
        if theme is not None:
            self._theme = theme
        else:
            self._theme = load_theme(theme_name)
        self._css_rules = get_inline_css_rules(self._theme)

    # ------------------------------------------------------------------ 入口
    def convert(self, markdown_text: str, keep_h1: bool = False) -> ConvertResult:
        title = self._extract_title(markdown_text)
        if not keep_h1:
            markdown_text = self._strip_h1(markdown_text)

        # :::dialogue / :::timeline / :::callout 等容器
        markdown_text = self._preprocess_containers(markdown_text)

        # CJK 间距：中英混排自动加空格（在解析前对原文做）
        markdown_text = self._fix_cjk_spacing(markdown_text)

        # Markdown → HTML
        html = self._markdown_to_html(markdown_text)

        html = self._enhance_code_blocks(html)  # 代码块加 data-lang
        html = self._number_sections(html)  # H2 章节编号（主题开关）
        html, images = self._process_images(html)  # 图片响应式 + GIF 角标
        html = self._fix_cjk_bold_punctuation(html)  # 加粗尾部标点移出
        html = self._convert_lists_to_sections(html)  # ul/ol → section
        html = self._convert_links_to_footnotes(html)  # 外链 → 脚注
        html = self._apply_inline_styles(html)  # 主题内联样式
        html = self._fix_table_headers(html)  # 表头可读性修复
        html = self._apply_wechat_fixes(html)  # 微信兼容修复
        html = self._sanitize_for_wechat(html)  # 净化 div/class
        html = self._inject_darkmode(html)  # 暗色模式属性

        # AIGC 声明页脚（合规：AI 生成/辅助内容需标识）
        raw = self._theme.raw or {}
        aigc = raw.get("aigc_footer", self._theme.colors.get("aigc_footer", True))
        if aigc:
            html = self._append_aigc_footer(html)

        digest = self._generate_digest(html)
        return ConvertResult(html=html, title=title, digest=digest, images=images)

    def convert_file(self, input_path: str, keep_h1: bool = False) -> ConvertResult:
        path = Path(input_path)
        if not path.exists():
            raise FileNotFoundError(f"输入文件不存在: {input_path}")
        return self.convert(path.read_text(encoding="utf-8"), keep_h1=keep_h1)

    # ------------------------------------------------------------- 内部方法
    def _extract_title(self, text: str) -> str:
        for line in text.split("\n"):
            stripped = line.strip()
            if stripped.startswith("# ") and not stripped.startswith("## "):
                return stripped[2:].strip()
        return ""

    def _strip_h1(self, text: str) -> str:
        """微信有独立标题字段，正文不再保留 H1。"""
        lines = []
        for line in text.split("\n"):
            stripped = line.strip()
            if stripped.startswith("# ") and not stripped.startswith("## "):
                continue
            lines.append(line)
        return "\n".join(lines)

    def _markdown_to_html(self, text: str) -> str:
        extensions = [
            "markdown.extensions.fenced_code",
            "markdown.extensions.tables",
            "markdown.extensions.nl2br",
            "markdown.extensions.sane_lists",
            "markdown.extensions.codehilite",
        ]
        extension_configs = {
            "codehilite": {"linenums": False, "guess_lang": True, "noclasses": True}
        }
        md = markdown.Markdown(extensions=extensions, extension_configs=extension_configs)
        return md.convert(text)

    def _enhance_code_blocks(self, html: str) -> str:
        soup = BeautifulSoup(html, "html.parser")
        for pre in soup.find_all("pre"):
            code = pre.find("code")
            if code:
                for cls in code.get("class", []):
                    if cls.startswith("language-"):
                        pre["data-lang"] = cls.replace("language-", "")
                        break
        return str(soup)

    def _process_images(self, html: str) -> tuple[str, list[str]]:
        soup = BeautifulSoup(html, "html.parser")
        images = []
        for img in soup.find_all("img"):
            src = img.get("src", "")
            if src:
                images.append(src)
            # GIF 角标：动图上方右对齐小标签（不用 absolute —— 微信不支持）
            is_gif = src.lower().split("?")[0].endswith(".gif")
            if is_gif:
                badge = soup.new_tag("section")
                badge["style"] = "display: flex; justify-content: flex-end; margin: 24px 0 4px"
                tag = soup.new_tag("span")
                tag["style"] = (
                    "background: rgba(0,0,0,0.55); color: #ffffff; font-size: 11px; "
                    "padding: 2px 8px; border-radius: 4px; letter-spacing: 1px"
                )
                tag.string = "GIF"
                badge.append(tag)
                img.insert_before(badge)
            existing = img.get("style", "")
            if "max-width" not in existing:
                margin = "margin: 4px auto 24px" if is_gif else "margin: 24px auto"
                additions = f"max-width: 100%; height: auto; display: block; {margin}"
                img["style"] = f"{existing}; {additions}" if existing else additions
        return str(soup), images

    def _apply_inline_styles(self, html: str) -> str:
        """把主题 CSS 规则逐条内联到匹配元素上。"""
        soup = BeautifulSoup(html, "html.parser")

        for selector, styles in self._css_rules.items():
            if selector.strip() == "body":
                continue
            try:
                elements = soup.select(selector)
            except Exception:
                continue
            for elem in elements:
                existing = elem.get("style", "")
                style_dict: dict[str, str] = {}
                if existing:
                    for item in existing.split(";"):
                        if ":" in item:
                            key, val = item.split(":", 1)
                            style_dict[key.strip()] = val.strip()
                # 既有内联样式优先，主题样式补齐缺口
                for prop, val in styles.items():
                    if prop not in style_dict:
                        style_dict[prop] = val
                elem["style"] = "; ".join(f"{k}: {v}" for k, v in style_dict.items())

        return str(soup)

    def _apply_wechat_fixes(self, html: str) -> str:
        soup = BeautifulSoup(html, "html.parser")
        text_color = self._theme.colors.get("text", "#333333")

        # 每个 <p> 显式给 color（微信会吞继承色）
        for p in soup.find_all("p"):
            style = p.get("style", "")
            if "color" not in style:
                p["style"] = f"{style}; color: {text_color}" if style else f"color: {text_color}"

        # <pre> 保留空白
        for pre in soup.find_all("pre"):
            style = pre.get("style", "")
            if "white-space" not in style:
                pre["style"] = (
                    f"{style}; white-space: pre-wrap; word-wrap: break-word"
                    if style
                    else "white-space: pre-wrap; word-wrap: break-word"
                )
        return str(soup)

    # ---------------------------------------------------- 表头可读性修复
    @staticmethod
    def _css_color_is_light(value: str) -> bool:
        """判断 CSS 颜色值是否为浅色（用于检测「白字无底色」）。"""
        value = (value or "").strip().lower()
        m = re.search(r"#([0-9a-f]{3}|[0-9a-f]{6})\b", value)
        if m:
            h = m.group(1)
            if len(h) == 3:
                h = "".join(c * 2 for c in h)
            r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        else:
            m = re.search(r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)", value)
            if not m:
                return False
            r, g, b = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return (0.299 * r + 0.587 * g + 0.114 * b) / 255 > 0.72

    @staticmethod
    def _bg_longhands(bg_value: str, primary: str) -> str:
        """把 thead 的 background 拆成可下推到单元格的长写法。

        渐变用 background-image + background-color 兜底（微信对渐变的支持
        不稳定，纯色兜底能保证文字始终可读）。
        """
        v = (bg_value or "").strip()
        if "gradient" in v.lower():
            m = re.search(r"#([0-9a-fA-F]{3,6})", v)
            first = ("#" + m.group(1)) if m else primary
            return f"background-color: {first}; background-image: {v}"
        return f"background-color: {v or primary}"

    def _fix_table_headers(self, html: str) -> str:
        """修复表头不可读。

        主题常见写法：`thead { background: 渐变 } th { color:#fff }` 外加
        `tr { background:#fff }`。问题出在不同的渲染环境：
          · 预览页注入了主题原始 CSS，`tr{background:#fff}` 会**盖住** thead
            的渐变，白色表头文字「消失」；
          · 微信端不含任何样式表，只认内联样式。
        所以把 thead 的底色**下推到每个 th 单元格**（长写法 + 纯色兜底），
        并清掉 thead 内 tr 的底色——这样预览与微信端表现一致。
        """
        soup = BeautifulSoup(html, "html.parser")
        primary = self._theme.colors.get("primary", "#2563eb")

        for thead in soup.find_all("thead"):
            st = thead.get("style", "")
            m = re.search(r"\bbackground\s*:\s*([^;]+)", st)
            bg_value = m.group(1).strip() if m else ""
            has_bg = bool(bg_value)

            for tr in thead.find_all("tr"):
                tstyle = tr.get("style", "")
                if has_bg and "background" in tstyle:
                    kept = [p.strip() for p in tstyle.split(";")
                            if p.strip() and not p.strip().startswith("background")]
                    if kept:
                        tr["style"] = "; ".join(kept)
                    else:
                        del tr["style"]

            if has_bg:
                for th in thead.find_all("th"):
                    tstyle = th.get("style", "")
                    if not re.search(r"(?<!-)\bbackground(-color)?\s*:", tstyle):
                        th["style"] = f"{tstyle}; {self._bg_longhands(bg_value, primary)}"

        # 兜底：th 用浅色文字、又完全没有可用底色时，给主色底
        for th in soup.find_all("th"):
            style = th.get("style", "")
            m = re.search(r"(?<!background-)\bcolor\s*:\s*([^;]+)", style)
            if not m or not self._css_color_is_light(m.group(1)):
                continue
            if not re.search(r"(?<!-)\bbackground(-color)?\s*:", style):
                th["style"] = f"{style}; background-color: {primary}"

        return str(soup)

    # -------------------------------------------------------- CJK 兼容修复
    def _fix_cjk_spacing(self, text: str) -> str:
        """中英/中数之间插入空格（盘古之白）。跳过代码块。

        与 wewrite 的差异（有意修正）：CJK 类只取**表意文字与假名**，不含
        全角标点（。，、：；！？《》「」）。上游把 \\uff00-\\uffef 也算进来，
        会在拉丁字符与全角标点之间插空格，产出「MP4 。」「： Remotion」这类
        错误。标点本就自带视觉留白，无需再加空格。
        """
        cjk = r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]"
        latin = r"[A-Za-z0-9]"

        lines = text.split("\n")
        result = []
        in_code_block = False
        for line in lines:
            if line.strip().startswith("```"):
                in_code_block = not in_code_block
                result.append(line)
                continue
            if in_code_block:
                result.append(line)
                continue
            line = re.sub(f"({cjk})({latin})", r"\1 \2", line)
            line = re.sub(f"({latin})({cjk})", r"\1 \2", line)
            result.append(line)
        return "\n".join(result)

    def _fix_cjk_bold_punctuation(self, html: str) -> str:
        """把加粗尾部的中文标点移到 </strong> 外（微信加粗标点会错位）。"""
        pattern = r"(<strong[^>]*>)(.*?)([，。、；：！？）》」』,.!?;:]+)(</strong>)"
        return re.sub(pattern, r"\1\2\4\3", html, flags=re.S)

    def _convert_lists_to_sections(self, html: str) -> str:
        """ul/ol → section（微信原生列表项目符号与缩进很不稳定）。"""
        soup = BeautifulSoup(html, "html.parser")
        text_color = self._theme.colors.get("text", "#333333")
        primary = self._theme.colors.get("primary", "#2563eb")

        for ul in soup.find_all("ul"):
            section = soup.new_tag("section")
            for li in ul.find_all("li", recursive=False):
                item = soup.new_tag(
                    "section",
                    style=f"display: flex; align-items: flex-start; margin-bottom: 8px; color: {text_color}",
                )
                bullet = soup.new_tag(
                    "span",
                    style=f"color: {primary}; margin-right: 8px; flex-shrink: 0; font-size: 18px; line-height: 1.6",
                )
                bullet.string = "•"
                content = soup.new_tag("span", style="flex: 1")
                for child in list(li.children):
                    content.append(child.extract())
                item.append(bullet)
                item.append(content)
                section.append(item)
            ul.replace_with(section)

        for ol in soup.find_all("ol"):
            section = soup.new_tag("section")
            for num, li in enumerate(ol.find_all("li", recursive=False), 1):
                item = soup.new_tag(
                    "section",
                    style=f"display: flex; align-items: flex-start; margin-bottom: 8px; color: {text_color}",
                )
                number = soup.new_tag(
                    "span",
                    style=f"color: {primary}; margin-right: 8px; flex-shrink: 0; font-weight: 700; line-height: 1.8",
                )
                number.string = f"{num}."
                content = soup.new_tag("span", style="flex: 1")
                for child in list(li.children):
                    content.append(child.extract())
                item.append(number)
                item.append(content)
                section.append(item)
            ol.replace_with(section)

        return str(soup)

    # ------------------------------------------------- 外链 → 脚注
    def _convert_links_to_footnotes(self, html: str) -> str:
        soup = BeautifulSoup(html, "html.parser")
        footnotes = []
        counter = 0
        primary = self._theme.colors.get("primary", "#2563eb")

        for a in soup.find_all("a"):
            href = a.get("href", "")
            if not href or href.startswith("#"):
                continue
            counter += 1
            text = a.get_text()
            footnotes.append((counter, text, href))

            sup = soup.new_tag("sup")
            sup_link = soup.new_tag("span", style=f"color: {primary}; font-size: 12px")
            sup_link.string = f"[{counter}]"
            sup.append(sup_link)
            a.replace_with(text, sup)

        if footnotes:
            hr = soup.new_tag(
                "hr", style="border: none; border-top: 1px solid #e5e5e5; margin: 32px 0 16px"
            )
            soup.append(hr)
            ref_title = soup.new_tag(
                "p", style="font-size: 13px; color: #999999; margin-bottom: 8px; font-weight: 700"
            )
            ref_title.string = "参考链接"
            soup.append(ref_title)
            for num, text, href in footnotes:
                ref = soup.new_tag(
                    "p", style="font-size: 12px; color: #999999; margin: 2px 0; word-break: break-all"
                )
                ref.string = f"[{num}] {text}: {href}"
                soup.append(ref)

        return str(soup)

    # ------------------------------------------------------ 暗色模式
    def _inject_darkmode(self, html: str) -> str:
        darkmode = self._theme.colors.get("darkmode", {})
        if not darkmode:
            return html

        soup = BeautifulSoup(html, "html.parser")
        dm_text = darkmode.get("text", "#c8c8c8")
        dm_primary = darkmode.get("primary", "#6aadff")

        for tag_name in ("p", "span", "section"):
            for elem in soup.find_all(tag_name):
                if "color" in elem.get("style", ""):
                    elem["data-darkmode-color"] = dm_text
                    elem["data-darkmode-bgcolor"] = "transparent"

        dm_heading = darkmode.get("text", "#e0e0e0")
        for tag_name in ("h1", "h2", "h3", "h4"):
            for elem in soup.find_all(tag_name):
                elem["data-darkmode-color"] = dm_heading
                elem["data-darkmode-bgcolor"] = "transparent"

        dm_code_bg = darkmode.get("code_bg", "#2d2d2d")
        dm_code_color = darkmode.get("code_color", "#d4d4d4")
        for pre in soup.find_all("pre"):
            pre["data-darkmode-bgcolor"] = dm_code_bg
            pre["data-darkmode-color"] = dm_code_color
        for code in soup.find_all("code"):
            code["data-darkmode-color"] = dm_code_color

        dm_quote_bg = darkmode.get("quote_bg", "#2a2a2a")
        for bq in soup.find_all("blockquote"):
            bq["data-darkmode-bgcolor"] = dm_quote_bg
            bq["data-darkmode-color"] = dm_text

        for strong in soup.find_all("strong"):
            strong["data-darkmode-color"] = dm_primary

        return str(soup)

    def _sanitize_for_wechat(self, html: str) -> str:
        """微信会改写 <div>、剥 class/id —— 统一转 section 并清属性。"""
        soup = BeautifulSoup(html, "html.parser")
        for div in soup.find_all("div"):
            div.name = "section"
        for el in soup.find_all(attrs={"class": True}):
            del el["class"]
        for el in soup.find_all(attrs={"id": True}):
            del el["id"]
        return str(soup)

    # ------------------------------------------------------ 容器块语法
    # 统一的开块正则：:::name 后可跟同一行的可选参数（如 :::callout info 标题）
    _OPEN = r":{3}%s(?:[ \t]+([^\n]*))?\n"
    _INLINE_CODE_RE = re.compile(r"`([^`\n]+?)`")
    _INLINE_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
    _INLINE_EM_RE = re.compile(r"(?<!\*)\*([^*\n]+?)\*(?!\*)")
    _INLINE_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")

    def _inline_md(self, text: str) -> str:
        """渲染容器内容里的行内 Markdown。

        容器在 Markdown 解析前就渲染成 HTML，python-markdown 会跳过 HTML
        块内的行内语法，所以必须自己处理 `code` / **bold** / *em*。
        """
        text = self._INLINE_CODE_RE.sub(
            r'<code style="background: rgba(0,0,0,0.06); padding: 2px 5px; '
            r'border-radius: 3px; font-size: 0.9em">\1</code>',
            text,
        )
        text = self._INLINE_BOLD_RE.sub(r"<strong>\1</strong>", text)
        text = self._INLINE_EM_RE.sub(r"<em>\1</em>", text)
        # 容器在 Markdown 解析前就渲染成 HTML，python-markdown 会跳过块内行内
        # 语法，所以这里的 [text](url) 不会被转成 <a>，后续「外链转脚注」也就
        # 抓不到它。这里先产出 <a href>，交给统一的 _convert_links_to_footnotes
        # 处理成上标脚注（与正文外链行为一致）。
        text = self._INLINE_LINK_RE.sub(r'<a href="\2">\1</a>', text)
        return text

    def _md_paragraphs(self, text: str, color: str | None = None) -> str:
        """把容器正文按空行拆段，渲染成 <p>（微信里裸换行会塌成一行）。"""
        blocks = [b.strip() for b in re.split(r"\n\s*\n", text.strip()) if b.strip()]
        if not blocks:
            return ""
        col = f"color: {color};" if color else ""
        parts = []
        for i, b in enumerate(blocks):
            gap = "0" if i == len(blocks) - 1 else "0 0 8px"
            body = self._inline_md(b.replace("\n", " "))
            parts.append(f'<p style="margin: {gap}; {col}">{body}</p>')
        return "".join(parts)

    def _preprocess_containers(self, text: str) -> str:
        text = self._process_dialogue(text)
        text = self._process_timeline(text)
        text = self._process_callout(text)
        text = self._process_quote_block(text)
        text = self._process_pullquote(text)
        text = self._process_label(text)
        text = self._process_steps(text)
        text = self._process_highlight(text)
        text = self._process_summary(text)
        text = self._process_video(text)
        text = self._process_article(text)
        text = self._process_readmore(text)
        return text

    def _process_dialogue(self, text: str) -> str:
        primary = self._theme.colors.get("primary", "#2563eb")

        def replace_dialogue(match):
            lead = (match.group(1) or "").strip()
            content = match.group(2).strip()
            if lead:
                content = lead + "\n" + content
            bubbles = []
            for line in content.split("\n"):
                line = line.strip()
                if not line:
                    continue
                if line.startswith("> "):
                    msg = line[2:].strip()
                    bubbles.append(
                        '<section style="display: flex; justify-content: flex-end; margin-bottom: 12px">'
                        f'<section style="background: {primary}; color: white; padding: 10px 14px; '
                        f'border-radius: 12px 12px 2px 12px; max-width: 80%; font-size: 15px; '
                        f'line-height: 1.6">{self._inline_md(msg)}</section></section>'
                    )
                else:
                    bubbles.append(
                        '<section style="display: flex; justify-content: flex-start; margin-bottom: 12px">'
                        f'<section style="background: #f3f4f6; color: #333; padding: 10px 14px; '
                        f'border-radius: 12px 12px 12px 2px; max-width: 80%; font-size: 15px; '
                        f'line-height: 1.6">{self._inline_md(line)}</section></section>'
                    )
            return "\n".join(bubbles)

        return re.sub(
            self._OPEN % "dialogue" + r"(.*?)\n:::", replace_dialogue, text, flags=re.DOTALL
        )

    def _process_timeline(self, text: str) -> str:
        primary = self._theme.colors.get("primary", "#2563eb")

        def replace_timeline(match):
            lead = (match.group(1) or "").strip()
            content = match.group(2).strip()
            if lead:
                content = lead + "\n" + content
            items = []
            for line in content.split("\n"):
                line = line.strip()
                if not line:
                    continue
                items.append(
                    '<section style="display: flex; margin-bottom: 16px">'
                    '<section style="flex-shrink: 0; width: 12px; display: flex; flex-direction: column; align-items: center">'
                    f'<section style="width: 10px; height: 10px; border-radius: 50%; background: {primary}; margin-top: 6px"></section>'
                    '<section style="width: 2px; flex: 1; background: #e5e7eb; margin-top: 4px"></section>'
                    "</section>"
                    '<section style="flex: 1; padding-left: 12px; padding-bottom: 8px; font-size: 15px; '
                    f'line-height: 1.7">{self._inline_md(line)}</section>'
                    "</section>"
                )
            return "\n".join(items)

        return re.sub(
            self._OPEN % "timeline" + r"(.*?)\n:::", replace_timeline, text, flags=re.DOTALL
        )

    def _process_callout(self, text: str) -> str:
        """:::callout <type> [标题] —— 支持 info/tip/warning/danger。

        修正上游缺陷：上游要求 `:::callout info` 后**必须立刻换行**，导致
        `:::callout info 一句实话` 这种带标题的写法不被识别、原样输出。
        这里允许同一行带标题，并把正文按空行分段。
        """
        colors_map = {
            "tip": ("#059669", "#ecfdf5", "💡"),
            "warning": ("#d97706", "#fffbeb", "⚠️"),
            "info": ("#2563eb", "#eff6ff", "ℹ️"),
            "danger": ("#dc2626", "#fef2f2", "🚨"),
        }
        labels = {"tip": "提示", "info": "说明", "warning": "注意", "danger": "警告"}

        def replace_callout(match):
            ctype = (match.group(1) or "").strip().lower()
            lead = (match.group(2) or "").strip()
            content = (match.group(3) or "").strip()
            color, bg, icon = colors_map.get(ctype, colors_map["info"])
            label = lead or labels.get(ctype, "说明")
            body = self._md_paragraphs(content)
            return (
                f'<section style="background: {bg}; border-left: 4px solid {color}; '
                f'padding: 14px 16px; border-radius: 4px; margin: 16px 0; font-size: 15px; line-height: 1.7">'
                f'<section style="font-weight: 700; color: {color}; margin-bottom: 8px">'
                f'{icon} {self._inline_md(label)}</section>'
                f"{body}</section>"
            )

        pattern = r":{3}callout[ \t]+(\w+)(?:[ \t]+([^\n]*))?\n(.*?)\n:::"
        return re.sub(pattern, replace_callout, text, flags=re.DOTALL)

    def _process_quote_block(self, text: str) -> str:
        primary = self._theme.colors.get("primary", "#2563eb")

        def replace_quote(match):
            lead = (match.group(1) or "").strip()
            content = match.group(2).strip()
            if lead:
                content = lead + " " + content
            return (
                f'<section style="margin: 24px 0; padding: 20px 24px; border-left: 4px solid {primary}; '
                f'background: linear-gradient(135deg, #f8f9fa 0%, #ffffff 100%); border-radius: 0 8px 8px 0">'
                f'<section style="font-size: 18px; line-height: 1.8; color: #333; font-style: italic">'
                f'“{self._inline_md(content)}”</section></section>'
            )

        return re.sub(
            self._OPEN % "quote" + r"(.*?)\n:::", replace_quote, text, flags=re.DOTALL
        )

    def _process_pullquote(self, text: str) -> str:
        """:::pullquote —— 金句居中。"""
        primary = self._theme.colors.get("primary", "#2563eb")

        def replace_pullquote(match):
            lead = (match.group(1) or "").strip()
            content = match.group(2).strip()
            if lead:
                content = lead + " " + content
            content = self._inline_md(content.replace("\n", "<br>"))
            return (
                '<section style="margin: 36px 0; padding: 0 24px; text-align: center">'
                f'<section style="font-size: 30px; line-height: 1; color: {primary}; font-weight: 700; margin-bottom: 10px">“</section>'
                f'<section style="font-size: 18px; font-weight: 600; line-height: 1.9; color: #333333">{content}</section>'
                # 装饰短横内置占位，防微信剥空元素样式
                f'<section style="width: 36px; height: 2px; background: {primary}; margin: 16px auto 0">'
                '<span leaf=""><br></span></section>'
                "</section>"
            )

        return re.sub(
            self._OPEN % "pullquote" + r"(.*?)\n:::", replace_pullquote, text, flags=re.DOTALL
        )

    def _process_label(self, text: str) -> str:
        """:::label [pill] —— 小标签标题。"""
        primary = self._theme.colors.get("primary", "#2563eb")

        def replace_label(match):
            variant = (match.group(1) or "").strip().lower()
            content = self._inline_md(match.group(2).strip())
            if variant == "pill":
                return (
                    '<section style="margin: 28px 0 14px">'
                    f'<span style="display: inline-block; background: {primary}; color: #ffffff; '
                    "font-size: 13px; font-weight: 700; padding: 4px 14px; border-radius: 999px; "
                    f'letter-spacing: 1px">{content}</span></section>'
                )
            return (
                '<section style="display: flex; align-items: center; margin: 28px 0 14px">'
                # 竖条装饰内置占位，防微信剥空元素样式
                f'<section style="flex-shrink: 0; width: 4px; height: 16px; background: {primary}; '
                'border-radius: 2px; margin-right: 8px"><span leaf=""><br></span></section>'
                f'<section style="font-size: 16px; font-weight: 700; color: #1a1a1a">{content}</section>'
                "</section>"
            )

        return re.sub(
            r":{3}label(?:[ \t]+(\w*))?\n(.*?)\n:::", replace_label, text, flags=re.DOTALL
        )

    def _process_steps(self, text: str) -> str:
        """:::steps —— 编号步骤卡。"""
        primary = self._theme.colors.get("primary", "#2563eb")

        def replace_steps(match):
            lead = (match.group(1) or "").strip()
            content = match.group(2).strip()
            if lead:
                content = lead + "\n" + content
            items = []
            n = 0
            for line in content.split("\n"):
                line = line.strip().lstrip("-").strip()
                if not line:
                    continue
                n += 1
                items.append(
                    '<section style="display: flex; margin-bottom: 14px">'
                    '<section style="flex-shrink: 0; width: 22px; height: 22px; border-radius: 50%; '
                    f'background: {primary}; color: #ffffff; font-size: 13px; font-weight: 700; '
                    f'text-align: center; line-height: 22px; margin-right: 10px">{n}</section>'
                    '<section style="flex: 1; font-size: 15px; line-height: 1.7; padding-top: 1px">'
                    f"{self._inline_md(line)}</section>"
                    "</section>"
                )
            return '<section style="margin: 20px 0">' + "\n".join(items) + "</section>"

        return re.sub(
            self._OPEN % "steps" + r"(.*?)\n:::", replace_steps, text, flags=re.DOTALL
        )

    def _process_highlight(self, text: str) -> str:
        secondary = self._theme.colors.get("secondary", "#c4820e")
        highlight_bg = self._theme.colors.get("highlight_bg", "#fef7e8")
        highlight_border = self._theme.colors.get("highlight_border", "rgba(196,130,14,0.2)")

        def replace_highlight(match):
            lead = (match.group(1) or "").strip()
            content = (match.group(2) or "").strip()
            if lead:
                title, body_text = lead, content
            else:
                lines = content.split("\n", 1)
                title = lines[0].strip() if lines else ""
                body_text = lines[1].strip() if len(lines) > 1 else ""
            html = (
                f'<section style="margin: 24px 0; padding: 20px 24px; background: {highlight_bg}; '
                f'border: 1px solid {highlight_border}; border-radius: 6px;">'
            )
            if title:
                html += (
                    f'<p style="margin: 0;"><strong style="color: {secondary};">'
                    f"{self._inline_md(title)}</strong></p>"
                )
            if body_text:
                html += f'<p style="margin: 8px 0 0 0;">{self._inline_md(body_text)}</p>'
            html += "</section>"
            return html

        return re.sub(
            self._OPEN % "highlight" + r"(.*?)\n:::", replace_highlight, text, flags=re.DOTALL
        )

    def _process_summary(self, text: str) -> str:
        """:::summary [标题] —— 支持标题写在开块同一行或正文首行。"""
        primary = self._theme.colors.get("primary", "#1a6b5a")
        summary_bg = self._theme.colors.get("summary_bg", "#e8f5f0")
        summary_border = self._theme.colors.get("summary_border", "rgba(26,107,90,0.15)")

        def replace_summary(match):
            lead = (match.group(1) or "").strip()
            content = (match.group(2) or "").strip()
            if lead:
                title, body_text = lead, content
            else:
                lines = content.split("\n", 1)
                title = lines[0].strip() if lines else "总结"
                body_text = lines[1].strip() if len(lines) > 1 else ""
            html = (
                f'<section style="margin: 24px 0; padding: 20px 24px; background: {summary_bg}; '
                f'border: 1px solid {summary_border}; border-radius: 6px;">'
            )
            html += (
                f'<p style="margin: 0;"><strong style="color: {primary};">'
                f"{self._inline_md(title)}</strong></p>"
            )
            if body_text:
                html += f'<p style="margin: 8px 0 0 0;">{self._inline_md(body_text)}</p>'
            html += "</section>"
            return html

        return re.sub(
            self._OPEN % "summary" + r"(.*?)\n:::", replace_summary, text, flags=re.DOTALL
        )

    # ------------------------------------------------ 正文嵌入占位卡
    # 视频号卡片 / 其他文章链接 / 往期推荐，微信草稿箱 API **无法**写入这两类
    # 富组件（见 references/wechat-api.md 与 docs/embeds.md）：
    #   · 视频号：draft/add 会丢掉 video_snap_card 属性，卡片在编辑器里一直转圈；
    #   · 其它文章超链接：官方只支持在编辑器工具栏「超链接」里插入。
    # 所以这里产出「占位卡」——视觉上成块、带明确文字提示，发布后由作者在
    # 公众号编辑器里手动替换成真卡片。占位卡不产出 <a>，避免被「外链转脚注」
    # 抓成上标脚注（这两类本就是站内链接，不应走脚注）。
    _URL_RE = re.compile(r"https?://\S+")

    def _embed_card(self, tag: str, title: str, url: str, desc_html: str, hint: str) -> str:
        primary = self._theme.colors.get("primary", "#2563eb")
        url_line = (
            f'<section style="font-size: 12px; color: #9ca3af; margin-top: 6px; '
            f'word-break: break-all">{url}</section>'
            if url
            else ""
        )
        desc = f'<section style="margin-top: 6px">{desc_html}</section>' if desc_html else ""
        return (
            '<section style="margin: 24px 0; border: 1px solid #e5e7eb; border-radius: 10px; overflow: hidden">'
            f'<section style="background: {primary}; padding: 8px 14px; color: #ffffff; '
            f'font-size: 12px; letter-spacing: 1px">{tag}</section>'
            '<section style="padding: 14px 16px; background: #fafafa">'
            f'<section style="font-size: 15px; font-weight: 700; color: #1a1a1a; line-height: 1.6">'
            f"{self._inline_md(title)}</section>"
            f"{url_line}{desc}"
            f'<section style="margin-top: 10px; font-size: 12px; color: #b45309; '
            f'background: #fffbeb; border-radius: 6px; padding: 6px 10px">⚠️ {hint}</section>'
            "</section></section>"
        )

    def _process_video(self, text: str) -> str:
        """:::video <视频号标题> —— 视频号卡片占位。"""

        def replace_video(match):
            title = (match.group(1) or "").strip() or "视频号内容"
            body = (match.group(2) or "").strip()
            desc = self._md_paragraphs(body, color="#6b7280") if body else ""
            return self._embed_card(
                "视频号", title, "", desc,
                f"发布后请在公众号编辑器「视频号」里搜索并手动插入该视频（标题：{title}）",
            )

        return re.sub(self._OPEN % "video" + r"(.*?)\n:::", replace_video, text, flags=re.DOTALL)

    def _process_article(self, text: str) -> str:
        """:::article <文章标题> —— 引用他人/其它文章的占位。

        body 首行若为 URL 则作为链接，其余行作为说明。
        """

        def replace_article(match):
            title = (match.group(1) or "").strip()
            body = (match.group(2) or "").strip()
            lines = [ln.strip() for ln in body.split("\n") if ln.strip()]
            url = ""
            if lines and re.match(r"^https?://", lines[0]):
                url = lines.pop(0)
            if not title and lines:
                title = lines.pop(0)
            title = title or "关联文章"
            desc = self._md_paragraphs("\n\n".join(lines), color="#6b7280") if lines else ""
            return self._embed_card(
                "关联阅读", title, url, desc,
                "发布后请在编辑器工具栏「超链接 → 选择其它文章」插入站内链接",
            )

        return re.sub(self._OPEN % "article" + r"(.*?)\n:::", replace_article, text, flags=re.DOTALL)

    def _process_readmore(self, text: str) -> str:
        """:::readmore [标题] —— 往期推荐列表占位。

        body 每行一条：`标题 | url` 或 `- 标题 url`（url 可省略）。
        """

        def replace_readmore(match):
            title = (match.group(1) or "").strip() or "往期推荐"
            body = (match.group(2) or "").strip()
            rows = []
            for raw in body.split("\n"):
                line = raw.strip().lstrip("-").lstrip("0123456789.").strip()
                if not line:
                    continue
                m = self._URL_RE.search(line)
                if m:
                    url = m.group(0)
                    label = (line[: m.start()] + line[m.end():]).strip().strip("|").strip()
                else:
                    url, label = "", line
                label = label or url or "（未命名）"
                url_html = (
                    f'<section style="font-size: 12px; color: #9ca3af; margin-top: 2px; '
                    f'word-break: break-all">{url}</section>'
                    if url
                    else ""
                )
                rows.append(
                    f'<section style="margin-bottom: 10px"><section style="font-size: 14px; '
                    f'font-weight: 600; color: #1a1a1a; line-height: 1.6">{self._inline_md(label)}'
                    f"</section>{url_html}</section>"
                )
            body_html = "".join(rows) or '<section style="font-size: 13px; color: #9ca3af">（待补充）</section>'
            return self._embed_card(
                "往期推荐", title, "", body_html,
                "发布后请在编辑器里用「超链接」逐条替换为真实站内链接",
            )

        return re.sub(self._OPEN % "readmore" + r"(.*?)\n:::", replace_readmore, text, flags=re.DOTALL)

    def _number_sections(self, html: str) -> str:
        """给 H2 加两位数章节编号（01/02/…）。主题 section_numbering: true 启用。"""
        if not (self._theme.raw or {}).get("section_numbering"):
            return html
        primary = self._theme.colors.get("primary", "#2563eb")
        soup = BeautifulSoup(html, "html.parser")
        for i, h2 in enumerate(soup.find_all("h2"), 1):
            num = soup.new_tag("span")
            num["style"] = f"color: {primary}; font-weight: 800; margin-right: 10px; letter-spacing: 1px"
            num.string = f"{i:02d}"
            h2.insert(0, num)
        return str(soup)

    def _append_aigc_footer(self, html: str) -> str:
        footer = (
            '<p style="text-align: center; font-size: 13px; color: #9ca3af; '
            'margin-top: 48px; padding-top: 24px; border-top: 1px solid #e5e7eb;">'
            "本文由 AI 辅助创作，作者进行了实测验证和编辑修改。</p>"
        )
        return html + "\n" + footer

    def _generate_digest(self, html: str, max_chars: int = 120) -> str:
        """从正文抽前若干字做摘要。

        微信文档说摘要上限约 120 **字**——不是字节。按字节截会把中文砍到只剩
        40 字左右（还带个省略号），所以这里按字符数算。
        """
        soup = BeautifulSoup(html, "html.parser")
        text = soup.get_text(separator=" ", strip=True)
        text = re.sub(r"\s+", " ", text).strip()
        if len(text) <= max_chars:
            return text
        return text[: max_chars - 3].rstrip() + "..."


def make_paste_safe(html: str) -> str:
    """粘贴路径加固：文本节点包 <span leaf="">，空装饰元素补 <br> 占位。

    微信编辑器粘贴时会重排不在 leaf span 内的文本、剥掉空元素的样式；API
    发布草稿箱不经编辑器改写，无需本处理——本函数只用于 preview（复制粘贴
    进编辑器）路径。
    """
    soup = BeautifulSoup(html, "html.parser")

    for node in list(soup.find_all(string=True)):
        if not str(node).strip():
            continue
        if node.find_parent(["pre", "code"]) is not None:
            continue
        parent = node.parent
        if parent is None or (parent.name == "span" and parent.has_attr("leaf")):
            continue
        wrapper = soup.new_tag("span")
        wrapper["leaf"] = ""
        node.wrap(wrapper)

    for el in soup.find_all(["section", "span"]):
        if el.get_text(strip=True):
            continue
        if el.find(["img", "br"]) is not None:
            continue
        if el.name == "span" and el.has_attr("leaf"):
            continue
        ph = soup.new_tag("span")
        ph["leaf"] = ""
        ph.append(soup.new_tag("br"))
        el.append(ph)

    return str(soup)


def preview_html(body_html: str, theme: Theme, title: str = "", subtitle: str = "") -> str:
    """把正文片段包成完整 HTML 文档，供浏览器预览用（**不用于发布**）。

    用手机宽度白卡片还原公众号阅读体验；主题原始 CSS 直接注入（预览页可以
    用 <style>，发布产物不行）。
    """

    def esc(s: str) -> str:
        return (
            (s or "")
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
        )

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{esc(title) or '预览'}</title>
<style>
  html, body {{ margin: 0; padding: 0; background: #eceff3; }}
  .phone {{ max-width: 420px; margin: 20px auto 40px; background: #ffffff;
           border-radius: 14px; box-shadow: 0 8px 32px rgba(0,0,0,.10);
           padding: 22px 18px 40px; overflow: hidden; }}
  .pv-head {{ max-width: 420px; margin: 28px auto 0; padding: 0 18px; }}
  h1.pv {{ font-size: 22px; font-weight: 800; line-height: 1.45; margin: 0 0 8px; color: #1a1a1a; }}
  .pvsub {{ font-size: 13px; line-height: 1.6; color: #8792a2; }}
  .hint {{ max-width: 420px; margin: 16px auto 0; padding: 0 18px; font-size: 12px;
          color: #a0aab8; text-align: center; }}
{theme.base_css}
</style>
</head>
<body>
<div class="pv-head">
  <h1 class="pv">{esc(title)}</h1>
  <div class="pvsub">{esc(subtitle)}</div>
</div>
<div class="hint">↓ 微信公众号正文实际渲染效果预览 ↓</div>
<div class="phone">{body_html}</div>
</body>
</html>"""
