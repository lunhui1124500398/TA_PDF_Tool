from __future__ import annotations

import argparse
import csv
import io
import json
import re
import shutil
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Iterable

import fitz
from PIL import Image, ImageDraw, ImageFont


ID_PATTERN = re.compile(r"(?<!\d)(\d{10})(?!\d)")
NAME_PATTERN = re.compile(r"[\u4e00-\u9fff·]{2,20}")
HEADER_HEIGHT_PT = 42.0
COMMENT_PANEL_WIDTH_PT = 220.0
COMMENT_MARGIN_PT = 14.0
PNG_SCALE = 2.5
COMMENT_PLACEHOLDER = "批语待填写\n\n可在批改后回到终端补写批语。"
FONT_CANDIDATES = [
    Path(r"C:\Windows\Fonts\msyh.ttc"),
    Path(r"C:\Windows\Fonts\simhei.ttf"),
    Path(r"C:\Windows\Fonts\simsun.ttc"),
]
FONT_BOLD_CANDIDATES = [
    Path(r"C:\Windows\Fonts\msyhbd.ttc"),
    Path(r"C:\Windows\Fonts\simhei.ttf"),
    Path(r"C:\Windows\Fonts\msyh.ttc"),
]


@dataclass
class StudentMeta:
    student_id: str
    name: str
    source_name: str
    source_path: Path

    @property
    def normalized_name(self) -> str:
        return sanitize_filename(f"{self.student_id}-{self.name}.pdf")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="助教 PDF 整理与批语工具：规范化命名、合并 PDF、写回批语。"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    organize = subparsers.add_parser("organize", help="整理文件名并复制/移动到新目录。")
    organize.add_argument("source_dir", type=Path, help="原始作业目录。")
    organize.add_argument(
        "--output-dir",
        type=Path,
        help="整理后目录，默认是 <source_dir>/organized。",
    )
    organize.add_argument(
        "--move",
        action="store_true",
        help="直接移动文件。默认是复制，避免误操作。",
    )
    organize.add_argument(
        "--dry-run",
        action="store_true",
        help="只打印会发生什么，不真正修改文件。",
    )

    merge = subparsers.add_parser("merge", help="合并 PDF，并给每页加页眉与批语区。")
    merge.add_argument("input_dir", type=Path, help="待合并的 PDF 目录。")
    merge.add_argument(
        "--output-pdf",
        type=Path,
        help="输出 PDF 路径，默认是 <input_dir>/merged_for_grading.pdf。",
    )
    merge.add_argument(
        "--manifest",
        type=Path,
        help="输出清单路径，默认是与输出 PDF 同目录同名 .json。",
    )

    comment = subparsers.add_parser("comment", help="给合并后的 PDF 写回批语。")
    comment.add_argument("manifest", type=Path, help="merge 生成的 manifest.json。")
    comment.add_argument("--student-id", help="按学号写入单个学生批语。")
    comment.add_argument("--text", help="批语文本。")
    comment.add_argument("--text-file", type=Path, help="从文本文件读取批语。")
    comment.add_argument(
        "--interactive",
        action="store_true",
        help="按学生顺序逐个提示输入批语。",
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.command == "organize":
        run_organize(
            source_dir=args.source_dir,
            output_dir=args.output_dir,
            move_files=args.move,
            dry_run=args.dry_run,
        )
        return
    if args.command == "merge":
        run_merge(args.input_dir, args.output_pdf, args.manifest)
        return
    if args.command == "comment":
        run_comment(
            manifest_path=args.manifest,
            student_id=args.student_id,
            text=args.text,
            text_file=args.text_file,
            interactive=args.interactive,
        )
        return
    raise ValueError(f"Unknown command: {args.command}")


def run_organize(
    source_dir: Path,
    output_dir: Path | None,
    move_files: bool,
    dry_run: bool,
) -> None:
    source_dir = source_dir.resolve()
    if not source_dir.is_dir():
        raise SystemExit(f"目录不存在: {source_dir}")

    target_dir = (output_dir or (source_dir / "organized")).resolve()
    files = list_pdf_files(source_dir)
    if not files:
        raise SystemExit(f"目录里没有 PDF: {source_dir}")

    rows: list[dict[str, str]] = []
    planned_targets: set[str] = set()
    for pdf_path in files:
        meta = extract_student_meta(pdf_path)
        if meta is None:
            rows.append(
                {
                    "status": "unresolved",
                    "student_id": "",
                    "name": "",
                    "source_name": pdf_path.name,
                    "target_name": "",
                    "note": "无法从文件名中识别学号和姓名",
                }
            )
            continue

        target_name = make_unique_name(meta.normalized_name, planned_targets)
        planned_targets.add(target_name.lower())
        rows.append(
            {
                "status": "planned",
                "student_id": meta.student_id,
                "name": meta.name,
                "source_name": pdf_path.name,
                "target_name": target_name,
                "note": "move" if move_files else "copy",
            }
        )

        if dry_run:
            continue

        target_dir.mkdir(parents=True, exist_ok=True)
        final_path = dedupe_path(target_dir / target_name)
        if move_files:
            shutil.move(str(pdf_path), str(final_path))
        else:
            shutil.copy2(pdf_path, final_path)

    if not dry_run:
        write_csv(
            target_dir / "organize_summary.csv",
            rows,
            ["status", "student_id", "name", "source_name", "target_name", "note"],
        )

    print(f"共扫描 {len(files)} 个 PDF。")
    resolved = sum(1 for row in rows if row["status"] == "planned")
    unresolved = len(rows) - resolved
    print(f"成功识别 {resolved} 个，未识别 {unresolved} 个。")
    for row in rows:
        if row["status"] == "planned":
            print(f"{row['source_name']} -> {row['target_name']}")
        else:
            print(f"{row['source_name']} -> [未处理] {row['note']}")

    if dry_run:
        print("dry-run 模式：未实际复制/移动文件。")
    else:
        print(f"输出目录: {target_dir}")


def run_merge(input_dir: Path, output_pdf: Path | None, manifest: Path | None) -> None:
    input_dir = input_dir.resolve()
    if not input_dir.is_dir():
        raise SystemExit(f"目录不存在: {input_dir}")

    output_pdf = (output_pdf or (input_dir / "merged_for_grading.pdf")).resolve()
    manifest_path = (manifest or output_pdf.with_suffix(".json")).resolve()
    temp_output_pdf = output_pdf.with_name(f"{output_pdf.stem}.tmp{output_pdf.suffix}")

    pdf_files = [
        path
        for path in list_pdf_files(input_dir)
        if path.resolve() not in {output_pdf, temp_output_pdf}
    ]
    students = []
    for pdf_path in pdf_files:
        meta = extract_student_meta(pdf_path)
        if meta is None:
            print(f"跳过无法识别的文件: {pdf_path.name}")
            continue
        students.append(meta)

    if not students:
        raise SystemExit("没有可合并的已识别 PDF。")

    students.sort(key=lambda item: (item.student_id, item.name, item.source_name))
    output_pdf.parent.mkdir(parents=True, exist_ok=True)

    existing_comments = load_existing_comments(manifest_path)
    merged_doc = fitz.open()
    toc: list[list[int | str]] = []
    manifest_students: list[dict[str, object]] = []

    for meta in students:
        with fitz.open(meta.source_path) as source_doc:
            source_page_count = source_doc.page_count
            first_page_index = merged_doc.page_count + 1
            comment_text = existing_comments.get(meta.student_id, "")
            comment_rect_for_manifest: list[float] | None = None

            for page_index in range(source_page_count):
                source_page = source_doc[page_index]
                source_rect = source_page.rect
                extra_width = COMMENT_PANEL_WIDTH_PT if page_index == 0 else 0.0
                dest_width = source_rect.width + extra_width
                dest_height = source_rect.height + HEADER_HEIGHT_PT
                dest_page = merged_doc.new_page(width=dest_width, height=dest_height)
                dest_page.show_pdf_page(
                    fitz.Rect(0, HEADER_HEIGHT_PT, source_rect.width, dest_height),
                    source_doc,
                    page_index,
                )

                header_rect = fitz.Rect(0, 0, dest_width, HEADER_HEIGHT_PT)
                header_stream = render_header_image(
                    width_pt=dest_width,
                    height_pt=HEADER_HEIGHT_PT,
                    label=f"{meta.student_id}  {meta.name}",
                    page_index=page_index + 1,
                    total_pages=source_page_count,
                )
                dest_page.insert_image(header_rect, stream=header_stream, overlay=True)

                if page_index == 0:
                    comment_rect = fitz.Rect(
                        source_rect.width + COMMENT_MARGIN_PT,
                        HEADER_HEIGHT_PT + COMMENT_MARGIN_PT,
                        dest_width - COMMENT_MARGIN_PT,
                        dest_height - COMMENT_MARGIN_PT,
                    )
                    comment_stream = render_comment_panel_image(
                        width_pt=comment_rect.width,
                        height_pt=comment_rect.height,
                        title=f"{meta.student_id} {meta.name}",
                        comment_text=comment_text,
                    )
                    dest_page.insert_image(comment_rect, stream=comment_stream, overlay=True)
                    comment_rect_for_manifest = [
                        comment_rect.x0,
                        comment_rect.y0,
                        comment_rect.x1,
                        comment_rect.y1,
                    ]

            last_page_index = merged_doc.page_count
            toc.append([1, f"{meta.student_id} {meta.name}", first_page_index])
            manifest_students.append(
                {
                    "student_id": meta.student_id,
                    "name": meta.name,
                    "source_pdf": str(meta.source_path),
                    "source_name": meta.source_name,
                    "page_count": source_page_count,
                    "first_page_index": first_page_index,
                    "last_page_index": last_page_index,
                    "comment_page_index": first_page_index,
                    "comment_rect": comment_rect_for_manifest,
                    "comment": comment_text,
                }
            )

    merged_doc.set_toc(toc)
    save_pdf_atomic(merged_doc, output_pdf)

    manifest_data = {
        "version": 1,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "input_dir": str(input_dir),
        "merged_pdf": str(output_pdf),
        "header_height_pt": HEADER_HEIGHT_PT,
        "comment_panel_width_pt": COMMENT_PANEL_WIDTH_PT,
        "students": manifest_students,
    }
    write_json_atomic(manifest_path, manifest_data)

    print(f"已输出合并 PDF: {output_pdf}")
    print(f"已输出清单文件: {manifest_path}")
    print(f"共合并 {len(manifest_students)} 名学生，合计 {merged_doc.page_count} 页。")


def run_comment(
    manifest_path: Path,
    student_id: str | None,
    text: str | None,
    text_file: Path | None,
    interactive: bool,
) -> None:
    manifest_path = manifest_path.resolve()
    if not manifest_path.is_file():
        raise SystemExit(f"manifest 不存在: {manifest_path}")

    manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
    merged_pdf = Path(manifest_data["merged_pdf"]).resolve()
    if not merged_pdf.is_file():
        raise SystemExit(f"合并后的 PDF 不存在: {merged_pdf}")

    students: list[dict[str, object]] = manifest_data["students"]
    if interactive:
        updates = collect_comments_interactively(students)
        if not updates:
            print("没有新增批语。")
            return
        apply_comment_updates(merged_pdf, manifest_path, manifest_data, updates)
        print(f"已写入 {len(updates)} 条批语。")
        return

    if text_file:
        text = text_file.read_text(encoding="utf-8")
    if not student_id or text is None:
        raise SystemExit("单条写回需要同时提供 --student-id 和 --text / --text-file。")

    apply_comment_updates(merged_pdf, manifest_path, manifest_data, {student_id: text})
    print(f"已写入 {student_id} 的批语。")


def collect_comments_interactively(
    students: list[dict[str, object]],
) -> dict[str, str]:
    updates: dict[str, str] = {}
    print("交互模式：直接输入批语并回车，留空表示跳过，输入 :q 退出。")
    for item in students:
        sid = str(item["student_id"])
        name = str(item["name"])
        existing = str(item.get("comment", "") or "")
        if existing:
            print(f"[{sid} {name}] 现有批语: {existing}")
        user_input = input(f"[{sid} {name}] 新批语: ").strip()
        if user_input == ":q":
            break
        if not user_input:
            continue
        updates[sid] = user_input
    return updates


def apply_comment_updates(
    merged_pdf: Path,
    manifest_path: Path,
    manifest_data: dict[str, object],
    updates: dict[str, str],
) -> None:
    student_map = {
        str(item["student_id"]): item for item in manifest_data["students"]  # type: ignore[index]
    }
    missing = [sid for sid in updates if sid not in student_map]
    if missing:
        raise SystemExit(f"这些学号不在 manifest 中: {', '.join(missing)}")

    doc = fitz.open(merged_pdf)
    try:
        for sid, comment in updates.items():
            item = student_map[sid]
            page_index = int(item["comment_page_index"]) - 1
            rect = fitz.Rect(item["comment_rect"])
            title = f"{item['student_id']} {item['name']}"
            page = doc[page_index]
            page.draw_rect(rect, color=(1, 1, 1), fill=(1, 1, 1), width=0, overlay=True)
            comment_stream = render_comment_panel_image(
                width_pt=rect.width,
                height_pt=rect.height,
                title=title,
                comment_text=comment,
            )
            page.insert_image(rect, stream=comment_stream, overlay=True)
            item["comment"] = comment

        try:
            save_pdf_in_place(doc, merged_pdf)
        except PermissionError as exc:
            raise SystemExit(
                f"写回 PDF 失败，请先关闭正在占用文件的预览器或编辑器: {merged_pdf}"
            ) from exc
        write_json_atomic(manifest_path, manifest_data)
    finally:
        doc.close()


def list_pdf_files(folder: Path) -> list[Path]:
    return sorted(
        [
            item
            for item in folder.iterdir()
            if item.is_file() and item.name.lower().endswith(".pdf")
        ],
        key=lambda path: path.name.lower(),
    )


def extract_student_meta(pdf_path: Path) -> StudentMeta | None:
    clean_name = strip_pdf_suffixes(pdf_path.name)
    id_match = ID_PATTERN.search(clean_name)
    if not id_match:
        return None

    candidates = []
    for match in NAME_PATTERN.finditer(clean_name):
        name = match.group()
        distance = min(
            abs(match.start() - id_match.start()),
            abs(match.end() - id_match.end()),
        )
        candidates.append((distance, match.start(), name))

    if not candidates:
        return None

    _, _, name = min(candidates, key=lambda item: (item[0], item[1]))
    return StudentMeta(
        student_id=id_match.group(1),
        name=name,
        source_name=pdf_path.name,
        source_path=pdf_path.resolve(),
    )


def strip_pdf_suffixes(name: str) -> str:
    cleaned = name
    while cleaned.lower().endswith(".pdf"):
        cleaned = cleaned[:-4]
    return cleaned


def make_unique_name(name: str, seen_names: set[str]) -> str:
    base = strip_pdf_suffixes(name)
    candidate = f"{base}.pdf"
    index = 2
    while candidate.lower() in seen_names:
        candidate = f"{base}-重复{index}.pdf"
        index += 1
    return candidate


def dedupe_path(path: Path) -> Path:
    if not path.exists():
        return path
    base = strip_pdf_suffixes(path.name)
    counter = 2
    while True:
        candidate = path.with_name(f"{base}-重复{counter}.pdf")
        if not candidate.exists():
            return candidate
        counter += 1


def sanitize_filename(name: str) -> str:
    return re.sub(r'[<>:"/\\\\|?*]', "_", name)


def load_existing_comments(manifest_path: Path) -> dict[str, str]:
    if not manifest_path.is_file():
        return {}
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}

    result = {}
    for item in data.get("students", []):
        sid = item.get("student_id")
        comment = item.get("comment", "")
        if sid:
            result[str(sid)] = str(comment or "")
    return result


def write_csv(path: Path, rows: Iterable[dict[str, str]], fieldnames: list[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_json_atomic(path: Path, data: object) -> None:
    temp_path = path.with_name(f"{path.stem}.tmp{path.suffix}")
    temp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_path.replace(path)


def save_pdf_atomic(doc: fitz.Document, output_path: Path) -> None:
    temp_path = output_path.with_name(f"{output_path.stem}.tmp{output_path.suffix}")
    doc.save(temp_path, garbage=4, deflate=True)
    temp_path.replace(output_path)


def save_pdf_in_place(doc: fitz.Document, output_path: Path) -> None:
    if doc.can_save_incrementally():
        doc.saveIncr()
        return
    save_pdf_atomic(doc, output_path)


@lru_cache(maxsize=1)
def get_font_path(bold: bool = False) -> Path:
    candidates = FONT_BOLD_CANDIDATES if bold else FONT_CANDIDATES
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError("未找到可用的中文字体，请检查 C:\\Windows\\Fonts。")


@lru_cache(maxsize=16)
def load_font(size_px: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(get_font_path(bold=bold)), size=size_px)


def render_header_image(
    width_pt: float,
    height_pt: float,
    label: str,
    page_index: int,
    total_pages: int,
) -> bytes:
    width_px = max(1, int(width_pt * PNG_SCALE))
    height_px = max(1, int(height_pt * PNG_SCALE))
    image = Image.new("RGB", (width_px, height_px), color=(245, 248, 255))
    draw = ImageDraw.Draw(image)

    draw.rectangle((0, 0, width_px, height_px), outline=(173, 187, 214), width=2)
    accent_width = max(8, int(10 * PNG_SCALE))
    draw.rectangle((0, 0, accent_width, height_px), fill=(49, 91, 184))

    left_padding = accent_width + int(14 * PNG_SCALE)
    title_font = load_font(max(16, int(16 * PNG_SCALE)), bold=True)
    meta_font = load_font(max(14, int(13 * PNG_SCALE)))
    label_box = (left_padding, 0, width_px - int(160 * PNG_SCALE), height_px)
    draw.text(
        (label_box[0], int(10 * PNG_SCALE)),
        label,
        font=title_font,
        fill=(28, 44, 77),
    )

    page_text = f"第 {page_index} / {total_pages} 页"
    page_bbox = draw.textbbox((0, 0), page_text, font=meta_font)
    page_width = page_bbox[2] - page_bbox[0]
    draw.text(
        (width_px - page_width - int(18 * PNG_SCALE), int(13 * PNG_SCALE)),
        page_text,
        font=meta_font,
        fill=(68, 82, 110),
    )
    return image_to_png_bytes(image)


def render_comment_panel_image(
    width_pt: float,
    height_pt: float,
    title: str,
    comment_text: str,
) -> bytes:
    width_px = max(1, int(width_pt * PNG_SCALE))
    height_px = max(1, int(height_pt * PNG_SCALE))
    image = Image.new("RGB", (width_px, height_px), color=(255, 252, 240))
    draw = ImageDraw.Draw(image)

    draw.rounded_rectangle(
        (0, 0, width_px - 1, height_px - 1),
        radius=max(8, int(8 * PNG_SCALE)),
        fill=(255, 252, 240),
        outline=(196, 176, 113),
        width=3,
    )

    title_font = load_font(max(16, int(15 * PNG_SCALE)), bold=True)
    subtitle_font = load_font(max(13, int(12 * PNG_SCALE)))
    body_font = load_font(max(14, int(13 * PNG_SCALE)))

    padding_x = int(14 * PNG_SCALE)
    cursor_y = int(12 * PNG_SCALE)
    draw.text((padding_x, cursor_y), "批语", font=title_font, fill=(96, 69, 18))
    cursor_y += int(24 * PNG_SCALE)
    draw.text((padding_x, cursor_y), title, font=subtitle_font, fill=(125, 95, 31))
    cursor_y += int(24 * PNG_SCALE)

    divider_y = cursor_y
    draw.line(
        (padding_x, divider_y, width_px - padding_x, divider_y),
        fill=(216, 195, 140),
        width=2,
    )
    cursor_y += int(12 * PNG_SCALE)

    text_color = (54, 47, 28) if comment_text.strip() else (132, 126, 112)
    wrapped = wrap_text(
        draw=draw,
        text=comment_text.strip() or COMMENT_PLACEHOLDER,
        font=body_font,
        max_width=width_px - padding_x * 2,
    )
    draw.multiline_text(
        (padding_x, cursor_y),
        wrapped,
        font=body_font,
        fill=text_color,
        spacing=int(6 * PNG_SCALE),
    )
    return image_to_png_bytes(image)


def wrap_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont,
    max_width: int,
) -> str:
    lines: list[str] = []
    for paragraph in text.splitlines() or [""]:
        if not paragraph:
            lines.append("")
            continue

        current = ""
        for char in paragraph:
            trial = current + char
            bbox = draw.textbbox((0, 0), trial, font=font)
            if bbox[2] - bbox[0] <= max_width or not current:
                current = trial
                continue
            lines.append(current)
            current = char
        if current:
            lines.append(current)
    return "\n".join(lines)


def image_to_png_bytes(image: Image.Image) -> bytes:
    stream = io.BytesIO()
    image.save(stream, format="PNG")
    return stream.getvalue()


if __name__ == "__main__":
    main()
