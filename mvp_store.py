from __future__ import annotations

import csv
import io
import json
import re
from collections import defaultdict
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Literal

import fitz
from PIL import Image, ImageColor, ImageDraw, ImageFont
from pydantic import BaseModel, Field


ID_PATTERN = re.compile(r"(?<!\d)(\d{10})(?!\d)")
NAME_PATTERN = re.compile(r"[\u4e00-\u9fff路]{2,20}")
COMMENT_LINE_RE = re.compile(r"^- \[(?P<comment_id>[^\]]+)\]\s+(?P<text>.+)$")
PNG_SCALE = 2.0
IMAGE_PADDING_PT = 6.0
RECENT_COMMENT_LIMIT = 12
VALID_SYMBOL_TEXTS = {"\u2713", "\u25b3", "\u2717"}
EXPORT_TEXT_FONT = "china-s"
EXPORT_SCORE_FONTS = {
    "normal": "helv",
    "bold": "hebo",
}
DEFAULT_LIBRARY = """# 常用批语

## Calculation
- [calc.unit_missing] 思路正确，但最后一步单位遗漏。
- [calc.sigfig] 计算过程基本正确，注意有效数字。

## Logic
- [logic.clear] 思路清晰，推导完整。
- [logic.skip_step] 关键结论正确，但中间推导步骤缺失。

## Writing
- [writing.clear] 表达清楚，格式规范。
- [writing.label] 建议补充必要的符号说明或坐标标注。
"""

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


class StudentStatus(BaseModel):
    value: Literal["not_started", "in_progress", "done"]


class AnnotationStyle(BaseModel):
    color: str = "#d11a2a"
    font_size: int = Field(default=14, ge=8, le=96)
    font_weight: Literal["normal", "bold"] = "normal"


class AnnotationRecord(BaseModel):
    id: str
    type: Literal["symbol", "text", "score"]
    page_index: int = Field(ge=1)
    x: float
    y: float
    width: float | None = None
    height: float | None = None
    text: str
    style: AnnotationStyle = Field(default_factory=AnnotationStyle)
    source_comment_id: str | None = None


class StudentAnnotationState(BaseModel):
    updated_at: str
    annotations: list[AnnotationRecord] = Field(default_factory=list)


class AnnotationStore(BaseModel):
    version: int = 1
    session_name: str = ""
    students: dict[str, StudentAnnotationState] = Field(default_factory=dict)


class StudentRecord(BaseModel):
    student_id: str
    name: str
    pdf_path: str
    source_name: str
    page_count: int
    status: Literal["not_started", "in_progress", "done"] = "not_started"
    last_page: int = 1
    score_summary: str = ""
    parse_status: Literal["parsed", "fallback"] = "parsed"


class SessionState(BaseModel):
    version: int = 1
    session_name: str
    root_dir: str
    created_at: str
    current_student_index: int = 0
    filter: Literal["all", "pending", "done"] = "all"
    students: list[StudentRecord]


class CommentUsageStat(BaseModel):
    count: int = 0
    last_used_at: str = ""


class CommentUsageStore(BaseModel):
    version: int = 1
    recent: list[str] = Field(default_factory=list)
    stats: dict[str, CommentUsageStat] = Field(default_factory=dict)


class CommentEntry(BaseModel):
    comment_id: str
    category: str
    text: str


class SessionSummary(BaseModel):
    session: SessionState
    completed_count: int
    remaining_count: int
    current_student: StudentRecord | None


class SessionCreateRequest(BaseModel):
    root_dir: str
    session_name: str | None = None


class SessionCurrentUpdate(BaseModel):
    current_student_index: int | None = None
    current_student_id: str | None = None
    current_page: int | None = None


class StudentStatusUpdate(BaseModel):
    status: Literal["not_started", "in_progress", "done"]
    score_summary: str | None = None


class CommentUseRequest(BaseModel):
    comment_id: str


class ExportResult(BaseModel):
    student_id: str | None = None
    output_pdf: str | None = None
    output_dir: str | None = None
    score_csv: str | None = None
    exported_count: int = 0


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def strip_pdf_suffixes(name: str) -> str:
    cleaned = name
    while cleaned.lower().endswith(".pdf"):
        cleaned = cleaned[:-4]
    return cleaned


def sanitize_filename(name: str) -> str:
    return re.sub(r'[<>:"/\\|?*]', "_", name)


def extract_student_meta(pdf_path: Path) -> tuple[str, str, str]:
    clean_name = strip_pdf_suffixes(pdf_path.name)
    id_match = ID_PATTERN.search(clean_name)
    if not id_match:
        fallback_name = clean_name
        return f"unresolved-{sanitize_filename(clean_name)}", fallback_name, "fallback"

    candidates: list[tuple[int, int, str]] = []
    for match in NAME_PATTERN.finditer(clean_name):
        distance = min(
            abs(match.start() - id_match.start()),
            abs(match.end() - id_match.end()),
        )
        candidates.append((distance, match.start(), match.group()))

    if not candidates:
        fallback_name = clean_name
        return id_match.group(1), fallback_name, "fallback"

    _, _, name = min(candidates, key=lambda item: (item[0], item[1]))
    return id_match.group(1), name, "parsed"


def list_pdf_files(folder: Path) -> list[Path]:
    return sorted(
        [item for item in folder.iterdir() if item.is_file() and item.suffix.lower() == ".pdf"],
        key=lambda path: path.name.lower(),
    )


class MVPStore:
    def __init__(self, base_dir: Path | None = None) -> None:
        self.base_dir = (base_dir or (Path(__file__).resolve().parent / "data")).resolve()
        self.session_path = self.base_dir / "session.json"
        self.annotations_path = self.base_dir / "annotations.json"
        self.comment_library_path = self.base_dir / "comment_library.md"
        self.comment_usage_path = self.base_dir / "comment_usage.json"
        self.export_dir = self.base_dir / "exports"
        self.ensure_base_layout()

    def ensure_base_layout(self) -> None:
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.export_dir.mkdir(parents=True, exist_ok=True)
        if not self.comment_library_path.exists():
            self.comment_library_path.write_text(DEFAULT_LIBRARY, encoding="utf-8")
        if not self.comment_usage_path.exists():
            self._write_json(self.comment_usage_path, CommentUsageStore().model_dump())

    def create_session(self, request: SessionCreateRequest) -> SessionSummary:
        root_dir = Path(request.root_dir).resolve()
        if not root_dir.is_dir():
            raise FileNotFoundError(f"Homework directory not found: {root_dir}")

        pdf_files = list_pdf_files(root_dir)
        if not pdf_files:
            raise FileNotFoundError(f"No PDF files found in: {root_dir}")

        students: list[StudentRecord] = []
        for pdf_path in pdf_files:
            student_id, name, parse_status = extract_student_meta(pdf_path)
            with fitz.open(pdf_path) as doc:
                page_count = doc.page_count
            students.append(
                StudentRecord(
                    student_id=student_id,
                    name=name,
                    pdf_path=str(pdf_path),
                    source_name=pdf_path.name,
                    page_count=page_count,
                    parse_status=parse_status,
                )
            )

        students.sort(key=lambda item: (item.student_id, item.name, item.source_name.lower()))
        session_name = request.session_name or f"{sanitize_filename(root_dir.name)}-{datetime.now():%Y%m%d-%H%M%S}"
        session = SessionState(
            session_name=session_name,
            root_dir=str(root_dir),
            created_at=now_iso(),
            students=students,
        )
        annotations = AnnotationStore(session_name=session_name)
        self.save_session(session)
        self.save_annotations(annotations)
        self.ensure_base_layout()
        return self.session_summary(session)

    def load_session(self) -> SessionState:
        if not self.session_path.exists():
            raise FileNotFoundError("Session has not been created yet.")
        return SessionState.model_validate_json(self.session_path.read_text(encoding="utf-8"))

    def save_session(self, session: SessionState) -> None:
        self._write_json(self.session_path, session.model_dump())

    def session_summary(self, session: SessionState | None = None) -> SessionSummary:
        current_session = session or self.load_session()
        completed_count = sum(1 for item in current_session.students if item.status == "done")
        remaining_count = len(current_session.students) - completed_count
        current_student = None
        if current_session.students:
            index = max(0, min(current_session.current_student_index, len(current_session.students) - 1))
            current_student = current_session.students[index]
        return SessionSummary(
            session=current_session,
            completed_count=completed_count,
            remaining_count=remaining_count,
            current_student=current_student,
        )

    def update_current(self, payload: SessionCurrentUpdate) -> SessionSummary:
        session = self.load_session()
        if payload.current_student_id is not None:
            try:
                target_index = next(
                    idx for idx, item in enumerate(session.students) if item.student_id == payload.current_student_id
                )
            except StopIteration as exc:
                raise KeyError(f"Unknown student id: {payload.current_student_id}") from exc
            session.current_student_index = target_index
        elif payload.current_student_index is not None:
            if not 0 <= payload.current_student_index < len(session.students):
                raise IndexError("Current student index is out of range.")
            session.current_student_index = payload.current_student_index

        if payload.current_page is not None and session.students:
            current_student = session.students[session.current_student_index]
            current_student.last_page = max(1, min(payload.current_page, current_student.page_count))
            if current_student.status == "not_started":
                current_student.status = "in_progress"

        self.save_session(session)
        return self.session_summary(session)

    def update_student_status(self, student_id: str, payload: StudentStatusUpdate) -> StudentRecord:
        session = self.load_session()
        student = self._get_student(session, student_id)
        student.status = payload.status
        if payload.score_summary is not None:
            student.score_summary = payload.score_summary
        self.save_session(session)
        return student

    def load_annotations(self) -> AnnotationStore:
        if not self.annotations_path.exists():
            return AnnotationStore()
        store = AnnotationStore.model_validate_json(self.annotations_path.read_text(encoding="utf-8"))
        normalized_store, changed = normalize_annotation_store(store)
        if changed:
            self.save_annotations(normalized_store)
        return normalized_store

    def save_annotations(self, store: AnnotationStore) -> None:
        normalized_store, _ = normalize_annotation_store(store)
        self._write_json(self.annotations_path, normalized_store.model_dump())

    def get_student_annotations(self, student_id: str) -> StudentAnnotationState:
        store = self.load_annotations()
        return store.students.get(student_id, StudentAnnotationState(updated_at="", annotations=[]))

    def replace_student_annotations(
        self,
        student_id: str,
        annotations: list[AnnotationRecord],
    ) -> StudentAnnotationState:
        session = self.load_session()
        self._get_student(session, student_id)
        store = self.load_annotations()
        normalized_annotations = [normalize_annotation_record(item) for item in annotations]
        store.students[student_id] = StudentAnnotationState(updated_at=now_iso(), annotations=normalized_annotations)
        self.save_annotations(store)

        score_summary = self._derive_score_summary(normalized_annotations)
        if score_summary is not None:
            student = self._get_student(session, student_id)
            student.score_summary = score_summary
            if student.status == "not_started":
                student.status = "in_progress"
            self.save_session(session)
        return store.students[student_id]

    def load_comment_library(self) -> list[CommentEntry]:
        self.ensure_base_layout()
        entries: list[CommentEntry] = []
        current_category = "Uncategorized"
        for raw_line in self.comment_library_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if line.startswith("## "):
                current_category = line[3:].strip() or current_category
                continue
            match = COMMENT_LINE_RE.match(line)
            if not match:
                continue
            entries.append(
                CommentEntry(
                    comment_id=match.group("comment_id"),
                    category=current_category,
                    text=match.group("text"),
                )
            )
        return entries

    def load_recent_comments(self) -> list[CommentEntry]:
        usage = self._load_comment_usage()
        library_by_id = {entry.comment_id: entry for entry in self.load_comment_library()}
        result: list[CommentEntry] = []
        for comment_id in usage.recent:
            entry = library_by_id.get(comment_id)
            if entry is not None:
                result.append(entry)
        return result

    def mark_comment_used(self, comment_id: str) -> CommentUsageStore:
        usage = self._load_comment_usage()
        usage.recent = [item for item in usage.recent if item != comment_id]
        usage.recent.insert(0, comment_id)
        usage.recent = usage.recent[:RECENT_COMMENT_LIMIT]
        stat = usage.stats.get(comment_id, CommentUsageStat())
        stat.count += 1
        stat.last_used_at = now_iso()
        usage.stats[comment_id] = stat
        self._write_json(self.comment_usage_path, usage.model_dump())
        return usage

    def export_current(self, student_id: str) -> ExportResult:
        session = self.load_session()
        student = self._get_student(session, student_id)
        output_pdf = self._export_student_pdf(student)
        return ExportResult(student_id=student.student_id, output_pdf=str(output_pdf), exported_count=1)

    def export_all(self) -> ExportResult:
        session = self.load_session()
        output_dir = Path(session.root_dir) / "graded"
        output_dir.mkdir(parents=True, exist_ok=True)

        exported_count = 0
        for student in session.students:
            self._export_student_pdf(student)
            exported_count += 1

        score_csv = output_dir / "scores.csv"
        with score_csv.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["student_id", "name", "status", "score_summary", "pdf_path"])
            for student in session.students:
                writer.writerow(
                    [student.student_id, student.name, student.status, student.score_summary, student.pdf_path]
                )

        return ExportResult(output_dir=str(output_dir), score_csv=str(score_csv), exported_count=exported_count)

    def _export_student_pdf(self, student: StudentRecord) -> Path:
        annotations = self.get_student_annotations(student.student_id)
        output_dir = Path(self.load_session().root_dir) / "graded"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / sanitize_filename(f"{student.student_id}-{student.name}.pdf")

        grouped: dict[int, list[AnnotationRecord]] = defaultdict(list)
        for item in annotations.annotations:
            grouped[item.page_index].append(item)

        with fitz.open(student.pdf_path) as doc:
            for page_index, items in grouped.items():
                if not 1 <= page_index <= doc.page_count:
                    continue
                page = doc[page_index - 1]
                for item in items:
                    self._draw_annotation(page, item)
            doc.ez_save(output_path)
        return output_path

    def _draw_annotation(self, page: fitz.Page, annotation: AnnotationRecord) -> None:
        annotation = normalize_annotation_record(annotation)
        if annotation.type == "text":
            self._draw_text_annotation(page, annotation)
            return
        if annotation.type == "score":
            self._draw_score_annotation(page, annotation)
            return

        stream, width_pt, height_pt = render_annotation_image(annotation)
        top_y = page.rect.height - annotation.y
        rect = fitz.Rect(annotation.x, top_y, annotation.x + width_pt, top_y + height_pt)
        page.insert_image(rect, stream=stream, overlay=True)

    def _draw_text_annotation(self, page: fitz.Page, annotation: AnnotationRecord) -> None:
        layout = measure_text_layout(annotation)
        top_y = page.rect.height - annotation.y
        height_pt = resolve_textbox_height(annotation, layout)
        rect = fitz.Rect(annotation.x, top_y, annotation.x + layout.width_pt, top_y + height_pt)
        page.insert_textbox(
            rect,
            layout.text,
            fontsize=annotation.style.font_size,
            fontname=EXPORT_TEXT_FONT,
            color=pdf_color(annotation.style.color),
            lineheight=layout.line_height,
            overlay=True,
        )

    def _draw_score_annotation(self, page: fitz.Page, annotation: AnnotationRecord) -> None:
        top_y = page.rect.height - annotation.y
        fontname = export_score_font_name(annotation)
        page.insert_text(
            fitz.Point(annotation.x, top_y + annotation.style.font_size),
            annotation.text,
            fontsize=annotation.style.font_size,
            fontname=fontname,
            color=pdf_color(annotation.style.color),
            overlay=True,
        )

    def _load_comment_usage(self) -> CommentUsageStore:
        self.ensure_base_layout()
        return CommentUsageStore.model_validate_json(self.comment_usage_path.read_text(encoding="utf-8"))

    def _derive_score_summary(self, annotations: list[AnnotationRecord]) -> str | None:
        scores = [item for item in annotations if item.type == "score" and item.text.strip()]
        if not scores:
            return None
        scores.sort(key=lambda item: (item.page_index, item.y, item.x))
        return scores[-1].text.strip()

    def _get_student(self, session: SessionState, student_id: str) -> StudentRecord:
        for item in session.students:
            if item.student_id == student_id:
                return item
        raise KeyError(f"Unknown student id: {student_id}")

    def _write_json(self, path: Path, data: object) -> None:
        temp_path = path.with_name(f"{path.stem}.tmp{path.suffix}")
        temp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        temp_path.replace(path)


@lru_cache(maxsize=1)
def get_font_path(bold: bool = False) -> Path:
    candidates = FONT_BOLD_CANDIDATES if bold else FONT_CANDIDATES
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError("No suitable Chinese font was found under C:\\Windows\\Fonts.")


@lru_cache(maxsize=64)
def load_font(size_px: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(get_font_path(bold=bold)), size=size_px)


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


def is_valid_symbol_text(text: str) -> bool:
    return text.strip() in VALID_SYMBOL_TEXTS


def normalize_annotation_record(annotation: AnnotationRecord) -> AnnotationRecord:
    normalized = annotation.model_copy(deep=True)
    normalized.text = normalized.text or ""

    if normalized.type == "symbol" and not is_valid_symbol_text(normalized.text):
        normalized.type = "text"

    if normalized.type == "symbol":
        normalized.text = normalized.text.strip() or normalized.text
        if normalized.width is not None and normalized.width <= 0:
            normalized.width = None
        if normalized.height is not None and normalized.height <= 0:
            normalized.height = None
        return normalized

    if normalized.type == "text":
        if normalized.width is None or normalized.width <= 0:
            normalized.width = max(normalized.style.font_size * 8, 160)
        if normalized.height is not None and normalized.height <= 0:
            normalized.height = None
        return normalized

    if normalized.width is None or normalized.width <= 0:
        normalized.width = max(normalized.style.font_size * 3.5, 90)
    if normalized.height is None or normalized.height <= 0:
        normalized.height = max(normalized.style.font_size * 1.8, 40)
    return normalized


def normalize_annotation_store(store: AnnotationStore) -> tuple[AnnotationStore, bool]:
    changed = False
    normalized_store = store.model_copy(deep=True)

    for student_id, state in normalized_store.students.items():
        normalized_annotations: list[AnnotationRecord] = []
        for annotation in state.annotations:
            normalized = normalize_annotation_record(annotation)
            normalized_annotations.append(normalized)
            if normalized.model_dump() != annotation.model_dump():
                changed = True
        normalized_store.students[student_id] = StudentAnnotationState(
            updated_at=state.updated_at,
            annotations=normalized_annotations,
        )

    return normalized_store, changed


class TextLayout(BaseModel):
    text: str
    width_pt: float
    height_pt: float
    line_height: float


def measure_text_layout(annotation: AnnotationRecord) -> TextLayout:
    scale = PNG_SCALE
    padding_px = max(4, int(IMAGE_PADDING_PT * scale))
    font_size_px = max(12, int(annotation.style.font_size * scale))
    font = load_font(font_size_px, bold=annotation.style.font_weight == "bold")
    scratch = Image.new("RGBA", (16, 16), (255, 255, 255, 0))
    draw = ImageDraw.Draw(scratch)
    spacing_px = max(4, int(3 * scale))

    if annotation.type == "text":
        width_pt = annotation.width or max(annotation.style.font_size * 8, 160)
        max_width_px = max(40, int(width_pt * scale) - padding_px * 2)
        wrapped = wrap_text(draw, annotation.text, font, max_width_px)
        line_count = max(1, wrapped.count("\n") + 1)
        line_height = 1.2
        content_height_pt = line_count * annotation.style.font_size * line_height + IMAGE_PADDING_PT * 2
        height_pt = max(annotation.height or 0, content_height_pt)
        return TextLayout(
            text=wrapped,
            width_pt=width_pt,
            height_pt=height_pt,
            line_height=line_height,
        )

    bbox = draw.textbbox((0, 0), annotation.text, font=font)
    intrinsic_width_pt = (bbox[2] - bbox[0] + padding_px * 2) / scale
    intrinsic_height_pt = (bbox[3] - bbox[1] + padding_px * 2) / scale
    width_pt = max(annotation.width or 0, intrinsic_width_pt)
    height_pt = max(annotation.height or 0, intrinsic_height_pt)
    return TextLayout(
        text=annotation.text,
        width_pt=width_pt,
        height_pt=height_pt,
        line_height=1.0,
    )


def pdf_color(color: str) -> tuple[float, float, float]:
    red, green, blue = ImageColor.getrgb(color)
    return (red / 255, green / 255, blue / 255)


def export_score_font_name(annotation: AnnotationRecord) -> str:
    if any(ord(char) > 127 for char in annotation.text):
        return EXPORT_TEXT_FONT
    return EXPORT_SCORE_FONTS.get(annotation.style.font_weight, "helv")


def resolve_textbox_height(annotation: AnnotationRecord, layout: TextLayout) -> float:
    height_pt = layout.height_pt
    step = max(annotation.style.font_size * layout.line_height, 10)
    for _ in range(8):
        if textbox_fits(annotation, layout, height_pt):
            return height_pt
        height_pt += step
    return height_pt


def textbox_fits(annotation: AnnotationRecord, layout: TextLayout, height_pt: float) -> bool:
    doc = fitz.open()
    try:
        page = doc.new_page(width=max(layout.width_pt + 20, 200), height=max(height_pt + 20, 200))
        rect = fitz.Rect(10, 10, 10 + layout.width_pt, 10 + height_pt)
        result = page.insert_textbox(
            rect,
            layout.text,
            fontsize=annotation.style.font_size,
            fontname=EXPORT_TEXT_FONT,
            color=pdf_color(annotation.style.color),
            lineheight=layout.line_height,
            overlay=True,
        )
        return result >= 0
    finally:
        doc.close()


def render_annotation_image(annotation: AnnotationRecord) -> tuple[bytes, float, float]:
    scale = PNG_SCALE
    padding_px = max(4, int(IMAGE_PADDING_PT * scale))
    font_size_px = max(12, int(annotation.style.font_size * scale))
    font = load_font(font_size_px, bold=annotation.style.font_weight == "bold")

    scratch = Image.new("RGBA", (16, 16), (255, 255, 255, 0))
    draw = ImageDraw.Draw(scratch)
    fill = ImageColor.getrgb(annotation.style.color)

    if annotation.type == "text":
        width_pt = annotation.width or max(annotation.style.font_size * 8, 160)
        max_width_px = max(40, int(width_pt * scale) - padding_px * 2)
        wrapped = wrap_text(draw, annotation.text, font, max_width_px)
        bbox = draw.multiline_textbbox((0, 0), wrapped, font=font, spacing=max(4, int(3 * scale)))
        text_width_px = bbox[2] - bbox[0]
        text_height_px = bbox[3] - bbox[1]
        height_pt = annotation.height or ((text_height_px + padding_px * 2) / scale)
        image = Image.new(
            "RGBA",
            (max(1, int(width_pt * scale)), max(1, int(height_pt * scale))),
            (255, 255, 255, 0),
        )
        draw = ImageDraw.Draw(image)
        draw.multiline_text(
            (padding_px, padding_px),
            wrapped,
            font=font,
            fill=fill,
            spacing=max(4, int(3 * scale)),
        )
        return image_to_png_bytes(image), width_pt, height_pt

    if annotation.type == "symbol":
        return render_symbol_image(annotation, fill)

    bbox = draw.textbbox((0, 0), annotation.text, font=font)
    text_width_px = bbox[2] - bbox[0]
    text_height_px = bbox[3] - bbox[1]
    width_pt = annotation.width or ((text_width_px + padding_px * 2) / scale)
    height_pt = annotation.height or ((text_height_px + padding_px * 2) / scale)
    image = Image.new(
        "RGBA",
        (max(1, int(width_pt * scale)), max(1, int(height_pt * scale))),
        (255, 255, 255, 0),
    )
    draw = ImageDraw.Draw(image)
    draw.text((padding_px, padding_px), annotation.text, font=font, fill=fill)
    return image_to_png_bytes(image), width_pt, height_pt


def render_symbol_image(annotation: AnnotationRecord, fill: tuple[int, int, int]) -> tuple[bytes, float, float]:
    scale = PNG_SCALE
    width_pt = annotation.width or max(annotation.style.font_size * 1.8, 24)
    height_pt = annotation.height or max(annotation.style.font_size * 1.8, 24)
    image = Image.new(
        "RGBA",
        (max(1, int(width_pt * scale)), max(1, int(height_pt * scale))),
        (255, 255, 255, 0),
    )
    draw = ImageDraw.Draw(image)
    stroke_width = max(3, int(max(image.size) * 0.08))
    draw_symbol(draw, annotation.text, image.size[0], image.size[1], fill, stroke_width)
    return image_to_png_bytes(image), width_pt, height_pt


def draw_symbol(
    draw: ImageDraw.ImageDraw,
    text: str,
    width_px: int,
    height_px: int,
    fill: tuple[int, int, int],
    stroke_width: int,
) -> None:
    if text == "✓":
        points = [
            (int(width_px * 0.18), int(height_px * 0.56)),
            (int(width_px * 0.42), int(height_px * 0.82)),
            (int(width_px * 0.84), int(height_px * 0.18)),
        ]
        draw.line(points, fill=fill, width=stroke_width)
        return

    if text == "✗":
        draw.line(
            [
                (int(width_px * 0.22), int(height_px * 0.2)),
                (int(width_px * 0.78), int(height_px * 0.8)),
            ],
            fill=fill,
            width=stroke_width,
        )
        draw.line(
            [
                (int(width_px * 0.78), int(height_px * 0.2)),
                (int(width_px * 0.22), int(height_px * 0.8)),
            ],
            fill=fill,
            width=stroke_width,
        )
        return

    if text == "△":
        points = [
            (int(width_px * 0.5), int(height_px * 0.14)),
            (int(width_px * 0.18), int(height_px * 0.82)),
            (int(width_px * 0.82), int(height_px * 0.82)),
            (int(width_px * 0.5), int(height_px * 0.14)),
        ]
        draw.line(points, fill=fill, width=max(2, stroke_width - 1))
        return

    font_size_px = max(12, int(min(width_px, height_px) * 0.7))
    font = load_font(font_size_px, bold=True)
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width_px = bbox[2] - bbox[0]
    text_height_px = bbox[3] - bbox[1]
    draw.text(
        ((width_px - text_width_px) / 2, (height_px - text_height_px) / 2),
        text,
        font=font,
        fill=fill,
    )


def image_to_png_bytes(image: Image.Image) -> bytes:
    stream = io.BytesIO()
    image.save(stream, format="PNG")
    return stream.getvalue()
