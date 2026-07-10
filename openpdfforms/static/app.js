const state = {
  documentId: null,
  pageSizes: [],
  fields: [],
  selectedId: null,
};

const pages = document.querySelector("#pages");
const pdfInput = document.querySelector("#pdf-input");
const exportButton = document.querySelector("#export-button");
const inspector = document.querySelector("#field-form");
const deleteButton = document.querySelector("#delete-field");

pdfInput.addEventListener("change", async () => {
  const file = pdfInput.files[0];
  if (!file) return;
  const body = new FormData();
  body.append("file", file);
  pages.innerHTML = "<div class=\"empty\"><h2>Processing PDF...</h2></div>";
  const response = await fetch("/api/documents", { method: "POST", body });
  if (!response.ok) {
    pages.innerHTML = `<div class="empty"><h2>Upload failed</h2><p>${await response.text()}</p></div>`;
    return;
  }
  const info = await response.json();
  state.documentId = info.document_id;
  state.pageSizes = info.page_sizes;
  state.fields = info.fields;
  state.selectedId = null;
  exportButton.disabled = false;
  renderDocument(info.render_urls);
});

document.querySelectorAll("[data-add]").forEach((button) => {
  button.addEventListener("click", () => addField(button.dataset.add));
});

exportButton.addEventListener("click", async () => {
  if (!state.documentId) return;
  const response = await fetch(`/api/documents/${state.documentId}/export`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ fields: state.fields }),
  });
  if (!response.ok) {
    alert(await response.text());
    return;
  }
  const payload = await response.json();
  window.location.href = payload.download_url;
});

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

function renderDocument(renderUrls) {
  pages.innerHTML = "";
  renderUrls.forEach((url, pageIndex) => {
    const page = document.createElement("div");
    page.className = "page";
    page.dataset.page = pageIndex;
    const img = document.createElement("img");
    img.src = url;
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
    page.appendChild(element);
  });
}

function startDrag(event) {
  const element = event.currentTarget;
  const field = state.fields.find((item) => item.id === element.dataset.id);
  if (!field) return;
  selectField(field.id);
  const page = element.closest(".page");
  const img = page.querySelector("img");
  const [pdfWidth, pdfHeight] = state.pageSizes[field.page];
  const scaleX = img.clientWidth / pdfWidth;
  const scaleY = img.clientHeight / pdfHeight;
  const startX = event.clientX;
  const startY = event.clientY;
  const original = { x: field.x, y: field.y };
  element.setPointerCapture(event.pointerId);

  const move = (moveEvent) => {
    field.x = Math.max(0, original.x + (moveEvent.clientX - startX) / scaleX);
    field.y = Math.max(0, original.y + (moveEvent.clientY - startY) / scaleY);
    renderFields();
  };
  const up = () => {
    element.removeEventListener("pointermove", move);
    element.removeEventListener("pointerup", up);
  };
  element.addEventListener("pointermove", move);
  element.addEventListener("pointerup", up);
}

function addField(type) {
  if (!state.documentId) return;
  const page = 0;
  const id = crypto.randomUUID();
  state.fields.push({
    id,
    page,
    type,
    name: `${type}_${state.fields.length + 1}`,
    x: 72,
    y: 72,
    width: type === "checkbox" || type === "radio" ? 14 : 160,
    height: type === "checkbox" || type === "radio" ? 14 : 20,
    label: "",
    tooltip: "",
    required: false,
    options: [],
    group: "",
  });
  selectField(id);
  renderFields();
}

function selectField(id) {
  state.selectedId = id;
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
}

function numberValue(value, fallback) {
  const parsed = Number.parseFloat(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function round(value) {
  return Math.round(value * 10) / 10;
}
