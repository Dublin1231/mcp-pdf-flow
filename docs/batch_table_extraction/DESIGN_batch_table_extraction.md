# DESIGN: Batch Table Extraction

## 1. 模块设计

### 1.1 `server.py` 更新
新增两个主要组件：
1. **`_process_single_pdf_tables(args)`**:
   - Worker function for `ProcessPoolExecutor`.
   - Args: `(pdf_path, output_dir)`
   - Returns: `(pdf_path, num_tables_found, output_file_path)`

2. **`batch_extract_tables(directory, output_dir=None, pattern="**/*.pdf")`**:
   - Main tool function.
   - Scans directory.
   - Submits tasks to executor.
   - Aggregates results.

### 1.2 数据流
User -> `batch_extract_tables` -> `glob` -> `ProcessPoolExecutor` -> `_process_single_pdf_tables` -> `fitz` -> `Markdown File`

## 2. 接口定义
```python
async def batch_extract_tables(directory: str, output_dir: str = None, pattern: str = "**/*.pdf") -> list[types.TextContent]:
    """
    批量提取指定目录下的PDF表格并保存为Markdown文件。
    """
```

## 3. 异常处理
- 单个 PDF 处理失败不应中断整体流程。
- 错误信息记录在返回结果中。
