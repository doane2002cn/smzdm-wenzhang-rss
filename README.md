# 什么值得买文章 RSS

通过 GitHub Actions 每小时抓取“什么值得买”文章，把结果发布到 GitHub Pages，再由 Huginn 转成 RSS。

## 在线地址

- 文章页: https://doane2002cn.github.io/smzdm-wenzhang-rss/
- 每日精选 RSS: https://doane2002cn.github.io/smzdm-wenzhang-rss/daily_digest.xml
- 每日精选 Markdown: https://doane2002cn.github.io/smzdm-wenzhang-rss/daily_digest.md
- 每日精选 JSON: https://doane2002cn.github.io/smzdm-wenzhang-rss/daily_digest.json
- 完整社区日榜: https://doane2002cn.github.io/smzdm-wenzhang-rss/community_daily_rank.md
- Actions: https://github.com/doane2002cn/smzdm-wenzhang-rss/actions

## 部署方式

1. GitHub Pages 来源设为 `main` 分支的 `/docs` 目录。
2. GitHub Actions 每小时运行 `crawl.yml`。
3. 生成器更新每日精选 Markdown、JSON、RSS 和完整社区日榜。
4. 工作流提交并推送 `main`，GitHub Pages 自动重建站点。

完整配置见 [IFLOW.md](./IFLOW.md)。
