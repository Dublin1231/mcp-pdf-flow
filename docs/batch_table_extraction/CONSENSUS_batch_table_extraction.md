# CONSENSUS: Batch Table Extraction

## 1. 最终需求
新增 MCP 工具 `batch_extract_tables`，用于批量从指定目录下的 PDF 文件中提取表格，并保存为 Markdown 格式。

## 2. 技术实现
### 2.1 新增工具函数 `batch_extract_tables`
- **参数**:
  - `directory`: 搜索根目录。
  - `output_dir`: 输出目录 (默认: `directory/extracted_tables`).
  - `pattern`: 文件匹配模式 (默认: `**/*.pdf`).
  
### 2.2 核心处理逻辑 (`_process_single_pdf_tables`)
- 独立函数，支持多进程调用。
- 逻辑:
  1. 打开 PDF。
  2. 遍历所有页面。
  3. `page.find_tables()`.
  4. 使用 `is_valid_table` 过滤。
  5. 使用 `table_to_markdown` 转换。
  6. 如果发现表格，写入 `[filename]_tables.md`。

### 2.3 集成点
- 在 `src/simple_pdf/server.py` 中注册新工具。
- 复用现有的 `table_to_markdown` 和 `is_valid_table`。

## 3. 验收标准
- 运行 `batch_extract_tables` 后，目标文件夹生成对应的 Markdown 文件。
- Markdown 文件包含清晰的页码标记和表格内容。
- 无表格的 PDF 不生成文件。
