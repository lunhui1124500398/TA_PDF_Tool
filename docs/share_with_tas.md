# 给其他助教分发使用

## 最快的分发方式

### 方案 A：GitHub 仓库

适合后续还会持续更新。

1. 把项目推到 GitHub。
2. 让其他助教安装：
   - Conda
   - Python 3.11 环境
   - Node.js
3. 他们执行：

```powershell
git clone <你的仓库地址>
cd ta_pdf_tool
npm install
conda activate ta_ocr_gpu
.\start_mvp.ps1
```

优点：

- 更新最方便
- 文档、问题修复、功能迭代都能同步

### 方案 B：打一个 zip 包

适合“今天就要给 2-3 个助教先用起来”。

建议把这些文件打包：

- `app.py`
- `mvp_store.py`
- `static/`
- `docs/`
- `requirements-mvp-backend.txt`
- `start_mvp.ps1`
- `package.json`
- `package-lock.json`
- `README.md`

不要打包这些本地内容：

- `data/`
- `node_modules/`
- `.conda/`
- `.conda-pkgs/`
- 你的真实作业 PDF

其他助教收到压缩包后执行：

```powershell
cd ta_pdf_tool
npm install
conda activate ta_ocr_gpu
.\start_mvp.ps1
```

## 给其他助教的最小安装要求

### Python 依赖

当前后端主要依赖：

- `fastapi`
- `uvicorn`
- `pydantic`
- `PyMuPDF`
- `Pillow`
- `requests`

### Node 依赖

前端 PDF 渲染依赖：

- `pdfjs-dist`

安装方式：

```powershell
npm install
```

## 推荐的演示顺序

第一次给助教演示时，建议只讲这 6 件事：

1. 创建会话
2. 上一份 / 下一份
3. 上一页 / 下一页
4. `✓ / △ / ✗`
5. 右键进入文本批注，`Enter` 保存后自动回到批改模式
6. 导出当前学生 PDF

## 常见问题

### 为什么不是一个安装包？

当前这版是 MVP，目标是先让批改流程顺起来。现在最稳的分发方式还是：

- GitHub 仓库
- 或 zip 包 + 运行脚本

如果后面要面向更多助教长期使用，再继续做成：

- `PyInstaller` 打包的单机版
- 或 `Tauri/Electron` 桌面版

## 建议的下一步

如果你准备正式推广给其他助教，下一步最值钱的是：

1. 固定一个干净的 Conda 环境导出方案
2. 写一个 5 分钟 demo
3. 录一段短视频或 GIF
4. 再决定是否做一键安装包
