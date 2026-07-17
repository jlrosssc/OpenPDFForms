const state = {
  documentId: null,
  filename: "",
  pageCount: 0,
  pageSizes: [],
  renderUrls: [],
  fields: [],
  selectedId: null,
  signatureMode: "draw",
  currentPage: 0,
  pendingType: null,
};

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
  renderFields();
});

deleteButton.addEventListener("click", () => {
  if (!state.selectedId) return;
  state.fields = state.fields.filter((field) => field.id !== state.selectedId);
  state.selectedId = null;
  syncInspector();
  renderFields();
});

function loadDocumentInfo(info) {
  state.documentId = info.document_id;
  state.filename = info.filename;
  state.pageCount = info.page_count;
  state.pageSizes = info.page_sizes;
  state.renderUrls = info.render_urls;
  state.fields = info.fields;
  state.selectedId = null;
  state.currentPage = 0;
  exportButton.disabled = false;
  saveProjectButton.disabled = false;
  renderDocument(info.render_urls);
  syncInspector();
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
    element.className = `field${field.id === state.selectedId ? " is-selected" : ""}`;
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
      selectField(field.id);
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
  if (state.selectedId !== field.id) {
    state.selectedId = field.id;
    state.currentPage = field.page;
    syncInspector();
    document.querySelectorAll(".field").forEach((el) => {
      el.classList.toggle("is-selected", el.dataset.id === field.id);
    });
  }
  const page = element.closest(".page");
  const img = page.querySelector("img");
  const [pdfWidth, pdfHeight] = state.pageSizes[field.page];
  const scaleX = img.clientWidth / pdfWidth;
  const scaleY = img.clientHeight / pdfHeight;
  const startX = event.clientX;
  const startY = event.clientY;
  const original = { x: field.x, y: field.y };

  const move = (moveEvent) => {
    field.x = Math.max(0, original.x + (moveEvent.clientX - startX) / scaleX);
    field.y = Math.max(0, original.y + (moveEvent.clientY - startY) / scaleY);
    element.style.left = `${field.x * scaleX}px`;
    element.style.top = `${field.y * scaleY}px`;
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
  selectField(id);
  renderFields();
}

function selectField(id) {
  state.selectedId = id;
  const field = selectedField();
  if (field) state.currentPage = field.page;
  syncInspector();
  renderFields();
}

function selectedField() {
  return state.fields.find((field) => field.id === state.selectedId);
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
  signatureButton.disabled = field?.type !== "signature";
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
