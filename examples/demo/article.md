---
title: 用 Markdown 写公众号：从排版到配图
author: 示例作者
digest: 一份可直接跑通的示例稿件，演示 frontmatter、容器组件、代码图示，以及视频号/站内链接占位卡的写法。
theme: professional-clean
source_url: https://github.com/
---

# 用 Markdown 写公众号：从排版到配图

这是一份**可直接跑通**的示例稿件。它把本 skill 支持的语法都用了一遍，
你可以照着改，也可以直接删掉重写。

## 为什么用 Markdown 写公众号

微信编辑器里调排版很痛苦：字号、行高、留白都不好精确控制。
把内容留在 Markdown 里，用脚本渲染成**全内联样式**的 HTML，排版就变成了可复现的事。

:::callout tip 先看结论
正文用 Markdown，配图用代码图示，发布进草稿箱后再手工补视频号和站内链接。
:::

## 容器组件

正文可以嵌入一组预制的容器，参数与 `:::` 同行：

:::summary 一句话说清楚
容器组件让「突出重点」不需要手调样式——主题决定了它们的配色与间距。
:::

:::timeline
**Step 1** 写 `article.md`
**Step 2** 跑 `build_article.py`
**Step 3** 打开 `build/preview.html`
:::

:::steps
安装依赖
生成配图
渲染排版
推进草稿箱
:::

## 配图交给代码

内文示意图**不要用 AI 生图**——免费模型会塞进假的英文单词、深色噪点。
用代码绘制的图示，文字准确、可复现：

![三种方案对比](images/fig-compare.jpg)

图注：左右对照能一眼看清差异。

## 正文里接视频号与站内文章

下面两块是**占位卡**。微信草稿箱 API 带不过去这两类富组件，
所以它们在排版产物里会显示成带提示的卡片，发布后由你在编辑器里替换。

:::video 三分钟讲清楚 Remotion
用代码生成视频的完整演示。
:::

:::article 官方团队的排版指南
https://mp.weixin.qq.com/s/xxxxxxxxxx
把移动端字号、行高、留白的经验讲透了。
:::

:::readmore 往期推荐
- 免费生图 API 实测 | https://mp.weixin.qq.com/s/aaa111
- 微信兼容排版避坑 https://mp.weixin.qq.com/s/bbb222
:::

## 结尾

外链会被微信过滤，所以脚本会把它们转成脚注，比如 [wewrite 项目](https://github.com/imraywang/wewrite) 会变成上标。

:::highlight 划重点
本文由示例脚本演示，`docs/` 下有完整说明。
:::
