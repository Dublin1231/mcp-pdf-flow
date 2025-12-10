# ALIGNMENT: Batch Table Extraction

## 1. 原始需求
用户要求 "新增批量提取表格的功能"。
目标是能够指定一个目录，批量处理其中的 PDF 文件，提取其中的所有表格，并保存为独立的文件（如 Markdown）。

## 2. 现有架构分析
- **Current Tools**:
  - `extract_pdf_content`: Single PDF text/image extraction.
  - `batch_extract_pdf_content`: Batch version of above.
  - `table_to_markdown`: Helper function to convert table objects to Markdown.
- **Library**: Uses `PyMuPDF` (`fitz`).
- **Pattern**:
  - Worker functions (`_process_single_pdf_worker`) for concurrency.
  - Tools registered with `server.list_tools()`.

## 3. 需求规范
### 功能定义
- **Tool Name**: `batch_extract_tables`
- **Input**:
  - `directory` (string, required): Source directory containing PDFs.
  - `output_dir` (string, optional): Destination directory for extracted tables. Defaults to `[directory]/extracted_tables`.
  - `format` (string, optional): Output format. Currently supports 'markdown'. (Future: 'csv', 'json').
- **Output**:
  - Returns a summary string (processed count, success/fail count).
  - Creates files in `output_dir`.
    - Naming convention: `[pdf_filename]_tables.md`
    - Content:
      - Header: `## File: [pdf_filename]`
      - Per Table:
        - `### Page [N] Table [M]`
        - The Markdown table.

### 核心逻辑
1. **Recursively find PDFs** in `directory`.
2. **Process each PDF**:
   - Open PDF.
   - Iterate Pages.
   - `page.find_tables()`.
   - Filter valid tables using `is_valid_table()`.
   - Convert to Markdown using `table_to_markdown()`.
   - Accumulate results.
   - Write to `output_dir/[pdf_name]_tables.md`.
3. **Concurrency**: Use `ProcessPoolExecutor` (similar to `batch_extract_pdf_content`) for speed.

## 4. 关键决策
- **Format**: Start with Markdown as it's the current strong suit (and verified in previous tasks).
- **Validation**: Reuse `is_valid_table` to ensure high quality (avoiding garbage text).
- **Empty Tables**: If a PDF has no tables, should we create an empty file? -> **Decision**: No, skip creating files for PDFs with no tables to keep output clean.

## 5. 验收标准
- [ ] Tool `batch_extract_tables` is available.
- [ ] Can process a directory with multiple PDFs.
- [ ] Generates `*_tables.md` files in the specified output directory.
- [ ] Only valid tables are extracted.
- [ ] Page numbers are preserved in the output.
