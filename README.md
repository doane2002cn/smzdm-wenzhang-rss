# 什么值得买文章 RSS

通过 GitHub Actions 每小时抓取“什么值得买”文章，把结果发布到 GitHub Pages，再由 Huginn 转成 RSS。

## 在线地址

- 文章页: https://doane2002cn.github.io/smzdm-wenzhang-rss/
- Actions: https://github.com/doane2002cn/smzdm-wenzhang-rss/actions

## 部署方式

1. GitHub Pages 来源设为 `main` 分支的 `/docs` 目录。
2. GitHub Actions 定时或手动运行 `crawl.yml`。
3. 爬虫更新 `docs/index.html` 和 `docs/articles.json`。
4. 工作流提交并推送 `main`，GitHub Pages 自动重建站点。

完整配置见 [IFLOW.md](./IFLOW.md)。
