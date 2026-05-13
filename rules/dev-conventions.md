# 开发规范

- **文档归入 `docs/`**：禁止在根目录创建散落文档
- **RaiDrive 路径优先**：涉及 `.openclaw` 必须用 `Z:\.openclaw` 而非 `C:\Users\Mac\.openclaw`
- **状态文件为唯一真值**：不以终端输出判定成功/失败
- **禁止 commit .log/.tmp/.bak**：hooks 自动过滤
