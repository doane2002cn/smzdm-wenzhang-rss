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

## Hermes 好价策略

- GitHub 公开仓库只保留脱敏示例：`config/hermes_deal_profile.example.json`
- Hermes 真实 profile：`/opt/data/scripts/state/smzdm_deal_profile.json`
- 文章精选：每天 11:05 推送蓝色飞书卡片
- 好价精选：每天 11:10 推送一张飞书卡片，最多 2 条
- 默认关注：啤酒、起泡酒、智能门锁、3C 数码
- 默认排除：白酒及其相关品牌
- RSS 候选分类：`好价候选池`
