# TA PDF Tool MVP

一个面向助教批改 PDF 作业的轻量本地工具，重点解决这几件事：

- 按作业文件夹建立批改会话
- 快速打 `✓ / △ / ✗`
- 直接在 PDF 页面上写中文批注和分数
- 拖拽调整位置、颜色、字号、粗细
- 复用最近批语和常用批语
- 导出单个学生或全班批改后的 PDF

## 当前推荐环境

- Windows
- Conda 环境：`D:\Conda_Data\envs\ta_ocr_gpu`
- Python 3.11

## 启动

```powershell
cd D:\Zhujiao\ta_pdf_tool
.\start_mvp.ps1
```

启动后打开：

```text
http://127.0.0.1:8000
```

## 主要文档

- 用户使用说明：[docs/user_guide.md](docs/user_guide.md)
- 后端运行说明：[docs/run_mvp_backend.md](docs/run_mvp_backend.md)
- 给其他助教分发使用：[docs/share_with_tas.md](docs/share_with_tas.md)
- 5 分钟演示脚本：[docs/demo_walkthrough.md](docs/demo_walkthrough.md)

## 当前代码结构

- `app.py`：FastAPI 入口
- `mvp_store.py`：会话、批注、导出逻辑
- `static/`：前端页面与交互
- `docs/`：运行、使用、演示、分发文档

## Git

这个目录现在已经适合直接用 Git 管理。推荐把本仓库推到 GitHub 后，再让其他助教按文档拉取并运行。
