# Easy Note · 会整理的个人笔记助手

> 像聊天一样记笔记。你随口说一句，它替你提炼标题、整理要点、打好标签，按日期归档；想回顾时直接问，它检索你的全部笔记并**标注出处**回答。

不用学命令，不用想分类，**说人话就行**。

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-green.svg)
![Python](https://img.shields.io/badge/python-3.10%2B-yellow.svg)
![LLM](https://img.shields.io/badge/LLM-OpenAI%20compatible-orange.svg)

```
你：今天学了 Python 装饰器，关键是闭包和 @ 语法糖
Easy Note：✅ 已保存到 2026-07-09 · 「Python 装饰器要点」 #Python #语言特性

你：我之前关于装饰器记了什么？
Easy Note：你在 7-09 记过装饰器的核心是闭包与 @ 语法糖……（来源：notes/2026-07-09.md）
```

---

## 💾 下载即用（免装 Python）

不想折腾环境？直接下载打包好的桌面应用，解压双击即可运行。

| 平台 | 下载 | 使用方式 |
|---|---|---|
| **Windows** | [EasyNote.zip](http://xlink-touch-dev.oss-cn-hzfinance.aliyuncs.com/xlink/touch/download/easy-note.zip?OSSAccessKeyId=LTAI5tPfhok3T7DdQR6k5A5T&Expires=1787099280&Signature=8mUEkvEXbJ%2FE797L7cm9lksjLyk%3D) | 解压后双击 `EasyNote.exe` |
| macOS / Linux | _规划中_ | 可先[从源码运行](#方式二从源码运行)或自行[打包](#自己打包) |

**首次启动后**：点窗口右上角 **⚙ 设置**，填入你自己的 OpenAI 兼容 API 地址与密钥，即可开始记笔记。配置保存在用户数据目录（Windows `%APPDATA%\EasyNote`、macOS `~/Library/Application Support/EasyNote`），不会随程序卸载丢失。

> 📷 _建议在此放一张聊天界面截图（记笔记 + 查笔记 + 工具活动轨迹）。_

---

## 为什么用它

- 📝 **记得随意，存得整齐** —— 你只管把想法丢进来，标题、要点、标签由它自动整理，每天一个 Markdown 文件，永远不乱。
- 🔍 **问得自然，答得有据** —— 用大白话提问，它检索你的笔记并标注来源，不编造、可溯源。
- 🗂️ **你的笔记，你的文件** —— 全部以纯 Markdown 落盘在本地目录，可用任意编辑器打开、可同步、可备份，**不锁定、不上云**。
- 💬 **桌面聊天界面** —— 实时显示「思考中…」与检索 / 读取 / 保存的活动轨迹，回答以 Markdown 渲染。
- ⚙️ **开箱即配** —— 窗口内图形化修改笔记目录、模型与密钥，保存即生效并持久化。
- 🔌 **兼容任意 OpenAI 接口** —— 官方、第三方、本地自部署模型都能接。
- 🧠 **Agent 架构 + 三档上下文压缩** —— 思考→调用工具→观察→再思考的完整循环；长对话自动压缩（snip / micro / auto），不超 token 预算。

---

## 快速开始

### 方式一：下载打包应用（推荐，零环境配置）

1. 下载上方 [EasyNote.zip](#-下载即用免装-python) 并解压；
2. 双击 `EasyNote.exe` 启动；
3. 在 **⚙ 设置** 中填入 OpenAI 兼容 API 地址与密钥；
4. 直接在输入框记笔记即可。

### 方式二：从源码运行

```bash
git clone https://github.com/your-name/easy-note.git
cd easy-note
pip install -r requirements.txt
export OPENAI_API_KEY=sk-xxx        # Windows PowerShell: $env:OPENAI_API_KEY="sk-xxx"
python -m src.ui.app                # 或 python run_gui.py
```

环境要求：**Python 3.10+**，以及一个 OpenAI 兼容的 LLM API。

### 配置说明

**源码运行**时，读取仓库根目录的 `config.yaml`：

```yaml
llm:
  api_url: "https://your-endpoint/v1/chat/completions"  # OpenAI 兼容接口
  api_key: "${OPENAI_API_KEY}"                          # 支持 ${ENV_VAR} 占位
  model: "your-model-name"
  temperature: 0.7
  max_tokens: 4096

notes_dir: "./notes"        # 笔记保存目录
search_dirs:                # 额外的本地检索目录（查询时与 notes_dir 合并）
  - "./example_data"
```

**打包应用**无需 `config.yaml`：首次运行用内置默认值启动，在 **⚙ 设置** 里填好凭据后保存，配置落到用户数据目录。密钥推荐用环境变量，避免明文落盘。

两种方式都支持在程序内点 **⚙ 设置** 图形化修改，保存即时生效。

---

## 交互

- **记笔记**：直接输入想记的内容（如「今天学了 Python 装饰器，关键是闭包和 @ 语法糖」），AI 整理后落盘。
- **查笔记**：用自然语言提问回顾（如「我关于装饰器记了什么？」），AI 检索笔记目录并标注来源作答。
- 输入框：`Enter` 发送，`Shift+Enter` 换行。
- 处理中禁用输入，串行执行以保护单一会话上下文。

---

## 笔记长什么样

每天一个 `notes/YYYY-MM-DD.md`，纯 Markdown，可被任何编辑器或笔记软件打开：

```markdown
# 2026-07-09

## 15:45 Python 装饰器要点
- 本质是返回函数的高阶函数，依赖闭包捕获外层变量
- `@` 只是 `f = deco(f)` 的语法糖

Tags: #Python #语言特性
---
```

---

## 它是怎么工作的（Agent 架构）

Easy Note 是一个 **Agent**：它不是一次性问答，而是「思考 → 调用工具 → 获取结果 → 再思考」的循环，直到得出结论。

- **两种模式（由系统提示词按用户意图分流，无硬编码路由）**：
  - **记录模式**：用户文本 → AI 结构化整理（提炼标题、整理要点、生成标签）→ 调 `write_note` 追加写入按日期命名的日记。
  - **查询模式**：用户提问 → 复用 `search_files` / `read_file` 在笔记目录检索并标注来源作答。
- **工具调用协议**：XML 标签 `<tool_call>` + JSON，Agent 自主解析，不依赖原生 function calling。
- **上下文压缩**：snip（规则截断超大工具结果）/ micro（LLM 摘要最旧几条）/ auto（LLM 全局摘要替换历史）三档分层，按预算比例触发。

```
src/
├── config.py          # 配置 dataclass + YAML 加载/保存（${ENV_VAR} 占位、用户数据目录）
├── prompts.py         # 系统提示词（记录 / 查询双模式自动分流）
├── plan.py            # 任务计划状态
│
├── llm/               # 与 LLM 通信的 I/O 边界
│   ├── client.py              # HTTP 客户端（OpenAI 兼容格式）
│   └── tool_call_parser.py    # 解析 <tool_call> XML 标签
│
├── agent/loop.py      # 思考 -> 调用工具 -> 观察 -> 再思考 主循环
│
├── conversation/      # 对话历史 + 上下文预算
│   ├── context.py             # messages 读写
│   ├── tokens.py              # token 估算（中英混合）
│   └── compaction.py          # snip / micro / auto 三档压缩
│
├── tools/             # write_note / search_files / read_file / list_directory / update_plan
│
└── ui/                # PySide6 桌面聊天客户端（程序入口）
    ├── app.py                 # 入口：组装 config / registry / agent
    ├── chat_window.py         # 消息流 + 气泡 + 活动轨迹 + 输入框
    ├── settings_dialog.py     # 图形化设置并写回配置
    ├── worker.py              # AgentWorker(QThread)：后台跑 agent.run
    └── reporter.py            # GuiReporter：进度事件 -> Qt 信号
```

依赖方向是无环 DAG：`config` ← 所有；`plan` 无依赖；`llm` → config；`conversation` → llm/tokens；`tools` → base/plan；`agent` → 其余；`ui` → 全部。

---

## 自己打包

需要分发或自用免安装版时，可用内置脚本打包（依赖 PyInstaller）：

```bash
pip install pyinstaller

python script/build_exe.py    # Windows：产出 dist/EasyNote.exe（单文件）
python script/build_app.py    # macOS：产出 dist/EasyNote.app（须在 macOS 上运行）
```

打包产物**不含 `config.yaml`**：首次运行用内置默认值启动，用户在设置对话框保存后才在用户数据目录落盘，避免凭据随发行包泄露。图标取自 `assets/`。

---

## 扩展新工具

1. 在 `src/tools/` 下新建文件，继承 `BaseTool`；
2. 在 `src/ui/app.py` 的 `build_agent` 中 `registry.register(YourTool(...))`；
3. 工具描述会自动注入 system prompt（见 `src/prompts.py`）。

---

## 路线图

- [x] 一键打包的 Windows 免安装版
- [ ] macOS / Linux 打包发行版
- [ ] 笔记全文搜索高亮与标签视图
- [ ] 多笔记目录 / 工作区切换
- [ ] 导出与同步

欢迎在 Issue 区提需求与反馈。

---

## 贡献

欢迎提交 Issue 与 Pull Request。提交前请确保**不包含任何私密配置或密钥**（`config.yaml` 已在 `.gitignore` 中）。

## 许可证

[MIT](LICENSE)
