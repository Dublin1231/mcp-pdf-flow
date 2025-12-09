# PDF MCP Flow  - AI 驱动的 PDF 处理引擎

**中文** | [English](README_EN.md)

> 🚀 **专为 LLM 和 RAG 设计的 MCP 文档处理服务器** | PDF 转 Markdown | 格式转换 | 智能提取

**MCP PDF Flow** 是一个强大的 **Model Context Protocol (MCP)** 服务器，旨在弥合 LLM（如 Claude）与本地文档之间的鸿沟。

它不仅是**PDF 转 Markdown** 的最佳工具，还提供了一套完整的文档处理工作流，支持 **RAG（检索增强生成）** 场景下的数据清洗和格式化。

## ✨ 核心优势

*   **🤖 LLM 友好**：输出清洗后的结构化 Markdown，完美适配 AI 上下文阅读。
*   **🔍 智能 RAG 支持**：支持语义模糊搜索和元数据提取，快速定位文档关键信息。
*   **🔄 全能格式转换**：PDF ⇋ Word ⇋ Markdown 无缝互转。

## ✨ 功能特性

*   **📝 智能文本提取**：
    *   精准提取 PDF 页面文本。
    *   **智能 Markdown 识别**：自动识别标题、列表、段落结构，合并跨行文本，输出干净的 Markdown。
*   **🖼️ 图片提取**：
    *   支持提取页面内的所有图片。
    *   **自动保存与引用**：默认将图片保存到本地 `extracted_images/` 目录，并在 Markdown 中插入图片路径引用，避免大量 Base64 数据占用上下文。
    *   **Base64 预览**：可选直接返回图片 Base64 编码，支持在 MCP 客户端中即时预览（适合少量小图）。
*   **📂 批量处理**：支持对指定目录下的 PDF 文件进行批量提取，自动生成 Markdown 和图片，并保持目录结构整洁。
*   **📊 增强表格提取**：
    *   **高精度识别**：自动处理跨行表头、错位列和复杂排版。
    *   **智能清洗**：自动移除空行、空表头，过滤伪表格（如文本列表）。
    *   **批量导出**：支持一键提取目录下所有 PDF 中的表格为 Markdown 文件。
*   **🔍 模糊搜索**：
    *   **智能查找**：支持通过文件名关键词（模糊匹配、拼写错误兼容）快速定位 PDF 文件路径。
    *   **递归搜索**：默认支持多级目录递归查找。
*   **🔄 格式转换**：
    *   **Markdown 转 Word**：将生成的 Markdown 报告一键转换为格式完美的 Word (.docx) 文档。
    *   **Word 转 PDF**：支持将 Word 文档转换为 PDF 文件。
        *   *自动适配*：优先使用 Microsoft Word，若未安装则自动回退到 WPS Office。
*   **⚙️ 灵活提取**：支持提取全部页面、指定页码范围（如 `1`, `1-5`）或按关键词智能搜索。
*   **📂 批量处理**：支持对指定目录下的 PDF 文件进行批量提取，自动生成 Markdown 和图片，并保持目录结构整洁。
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

### 3. 运行服务

本服务是一个 MCP Server，设计为由 Claude Desktop 等客户端**自动启动**。
您**不需要**手动在终端运行启动命令。请继续阅读下方的 [Claude Desktop 配置](#-claude-desktop-配置) 章节完成设置。一旦配置完成，Claude Desktop 启动时会自动在后台运行此服务。

## 🔌 Claude Desktop 配置

要将此工具添加到 Claude Desktop，请编辑配置文件：

*   **Windows**: `%AppData%\Claude\claude_desktop_config.json`
*   **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`

添加以下内容（请**务必**将路径修改为您本地的实际路径）：

```jsonc
{
  "mcpServers": {
    "simple-pdf": {
      "command": "uv",
      "args": [
        "--directory",
        "D:/path/to/your/mcp-pdf-flow", // ⚠️ 请务必修改为您本地的实际项目路径
        "run",
        "simple-pdf"
      ],
      "env": {
        "PYTHONIOENCODING": "utf-8",
        // (可选) 指定额外的 PDF 搜索路径。Windows 使用分号 (;)，Mac/Linux 使用冒号 (:) 分隔
        "PDF_SEARCH_PATHS": //"D:\\example;E:\\example"
      }
    }
  }
}
```

*注意：*
*   *Windows 用户路径分隔符请使用 `/` 或 `\\`。*
*   *`PDF_SEARCH_PATHS` 为可选配置，用于指定额外的 PDF 搜索路径，多个路径用 `;` (Windows) 或 `:` (Mac/Linux) 分隔。*

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

#### 4. 批量处理 PDF
> **用户**: "批量处理 `D:\Docs` 目录下的所有 PDF，导出为 Markdown。"
>
> **Claude**: (自动调用 `batch_extract_pdf_content` 工具)

#### 5. 批量处理并指定输出目录
> **用户**: "批量处理 `D:\Docs` 下的 PDF，将 Markdown 存到 `D:\Output\MD`，图片存到 `D:\Output\Images`。"
>
> **Claude**: (调用 `batch_extract_pdf_content`，参数 `custom_output_dir="D:\\Output\\MD"`, `custom_image_output_dir="D:\\Output\\Images"`)

#### 6. 模糊查找 PDF
> **用户**: "帮我找一下 `D:\Study` 下面关于 `springboot` 的 PDF 文件。"
>
> **Claude**: (自动调用 `search_pdf_files` 工具)

#### 7. 获取 PDF 目录结构
> **用户**: "提取 `D:\Books\Guide.pdf` 的目录大纲。"
>
> **Claude**: (自动调用 `get_pdf_metadata` 工具)


#### 8. 批量提取表格
> **用户**: "把 `D:\Books` 下所有 PDF 的表格提取出来，存到 `D:\Tables`。"
>
> **Claude**: (自动调用 `batch_extract_tables` 工具)


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
    *   `"json"`: 返回结构化 JSON 数据，包含每一页的文本和图片信息，适合程序化处理。
*   `include_text` (可选): 是否提取文本，默认为 `true`。
*   `include_images` (可选): 是否提取图片，默认为 `false`。
*   `use_local_images_only` (可选): 图片处理模式，默认为 `true`。
    *   `true` (默认): 图片保存到本地 `extracted_images` 目录，Markdown 中使用路径引用。**推荐用于大文件或包含大量图片的 PDF，防止 Token 溢出**。
    *   `false`: 返回图片的 Base64 数据流，可直接预览，但消耗大量 Token。
*   `skip_table_detection` (可选): **极速模式**开关，默认为 `false`。
    *   `false` (默认): 智能检测并提取表格，转换为 Markdown 表格格式。
    *   `true`: **跳过表格检测**。适用于仅需要纯文本内容的场景，速度可提升 3-4 倍（约 400+ 页/秒）。

### 2. `batch_extract_pdf_content`
批量处理指定目录下的所有 PDF 文件。

**参数：**
*   `directory` (必填): 要搜索的根目录绝对路径。
*   `pattern` (可选): 文件匹配模式，默认为 `**/*.pdf` (支持递归)。
*   `custom_output_dir` (可选): 指定 Markdown/JSON 文件的输出目录。如果不填，默认保存在 PDF 文件同级目录。
*   `custom_image_output_dir` (可选): 指定图片的输出根目录。如果不填，默认保存在 PDF 文件同级目录下的 `extracted_images` 文件夹中。
*   `format` (可选): 输出格式，支持 `markdown` (默认), `json`, `text`。
*   `include_text` (可选): 是否提取文本，默认为 `true`。
*   `include_images` (可选): 是否提取图片，默认为 `false`。
*   `use_local_images_only` (可选): 图片处理模式，默认为 `true`。
*   `skip_table_detection` (可选): **极速模式**开关，默认为 `false`。
    *   `false` (默认): 智能检测并提取表格，转换为 Markdown 表格格式。
    *   `true`: **跳过表格检测**。适用于仅需要纯文本内容的场景，速度可提升 3-4 倍（约 400+ 页/秒）。


### 3. `get_pdf_metadata`
快速获取 PDF 的元数据和目录结构。

**参数：**
*   `file_path` (必填): PDF 文件的绝对路径。

### 4. `convert_markdown_to_docx`
将 Markdown 内容转换为 Word 文档。

**参数：**
*   `markdown_content` (必填): 要转换的 Markdown 文本内容。
*   `output_path` (必填): 输出 .docx 文件的绝对路径。
    *   *注意*: 这里需要填写**你希望保存的新文件路径**。
    *   *示例*: `D:\Documents\report_output.docx`

### 5. `convert_docx_to_pdf`
将 Word 文档转换为 PDF 文件。

**参数：**
*   `docx_path` (必填): 输入的 .docx 文件绝对路径。
*   `pdf_path` (可选): 输出 .pdf 文件的绝对路径。
    *   如果不提供，将在原 docx 文件同目录下生成同名 pdf 文件。

### 6. `search_pdf_files`
通过文件名模糊搜索 PDF 文件路径。

**参数：**
*   `query` (必填): 文件名关键词。支持模糊匹配（如拼写错误）、中文匹配。
*   `directory` (可选): 搜索根目录。默认为当前工作目录。
*   `limit` (可选): 返回的最大结果数量，默认 10。
*   `threshold` (可选): 匹配阈值 (0.0-1.0)，默认 0.45。


### 7. `batch_extract_tables`
批量提取目录中所有 PDF 的表格。

**参数：**
*   `directory` (必填): 要搜索的根目录绝对路径。
*   `output_dir` (必填): 表格 Markdown 文件的输出目录。
*   `pattern` (可选): 文件匹配模式，默认为 `**/*.pdf`。

**✨ 表格提取增强特性：**
*   **智能表头合并**：自动处理跨行表头和被拆分的列名。
*   **错位列修复**：智能识别并合并因格式问题错位的标题和内容列。
*   **空行/空表头优化**：
    *   自动移除无效的空行。
    *   智能识别 KV 结构表格，仅在必要时保留表头，避免对中文 KV 表格生成错误的空表头。
*   **伪表格过滤**：
    *   自动识别并过滤文本列表（如目录、步骤说明）。
    *   自动过滤被误判为表格的代码块或长文本段落。
*   **排版优化**：智能处理单元格内的换行符，保持列表结构清晰，同时让普通长文本自然回流。

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
