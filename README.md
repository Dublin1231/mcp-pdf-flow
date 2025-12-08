# MCP PDF Flow (Simple PDF Extractor)

**中文** | [English](README_EN.md)

一个全能的 MCP (Model Context Protocol) 文档处理服务器，打通 LLM 与本地文档的交互。

它不仅能**精准提取** PDF 中的文本和图片并转换为**结构化 Markdown**，还支持 Markdown、Word (.docx) 和 PDF 之间的**无缝格式转换**。

## ✨ 功能特性

*   **📝 智能文本提取**：
    *   精准提取 PDF 页面文本。
    *   **智能 Markdown 识别**：自动识别标题、列表、段落结构，合并跨行文本，输出干净的 Markdown。
*   **🖼️ 图片提取**：
    *   支持提取页面内的所有图片。
    *   **自动保存与引用**：默认将图片保存到本地 `extracted_images/` 目录，并在 Markdown 中插入图片路径引用，避免大量 Base64 数据占用上下文。
    *   **Base64 预览**：可选直接返回图片 Base64 编码，支持在 MCP 客户端中即时预览（适合少量小图）。
*   **🔄 格式转换**：
    *   **Markdown 转 Word**：将生成的 Markdown 报告一键转换为格式完美的 Word (.docx) 文档。
    *   **Word 转 PDF**：支持将 Word 文档转换为 PDF 文件。
        *   *自动适配*：优先使用 Microsoft Word，若未安装则自动回退到 WPS Office。
*   **⚙️ 灵活提取**：支持提取全部页面、指定页码范围（如 `1`, `1-5`）或按关键词智能搜索。
*   **ℹ️ 元数据获取**：支持获取 PDF 标题、作者、页数及**目录结构 (TOC)**。

## 🛠️ 环境要求

*   **操作系统**：Windows (推荐，用于支持 Word/WPS 转换) / macOS / Linux
*   **Python**：>= 3.10
*   **Office 软件** (仅 Word 转 PDF 功能需要)：
    *   Microsoft Word (最佳兼容性)
    *   或 WPS Office (支持 Windows)

## 📦 安装与使用

本项目使用 `uv` 进行包管理。

### 1. 克隆项目
```bash
git clone https://github.com/Dublin1231/mcp-pdf-flow.git
cd mcp-pdf-flow
```

### 2. 安装依赖
```bash
uv sync
```

## 🔌 Claude Desktop 配置

要将此工具添加到 Claude Desktop，请编辑配置文件：

*   **Windows**: `%AppData%\Claude\claude_desktop_config.json`
*   **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`

添加以下内容（请**务必**将路径修改为您本地的实际路径）：

```json
{
  "mcpServers": {
    "simple-pdf": {
      "command": "uv",
      "args": [
        "--directory",
        "D:/path/to/your/mcp-pdf-flow", 
        "run",
        "simple-pdf"
      ],
      "env": {
        "PYTHONIOENCODING": "utf-8"
      }
    }
  }
}
```
*注意：Windows 用户路径分隔符请使用 `/` 或 `\\`。*

## 💬 如何在对话中使用

**你不需要手动填写 JSON 参数！** 只需要在对话中告诉 Claude 你想做什么，它会自动调用工具。

### 场景示例

#### 1. 读取 PDF
*   **指定绝对路径**：
    > **用户**: "帮我读取 `D:\Documents\report.pdf` 的第 1 到 5 页。"
*   **读取项目目录下文件**：
    > **用户**: "读取当前目录下的 `test.pdf`。"
    > *(注：Claude 会自动查找运行目录下的文件)*

#### 2. 转换 Markdown 为 Word
> **用户**: "把刚刚提取的内容保存为 Word 文档，放在 `D:\Documents\output.docx`。"
>
> **Claude**: (自动调用 `convert_markdown_to_docx` 工具)

#### 3. Word 转 PDF
> **用户**: "把 `D:\Documents\draft.docx` 转换成 PDF。"
>
> **Claude**: (自动调用 `convert_docx_to_pdf` 工具)

---

## 📖 工具列表

> **💡 小贴士：如何获取“绝对路径”？**
> *   **Windows**: 按住 `Shift` 键，右键点击文件，选择“复制文件地址 (Copy as path)”。粘贴时去掉首尾的引号。
>     *   示例: `C:\Users\Name\Documents\report.pdf`
> *   **macOS**: 选中文件，按下 `Option + Command + C` 复制路径。
>     *   示例: `/Users/name/Documents/report.pdf`

### 1. `extract_pdf_content`
提取 PDF 内容的核心工具。

**参数：**
*   `file_path` (必填): PDF 文件的绝对路径。
    *   *Windows 示例*: `D:\Documents\paper.pdf`
    *   *macOS 示例*: `/Users/username/Documents/paper.pdf`
*   `page_range` (可选): 页码范围，默认为 "all"。
    *   示例: `"1"`, `"1-5"`, `"1,3,5"`, `"all"`。
*   `keyword` (可选): 关键词搜索。若提供，将忽略页码范围，仅提取包含关键词的页面。
*   `format` (可选): 输出格式。
    *   `"text"` (默认): 纯文本提取。
    *   `"markdown"`: **推荐**。智能识别标题和段落，适合 LLM 阅读。
*   `include_text` (可选): 是否提取文本，默认为 `true`。
*   `include_images` (可选): 是否提取图片，默认为 `false`。
*   `use_local_images_only` (可选): 图片处理模式，默认为 `true`。
    *   `true` (默认): 图片保存到本地 `extracted_images` 目录，Markdown 中使用路径引用。**推荐用于大文件或包含大量图片的 PDF，防止 Token 溢出**。
    *   `false`: 返回图片的 Base64 数据流，可直接预览，但消耗大量 Token。

### 2. `get_pdf_metadata`
快速获取 PDF 的元数据和目录结构。

**参数：**
*   `file_path` (必填): PDF 文件的绝对路径。

### 3. `convert_markdown_to_docx`
将 Markdown 内容转换为 Word 文档。

**参数：**
*   `markdown_content` (必填): 要转换的 Markdown 文本内容。
*   `output_path` (必填): 输出 .docx 文件的绝对路径。
    *   *注意*: 这里需要填写**你希望保存的新文件路径**。
    *   *示例*: `D:\Documents\report_output.docx`

### 4. `convert_docx_to_pdf`
将 Word 文档转换为 PDF 文件。

**参数：**
*   `docx_path` (必填): 输入的 .docx 文件绝对路径。
*   `pdf_path` (可选): 输出 .pdf 文件的绝对路径。
    *   如果不提供，将在原 docx 文件同目录下生成同名 pdf 文件。


## 📂 输出目录结构

运行工具后，图片将按以下结构保存：

```
extracted_images/
  └── PDF文件名/
      ├── page_1_img_1.jpeg
      ├── page_1_img_2.png
      └── ...
```

## 💻 开发

*   **核心代码**: `src/simple_pdf/server.py`
*   **转换逻辑**: `src/simple_pdf/convert.py`
