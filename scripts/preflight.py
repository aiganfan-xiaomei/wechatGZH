#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""wechat-article 环境自检：依赖 / 配置 / 出口 IP / 主题 / 风格。"""

from __future__ import annotations

import importlib
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wc_common import config_path, egress_ip, home_dir, load_config, wechat_egress_ip  # noqa: E402
from wc_theme import list_themes, theme_meta  # noqa: E402


def main() -> int:
    print("=" * 58)
    print("wechat-article 自检")
    print("=" * 58)

    ok = True

    # 1. Python 与依赖
    print(f"\n[1] Python {sys.version.split()[0]}  ({sys.executable})")
    for mod, hint in (
        ("PIL", "Pillow"),
        ("requests", "requests"),
        ("yaml", "PyYAML"),
        ("markdown", "Markdown"),
        ("bs4", "beautifulsoup4"),
        ("cssutils", "cssutils"),
    ):
        try:
            m = importlib.import_module(mod)
            print(f"    ✓ {hint:14s} {getattr(m, '__version__', 'ok')}")
        except Exception:
            ok = False
            print(f"    ✗ {hint:14s} 缺失 → python -m pip install {hint}")

    # 2. 状态目录与配置
    h = home_dir()
    cp = config_path()
    print(f"\n[2] 状态目录 {h}")
    print(f"    config.json {'存在' if cp.exists() else '不存在（将使用默认值，发布时需 appid/secret）'}")
    cfg = load_config()
    print(f"    appid : {cfg['appid'] or '(未配置)'}")
    print(f"    secret: {'已配置' if cfg['secret'] else '(未配置)'}")
    print(f"    author: {cfg['author'] or '(未配置)'}")
    print(f"    默认主题: {cfg.get('default_theme')}   默认风格: {cfg.get('default_style')}")
    print(f"    图片后端: {cfg['image'].get('backend')}")

    # 3. 出口 IP
    print("\n[3] 出口 IP（IP 白名单要填下面这个）")
    appid = str(cfg.get("appid") or "").strip()
    secret = str(cfg.get("secret") or "").strip()
    if appid:
        # 微信自己回显的地址才是权威值：通用回显服务可能给出另一个地址族
        wip = wechat_egress_ip(appid, secret)
        if wip == "ok":
            print("    ✓ 微信已返回 access_token —— 白名单已生效，无需再改")
        else:
            print(f"    → {wip}   ← 微信实际看到的地址，白名单要填这个")
            if wip != "unknown":
                print(f"    微信公众平台 → 设置与开发 → 安全中心 → IP 白名单 → 添加 {wip}")
            else:
                ok = False
                print("    ✗ 没能问出微信看到的 IP，检查网络/代理")
        gip = egress_ip()
        if gip not in ("unknown", wip) and wip != "ok":
            print(f"    （参考：通用回显服务看到的是 {gip}，与微信不一致时以微信那个为准）")
    else:
        gip = egress_ip()
        if gip == "unknown":
            ok = False
            print("    ✗ 无法获取出口 IP，检查网络/代理")
        else:
            print(f"    → {gip}   （仅通用回显；配置 appid 后可给出微信权威值）")
            print(f"    微信公众平台 → 设置与开发 → 安全中心 → IP 白名单 → 添加 {gip}")

    # 4. 主题与风格
    names = list_themes()
    print(f"\n[4] 排版主题（{len(names)} 套，YAML / wewrite 内核）")
    for n in names:
        m = theme_meta(n)
        print(f"    · {n:20s} {m['primary']:9s} {m['description']}")
    try:
        gi = importlib.import_module("gen_images")
        print(f"\n[5] 内置配图风格（{len(gi.STYLES)} 种）")
        for k, v in gi.STYLES.items():
            print(f"    · {k:16s} {v['label']}")
    except Exception as e:  # noqa: BLE001
        ok = False
        print(f"\n[5] ✗ 无法加载 gen_images.py：{e}")

    # 6. 中文字体（封面叠字用）
    print("\n[6] 中文字体")
    try:
        gi = importlib.import_module("gen_images")
        f = gi.find_font()
        print(f"    {'✓ ' + f if f else '✗ 未找到中文字体，封面将不叠字'}")
    except Exception:
        print("    - 跳过")

    print("\n" + "=" * 58)
    print("自检完成：" + ("全部通过，可开始创作" if ok else "存在问题，见上方 ✗"))
    print("=" * 58)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
