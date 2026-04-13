from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

import fitz


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="最小 OCR 验证链路：读取 PDF，逐页 OCR，并输出结构化 JSON。"
    )
    parser.add_argument("input_path", type=Path, help="输入 PDF 文件或目录。")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("ocr_output"),
        help="OCR 输出目录，默认是 ./ocr_output。",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=None,
        help="仅处理前 N 页，用于快速验证。",
    )
    parser.add_argument(
        "--lang",
        default="ch",
        help="PaddleOCR 语言参数，默认 ch。",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
    from paddleocr import PaddleOCR

    pdf_paths = collect_pdf_paths(args.input_path)
    if not pdf_paths:
        raise SystemExit(f"没有找到 PDF: {args.input_path}")

    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    print("初始化 PaddleOCR，这一步通常最慢，只会做一次。")
    init_start = time.perf_counter()
    ocr = PaddleOCR(lang=args.lang, enable_mkldnn=False)
    init_seconds = time.perf_counter() - init_start
    print(f"OCR 初始化完成，用时 {init_seconds:.2f}s")

    for pdf_path in pdf_paths:
        process_pdf(
            pdf_path=pdf_path,
            output_dir=output_dir,
            ocr=ocr,
            max_pages=args.max_pages,
            init_seconds=init_seconds,
        )


def collect_pdf_paths(input_path: Path) -> list[Path]:
    input_path = input_path.resolve()
    if input_path.is_file():
        return [input_path] if input_path.suffix.lower() == ".pdf" else []
    if input_path.is_dir():
        return sorted(
            [
                path
                for path in input_path.iterdir()
                if path.suffix.lower() == ".pdf" and path.stem.lower() != "merged_for_grading"
            ],
            key=lambda path: path.name.lower(),
        )
    return []


def process_pdf(
    pdf_path: Path,
    output_dir: Path,
    ocr,
    max_pages: int | None,
    init_seconds: float,
) -> None:
    print(f"开始处理: {pdf_path.name}")
    doc = fitz.open(pdf_path)
    try:
        pages = []
        total_pages = doc.page_count if max_pages is None else min(doc.page_count, max_pages)
        started = time.perf_counter()

        for page_index in range(total_pages):
            page = doc[page_index]
            image_path = render_page_image(pdf_path, output_dir, page_index, page)
            page_start = time.perf_counter()
            result = list(ocr.predict(str(image_path)))
            page_seconds = time.perf_counter() - page_start
            page_json = result[0].json["res"]
            pages.append(build_page_record(page_json, page_index + 1, page_seconds, image_path))
            print(
                f"  第 {page_index + 1}/{total_pages} 页完成，"
                f"{len(pages[-1]['blocks'])} 个文本块，{page_seconds:.2f}s"
            )

        total_seconds = time.perf_counter() - started
        payload = {
            "source_pdf": str(pdf_path),
            "source_name": pdf_path.name,
            "init_seconds": round(init_seconds, 3),
            "predict_seconds": round(total_seconds, 3),
            "page_count": total_pages,
            "pages": pages,
        }
        output_path = output_dir / f"{pdf_path.stem}.ocr.json"
        output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"已输出 OCR JSON: {output_path}")
    finally:
        doc.close()


def render_page_image(pdf_path: Path, output_dir: Path, page_index: int, page: fitz.Page) -> Path:
    image_dir = output_dir / "_rendered_pages" / pdf_path.stem
    image_dir.mkdir(parents=True, exist_ok=True)
    image_path = image_dir / f"page_{page_index + 1:03d}.png"
    pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
    pix.save(image_path)
    return image_path


def build_page_record(
    page_json: dict,
    page_index: int,
    page_seconds: float,
    image_path: Path,
) -> dict:
    texts = page_json.get("rec_texts", [])
    scores = page_json.get("rec_scores", [])
    polys = page_json.get("dt_polys", [])

    blocks = []
    for idx, text in enumerate(texts):
        blocks.append(
            {
                "text": text,
                "score": round(float(scores[idx]), 4) if idx < len(scores) else None,
                "polygon": polys[idx] if idx < len(polys) else None,
            }
        )

    full_text = "\n".join(texts)
    return {
        "page_index": page_index,
        "image_path": str(image_path),
        "predict_seconds": round(page_seconds, 3),
        "block_count": len(blocks),
        "full_text": full_text,
        "blocks": blocks,
    }


if __name__ == "__main__":
    main()
