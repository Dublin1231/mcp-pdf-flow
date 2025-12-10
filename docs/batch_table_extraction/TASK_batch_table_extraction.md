# TASK: Batch Table Extraction

## 1. Implement Worker Function
- **File**: `src/simple_pdf/server.py`
- **Function**: `_process_single_pdf_tables`
- **Logic**:
  - Open PDF.
  - Extract tables per page.
  - Convert to Markdown.
  - Save to file if tables exist.

## 2. Implement Tool Function
- **File**: `src/simple_pdf/server.py`
- **Function**: `batch_extract_tables`
- **Logic**:
  - Glob files.
  - Setup output directory.
  - Run pool.
  - Return summary.

## 3. Register Tool
- **File**: `src/simple_pdf/server.py`
- **Action**: Add to `server.list_tools` and `server.call_tool`.

## 4. Verify
- **Action**: Run a test script to extract tables from the sample directory.
