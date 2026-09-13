# wechat-article

> 把「一句话选题」变成「公众号草稿箱里一篇排版好、配图齐的文章」。
> 一个给 AI 助手（Claude / CodeBuddy 等支持 skill 的环境）用的**微信公众号写作全流程技能**。

写正文 → 配图（代码图示 + AI 封面）→ 按 wewrite 内核渲染微信兼容排版 → 推进草稿箱。
生图后端可换、可接自己的 API，视频号/站内链接以**占位卡**形式留给你在编辑器里补。

---

## 目录

- [它能做什么](#它能做什么)
- [快速开始](#快速开始)
- [工作流](#工作流)
- [配图：两条路线](#配图两条路线)
- [接自己的生图 API](#接自己的生图-api)
- [正文里接视频号 / 其他文章](#正文里接视频号--其他文章)
- [文档地图](#文档地图)
- [目录结构](#目录结构)
- [依赖与安装](#依赖与安装)
- [能力边界](#能力边界)
- [致谢与许可](#致谢与许可)

---

## 它能做什么

| ✅ 能做 | ❌ 不能做 |
|--------|----------|
| 撰写 / 润色正文 Markdown | 生成视频、音频 |
| 封面：AI 生成（10 种风格） | 代运营互动、回复留言 |
| 内文图：**代码绘制**极简图示（7 种版式，中文标签准确） | 自动「群发」文章（只能进草稿箱，发布要你手动点） |
| 渲染微信兼容 HTML（全内联样式 + 10 套 wewrite 主题） | 个人订阅号的草稿箱接口（无权限） |
| 推送 / 更新 / 删除草稿箱草稿 | 未经确认就对外发布 |
| 接你自己的外置生图 API（配置即用，不改代码） | 通过 API 插入视频号卡片、站内文章超链接 |

## 快速开始

```bash
# 1) 装依赖（Python 3.9+）
python -m pip install Pillow requests PyYAML Markdown beautifulsoup4 cssutils

# 2) 自检：会打印依赖、出口 IP、配置、主题与图示清单
python scripts/preflight.py

# 3) 写一篇（每篇稿件一个目录）
#    <slug>/article.md  +  <slug>/images.json

# 4) 排版，产出浏览器可直接看的预览页
python scripts/build_article.py article.md --outdir build
#    → build/preview.html  ← 打开它看效果

# 5) 推进草稿箱（需要公众号 AppID/Secret + IP 白名单）
python scripts/publish.py ip                                  # 拿要填白名单的出口 IP
python scripts/publish.py check                               # 验证白名单是否生效
python scripts/publish.py article article.md --cover images/cover.jpg
```

> 只写作 + 排版，不需要配置任何密钥。要发草稿箱时才需要 AppID/Secret，
> 且需把服务器出口 IP 加入公众号后台白名单（**要填的是「微信看到」的 IP**，见 FAQ）。

## 工作流

```
选题 / 文章 / 链接
      │
      ▼
Step 0  确认需求（写什么 / 发去哪 / 什么调性）
Step 1  建工作目录 <slug>/
Step 2  写 article.md（frontmatter + Markdown + ::: 组件）
Step 3  列 images.json（图示 render 或 AI subject）→ gen_images.py
Step 4  排版 build_article.py → build/preview.html  ← 先给用户看
Step 5  publish.py → 草稿箱（拿到 media_id）
```

细节见 [`SKILL.md`](SKILL.md)。

## 配图：两条路线

| 类型 | 适用 | 写法 | 为什么 |
|------|------|------|--------|
| **代码图示**（推荐做内文图） | 流程、结构、对比、时间线、规格 | `images.json` 里 `"render": "pipeline"` 等 | 免费文生图模型画示意图极不稳：会塞假英文、深色噪点、标签画错。代码绘制**永远干净、中文标签准确、可复现** |
| **AI 生成** | 封面、氛围图、艺术化题图 | `"subject": "英文主体描述"` | 画面丰富有质感，配合封面叠字效果好 |

内置图示版式：`pipeline` / `tree` / `layers` / `compare` / `timeline` / `matrix` / `hero`。
内置 AI 风格 10 种，见 [`references/image-styles.md`](references/image-styles.md)。

## 接自己的生图 API

**不用改代码**，在 `config.json` 的 `image.custom` 里填 URL / 请求头 / 请求体即可。
URL 与请求体里可写占位符 `{prompt}` `{width}` `{height}` `{seed}` `{negative_prompt}`，
密钥可写 `${ENV_VAR}` 从环境变量取（不落盘）。

```json
{
  "image": {
    "backend": "custom",
    "custom": {
      "url": "https://api.example.com/v1/images/generations",
      "method": "POST",
      "headers": { "Authorization": "Bearer ${MY_IMAGE_KEY}", "Content-Type": "application/json" },
      "body": { "model": "flux-schnell", "prompt": "{prompt}",
                "width": "{width}", "height": "{height}", "response_format": "b64_json" },
      "response_path": "data.0.b64_json"
    }
  }
}
```

响应会自动识别三种形态：**图片本体 / JSON+base64 / JSON+图片URL**。
5 个可复制示例（含 GET 直出、SD-WebUI、企业网关）与排错见 **[`docs/images.md`](docs/images.md)**。

## 正文里接视频号 / 其他文章

**重要**：草稿箱 API 带不过去视频号卡片和站内文章超链接——
`draft/add` 会丢掉视频号卡片的 `video_snap_card` 属性（结果一直「加载中」），
站内文章链接只能靠编辑器工具栏「超链接」插入。

所以本 skill 用**占位卡**：正文里写 `:::video` / `:::article` / `:::readmore`，
排版后渲染成一块带 `⚠️` 提示的卡片；发布进草稿箱后，你在编辑器里把它替换成真组件即可。

```markdown
:::video 三分钟讲清楚 Remotion
（可选）说明文字
:::

:::article 官方团队的排版指南
https://mp.weixin.qq.com/s/xxxxxx
:::

:::readmore 往期推荐
- 用 Markdown 写公众号 | https://mp.weixin.qq.com/s/aaa
- 免费生图 API 实测 https://mp.weixin.qq.com/s/bbb
:::
```

哪些能自动、哪些要手动、编辑器里具体怎么操作，见 **[`docs/embeds.md`](docs/embeds.md)**。

## 文档地图

| 文件 | 内容 |
|------|------|
| [`SKILL.md`](SKILL.md) | 技能主文档：完整工作流、容器语法、硬限 |
| [`docs/images.md`](docs/images.md) | 外置生图 API 配置、链接 / API 填写总表、排错 |
| [`docs/embeds.md`](docs/embeds.md) | 正文接视频号 / 站内文章 / 其它富组件的做法与限制 |
| [`docs/faq.md`](docs/faq.md) | 装不上、生图失败、排版不对、白名单 40164 等 |
| [`references/layout-guide.md`](references/layout-guide.md) | 容器组件、主题、微信兼容规则 |
| [`references/wechat-api.md`](references/wechat-api.md) | 草稿箱接口字段、错误码、白名单原理 |
| [`references/free-image-apis.md`](references/free-image-apis.md) | 免费生图后端实测与取舍 |
| [`references/image-styles.md`](references/image-styles.md) | 10 种 AI 风格与 7 种图示版式 |
| [`assets/config.example.json`](assets/config.example.json) | 配置模板（含 custom 生图接口示例） |

## 目录结构

```
wechat-article/
├── SKILL.md                 # 技能入口（含 YAML frontmatter）
├── scripts/                 # 全部逻辑，纯 Python
│   ├── preflight.py         # 环境自检
│   ├── build_article.py     # Markdown → 微信 HTML（排版）
│   ├── wc_converter.py      # wewrite 移植的转换内核
│   ├── wc_theme.py          # 主题加载 / CSS 内联
│   ├── gen_images.py        # 配图生成（图示 + AI + 外置 API）
│   ├── diagrams.py          # 代码绘制图示引擎
│   ├── publish.py           # 草稿箱上传 / 发布相关
│   └── wc_common.py         # 配置、HTTP、路径
├── assets/
│   ├── config.example.json
│   └── themes/*.yaml        # 10 套主题（真 CSS）
├── references/              # 参考文档
├── docs/                    # 生图 / 嵌入 / FAQ
├── evals/                   # 技能评测样本
└── examples/                # 可直接跑的示例稿件
```

## 依赖与安装

* Python **3.9+**
* 包：`Pillow requests PyYAML Markdown beautifulsoup4 cssutils`
* 配置（可选）：`~/.workbuddy/wechat-article/config.json`，
  可用环境变量 `WECHAT_ARTICLE_HOME` 改目录。**该文件不在本仓库内，密钥不会被提交。**

## 能力边界

* **发布**：只把文章推进**草稿箱**，「发布/群发」这一步由你手动点——
  同时那也是插入视频号、站内链接和最后检查的时机。
* **账号类型**：草稿箱 / 发布接口只对**服务号 / 认证订阅号**开放，个人订阅号无此权限。
* **微信兼容**：产物只含内联样式，无 `<style>`/`<script>`；外链会被微信过滤，
  脚本统一转成「上标脚注 + 文末参考链接」。

## 致谢与许可

* 排版内核移植自 **[imraywang/wewrite](https://github.com/imraywang/wewrite)**（MIT），
  并修正了其两处缺陷（CJK 全角标点间距、容器同行参数），详见 `wc_converter.py` 内注释。
* 本项目以 [MIT License](LICENSE) 开源。
