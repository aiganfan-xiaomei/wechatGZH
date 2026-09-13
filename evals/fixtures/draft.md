---
title: 我们为什么把排版引擎整个换掉了
author: 编辑部
digest: 从一堆样式 token 换成"真 CSS 主题"，排版终于能对上了。
theme: tech-modern
source_url: https://github.com/imraywang/wewrite
---

:::summary 一句话说清楚
这次把排版内核换成了 wewrite 的移植版：主题是完整 CSS，converter 负责确定性地内联。
中英混排、表格、外链这些在微信里最容易翻车的地方，现在都由脚本统一处理。
:::

## 换内核的原因

之前的做法是给每套主题写一堆样式 token，再由脚本拼成 HTML。问题是**token 表达不了真正的排版意图**——
字号和行高能调，但段间距、边框、强调色之间的配合很难描述清楚。

改成"主题即 CSS"之后，主题作者可以精确控制每一处细节。

:::callout info 一句实话
这不是重写，是移植。上游 [imraywang/wewrite](https://github.com/imraywang/wewrite) 已经把这条路走通了，
我们只是把它的 converter 移植过来，并修了两个明显的缺陷。
:::

## 改了什么

:::steps
把主题从 themes.json 换成 10 套 YAML，每套是一份完整 CSS
用 cssutils 解析出「选择器 → 属性」，再逐条内联到匹配元素
修掉 CJK 间距误伤全角标点的问题
让 :::summary 标题 这种同行写法能被正确识别
:::

## 时间线

:::timeline
**第一周** 读上游 converter 源码，梳理管线顺序
**第二周** 移植主题系统与容器组件
**第三周** 修表格表头、加图示引擎
:::

## 效果对比

| 维度 | 旧方案 | 新方案 |
|------|--------|--------|
| 主题定义 | 样式 token 字典 | 完整 CSS |
| 排版保真度 | 一般 | 高 |
| 可扩展性 | 改脚本 | 加一个 YAML |
| 中英混排 | 有误伤 | 已修正 |

## 还是个坑

微信不支持 `<style>`，所有样式必须内联。这意味着**主题里每一条规则都要能在内联后依然成立**，
像 `:hover`、媒体查询这类写法直接失效。写主题时要留心。

启动命令：

```bash
python scripts/build_article.py article.md --outdir build --theme tech-modern
```

:::quote
好的排版不是让读者注意到设计，而是让读者忘记设计。
:::
