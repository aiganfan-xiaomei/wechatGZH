# 常见问题（FAQ）

## 安装 / 环境

**Q：`python: command not found` 或找不准用哪个 Python？**
用 Python 3.9+。装依赖：

```bash
python -m pip install Pillow requests PyYAML Markdown beautifulsoup4 cssutils
```

装完跑一次自检，它会告诉你缺什么：

```bash
python scripts/preflight.py
```

> 如果你想用某个特定环境（venv / conda），直接用它对应的 python 解释器跑脚本即可，
> 脚本不挑环境，只挑包。

**Q：图示里的中文变成方框/乱码？**
系统里没有中文字体。脚本会依次找 `msyhbd.ttc`（微软雅黑）、`simhei.ttf`（黑体）、
`NotoSansSC`、`PingFang`（macOS）、`NotoSansCJK`（Linux）。
Linux 服务器上装一个即可：`apt install fonts-noto-cjk`。

**Q：Windows 控制台输出中文乱码？**
脚本已把 stdout 重设为 UTF-8。若仍乱码，执行 `chcp 65001` 后再跑。

---

## 配图

**Q：一生成图就走 `local-svg` 兜底（那张渐变卡片）？**
说明远程后端全失败了。看日志里的 `[fallback]` 行：
* `pollinations: HTTP 503` → 免费档限流，等一会儿或换个后端；
* 全都超时 → 检查网络/代理；
* 你要是在内网，那就配 `image.custom` 走自己的服务（见 `docs/images.md`）。

**Q：我想用自己的生图 API，怎么接？**
不用改代码，填 `config.json` 的 `image.custom` 即可。完整字段与 5 个示例见 `docs/images.md`。

**Q：AI 生成的图上有奇怪的英文单词/水印？**
免费文生图模型常干这事。两个对策：
1. 提示词里已经加了 `no text, no letters, no watermark`，但仍会漏；
2. **示意图别用 AI 生图**，改用内置代码图示引擎（`images.json` 里写 `"render": "pipeline"` 等）——
   文字准确、可复现、无噪点。

**Q：封面上的字被裁掉了？**
封面比例固定 `2.35:1`（微信首图裁剪），大字默认放在下三分之一。
如果标题太长，用 `\n` 手动断行，或用更短的标题。

---

## 排版

**Q：排版「不对」/和预览不一致？**
排版内核是 wewrite 的移植版，**以 `references/layout-guide.md` 与主题 YAML 为准**。
要改就改主题 YAML 或换主题，**别手改生成的 `article.html`**——下次构建就被覆盖。

**Q：表头文字看不见了？**
这是主题写法的经典坑（`thead` 渐变 + `th` 白字 + `tr` 白底，把渐变盖住）。
converter 已自动把表头底色下推到每个 `th` 并做纯色兜底。若还不对，换主题。

**Q：摘要被截得很短？**
旧版按「字节」截，中文会砍到 ~40 字。现已改为按「字」截，上限 120 **字**。
如果你看到异常，确认用的是本仓库最新脚本。

**Q：中英文之间的空格不对？**
CJK 间距只在中文字与拉丁字母/数字之间加空格，**全角标点不加**。
这是对 wewrite 上游的有意修正（上游会产出「MP4 。」这类错误）。

---

## 发布到草稿箱

**Q：报 `40164 invalid ip ... not in whitelist`？**
出口 IP 不在白名单。**关键**：要填的是「**微信看到**的 IP」，不是随便一个回显网站的 IP。
两个命令会给权威值：

```bash
python scripts/publish.py ip
python scripts/preflight.py
```

拿到后在后台 **设置与开发 → 安全中心 → IP 白名单** 添加，等 5~10 分钟生效。
原理见 `references/wechat-api.md` §0。

**Q：昨天还能发，今天突然 40164？**
多半是**代理节点换了**。`urllib` 默认遵循 `HTTP_PROXY`/`HTTPS_PROXY`，出口 IP 会随节点变。
对策：给 `api.weixin.qq.com` 配固定节点或直连；或把可能用到的出口 IP 都加进白名单。
绕过代理直连：

```bash
HTTPS_PROXY= HTTP_PROXY= python scripts/publish.py check
```

**Q：报「草稿箱功能未开启」/ 48001？**
* 个人**订阅号没有**草稿箱/发布接口权限，本 skill 的发布功能只对**服务号 / 认证订阅号**生效；
* 后台需开启「草稿箱」功能。

**Q：`thumb_media_id` 报错？**
封面必须是**永久素材** ID（`material/add_material` 返回的），临时素材 ID 不行。脚本会自动处理。

**Q：图片上传报 40009 / 图片太大？**
正文图单张必须 < 1MB。脚本会自动压到 900KB 以内；若你手动换图，注意这个限制。

**Q：我只想写作排版，不发草稿箱行吗？**
行。只用到 Step 2（写 `article.md`）和 Step 4（`build_article.py` 排版）即可，
连 `appid`/`secret` 都不用配。`build/preview.html` 浏览器直接打开就能看效果。

**Q：能自动「发布」吗？**
不能，也不该。skill 只负责把文章推进**草稿箱**；
「发布」这一步请你手动点——同时那也是你插入视频号/站内链接、最后检查的时机（见 `docs/embeds.md`）。

---

## 其它

**Q：配置和密钥存在哪？会进 git 吗？**
存在 `~/.workbuddy/wechat-article/config.json`（可用 `WECHAT_ARTICLE_HOME` 改），
**不在仓库目录内**，不会随代码提交。仓库的 `.gitignore` 另外忽略了常见密钥文件名，双保险。

**Q：一篇稿件的目录长什么样？**
```
<slug>/
├── article.md      # 正文（frontmatter + Markdown + ::: 组件）
├── images.json     # 配图任务单
├── images/         # 生成的图
└── build/          # 排版产物：article.html / preview.html / meta.json
```

**Q：怎么换主题？**
```bash
python scripts/build_article.py --list-themes        # 看 10 套主题
python scripts/build_article.py article.md --theme sspai
```
或在 `article.md` 的 frontmatter 写 `theme: sspai`。
