# MCP PDF Flow - AI-Powered PDF Extraction & Conversion for LLMs

[中文](README.md) | **English**

> 🚀 **The Ultimate MCP Server for RAG & LLM Document Processing** | PDF to Markdown | Format Converter | Intelligent Extraction

**MCP PDF Flow** is a powerful **Model Context Protocol (MCP)** server designed to bridge the gap between Large Language Models (LLMs, like Claude) and your local documents.

It serves as a comprehensive **ETL (Extract, Transform, Load)** tool for your personal knowledge base, optimizing PDFs into **clean, structured Markdown** perfectly suited for RAG pipelines and AI context windows.

## ✨ Key Highlights

*   **🤖 LLM-Ready Output**: Generates clean, structured Markdown optimized for AI reading and RAG indexing.
*   **🔍 RAG & Search**: Built-in fuzzy search and metadata extraction to quickly locate relevant document sections.
*   **🔄 Universal Converter**: Seamless conversion between PDF, Word (.docx), and Markdown.

## ✨ Features

*   **📝 Intelligent Text Extraction**:
    *   Precisely extracts text from PDF pages.
    *   **Smart Markdown Recognition**: Automatically identifies headers, lists, and paragraph structures, merges cross-line text, and outputs clean Markdown.
*   **🖼️ Image Extraction**:
    *   Extracts all images within pages.
    *   **Auto-save & Reference**: Defaults to saving images locally to `extracted_images/` and referencing them in Markdown paths, avoiding context overflow with large Base64 data.
    *   **Base64 Preview**: Optionally returns Base64 encoding for direct preview in MCP clients (suitable for small images).
*   **📂 Batch Processing**: Supports batch extraction of PDF files in a specified directory, automatically generates Markdown and images, and maintains a clean directory structure.
*   **📊 Enhanced Table Extraction**:
    *   **High-Precision Recognition**: Automatically handles multi-line headers, misaligned columns, and complex layouts.
    *   **Smart Cleaning**: Automatically removes empty rows/headers and filters pseudo-tables (e.g., text lists).
    *   **Batch Export**: Supports one-click extraction of tables from all PDFs in a directory to Markdown files.
*   **🔍 Fuzzy Search**:
    *   **Smart Lookup**: Support locating PDF file paths via filename keywords (fuzzy matching, spelling error compatibility).
    *   **Recursive Search**: Supports multi-level directory recursive search by default.
*   **🔄 Format Conversion**:
    *   **Markdown to Word**: Converts generated Markdown reports into perfectly formatted Word (.docx) documents with one click.
    *   **Word to PDF**: Supports converting Word documents to PDF files.
        *   *Auto-adapt*: Prioritizes Microsoft Word; falls back to WPS Office if not installed.
*   **⚙️ Flexible Extraction**: Supports extracting all pages, specific page ranges (e.g., `1`, `1-5`), or smart search by keywords.
*   **ℹ️ Metadata Retrieval**: Supports retrieving PDF title, author, page count, and **Table of Contents (TOC)**.

## 🛠️ Requirements

*   **OS**: Windows (Recommended for Word/WPS conversion support) / macOS / Linux
*   **Python**: >= 3.10


## 📦 Installation & Usage

This project uses `uv` for package management.

### 1. Clone the Project
```bash
git clone https://github.com/Dublin1231/mcp-pdf-flow.git
cd mcp-pdf-flow
```

### 2. Install Dependencies
```bash
uv sync
```

### 3. Run the Server

This is an MCP Server designed to be **automatically started** by clients like Claude Desktop.
You **do not need** to manually run a startup command in the terminal. Please proceed to the [Claude Desktop Configuration](#-claude-desktop-configuration) section below. Once configured, Claude Desktop will automatically run this service in the background.

## 🔌 Claude Desktop Configuration

To add this tool to Claude Desktop, edit the configuration file:

*   **Windows**: `%AppData%\Claude\claude_desktop_config.json`
*   **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`

Add the following content (Please **ensure** to change the path to your actual local path):

```jsonc
{
  "mcpServers": {
    "simple-pdf": {
      "command": "uv",
      "args": [
        "--directory",
        "D:/path/to/your/mcp-pdf-flow", // ⚠️ Make sure to update this to your actual local path
        "run",
        "simple-pdf"
      ],
      "env": {
        "PYTHONIOENCODING": "utf-8",
        // (Optional) Specify extra PDF search paths. Use semicolon (;) for Windows, colon (:) for Mac/Linux
        "PDF_SEARCH_PATHS": //"D:\\example;E:\\example"
      }
    }
  }
}
```

*Note:*
*   *Windows users please use `/` or `\\` as path separators.*
*   *`PDF_SEARCH_PATHS` is optional configuration for specifying extra PDF search paths. Separate multiple paths with `;` (Windows) or `:` (Mac/Linux).*

## 💬 How to Use in Chat

**You don't need to manually fill in JSON arguments!** Just tell Claude what you want to do in the chat, and it will automatically call the tools.

### Scenario Examples

#### 1. Read PDF
*   **Specify Absolute Path**:
    > **User**: "Read pages 1 to 5 of `D:\Documents\report.pdf` for me."
*   **Read file in project directory**:
    > **User**: "Read `test.pdf` in the current directory."
    > *(Note: Claude will automatically look for files in the running directory)*

#### 2. Convert Markdown to Word
> **User**: "Save the extracted content as a Word document at `D:\Documents\output.docx`."
>
> **Claude**: (Automatically calls `convert_markdown_to_docx` tool)

#### 3. Word to PDF
> **User**: "Convert `D:\Documents\draft.docx` to PDF."
>
> **Claude**: (Automatically calls `convert_docx_to_pdf` tool)

#### 4. Batch Process PDFs
> **User**: "Batch process all PDFs in the `D:\Docs` directory and export to Markdown."
>
> **Claude**: (Automatically calls the `batch_extract_pdf_content` tool)

#### 5. Batch Process with Custom Output Directories
> **User**: "Batch process PDFs in `D:\Docs`, save Markdown to `D:\Output\MD` and images to `D:\Output\Images`."
>
> **Claude**: (Calls `batch_extract_pdf_content` with `custom_output_dir="D:\\Output\\MD"`, `custom_image_output_dir="D:\\Output\\Images"`)

#### 6. Fuzzy Find PDF
> **User**: "Help me find PDF files about 'springboot' under `D:\Study`."
>
> **Claude**: (Automatically calls `search_pdf_files` tool)

#### 7. Get PDF Table of Contents
> **User**: "Extract the outline of `D:\Books\Guide.pdf`."
>
> **Claude**: (Automatically calls `get_pdf_metadata` tool)

#### 8. Batch Extract Tables
> **User**: "Extract tables from all PDFs in `D:\Books` and save them to `D:\Tables`."
>
> **Claude**: (Automatically calls `batch_extract_tables` tool)


---

## 📖 Tool List

> **💡 Tip: How to get "Absolute Path"?**
> *   **Windows**: Hold `Shift` and right-click the file, select "Copy as path". Remove the surrounding quotes when pasting.
>     *   Example: `C:\Users\Name\Documents\report.pdf`
> *   **macOS**: Select the file, press `Option + Command + C` to copy the path.
>     *   Example: `/Users/name/Documents/report.pdf`


### 1. `extract_pdf_content`
Core tool for extracting PDF content.

**Parameters:**
*   `file_path` (Required): Absolute path of the PDF file.
    *   *Windows Example*: `D:\Documents\paper.pdf`
    *   *macOS Example*: `/Users/username/Documents/paper.pdf`
*   `page_range` (Optional): Page range, default is "all".
    *   Examples: `"1"`, `"1-5"`, `"1,3,5"`, `"all"`.
*   `keyword` (Optional): Keyword search. If provided, ignores page range and extracts only pages containing the keyword.
*   `format` (Optional): Output format.
    *   `"text"` (Default): Plain text extraction.
    *   `"markdown"`: **Recommended**. Smartly identifies headers and paragraphs, suitable for LLM reading.
    *   `"json"`: Returns structured JSON data, suitable for programmatic processing.
*   `include_text` (Optional): Whether to extract text, default is `true`.
*   `include_images` (Optional): Whether to extract images, default is `false`.
*   `use_local_images_only` (Optional): Image processing mode, default is `true`.
    *   `true` (Default): Saves images locally to `extracted_images` directory and uses path references in Markdown. **Recommended for large files or PDFs with many images to prevent token overflow**.
    *   `false`: Returns Base64 data stream for images, allowing direct preview but consuming significant tokens.
*   `skip_table_detection` (Optional): **Speed Boost Mode** switch, default is `false`.
    *   `false` (Default): Intelligently detects and extracts tables, converting them to Markdown table format.
    *   `true`: **Skip table detection**. Suitable for scenarios requiring only plain text content. Speed can increase by 3-4x (approx. 400+ pages/sec).

### 2. `batch_extract_pdf_content`
Batch extracts PDF files in a specified directory.

**Parameters:**
*   `directory` (Required): Absolute path of the root directory to search.
*   `pattern` (Optional): File matching pattern, default is `"**/*.pdf"` (supports recursive search).
*   `custom_output_dir` (Optional): Specifies the output directory for Markdown/JSON files. If omitted, saves in the same directory as the PDF file.
*   `custom_image_output_dir` (Optional): Specifies the root output directory for images. If omitted, saves in an `extracted_images` folder within the PDF file's directory.
*   `format` (Optional): Output format, default is `"markdown"`.
*   `include_text` (Optional): Whether to extract text, default is `true`.
*   `include_images` (Optional): Whether to extract images, default is `false`.
*   `use_local_images_only` (Optional): Image processing mode, default is `true`.
*   `skip_table_detection` (Optional): **Speed Boost Mode** switch, default is `false`.
    *   `false` (Default): Intelligently detects and extracts tables, converting them to Markdown table format.
    *   `true`: **Skip table detection**. Suitable for scenarios requiring only plain text content. Speed can increase by 3-4x (approx. 400+ pages/sec).

### 3. `get_pdf_metadata`
Quickly retrieves PDF metadata and Table of Contents (TOC).

**Parameters:**
*   `file_path` (Required): Absolute path of the PDF file.

### 4. `convert_markdown_to_docx`
Converts Markdown content to a Word document.

**Parameters:**
*   `markdown_content` (Required): Markdown text content to convert.
*   `output_path` (Required): Absolute path for the output .docx file.
    *   *Note*: Enter the **new file path you want to save to**.
    *   *Example*: `D:\Documents\report_output.docx`

### 5. `convert_docx_to_pdf`
Converts a Word document to a PDF file.

**Parameters:**
*   `docx_path` (Required): Absolute path of the input .docx file.
*   `pdf_path` (Optional): Absolute path for the output .pdf file.
    *   If not provided, generates a pdf file with the same name in the same directory as the original docx file.

### 6. `search_pdf_files`
Fuzzy search for PDF file paths by filename.

**Parameters:**
*   `query` (Required): Filename keyword. Supports fuzzy matching (e.g., spelling errors), Chinese matching.
*   `directory` (Optional): Search root directory. Defaults to the current working directory.
*   `limit` (Optional): Maximum number of results to return, default is 10.
*   `threshold` (Optional): Matching threshold (0.0-1.0), default is 0.45.

### 7. `batch_extract_tables`
Batch extracts tables from all PDFs in a directory.

**Parameters:**
*   `directory` (Required): Absolute path of the root directory to search.
*   `output_dir` (Required): Output directory for table Markdown files.
*   `pattern` (Optional): File matching pattern, default is `"**/*.pdf"`.

**✨ Enhanced Table Extraction Features:**
*   **Smart Header Merging**: Automatically handles multi-line headers and split column names.
*   **Misaligned Column Fix**: Intelligently identifies and merges misaligned header and content columns due to formatting issues.
*   **Empty Row/Header Optimization**:
    *   Automatically removes invalid empty rows.
    *   Intelligently identifies KV structure tables, preserving headers only when necessary to avoid creating incorrect empty headers for Chinese KV tables.
*   **Pseudo-Table Filtering**:
    *   Automatically identifies and filters text lists (e.g., Table of Contents, step instructions).
    *   Automatically filters code blocks or long text paragraphs misidentified as tables.
*   **Layout Optimization**: Intelligently handles newlines within cells, maintaining clear list structures while allowing normal long text to reflow naturally.


## 📂 Output Directory Structure

After running the tool, images will be saved in the following structure:

```
extracted_images/
  └── PDF_Filename/
      ├── page_1_img_1.jpeg
      ├── page_1_img_2.png
      └── ...
```

## 💻 Development

*   **Core Code**: `src/simple_pdf/server.py`
*   **Conversion Logic**: `src/simple_pdf/convert.py`
