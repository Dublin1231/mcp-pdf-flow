# TODO: Batch Table Extraction

## 1. 待办事项 (Future Improvements)
- [ ] **监控新文档的误判情况**: 目前的伪表格过滤策略 (Strategy 9-11) 是基于启发式规则的，可能在极少数特殊格式文档上出现误杀或漏杀。建议在处理新类型文档时持续观察。
- [ ] **Excel (.xlsx) 输出支持**: 当前仅支持 Markdown，未来可考虑增加 Excel 格式输出，方便非技术人员使用。
- [ ] **日志优化**: 增强实时进度显示，支持 WebSocket 或回调方式通知客户端进度（目前为最终汇总返回）。
- [ ] **单元测试增强**: 为 `batch_extract_tables` 和 `is_valid_table` 的各种策略添加独立的单元测试用例，确保后续修改不破坏现有逻辑。

## 2. 配置检查
- 确保 Python 环境已安装 `pymupdf` (fitz)。
- 确保 `pypandoc` 或 `docx2pdf` 依赖已安装（如果未来需要转换功能）。
