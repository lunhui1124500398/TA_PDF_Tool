from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from collections import Counter


QUESTION_RE = re.compile(r"^\s*([0-9]{1,2}[.．][0-9]{1,2})(.*)$")
STUDENT_ID_RE = re.compile(r"(?<!\d)(\d{10})(?!\d)")
NAME_RE = re.compile(r"[\u4e00-\u9fff·]{2,20}")
LEFT_MARGIN_THRESHOLD = 260


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="将 OCR 结果按题号切分，输出每位学生每道题的作答文本。"
    )
    parser.add_argument("ocr_dir", type=Path, help="ocr_extract.py 输出的目录。")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("question_segments"),
        help="切分结果输出目录，默认是 ./question_segments。",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    ocr_dir = args.ocr_dir.resolve()
    if not ocr_dir.is_dir():
        raise SystemExit(f"目录不存在: {ocr_dir}")

    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    ocr_files = sorted(
        [
            path
            for path in ocr_dir.iterdir()
            if path.is_file()
            and path.name.endswith(".ocr.json")
            and path.stem.lower() != "merged_for_grading.ocr"
        ],
        key=lambda path: path.name.lower(),
    )
    if not ocr_files:
        raise SystemExit(f"目录里没有 .ocr.json 文件: {ocr_dir}")

    summary_rows = []
    for ocr_path in ocr_files:
        data = json.loads(ocr_path.read_text(encoding="utf-8"))
        segmented = segment_student_ocr(data)
        base_name = Path(data["source_name"]).stem
        json_path = output_dir / f"{base_name}.questions.json"
        md_path = output_dir / f"{base_name}.questions.md"
        json_path.write_text(json.dumps(segmented, ensure_ascii=False, indent=2), encoding="utf-8")
        md_path.write_text(render_markdown(segmented), encoding="utf-8")
        summary_rows.append(
            {
                "student_id": segmented["student_id"],
                "name": segmented["name"],
                "question_count": len(segmented["questions"]),
                "json_path": str(json_path),
                "markdown_path": str(md_path),
            }
        )
        print(
            f"{data['source_name']} -> {len(segmented['questions'])} 道题, "
            f"输出 {json_path.name}"
        )

    summary_path = output_dir / "summary.json"
    summary_path.write_text(json.dumps(summary_rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已输出汇总: {summary_path}")


def segment_student_ocr(data: dict) -> dict:
    source_name = data["source_name"]
    student_id, name = extract_student_meta(source_name)
    questions: dict[str, dict] = {}
    preface_lines: list[dict] = []
    current_question_id: str | None = None
    allowed_majors = detect_allowed_question_majors(data["pages"])

    for page in data["pages"]:
        page_index = page["page_index"]
        for block_index, block in enumerate(page["blocks"], start=1):
            text = clean_text(block["text"])
            if not text:
                continue

            found_question = split_question_header(text, block, allowed_majors)
            if found_question is not None:
                question_id, remainder = found_question
                current_question_id = question_id
                record = questions.setdefault(
                    question_id,
                    {
                        "question_id": question_id,
                        "pages": [],
                        "blocks": [],
                    },
                )
                if page_index not in record["pages"]:
                    record["pages"].append(page_index)
                if remainder:
                    record["blocks"].append(
                        make_block_record(page_index, block_index, remainder, block.get("score"))
                    )
                continue

            target = None
            if current_question_id is not None:
                target = questions[current_question_id]
                if page_index not in target["pages"]:
                    target["pages"].append(page_index)
                target["blocks"].append(
                    make_block_record(page_index, block_index, text, block.get("score"))
                )
            else:
                preface_lines.append(make_block_record(page_index, block_index, text, block.get("score")))

    question_list = []
    for question_id in sort_question_ids(questions):
        item = questions[question_id]
        item["full_text"] = "\n".join(block["text"] for block in item["blocks"])
        question_list.append(item)

    return {
        "student_id": student_id,
        "name": name,
        "source_name": source_name,
        "source_pdf": data.get("source_pdf"),
        "preface_text": "\n".join(block["text"] for block in preface_lines),
        "questions": question_list,
    }


def make_block_record(page_index: int, block_index: int, text: str, score: float | None) -> dict:
    return {
        "page_index": page_index,
        "block_index": block_index,
        "text": text,
        "score": round(float(score), 4) if score is not None else None,
    }


def split_question_header(text: str) -> tuple[str, str] | None:
    text = text.strip()
    match = QUESTION_RE.match(text)
    if not match:
        return None

    question_id = match.group(1).replace("．", ".")
    remainder = match.group(2).strip(" :：.-")
    return question_id, remainder


def split_question_header(text: str, block: dict, allowed_majors: set[int]) -> tuple[str, str] | None:
    parsed = parse_question_header(text)
    if parsed is None:
        return None

    question_id, remainder = parsed
    major = int(question_id.split(".", maxsplit=1)[0])
    if major not in allowed_majors:
        return None

    polygon = block.get("polygon") or []
    if polygon:
        min_x = min(point[0] for point in polygon)
        if min_x > LEFT_MARGIN_THRESHOLD:
            return None
    return question_id, remainder


def parse_question_header(text: str) -> tuple[str, str] | None:
    text = text.strip()
    match = QUESTION_RE.match(text)
    if not match:
        return None
    question_id = match.group(1).replace("．", ".")
    remainder = match.group(2).strip(" :：.-")
    return question_id, remainder


def detect_allowed_question_majors(pages: list[dict]) -> set[int]:
    counter: Counter[int] = Counter()
    for page in pages:
        for block in page["blocks"]:
            parsed = parse_question_header(clean_text(block["text"]))
            if parsed is None:
                continue
            question_id, _ = parsed
            polygon = block.get("polygon") or []
            if polygon and min(point[0] for point in polygon) > LEFT_MARGIN_THRESHOLD:
                continue
            major = int(question_id.split(".", maxsplit=1)[0])
            counter[major] += 1

    if not counter:
        return set()

    allowed = {major for major, count in counter.items() if count >= 2}
    if allowed:
        return allowed
    return {counter.most_common(1)[0][0]}


def clean_text(text: str) -> str:
    text = text.replace("\u3000", " ").strip()
    return re.sub(r"\s+", " ", text)


def extract_student_meta(source_name: str) -> tuple[str, str]:
    stem = Path(source_name).stem
    sid_match = STUDENT_ID_RE.search(stem)
    name_match = NAME_RE.search(stem)
    student_id = sid_match.group(1) if sid_match else ""
    name = name_match.group(0) if name_match else ""
    return student_id, name


def sort_question_ids(questions: dict[str, dict]) -> list[str]:
    def key_func(question_id: str) -> tuple[int, int]:
        left, right = question_id.split(".", maxsplit=1)
        return int(left), int(right)

    return sorted(questions.keys(), key=key_func)


def render_markdown(segmented: dict) -> str:
    lines = [
        f"# {segmented['student_id']} {segmented['name']}".rstrip(),
        "",
        f"- Source: {segmented['source_name']}",
        f"- Questions: {len(segmented['questions'])}",
        "",
    ]
    if segmented["preface_text"]:
        lines.extend(
            [
                "## Preface",
                "",
                segmented["preface_text"],
                "",
            ]
        )

    for question in segmented["questions"]:
        lines.extend(
            [
                f"## {question['question_id']}",
                "",
                f"- Pages: {', '.join(str(page) for page in question['pages'])}",
                "",
                question["full_text"],
                "",
            ]
        )
    return "\n".join(lines)


if __name__ == "__main__":
    main()
