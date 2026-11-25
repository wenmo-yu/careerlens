# GitHub 仓库导入：用你自己的只读令牌

这条路不需要注册 OAuth 应用、不需要 client secret、不需要回调地址。用户自己在 GitHub 生成一个最小权限的 fine-grained token，粘贴到 CareerLens，系统用它读一次仓库信息，令牌不落库。

## 1. 读什么、不读什么

| 读取 | 不读取 |
| --- | --- |
| `GET /user`：确认令牌有效，记录账号登录名 | Cookie、邮箱、关注列表、私有 gist |
| `GET /user/repos`：仓库列表（仅 `affiliation=owner`，最多 10 个） | issues、pull requests、commits、actions、secrets |
| `GET /repos/{owner}/{name}`：简介、语言、Star、Fork、可见性、最近推送 | 令牌未授权的仓库 |
| `GET /repos/{owner}/{name}/readme`：README 原文，截断 6000 字符 | 其他分支、Release 二进制、LFS 大文件 |

导入后的证据 `source_type=github`，`claim_strength=self_reported_published`：令牌能证明「这个账号是你的」，但不能证明仓库内容真实或代表你的能力，所以仍按自报处理。

## 2. 用户操作（可直接抄进教程）

1. GitHub 右上头像 → **Settings** → 左侧最下 **Developer settings**。
2. **Personal access tokens** → **Fine-grained tokens** → **Generate new token**。
3. **Repository access** 选 **Only select repositories**，只勾选要导入的仓库。
4. **Permissions** 里把 **Contents** 设为 **Read-only**，**Metadata** 设为 **Read-only**（Metadata 是必选）。
5. **Expiration** 选 7 天或更短。
6. 生成后复制令牌（只显示一次），回到工作台的「GitHub 仓库」表单粘贴。
7. 导入完成后可在 GitHub 直接删除该令牌；已导入的证据不受影响。

## 3. 服务端约束

- 令牌只在一次请求的内存中使用；不写数据库、不写日志、不进证据 `source_metadata`，响应体里也不会出现。
- 令牌长度不足 20 或包含空白直接拒绝；`Authorization: Bearer <token>` 只发给 `api.github.com`。
- 一次最多 10 个仓库；单个 README 截断 6000 字符；请求超时 10 秒。
- 仓库名为空时取最近推送的 10 个自有仓库；仓库没有 README 也没有简介时跳过，不生成空证据。
- 401 / 403 / 404 转成中文提示；403 且 `x-ratelimit-remaining: 0` 提示限流。
- 去重键为 `github:{owner}/{name}@{pushed_at}`：同一仓库再次导入不会重复；仓库有新推送才生成新证据。

## 4. 仍然不做的事

- 不做 OAuth 授权码流程，不保存 refresh token。
- 不读 issues / PR / commit，也就不把「合并过的 PR」自动当作能力证明。
- 不访问用户未勾选的仓库，不自动翻页。
- 不因为拿到了令牌就提高证据强度：仍需要用户自己确认这些内容可以代表自己。

## 5. 故障排查

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| 422「令牌无效或已过期」 | 复制不完整、已删除、已过期 | 重新生成；确认没有多余空格 |
| 422「仓库不存在，或该令牌没有访问权限」 | 仓库未在 token 的 Repository access 里 | 编辑 token 的仓库范围 |
| 422「GitHub 接口限流了」 | 未认证请求或短时间内重复调用 | 稍后重试；确认请求带了令牌 |
| 502「连接 GitHub 失败」 | 本机/服务器网络无法访问 api.github.com | 检查代理与 DNS，重试 |

实现见 `backend/app/connectors/github.py`，路由见 `POST /api/v1/connectors/github/import`，测试见 `backend/tests/test_github_connector.py`（全部使用 `httpx.MockTransport`，不访问真实网络）。
