# Alignment Document: Git Sync and Project Optimization

## 1. 项目上下文分析 (Project Context Analysis)

### 1.1 现有项目结构
- **核心代码**: `src/simple_pdf/server.py` (已更新支持矢量图形提取)
- **文档**: `BENCHMARK_REPORT.md` (性能基准测试报告)
- **工具**: `tools/extract_pdf.py` (独立提取工具)
- **依赖**: PyMuPDF (Fitz), MCP SDK

### 1.2 最近变更
- **矢量图形支持**: 在 `server.py` 中添加了 `merge_rects` 函数和 `get_drawings` 逻辑，解决了封面布局不一致的问题。
- **Git 状态**: 尝试提交中文 Commit 并在 HTTPS 推送时遇到 TLS 连接错误。

## 2. 需求理解确认 (Requirements Understanding)

### 2.1 核心目标
1.  **Git 同步 (Git Sync)**: 解决 Git Push 失败的问题，将本地代码（含最新的矢量图形支持）推送到远程仓库。
2.  **代码稳固 (Code Stabilization)**: 确保最近修改的 `server.py` 没有引入回归错误。
3.  **文档规范 (Documentation)**: 建立符合 6A 工作流的文档结构。

### 2.2 边界确认
- **范围**: 仅限于当前的 Git 问题和已有的代码功能验证。不开发新的 PDF 功能，除非用户另有指示。
- **环境**: Windows, PowerShell.

## 3. 智能决策策略 (Intelligent Decision Strategy)

### 3.1 Git 连接问题
- **现象**: `error:0A000126:SSL routines::unexpected eof while reading`
- **分析**: 这通常是网络代理或 OpenSSL 版本不兼容导致的。之前尝试过 `http.sslBackend=openssl` 和取消代理，但未成功。
- **策略**: 
    1.  **优先**: 尝试配置 SSH 方式连接 GitHub（绕过 HTTPS/TLS 问题）。
    2.  **备选**: 继续调试 HTTPS 代理设置 (Git config http.proxy)。

### 3.2 代码验证
- **策略**: 运行一次针对 NUC 手册的测试提取，确保输出稳定。

## 4. 关键决策点 (Key Decision Points)

1.  **Git 协议切换**: 鉴于 HTTPS 持续失败，是否同意切换到 SSH 协议？（需要生成 SSH Key 并添加到 GitHub）
2.  **任务范围**: 是否有其他未提及的 PDF 功能需求？

## 5. 待确认事项
- 请确认是否同意优先尝试 SSH 方式解决 Git 上传问题。
