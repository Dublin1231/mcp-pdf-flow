# MCP PDF Flow (Simple PDF Extractor)

一个全能的 MCP (Model Context Protocol) 文档处理服务器，打通 LLM 与本地文档的交互。

它不仅能**精准提取** PDF 中的文本和图片并转换为**结构化 Markdown**，还支持 Markdown、Word (.docx) 和 PDF 之间的**无缝格式转换**。

## 功能特性

*   **📝 智能文本提取**：
    *   精准提取 PDF 页面文本。
    *   **智能 Markdown 识别**：自动识别标题、列表、段落结构，输出结构化 Markdown。
*   **🖼️ 图片提取**：
    *   支持提取页面内的所有图片。
    *   **自动保存**：提取的图片会自动保存到运行目录下的 `extracted_images/<文件名>/` 文件夹中。
    *   **预览支持**：返回 Base64 编码，支持在 Claude 等 MCP 客户端中直接预览。
*   **🔄 格式转换**：
    *   **Markdown 转 Word**：将生成的 Markdown 报告一键转换为格式完美的 Word (.docx) 文档。
    *   **Word 转 PDF**：支持将 Word 文档转换为 PDF 文件 (自动检测 Microsoft Word 或 WPS Office)。
*   **⚙️ 灵活提取**：支持提取全部页面、指定页码范围（如 `1`, `1-5`）或按关键词智能搜索。
*   **ℹ️ 元数据获取**：支持获取 PDF 标题、作者、页数及**目录结构 (TOC)**。

## 安装与使用

本项目使用 `uv` 进行包管理。

### 1. 克隆项目
```bash
git clone <your-repo-url>
cd pdf-mcp-main
```

### 2. 安装依赖
```bash
uv sync
```

## Claude Desktop 配置

要将此工具添加到 Claude Desktop，请编辑配置文件：

*   **Windows**: `%AppData%\Claude\claude_desktop_config.json`
*   **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`

添加以下内容（请修改路径为您的实际路径）：

```json
{
  "mcpServers": {
    "simple-pdf": {
      "command": "uv",
      "args": [
        "--directory",
        "D:/Work/Server/pdf-mcp-main", 
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
*注意：Windows 用户请确保路径分隔符使用 `/` 或 `\\`，并保留 `PYTHONIOENCODING` 环境变量配置以避免编码问题。*

## 工具列表

### 1. `extract_pdf_content`
提取 PDF 内容的核心工具。

**参数：**
*   `file_path` (必填): PDF 文件的绝对路径。
*   `page_range` (可选): 页码范围，默认为 "1"。
    *   支持 `"1"`, `"1-5"`, `"1,3,5"`, `"all"`。
*   `keyword` (可选): 关键词搜索。提取包含该关键词的所有页面。
*   `format` (可选): 输出格式，支持 `"text"` (默认) 或 `"markdown"`。

### 2. `get_pdf_metadata`
快速获取 PDF 的元数据和目录结构。

**参数：**
*   `file_path` (必填): PDF 文件的绝对路径。

### 3. `convert_markdown_to_docx`
将 Markdown 内容转换为 Word 文档。

**参数：**
*   `markdown_content` (必填): 要转换的 Markdown 文本内容。
*   `output_path` (必填): 输出 .docx 文件的绝对路径。

### 4. `convert_docx_to_pdf`
将 Word 文档转换为 PDF 文件。

**参数：**
*   `docx_path` (必填): 输入的 .docx 文件绝对路径。
*   `pdf_path` (可选): 输出 .pdf 文件的绝对路径。

## 输出目录结构

运行工具后，图片将按以下结构保存：

```
extracted_images/
  └── PDF文件名/
      ├── page_1_img_1.jpeg
      ├── page_1_img_2.png
      └── ...
```

## 开发

*   **核心代码**: `src/simple_pdf/server.py`
*   **转换逻辑**: `src/simple_pdf/convert.py`
