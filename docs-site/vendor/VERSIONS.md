# 站点静态资源版本锁

本站把所用脚本与样式随站点产物发布，读者不依赖临时 CDN。所有资源从 jsDelivr 的**固定版本**下载，不写 `@latest`。升级时先改这里，再替换 `vendor/` 下对应文件，并在站点本地验收中回归。

| 文件 | 来源 | 版本 |
| --- | --- | --- |
| `docsify.min.js` | `docsify@4.13.1/lib/docsify.min.js` | 4.13.1 |
| `docsify-search.min.js` | `docsify@4.13.1/lib/plugins/search.min.js` | 4.13.1（全文搜索插件，配置在 index.html，需显式加载） |
| `docsify-theme.css` | `docsify@4.13.1/lib/themes/vue.css` | 4.13.1（已去掉 Google Fonts `@import`，改用系统字体，完全本地化） |
| `vue.min.js` | `vue@2.7.16/dist/vue.min.js` | 2.7.16（Docsify 4 依赖） |
| `docsify-copy-code.min.js` | `docsify-copy-code@2.1.1/dist/docsify-copy-code.min.js` | 2.1.1 |
| `docsify-pagination.min.js` | `docsify-pagination@2.10.1/dist/docsify-pagination.min.js` | 2.10.1 |
| `docsify-tabs.min.js` | `docsify-tabs@1.6.0/dist/docsify-tabs.min.js` | 1.6.0 |
| `docsify-mermaid.min.js` | `docsify-mermaid@2.0.0/dist/docsify-mermaid.min.js` | 2.0.0 |
| `mermaid.min.js` | `mermaid@10.9.1/dist/mermaid.min.js` | 10.9.1 |
| `prism-core.min.js` | `prismjs@1.29.0/components/prism-core.min.js` | 1.29.0 |
| `prism-clike.min.js` | `prismjs@1.29.0/components/prism-clike.min.js` | 1.29.0 |
| `prism-python.min.js` | `prismjs@1.29.0/components/prism-python.min.js` | 1.29.0 |
| `prism-bash.min.js` | `prismjs@1.29.0/components/prism-bash.min.js` | 1.29.0 |
| `prism-json.min.js` | `prismjs@1.29.0/components/prism-json.min.js` | 1.29.0 |
| `prism-js.min.js` | `prismjs@1.29.0/components/prism-javascript.min.js` | 1.29.0 |
| `prism.min.css` | `prismjs@1.29.0/themes/prism.min.css` | 1.29.0 |

下载基址：`https://cdn.jsdelivr.net/npm/<包>@<版本>/<路径>`。
