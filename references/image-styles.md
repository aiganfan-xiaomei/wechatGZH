# 配图：选型 + 10 种 AI 风格

## 先选型：代码图示 vs AI 生成

**内文示意图优先用「代码图示」，不要用 AI 生图。** 这是实测结论，不是偏好：

免费文生图模型（Pollinations/FLUX 等）画"示意图"时表现很差——
会往图里塞看起来像乱码的假英文、深色低对比噪点、把「流程/结构」画成一格一格的糊团，
而且**画不对中文标签**。作者的真实体验就是"配图丑"。

代码图示（`scripts/diagrams.py`）由 Pillow 按版式精确绘制：

* 白底或深底 + 单一强调色，**永远干净、不脏乱**；
* 中文标签用系统字体（`msyhbd.ttc`）真实绘制，**标签一定准确**；
* 完全可复现，同一个 spec 永远出同一张图；
* 不联网、不消耗额度、秒出。

| 内文图内容 | 用 `render` |
|-----------|------------|
| 流程、步骤、阶段 | `pipeline` |
| 一层分出多条 / 并行 | `tree` |
| 分层结构、叠加信息 | `layers` |
| A vs B 对照 | `compare` |
| 时间顺序、里程碑 | `timeline` |
| 参数/规格一览 | `matrix` |
| 封面卡（不想用 AI 时） | `hero` |

AI 生成留给你真正需要"质感"的地方：**封面**、氛围图、艺术化题图。
封面本来就要叠一层标题蒙版，AI 的噪点会被盖住，观感反而好。

配色（`palette`）：`ink-blue` `ink-purple` `ink-teal` `ink-red` `ink-gold` `ink-slate`
（白底）／ `dark-cyan` `dark-violet`（深底，适合科技、夜间题材）。

`--list-recipes` 查看所有版式；图示 spec 字段见 SKILL.md Step 3。

---

# 10 种内置 AI 风格

`scripts/gen_images.py` 内置以下 10 种风格。调用时用 `--style <id>` 指定，或在图片 spec 里给单张图覆盖。

风格由 **英文提示词前缀** 定义（免费图生模型对英文提示词更敏感），中文语义由排版层叠加。
封面图会自动加 `safe=true` 且不写文字，避免模型乱码汉字。

| # | id | 中文名 | 适合的内容 | 推荐比例 |
|---|----|--------|-----------|----------|
| 1 | `minimal-line` | 极简线性插画 | 观点文、方法论、知识科普 | 2.35:1 封面 / 16:9 内文 |
| 2 | `flat-vector` | 扁平矢量 | 商业分析、运营复盘、教程 | 2.35:1 / 16:9 |
| 3 | `isometric-3d` | 等距 3D | 产品拆解、系统架构、流程说明 | 2.35:1 / 1:1 |
| 4 | `watercolor` | 水彩手绘 | 生活方式、个人成长、散文 | 2.35:1 / 4:3 |
| 5 | `cyber-tech` | 赛博科技 | AI、编程、硬件、前沿技术 | 2.35:1 / 16:9 |
| 6 | `editorial` | 杂志编辑风 | 深度报道、行业观察、人物 | 2.35:1 / 3:2 |
| 7 | `ink-bw` | 水墨黑白 | 文化、历史、思辨、长文 | 2.35:1 / 3:2 |
| 8 | `neon-gradient` | 霓虹渐变 | 品牌、活动、年轻向内容 | 2.35:1 / 1:1 |
| 9 | `clay-3d` | 黏土 3D | 轻松科普、亲子、生活方式 | 2.35:1 / 1:1 |
| 10 | `guochao` | 国潮国风 | 传统文化、节日、东方美学 | 2.35:1 / 3:2 |

## 各风格提示词前缀（原文）

```
minimal-line    minimalist single-line illustration, clean solid white background, thin black strokes,
                generous negative space, abstract geometric shapes, flat 2d vector, editorial art, no text, no letters

flat-vector     flat vector illustration, bold simple geometric shapes, limited 3-color palette,
                modern corporate style, clean composition, subtle grain, no text, no letters

isometric-3d    isometric 3d illustration, soft clay-like rendering, pastel palette, clean white background,
                miniature diorama scene, soft ambient shadows, high detail, no text, no letters

watercolor      delicate watercolor illustration, soft washes of translucent color, cold-press paper texture,
                hand painted, muted pastel tones, artistic bleed edges, no text, no letters

cyber-tech      dark cyberpunk technology illustration, deep navy background, glowing cyan and violet neon accents,
                circuit and grid motifs, futuristic HUD elements, volumetric light, cinematic, no text, no letters

editorial       editorial magazine illustration, swiss design influence, bold color blocks,
                strong grid composition, risograph print texture, sophisticated restraint, no text, no letters

ink-bw          black and white ink brush illustration, sumi-e style, high contrast, textured rice paper,
                dramatic brush strokes, minimalist composition, no text, no letters

neon-gradient   gradient mesh background, vibrant neon gradient, smooth color transitions,
                abstract liquid shapes, glossy 3d blobs, modern digital art, no text, no letters

clay-3d         3d clay render, cute soft rounded shapes, matte material, studio three-point lighting,
                soft pastel colors, playful mood, high fidelity octane render, no text, no letters

guochao         chinese guochao style illustration, traditional ink and mineral pigment colors,
                gold and vermilion accents, auspicious clouds and mountain motifs, elegant oriental aesthetic,
                no text, no letters
```

## 提示词组装规则

最终发给模型的提示词由三段拼成，**顺序不能反**：

```
<主体描述 subject> + ", " + <风格前缀> + ", " + <通用质量后缀>
```

* `subject` 放**最前面**。实测风格词放前面会让模型只顾氛围、忽略主体；主体放前面贴合度明显更高。
* `subject` 建议写英文短语，越具体越好（形状、构图、内容物），例如
  `abstract glowing geometric pipeline converging into a single rectangular video frame, isometric line art`。
* 通用质量后缀（脚本内置，可用 spec 的 `quality` 字段覆盖）：
  `high quality, professional, balanced composition, centered subject, ample headroom for text overlay`
* `role: "cover"` 会额外追加 `no people, no human figures, no faces, no text, no letters, no watermark, no logo`——
  实测不加这句，cyber-tech 一类的风格很容易生成一张人脸，和科技选题完全不搭。
* 封面叠字由本地 Pillow 完成（字体 `msyhbd.ttc`），**不要让模型画汉字**，一定会乱码。

## 比例 → 像素

| 比例 | 生成尺寸 | 用途 |
|------|----------|------|
| `2.35:1` | 1410×600 | 公众号封面（首图裁剪 2.35_1） |
| `1:1` | 900×900 | 封面方图裁剪 / 头像卡 |
| `16:9` | 1280×720 | 内文插图 |
| `4:3` | 1200×900 | 内文插图（偏竖版内容） |
| `3:2` | 1200×800 | 内文插图 |

> 微信 `media/uploadimg` 要求单张图 **jpg/png 且 < 1MB**。脚本写完会自动按目标比例居中裁剪、缩放，并迭代 JPEG 质量直到低于 900KB。
