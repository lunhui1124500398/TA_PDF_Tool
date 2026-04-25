import * as pdfjsLib from "/vendor/pdfjs/build/pdf.mjs";

pdfjsLib.GlobalWorkerOptions.workerSrc = "/vendor/pdfjs/build/pdf.worker.mjs";

const STORAGE_KEY_SHORTCUTS = "ta-pdf-tool.shortcuts";
const STORAGE_KEY_PREFERENCES = "ta-pdf-tool.preferences";
const VALID_SYMBOL_TEXTS = new Set(["\u2713", "\u25b3", "\u2717"]);

const toolMap = {
  check: { type: "symbol", text: "\u2713", label: "\u2713" },
  half: { type: "symbol", text: "\u25b3", label: "\u25b3" },
  cross: { type: "symbol", text: "\u2717", label: "\u2717" },
  text: { type: "text", text: "", label: "\u6587\u672c" },
  score: { type: "score", text: "", label: "\u5206\u6570" },
};

const defaultShortcuts = {
  prevStudent: "J",
  nextStudent: "K",
  prevPage: "[",
  nextPage: "]",
  toolCheck: "1",
  toolHalf: "2",
  toolCross: "3",
  toolText: "T",
  toolScore: "G",
  deleteAnnotation: "Delete",
  deleteAnnotationAlt: "Backspace",
  markDone: "Ctrl+Enter",
  markInProgress: "Ctrl+I",
  exportCurrent: "Ctrl+E",
  exportAll: "Ctrl+Shift+E",
};

const defaultPreferences = {
  rootDir: "D:\\Zhujiao\\HW-4&5",
  sessionName: "hw45-mvp",
  tool: "check",
  scale: 1.35,
  draftStyle: {
    color: "#d11a2a",
    font_size: 14,
    font_weight: "normal",
  },
  draftText: "",
};

const shortcutLabels = {
  prevStudent: "\u4e0a\u4e00\u4efd\u4f5c\u4e1a",
  nextStudent: "\u4e0b\u4e00\u4efd\u4f5c\u4e1a",
  prevPage: "\u4e0a\u4e00\u9875",
  nextPage: "\u4e0b\u4e00\u9875",
  toolCheck: "\u5207\u6362\u5230 \u2713",
  toolHalf: "\u5207\u6362\u5230 \u25b3",
  toolCross: "\u5207\u6362\u5230 \u2717",
  toolText: "\u5207\u6362\u5230\u6587\u672c",
  toolScore: "\u5207\u6362\u5230\u5206\u6570",
  deleteAnnotation: "\u5220\u9664\u6279\u6ce8",
  deleteAnnotationAlt: "\u5220\u9664\u6279\u6ce8\uff08\u5907\u7528\uff09",
  markDone: "\u6807\u8bb0\u4e3a\u5b8c\u6210",
  markInProgress: "\u6807\u8bb0\u4e3a\u8fdb\u884c\u4e2d",
  exportCurrent: "\u5bfc\u51fa\u5f53\u524d",
  exportAll: "\u5bfc\u51fa\u5168\u90e8",
};

const shortcutActionOrder = [
  "prevStudent",
  "nextStudent",
  "prevPage",
  "nextPage",
  "toolCheck",
  "toolHalf",
  "toolCross",
  "toolText",
  "toolScore",
  "deleteAnnotation",
  "deleteAnnotationAlt",
  "markDone",
  "markInProgress",
  "exportCurrent",
  "exportAll",
];

const initialPreferences = loadPreferences();

const state = {
  summary: null,
  session: null,
  currentStudent: null,
  currentPage: 1,
  pdfDoc: null,
  scale: initialPreferences.scale,
  annotations: [],
  selectedAnnotationId: null,
  tool: initialPreferences.tool,
  draftStyle: { ...initialPreferences.draftStyle },
  draftText: initialPreferences.draftText,
  viewport: null,
  recentComments: [],
  libraryComments: [],
  backups: [],
  saveTimer: null,
  shortcuts: loadShortcuts(),
  capturingShortcutAction: null,
  inlineEditor: null,
  suppressAnnotationClickUntil: 0,
  lastNonTextTool: initialPreferences.tool === "text" ? "check" : initialPreferences.tool,
  transientTextReturnTool: null,
};

const els = {
  sessionForm: document.querySelector("#session-form"),
  rootDirInput: document.querySelector("#root-dir-input"),
  pickRootDirBtn: document.querySelector("#pick-root-dir-btn"),
  sessionNameInput: document.querySelector("#session-name-input"),
  importJsonInput: document.querySelector("#import-json-input"),
  pickImportJsonBtn: document.querySelector("#pick-import-json-btn"),
  importModeSelect: document.querySelector("#import-mode-select"),
  importAnnotationsBtn: document.querySelector("#import-annotations-btn"),
  backupList: document.querySelector("#backup-list"),
  statusStudent: document.querySelector("#status-student"),
  statusPage: document.querySelector("#status-page"),
  statusDone: document.querySelector("#status-done"),
  statusPending: document.querySelector("#status-pending"),
  statusTool: document.querySelector("#status-tool"),
  statusMessage: document.querySelector("#status-message"),
  queueSummary: document.querySelector("#queue-summary"),
  studentList: document.querySelector("#student-list"),
  prevStudentBtn: document.querySelector("#prev-student-btn"),
  nextStudentBtn: document.querySelector("#next-student-btn"),
  prevPageBtn: document.querySelector("#prev-page-btn"),
  nextPageBtn: document.querySelector("#next-page-btn"),
  zoomOutBtn: document.querySelector("#zoom-out-btn"),
  zoomInBtn: document.querySelector("#zoom-in-btn"),
  markInProgressBtn: document.querySelector("#mark-in-progress-btn"),
  markDoneBtn: document.querySelector("#mark-done-btn"),
  exportCurrentBtn: document.querySelector("#export-current-btn"),
  exportAllBtn: document.querySelector("#export-all-btn"),
  pdfCanvas: document.querySelector("#pdf-canvas"),
  pdfWrapper: document.querySelector("#pdf-wrapper"),
  annotationLayer: document.querySelector("#annotation-layer"),
  toolButtons: [...document.querySelectorAll(".tool-btn")],
  draftColorInput: document.querySelector("#draft-color-input"),
  draftSizeInput: document.querySelector("#draft-size-input"),
  draftWeightInput: document.querySelector("#draft-weight-input"),
  draftTextInput: document.querySelector("#draft-text-input"),
  selectedEmpty: document.querySelector("#selected-empty"),
  selectedEditor: document.querySelector("#selected-editor"),
  selectedTextInput: document.querySelector("#selected-text-input"),
  selectedColorInput: document.querySelector("#selected-color-input"),
  selectedSizeInput: document.querySelector("#selected-size-input"),
  selectedWeightInput: document.querySelector("#selected-weight-input"),
  selectedXInput: document.querySelector("#selected-x-input"),
  selectedYInput: document.querySelector("#selected-y-input"),
  selectedWidthInput: document.querySelector("#selected-width-input"),
  selectedHeightInput: document.querySelector("#selected-height-input"),
  deleteAnnotationBtn: document.querySelector("#delete-annotation-btn"),
  recentComments: document.querySelector("#recent-comments"),
  libraryComments: document.querySelector("#library-comments"),
  pageAnnotations: document.querySelector("#page-annotations"),
  shortcutList: document.querySelector("#shortcut-list"),
  resetShortcutsBtn: document.querySelector("#reset-shortcuts-btn"),
};

function loadShortcuts() {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY_SHORTCUTS);
    if (!raw) {
      return { ...defaultShortcuts };
    }
    return { ...defaultShortcuts, ...JSON.parse(raw) };
  } catch {
    return { ...defaultShortcuts };
  }
}

function cloneDefaultPreferences() {
  return {
    ...defaultPreferences,
    draftStyle: { ...defaultPreferences.draftStyle },
  };
}

function loadPreferences() {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY_PREFERENCES);
    if (!raw) {
      return cloneDefaultPreferences();
    }
    const parsed = JSON.parse(raw);
    return {
      ...cloneDefaultPreferences(),
      ...parsed,
      draftStyle: {
        ...defaultPreferences.draftStyle,
        ...(parsed.draftStyle || {}),
      },
    };
  } catch {
    return cloneDefaultPreferences();
  }
}

function saveShortcuts() {
  window.localStorage.setItem(STORAGE_KEY_SHORTCUTS, JSON.stringify(state.shortcuts));
}

function savePreferences() {
  window.localStorage.setItem(
    STORAGE_KEY_PREFERENCES,
    JSON.stringify({
      rootDir: els.rootDirInput.value.trim() || defaultPreferences.rootDir,
      sessionName: els.sessionNameInput.value.trim() || defaultPreferences.sessionName,
      tool: state.tool,
      scale: state.scale,
      draftStyle: { ...state.draftStyle },
      draftText: state.draftText,
    }),
  );
}

function setStatus(message) {
  els.statusMessage.textContent = message;
}

async function api(url, options = {}) {
  const response = await fetch(url, {
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
    ...options,
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(payload.detail || response.statusText);
  }
  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    return response.json();
  }
  return response;
}

function formatStatus(status) {
  if (status === "done") {
    return "\u5df2\u5b8c\u6210";
  }
  if (status === "in_progress") {
    return "\u8fdb\u884c\u4e2d";
  }
  return "\u672a\u5f00\u59cb";
}

function escapeHtml(value) {
  return value.replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;");
}

function roundNumber(value) {
  return Math.round(value * 10) / 10;
}

function isStrictSymbolText(text) {
  return VALID_SYMBOL_TEXTS.has((text || "").trim());
}

function normalizeAnnotation(annotation) {
  const normalized = {
    ...annotation,
    style: { ...annotation.style },
    text: annotation.text || "",
  };

  if (normalized.type === "symbol" && !isStrictSymbolText(normalized.text)) {
    normalized.type = "text";
  }

  if (normalized.type === "symbol") {
    normalized.text = normalized.text.trim() || normalized.text;
    normalized.width = normalized.width && normalized.width > 0 ? normalized.width : null;
    normalized.height = normalized.height && normalized.height > 0 ? normalized.height : null;
    return normalized;
  }

  if (normalized.type === "text") {
    normalized.width =
      normalized.width && normalized.width > 0 ? normalized.width : Math.max(normalized.style.font_size * 8, 160);
    normalized.height =
      normalized.height && normalized.height > 0 ? normalized.height : Math.max(normalized.style.font_size * 2.5, 60);
    return normalized;
  }

  normalized.width =
    normalized.width && normalized.width > 0 ? normalized.width : Math.max(normalized.style.font_size * 3.5, 90);
  normalized.height =
    normalized.height && normalized.height > 0 ? normalized.height : Math.max(normalized.style.font_size * 1.8, 40);
  return normalized;
}

function normalizeAnnotationInPlace(annotation) {
  const before = JSON.stringify(annotation);
  Object.assign(annotation, normalizeAnnotation(annotation));
  return before !== JSON.stringify(annotation);
}

function normalizeAnnotationsList(annotations) {
  let changed = false;
  const normalized = annotations.map((annotation) => {
    const next = normalizeAnnotation(annotation);
    if (JSON.stringify(next) !== JSON.stringify(annotation)) {
      changed = true;
    }
    return next;
  });
  return { annotations: normalized, changed };
}

function normalizeAnnotationsInPlace(annotations) {
  let changed = false;
  for (const annotation of annotations) {
    if (normalizeAnnotationInPlace(annotation)) {
      changed = true;
    }
  }
  return changed;
}

function getSelectedAnnotation() {
  return state.annotations.find((item) => item.id === state.selectedAnnotationId) || null;
}

function getCurrentStudentIndex() {
  if (!state.session || !state.currentStudent) {
    return -1;
  }
  return state.session.students.findIndex((item) => item.student_id === state.currentStudent.student_id);
}

function getPageHeightPt() {
  if (!state.viewport || !state.scale) {
    return 0;
  }
  return state.viewport.height / state.scale;
}

function getTopBasedY(annotation) {
  return roundNumber(getPageHeightPt() - annotation.y);
}

function clearSelection({ render = true } = {}) {
  if (!state.selectedAnnotationId && !state.inlineEditor) {
    return;
  }
  closeInlineEditor({ save: true });
  state.selectedAnnotationId = null;
  if (render) {
    renderAnnotationsForCurrentPage();
  }
  populateSelectedEditor();
}

function setTool(tool) {
  state.tool = tool;
  if (tool !== "text") {
    state.lastNonTextTool = tool;
    state.transientTextReturnTool = null;
  }
  els.toolButtons.forEach((button) => {
    button.classList.toggle("active", button.dataset.tool === tool);
  });
  els.statusTool.textContent = toolMap[tool].label;
  savePreferences();
  if (tool === "score" && state.pdfDoc && state.currentPage !== 1) {
    void goToPage(1);
  }
}

function enterTransientTextMode() {
  state.transientTextReturnTool = state.tool === "text" ? state.lastNonTextTool : state.tool;
  setTool("text");
  state.transientTextReturnTool = state.lastNonTextTool;
  setStatus("文本输入模式已开启，点击空白处开始输入，按 Enter 保存后自动回到批改模式。");
}

function enterPersistentTextMode() {
  state.transientTextReturnTool = null;
  setTool("text");
  setStatus("文本模式已开启，点击空白处开始输入。");
}

function updateDraftStyleFromInputs() {
  state.draftStyle = {
    color: els.draftColorInput.value,
    font_size: Number(els.draftSizeInput.value || 14),
    font_weight: els.draftWeightInput.value,
  };
  state.draftText = els.draftTextInput.value;
  savePreferences();
}

function populateSelectedEditor() {
  const selected = getSelectedAnnotation();
  const hasSelection = Boolean(selected);
  els.selectedEmpty.classList.toggle("hidden", hasSelection);
  els.selectedEditor.classList.toggle("hidden", !hasSelection);
  if (!selected) {
    return;
  }
  els.selectedTextInput.value = selected.text;
  els.selectedColorInput.value = selected.style.color;
  els.selectedSizeInput.value = selected.style.font_size;
  els.selectedWeightInput.value = selected.style.font_weight;
  els.selectedXInput.value = Math.round(selected.x);
  els.selectedYInput.value = Math.round(getTopBasedY(selected));
  els.selectedWidthInput.value = selected.width ?? "";
  els.selectedHeightInput.value = selected.height ?? "";
}

function closeInlineEditor({ save = true } = {}) {
  if (!state.inlineEditor) {
    return;
  }

  const { textarea, annotationId, returnTool = null, removeIfEmpty = false } = state.inlineEditor;
  const annotation = state.annotations.find((item) => item.id === annotationId);
  const value = textarea.value;
  textarea.remove();
  state.inlineEditor = null;

  if (annotation) {
    const trimmed = value.trim();
    if ((save && removeIfEmpty && !trimmed) || (!save && removeIfEmpty)) {
      state.annotations = state.annotations.filter((item) => item.id !== annotationId);
      state.selectedAnnotationId = null;
      renderAnnotationsForCurrentPage();
      populateSelectedEditor();
      scheduleSaveAnnotations();
      if (returnTool) {
        setTool(returnTool);
      }
      return;
    }
  }

  if (save && annotation) {
    annotation.text = value;
    normalizeAnnotationInPlace(annotation);
    state.selectedAnnotationId = null;
    renderAnnotationsForCurrentPage();
    populateSelectedEditor();
    scheduleSaveAnnotations();
    if (returnTool) {
      setTool(returnTool);
    }
    return;
  }

  state.selectedAnnotationId = null;
  renderAnnotationsForCurrentPage();
  populateSelectedEditor();
  if (returnTool) {
    setTool(returnTool);
  }
}

function openInlineEditor(annotation, element, options = {}) {
  if (annotation.type === "symbol" || state.inlineEditor?.annotationId === annotation.id) {
    return;
  }

  closeInlineEditor({ save: true });
  state.selectedAnnotationId = annotation.id;
  populateSelectedEditor();

  const textarea = document.createElement("textarea");
  textarea.className = "annotation-inline-editor";
  textarea.value = annotation.text;
  textarea.style.left = element.style.left;
  textarea.style.top = element.style.top;
  textarea.style.width = `${Math.max(element.offsetWidth + 16, 140)}px`;
  textarea.style.minHeight = `${Math.max(element.offsetHeight + 12, annotation.type === "score" ? 44 : 72)}px`;
  textarea.style.color = annotation.style.color;
  textarea.style.fontWeight = annotation.style.font_weight;
  textarea.style.fontSize = `${annotation.style.font_size * state.scale}px`;

  state.inlineEditor = {
    annotationId: annotation.id,
    textarea,
    returnTool: options.returnTool || null,
    removeIfEmpty: options.removeIfEmpty || false,
  };
  els.annotationLayer.appendChild(textarea);
  textarea.focus();
  textarea.select();

  textarea.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      event.preventDefault();
      closeInlineEditor({ save: false });
      return;
    }
    if (event.key === "Enter" && (annotation.type === "score" || !event.shiftKey || event.ctrlKey)) {
      event.preventDefault();
      closeInlineEditor({ save: true });
    }
  });

  textarea.addEventListener("blur", () => {
    closeInlineEditor({ save: true });
  });
}

function findAnnotationElement(annotationId) {
  return els.annotationLayer.querySelector(`[data-annotation-id="${annotationId}"]`);
}

function getPdfPointFromLayerEvent(event) {
  const rect = els.annotationLayer.getBoundingClientRect();
  return state.viewport.convertToPdfPoint(event.clientX - rect.left, event.clientY - rect.top);
}

function createInlineAnnotationAtPdfPoint(pdfX, pdfY, type, options = {}) {
  const annotation = normalizeAnnotation({
    id: `ann_${Date.now()}_${Math.random().toString(16).slice(2, 6)}`,
    type,
    page_index: state.currentPage,
    x: roundNumber(pdfX),
    y: roundNumber(pdfY),
    width: type === "score" ? 90 : 180,
    height: type === "score" ? 40 : 60,
    text: options.initialText ?? "",
    style: { ...state.draftStyle },
    source_comment_id: null,
  });
  state.annotations.push(annotation);
  state.selectedAnnotationId = annotation.id;
  renderAnnotationsForCurrentPage();
  populateSelectedEditor();
  const element = findAnnotationElement(annotation.id);
  if (element) {
    openInlineEditor(annotation, element, {
      returnTool: options.returnTool || null,
      removeIfEmpty: options.removeIfEmpty ?? true,
    });
  }
}

function renderQueue() {
  if (!state.summary) {
    els.queueSummary.textContent = "\u672a\u52a0\u8f7d\u4f1a\u8bdd";
    els.studentList.innerHTML = "";
    return;
  }

  const { session, completed_count, remaining_count, current_student } = state.summary;
  state.session = session;
  state.currentStudent = current_student;
  els.statusStudent.textContent = current_student ? `${current_student.student_id} ${current_student.name}` : "-";
  els.statusDone.textContent = completed_count;
  els.statusPending.textContent = remaining_count;
  els.queueSummary.textContent = `\u5171 ${session.students.length} \u4efd\uff0c\u5df2\u5b8c\u6210 ${completed_count} \u4efd`;
  els.studentList.innerHTML = session.students
    .map((student, index) => {
      const active = current_student && student.student_id === current_student.student_id;
      return `
        <div class="student-item ${active ? "active" : ""} ${student.status === "done" ? "done" : ""}" data-student-id="${student.student_id}">
          <div class="student-row">
            <strong>${index + 1}. ${student.name}</strong>
            <span>${student.score_summary || "-"}</span>
          </div>
          <div class="student-meta">
            ${student.student_id} · ${student.page_count} 页 · ${formatStatus(student.status)}
          </div>
        </div>
      `;
    })
    .join("");

  els.studentList.querySelectorAll(".student-item").forEach((item) => {
    item.addEventListener("click", () => selectStudent(item.dataset.studentId));
  });
}

async function refreshComments() {
  const [library, recent] = await Promise.all([api("/api/comments/library"), api("/api/comments/recent")]);
  state.libraryComments = library.entries;
  state.recentComments = recent.entries;
  renderCommentLists();
}

function renderCommentButtons(entries, showCategory) {
  if (!entries.length) {
    return '<div class="hint">\u6682\u65e0\u5185\u5bb9</div>';
  }
  return entries
    .map(
      (entry) => `
      <div class="comment-item">
        ${showCategory ? `<div class="comment-meta">${entry.category}</div>` : ""}
        <button type="button" data-comment-id="${entry.comment_id}">${entry.text}</button>
      </div>
    `,
    )
    .join("");
}

function renderCommentLists() {
  els.recentComments.innerHTML = renderCommentButtons(state.recentComments, true);
  els.libraryComments.innerHTML = renderCommentButtons(state.libraryComments, false);
  [...els.recentComments.querySelectorAll("button"), ...els.libraryComments.querySelectorAll("button")].forEach(
    (button) => {
      button.addEventListener("click", () => applyCommentEntry(button.dataset.commentId));
    },
  );
}

async function applyCommentEntry(commentId) {
  const entry =
    state.libraryComments.find((item) => item.comment_id === commentId) ||
    state.recentComments.find((item) => item.comment_id === commentId);
  if (!entry) {
    return;
  }

  const selected = getSelectedAnnotation();
  if (selected && selected.type === "text") {
    selected.text = entry.text;
    selected.source_comment_id = entry.comment_id;
    renderAnnotationsForCurrentPage();
    populateSelectedEditor();
    scheduleSaveAnnotations();
  } else {
    enterPersistentTextMode();
    state.draftText = entry.text;
    els.draftTextInput.value = entry.text;
    setStatus("\u6279\u8bed\u5df2\u653e\u5165\u6587\u672c\u8349\u7a3f\uff0c\u70b9\u51fb PDF \u9875\u9762\u5373\u53ef\u843d\u6279\u6ce8\u3002");
  }

  await api("/api/comments/use", {
    method: "POST",
    body: JSON.stringify({ comment_id: entry.comment_id }),
  });
  await refreshComments();
}

function renderShortcutList() {
  els.shortcutList.innerHTML = shortcutActionOrder
    .map((action) => {
      const capturing = state.capturingShortcutAction === action;
      const current = state.shortcuts[action] || "\u672a\u8bbe\u7f6e";
      return `
        <div class="shortcut-row">
          <span class="shortcut-label">${shortcutLabels[action]}</span>
          <button
            type="button"
            class="shortcut-capture ${capturing ? "capturing" : ""}"
            data-shortcut-action="${action}"
          >
            ${capturing ? "\u6309\u952e\u4e2d..." : current}
          </button>
        </div>
      `;
    })
    .join("");

  els.shortcutList.querySelectorAll(".shortcut-capture").forEach((button) => {
    button.addEventListener("click", () => {
      state.capturingShortcutAction = button.dataset.shortcutAction;
      renderShortcutList();
    });
  });
}

function normalizeKeyName(key) {
  if (key === " ") {
    return "Space";
  }
  if (key.length === 1) {
    return key.toUpperCase();
  }
  return key;
}

function normalizeShortcut(event) {
  const parts = [];
  if (event.ctrlKey) {
    parts.push("Ctrl");
  }
  if (event.altKey) {
    parts.push("Alt");
  }
  if (event.shiftKey) {
    parts.push("Shift");
  }
  const keyName = normalizeKeyName(event.key);
  if (["Control", "Shift", "Alt", "Meta"].includes(keyName)) {
    return parts.join("+");
  }
  parts.push(keyName);
  return parts.join("+");
}

async function loadSession() {
  try {
    state.summary = await api("/api/session");
    renderQueue();
    await refreshComments();
    await refreshBackups();
    await loadStudentDocument();
  } catch {
    await refreshBackups();
    setStatus("\u8fd8\u6ca1\u6709\u4f1a\u8bdd\u3002\u5148\u521b\u5efa\u4f1a\u8bdd\u540e\u5373\u53ef\u5f00\u59cb\u4f7f\u7528\u3002");
  }
}

async function createSession(event) {
  event.preventDefault();
  try {
    setStatus("\u6b63\u5728\u626b\u63cf\u4f5c\u4e1a\u76ee\u5f55...");
    state.summary = await api("/api/session/create", {
      method: "POST",
      body: JSON.stringify({
        root_dir: els.rootDirInput.value.trim(),
        session_name: els.sessionNameInput.value.trim() || null,
      }),
    });
    state.currentPage = 1;
    state.selectedAnnotationId = null;
    renderQueue();
    await refreshComments();
    await refreshBackups();
    await loadStudentDocument();
    setStatus("\u4f1a\u8bdd\u5df2\u521b\u5efa\uff0c\u73b0\u5728\u53ef\u4ee5\u5f00\u59cb\u6279\u6539\u3002");
  } catch (error) {
    setStatus(error.message);
  }
}

async function pickRootDirectory() {
  const initialDir = els.rootDirInput.value.trim();
  const originalLabel = els.pickRootDirBtn.textContent;
  els.pickRootDirBtn.disabled = true;
  els.pickRootDirBtn.textContent = "打开中...";
  try {
    const result = await api(`/api/system/pick-folder?initial_dir=${encodeURIComponent(initialDir)}`);
    if (!result.selected_path) {
      setStatus("已取消选择文件夹。");
      return;
    }
    els.rootDirInput.value = result.selected_path;
    savePreferences();
    setStatus(`已选择作业目录：${result.selected_path}`);
  } catch (error) {
    setStatus(error.message);
  } finally {
    els.pickRootDirBtn.disabled = false;
    els.pickRootDirBtn.textContent = originalLabel;
  }
}

async function refreshBackups() {
  try {
    state.backups = await api("/api/backups");
    renderBackupList();
  } catch {
    state.backups = [];
    renderBackupList();
  }
}

function renderBackupList() {
  if (!els.backupList) {
    return;
  }
  const backups = state.backups.slice(0, 6);
  if (!backups.length) {
    els.backupList.innerHTML = '<div class="hint">\u6682\u65e0\u5907\u4efd</div>';
    return;
  }

  els.backupList.innerHTML = backups
    .map((backup, index) => {
      const source = backup.annotations_path || backup.path;
      return `
        <div class="backup-item">
          <button type="button" data-backup-index="${index}">
            <strong>${escapeHtml(backup.reason || "\u5907\u4efd")}</strong>
            <span>${escapeHtml(backup.name)}</span>
            <small>${escapeHtml(source || "")}</small>
          </button>
        </div>
      `;
    })
    .join("");

  els.backupList.querySelectorAll("button").forEach((button) => {
    button.addEventListener("click", () => {
      const backup = backups[Number(button.dataset.backupIndex)];
      els.importJsonInput.value = backup.annotations_path || backup.path;
      setStatus("\u5df2\u586b\u5165\u5907\u4efd\u8def\u5f84\uff0c\u53ef\u4ee5\u70b9\u51fb\u5bfc\u5165\u6279\u6ce8\u3002");
    });
  });
}

async function pickImportJson() {
  const initialDir = els.importJsonInput.value.trim() || els.rootDirInput.value.trim();
  const originalLabel = els.pickImportJsonBtn.textContent;
  els.pickImportJsonBtn.disabled = true;
  els.pickImportJsonBtn.textContent = "\u6253\u5f00\u4e2d...";
  try {
    const result = await api(`/api/system/pick-json?initial_dir=${encodeURIComponent(initialDir)}`);
    if (!result.selected_path) {
      setStatus("\u5df2\u53d6\u6d88\u9009\u62e9 JSON\u3002");
      return;
    }
    els.importJsonInput.value = result.selected_path;
    setStatus(`\u5df2\u9009\u62e9 JSON\uff1a${result.selected_path}`);
  } catch (error) {
    setStatus(error.message);
  } finally {
    els.pickImportJsonBtn.disabled = false;
    els.pickImportJsonBtn.textContent = originalLabel;
  }
}

async function importAnnotations() {
  const jsonPath = els.importJsonInput.value.trim();
  if (!jsonPath) {
    setStatus("\u8bf7\u5148\u9009\u62e9\u6216\u586b\u5199 annotations.json \u8def\u5f84\u3002");
    return;
  }

  const originalLabel = els.importAnnotationsBtn.textContent;
  els.importAnnotationsBtn.disabled = true;
  els.importAnnotationsBtn.textContent = "\u5bfc\u5165\u4e2d...";
  try {
    if (state.currentStudent) {
      await saveAnnotations();
    }
    const result = await api("/api/annotations/import", {
      method: "POST",
      body: JSON.stringify({
        json_path: jsonPath,
        mode: els.importModeSelect.value,
      }),
    });
    state.summary = await api("/api/session");
    renderQueue();
    await refreshBackups();
    await loadStudentDocument();
    setStatus(
      `\u5df2\u5bfc\u5165 ${result.imported_students} \u4f4d\u5b66\u751f\u7684 ${result.imported_annotations} \u6761\u6279\u6ce8\u3002`,
    );
  } catch (error) {
    setStatus(error.message);
  } finally {
    els.importAnnotationsBtn.disabled = false;
    els.importAnnotationsBtn.textContent = originalLabel;
  }
}

async function selectStudent(studentId) {
  try {
    state.summary = await api("/api/session/current", {
      method: "POST",
      body: JSON.stringify({ current_student_id: studentId }),
    });
    state.currentPage = state.summary.current_student?.last_page || 1;
    state.selectedAnnotationId = null;
    renderQueue();
    await loadStudentDocument();
  } catch (error) {
    setStatus(error.message);
  }
}

async function updateCurrentPage(pageNumber) {
  if (!state.currentStudent) {
    return;
  }
  state.currentPage = pageNumber;
  state.summary = await api("/api/session/current", {
    method: "POST",
    body: JSON.stringify({
      current_student_id: state.currentStudent.student_id,
      current_page: pageNumber,
    }),
  });
  renderQueue();
}

async function loadStudentDocument() {
  if (!state.currentStudent) {
    return;
  }
  closeInlineEditor({ save: true });
  state.selectedAnnotationId = null;
  populateSelectedEditor();
  state.annotations = [];
  if (state.pdfDoc) {
    state.pdfDoc.destroy();
  }
  setStatus(`\u6b63\u5728\u52a0\u8f7d ${state.currentStudent.name} \u7684 PDF...`);
  state.pdfDoc = await pdfjsLib.getDocument({
    url: `/api/students/${encodeURIComponent(state.currentStudent.student_id)}/pdf`,
  }).promise;
  state.currentPage = Math.max(1, Math.min(state.currentPage || 1, state.pdfDoc.numPages));
  const annotationState = await api(`/api/students/${encodeURIComponent(state.currentStudent.student_id)}/annotations`);
  const normalized = normalizeAnnotationsList(annotationState.annotations || []);
  state.annotations = normalized.annotations;
  await renderCurrentPage();
  if (normalized.changed) {
    scheduleSaveAnnotations();
  }
  setStatus(`\u5df2\u6253\u5f00 ${state.currentStudent.name}\uff0c\u53ef\u4ee5\u5f00\u59cb\u6279\u6539\u3002`);
}

async function renderCurrentPage() {
  if (!state.pdfDoc) {
    return;
  }
  closeInlineEditor({ save: true });
  const page = await state.pdfDoc.getPage(state.currentPage);
  const viewport = page.getViewport({ scale: state.scale });
  state.viewport = viewport;
  els.pdfCanvas.width = viewport.width;
  els.pdfCanvas.height = viewport.height;
  els.pdfCanvas.style.width = `${viewport.width}px`;
  els.pdfCanvas.style.height = `${viewport.height}px`;
  els.annotationLayer.style.width = `${viewport.width}px`;
  els.annotationLayer.style.height = `${viewport.height}px`;
  els.pdfWrapper.style.width = `${viewport.width}px`;
  els.pdfWrapper.style.height = `${viewport.height}px`;
  const context = els.pdfCanvas.getContext("2d");
  await page.render({ canvasContext: context, viewport }).promise;
  renderAnnotationsForCurrentPage();
  els.statusPage.textContent = `${state.currentPage} / ${state.pdfDoc.numPages}`;
}

function renderAnnotationsForCurrentPage() {
  if (!state.viewport) {
    return;
  }
  let normalizedChanged = false;
  for (const annotation of state.annotations) {
    if (normalizeAnnotationInPlace(annotation)) {
      normalizedChanged = true;
    }
  }
  const pageAnnotations = state.annotations.filter((item) => item.page_index === state.currentPage);
  let dimensionsAdjusted = false;
  els.annotationLayer.innerHTML = "";
  els.pageAnnotations.innerHTML = pageAnnotations.length
    ? pageAnnotations
        .map(
          (item) => `
            <div class="annotation-row">
              <button type="button" data-annotation-id="${item.id}">
                ${item.type.toUpperCase()} · ${escapeHtml(item.text)}
              </button>
            </div>
          `,
        )
        .join("")
    : '<div class="hint">\u5f53\u524d\u9875\u8fd8\u6ca1\u6709\u6279\u6ce8</div>';

  els.pageAnnotations.querySelectorAll("button").forEach((button) => {
    button.addEventListener("click", () => {
      state.selectedAnnotationId = button.dataset.annotationId;
      populateSelectedEditor();
      renderAnnotationsForCurrentPage();
    });
  });

  for (const annotation of pageAnnotations) {
    const element = document.createElement("div");
    element.className = "annotation-item";
    if (annotation.id === state.selectedAnnotationId) {
      element.classList.add("selected");
    }
    const [left, top] = state.viewport.convertToViewportPoint(annotation.x, annotation.y);
    element.style.left = `${left}px`;
    element.style.top = `${top}px`;
    element.style.color = annotation.style.color;
    element.style.fontWeight = annotation.style.font_weight;
    element.style.fontSize = `${annotation.style.font_size * state.scale}px`;
    if (annotation.width) {
      element.style.width = `${annotation.width * state.scale}px`;
    }
    if (annotation.height) {
      element.style.minHeight = `${annotation.height * state.scale}px`;
    }
    element.textContent = annotation.text;
    element.dataset.annotationId = annotation.id;
    element.addEventListener("click", (event) => {
      event.stopPropagation();
      if (Date.now() < state.suppressAnnotationClickUntil) {
        return;
      }
      state.selectedAnnotationId = annotation.id;
      populateSelectedEditor();
      renderAnnotationsForCurrentPage();
    });
    element.addEventListener("dblclick", (event) => {
      event.preventDefault();
      event.stopPropagation();
      openInlineEditor(annotation, element);
    });
    attachDragBehavior(element, annotation);
    els.annotationLayer.appendChild(element);
    if (syncAnnotationDimensions(element, annotation)) {
      dimensionsAdjusted = true;
      applyAnnotationElementStyles(element, annotation);
    }
  }

  if (dimensionsAdjusted || normalizedChanged) {
    populateSelectedEditor();
    scheduleSaveAnnotations();
  }
}

function applyAnnotationElementStyles(element, annotation) {
  const [left, top] = state.viewport.convertToViewportPoint(annotation.x, annotation.y);
  element.style.left = `${left}px`;
  element.style.top = `${top}px`;
  element.style.color = annotation.style.color;
  element.style.fontWeight = annotation.style.font_weight;
  element.style.fontSize = `${annotation.style.font_size * state.scale}px`;
  if (annotation.width) {
    element.style.width = `${annotation.width * state.scale}px`;
  } else {
    element.style.removeProperty("width");
  }
  if (annotation.height) {
    element.style.minHeight = `${annotation.height * state.scale}px`;
  } else {
    element.style.removeProperty("min-height");
  }
}

function syncAnnotationDimensions(element, annotation) {
  if (!["text", "score"].includes(annotation.type)) {
    return false;
  }

  const nextWidth = roundNumber(element.scrollWidth / state.scale);
  const nextHeight = roundNumber(element.scrollHeight / state.scale);
  let changed = false;

  if (annotation.type === "score") {
    if (!annotation.width || nextWidth > annotation.width + 0.5) {
      annotation.width = nextWidth;
      changed = true;
    }
  }

  if (!annotation.height || nextHeight > annotation.height + 0.5) {
    annotation.height = nextHeight;
    changed = true;
  }

  return changed;
}

function attachDragBehavior(element, annotation) {
  let dragState = null;
  let handlePointerMove = null;
  let stopDragging = null;

  element.addEventListener("pointerdown", (event) => {
    if (event.button !== 0 || state.inlineEditor?.annotationId === annotation.id) {
      return;
    }
    event.preventDefault();
    event.stopPropagation();

    dragState = {
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      originalX: annotation.x,
      originalY: annotation.y,
      moved: false,
    };
    state.selectedAnnotationId = annotation.id;
    populateSelectedEditor();
    element.classList.add("dragging");

    handlePointerMove = (moveEvent) => {
      if (!dragState || moveEvent.pointerId !== dragState.pointerId) {
        return;
      }
      moveEvent.preventDefault();
      const deltaX = moveEvent.clientX - dragState.startX;
      const deltaY = moveEvent.clientY - dragState.startY;
      if (!dragState.moved && Math.hypot(deltaX, deltaY) >= 3) {
        dragState.moved = true;
      }
      annotation.x = roundNumber(dragState.originalX + deltaX / state.scale);
      annotation.y = roundNumber(dragState.originalY - deltaY / state.scale);
      const [left, top] = state.viewport.convertToViewportPoint(annotation.x, annotation.y);
      element.style.left = `${left}px`;
      element.style.top = `${top}px`;
      populateSelectedEditor();
    };

    stopDragging = (endEvent) => {
      if (!dragState || (endEvent && endEvent.pointerId !== dragState.pointerId)) {
        return;
      }
      const moved = dragState.moved;
      dragState = null;
      element.classList.remove("dragging");
      window.removeEventListener("pointermove", handlePointerMove, true);
      window.removeEventListener("pointerup", stopDragging, true);
      window.removeEventListener("pointercancel", stopDragging, true);
      if (moved) {
        state.suppressAnnotationClickUntil = Date.now() + 250;
        renderAnnotationsForCurrentPage();
        scheduleSaveAnnotations();
      }
    };

    window.addEventListener("pointermove", handlePointerMove, true);
    window.addEventListener("pointerup", stopDragging, true);
    window.addEventListener("pointercancel", stopDragging, true);
  });
}

async function goToPage(nextPage) {
  if (!state.pdfDoc) {
    return;
  }
  const clamped = Math.max(1, Math.min(nextPage, state.pdfDoc.numPages));
  if (clamped === state.currentPage) {
    return;
  }
  await updateCurrentPage(clamped);
  await renderCurrentPage();
}

async function moveStudent(offset) {
  if (!state.session || !state.currentStudent) {
    return;
  }
  const index = getCurrentStudentIndex();
  const target = index + offset;
  if (target < 0 || target >= state.session.students.length) {
    return;
  }
  await selectStudent(state.session.students[target].student_id);
}

function createAnnotationAtClick(event) {
  if (!state.viewport || !state.currentStudent || event.target !== els.annotationLayer) {
    return;
  }
  if (state.inlineEditor) {
    closeInlineEditor({ save: true });
    return;
  }
  if (state.selectedAnnotationId) {
    if (state.tool === "text" || state.tool === "score") {
      clearSelection({ render: false });
    } else {
      clearSelection();
      return;
    }
  }
  updateDraftStyleFromInputs();
  const [pdfX, pdfY] = getPdfPointFromLayerEvent(event);
  const toolConfig = toolMap[state.tool];
  if (toolConfig.type === "text") {
    const returnTool = state.transientTextReturnTool;
    state.transientTextReturnTool = null;
    createInlineAnnotationAtPdfPoint(pdfX, pdfY, "text", {
      initialText: state.draftText.trim(),
      returnTool,
      removeIfEmpty: true,
    });
    return;
  }
  if (toolConfig.type === "score") {
    createInlineAnnotationAtPdfPoint(pdfX, pdfY, "score", {
      initialText: state.draftText.trim(),
      removeIfEmpty: true,
    });
    return;
  }

  const annotation = {
    id: `ann_${Date.now()}_${Math.random().toString(16).slice(2, 6)}`,
    type: toolConfig.type,
    page_index: state.currentPage,
    x: roundNumber(pdfX),
    y: roundNumber(pdfY),
    width: null,
    height: null,
    text: toolConfig.text,
    style: { ...state.draftStyle },
    source_comment_id: null,
  };
  state.annotations.push(normalizeAnnotation(annotation));
  state.selectedAnnotationId = null;
  renderAnnotationsForCurrentPage();
  populateSelectedEditor();
  scheduleSaveAnnotations();
}

function scheduleSaveAnnotations() {
  if (!state.currentStudent) {
    return;
  }
  window.clearTimeout(state.saveTimer);
  state.saveTimer = window.setTimeout(saveAnnotations, 300);
}

async function saveAnnotations() {
  if (!state.currentStudent) {
    return;
  }
  normalizeAnnotationsInPlace(state.annotations);
  await api(`/api/students/${encodeURIComponent(state.currentStudent.student_id)}/annotations`, {
    method: "PUT",
    body: JSON.stringify(state.annotations),
  });
  setStatus("\u6279\u6ce8\u5df2\u4fdd\u5b58\u3002");
}

function updateSelectedAnnotation(mutator) {
  const selected = getSelectedAnnotation();
  if (!selected) {
    return;
  }
  mutator(selected);
  normalizeAnnotationInPlace(selected);
  renderAnnotationsForCurrentPage();
  populateSelectedEditor();
  scheduleSaveAnnotations();
}

async function updateStudentStatus(status) {
  if (!state.currentStudent) {
    return;
  }
  const score = state.annotations.filter((item) => item.type === "score" && item.text.trim()).at(-1);
  await api(`/api/students/${encodeURIComponent(state.currentStudent.student_id)}/status`, {
    method: "POST",
    body: JSON.stringify({
      status,
      score_summary: score ? score.text.trim() : state.currentStudent.score_summary || "",
    }),
  });
  state.summary = await api("/api/session");
  renderQueue();
  setStatus(
    status === "done"
      ? "\u5f53\u524d\u5b66\u751f\u5df2\u6807\u8bb0\u4e3a\u5b8c\u6210\u3002"
      : "\u5f53\u524d\u5b66\u751f\u5df2\u6807\u8bb0\u4e3a\u8fdb\u884c\u4e2d\u3002",
  );
}

async function exportCurrent() {
  if (!state.currentStudent) {
    return;
  }
  await saveAnnotations();
  const result = await api(`/api/export/current/${encodeURIComponent(state.currentStudent.student_id)}`, {
    method: "POST",
  });
  setStatus(`\u5df2\u5bfc\u51fa\u5230 ${result.output_pdf}`);
}

async function exportAll() {
  await saveAnnotations();
  const result = await api("/api/export/all", { method: "POST" });
  setStatus(`\u5df2\u5bfc\u51fa ${result.exported_count} \u4efd PDF\uff0c\u6210\u7ee9\u8868\u5728 ${result.score_csv}`);
}

function removeSelectedAnnotation() {
  if (!state.selectedAnnotationId) {
    return;
  }
  state.annotations = state.annotations.filter((item) => item.id !== state.selectedAnnotationId);
  state.selectedAnnotationId = null;
  renderAnnotationsForCurrentPage();
  populateSelectedEditor();
  scheduleSaveAnnotations();
}

function runShortcutAction(action) {
  switch (action) {
    case "prevStudent":
      return moveStudent(-1);
    case "nextStudent":
      return moveStudent(1);
    case "prevPage":
      return goToPage(state.currentPage - 1);
    case "nextPage":
      return goToPage(state.currentPage + 1);
    case "toolCheck":
      return setTool("check");
    case "toolHalf":
      return setTool("half");
    case "toolCross":
      return setTool("cross");
    case "toolText":
      return enterTransientTextMode();
    case "toolScore":
      return setTool("score");
    case "deleteAnnotation":
    case "deleteAnnotationAlt":
      return removeSelectedAnnotation();
    case "markDone":
      return updateStudentStatus("done");
    case "markInProgress":
      return updateStudentStatus("in_progress");
    case "exportCurrent":
      return exportCurrent();
    case "exportAll":
      return exportAll();
    default:
      return undefined;
  }
}

function handleShortcutCapture(event) {
  if (!state.capturingShortcutAction) {
    return false;
  }
  event.preventDefault();
  event.stopPropagation();
  if (event.key === "Escape") {
    state.capturingShortcutAction = null;
    renderShortcutList();
    setStatus("\u5df2\u53d6\u6d88\u5feb\u6377\u952e\u4fee\u6539\u3002");
    return true;
  }
  const shortcut = normalizeShortcut(event);
  if (!shortcut) {
    return true;
  }
  state.shortcuts[state.capturingShortcutAction] = shortcut;
  saveShortcuts();
  const label = shortcutLabels[state.capturingShortcutAction];
  state.capturingShortcutAction = null;
  renderShortcutList();
  setStatus(`\u5df2\u5c06\u300c${label}\u300d\u8bbe\u4e3a ${shortcut}`);
  return true;
}

function handleGlobalShortcuts(event) {
  if (handleShortcutCapture(event)) {
    return;
  }

  if (event.key === "Escape" && (state.selectedAnnotationId || state.inlineEditor)) {
    event.preventDefault();
    clearSelection();
    return;
  }

  const activeTag = document.activeElement?.tagName;
  if (["INPUT", "TEXTAREA", "SELECT"].includes(activeTag)) {
    return;
  }

  const pressed = normalizeShortcut(event);
  for (const action of shortcutActionOrder) {
    if (state.shortcuts[action] && state.shortcuts[action] === pressed) {
      event.preventDefault();
      runShortcutAction(action);
      return;
    }
  }
}

function bindEvents() {
  els.sessionForm.addEventListener("submit", createSession);
  els.pickRootDirBtn.addEventListener("click", pickRootDirectory);
  els.pickImportJsonBtn.addEventListener("click", pickImportJson);
  els.importAnnotationsBtn.addEventListener("click", importAnnotations);
  els.prevStudentBtn.addEventListener("click", () => moveStudent(-1));
  els.nextStudentBtn.addEventListener("click", () => moveStudent(1));
  els.prevPageBtn.addEventListener("click", () => goToPage(state.currentPage - 1));
  els.nextPageBtn.addEventListener("click", () => goToPage(state.currentPage + 1));
  els.zoomOutBtn.addEventListener("click", async () => {
    state.scale = Math.max(0.6, state.scale - 0.15);
    savePreferences();
    await renderCurrentPage();
  });
  els.zoomInBtn.addEventListener("click", async () => {
    state.scale = Math.min(3, state.scale + 0.15);
    savePreferences();
    await renderCurrentPage();
  });
  els.markInProgressBtn.addEventListener("click", () => updateStudentStatus("in_progress"));
  els.markDoneBtn.addEventListener("click", () => updateStudentStatus("done"));
  els.exportCurrentBtn.addEventListener("click", exportCurrent);
  els.exportAllBtn.addEventListener("click", exportAll);
  els.annotationLayer.addEventListener("click", createAnnotationAtClick);
  els.annotationLayer.addEventListener("contextmenu", (event) => {
    if (!state.viewport || !state.currentStudent || event.target !== els.annotationLayer) {
      return;
    }
    event.preventDefault();
    if (state.inlineEditor) {
      closeInlineEditor({ save: true });
    }
    if (state.selectedAnnotationId) {
      clearSelection({ render: false });
    }
    updateDraftStyleFromInputs();
    const [pdfX, pdfY] = getPdfPointFromLayerEvent(event);
    const returnTool = state.tool === "text" ? state.lastNonTextTool : state.tool;
    setTool("text");
    state.transientTextReturnTool = returnTool;
    createInlineAnnotationAtPdfPoint(pdfX, pdfY, "text", {
      initialText: state.draftText.trim(),
      returnTool,
      removeIfEmpty: true,
    });
  });
  els.toolButtons.forEach((button) => {
    button.addEventListener("click", () => {
      if (button.dataset.tool === "text") {
        enterPersistentTextMode();
        return;
      }
      setTool(button.dataset.tool);
    });
  });
  [els.draftColorInput, els.draftSizeInput, els.draftWeightInput, els.draftTextInput].forEach((input) => {
    input.addEventListener("input", updateDraftStyleFromInputs);
  });
  [els.rootDirInput, els.sessionNameInput].forEach((input) => {
    input.addEventListener("input", savePreferences);
  });

  els.selectedTextInput.addEventListener("input", () => {
    updateSelectedAnnotation((item) => {
      item.text = els.selectedTextInput.value;
    });
  });
  els.selectedColorInput.addEventListener("input", () => {
    updateSelectedAnnotation((item) => {
      item.style.color = els.selectedColorInput.value;
    });
  });
  els.selectedSizeInput.addEventListener("input", () => {
    updateSelectedAnnotation((item) => {
      item.style.font_size = Number(els.selectedSizeInput.value || 14);
    });
  });
  els.selectedWeightInput.addEventListener("change", () => {
    updateSelectedAnnotation((item) => {
      item.style.font_weight = els.selectedWeightInput.value;
    });
  });
  els.selectedXInput.addEventListener("input", () => {
    updateSelectedAnnotation((item) => {
      item.x = Number(els.selectedXInput.value || 0);
    });
  });
  els.selectedYInput.addEventListener("input", () => {
    updateSelectedAnnotation((item) => {
      item.y = roundNumber(getPageHeightPt() - Number(els.selectedYInput.value || 0));
    });
  });
  els.selectedWidthInput.addEventListener("input", () => {
    updateSelectedAnnotation((item) => {
      item.width = els.selectedWidthInput.value ? Number(els.selectedWidthInput.value) : null;
    });
  });
  els.selectedHeightInput.addEventListener("input", () => {
    updateSelectedAnnotation((item) => {
      item.height = els.selectedHeightInput.value ? Number(els.selectedHeightInput.value) : null;
    });
  });
  els.deleteAnnotationBtn.addEventListener("click", removeSelectedAnnotation);
  els.resetShortcutsBtn.addEventListener("click", () => {
    state.shortcuts = { ...defaultShortcuts };
    state.capturingShortcutAction = null;
    saveShortcuts();
    renderShortcutList();
    setStatus("\u5df2\u6062\u590d\u9ed8\u8ba4\u5feb\u6377\u952e\u3002");
  });

  document.addEventListener("keydown", handleGlobalShortcuts);
}

async function boot() {
  els.rootDirInput.value = initialPreferences.rootDir;
  els.sessionNameInput.value = initialPreferences.sessionName;
  els.draftColorInput.value = initialPreferences.draftStyle.color;
  els.draftSizeInput.value = initialPreferences.draftStyle.font_size;
  els.draftWeightInput.value = initialPreferences.draftStyle.font_weight;
  els.draftTextInput.value = initialPreferences.draftText;
  bindEvents();
  updateDraftStyleFromInputs();
  setTool(initialPreferences.tool);
  renderShortcutList();
  await loadSession();
}

boot();
