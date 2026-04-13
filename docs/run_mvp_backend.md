# MVP 后端启动说明

## 当前定位

这是当前手动 PDF 批改 MVP 的后端与静态前端入口。

它负责：

1. 扫描作业目录并创建会话。
2. 保存队列进度。
3. 保存每位学生的批注 sidecar。
4. 读取常用批语和最近批语。
5. 导出带批注的 PDF。
6. 提供前端页面和 API。

当前这条线不依赖 OCR。`ocr_extract.py`、`segment_questions.py`、`doubao_grader.py` 属于之前 AI / OCR 原型，不是这版 MVP 的必需依赖。

## 推荐环境

当前推荐直接使用：

```text
D:\Conda_Data\envs\ta_ocr_gpu
```

这个环境里已经具备当前 MVP 需要的核心包：

- `fastapi`
- `uvicorn`
- `PyMuPDF`
- `Pillow`
- `requests`
- `pydantic`

## 启动命令

推荐：

```powershell
cd D:\Zhujiao\ta_pdf_tool
.\start_mvp.ps1
```

或者手动运行：

```powershell
cd D:\Zhujiao\ta_pdf_tool
& 'D:\Conda_Data\envs\ta_ocr_gpu\python.exe' -m uvicorn app:app --reload --host 127.0.0.1 --port 8000
```

启动后访问：

```text
http://127.0.0.1:8000
```

## 首次使用建议

页面顶部建议这样创建会话：

```json
{
  "root_dir": "D:\\Zhujiao\\HW-4&5",
  "session_name": "hw45-mvp"
}
```

## 主要接口

- `GET /health`
- `GET /`
- `POST /api/session/create`
- `GET /api/session`
- `POST /api/session/current`
- `POST /api/students/{student_id}/status`
- `GET /api/students/{student_id}/pdf`
- `GET /api/students/{student_id}/annotations`
- `PUT /api/students/{student_id}/annotations`
- `GET /api/comments/library`
- `GET /api/comments/recent`
- `POST /api/comments/use`
- `POST /api/export/current/{student_id}`
- `POST /api/export/all`
