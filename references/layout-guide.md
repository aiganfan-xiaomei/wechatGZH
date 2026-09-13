# 微信兼容排版指南

排版内核是 [imraywang/wewrite](https://github.com/imraywang/wewrite) 转换器的移植版：
**主题是"真 CSS"，converter 负责确定性内联**。`build_article.py` 自动完成下表所有修复，
写作时只需专注内容。

## 主题（10 套，`assets/themes/*.yaml`）

主题 = `name` / `description` / `colors` / `base_css`（完整 CSS）。
converter 用 `colors` 解析 `var(--primary)` 之类的变量，再用 cssutils 把 CSS 拆成
「选择器 → 属性」，逐条内联到匹配元素上。**要改排版就改主题 YAML 或换主题。**

| 主题 | 主色 | 适合 |
|------|------|------|
| `professional-clean` | `#2563eb` | 大多数商业内容（默认） |
| `tech-modern` | `#7c3aed` | 技术、产品 |
| `warm-editorial` | `#d97706` | 生活方式、文化 |
| `minimal` | `#333333` | 黑白灰，内容至上 |
| `sspai` | `#c7372f` | 数码、效率工具（少数派风） |
| `midnight` | `#60a5fa` | 深色底，技术、夜间阅读 |
| `bauhaus` | `#e63226` | 几何感、设计 |
| `minimal-gold` | `#b8860b` | 高端品牌、精品内容 |
| `bold-navy` | `#1e3a5f` | 金融商务、行业分析 |
| `ink` | `#4a4a4a` | 文化人文，宣纸底 |

`--list-themes` 可列。主题字段 `section_numbering: true` 会给 H2 加 `01/02` 编号；
`aigc_footer: false` 可关掉文末 AI 声明。

## 对 wewrite 上游的两处修正

移植时改了上游两个明确缺陷（`wc_converter.py` 内有注释）：

1. **CJK 间距**只作用于"中文 ↔ 拉丁/数字"边界，**不含全角标点**。
   上游把 `\uff00-\uffef` 也计入，会产出「MP4 。」「： Remotion」这类错误。
   标点自带视觉留白，不需再加空格。
2. **容器开块同行参数**：`:::summary 标题`、`:::callout info 标题` 上游要求名字后必须立刻换行，
   否则整块当普通文本原样输出。这里已支持同行参数，并把容器正文按空行分段。

另外补了一个**主题缺陷兜底**：若主题写了 `thead{background:渐变}` + `th{color:#fff}` + `tr{background:#fff}`，
在预览页里 `tr` 的白底会盖住 thead 渐变，白字表头就"消失"了。converter 把 thead 底色
下推到每个 `th`（`background-color` 纯色 + `background-image` 渐变），预览与微信端一致。

## 硬约束（会被微信剥离或渲染错的东西）

| 约束 | 后果 | 本工具的处理 |
|------|------|--------------|
| `<style>` / `<link>` 外部样式 | 被剥离 | 所有 CSS **内联**进 `style` 属性 |
| `<script>` / 事件属性 | 被禁用 | 不输出任何 JS |
| `position:fixed/sticky`、`animation`、`@keyframes`、`filter`、`backdrop-filter`、`transform:3d` | 不支持 | 不使用 |
| 外部链接 | 未认证号点不开；认证号也可能被拦 | 转成**上标编号脚注** + 文末「参考链接」列表 |
| 原生 `<ul>/<ol>` | 渲染不稳定、缩进丢失 | 转 `<section>` + 手绘 bullet/序号 |
| 外链图片 | **被过滤掉** | 必须 `media/uploadimg` 换成 mmbiz url |
| 中英混排 | 无间距，难看 | CJK 与拉丁/数字边界自动插入空格 |
| 加粗后紧跟中文标点 | 标点被渲染进加粗或错位 | 标点移到 `</strong>` 外 |
| `rgba()` 半透明色 | 部分机型显示不一致 | 一律用 `#rrggbb` 实色 |
| `border: 1px solid` 无色 | 显示异常 | 必须显式写颜色 |
| 渐变 | 部分机型不显示 | 提供纯色兜底 + 渐变叠加 |
| `absolute` 定位的小装饰 | 微信不支持定位 | 改成 flex 布局或内置占位元素 |
| 空元素（分隔线、圆点） | 样式被剥 | 补 `<span leaf=""><br></span>` 占位 |
| 裸文本节点（粘贴路径） | 编辑器会重排 | `--paste-safe` 包 `<span leaf="">` |
| 暗黑模式 | 文字与背景撞色 | 注入 `data-darkmode-color` / `data-darkmode-bgcolor` |

## 尺寸基线

* 正文最大宽度由主题控制（约 720px），预览用 420px 手机卡片还原
* 正文字号 16px（移动端可读下限 15px），行高 1.8~2.0
* 段间距用段落 `margin`，**不用 `<br>` 造空行**
* 图片宽 100%，居中；`figcaption` 转居中小字
* 代码块用 `<pre>` + `white-space:pre-wrap;word-wrap:break-word` 防溢出
* 表格列数 ≤ 4；宽表用外层 `display:block;overflow-x:auto`（微信大表本身就很挤）

## 容器组件（Markdown 里直接写，参数可与 `:::` 同行）

用 `:::` 围栏语法，与 wewrite 兼容：

```markdown
:::summary 一句话说清楚
这是摘要内容。
:::

:::callout info 一句实话
提示框，支持 tip / info / warning / danger 四种；标题写在同一行。
:::

:::quote
好的排版不是让读者注意到设计，而是让读者忘记设计。
:::

:::pullquote
把复杂的事讲清楚，本身就是一种能力。
:::

:::timeline
**2024 Q1** 立项启动
**2024 Q3** MVP 上线
:::

:::steps
安装依赖
运行脚本
推送到草稿箱
:::

:::label pill 小标签

:::highlight 划重点
需要重点强调的一句话。
:::

:::dialogue
用户说的一句话
> 助手回的一句话（右对齐气泡）
:::

:::video 三分钟讲清楚 Remotion
（可选）这张卡片的说明文字
:::

:::article 官方团队的排版指南
https://mp.weixin.qq.com/s/xxxxxx
（可选）为什么推荐这篇
:::

:::readmore 往期推荐
- 用 Markdown 写公众号 | https://mp.weixin.qq.com/s/aaa
- 免费生图 API 实测 https://mp.weixin.qq.com/s/bbb
:::
```

> `:::video` / `:::article` / `:::readmore` 是**占位卡**，不是真卡片。
> 微信草稿箱 API 无法写入视频号卡片和站内文章超链接（原理见 `docs/embeds.md`），
> 所以这三类会渲染成一块带 `⚠️` 提示的占位卡，**发布后需在公众号编辑器里手动替换**。
> 卡片里的 URL 是纯文本，不会走「外链转脚注」。

## 文件结构约定

一篇稿件对应一个工作目录：

```
<article-slug>/
├── article.md          # 正文（Markdown，含 ::: 组件与图片引用）
├── images.json         # 配图任务单（图示 render / AI subject）
├── images/             # 生成的配图（封面 + 内文）
└── build/
    ├── article.html        # 排版后的 HTML 片段（内联样式，用于发布）
    ├── preview.html        # 完整预览页（手机卡片，浏览器直接看效果）
    ├── article.paste.html  # --paste-safe 产物，可复制进编辑器
    └── meta.json           # 字数/图片数/校验结果
```

## 发布前自检清单

- [ ] 所有样式内联，无 `<style>` / `<script>`
- [ ] 图片全部换成 `mmbiz.qpic.cn` url，单张 < 1MB
- [ ] 标题 ≤ 32 字、作者 ≤ 16 字、摘要 ≤ 120 字节
- [ ] 正文 < 2 万字符
- [ ] 外链已转脚注
- [ ] H1 只用于文章大标题，正文从 H2 开始
- [ ] 封面 `thumb_media_id` 为永久素材 ID
- [ ] 在浏览器打开过 `build/preview.html`，确认排版与配图
