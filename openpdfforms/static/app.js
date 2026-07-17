const state = {
  documentId: null,
  filename: "",
  pageCount: 0,
  pageSizes: [],
  renderUrls: [],
  fields: [],
  selectedIds: new Set(),
  activeId: null,
  signatureMode: "draw",
  currentPage: 0,
  pendingType: null,
  zoom: 1,
  history: [],
  future: [],
  inspectorDirty: false,
};

const MAX_HISTORY = 50;

function snapshotFields() {
  return JSON.parse(JSON.stringify(state.fields));
}

function pushHistory() {
  state.history.push(snapshotFields());
  if (state.history.length > MAX_HISTORY) state.history.shift();
  state.future = [];
  refreshToolbarState();
}

function undo() {
  if (!state.history.length) return;
  state.future.push(snapshotFields());
  state.fields = state.history.pop();
  pruneSelection();
  renderFields();
  syncInspector();
  refreshToolbarState();
}

function redo() {
  if (!state.future.length) return;
  state.history.push(snapshotFields());
  state.fields = state.future.pop();
  pruneSelection();
  renderFields();
  syncInspector();
  refreshToolbarState();
}

function refreshToolbarState() {
  undoButton.disabled = !state.history.length;
  redoButton.disabled = !state.future.length;
  const count = state.selectedIds.size;
  deleteButton.disabled = count === 0;
  Object.values(alignButtons).forEach((button) => {
    button.disabled = count < 2;
  });
  distributeHButton.disabled = count < 3;
  distributeVButton.disabled = count < 3;
  duplicateButton.disabled = count < 1;
  duplicateAllPagesButton.disabled = count < 1;
}

function pruneSelection() {
  const ids = new Set(state.fields.map((field) => field.id));
  state.selectedIds.forEach((id) => {
    if (!ids.has(id)) state.selectedIds.delete(id);
  });
  if (state.activeId && !ids.has(state.activeId)) {
    state.activeId = state.selectedIds.size ? [...state.selectedIds].pop() : null;
  }
}

function generateId() {
  if (window.crypto && typeof window.crypto.randomUUID === "function") {
    return window.crypto.randomUUID();
  }
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (char) => {
    const random = (Math.random() * 16) | 0;
    const value = char === "x" ? random : (random & 0x3) | 0x8;
    return value.toString(16);
  });
}

const pages = document.querySelector("#pages");
const pdfInput = document.querySelector("#pdf-input");
const exportButton = document.querySelector("#export-button");
const saveProjectButton = document.querySelector("#save-project-button");
const openProjectButton = document.querySelector("#open-project-button");
const inspector = document.querySelector("#field-form");
const deleteButton = document.querySelector("#delete-field");
const signatureButton = document.querySelector("#signature-button");
const projectDialog = document.querySelector("#project-dialog");
const projectList = document.querySelector("#project-list");
const signatureDialog = document.querySelector("#signature-dialog");
const signatureCanvas = document.querySelector("#signature-canvas");
const signatureText = document.querySelector("#signature-text");
const signaturePreview = document.querySelector("#signature-preview");
const clearSignatureButton = document.querySelector("#clear-signature");
const applySignatureButton = document.querySelector("#apply-signature");
const signatureContext = signatureCanvas.getContext("2d");
const undoButton = document.querySelector("#undo-button");
const redoButton = document.querySelector("#redo-button");
const zoomOutButton = document.querySelector("#zoom-out");
const zoomInButton = document.querySelector("#zoom-in");
const zoomLevelLabel = document.querySelector("#zoom-level");
const alignButtons = {
  left: document.querySelector("#align-left"),
  right: document.querySelector("#align-right"),
  top: document.querySelector("#align-top"),
  bottom: document.querySelector("#align-bottom"),
  centerH: document.querySelector("#align-center-h"),
  centerV: document.querySelector("#align-center-v"),
};
const distributeHButton = document.querySelector("#distribute-h");
const distributeVButton = document.querySelector("#distribute-v");
const duplicateButton = document.querySelector("#duplicate-field");
const duplicateAllPagesButton = document.querySelector("#duplicate-all-pages");

function appUrl(path) {
  return new URL(path, window.location.href).toString();
}

pdfInput.addEventListener("change", async () => {
  const file = pdfInput.files[0];
  if (!file) return;
  const body = new FormData();
  body.append("file", file);
  pages.innerHTML = "<div class=\"empty\"><h2>Processing PDF...</h2></div>";
  const response = await fetch(appUrl("api/documents"), { method: "POST", body });
  if (!response.ok) {
    pages.innerHTML = `<div class="empty"><h2>Upload failed</h2><p>${await response.text()}</p></div>`;
    return;
  }
  const info = await response.json();
  loadDocumentInfo(info);
});

document.querySelectorAll("[data-add]").forEach((button) => {
  button.addEventListener("click", () => startPlacing(button.dataset.add));
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && state.pendingType) {
    stopPlacing();
    return;
  }
  const tag = event.target.tagName;
  const isFormField = tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT";
  if (isFormField || !(event.metaKey || event.ctrlKey)) return;
  const key = event.key.toLowerCase();
  if (key === "z" && event.shiftKey) {
    event.preventDefault();
    redo();
  } else if (key === "z") {
    event.preventDefault();
    undo();
  } else if (key === "y") {
    event.preventDefault();
    redo();
  }
});

exportButton.addEventListener("click", async () => {
  if (!state.documentId) return;
  const response = await fetch(appUrl(`api/documents/${state.documentId}/export`), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ fields: state.fields }),
  });
  if (!response.ok) {
    alert(await response.text());
    return;
  }
  const payload = await response.json();
  window.location.href = appUrl(payload.download_url);
});

saveProjectButton.addEventListener("click", saveProject);
openProjectButton.addEventListener("click", openProjectChooser);
signatureButton.addEventListener("click", openSignatureDialog);
clearSignatureButton.addEventListener("click", clearSignature);
applySignatureButton.addEventListener("click", applySignature);

document.querySelectorAll("[data-signature-tab]").forEach((button) => {
  button.addEventListener("click", () => setSignatureMode(button.dataset.signatureTab));
});

signatureText.addEventListener("input", () => {
  signaturePreview.textContent = signatureText.value;
});

signatureCanvas.addEventListener("pointerdown", startSignatureDraw);

inspector.addEventListener("input", () => {
  const field = selectedField();
  if (!field) return;
  if (!state.inspectorDirty) {
    pushHistory();
    state.inspectorDirty = true;
  }
  const data = new FormData(inspector);
  field.name = data.get("name") || field.name;
  field.label = data.get("label") || "";
  field.tooltip = field.label;
  field.type = data.get("type") || field.type;
  field.x = numberValue(data.get("x"), field.x);
  field.y = numberValue(data.get("y"), field.y);
  field.width = Math.max(1, numberValue(data.get("width"), field.width));
  field.height = Math.max(1, numberValue(data.get("height"), field.height));
  field.options = (data.get("options") || "").split("\n").map((value) => value.trim()).filter(Boolean);
  field.required = data.get("required") === "on";
  field.group = data.get("group") || "";
  field.font_size = Math.max(1, numberValue(data.get("font_size"), field.font_size || 10));
  field.max_length = Math.max(0, Math.round(numberValue(data.get("max_length"), field.max_length || 0)));
  field.multiline = data.get("multiline") === "on";
  field.comb = data.get("comb") === "on";
  field.border_color = data.get("border_color_on") === "on" ? data.get("border_color") : "";
  field.background_color = data.get("background_color_on") === "on" ? data.get("background_color") : "";
  field.format = data.get("format") || "";
  field.calc_operation = data.get("calc_operation") || "";
  field.calc_fields = (data.get("calc_fields") || "").split(",").map((value) => value.trim()).filter(Boolean);
  renderFields();
});

deleteButton.addEventListener("click", () => {
  if (!state.selectedIds.size) return;
  pushHistory();
  state.fields = state.fields.filter((field) => !state.selectedIds.has(field.id));
  state.selectedIds.clear();
  state.activeId = null;
  syncInspector();
  renderFields();
  refreshToolbarState();
});

undoButton.addEventListener("click", undo);
redoButton.addEventListener("click", redo);

alignButtons.left.addEventListener("click", () => alignSelection("left"));
alignButtons.right.addEventListener("click", () => alignSelection("right"));
alignButtons.top.addEventListener("click", () => alignSelection("top"));
alignButtons.bottom.addEventListener("click", () => alignSelection("bottom"));
alignButtons.centerH.addEventListener("click", () => alignSelection("centerH"));
alignButtons.centerV.addEventListener("click", () => alignSelection("centerV"));
distributeHButton.addEventListener("click", () => distributeSelection("horizontal"));
distributeVButton.addEventListener("click", () => distributeSelection("vertical"));
duplicateButton.addEventListener("click", duplicateSelection);
duplicateAllPagesButton.addEventListener("click", duplicateSelectionToAllPages);

const ZOOM_MIN = 0.5;
const ZOOM_MAX = 2;
const ZOOM_BASE_WIDTH = 980;

zoomInButton.addEventListener("click", () => {
  state.zoom = Math.min(ZOOM_MAX, Math.round((state.zoom + 0.1) * 10) / 10);
  applyZoom();
});

zoomOutButton.addEventListener("click", () => {
  state.zoom = Math.max(ZOOM_MIN, Math.round((state.zoom - 0.1) * 10) / 10);
  applyZoom();
});

function applyZoom() {
  document.querySelectorAll(".page img").forEach((img) => {
    if (state.zoom === 1) {
      img.style.width = "";
      img.style.maxWidth = "";
    } else {
      img.style.maxWidth = "none";
      img.style.width = `${ZOOM_BASE_WIDTH * state.zoom}px`;
    }
  });
  zoomLevelLabel.textContent = `${Math.round(state.zoom * 100)}%`;
  zoomOutButton.disabled = state.zoom <= ZOOM_MIN;
  zoomInButton.disabled = state.zoom >= ZOOM_MAX;
  renderFields();
}

function alignSelection(mode) {
  const fields = selectedFields();
  const anchor = selectedField();
  if (fields.length < 2 || !anchor) return;
  pushHistory();
  fields.forEach((field) => {
    if (field.id === anchor.id) return;
    switch (mode) {
      case "left":
        field.x = anchor.x;
        break;
      case "right":
        field.x = anchor.x + anchor.width - field.width;
        break;
      case "top":
        field.y = anchor.y;
        break;
      case "bottom":
        field.y = anchor.y + anchor.height - field.height;
        break;
      case "centerH":
        field.x = anchor.x + anchor.width / 2 - field.width / 2;
        break;
      case "centerV":
        field.y = anchor.y + anchor.height / 2 - field.height / 2;
        break;
    }
    field.x = Math.max(0, field.x);
    field.y = Math.max(0, field.y);
  });
  renderFields();
}

function distributeSelection(axis) {
  const fields = selectedFields();
  if (fields.length < 3) return;
  pushHistory();
  if (axis === "horizontal") {
    fields.sort((a, b) => a.x - b.x);
    const first = fields[0];
    const last = fields[fields.length - 1];
    const span = last.x - first.x;
    const step = span / (fields.length - 1);
    fields.forEach((field, index) => {
      if (index === 0 || index === fields.length - 1) return;
      field.x = first.x + step * index;
    });
  } else {
    fields.sort((a, b) => a.y - b.y);
    const first = fields[0];
    const last = fields[fields.length - 1];
    const span = last.y - first.y;
    const step = span / (fields.length - 1);
    fields.forEach((field, index) => {
      if (index === 0 || index === fields.length - 1) return;
      field.y = first.y + step * index;
    });
  }
  renderFields();
}

function duplicateSelection() {
  const fields = selectedFields();
  if (!fields.length) return;
  pushHistory();
  const offset = 14;
  const newIds = [];
  fields.forEach((field) => {
    const id = generateId();
    newIds.push(id);
    state.fields.push({
      ...field,
      id,
      x: field.x + offset,
      y: field.y + offset,
      name: `${field.name}_copy`,
    });
  });
  state.selectedIds = new Set(newIds);
  state.activeId = newIds[newIds.length - 1];
  afterSelectionChange();
}

function duplicateSelectionToAllPages() {
  const fields = selectedFields();
  if (!fields.length || !state.pageCount) return;
  pushHistory();
  const newIds = [];
  for (let page = 0; page < state.pageCount; page += 1) {
    fields.forEach((field) => {
      if (field.page === page) return;
      const id = generateId();
      newIds.push(id);
      state.fields.push({
        ...field,
        id,
        page,
      });
    });
  }
  if (newIds.length) {
    state.selectedIds = new Set(newIds);
    state.activeId = newIds[newIds.length - 1];
  }
  afterSelectionChange();
}

function loadDocumentInfo(info) {
  state.documentId = info.document_id;
  state.filename = info.filename;
  state.pageCount = info.page_count;
  state.pageSizes = info.page_sizes;
  state.renderUrls = info.render_urls;
  state.fields = info.fields;
  state.selectedIds.clear();
  state.activeId = null;
  state.currentPage = 0;
  state.history = [];
  state.future = [];
  state.zoom = 1;
  exportButton.disabled = false;
  saveProjectButton.disabled = false;
  renderDocument(info.render_urls);
  applyZoom();
  syncInspector();
  refreshToolbarState();
}

function renderDocument(renderUrls) {
  pages.innerHTML = "";
  renderUrls.forEach((url, pageIndex) => {
    const page = document.createElement("div");
    page.className = "page";
    page.dataset.page = pageIndex;
    page.addEventListener("click", (event) => {
      if (state.pendingType) {
        placeField(state.pendingType, page, pageIndex, event);
        return;
      }
      state.currentPage = pageIndex;
      if (!event.shiftKey) clearSelection();
    });
    const img = document.createElement("img");
    img.src = url;
    img.draggable = false;
    img.onload = renderFields;
    page.appendChild(img);
    pages.appendChild(page);
  });
}

function renderFields() {
  document.querySelectorAll(".field").forEach((element) => element.remove());
  state.fields.forEach((field) => {
    const page = document.querySelector(`.page[data-page="${field.page}"]`);
    if (!page) return;
    const img = page.querySelector("img");
    const [pdfWidth, pdfHeight] = state.pageSizes[field.page];
    const scaleX = img.clientWidth / pdfWidth;
    const scaleY = img.clientHeight / pdfHeight;

    const element = document.createElement("div");
    element.className = `field${state.selectedIds.has(field.id) ? " is-selected" : ""}${field.id === state.activeId ? " is-active" : ""}`;
    element.dataset.id = field.id;
    element.dataset.type = field.type;
    element.dataset.name = field.name;
    element.style.left = `${field.x * scaleX}px`;
    element.style.top = `${field.y * scaleY}px`;
    element.style.width = `${field.width * scaleX}px`;
    element.style.height = `${field.height * scaleY}px`;
    element.addEventListener("pointerdown", startDrag);
    element.addEventListener("click", (event) => {
      event.stopPropagation();
      if (event.shiftKey) {
        toggleSelect(field.id);
      } else {
        selectOnly(field.id);
      }
    });
    if (field.type === "signature" && field.signature_data_url) {
      const image = document.createElement("img");
      image.className = "signature-image";
      image.src = field.signature_data_url;
      element.appendChild(image);
    }
    page.appendChild(element);
  });
}

function startDrag(event) {
  const element = event.currentTarget;
  const field = state.fields.find((item) => item.id === element.dataset.id);
  if (!field) return;
  if (!state.selectedIds.has(field.id)) {
    selectOnly(field.id);
  } else {
    state.activeId = field.id;
    state.currentPage = field.page;
    syncInspector();
  }

  const startX = event.clientX;
  const startY = event.clientY;

  const draggedFields = state.fields.filter((item) => state.selectedIds.has(item.id));
  const dragInfo = new Map(
    draggedFields.map((item) => {
      const itemPage = document.querySelector(`.page[data-page="${item.page}"]`);
      const itemImg = itemPage.querySelector("img");
      const [pdfWidth, pdfHeight] = state.pageSizes[item.page];
      return [
        item.id,
        {
          origin: { x: item.x, y: item.y },
          scaleX: itemImg.clientWidth / pdfWidth,
          scaleY: itemImg.clientHeight / pdfHeight,
          element: document.querySelector(`.field[data-id="${item.id}"]`),
        },
      ];
    })
  );
  pushHistory();

  const move = (moveEvent) => {
    draggedFields.forEach((item) => {
      const info = dragInfo.get(item.id);
      const dx = (moveEvent.clientX - startX) / info.scaleX;
      const dy = (moveEvent.clientY - startY) / info.scaleY;
      item.x = Math.max(0, info.origin.x + dx);
      item.y = Math.max(0, info.origin.y + dy);
      if (info.element) {
        info.element.style.left = `${item.x * info.scaleX}px`;
        info.element.style.top = `${item.y * info.scaleY}px`;
      }
    });
  };
  const up = () => {
    document.removeEventListener("pointermove", move);
    document.removeEventListener("pointerup", up);
  };
  document.addEventListener("pointermove", move);
  document.addEventListener("pointerup", up);
}

function startPlacing(type) {
  if (!state.documentId) return;
  state.pendingType = type;
  pages.classList.add("placing");
  document.querySelectorAll("[data-add]").forEach((button) => {
    button.classList.toggle("is-active", button.dataset.add === type);
  });
}

function stopPlacing() {
  state.pendingType = null;
  pages.classList.remove("placing");
  document.querySelectorAll("[data-add]").forEach((button) => {
    button.classList.remove("is-active");
  });
}

function placeField(type, pageElement, pageIndex, event) {
  const img = pageElement.querySelector("img");
  const rect = img.getBoundingClientRect();
  const [pdfWidth, pdfHeight] = state.pageSizes[pageIndex];
  const scaleX = img.clientWidth / pdfWidth;
  const scaleY = img.clientHeight / pdfHeight;
  const width = type === "checkbox" || type === "radio" ? 14 : 160;
  const height = type === "checkbox" || type === "radio" ? 14 : 20;
  const x = Math.max(0, (event.clientX - rect.left) / scaleX - width / 2);
  const y = Math.max(0, (event.clientY - rect.top) / scaleY - height / 2);
  const id = generateId();
  pushHistory();
  state.fields.push({
    id,
    page: pageIndex,
    type,
    name: `${type}_${state.fields.length + 1}`,
    x,
    y,
    width,
    height,
    label: "",
    tooltip: "",
    required: false,
    options: [],
    group: "",
    value: "",
    signature_data_url: "",
  });
  state.currentPage = pageIndex;
  stopPlacing();
  selectOnly(id);
}

function selectOnly(id) {
  state.selectedIds = new Set([id]);
  state.activeId = id;
  afterSelectionChange();
}

function toggleSelect(id) {
  if (state.selectedIds.has(id)) {
    state.selectedIds.delete(id);
    if (state.activeId === id) {
      state.activeId = state.selectedIds.size ? [...state.selectedIds].pop() : null;
    }
  } else {
    state.selectedIds.add(id);
    state.activeId = id;
  }
  afterSelectionChange();
}

function clearSelection() {
  if (!state.selectedIds.size && !state.activeId) return;
  state.selectedIds.clear();
  state.activeId = null;
  afterSelectionChange();
}

function afterSelectionChange() {
  const field = selectedField();
  if (field) state.currentPage = field.page;
  state.inspectorDirty = false;
  syncInspector();
  renderFields();
  refreshToolbarState();
}

function selectedField() {
  return state.fields.find((field) => field.id === state.activeId);
}

function selectedFields() {
  return state.fields.filter((field) => state.selectedIds.has(field.id));
}

function syncInspector() {
  const field = selectedField();
  inspector.name.value = field?.name || "";
  inspector.label.value = field?.label || "";
  inspector.type.value = field?.type || "text";
  inspector.x.value = field ? round(field.x) : "";
  inspector.y.value = field ? round(field.y) : "";
  inspector.width.value = field ? round(field.width) : "";
  inspector.height.value = field ? round(field.height) : "";
  inspector.options.value = field?.options?.join("\n") || "";
  inspector.required.checked = Boolean(field?.required);
  inspector.group.value = field?.group || "";
  inspector.font_size.value = field ? field.font_size || 10 : "";
  inspector.max_length.value = field ? field.max_length || 0 : "";
  inspector.multiline.checked = Boolean(field?.multiline);
  inspector.comb.checked = Boolean(field?.comb);
  inspector.border_color_on.checked = Boolean(field?.border_color);
  inspector.border_color.value = field?.border_color || "#1769aa";
  inspector.background_color_on.checked = Boolean(field?.background_color);
  inspector.background_color.value = field?.background_color || "#ffffff";
  inspector.format.value = field?.format || "";
  inspector.calc_operation.value = field?.calc_operation || "";
  inspector.calc_fields.value = field?.calc_fields?.join(", ") || "";
  signatureButton.disabled = field?.type !== "signature";

  const groupNames = [...new Set(state.fields.filter((item) => item.type === "radio" && item.group).map((item) => item.group))];
  const datalist = document.querySelector("#group-suggestions");
  datalist.innerHTML = groupNames.map((name) => `<option value="${escapeHtml(name)}"></option>`).join("");
}

function numberValue(value, fallback) {
  const parsed = Number.parseFloat(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function round(value) {
  return Math.round(value * 10) / 10;
}

async function saveProject() {
  if (!state.documentId) return;
  const response = await fetch(appUrl(`api/projects/${state.documentId}`), {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      filename: state.filename,
      page_count: state.pageCount,
      page_sizes: state.pageSizes,
      render_urls: state.renderUrls,
      fields: state.fields,
    }),
  });
  if (!response.ok) {
    alert(await response.text());
    return;
  }
  const saved = await response.json();
  saveProjectButton.textContent = "Saved";
  setTimeout(() => {
    saveProjectButton.textContent = "Save Project";
  }, 1400);
  document.title = `OpenPDFForms - ${saved.filename}`;
}

async function openProjectChooser() {
  const response = await fetch(appUrl("api/projects"));
  if (!response.ok) {
    alert(await response.text());
    return;
  }
  const projects = await response.json();
  projectList.innerHTML = "";
  if (!projects.length) {
    projectList.innerHTML = "<div class=\"empty\"><p>No saved projects yet.</p></div>";
  }
  projects.forEach((project) => {
    const item = document.createElement("article");
    item.className = "project-item";
    const info = document.createElement("div");
    info.innerHTML = `<strong>${escapeHtml(project.filename)}</strong><span>${new Date(project.updated_at).toLocaleString()}</span>`;
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = "Open";
    button.addEventListener("click", () => openProject(project.document_id));
    item.append(info, button);
    projectList.appendChild(item);
  });
  projectDialog.showModal();
}

async function openProject(documentId) {
  const response = await fetch(appUrl(`api/projects/${documentId}`));
  if (!response.ok) {
    alert(await response.text());
    return;
  }
  loadDocumentInfo(await response.json());
  projectDialog.close();
}

function openSignatureDialog() {
  const field = selectedField();
  if (!field || field.type !== "signature") return;
  clearSignature();
  if (field.signature_data_url) {
    const image = new Image();
    image.onload = () => {
      signatureContext.drawImage(image, 0, 0, signatureCanvas.width, signatureCanvas.height);
    };
    image.src = field.signature_data_url;
  }
  signatureDialog.showModal();
}

function setSignatureMode(mode) {
  state.signatureMode = mode;
  document.querySelectorAll("[data-signature-tab]").forEach((button) => {
    button.classList.toggle("is-active", button.dataset.signatureTab === mode);
  });
  document.querySelector("#signature-draw-panel").hidden = mode !== "draw";
  document.querySelector("#signature-type-panel").hidden = mode !== "type";
}

function clearSignature() {
  signatureContext.clearRect(0, 0, signatureCanvas.width, signatureCanvas.height);
  signatureText.value = "";
  signaturePreview.textContent = "";
}

function startSignatureDraw(event) {
  if (state.signatureMode !== "draw") return;
  const rect = signatureCanvas.getBoundingClientRect();
  signatureContext.lineWidth = 4;
  signatureContext.lineCap = "round";
  signatureContext.lineJoin = "round";
  signatureContext.strokeStyle = "#111827";
  signatureContext.beginPath();
  signatureContext.moveTo((event.clientX - rect.left) * signatureCanvas.width / rect.width, (event.clientY - rect.top) * signatureCanvas.height / rect.height);
  signatureCanvas.setPointerCapture(event.pointerId);

  const draw = (moveEvent) => {
    signatureContext.lineTo((moveEvent.clientX - rect.left) * signatureCanvas.width / rect.width, (moveEvent.clientY - rect.top) * signatureCanvas.height / rect.height);
    signatureContext.stroke();
  };
  const stop = () => {
    signatureCanvas.removeEventListener("pointermove", draw);
    signatureCanvas.removeEventListener("pointerup", stop);
  };
  signatureCanvas.addEventListener("pointermove", draw);
  signatureCanvas.addEventListener("pointerup", stop);
}

function applySignature() {
  const field = selectedField();
  if (!field || field.type !== "signature") return;
  field.signature_data_url = state.signatureMode === "type" ? typedSignatureDataUrl() : signatureCanvas.toDataURL("image/png");
  signatureDialog.close();
  renderFields();
}

function typedSignatureDataUrl() {
  const canvas = document.createElement("canvas");
  canvas.width = 900;
  canvas.height = 260;
  const context = canvas.getContext("2d");
  context.clearRect(0, 0, canvas.width, canvas.height);
  context.fillStyle = "#111827";
  context.font = "92px Snell Roundhand, Brush Script MT, Segoe Script, cursive";
  context.textBaseline = "middle";
  context.fillText(signatureText.value || "Signature", 36, canvas.height / 2);
  return canvas.toDataURL("image/png");
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#039;",
  }[char]));
}
