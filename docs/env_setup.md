# TA PDF Tool 环境说明

## 1. 推荐方案

当前项目改为使用 `conda` 管理环境，推荐 `Python 3.11`。

推荐 `3.11` 的原因：

1. 当前项目计划使用的 FastAPI 最新版要求 `Python >= 3.10`。
2. PyMuPDF 最新版要求 `Python >= 3.10`。
3. 这台机器上已有一个已经验证过的 OCR 环境 `D:\Conda_Data\envs\ta_ocr_gpu`，使用的是 `Python 3.11.15`，说明你当前机器对 `3.11` 已经跑通过相关依赖。
4. `3.11` 相比 `3.10` 一般有更好的运行性能，同时兼容性已经足够成熟。

如果只在 `3.10` 和 `3.11` 中二选一，当前建议是 `3.11`。

## 1.1 当前已验证可用环境

当前最省事的做法，是直接复用这套已经装好依赖的环境：

```text
D:\Conda_Data\envs\ta_ocr_gpu
```

它已经具备当前 MVP 后端需要的核心包，包括：

- `fastapi`
- `uvicorn`
- `pydantic`
- `PyMuPDF`
- `Pillow`
- `requests`

## 2. 为什么刚才不是最终用 3.9

刚才临时使用 `3.9`，只是因为这台机器上现成可直接调用且自带 `pip` 的系统解释器是 `Python 3.9`，方便先把依赖安装链路跑通。

那是一个“先验证工具链能不能动”的临时选择，不是最终推荐版本。现在既然你明确希望统一走 `conda`，就应该直接切到 `3.11`。

## 3. 创建 conda 环境

建议把环境建在项目目录里，避免受全局 `envs_dirs` 权限影响。

在 `d:\Zhujiao\ta_pdf_tool` 目录执行：

```powershell
$env:CONDA_OVERRIDE_CUDA='0'
conda env create -p .\.conda -f .\environment.mvp.yml
```

说明：

1. 这里显式设置 `CONDA_OVERRIDE_CUDA=0`，是为了绕开这台机器当前 `conda` 的 CUDA 虚拟包探测报错。
2. 使用 `-p .\.conda` 是为了把环境放在当前项目目录里，避免写全局目录失败。

## 4. 安装内容

`environment.mvp.yml` 当前优先从 `conda-forge` 安装这些核心依赖：

- `python=3.11`
- `fastapi`
- `uvicorn`
- `pydantic`
- `pillow`
- `requests`

`PyMuPDF` 目前不放在 `conda` 这一步里，后续用 `pip` 单独补装。

仓库里仍保留 `requirements-mvp-backend.txt`，作为后续 `pip` 兜底方案。

## 5. 更新环境

```powershell
$env:CONDA_OVERRIDE_CUDA='0'
conda env update -p .\.conda -f .\environment.mvp.yml --prune
```

## 6. 补装 PyMuPDF

环境创建成功后，再补这一条：

```powershell
.\.conda\python.exe -m pip install PyMuPDF>=1.24,<1.27
```

如果后面发现还想统一走 `pip`，也可以改用：

```powershell
.\.conda\python.exe -m pip install -r .\requirements-mvp-backend.txt
```

## 7. 使用环境

不强依赖 `conda activate`，直接调用解释器更稳：

```powershell
.\.conda\python.exe -V
.\.conda\python.exe -m pip --version
```

如果后面确实想激活：

```powershell
conda activate d:\Zhujiao\ta_pdf_tool\.conda
```

## 8. 快速验证

```powershell
.\.conda\python.exe -c "import fitz, PIL, fastapi, uvicorn, requests; print('ok')"
```

## 9. 当前默认不安装的内容

以下依赖暂不作为默认安装项：

- `paddleocr`
- `paddlepaddle`

原因：

1. 体积大，下载更容易卡。
2. 手动批改 MVP 本身不依赖它们。
3. 你们已经有单独的 OCR 环境，后续如需复用 OCR，更适合独立维护。

## 10. 建议的目录约定

```text
ta_pdf_tool/
  .conda/
  docs/
  environment.mvp.yml
  requirements-mvp-backend.txt
  grade_tool.py
  ...
```

## 11. 后续启动方式

当前仓库还没有完整的 Web MVP 服务入口。后续补上 `app.py` 后，推荐统一用下面的方式启动：

```powershell
.\.conda\python.exe -m uvicorn app:app --reload
```
