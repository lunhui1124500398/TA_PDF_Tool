from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from mvp_store import (
    AnnotationImportRequest,
    AnnotationImportResult,
    AnnotationRecord,
    BackupSummary,
    CommentUseRequest,
    MVPStore,
    SessionCreateRequest,
    SessionCurrentUpdate,
    SessionSummary,
    StudentAnnotationState,
    StudentStatusUpdate,
)


app = FastAPI(title="TA PDF Tool MVP", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
store = MVPStore()
BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
PDFJS_DIR = BASE_DIR / "node_modules" / "pdfjs-dist"


def open_folder_dialog(initial_dir: str | None = None) -> str:
    if sys.platform == "win32":
        script = """
Add-Type -AssemblyName System.Windows.Forms
$dialog = New-Object System.Windows.Forms.FolderBrowserDialog
$dialog.Description = "选择作业文件夹"
$dialog.ShowNewFolderButton = $false
if ($args.Count -gt 0 -and $args[0] -and (Test-Path $args[0])) {
    $dialog.SelectedPath = $args[0]
}
$result = $dialog.ShowDialog()
if ($result -eq [System.Windows.Forms.DialogResult]::OK) {
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
    Write-Output $dialog.SelectedPath
}
"""
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script, initial_dir or ""],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "打开文件夹选择器失败。")
        return result.stdout.strip()

    import tkinter as tk
    from tkinter import filedialog

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    selected = filedialog.askdirectory(initialdir=initial_dir or str(Path.home()))
    root.destroy()
    return selected.strip()


def open_json_file_dialog(initial_dir: str | None = None) -> str:
    if sys.platform == "win32":
        script = """
Add-Type -AssemblyName System.Windows.Forms
$dialog = New-Object System.Windows.Forms.OpenFileDialog
$dialog.Title = "Select annotations JSON"
$dialog.Filter = "JSON files (*.json)|*.json|All files (*.*)|*.*"
$dialog.CheckFileExists = $true
if ($args.Count -gt 0 -and $args[0] -and (Test-Path $args[0])) {
    $candidate = Get-Item $args[0]
    if ($candidate.PSIsContainer) {
        $dialog.InitialDirectory = $candidate.FullName
    } else {
        $dialog.InitialDirectory = $candidate.DirectoryName
        $dialog.FileName = $candidate.Name
    }
}
$result = $dialog.ShowDialog()
if ($result -eq [System.Windows.Forms.DialogResult]::OK) {
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
    Write-Output $dialog.FileName
}
"""
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script, initial_dir or ""],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "Failed to open JSON file picker.")
        return result.stdout.strip()

    import tkinter as tk
    from tkinter import filedialog

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    selected = filedialog.askopenfilename(
        initialdir=initial_dir or str(Path.home()),
        filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
    )
    root.destroy()
    return selected.strip()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/system/pick-folder")
def pick_folder(initial_dir: str | None = None) -> dict[str, str]:
    try:
        selected = open_folder_dialog(initial_dir)
    except Exception as exc:  # pragma: no cover - native dialog failure is environment-specific
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"selected_path": selected}


@app.get("/api/system/pick-json")
def pick_json(initial_dir: str | None = None) -> dict[str, str]:
    try:
        selected = open_json_file_dialog(initial_dir)
    except Exception as exc:  # pragma: no cover - native dialog failure is environment-specific
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"selected_path": selected}


@app.post("/api/session/create", response_model=SessionSummary)
def create_session(request: SessionCreateRequest) -> SessionSummary:
    try:
        return store.create_session(request)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/session", response_model=SessionSummary)
def get_session() -> SessionSummary:
    try:
        return store.session_summary()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/session/current", response_model=SessionSummary)
def update_current(payload: SessionCurrentUpdate) -> SessionSummary:
    try:
        return store.update_current(payload)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (KeyError, IndexError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/students/{student_id}/status")
def update_student_status(student_id: str, payload: StudentStatusUpdate) -> dict[str, object]:
    try:
        student = store.update_student_status(student_id, payload)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"student": student.model_dump()}


@app.get("/api/students/{student_id}/pdf")
def get_student_pdf(student_id: str) -> FileResponse:
    try:
        session = store.load_session()
        student = next(item for item in session.students if item.student_id == student_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except StopIteration as exc:
        raise HTTPException(status_code=404, detail=f"Unknown student id: {student_id}") from exc

    pdf_path = Path(student.pdf_path)
    if not pdf_path.is_file():
        raise HTTPException(status_code=404, detail=f"PDF file not found: {pdf_path}")
    return FileResponse(pdf_path, media_type="application/pdf", filename=pdf_path.name)


@app.get("/api/students/{student_id}/annotations", response_model=StudentAnnotationState)
def get_student_annotations(student_id: str) -> StudentAnnotationState:
    try:
        return store.get_student_annotations(student_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.put("/api/students/{student_id}/annotations", response_model=StudentAnnotationState)
def replace_student_annotations(student_id: str, annotations: list[AnnotationRecord]) -> StudentAnnotationState:
    try:
        return store.replace_student_annotations(student_id, annotations)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/backups", response_model=list[BackupSummary])
def list_backups() -> list[BackupSummary]:
    return store.list_backups()


@app.post("/api/annotations/import", response_model=AnnotationImportResult)
def import_annotations(request: AnnotationImportRequest) -> AnnotationImportResult:
    try:
        return store.import_annotations(request)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/comments/library")
def get_comment_library() -> dict[str, object]:
    entries = [item.model_dump() for item in store.load_comment_library()]
    return {"entries": entries}


@app.get("/api/comments/recent")
def get_recent_comments() -> dict[str, object]:
    entries = [item.model_dump() for item in store.load_recent_comments()]
    return {"entries": entries}


@app.post("/api/comments/use")
def mark_comment_used(payload: CommentUseRequest) -> dict[str, object]:
    usage = store.mark_comment_used(payload.comment_id)
    return usage.model_dump()


@app.post("/api/export/current/{student_id}")
def export_current(student_id: str) -> dict[str, object]:
    try:
        result = store.export_current(student_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return result.model_dump()


@app.post("/api/export/all")
def export_all() -> dict[str, object]:
    try:
        result = store.export_all()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return result.model_dump()


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

if PDFJS_DIR.exists():
    app.mount("/vendor/pdfjs", StaticFiles(directory=PDFJS_DIR), name="vendor-pdfjs")
