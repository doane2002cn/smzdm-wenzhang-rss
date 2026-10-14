# 什么值得买爬虫 + Huginn RSS 方案

## 项目概述

这是一个基于 GitHub Actions + Huginn 的 RSS 信息抓取和处理方案。该方案通过 GitHub Actions 定时爬取"什么值得买"网站内容，生成静态 HTML 页面，然后通过 Huginn 解析并转换为 RSS 格式。

## 架构设计

```
GitHub Actions (每小时) → 爬取什么值得买 → 生成HTML页面 → GitHub Pages托管
                                                                    ↓
                                                              Huginn定时抓取
                                                                    ↓
                                                              解析HTML并生成RSS
```

## 主要技术栈

- **Python**: 爬虫脚本语言
- **GitHub Actions**: 定时任务和自动化部署
- **GitHub Pages**: 静态页面托管
- **Huginn**: RSS 生成和内容处理
- **Crawl4AI**: 浏览器渲染与页面抓取
- **Playwright**: 无头 Chromium 运行环境

## 项目结构

```
smzdm-wenzhang-rss/
├── .github/workflows/
│   └── crawl.yml              # GitHub Actions 工作流配置
├── docs/
│   ├── index.html             # 生成的静态HTML页面
│   └── articles.json          # 文章数据JSON（调试用）
├── crawler.py                 # 爬虫主脚本
├── requirements.txt           # Python依赖
└── IFLOW.md                   # 项目文档
```

## 部署说明

### 1. GitHub 仓库设置

1. 创建 GitHub 仓库
2. 启用 GitHub Pages：
   - 进入 Settings → Pages
   - Source 选择 "Deploy from a branch"
   - Branch 选择 "main" 和 "/docs" 文件夹
3. 如果是 fork 仓库，进入 Actions 页面并按提示启用工作流

### 2. GitHub Actions 配置

- **定时运行**: 每小时自动运行一次
- **手动触发**: 可通过 GitHub 界面手动运行
- **自动发布**: 抓取完成后更新 `main` 分支的 `docs/` 目录
- **Pages 重建**: `main/docs` 更新后由 GitHub Pages 自动重新构建
- **说明**: 不再维护额外的 `gh-pages` 分支
- **RSS**: `https://doane2002cn.github.io/smzdm-wenzhang-rss/daily_digest.xml`
- **完整社区日榜**: `https://doane2002cn.github.io/smzdm-wenzhang-rss/community_daily_rank.md`

### 3. Huginn 配置

#### 3.1 创建 Website Agent
- **URL**: `https://doane2002cn.github.io/smzdm-wenzhang-rss/`
- **Mode**: on_change
- **Update Every**: 30 分钟
- **Expected Update Period In Seconds**: 1800

#### 3.2 创建 HTML Extractor Agent
- **Source**: 选择上面的 Website Agent
- **Extraction Pattern**: 
  ```
  articles: article.article
  title: .article-title a@text
  url: .article-title a@href
  description: .article-desc@text
  pub_date: @data-date
  author: @data-author
  price: .article-price@text
  ```

#### 3.3 创建 RSS Output Agent
- **Source**: 选择上面的 HTML Extractor Agent
- **Title**: 什么值得买 - 最新文章
- **Description**: 什么值得买网站最新文章RSS订阅
- **Link**: `https://doane2002cn.github.io/smzdm-wenzhang-rss/`

## 本地开发

### 依赖安装

```bash
pip install -r requirements.txt
python -m playwright install chromium
```

### 运行爬虫

```bash
python crawler.py
```

生成的 HTML 文件会保存在 `docs/index.html`。

## 功能特性

- ✅ 网页内容智能抓取
- ✅ 静态 HTML 页面生成
- ✅ 定时任务调度（每小时）
- ✅ 自动部署到 GitHub Pages
- ✅ Huginn 集成支持
- ✅ 错误处理和日志记录
- ⏳ RSS 格式输出（通过 Huginn）

## 监控和维护

- **GitHub Actions**: 在 Actions 标签页查看运行历史
- **GitHub Pages**: 访问 `https://doane2002cn.github.io/smzdm-wenzhang-rss/` 查看生成的页面
- **Huginn**: 在 Huginn 界面监控 Agent 运行状态

## 故障排除

### 常见问题

1. **爬取失败**: 检查什么值得买网站是否有反爬机制更新
2. **GitHub Actions 失败**: 查看 Actions 日志，检查依赖安装或网络问题
3. **Huginn 解析失败**: 检查 HTML 结构是否有变化，调整 Extraction Pattern

### 调试方法

- 查看 `docs/articles.json` 文件了解原始数据结构
- 在 GitHub Actions 中添加调试输出
- 使用浏览器开发者工具检查 HTML 结构

## 扩展功能

- 添加更多网站支持
- 实现内容过滤和去重
- 添加邮件通知功能
- 支持多种输出格式

## 贡献指南

欢迎提交 Issue 和 Pull Request 来改进这个项目。

## 许可证

MIT License
