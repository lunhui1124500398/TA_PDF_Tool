# TA PDF 批改助手 MVP 设计稿

## 1. 目标

本 MVP 只解决助教手动批改 PDF 作业时最频繁、最痛的操作：

1. 基于 `HW-4&5` 目录创建一次批改会话，按学生形成队列。
2. 支持快捷键切换上一份、下一份、上一页、下一页，并实时显示队列进度。
3. 支持在 PDF 任意位置落三类批注：
   - 符号批注：`✓`、`✗`、`△`
   - 文字批注：中文批语、公式旁说明、数字说明
   - 分数批注：如 `8/10`、`-2`、`87`
4. 支持样式调整：颜色、字号、字体粗细。
5. 支持批语复用：优先弹出最近使用的批语，不合适时再切换常用批语。
6. 支持导出：把批注写回 PDF，并导出总成绩表。

## 2. 非目标

以下内容不进入本轮 MVP：

1. 自动 OCR 判题。
2. 自动识别题号并自动给分。
3. 多人协作和云同步。
4. 非 PDF 文件格式支持。
5. 复杂图形标注工具，如自由画笔、形状框选、橡皮擦。

## 3. 产品形态

### 3.1 开发阶段

MVP 先做成本地 Web 工具：

- 后端：`FastAPI + PyMuPDF`
- 前端：`PDF.js + 本地静态页面`
- 运行方式：本地启动一个 HTTP 服务，在浏览器中打开

这样做的原因：

1. 轻量，不需要先引入 Electron 或 Tauri。
2. 现有 Python 原型可以直接复用。
3. 批注导出、中文字体、PDF 写回都可沿用 PyMuPDF。
4. 后面如果需要桌面包，再把同一前端包进 Tauri 即可。

### 3.2 打包阶段

交互稳定后再决定是否套一层 Tauri：

- 如果浏览器版已经足够顺手，可以继续保留浏览器版。
- 如果需要更稳定的快捷键、窗口控制和更像桌面软件的体验，再封装 Tauri。

## 4. 核心用户流程

1. 用户选择作业目录 `HW-4&5`。
2. 系统扫描 PDF，按文件名解析 `学号-姓名`，生成会话。
3. 默认打开当前队列中的第一份未完成作业。
4. 用户用快捷键切页、切人、落勾叉、落文字、落分数。
5. 用户从“最近批语”中复用批语，必要时修改后再次使用。
6. 用户将当前学生标记为已完成，进入下一份。
7. 会话中途退出后，再次打开可恢复上次位置。
8. 最后导出批注后的 PDF 和总成绩 CSV。

## 5. 界面布局

### 5.1 顶部状态栏

展示以下信息：

- 当前会话名
- 当前学生：`3 / 20`
- 当前页：`2 / 5`
- 已完成：`8`
- 未完成：`12`
- 当前工具：`✓ / ✗ / △ / 文本 / 分数`

### 5.2 左侧队列栏

字段：

- 学号
- 姓名
- 页数
- 状态：`未开始 / 进行中 / 已完成`
- 分数摘要

操作：

- 点击切换到某一份作业
- 支持“仅看未完成”
- 支持按学号排序

### 5.3 中间 PDF 区

行为：

- 一次只打开一个学生 PDF
- 只渲染当前页和附近页，避免卡顿
- 缩放不影响批注位置
- 批注以覆盖层显示，点击后立即可拖动或编辑

### 5.4 右侧工具栏

模块：

1. 工具选择
   - `✓`
   - `✗`
   - `△`
   - 文本
   - 分数
2. 样式设置
   - 颜色
   - 字号
   - 粗细
3. 最近批语
4. 常用批语
5. 当前页批注列表

## 6. 快捷键设计

### 6.1 导航

- `J`：上一份作业
- `K`：下一份作业
- `[`：上一页
- `]`：下一页
- `Ctrl+J`：跳到上一份未完成
- `Ctrl+K`：跳到下一份未完成
- `Ctrl+Enter`：标记当前学生已完成

### 6.2 批注工具

- `1`：切换为 `✓`
- `2`：切换为 `△`
- `3`：切换为 `✗`
- `T`：切换为文本批注
- `G`：切换为分数批注
- `Delete`：删除当前选中批注
- `Ctrl+Z`：撤销最近一次本地编辑

### 6.3 批语复用

- `R`：打开最近批语列表
- `C`：打开常用批语列表
- `Enter`：应用当前选中的批语

## 7. 批注模型

所有批注先保存到 sidecar 文件，不立即回写原 PDF。

### 7.1 支持的批注类型

#### `symbol`

用于 `✓`、`✗`、`△`

#### `text`

用于中文批语、数字说明、题旁说明

#### `score`

用于分数和扣分说明

### 7.2 坐标系统

统一使用 PDF 页坐标：

- `page_index`：从 1 开始
- `x`、`y`：基于 PDF 原始页面坐标
- `width`、`height`：仅文本类和分数类需要

这样可以保证：

1. 缩放时不漂移。
2. 导出时无需做屏幕坐标换算。
3. 后续如果更换前端框架，数据仍可复用。

## 8. 本地数据文件

### 8.1 `session.json`

用于记录会话和进度。

```json
{
  "version": 1,
  "session_name": "HW4&5-2026-spring",
  "root_dir": "D:\\Zhujiao\\HW-4&5",
  "created_at": "2026-04-12T15:00:00+08:00",
  "current_student_index": 2,
  "filter": "all",
  "students": [
    {
      "student_id": "2500011895",
      "name": "王泽楷",
      "pdf_path": "D:\\Zhujiao\\HW-4&5\\2500011895-王泽楷-HW4&5.pdf",
      "page_count": 4,
      "status": "done",
      "last_page": 4,
      "score_summary": "88"
    }
  ]
}
```

### 8.2 `annotations.json`

用于记录所有可编辑批注。

```json
{
  "version": 1,
  "session_name": "HW4&5-2026-spring",
  "students": {
    "2500011895": {
      "updated_at": "2026-04-12T15:30:00+08:00",
      "annotations": [
        {
          "id": "ann_001",
          "type": "symbol",
          "page_index": 1,
          "x": 322.4,
          "y": 415.2,
          "text": "✓",
          "style": {
            "color": "#d11a2a",
            "font_size": 24,
            "font_weight": "bold"
          }
        },
        {
          "id": "ann_002",
          "type": "text",
          "page_index": 2,
          "x": 118.0,
          "y": 530.0,
          "width": 180.0,
          "height": 48.0,
          "text": "思路正确，但最后一步单位遗漏。",
          "style": {
            "color": "#1f5aa6",
            "font_size": 12,
            "font_weight": "normal"
          },
          "source_comment_id": "calc.unit_missing"
        },
        {
          "id": "ann_003",
          "type": "score",
          "page_index": 4,
          "x": 460.0,
          "y": 88.0,
          "text": "8/10",
          "style": {
            "color": "#111111",
            "font_size": 14,
            "font_weight": "bold"
          }
        }
      ]
    }
  }
}
```

### 8.3 `comment_library.md`

用于人工维护的常用批语库。

建议格式：

```md
# 常用批语

## Calculation
- [calc.unit_missing] 思路正确，但最后一步单位遗漏。
- [calc.sigfig] 计算过程基本正确，注意有效数字。

## Logic
- [logic.clear] 思路清晰，推导完整。
- [logic.skip_step] 关键结论正确，但中间推导步骤缺失。
```

### 8.4 `comment_usage.json`

用于记录最近使用顺序和频次。

```json
{
  "version": 1,
  "recent": [
    "calc.unit_missing",
    "logic.skip_step"
  ],
  "stats": {
    "calc.unit_missing": {
      "count": 8,
      "last_used_at": "2026-04-12T15:28:00+08:00"
    }
  }
}
```

说明：

1. `comment_library.md` 负责“内容可编辑”。
2. `comment_usage.json` 负责“最近优先”和“频次排序”。
3. 批注中只引用 `source_comment_id`，保留来源关系。

## 9. 本地 API 设计

### 9.1 会话

- `POST /api/session/create`
  - 输入：作业目录
  - 输出：扫描结果、学生列表、默认 current index

- `GET /api/session`
  - 输出：当前会话状态、进度、当前学生

- `POST /api/session/current`
  - 输入：当前学生索引、当前页
  - 用途：切换后即时保存

### 9.2 PDF

- `GET /api/students/{student_id}/pdf`
  - 返回原 PDF

- `GET /api/students/{student_id}/annotations`
  - 返回该学生所有本地批注

- `PUT /api/students/{student_id}/annotations`
  - 覆盖保存该学生全部批注

### 9.3 批语库

- `GET /api/comments/library`
  - 返回解析后的常用批语

- `GET /api/comments/recent`
  - 返回最近使用批语

- `POST /api/comments/use`
  - 输入：`comment_id`
  - 用途：更新最近使用和频次

### 9.4 导出

- `POST /api/export/current`
  - 导出当前学生 PDF

- `POST /api/export/all`
  - 导出全部批注后的 PDF 和成绩 CSV

## 10. 导出策略

### 10.1 原则

1. 编辑态与导出态分离。
2. 编辑时只存 JSON，不频繁改 PDF。
3. 导出时再批量写回 PDF。

### 10.2 写回方式

导出时用 `PyMuPDF` 将批注直接绘制到页面：

- `symbol`：按文本写入
- `text`：按文本框写入
- `score`：按文本写入

不依赖阅读器自己的注释渲染，原因是：

1. 中文显示更可控。
2. 样式一致性更高。
3. 不容易出现不同 PDF 阅读器显示差异。

## 11. 性能策略

1. 一次只打开一份 PDF。
2. 前端只渲染当前页和相邻页。
3. 批注保存做 300ms 防抖。
4. 切换学生时强制落盘 sidecar。
5. 导出时按学生逐个处理，避免一次持有全部 PDF。

## 12. 复用现有原型的部分

当前仓库中的 [grade_tool.py](../legacy/grade_tool.py) 可以直接复用这些能力：

1. 文件名解析 `学号-姓名`
2. PDF 枚举和批量处理
3. PyMuPDF 写回 PDF
4. Windows 中文字体探测

建议保留这部分为后端导出层，不再继续沿用“先合并成一个大 PDF 再批改”的交互模型。

## 13. 建议的开发顺序

### 里程碑 1：会话与查看

1. 扫描目录生成 `session.json`
2. 打开当前学生 PDF
3. 实现上一份、下一份、上一页、下一页
4. 实现进度展示

### 里程碑 2：基本批注

1. 实现 `✓ / △ / ✗`
2. 实现文本批注
3. 实现分数批注
4. 实现样式切换

### 里程碑 3：批语复用

1. 解析 `comment_library.md`
2. 记录 `comment_usage.json`
3. 支持最近批语和常用批语选择

### 里程碑 4：导出

1. 导出当前学生 PDF
2. 导出全部 PDF
3. 导出总成绩 CSV

## 14. 当前推荐依赖

MVP 后端只安装这组依赖：

- `fastapi`
- `uvicorn[standard]`
- `pydantic`
- `PyMuPDF`
- `Pillow`
- `requests`

说明：

1. `PyMuPDF` 和 `Pillow` 是当前原型已经在用的基础能力。
2. `requests` 保留给后续答题卡审阅或外部 API 原型使用。
3. `paddleocr` 暂不进入默认安装，因为它体积大、网络更容易卡，而且手动批改 MVP 当前并不依赖它。
