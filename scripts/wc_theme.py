#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""主题系统 —— 移植自 imraywang/wewrite 的 toolkit/theme.py。

一套主题 = 一个 YAML：`name` / `description` / `colors` / `base_css`（完整 CSS），
外加可选顶层字段 `section_numbering`、`aigc_footer`。

设计要点：主题写的是**真 CSS**，不是一堆样式 token。converter 会：
  1. 用 colors 把 `var(--primary)` 这类变量替换成实际色值；
  2. 用 cssutils 解析出 `选择器 -> {属性: 值}`；
  3. 只保留「简单选择器」——不含伪类/伪元素/at-rule/兄弟与属性选择器；
     带空格的**后代选择器**（如 `pre code`、`blockquote p`）是允许的，
     因为 BeautifulSoup 的 select 本身支持。
这样主题作者能精确控制每一处字号、行高、边距，排版才可能真的对。
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

import cssutils
import yaml

cssutils.log.setLevel(logging.CRITICAL)  # cssutils 对非标准属性极其聒噪

SKILL_DIR = Path(__file__).resolve().parent.parent
BUILTIN_THEMES = SKILL_DIR / "assets" / "themes"


@dataclass
class Theme:
    name: str
    description: str
    base_css: str
    colors: dict = field(default_factory=dict)
    raw: dict = field(default_factory=dict)

    @property
    def section_numbering(self) -> bool:
        return bool(self.raw.get("section_numbering"))

    @property
    def aigc_footer(self) -> bool:
        return bool(self.raw.get("aigc_footer", True))


def theme_dirs() -> list[str]:
    """查找顺序：用户目录（$WECHAT_ARTICLE_HOME/themes）> 内置目录。"""
    out = []
    home = os.environ.get("WECHAT_ARTICLE_HOME")
    if home:
        d = Path(home).expanduser() / "themes"
        if d.is_dir():
            out.append(str(d))
    out.append(str(BUILTIN_THEMES))
    return out


def list_themes() -> list[str]:
    names = set()
    for d in theme_dirs():
        if not os.path.isdir(d):
            continue
        for fn in os.listdir(d):
            if fn.endswith((".yaml", ".yml")):
                names.add(fn.rsplit(".", 1)[0])
    return sorted(names)


def load_theme(name: str) -> Theme:
    path = None
    for d in theme_dirs():
        c = os.path.join(d, f"{name}.yaml")
        if os.path.exists(c):
            path = c
            break
        c = os.path.join(d, f"{name}.yml")
        if os.path.exists(c):
            path = c
            break
    if path is None:
        avail = ", ".join(list_themes())
        raise FileNotFoundError(f"主题不存在: {name}（可用: {avail}）")

    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError(f"主题文件格式错误: {path}")
    for k in ("name", "description", "base_css", "colors"):
        if k not in data:
            raise ValueError(f"主题缺少必填字段 '{k}': {path}")
    return Theme(
        name=data["name"],
        description=data["description"],
        base_css=data["base_css"],
        colors=data.get("colors", {}),
        raw=data,
    )


def theme_meta(name: str) -> dict:
    t = load_theme(name)
    return {
        "name": t.name,
        "description": t.description,
        "primary": t.colors.get("primary", "#333333"),
        "background": t.colors.get("background", "#ffffff"),
    }


def resolve_css_variables(css_text: str, colors: dict) -> str:
    """把 var(--x) 换成 colors 里的实际值（x 支持连字符与下划线写法）。"""

    def replacer(m: re.Match) -> str:
        key = m.group(1).strip().lstrip("-")
        if key in colors:
            return str(colors[key])
        if key.replace("-", "_") in colors:
            return str(colors[key.replace("-", "_")])
        return m.group(0)

    return re.sub(r"var\(\s*--([a-zA-Z0-9_-]+)\s*\)", replacer, css_text)


def _is_simple_selector(selector: str) -> bool:
    """伪类/伪元素/at-rule/兄弟/属性选择器一律拒绝；后代选择器（空格）放行。"""
    selector = selector.strip()
    for ch in (":", "@", ">", "+", "~", "[", "*"):
        if ch in selector:
            return False
    return bool(selector)


def get_inline_css_rules(theme: Theme) -> dict[str, dict[str, str]]:
    """解析 base_css → {选择器: {属性: 值}}，已解析变量、已剔除复杂选择器。"""
    resolved = resolve_css_variables(theme.base_css, theme.colors)
    sheet = cssutils.parseString(resolved, validate=False)
    rules: dict[str, dict[str, str]] = {}
    for rule in sheet:
        if rule.type != rule.STYLE_RULE:
            continue
        props = {p.name: p.value for p in rule.style}
        if not props:
            continue
        for sel in (s.strip() for s in rule.selectorText.split(",")):
            if not _is_simple_selector(sel):
                continue
            if sel in rules:
                rules[sel].update(props)
            else:
                rules[sel] = dict(props)
    return rules
