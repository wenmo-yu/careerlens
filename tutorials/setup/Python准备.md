# Python 选做准备

**这是选做篇。** 用 Docker Compose 跑通 Demo **不需要**在本机安装 Python——镜像里已经带了。只有在你想做以下事情时才需要它：

- 跑 `examples/tutorials/` 里的脚本练习；
- 不通过 Compose，手动启动本地服务；
- 修改后端代码或做开发。

只想理解原理或在本机跑通工作台？回到[第 01 篇](../01-第一次跑起来.md)或[开始页](../从这里开始.md)，不必装 Python。

---

## 步骤 1：确认是否已安装

Windows 打开 PowerShell，macOS / Linux 打开终端：

```powershell
# Windows：py 是启动器；也可用 python --version
py --version
```

```bash
# macOS / Linux
python3 --version
```

看到类似 `Python 3.11.9` 就说明已装好。项目要求 **Python 3.11+**。报「找不到命令」再往下装。

## 步骤 2：按系统安装

| 系统 | 做法 |
| --- | --- |
| Windows | 按 [Python 官方 Windows 指南](https://docs.python.org/3/using/windows.html)下载安装器，安装时勾选 **Add Python to PATH**，完成后重开 PowerShell 再跑 `py --version`。 |
| macOS | 按 [Python 官方 macOS 指南](https://docs.python.org/3/using/mac.html)选择安装包；也可用 Homebrew。完成后重开终端跑 `python3 --version`。 |
| Linux | 多数发行版自带 Python 3；版本过低时用系统包管理器安装 python3，再验证 `python3 --version`。 |

安装器或包管理器的具体按钮会随版本变化，以官方文档当前页面为准；本教程不绑定某个具体版本号。

## 步骤 3：跑第一行代码

```powershell
# Windows
py -c "print('hello from Python')"
```

```bash
# macOS / Linux
python3 -c "print('hello from Python')"
```

输出 `hello from Python` 即完成。

## 步骤 4：给项目建虚拟环境（可选）

准备改后端代码时，在仓库的 `backend/` 目录下建一个隔离环境，避免污染系统 Python：

```powershell
# Windows，在 backend/ 目录下
py -m venv .venv
.\.venv\Scripts\Activate.ps1
```

```bash
# macOS / Linux，在 backend/ 目录下
python3 -m venv .venv
source .venv/bin/activate
```

激活后终端前面通常出现 `(.venv)`。依赖安装与运行方式见[完整启动与配置指南](../../docs/api-and-configuration.md)。

> **说明**：
> 默认 Demo 用确定性 Provider 和轻量检索，不需要真实模型密钥。接真实模型属于进阶内容，见阶段 5。

---

## 常见问题

- **`py` 和 `python3` 该用哪个**：Windows 用 `py`（启动器），macOS / Linux 用 `python3`。不要把系统自带的 `python` 当成项目 Python。
- **装了但还是找不到命令**：关掉终端重新打开（PATH 要刷新）；仍不行就检查安装时是否勾选了加入 PATH。
- **版本低于 3.11**：项目要求 3.11+，请升级后重试。
- **虚拟环境激活失败（Windows PowerShell）**：可在 `backend/` 目录直接运行 `.\.venv\Scripts\python.exe --version`。用同一个解释器安装依赖或运行脚本即可。

## 下一步

回到[教程总览](../README.md)选择路线，或直接进入[第 01 篇](../01-第一次跑起来.md)跑通工作台。
