# 生图后端（本地模型 + 免费 API）

`gen_images.py` 内置一条 **后端降级链**：从上到下依次尝试，第一个成功即返回。

> **先想清楚要不要 AI 生图。** 内文"示意图"请优先用代码图示（`render` 字段，见
> `image-styles.md`）——免费模型画示意图会塞假英文、发暗、标签画错。AI 生图留给封面与氛围图。

## 降级链顺序（`backend: "auto"`）

| # | 后端 id | 是否需 key | 说明 |
|---|---------|-----------|------|
| 1 | `local` | ❌ | 自动探测本机模型：A1111/Forge `/sdapi/v1/txt2img` 或 OpenAI 兼容 `/v1/images/generations`。**最快、最可控，且能真正用上 negative prompt** |
| 2 | `pollinations` | ❌ 不需要 | 默认远程主力，GET 直接返回 JPEG |
| 3 | `pollinations-alt` | ❌ 不需要 | `pollinations.ai/p/{prompt}` 备用域名 |
| 4 | `siliconflow` | ✅ 需要 | 国内直连快，需 `SILICONFLOW_API_KEY` |
| 5 | `cloudflare` | ✅ 需要 | FLUX-schnell，需 `CF_ACCOUNT_ID` + `CF_API_TOKEN` |
| 6 | `huggingface` | ✅ 需要 | 需 `HF_TOKEN` |
| 7 | `local-svg` | ❌ 不需要 | 离线兜底：渐变几何卡片，永远可用 |

也可以只用一个：`backend` 设成具体名字（`"local-a1111"` / `"pollinations"` …）。

## 本机实测结论（2026-09，出口走代理）

| 后端 | 结果 |
|------|------|
| `pollinations`（flux） | ✅ 可用，约 5s/张 |
| `pollinations`（nologo=true） | ⚠️ **水印去不掉**，右下角仍有 `pollinations.ai`；需靠裁边（见下） |
| `pollinations`（model 参数） | ⚠️ 匿名档换 `model` 返回的图可能相同（疑似忽略 model / 命中缓存） |
| `local` | ⛔ 本机无本地模型（无 GPU、无 Ollama、常见端口全关）→ 自动跳过。**接口已实现，待用户本地跑起来即可用** |
| `siliconflow` / `cloudflare` / `huggingface` | ⛔ 未测（缺 key）。接口按官方文档实现，填 key 即用 |
| HuggingFace Space（FLUX.1-schnell，gradio） | 🟡 submit 返回 event_id，可用但需按 gradio 协议轮询；未接入主链路 |

## 本地模型（`local`）

无需 API key。`detect_local_base()` 会探测常见端口：
`7860`(A1111/Forge) `7861` `8188`(ComfyUI) `1234` `8000` `8080` `5000` `3000` `11434` `8501`。
命中后自动判断类型（能用 `/sdapi/v1/options` 则是 A1111，否则按 OpenAI 兼容处理）。

```json
{
  "image": {
    "local_base": "http://127.0.0.1:7860",
    "local_kind": "auto",        // auto | openai | a1111
    "local_model": "",           // OpenAI 兼容端点用；A1111 忽略
    "local_steps": 26,
    "local_cfg": 7.0,
    "negative_prompt": "text, letters, words, watermark, low quality, blurry, cluttered"
  }
}
```

* A1111/Forge：`POST {base}/sdapi/v1/txt2img`，返回 `images[0]` 为 base64。
* OpenAI 兼容（如某些 `sd.cpp` / 自建网关）：`POST {base}/v1/images/generations`，支持 `b64_json` 或 `url`。
* 只有本地模型会让 `negative_prompt` 真正生效；Pollinations 匿名档不支持负向提示词。

## 1. Pollinations（远程默认，零配置）


* 仓库：https://github.com/pollinations/pollinations
* 文档：https://github.com/pollinations/pollinations/blob/master/APIDOCS.md
* 端点：`GET https://image.pollinations.ai/prompt/{urlencoded_prompt}`
* 参数：`width` `height` `seed` `model` `nologo` `enhance` `safe` `private`

```bash
curl "https://image.pollinations.ai/prompt/a%20cozy%20cabin?width=1024&height=576&model=flux&nologo=true&safe=true" -o out.jpg
```

**关键坑（已在本 skill 脚本内处理）**：
* 必须带浏览器 `User-Agent`，否则直接 `403 Forbidden`；再加 `Referer: https://pollinations.ai/` 更稳。
* 匿名档限流约 **15 秒 1 次**，脚本对同一批图会顺序请求并 sleep。
* `nologo=true` 匿名档**去不掉水印**——右下角会盖一枚 `pollinations.ai`。
  脚本的对策是**超采样再裁边**：按目标尺寸的 `1/0.84` 请求，出图后裁掉右侧 16.5% 与底部 12.5%，
  水印正好落在裁剪区外，最终尺寸仍是目标尺寸（见 `gen_images.py` 的 `WATERMARK_TRIM` / `SUPERSAMPLE`）。
  若你注册了免费账号并配了 token，可以把 `SUPERSAMPLE` 调回 `1.0` 以省像素。
* 提示词必须 URL 编码（脚本用 `urllib.parse.quote`）。
* `safe=true` 会开启严格 NSFW 过滤，命中直接报错。

## 2. SiliconFlow 硅基流动（可选，国内快）

* 文档：https://docs.siliconflow.cn/
* 端点：`POST https://api.siliconflow.cn/v1/images/generations`
* 头：`Authorization: Bearer $SILICONFLOW_API_KEY`
* 体：`{"model":"Kwai-Kolors/Kolors","prompt":"...","image_size":"1024x576","batch_size":1}`
* 返回：`{"images":[{"url":"..."}]}`

## 3. Cloudflare Workers AI（可选）

* 端点：`POST https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/ai/run/@cf/black-forest-labs/flux-1-schnell`
* 头：`Authorization: Bearer $CF_API_TOKEN`
* 体：`{"prompt":"...","steps":4}` → 返回 base64（`result.image`）
* 免费额度按 neurons 计，约 230 张/天，UTC 0 点重置。

## 4. Hugging Face Inference（可选）

* 端点：`POST https://api-inference.huggingface.co/models/{model}`（如 `black-forest-labs/FLUX.1-schnell`）
* 头：`Authorization: Bearer $HF_TOKEN`
* 体：`{"inputs":"..."}` → 直接返回图片二进制

## 5. local-svg 兜底（离线可用）

不联网时生成本地几何渐变卡片（Pillow 绘制）：纯色/渐变底 + 网格 + 大标题，风格与主题色一致。
用于「网络全挂但仍然要出一版可排版产物」的场景。

## 配置方式

脚本按以下顺序读取配置（后者覆盖前者）：

1. 环境变量：`WECHAT_ARTICLE_HOME`（状态目录，默认 `~/.workbuddy/wechat-article`）
2. 状态目录下的 `config.json` 的 `image` 段：

```json
{
  "image": {
    "backend": "auto",
    "pollinations_model": "flux",
    "siliconflow_key": "",
    "cf_account_id": "",
    "cf_token": "",
    "hf_token": "",
    "request_timeout": 150,
    "rate_limit_sleep": 16,
    "negative_prompt": "text, letters, words, captions, watermark, logo, low quality, blurry, cluttered",
    "local_kind": "auto",
    "local_base": "",
    "local_model": "",
    "local_steps": 26,
    "local_cfg": 7.0,
    "auto_detect_local": true,
    "diagram_palette": "ink-blue"
  }
}
```

3. 也识别通用环境变量 `SILICONFLOW_API_KEY` / `CF_ACCOUNT_ID` / `CF_API_TOKEN` / `HF_TOKEN`

`backend` 设为具体后端名（如 `"pollinations"`）则只用该后端；`"auto"` 走完整降级链。
