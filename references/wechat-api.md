# 微信公众号草稿箱 API 速查

所有接口**必须在服务端调用**（本 skill 的 `publish.py` 就是那个服务端）。
调用方公网出口 IP 必须加入后台白名单，否则返回 `40164`。

## 0. 前置：白名单 IP

* 路径：微信公众平台 → **设置与开发 → 安全中心** → **IP 白名单**
  （旧版控制台在「开发管理 → 开发设置」下）
* 规则：支持具体 IP 与 CIDR（`1.2.3.4` 或 `1.2.3.0/24`），**不支持** `IP:端口` 和 `1.2.3.*`
* 未在白名单时返回：
  ```json
  {"errcode":40164,"errmsg":"invalid ip 1.2.3.4 ipv6 ::ffff:1.2.3.4, not in whitelist rid: xxx"}
  ```
* 保存后约 **5～10 分钟**生效。

### ✅ 要填的是「微信看到的 IP」，不是随便一个回显网站的 IP

```bash
python scripts/publish.py ip       # 配置了 appid 时给出权威值
python scripts/preflight.py        # 自检里的 [3] 段同样给出
```

**为什么必须问微信自己**：`api.ipify.org` / `ifconfig.me` 这类回显服务返回的是
**它们各自看到的结果**。本机同时具备 IPv4 / IPv6 出口时，回显服务可能返回 IPv6，
而 `api.weixin.qq.com` 只有 A 记录（纯 IPv4），微信看到的是完全不同的地址。
照着回显结果填白名单 → 一直 `40164`，而且看起来"明明加对了"。

拿到权威值的办法就是上面那两个命令：它们故意用一个错 secret 发 token 请求，
微信会在 `40164` 的 `errmsg` 里**回显它实际看到的来源 IP**。

> 已踩过的实例：回显服务报一个 IPv6 地址（形如 `2001:xxxx::xxxx`），
> 而微信实际看到的是一个 IPv4 `A.B.C.D`。两者完全不是一个地址族，照回显结果填会一直失败。

### ⚠️ 走代理时的坑

如果系统设了 `HTTP_PROXY` / `HTTPS_PROXY`（本地 Clash / V2Ray 之类），Python 的 `urllib` 会**默认遵循**这些环境变量，
于是**连 api.weixin.qq.com 的请求也从代理出去**。这时：

1. 微信看到的出口 IP 由代理链路决定，不是你本机的宽带 IP。
2. **代理端口/节点一变，出口 IP 就变，白名单立刻失效**——表现为"昨天还能发，今天突然 40164"。
   所以每次发布失败先重跑一次 `publish.py ip`，而不是怀疑凭证。
3. 对策：给 `api.weixin.qq.com` 配**固定节点或直连**规则；或把多个可能出口 IP 都加进白名单。
4. 想绕过代理直连微信：
   ```bash
   HTTPS_PROXY= HTTP_PROXY= python scripts/publish.py check
   ```
   此时出口 IP 会变成本机真实 IP，**那个 IP 也得在白名单里**——两个都加最省事。

## 1. 获取 access_token

```
GET https://api.weixin.qq.com/cgi-bin/token?grant_type=client_credential&appid=APPID&secret=SECRET
```

返回 `{"access_token":"...","expires_in":7200}`；失败返回 `{"errcode":40164,...}` 或 `{"errcode":40125,...}`。

> 稳定版接口（推荐生产用）：`POST /cgi-bin/stable_token`，body `{"grant_type":"client_credential","appid":"..","secret":".."}`。
> 本 skill 用普通 token 接口并本地缓存 7000 秒。

## 2. 上传正文图片（关键）

```
POST https://api.weixin.qq.com/cgi-bin/media/uploadimg?access_token=ACCESS_TOKEN
Content-Type: multipart/form-data
media=@image.jpg
```

返回 `{"url":"http://mmbiz.qpic.cn/XXXXX","errcode":0,"errmsg":"ok"}`

**限制**：仅 `jpg`/`png`，**单张 < 1MB**；不占用素材库 10 万张配额。
**正文里的 `<img src>` 必须用这个接口返回的 url —— 外部图片 URL 会被系统过滤掉。**

## 3. 上传封面（永久素材）

```
POST https://api.weixin.qq.com/cgi-bin/material/add_material?access_token=ACCESS_TOKEN&type=image
Content-Type: multipart/form-data
media=@cover.jpg
```

返回 `{"media_id":"...","url":"http://mmbiz.qpic.cn/..."}`
`media_id` 即草稿的 `thumb_media_id`（**必须是永久 MediaID**，临时素材的 id 不行）。

## 4. 新增草稿

```
POST https://api.weixin.qq.com/cgi-bin/draft/add?access_token=ACCESS_TOKEN
Content-Type: application/json（body 需 UTF-8，不要 ascii 转义）
```

```json
{
  "articles": [
    {
      "article_type": "news",
      "title": "标题，≤32 字",
      "author": "作者，≤16 字",
      "digest": "摘要，≤120 字；不填则抓正文前 54 字",
      "content": "<p>正文 HTML</p>",
      "content_source_url": "https://... 阅读原文链接",
      "thumb_media_id": "永久素材 media_id（图文消息必填）",
      "need_open_comment": 0,
      "only_fans_can_comment": 0
    }
  ]
}
```

返回 `{"media_id":"..."}`。

**字段硬限**
| 字段 | 限制 |
|------|------|
| title | ≤ 32 字 |
| author | ≤ 16 字 |
| digest | ≤ 120 字 |
| content | < 2 万字符，且 < 1MB；会剔除 JS；外链图被过滤 |
| content_source_url | ≤ 1KB |
| thumb_media_id | 图文消息必填，须为永久 MediaID |

> ⚠️ 不要传 `"\u4f5c\u8005\u540d"` 这种 Unicode 转义，直接传中文原文。Python 里用 `json.dumps(..., ensure_ascii=False).encode('utf-8')`。

## 5. 其它常用

| 用途 | 端点 |
|------|------|
| 草稿列表 | `GET /cgi-bin/draft/batchget`（POST，body `{"offset":0,"count":20,"no_content":1}`） |
| 草稿详情 | `POST /cgi-bin/draft/get`（body `{"media_id":".."}`） |
| 更新草稿 | `POST /cgi-bin/draft/update`（body `{"media_id":"..","index":0,"articles":{...}}`） |
| 删除草稿 | `POST /cgi-bin/draft/delete`（body `{"media_id":".."}`） |
| 发布草稿 | `POST /cgi-bin/freepublish/submit`（body `{"media_id":".."}`） |
| 校验正文 HTML | `POST /cgi-bin/draft/...` 无独立接口；`publish.py --dry-run` 做本地校验 |
| 查询发布状态 | `POST /cgi-bin/freepublish/get` |

## 6. 常见错误码

| 码 | 含义 | 处理 |
|----|------|------|
| 40001 | access_token 无效/被刷新 | 重新获取 token |
| 40164 | IP 不在白名单 | 加入白名单，等 5~10 分钟 |
| 40005 | 文件格式不对 | 图片用 jpg/png |
| 40009 | 图片太大 | 压到 < 1MB |
| 45009 | 接口调用频率超限 | 降低频率 |
| 41001 | 缺少 access_token | 检查 URL 参数 |
| 48001 | 接口未授权 | 该账号类型无此权限（订阅号无部分接口） |
| 53503 | 草稿箱功能未开启 | 后台开启，或用 `/cgi-bin/draft/switch` |
| 53404/53405/53406 | 带货商品相关 | 删除 product_info 后重试 |

> 订阅号（个人号）**没有**草稿箱/发布接口权限，本 skill 发布功能仅对**服务号 / 认证订阅号**生效。
