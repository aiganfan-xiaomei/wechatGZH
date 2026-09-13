# 生图与「链接 / API 填写」指南

本文回答两件事：

1. **怎么接入自己的生图服务**（外置生图 API）。
2. **所有需要你填的东西在哪填**——API 地址、密钥、链接、作者名、appid/secret。

不想改代码、只想开箱用免费后端，直接跳到 §1「默认后端」即可。

---

## 0. 配置在哪

只有一个配置文件：

```
~/.workbuddy/wechat-article/config.json
```

* Windows：`C:\Users\<你>\.workbuddy\wechat-article\config.json`
* macOS / Linux：`~/.workbuddy/wechat-article/config.json`
* 想换位置：设环境变量 `WECHAT_ARTICLE_HOME=/你的目录`，配置就放该目录下。

没有这个文件也能跑（用内置默认值），只是发布和自定义后端会缺参数。
从 `assets/config.example.json` 复制一份改名即可。**该文件不在 git 仓库里，你的密钥不会被提交。**

> ⚠️ 别把填好密钥的 `config.json` 提交到任何公开仓库。仓库自带的 `.gitignore` 已经忽略常见密钥文件名，但位置在 `~/.workbuddy` 下，本就不在仓库内。

---

## 1. 默认后端（不改代码）

`image.backend = "auto"` 时，按顺序降级尝试，任一个成功就用它：

```
custom（你配了才启用） → local（本地/局域网模型） → pollinations → pollinations-alt
→ siliconflow → cloudflare → huggingface → local-svg（离线兜底）
```

| 后端 | 要不要密钥 | 说明 |
|------|-----------|------|
| `pollinations` / `pollinations-alt` | 不要 | 免费、无需注册。匿名档右下角有水印，脚本会自动裁掉。可能限流/503。 |
| `siliconflow` | 要 `siliconflow_key` | 国内可用，有免费额度。 |
| `cloudflare` | 要 `cf_account_id` + `cf_token` | Workers AI 的 FLUX schnell，有免费额度。 |
| `huggingface` | 要 `hf_token` | 免费档会排队/限流。 |
| `local` / `local-a1111` / `local-openai` | 不要 | 打你本机/局域网的模型服务。 |
| `local-svg` | 不要 | 纯本地几何兜底，永不失手，但只是渐变卡片，别当正式配图。 |
| `custom` | 看你接口 | **外置自定义接口，见下一节。** |

强制只用某一个：

```json
{ "image": { "backend": "siliconflow" } }
```

密钥也可以走环境变量，避免写进文件：
`SILICONFLOW_API_KEY` / `CF_ACCOUNT_ID` / `CF_API_TOKEN` / `HF_TOKEN`。

**经验之谈**：免费文生图模型画「示意图」很不靠谱——会塞进假的英文单词、深色噪点、标签画错。
所以流程图/结构图/对比图这类**内文图，优先用内置的代码图示引擎**（`images.json` 里写 `"render": "pipeline"` 等），
AI 生图只用来做**封面和氛围图**。理由与实测见 `references/free-image-apis.md`。

---

## 2. 外置生图 API（`image.custom`）—— 接你自己的服务

设计目标：**任何「发一个 HTTP 请求 → 拿回一张图」的接口都能接，不用改一行代码。**

`config.json` 的 `image.custom` 里填：

| 字段 | 必填 | 说明 |
|------|------|------|
| `enabled` | 否 | 设 `false` 可临时停用（默认启用，URL 填了才真正生效） |
| `url` | **是** | 接口地址。可含占位符 |
| `method` | 否 | `POST`（默认）或 `GET` |
| `headers` | 否 | 请求头。可含占位符与 `${环境变量}` |
| `body` | 否 | 请求体（`GET` 时忽略）。可含占位符 |
| `response_path` | 否 | 图片字段的点号路径，如 `data.0.b64_json`。留空自动猜 |
| `timeout` | 否 | 超时秒数，默认取 `image.request_timeout` |

### 2.1 占位符（写在 url / headers / body 里）

| 占位符 | 会替换成 |
|--------|---------|
| `{prompt}` | 组装好的完整提示词 |
| `{width}` / `{height}` | 目标像素（已按 8 对齐） |
| `{seed}` | 随机种子 |
| `{negative_prompt}` | `image.negative_prompt` 的值 |

另外，任何字符串里都可以写 `${ENV_VAR}`，运行时会从环境变量取值——
**密钥就可以不落盘**：

```json
"headers": { "Authorization": "Bearer ${MY_IMAGE_KEY}" }
```

### 2.2 响应怎么被解析（三种都支持）

脚本拿到响应后依次判断，你多半什么都不用配：

1. **响应本身就是图片**（按魔数识别 PNG / JPEG / GIF / WebP / SVG）→ 直接当图片用。GET 直出图就是这种。
2. **响应是 JSON，里面是 base64** → 自动解码。兼容 `data:image/png;base64,xxxx` 前缀。
3. **响应是 JSON，里面是图片 URL** → 自动去下载那张图。

JSON 里找图片字段的路径，优先用你写的 `response_path`；没写就按这套常见结构自动猜：

```
data.0.b64_json → data.0.url → images.0.url → images.0 → output.0
→ result.0 → url → image → b64_json
```

路径用**点号**表示层级，数字段当下标用，例如 `data.0.url` 指 `{"data":[{"url":...}]}`。
猜不准时会明确报错，并提示你该往 `response_path` 填什么。

---

### 2.3 五个可复制示例

**例 1 · OpenAI 兼容接口（返回 base64）** —— 最常见

```json
{
  "image": {
    "custom": {
      "url": "https://api.example.com/v1/images/generations",
      "method": "POST",
      "headers": { "Authorization": "Bearer ${MY_IMAGE_KEY}", "Content-Type": "application/json" },
      "body": {
        "model": "flux-schnell",
        "prompt": "{prompt}",
        "width": "{width}",
        "height": "{height}",
        "response_format": "b64_json"
      },
      "response_path": "data.0.b64_json"
    }
  }
}
```

**例 2 · 同上但返回图片 URL** —— 只改 `response_path`

```json
"response_path": "data.0.url"
```

（其实留空也能自动猜到，写出来更稳。）

**例 3 · GET 直接吐图** —— 无需 `response_path`，无需 `body`

```json
{
  "image": {
    "custom": {
      "url": "https://api.example.com/render?prompt={prompt}&w={width}&h={height}&seed={seed}",
      "method": "GET"
    }
  }
}
```

**例 4 · 兼容老式 SD-WebUI / Forge（`/sdapi/v1/txt2img`）**

```json
{
  "image": {
    "custom": {
      "url": "http://192.168.1.20:7860/sdapi/v1/txt2img",
      "method": "POST",
      "headers": { "Content-Type": "application/json" },
      "body": {
        "prompt": "{prompt}",
        "negative_prompt": "{negative_prompt}",
        "width": "{width}",
        "height": "{height}",
        "seed": {seed},
        "steps": 26
      },
      "response_path": "images.0"
    }
  }
}
```

> `images.0` 的值是纯 base64（A1111 风格），脚本能直接解。

**例 5 · 企业网关，密钥放环境变量，响应结构自定义**

```json
{
  "image": {
    "custom": {
      "url": "https://gateway.corp.example/ai/image",
      "method": "POST",
      "headers": { "X-API-KEY": "${CORP_IMAGE_KEY}", "Content-Type": "application/json" },
      "body": { "task": "text2image", "text": "{prompt}", "size": "{width}x{height}" },
      "response_path": "result.images.0.base64"
    }
  }
}
```

> 注意示例用 `{prompt}`（花括号）是**占位符**；密钥用 `${CORP_IMAGE_KEY}`（美元花括号）是**环境变量**。两者不要混。

---

### 2.4 排错

| 现象 | 原因 / 解法 |
|------|-----------|
| 生图时完全没看到 custom 的日志 | `url` 没填，或 `enabled: false` → 该后端被静默跳过（这是有意的） |
| `拿不到图片字段，请…指定 response_path` | 自动猜失败。用 `response_path` 显式指定，如 `data.0.b64_json` |
| `外置接口返回既不是图片也不是 JSON` | 接口返回了 HTML（错误页）或纯文本。先用 curl 单独验证接口 |
| `HTTP 401/403` | 密钥错。检查 `${ENV_VAR}` 是否真的被导出到当前 shell |
| `HTTP 400` + 模型不认宽高 | 有些接口只收固定尺寸枚举，把 `body` 里的 `{width}x{height}` 换成固定值 |
| 图片字段既非 URL 也非 base64 | 返回的是二进制但没被魔数识别（少见格式）。让接口返回标准 png/jpg |

想只测 custom 一个后端（不走降级链）：

```json
{ "image": { "backend": "custom" } }
```

---

## 3. 「链接 / API 填写」总表

所有需要你手工填的东西，一览：

| 你要填的东西 | 填在哪 | 字段 |
|-------------|--------|------|
| 公众号 AppID | `config.json` 或环境变量 | `appid` / `WECHAT_APPID` |
| 公众号 AppSecret | `config.json` 或环境变量 | `secret` / `WECHAT_SECRET` |
| 作者名（≤16 字） | `config.json` | `author`（也可在每篇 frontmatter 覆盖） |
| 外置生图 API 地址 | `config.json` | `image.custom.url` |
| 外置生图 API 密钥 | `config.json` 或环境变量 | `image.custom.headers` 里写 `${ENV_VAR}` |
| 免费后端密钥 | `config.json` 或环境变量 | `siliconflow_key` / `cf_token` / `hf_token` |
| 本地模型地址 | `config.json` | `image.local_base`（留空自动探测） |
| 阅读原文链接 | 每篇 `article.md` frontmatter | `source_url` |
| 正文里的站内链接（视频号/文章/往期） | 每篇 `article.md` 正文 | `:::video` / `:::article` / `:::readmore`（见 `docs/embeds.md`） |
| 正文里的外链 | 每篇 `article.md` 正文 | 正常写 `[文字](https://...)`，自动转脚注 |

### 3.1 关于 API 地址的两个提醒

1. **外链 vs 站内链接，待遇不同。** 正文里指向外部的 `[文字](https://...)` 会被微信过滤，
   脚本统一转成「上标脚注 + 文末参考链接」；指向 `mp.weixin.qq.com` 的**站内**链接则是另一套做法，
   见 `docs/embeds.md`。
2. **图片 URL 也会被过滤。** 正文 `<img src>` 必须是微信 `media/uploadimg` 返回的
   `mmbiz.qpic.cn` 地址，外部图床 URL 会被系统丢掉。这一步 `publish.py` 会自动做，你只管写本地图片路径。

---

## 4. 多后端组合的取舍（实测结论）

| 场景 | 建议 |
|------|------|
| 有企业/自建生图网关 | 配 `image.custom` + `backend: "custom"` |
| 手边有 ComfyUI / SD | 配 `local_base`，快且免费、不联网 |
| 什么都没有、要快速出图 | 留 `backend: "auto"`，让它走 pollinations（有水印会自裁） |
| 内文示意图 | 用代码图示引擎（`render`），别用 AI |
| 纯离线 / 断网 | 会落到 `local-svg` 兜底；正式发文前建议换掉 |
