# Conda 环境状态说明

更新时间：2026-04-12

## 1. 当前状态

项目内目标环境位置仍然是：

```text
D:\Zhujiao\ta_pdf_tool\.conda
```

当前这个独立环境还没有创建成功。

项目目录下保留了本地 conda 缓存目录：

```text
D:\Zhujiao\ta_pdf_tool\.conda-pkgs
```

它目前只作为下载缓存使用，不是可运行环境。

## 2. 当前已经验证可用的环境

当前可直接用于继续开发的环境是：

```text
D:\Conda_Data\envs\ta_ocr_gpu
```

我已经确认这个环境里具备：

- `Python 3.11.15`
- `fastapi 0.135.3`
- `uvicorn 0.44.0`
- `pydantic 2.12.5`
- `PyMuPDF 1.27.2.2`
- `Pillow 12.2.0`
- `requests 2.33.1`
- `paddleocr`

## 3. 对当前半自动批改 MVP 的含义

当前这条半自动批改线不依赖 OCR。

也就是说，现在真正需要的后端依赖已经齐了：

- `fastapi`
- `uvicorn`
- `pydantic`
- `PyMuPDF`
- `Pillow`
- `requests`

`paddleocr` 只是之前 AI / OCR 原型链路留下的能力，不是当前这版手动批改 MVP 的必需项。

## 4. 当前最推荐的做法

直接复用：

```text
D:\Conda_Data\envs\ta_ocr_gpu
```

启动当前 MVP 后端：

```powershell
& 'D:\Conda_Data\envs\ta_ocr_gpu\python.exe' -m uvicorn app:app --reload --host 127.0.0.1 --port 8000
```

工作目录：

```text
D:\Zhujiao\ta_pdf_tool
```

## 5. 如果后面还想补独立项目环境

后面如果仍然想把独立环境建在项目目录里，可以继续尝试：

```powershell
$env:CONDA_OVERRIDE_CUDA='0'
$env:CONDA_PKGS_DIRS='D:\Zhujiao\ta_pdf_tool\.conda-pkgs'
conda create -p D:\Zhujiao\ta_pdf_tool\.conda -c conda-forge python=3.11 pip fastapi uvicorn pydantic pillow requests -y
D:\Zhujiao\ta_pdf_tool\.conda\python.exe -m pip install PyMuPDF
```

但就当前开发进度来说，这不是阻塞项。
