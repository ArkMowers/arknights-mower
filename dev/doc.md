---
sort: 3
---

# 文档的编写与构建

文档使用 Jekyll 框架，源码在 [doc-pages 分支](https://github.com/ArkMowers/arknights-mower/tree/doc-pages)。

预览与构建文档，需要安装 Ruby 3.3 和 Bundler。

## 安装依赖

```bash
bundle install
```

## 预览文档

```bash
bundle exec jekyll serve
```

## 构建文档

```bash
bundle exec jekyll build -b /docs
```

将生成的 `_site` 复制到 `<mower 文件夹>/dist/docs`，就可以在 mower 中看到文档了。
