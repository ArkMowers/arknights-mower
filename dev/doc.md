---
sort: 3
---

# 文档

文档使用 Jekyll 框架，源码在 [doc-pages 分支](https://github.com/ArkMowers/arknights-mower/tree/doc-pages)，使用 [Publishing from a branch](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site#publishing-from-a-branch) 的方式自动部署到 GitHub Pages。

在本地预览与构建文档，需要安装 Ruby 3.3 和 Bundler。

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

GitHub Actions 为 Windows 打包 mower 时，会构建文档，随 mower 分发。

## 嵌入 Jupyter Notebook

```bash
jupyter nbconvert notebook.ipynb --to html --template basic
```

将转换得到的 html 文件移至 `_includes/` 文件夹下。

在 Markdown 中引入：

```liquid
{% raw %}{% include notebook.html %}{% endraw %}
```

如果内容较长，可以放在 `<details>` 标签中：

```liquid
<details>
<summary>使用示例</summary>
{% raw %}{% include notebook.html %}{% endraw %}
</details>
```
