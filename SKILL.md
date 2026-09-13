---
name: wechat-article
description: 写公众号文章的全流程技能——撰写正文、配图（AI 生成封面 + 代码绘制的极简图示）、按 wewrite 内核渲染成微信公众号可直接粘贴的排版，并把成品推送进公众号草稿箱。当用户说到任何以下情形时都必须使用本技能：想写/生成/润色一篇公众号文章或推文；给文章配图、做封面图、生成题图或插图、画示意图；把 Markdown 排版成公众号样式、抱怨"排版不好看/排版不对"；提到公众号、推文、草稿箱、订阅号、服务号、封面图、微信排版、mmbiz、appid/AppSecret、IP 白名单、发布到草稿箱、@公众号；以及 ANY 用户提供一篇文章、一个选题或一个链接并希望产出一篇公众号成品时，即使用户没有明确说出"公众号"三个字。
---

# 微信公众号文章创作与发布

把「一句话选题」变成「草稿箱里一篇排版好、配图齐的文章」。

## 能力边界

| 能做 | 不能做 |
|------|--------|
| 撰写/润色正文 Markdown | 生成视频、音频 |
| 封面：AI 生成（10 种风格） | 代运营互动、回复留言 |
| 内文图：代码绘制极简图示（7 种版式） | 发布到公众号（只进草稿箱，发布需人工点） |
| 渲染微信兼容 HTML（全内联样式 + 10 套 wewrite 主题） | 个人订阅号的草稿箱接口（无权限） |
| 推送/更新/删除草稿箱草稿 | 未经用户确认就对外发布 |

## 环境

脚本在本技能 `scripts/`，用 **Python 3.9+** 运行。依赖：
`Pillow requests PyYAML Markdown beautifulsoup4 cssutils`。
缺了先装：

```bash
python -m pip install Pillow requests PyYAML Markdown beautifulsoup4 cssutils
```

状态目录 `~/.workbuddy/wechat-article/`（可用 `WECHAT_ARTICLE_HOME` 覆盖），存放 `config.json` 与 token 缓存。

**开工前先自检**：

```bash
python scripts/preflight.py
```

它会打印依赖、出口 IP、配置、主题与图示清单。**IP 那行就是要填进公众号后台白名单的地址。**

## 排版内核（重要）

排版由 `scripts/wc_converter.py` 完成，它是 **imraywang/wewrite 转换器的忠实移植**：
主题是**真 CSS**（`assets/themes/*.yaml`，10 套），converter 用 cssutils 解析成选择器→属性，
再逐条内联到匹配元素上。这样字号、行高、边距、强调色都能精确控制——**排版"对不对"就以它为准**。

想调排版，改主题 YAML 或换主题，**不要手改生成的 HTML**。

对上游做的两处修正（都在 `wc_converter.py` 里有注释说明）：
1. **CJK 间距**：只在中文字与拉丁字母/数字之间加空格，**不含全角标点**。上游把全角标点也计入，
   会产出「MP4 。」「： Remotion」这类错误。
2. **容器解析**：`:::summary 标题`、`:::callout info 标题` 这类**同一行带参数**的写法上游识别不了，
   会原样输出。这里已修正，并支持容器内多段落（微信里裸换行会塌成一行）。

另有一处**主题缺陷的兜底**：主题若写了 `thead{background:渐变}` + `th{color:#fff}` + `tr{background:#fff}`，
行的白底会盖住表头渐变导致白字表格头「消失」。converter 会把 thead 底色**下推到每个 th**（长写法 + 纯色兜底），
使预览与微信端表现一致。

## 标准工作流

### Step 0 · 确认需求（别跳过）

最少问清三件事，其余自己决定：

1. **写什么**——选题 / 文章 / 链接 / 已有草稿；
2. **发去哪**——只要正文？要配图？要排版产物？要进草稿箱？
3. **什么调性**——目标读者 + 风格（可给 3 个建议让它挑）。

用户已说清楚就直接开干，别反问已经回答过的问题。

### Step 1 · 建工作目录

每篇稿件一个独立目录，避免串味：

```
<workspace>/<slug>/
├── article.md      # 正文（frontmatter + Markdown + ::: 组件）
├── images.json     # 配图任务单
├── images/         # 生成的图
└── build/          # 排版产物（article.html / preview.html / meta.json）
```

### Step 2 · 写 `article.md`

frontmatter（全部可选，但发布时 `title` 必需）：

```markdown
---
title: 标题（≤32 字，有钩子）
author: 作者名（≤16 字）
digest: 摘要（≤120 字；超长会被自动截断）
cover: images/cover.jpg
theme: professional-clean
source_url: 阅读原文链接
---
```

正文写作要求：

- **H2 起正文结构**，`#` 一级标题会被自动剔除（微信标题栏单独展示）。
- 段落短，2~4 句一段；移动端阅读。
- 观点文要有明确判断 + 证据边界；教程文要有可执行步骤。
- **不要编造作者个人经历、数据或引述**。没有来源就说"据报道/公开资料显示"，或直接删掉。
- 外链正常写 `[文字](https://...)`，脚本会自动转成上标脚注 + 文末参考链接（微信会屏蔽外链）。

排版组件（直接写在 Markdown 里，参数可与 `:::` 同行）：

```markdown
:::summary 标题        （正文首行不写标题时取首行作标题）
:::callout tip|info|warning|danger 标题
:::quote 引文
:::pullquote 金句      （居中大字）
:::label [pill] 小标签
:::steps               （每行一步）
:::timeline            （每行 `**时间** 事件`）
:::dialogue            （左气泡；`> ` 开头为右气泡）
:::highlight 标题      （琥珀色提示框）
:::video 视频号标题     （视频号占位卡，发布后在编辑器手动插入）
:::article 文章标题     （站内文章占位卡，正文首行可写 URL）
:::readmore 往期推荐    （每行 `标题 | url`）
```

> `:::video` / `:::article` / `:::readmore` 产出的是**占位卡**：微信草稿箱 API
> 写入不了视频号卡片和站内超链接（`draft/add` 会丢 `video_snap_card`），
> 所以这几块会在文里留一块带 `⚠️` 提示的卡片，发布后由你在公众号编辑器里手动替换。
> 细则见 `docs/embeds.md`。

完整语法与示例见 `references/layout-guide.md`。

### Step 3 · 列配图任务 `images.json`

**配图分两类，按内容选，别一股脑用 AI 生图：**

| 类型 | 适用 | 怎么写 | 为什么 |
|------|------|--------|--------|
| **代码图示**（推荐做内文图） | 流程图、结构、对比、时间线、规格 | `"render": "pipeline"` 等 | 免费文生图模型画"示意图"极不稳：会塞假英文、深色噪点、标签画错。代码绘制**永远干净、中文标签准确、可复现** |
| **AI 生成** | 封面、氛围图、艺术化题图 | `"subject": "英文主体描述"` | 画面丰富、有质感；配合封面叠字效果好 |

图示版式（`render` 取值）：`pipeline` 横向流程 / `tree` 扇出树 / `layers` 层叠 /
`compare` 左右对照 / `timeline` 时间轴 / `matrix` 规格矩阵 / `hero` 封面卡。
配色（`palette`）：`ink-blue` `ink-purple` `ink-teal` `ink-red` `ink-gold` `ink-slate`
`dark-cyan` `dark-violet`。`--list-recipes` 可查。

```json
{
  "images": [
    { "id": "cover", "role": "cover", "ratio": "2.35:1",
      "render": "hero", "palette": "dark-violet",
      "title": "封面大字\n可换行", "subtitle": "副标题" },

    { "id": "fig1", "role": "inline", "ratio": "16:9",
      "render": "pipeline", "palette": "ink-purple",
      "title": "小标题", "items": ["第一步", "第二步", "第三步"],
      "note": "底部注释", "caption": "图 1　图注" },

    { "id": "fig2", "role": "inline", "ratio": "16:9",
      "render": "compare",
      "left":  {"title": "A", "bullets": ["要点一", "要点二"]},
      "right": {"title": "B", "bullets": ["要点一", "要点二"]} },

    { "id": "cover_ai", "role": "cover", "ratio": "2.35:1",
      "subject": "abstract glowing pipeline, geometric nodes",
      "title": "封面大字" }
  ]
}
```

要诀：

- 图示 `title` 用**中文短语**，会把真实文字画进图里；想手动断行就写 `\n`。
- AI 图 `subject` 用**英文短语**描述主体；风格前缀与质量后缀由脚本自动补。
  风格 id 见 `references/image-styles.md`（`--list-styles` 也能列）。
- 封面比例固定 `2.35:1`（微信首图裁剪），建议再出一张 `1:1`。
- 内文图 3~6 张，每张必须有信息增量，不要为凑数插图。
- 图片会自动裁剪到目标比例、压到 900KB 以内（微信 `uploadimg` 单张硬限 1MB）。

生成：

```bash
python scripts/gen_images.py --spec images.json --outdir images
```

生图后端（AI 图）按降级链自动尝试：**外置自定义接口（若已配置）→ 本地模型 → Pollinations → SiliconFlow → Cloudflare → HuggingFace → 本地几何兜底**。
本地模型支持 OpenAI 兼容 `/v1/images/generations` 与 A1111/Forge `/sdapi/v1/txt2img`，会自动探测常见端口；
显式配置见 `config.json` 的 `local_base`。后端清单与实测结论见 `references/free-image-apis.md`。

**想接自己的生图服务**（AnyAPI / 自建网关 / 企业内部模型）：不用改代码，只填 `config.json` 的
`image.custom`（URL/请求头/请求体里可写 `{prompt}` `{width}` `{height}` `{seed}`，密钥可写 `${ENV_VAR}`）。
完整字段、5 个可复制示例与排错见 `docs/images.md`。

### Step 4 · 排版

```bash
python scripts/build_article.py article.md --outdir build            # 用 frontmatter 里的 theme
python scripts/build_article.py article.md --outdir build --theme sspai --paste-safe
python scripts/build_article.py --list-themes                        # 列出 10 套主题
```

产出：

- `build/article.html` —— 发布用片段（全内联样式）
- `build/preview.html` —— **浏览器直接打开看效果**，手机宽度卡片还原公众号阅读体验
- `build/article.paste.html` —— `--paste-safe` 时生成，文本节点加 `<span leaf="">`，可直接复制进编辑器
- `build/meta.json` —— 字数/图片数/外链脚注/校验结果

脚本自动完成所有微信兼容修复：样式内联、外链转脚注、列表转 section、CJK-Latin 加空格、
加粗标点外移、表头可读性修复、暗黑模式属性注入、AIGC 声明页脚。
**不要手工改 `article.html`**——要改就改 `article.md` 重跑。

**先把 `build/preview.html` 给用户看**，确认后再发。

### Step 5 · 进草稿箱

**首次使用必须先过白名单这一关**：

```bash
python scripts/publish.py ip        # 拿到出口 IP，请用户加到公众号后台 IP 白名单
python scripts/publish.py check     # 白名单生效后验证凭证（会明确报 40164 并给解法）
```

然后一条龙：

```bash
python scripts/publish.py article article.md --cover images/cover.jpg --theme professional-clean
```

这条命令会：生成配图（若存在 `images.json`）→ 排版 → 把正文图片逐张上传换成 `mmbiz.qpic.cn` 地址 →
上传封面永久素材拿 `thumb_media_id` → 调 `draft/add` 写入草稿箱 → 结果写进 `build/publish-result.json`（含 `media_id`）。

先干跑一遍看校验：

```bash
python scripts/publish.py article article.md --cover images/cover.jpg --dry-run
```

其它常用：

```bash
python scripts/publish.py list --count 10                              # 看草稿列表
python scripts/publish.py update --media-id ID --article-json art.json # 更新草稿
python scripts/publish.py delete --media-id ID                         # 删草稿
```

## 发布前硬限（脚本会拦，但写的时候就该避开）

| 项 | 上限 |
|----|------|
| 标题 | 32 字 |
| 作者 | 16 字 |
| 摘要 | 120 字 |
| 正文 | 2 万字符 |
| 图片 | 10 张以内；正文图单张 < 1MB |
| 封面 | `thumb_media_id` **必须是永久素材 ID** |
| 正文图 | `src` 必须是 `media/uploadimg` 返回的地址，外部 URL 会被过滤 |

## 交付话术

完成一步就报一件事，别把过程当成果：

- 排版完成 → 给出 `build/preview.html` 的绝对路径，让用户直接在浏览器看。
- 需要白名单 → 明确给 IP 原文 + 后台路径，不要只说"去加个白名单"。
- 进了草稿箱 → 报 `media_id`，并提醒"草稿箱里可预览/发布，发布动作请你手动点"。

## 参考文档

| 文件 | 什么时候读 |
|------|-----------|
| `references/layout-guide.md` | 写容器组件、查主题、查微信兼容规则 |
| `references/image-styles.md` | 选 AI 风格、调提示词、查比例像素 |
| `references/free-image-apis.md` | 换生图后端、配本地模型、排查生图失败 |
| `references/wechat-api.md` | 查接口字段、错误码、白名单规则 |
| `docs/images.md` | 接自己的外置生图接口（custom 后端）、填链接与 API |
| `docs/embeds.md` | 正文接视频号 / 站内文章链接的做法与限制 |
| `docs/faq.md` | 装不上、生图失败、排版不对、白名单等常见问题 |
