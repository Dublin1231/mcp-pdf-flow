# Consensus Document: Git Sync via SSH Strategy

## 1. 决策变更 (Decision Change)
- **最新决策**: 用户已明确指示切换到 **SSH 协议** ("ssh")。
- **废弃决策**: 之前的 HTTPS 调试方案 (Option B) 已被废弃。

## 2. 技术实施路径 (Technical Implementation Path)

我们将执行以下步骤来配置 SSH 连接：

1.  **检查/生成 SSH 密钥**:
    - 检查用户主目录 `.ssh` 下是否存在 `id_ed25519` 或 `id_rsa` 密钥对。
    - 如果不存在，使用 `ssh-keygen -t ed25519 -C "pdf-mcp-flow"` 生成新密钥。

2.  **获取公钥**:
    - 读取 `.pub` 文件内容。
    - **关键动作**: 将公钥展示给用户，由用户手动添加到 GitHub 仓库或账户设置中。

3.  **更新远程仓库 URL**:
    - 执行 `git remote set-url origin git@github.com:Dublin1231/PDF_MCP_Flow.git`。

4.  **验证与推送**:
    - 用户添加密钥后，执行 `git push --force` (因为我们要覆盖之前的提交历史)。

## 3. 验收标准 (Acceptance Criteria)
- 远程 URL 更新为 SSH 格式。
- `git push` 成功完成。
- 代码同步到 GitHub。
