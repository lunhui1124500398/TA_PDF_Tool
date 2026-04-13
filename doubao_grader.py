from __future__ import annotations

import argparse
import base64
import io
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from zipfile import ZipFile

import fitz
import requests
import xml.etree.ElementTree as ET
from PIL import Image


DOCX_NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
ARK_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
PROMPT_START_PATTERNS = [
    r"How many grams of ",
    r"25\.00 mL formic acid",
    r"Titrate a weak base",
    r"A sample was analyzed by the Kjeldahl method",
    r"Write one experimental design",
    r"A 0\.1000 mol",
    r"Titrate 20\.00 mL of 0\.1 M NaOH",
    r"Calculate the pH of the following standard solutions",
    r"Weigh a 1\.000 g sample",
]
PROMPT_START_RE = re.compile("|".join(f"(?:{pattern})" for pattern in PROMPT_START_PATTERNS))
ID_PATTERN = re.compile(r"(?<!\d)(\d{10})(?!\d)")
NAME_PATTERN = re.compile(r"[\u4e00-\u9fff·]{2,20}")


@dataclass
class QuestionRef:
    question_id: str
    prompt: str
    reference_answer: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="豆包视觉判卷原型：可先审答案，再批学生。"
    )
    parser.add_argument(
        "student_input",
        type=Path,
        nargs="?",
        help="单个学生 PDF，或包含多个 PDF 的目录。若只检查答案，可不传。",
    )
    parser.add_argument(
        "--answer-docx",
        type=Path,
        default=Path(r".\HW-4&5\Answers to HW-4 - revised.docx"),
        help="答案 docx 路径，默认使用 HW-4 答案。",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("doubao_grading"),
        help="输出目录，默认是 ./doubao_grading。",
    )
    parser.add_argument(
        "--endpoint-id",
        default=os.getenv("ARK_VISION_ENDPOINT_ID", ""),
        help="豆包视觉模型 Endpoint ID，也可通过环境变量 ARK_VISION_ENDPOINT_ID 提供。",
    )
    parser.add_argument(
        "--api-key",
        default=os.getenv("ARK_API_KEY", ""),
        help="ARK API Key，也可通过环境变量 ARK_API_KEY 提供。",
    )
    parser.add_argument(
        "--base-url",
        default=os.getenv("ARK_BASE_URL", ARK_BASE_URL),
        help="方舟 API Base URL，默认 https://ark.cn-beijing.volces.com/api/v3。",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=4,
        help="最多发送前 N 页到模型，默认 4。",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.2,
        help="推理温度，默认 0.2。",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只生成答案结构和请求体，不实际请求 API。",
    )
    parser.add_argument(
        "--review-answer-key",
        action="store_true",
        help="先让豆包检查答案文档本身是否有错误、冲突或遗漏。",
    )
    parser.add_argument(
        "--review-answer-key-only",
        action="store_true",
        help="只检查答案文档，不批学生。",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    answer_docx = args.answer_docx.resolve()
    if not answer_docx.is_file():
        raise SystemExit(f"答案文档不存在: {answer_docx}")

    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    answer_key = parse_hw4_answer_docx(answer_docx)
    answer_key_path = output_dir / "answer_key.hw4.json"
    answer_key_path.write_text(
        json.dumps([question.__dict__ for question in answer_key], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"已生成参考答案结构: {answer_key_path}")

    if args.review_answer_key or args.review_answer_key_only:
        review_answer_key(
            answer_key=answer_key,
            output_dir=output_dir,
            base_url=args.base_url.rstrip("/"),
            endpoint_id=args.endpoint_id,
            api_key=args.api_key,
            temperature=args.temperature,
            dry_run=args.dry_run,
        )

    if args.review_answer_key_only:
        return

    if args.student_input is None:
        raise SystemExit("未提供 student_input。若只检查答案，请使用 --review-answer-key-only。")

    student_paths = collect_student_pdfs(args.student_input)
    if not student_paths:
        raise SystemExit(f"没有找到学生 PDF: {args.student_input}")

    for pdf_path in student_paths:
        process_student_pdf(
            pdf_path=pdf_path.resolve(),
            answer_key=answer_key,
            output_dir=output_dir,
            base_url=args.base_url.rstrip("/"),
            endpoint_id=args.endpoint_id,
            api_key=args.api_key,
            max_pages=args.max_pages,
            temperature=args.temperature,
            dry_run=args.dry_run,
        )


def collect_student_pdfs(student_input: Path) -> list[Path]:
    student_input = student_input.resolve()
    if student_input.is_file():
        return [student_input] if student_input.suffix.lower() == ".pdf" else []

    if student_input.is_dir():
        return sorted(
            [
                path
                for path in student_input.iterdir()
                if path.is_file()
                and path.suffix.lower() == ".pdf"
                and path.stem.lower() != "merged_for_grading"
            ],
            key=lambda path: path.name.lower(),
        )
    return []


def parse_hw4_answer_docx(docx_path: Path) -> list[QuestionRef]:
    paragraphs = extract_docx_paragraphs(docx_path)
    blocks = split_hw4_blocks(paragraphs)
    return [
        QuestionRef(
            question_id=f"4.{index}",
            prompt="\n".join(block["prompt"]).strip(),
            reference_answer="\n".join(block["answer"]).strip(),
        )
        for index, block in enumerate(blocks, start=1)
    ]


def extract_docx_paragraphs(docx_path: Path) -> list[str]:
    with ZipFile(docx_path) as zf:
        xml = zf.read("word/document.xml")
    root = ET.fromstring(xml)
    paragraphs = []
    for p in root.findall(".//w:p", DOCX_NS):
        texts = [t.text for t in p.findall(".//w:t", DOCX_NS) if t.text]
        line = "".join(texts).strip()
        if line:
            paragraphs.append(line)
    return paragraphs


def split_hw4_blocks(paragraphs: list[str]) -> list[dict[str, list[str]]]:
    content = [line for line in paragraphs if not line.startswith("Answer to HW-4") and not re.match(r"\d{4}\.\d{2}\.\d{2}", line)]
    starts = [
        index
        for index, line in enumerate(content)
        if PROMPT_START_RE.match(line)
    ]
    if len(starts) != 10:
        raise SystemExit(
            f"答案文档题目切分失败，期望识别 10 题，实际识别 {len(starts)} 个起点。"
        )

    blocks = []
    for i, start in enumerate(starts):
        end = starts[i + 1] if i + 1 < len(starts) else len(content)
        block_lines = content[start:end]
        prompt_lines, answer_lines = split_prompt_and_answer(block_lines)
        blocks.append({"prompt": prompt_lines, "answer": answer_lines})
    return blocks


def split_prompt_and_answer(block_lines: list[str]) -> tuple[list[str], list[str]]:
    prompt_lines = [block_lines[0]]
    answer_start = None
    for idx in range(1, len(block_lines)):
        line = block_lines[idx]
        if looks_like_answer_start(line):
            answer_start = idx
            break
        prompt_lines.append(line)

    if answer_start is None:
        return prompt_lines, []
    return prompt_lines, block_lines[answer_start:]


def looks_like_answer_start(line: str) -> bool:
    answer_markers = (
        "CBE",
        "Let the amount",
        "where ",
        "The stoichiometric ratio",
        "Assume the weak base",
        "Ka of ",
        "At SP",
        "Be aware",
        "Take a sample",
        "According to ",
        "Same as above",
        "Borax dissociates",
        "therefore",
        "Assume the titration",
    )
    return line.startswith(answer_markers)


def review_answer_key(
    answer_key: list[QuestionRef],
    output_dir: Path,
    base_url: str,
    endpoint_id: str,
    api_key: str,
    temperature: float,
    dry_run: bool,
) -> None:
    payload = build_answer_review_payload(
        endpoint_id=endpoint_id,
        answer_key=answer_key,
        temperature=temperature,
    )
    request_path = output_dir / "answer_review.request.json"
    request_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已生成答案自检请求体: {request_path}")

    if dry_run or not api_key or not endpoint_id:
        print("答案自检 dry-run 完成。如需真实请求，请提供 ARK_API_KEY 和 ARK_VISION_ENDPOINT_ID。")
        return

    response_json = call_ark_chat_completions(base_url, api_key, payload)
    raw_path = output_dir / "answer_review.raw_response.json"
    raw_path.write_text(json.dumps(response_json, ensure_ascii=False, indent=2), encoding="utf-8")

    parsed = parse_model_json_response(response_json)
    result_path = output_dir / "answer_review.result.json"
    result_path.write_text(json.dumps(parsed, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path = output_dir / "answer_review.result.md"
    markdown_path.write_text(render_answer_review_markdown(parsed), encoding="utf-8")
    print(f"已输出答案自检结果: {result_path}")


def process_student_pdf(
    pdf_path: Path,
    answer_key: list[QuestionRef],
    output_dir: Path,
    base_url: str,
    endpoint_id: str,
    api_key: str,
    max_pages: int,
    temperature: float,
    dry_run: bool,
) -> None:
    student_dir = output_dir / pdf_path.stem
    student_dir.mkdir(parents=True, exist_ok=True)

    student_meta = extract_student_meta(pdf_path.name)
    page_images = render_pdf_pages(pdf_path, student_dir / "pages", max_pages=max_pages)
    payload = build_chat_payload(
        endpoint_id=endpoint_id,
        student_meta=student_meta,
        answer_key=answer_key,
        page_images=page_images,
        temperature=temperature,
    )
    (student_dir / "request_payload.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"已生成请求体: {student_dir / 'request_payload.json'}")

    if dry_run or not api_key or not endpoint_id:
        print(
            f"{pdf_path.name}: dry-run 完成。"
            "如需真实请求，请提供 ARK_API_KEY 和 ARK_VISION_ENDPOINT_ID。"
        )
        return

    response_json = call_ark_chat_completions(base_url, api_key, payload)
    (student_dir / "raw_response.json").write_text(
        json.dumps(response_json, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    parsed = parse_model_json_response(response_json)
    (student_dir / "grading_result.json").write_text(
        json.dumps(parsed, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (student_dir / "grading_result.md").write_text(
        render_grading_markdown(parsed, pdf_path.name),
        encoding="utf-8",
    )
    print(f"已输出判卷结果: {student_dir / 'grading_result.json'}")


def extract_student_meta(filename: str) -> dict[str, str]:
    stem = Path(filename).stem
    sid_match = ID_PATTERN.search(stem)
    name_match = NAME_PATTERN.search(stem)
    return {
        "student_id": sid_match.group(1) if sid_match else "",
        "name": name_match.group(0) if name_match else "",
    }


def render_pdf_pages(pdf_path: Path, page_dir: Path, max_pages: int) -> list[dict[str, str]]:
    page_dir.mkdir(parents=True, exist_ok=True)
    page_images = []
    with fitz.open(pdf_path) as doc:
        total_pages = min(doc.page_count, max_pages)
        for page_index in range(total_pages):
            page = doc[page_index]
            pix = page.get_pixmap(matrix=fitz.Matrix(1.6, 1.6), alpha=False)
            image = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
            image_path = page_dir / f"page_{page_index + 1:03d}.jpg"
            image.save(image_path, format="JPEG", quality=82, optimize=True)
            page_images.append(
                {
                    "page_index": page_index + 1,
                    "image_path": str(image_path),
                    "data_url": image_path_to_data_url(image_path),
                }
            )
    return page_images


def image_path_to_data_url(image_path: Path) -> str:
    encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"


def build_chat_payload(
    endpoint_id: str,
    student_meta: dict[str, str],
    answer_key: list[QuestionRef],
    page_images: list[dict[str, str]],
    temperature: float,
) -> dict[str, Any]:
    answer_key_text = json.dumps(
        [question.__dict__ for question in answer_key],
        ensure_ascii=False,
        indent=2,
    )
    prompt = (
        "You are grading an Analytical Chemistry homework.\n"
        "The answer key only covers HW-4 questions 4.1 to 4.10.\n"
        "Please read the student's uploaded pages directly. Do not rely on OCR from the client.\n"
        "Only evaluate questions 4.1 to 4.10. Ignore any HW-5 content or unrelated pages.\n"
        "For each question, give a short student_answer_summary, list the main issues, and list cautions or things to check.\n"
        "Keep feedback concise. Do not write long explanations.\n"
        "Return valid JSON only.\n\n"
        f"Student metadata:\n{json.dumps(student_meta, ensure_ascii=False)}\n\n"
        f"Answer key:\n{answer_key_text}\n\n"
        "Return JSON with this shape:\n"
        "{\n"
        '  "student_id": "string",\n'
        '  "name": "string",\n'
        '  "assignment": "HW-4",\n'
        '  "questions": [\n'
        "    {\n"
        '      "question_id": "4.1",\n'
        '      "attempted": true,\n'
        '      "student_answer_summary": "one or two short sentences",\n'
        '      "issues": ["short issue 1", "short issue 2"],\n'
        '      "cautions": ["short caution"],\n'
        '      "judgement": "correct|partial|wrong|unclear"\n'
        "    }\n"
        "  ],\n"
        '  "overall_comment": "one short paragraph about main problems and what to pay attention to"\n'
        "}\n"
    )

    content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
    for item in page_images:
        content.append(
            {
                "type": "text",
                "text": f"Student page {item['page_index']}",
            }
        )
        content.append(
            {
                "type": "image_url",
                "image_url": {"url": item["data_url"]},
            }
        )

    return {
        "model": endpoint_id,
        "temperature": temperature,
        "max_tokens": 4000,
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "system",
                "content": "You are a careful teaching assistant. Be concise and faithful to the answer key.",
            },
            {
                "role": "user",
                "content": content,
            },
        ],
    }


def build_answer_review_payload(
    endpoint_id: str,
    answer_key: list[QuestionRef],
    temperature: float,
) -> dict[str, Any]:
    answer_key_text = json.dumps(
        [question.__dict__ for question in answer_key],
        ensure_ascii=False,
        indent=2,
    )
    prompt = (
        "You are checking a homework answer key before it is used for grading.\n"
        "Please review the answer key for possible issues such as:\n"
        "- obvious calculation mistakes\n"
        "- contradiction between prompt and answer\n"
        "- question-answer mismatch\n"
        "- missing key steps or missing conclusion\n"
        "- ambiguous or unsafe grading guidance\n"
        "Be conservative: only flag something when there is a clear reason.\n"
        "Return valid JSON only.\n\n"
        f"Answer key:\n{answer_key_text}\n\n"
        "Return JSON with this shape:\n"
        "{\n"
        '  "assignment": "HW-4",\n'
        '  "overall_status": "ok|needs_review",\n'
        '  "summary": "one short paragraph",\n'
        '  "questions": [\n'
        "    {\n"
        '      "question_id": "4.1",\n'
        '      "status": "ok|needs_review",\n'
        '      "issues": ["short issue"],\n'
        '      "suggestion": "short suggestion"\n'
        "    }\n"
        "  ]\n"
        "}\n"
    )
    return {
        "model": endpoint_id,
        "temperature": temperature,
        "max_tokens": 2500,
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "system",
                "content": "You are a careful chemistry TA checking an answer key. Be concise and cautious.",
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
    }


def call_ark_chat_completions(base_url: str, api_key: str, payload: dict[str, Any]) -> dict[str, Any]:
    response = requests.post(
        f"{base_url}/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=600,
    )
    response.raise_for_status()
    return response.json()


def parse_model_json_response(response_json: dict[str, Any]) -> dict[str, Any]:
    content = response_json["choices"][0]["message"]["content"]
    if isinstance(content, list):
        content = "\n".join(
            item.get("text", "") if isinstance(item, dict) else str(item) for item in content
        )
    content = str(content).strip()
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", content, re.S)
        if not match:
            raise
        return json.loads(match.group(0))


def render_grading_markdown(result: dict[str, Any], source_name: str) -> str:
    lines = [
        f"# {result.get('student_id', '')} {result.get('name', '')}".rstrip(),
        "",
        f"- Source: {source_name}",
        f"- Assignment: {result.get('assignment', 'HW-4')}",
        "",
        "## Overall",
        "",
        result.get("overall_comment", ""),
        "",
    ]
    for question in result.get("questions", []):
        lines.extend(
            [
                f"## {question.get('question_id', '')}",
                "",
                f"- Attempted: {question.get('attempted')}",
                f"- Judgement: {question.get('judgement', '')}",
                f"- Student Answer Summary: {question.get('student_answer_summary', '')}",
                f"- Issues: {'; '.join(question.get('issues', [])) if question.get('issues') else ''}",
                f"- Cautions: {'; '.join(question.get('cautions', [])) if question.get('cautions') else ''}",
                "",
            ]
        )
    return "\n".join(lines)


def render_answer_review_markdown(result: dict[str, Any]) -> str:
    lines = [
        "# Answer Key Review",
        "",
        f"- Assignment: {result.get('assignment', 'HW-4')}",
        f"- Overall Status: {result.get('overall_status', '')}",
        "",
        "## Summary",
        "",
        result.get("summary", ""),
        "",
    ]
    for question in result.get("questions", []):
        lines.extend(
            [
                f"## {question.get('question_id', '')}",
                "",
                f"- Status: {question.get('status', '')}",
                f"- Issues: {'; '.join(question.get('issues', [])) if question.get('issues') else ''}",
                f"- Suggestion: {question.get('suggestion', '')}",
                "",
            ]
        )
    return "\n".join(lines)


if __name__ == "__main__":
    main()
