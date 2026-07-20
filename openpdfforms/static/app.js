const state = {
  documentId: null,
  filename: "",
  pageCount: 0,
  pageSizes: [],
  renderUrls: [],
  fields: [],
  selectedIds: new Set(),
  activeId: null,
  signatureMode: "type",
  currentPage: 0,
  pendingType: null,
  zoom: 1,
  history: [],
  future: [],
  inspectorDirty: false,
  mode: "design",
  pendingSignField: null,
  signedFields: new Set(),
  suppressNextPageClick: false,
  radioGroupHotkeyActive: false,
  radioGroupHotkeyDown: false,
  activeRadioPlacementGroup: "",
  nextRadioPlacementGroup: 1,
  textSplitCount: 1,
  currentUser: null,
  previewValues: null,
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

function fieldNamePrefix(type) {
  return {
    text: "text",
    date: "date",
    checkbox: "checkbox",
    radio: "radio",
    dropdown: "dropdown",
    listbox: "listbox",
    button: "button",
    static_text: "static",
    whiteout: "whiteout",
    signature: "signature",
    initials: "initials",
    digital_signature: "esign",
  }[type] || "field";
}

function isGeneratedFieldName(name) {
  return /^(text|date|checkbox|radio|dropdown|listbox|button|static|whiteout|signature|initials|esign|digital_signature|field)_\d+$/.test(name || "");
}

function generatedFieldName(type, count) {
  return `${fieldNamePrefix(type)}_${count}`;
}

function nextGeneratedFieldName(type) {
  const prefix = fieldNamePrefix(type);
  let max = 0;
  state.fields.forEach((field) => {
    if (fieldNamePrefix(field.type) !== prefix) return;
    const match = String(field.name || "").match(new RegExp(`^${prefix}_(\\d+)$`));
    if (match) max = Math.max(max, Number(match[1]));
  });
  return generatedFieldName(type, max + 1);
}

function normalizeGeneratedFieldNames(fields) {
  const counts = {};
  return fields.map((field) => {
    const prefix = fieldNamePrefix(field.type);
    counts[prefix] = (counts[prefix] || 0) + 1;
    if (!field.name || isGeneratedFieldName(field.name)) {
      field.name = generatedFieldName(field.type, counts[prefix]);
    }
    return field;
  });
}

const pages = document.querySelector("#pages");
const pdfInput = document.querySelector("#pdf-input");
const newBlankButton = document.querySelector("#new-blank-button");
const blankDialog = document.querySelector("#blank-dialog");
const blankFilename = document.querySelector("#blank-filename");
const blankPageSize = document.querySelector("#blank-page-size");
const blankOrientation = document.querySelector("#blank-orientation");
const blankPageCount = document.querySelector("#blank-page-count");
const createBlankButton = document.querySelector("#create-blank-button");
const previewButton = document.querySelector("#preview-button");
const previewDialog = document.querySelector("#preview-dialog");
const previewPages = document.querySelector("#preview-pages");
const exportButton = document.querySelector("#export-button");
const saveProjectButton = document.querySelector("#save-project-button");
const openProjectButton = document.querySelector("#open-project-button");
const inspector = document.querySelector("#field-form");
const deleteButton = document.querySelector("#delete-field");
const scriptTestResult = document.querySelector("#script-test-result");
const buttonScriptBlock = document.querySelector("#button-script-block");
const generatedConditionScript = document.querySelector("#generated-condition-script");
const useGeneratedConditionScriptButton = document.querySelector("#use-generated-condition-script");
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
const fillModeButton = document.querySelector("#fill-mode-button");
const fillModePanel = document.querySelector("#fill-mode-panel");
const backToDesignButton = document.querySelector("#back-to-design-button");
const downloadWorkingButton = document.querySelector("#download-working-button");
const addFieldPanel = document.querySelector("#add-field-panel");
const arrangeGroupPanel = document.querySelector("#arrange-group");
const fieldContextMenu = document.querySelector("#field-context-menu");
const conditionRows = document.querySelector("#condition-rows");
const addConditionButton = document.querySelector("#add-condition");
const esignDialog = document.querySelector("#esign-dialog");
const esignNameInput = document.querySelector("#esign-name");
const esignReasonInput = document.querySelector("#esign-reason");
const esignLocationInput = document.querySelector("#esign-location");
const confirmEsignButton = document.querySelector("#confirm-esign");
const userAdminButton = document.querySelector("#user-admin-button");
const userDialog = document.querySelector("#user-dialog");
const userList = document.querySelector("#user-list");
const newUsername = document.querySelector("#new-username");
const newPassword = document.querySelector("#new-password");
const newIsAdmin = document.querySelector("#new-is-admin");
const createUserButton = document.querySelector("#create-user-button");

function appUrl(path) {
  return new URL(path, window.location.href).toString();
}

async function loadCurrentUser() {
  const response = await fetch(appUrl("api/me"));
  if (!response.ok) return;
  state.currentUser = await response.json();
  userAdminButton.hidden = !state.currentUser.is_admin;
}

async function openUserAdmin() {
  if (!state.currentUser?.is_admin) return;
  await refreshUsers();
  userDialog.showModal();
}

async function refreshUsers() {
  const response = await fetch(appUrl("api/users"));
  if (!response.ok) {
    alert(await response.text());
    return;
  }
  const users = await response.json();
  userList.innerHTML = users
    .map(
      (user) => `
      <article class="user-row" data-user-id="${user.id}">
        <div><strong>${escapeHtml(user.username)}</strong><span>${user.is_admin ? "Admin" : "User"} · ${user.active ? "Active" : "Disabled"}</span></div>
        <button type="button" data-user-action="toggle-admin">${user.is_admin ? "Remove Admin" : "Make Admin"}</button>
        <button type="button" data-user-action="toggle-active">${user.active ? "Disable" : "Enable"}</button>
        <button type="button" data-user-action="reset-password">Reset Password</button>
        <button type="button" data-user-action="delete">Delete</button>
      </article>`
    )
    .join("");
}

async function createUserFromDialog() {
  const payload = {
    username: newUsername.value.trim(),
    password: newPassword.value,
    is_admin: newIsAdmin.checked,
    active: true,
  };
  const response = await fetch(appUrl("api/users"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    alert(await response.text());
    return;
  }
  newUsername.value = "";
  newPassword.value = "";
  newIsAdmin.checked = false;
  await refreshUsers();
}

userList.addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-user-action]");
  if (!button) return;
  const row = button.closest(".user-row");
  const userId = row.dataset.userId;
  const action = button.dataset.userAction;
  const username = row.querySelector("strong").textContent;
  let method = "PATCH";
  let payload = {};
  if (action === "toggle-admin") {
    payload.is_admin = button.textContent === "Make Admin";
  } else if (action === "toggle-active") {
    payload.active = button.textContent === "Enable";
  } else if (action === "reset-password") {
    const password = prompt(`New password for ${username}`);
    if (!password) return;
    payload.password = password;
  } else if (action === "delete") {
    if (!confirm(`Delete ${username}?`)) return;
    method = "DELETE";
  }
  const response = await fetch(appUrl(`api/users/${userId}`), {
    method,
    headers: { "Content-Type": "application/json" },
    body: method === "DELETE" ? undefined : JSON.stringify(payload),
  });
  if (!response.ok) {
    alert(await response.text());
    return;
  }
  await refreshUsers();
});

loadCurrentUser();

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

newBlankButton.addEventListener("click", () => {
  blankDialog.showModal();
});

createBlankButton.addEventListener("click", createBlankDocument);

async function createBlankDocument() {
  const payload = {
    filename: blankFilename.value.trim() || "Blank Form.pdf",
    page_size: blankPageSize.value || "letter",
    orientation: blankOrientation.value || "portrait",
    page_count: Math.max(1, Math.min(50, Math.round(numberValue(blankPageCount.value, 1)))),
  };
  pages.innerHTML = "<div class=\"empty\"><h2>Creating blank form...</h2></div>";
  const response = await fetch(appUrl("api/documents/blank"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    pages.innerHTML = `<div class="empty"><h2>Create failed</h2><p>${await response.text()}</p></div>`;
    return;
  }
  blankDialog.close();
  loadDocumentInfo(await response.json());
}

document.querySelectorAll("[data-add]").forEach((button) => {
  button.addEventListener("click", () => startPlacing(button.dataset.add));
  button.addEventListener("dblclick", () => startPlacing(button.dataset.add, true));
  button.addEventListener("pointerdown", (event) => {
    if (event.button !== 0) return;
    dragPlace = { type: button.dataset.add, startX: event.clientX, startY: event.clientY, moved: false, pointerId: event.pointerId };
    button.setPointerCapture(event.pointerId);
  });
});

// Supports pressing a field button and dragging straight onto the document in one
// motion. A plain click still arms click-then-click placement via the listener
// above -- native click semantics only fire on matching mousedown+mouseup targets,
// so this never double-places: a drag's mouseup lands off the button entirely.
let dragPlace = null;

document.addEventListener("pointermove", (event) => {
  if (!dragPlace || dragPlace.pointerId !== event.pointerId) return;
  if (dragPlace.moved) return;
  const dx = event.clientX - dragPlace.startX;
  const dy = event.clientY - dragPlace.startY;
  if (Math.hypot(dx, dy) <= 6) return;
  dragPlace.moved = true;
  pages.classList.add("placing");
  document.querySelectorAll("[data-add]").forEach((button) => {
    button.classList.toggle("is-active", button.dataset.add === dragPlace.type);
  });
});

document.addEventListener("pointerup", (event) => {
  if (!dragPlace || dragPlace.pointerId !== event.pointerId) return;
  if (dragPlace.moved) {
    const target = document.elementFromPoint(event.clientX, event.clientY);
    const pageElement = target ? target.closest(".page") : null;
    if (pageElement && state.documentId) {
      placeField(dragPlace.type, pageElement, Number(pageElement.dataset.page), event);
    }
    stopPlacing();
  }
  dragPlace = null;
});

document.addEventListener("pointercancel", (event) => {
  if (!dragPlace || dragPlace.pointerId !== event.pointerId) return;
  if (dragPlace.moved) stopPlacing();
  dragPlace = null;
});

document.addEventListener("keydown", (event) => {
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "g" && radioGroupingAvailable()) {
    event.preventDefault();
    if (!state.radioGroupHotkeyDown) {
      state.radioGroupHotkeyDown = true;
      startRadioPlacementGroup();
    }
    return;
  }
  if ((event.ctrlKey || event.metaKey) && /^[2-9]$/.test(event.key) && textSplitAvailable()) {
    event.preventDefault();
    state.textSplitCount = Number(event.key);
    return;
  }
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

document.addEventListener("keyup", (event) => {
  if (!state.radioGroupHotkeyDown) return;
  if (event.key.toLowerCase() === "g" || event.key === "Control" || event.key === "Meta") {
    endRadioPlacementGroup();
  }
});

previewButton.addEventListener("click", () => {
  if (!state.documentId) return;
  previewDialog.showModal();
  renderInteractivePreview();
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
clearSignatureButton.addEventListener("click", clearSignature);
applySignatureButton.addEventListener("click", confirmMockSign);
confirmEsignButton.addEventListener("click", confirmEsign);
userAdminButton.addEventListener("click", openUserAdmin);
createUserButton.addEventListener("click", createUserFromDialog);
fillModeButton.addEventListener("click", enterFillMode);
backToDesignButton.addEventListener("click", exitFillMode);
downloadWorkingButton.addEventListener("click", () => {
  if (!state.documentId) return;
  window.location.href = appUrl(`api/documents/${state.documentId}/download-working`);
});

document.querySelectorAll("[data-signature-tab]").forEach((button) => {
  button.addEventListener("click", () => setSignatureMode(button.dataset.signatureTab));
});

document.querySelectorAll("[data-script-test]").forEach((button) => {
  button.addEventListener("click", () => testCustomScript(button.dataset.scriptTest));
});

useGeneratedConditionScriptButton.addEventListener("click", () => {
  const field = selectedField();
  const script = generatedConditionScript.value || "";
  if (!field || !script.trim()) return;
  if (!state.inspectorDirty) {
    pushHistory();
    state.inspectorDirty = true;
  }
  field.custom_script_calculate = script;
  inspector.custom_script_calculate.value = script;
  clearScriptTestResult();
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
  const previousDefaultValue = field.default_value || "";
  field.name = data.get("name") || field.name;
  field.label = data.get("label") || "";
  field.tooltip = data.get("tooltip") || field.label || "";
  field.type = data.get("type") || field.type;
  field.x = numberValue(data.get("x"), field.x);
  field.y = numberValue(data.get("y"), field.y);
  field.width = Math.max(1, numberValue(data.get("width"), field.width));
  field.height = Math.max(1, numberValue(data.get("height"), field.height));
  field.options = (data.get("options") || "").split("\n").map((value) => value.trim()).filter(Boolean);
  field.default_value = data.get("default_value") || "";
  field.button_action = data.get("button_action") || "";
  field.button_script = data.get("button_script") || "";
  if (!field.value || field.value === previousDefaultValue) {
    field.value = field.default_value;
  }
  field.required = data.get("required") === "on";
  field.read_only = data.get("read_only") === "on";
  field.hidden = data.get("hidden") === "on";
  field.printable = data.get("printable") === "on";
  field.no_export = data.get("no_export") === "on";
  field.group = data.get("group") || "";
  field.font_size = Math.max(1, numberValue(data.get("font_size"), field.font_size || 10));
  field.max_length = Math.max(0, Math.round(numberValue(data.get("max_length"), field.max_length || 0)));
  field.auto_fit_text = data.get("auto_fit_text") === "on";
  field.multiline = data.get("multiline") === "on";
  field.comb = data.get("comb") === "on";
  field.multi_select = data.get("multi_select") === "on";
  field.text_alignment = data.get("text_alignment") || "left";
  field.border_style = data.get("border_style") || "solid";
  field.tab_order = Math.max(0, Math.round(numberValue(data.get("tab_order"), field.tab_order || 0)));
  field.border_color = data.get("border_color_on") === "on" ? data.get("border_color") : "";
  field.background_color = data.get("background_color_on") === "on" ? data.get("background_color") : "";
  field.format = data.get("format") || "";
  field.date_auto_fill = data.get("date_auto_fill") === "on";
  field.date_format = data.get("date_format") || "mm/dd/yyyy";
  field.calc_operation = data.get("calc_operation") || "";
  field.calc_fields = (data.get("calc_fields") || "").split(",").map((value) => value.trim()).filter(Boolean);
  field.condition_default = data.get("condition_default") || "";
  field.custom_script_format = data.get("custom_script_format") || "";
  field.custom_script_validate = data.get("custom_script_validate") || "";
  field.custom_script_calculate = data.get("custom_script_calculate") || "";
  const sources = data.getAll("condition_source");
  const operators = data.getAll("condition_operator");
  const values = data.getAll("condition_value");
  const outputs = data.getAll("condition_output");
  field.conditions = sources.map((source_field, index) => ({
    source_field,
    operator: operators[index] || "equals",
    value: values[index] || "",
    output: outputs[index] || "",
  }));
  refreshGeneratedConditionScript(field);
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
  state.fields = normalizeGeneratedFieldNames(info.fields || []);
  state.selectedIds.clear();
  state.activeId = null;
  state.currentPage = 0;
  const firstLogicField = state.fields.find((field) => field.conditions && field.conditions.length);
  if (firstLogicField) {
    state.selectedIds = new Set([firstLogicField.id]);
    state.activeId = firstLogicField.id;
    state.currentPage = firstLogicField.page;
  }
  state.history = [];
  state.future = [];
  state.zoom = 1;
  state.mode = "design";
  state.pendingSignField = null;
  state.signedFields = new Set();
  const groupNumbers = state.fields
    .map((field) => String(field.group || "").match(/^radio_group_(\d+)$/))
    .filter(Boolean)
    .map((match) => Number(match[1]));
  state.nextRadioPlacementGroup = Math.max(0, ...groupNumbers) + 1;
  previewButton.disabled = false;
  exportButton.disabled = false;
  saveProjectButton.disabled = false;
  fillModeButton.disabled = false;
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
      if (state.mode === "fill") return;
      if (state.suppressNextPageClick) {
        state.suppressNextPageClick = false;
        return;
      }
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
    img.onload = () => (state.mode === "fill" ? renderFillFields() : renderFields());
    page.appendChild(img);
    pages.appendChild(page);
  });
}

function enterFillMode() {
  if (!state.documentId) return;
  state.mode = "fill";
  clearSelection();
  addFieldPanel.hidden = true;
  arrangeGroupPanel.hidden = true;
  inspector.hidden = true;
  fillModePanel.hidden = false;
  renderFillFields();
}

function exitFillMode() {
  state.mode = "design";
  addFieldPanel.hidden = false;
  arrangeGroupPanel.hidden = false;
  inspector.hidden = false;
  fillModePanel.hidden = true;
  renderFields();
}

function renderFillFields() {
  renderFillControls({
    clearSelector: ".field, .fill-input, .fill-sign-box, .base-object",
    pageSelector: (field) => document.querySelector(`.page[data-page="${field.page}"]`),
    inputClass: "fill-input",
    signClass: "fill-sign-box",
    radioNamePrefix: "fill-radio",
    interactiveSignatures: true,
    valueMap: null,
    rerender: renderFillFields,
  });
}

function renderInteractivePreview() {
  state.previewValues = buildPreviewValues();
  recomputeConditions(state.previewValues);
  previewPages.innerHTML = "";
  state.renderUrls.forEach((url, pageIndex) => {
    const page = document.createElement("div");
    page.className = "preview-page";
    page.dataset.page = pageIndex;
    const img = document.createElement("img");
    img.src = `${url}?t=${Date.now()}`;
    img.onload = renderPreviewControls;
    page.appendChild(img);
    previewPages.appendChild(page);
  });
  renderPreviewControls();
}

function renderPreviewControls() {
  renderFillControls({
    clearSelector: ".preview-fill-input, .preview-fill-sign-box",
    pageSelector: (field) => previewPages.querySelector(`.preview-page[data-page="${field.page}"]`),
    inputClass: "fill-input preview-fill-input",
    signClass: "fill-sign-box preview-fill-sign-box",
    radioNamePrefix: "preview-radio",
    interactiveSignatures: false,
    valueMap: state.previewValues,
    rerender: renderPreviewControls,
  });
}

function fieldInitialPreviewValue(field) {
  if (field.type === "checkbox" || field.type === "radio") {
    return field.default_value === "Yes" ? "Yes" : "Off";
  }
  if (field.type === "date" && field.date_auto_fill) {
    return formatDateValue(new Date(), field.date_format || "mm/dd/yyyy");
  }
  return field.default_value || "";
}

function isBaseDocumentObject(field) {
  return field.type === "static_text" || field.type === "whiteout";
}

function formatDateValue(date, format) {
  const month = date.getMonth() + 1;
  const day = date.getDate();
  const year = date.getFullYear();
  const hours24 = date.getHours();
  const hours12 = hours24 % 12 || 12;
  const minutes = date.getMinutes();
  const seconds = date.getSeconds();
  const monthNames = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
  ];
  const pad = (value) => String(value).padStart(2, "0");
  return (format || "mm/dd/yyyy")
    .replace(/mmmm/g, monthNames[month - 1])
    .replace(/yyyy/g, String(year))
    .replace(/mm/g, pad(month))
    .replace(/m/g, String(month))
    .replace(/dd/g, pad(day))
    .replace(/d/g, String(day))
    .replace(/HH/g, pad(hours24))
    .replace(/h/g, String(hours12))
    .replace(/MM/g, pad(minutes))
    .replace(/ss/g, pad(seconds))
    .replace(/tt/g, hours24 >= 12 ? "PM" : "AM");
}

function buildPreviewValues() {
  return new Map(state.fields.map((field) => [field.id, fieldInitialPreviewValue(field)]));
}

function fieldCurrentValue(field, valueMap) {
  if (valueMap) return valueMap.get(field.id) ?? fieldInitialPreviewValue(field);
  return field.value || field.default_value || "";
}

function setFieldCurrentValue(field, value, valueMap) {
  if (valueMap) {
    valueMap.set(field.id, value);
  } else {
    field.value = value;
  }
}

function renderFillControls({ clearSelector, pageSelector, inputClass, signClass, radioNamePrefix, interactiveSignatures, valueMap, rerender }) {
  document.querySelectorAll(clearSelector).forEach((el) => el.remove());
  state.fields.forEach((field) => {
    const page = pageSelector(field);
    if (!page) return;
    const img = page.querySelector("img");
    if (!img || !img.clientWidth || !img.clientHeight) return;
    const [pdfWidth, pdfHeight] = state.pageSizes[field.page];
    const scaleX = img.clientWidth / pdfWidth;
    const scaleY = img.clientHeight / pdfHeight;
    const style = (el) => {
      el.style.left = `${field.x * scaleX}px`;
      el.style.top = `${field.y * scaleY}px`;
      el.style.width = `${field.width * scaleX}px`;
      el.style.height = `${field.height * scaleY}px`;
      if (!["checkbox", "radio"].includes(field.type) && field.font_size) {
        el.style.fontSize = `${Math.max(7, field.font_size * scaleY)}px`;
      }
    };

    if (field.hidden) return;

    if (isBaseDocumentObject(field)) {
      if (inputClass.includes("preview-fill-input")) return;
      const baseObject = document.createElement("div");
      baseObject.className = `base-object base-object-${field.type}`;
      if (field.type === "static_text") {
        baseObject.textContent = field.default_value || field.label || "";
        baseObject.style.fontSize = `${Math.max(7, (field.font_size || 10) * scaleY)}px`;
        baseObject.style.textAlign = field.text_alignment || "left";
      }
      style(baseObject);
      page.appendChild(baseObject);
      return;
    }

    if (field.type === "button") {
      const button = document.createElement("button");
      button.type = "button";
      button.className = inputClass;
      button.textContent = field.label || field.default_value || field.name || "Button";
      button.addEventListener("click", (event) => {
        event.preventDefault();
        executeButtonAction(field, valueMap, rerender);
      });
      style(button);
      page.appendChild(button);
      return;
    }

    if (field.type === "signature" || field.type === "initials" || field.type === "digital_signature") {
      const box = document.createElement("div");
      box.className = `${signClass} fill-sign-box-${field.type}`;
      style(box);
      const signed = state.signedFields.has(field.name);
      box.textContent = signed ? "Signed" : field.type === "digital_signature" ? "E Sign" : field.type === "initials" ? "Initials" : "Mock Sign";
      if (signed) {
        box.classList.add("is-signed");
      } else if (interactiveSignatures) {
        box.textContent = field.type === "digital_signature" ? "Click to E Sign" : field.type === "initials" ? "Click to Initial" : "Click to Mock Sign";
        box.addEventListener("click", (event) => {
          event.stopPropagation();
          if (field.type === "signature" || field.type === "initials") {
            openMockSignDialog(field);
          } else {
            openEsignDialog(field);
          }
        });
      }
      page.appendChild(box);
      return;
    }

    let input;
    if (field.type === "checkbox") {
      input = document.createElement("input");
      input.type = "checkbox";
      input.checked = fieldCurrentValue(field, valueMap) === "Yes";
      input.addEventListener("change", () => {
        setFieldCurrentValue(field, input.checked ? "Yes" : "Off", valueMap);
        recomputeConditions(valueMap);
      });
    } else if (field.type === "radio") {
      input = document.createElement("input");
      input.type = "radio";
      input.name = `${radioNamePrefix}-${field.group || field.name}`;
      input.checked = fieldCurrentValue(field, valueMap) === "Yes";
      input.addEventListener("change", () => {
        state.fields
          .filter((item) => item.type === "radio" && (item.group || item.name) === (field.group || field.name))
          .forEach((item) => {
            setFieldCurrentValue(item, item.id === field.id ? "Yes" : "Off", valueMap);
          });
        recomputeConditions(valueMap);
        rerender();
      });
    } else if (field.type === "dropdown" || field.type === "listbox") {
      input = document.createElement("select");
      if (field.type === "listbox") {
        input.size = Math.min(Math.max((field.options || []).length, 2), 8);
        input.multiple = Boolean(field.multi_select);
      }
      (field.options || []).forEach((option) => {
        const opt = document.createElement("option");
        opt.value = option;
        opt.textContent = option;
        input.appendChild(opt);
      });
      input.value = fieldCurrentValue(field, valueMap);
      input.addEventListener("change", () => {
        setFieldCurrentValue(field, input.multiple ? [...input.selectedOptions].map((option) => option.value).join(", ") : input.value, valueMap);
        recomputeConditions(valueMap);
      });
    } else if (field.multiline) {
      input = document.createElement("textarea");
      input.value = fieldCurrentValue(field, valueMap);
      input.addEventListener("input", () => {
        setFieldCurrentValue(field, input.value, valueMap);
        recomputeConditions(valueMap);
      });
    } else {
      input = document.createElement("input");
      input.type = "text";
      input.value = fieldCurrentValue(field, valueMap);
      input.addEventListener("input", () => {
        setFieldCurrentValue(field, input.value, valueMap);
        recomputeConditions(valueMap);
      });
    }
    input.className = inputClass;
    input.dataset.fieldId = field.id;
    if (field.read_only) {
      if (input.tagName === "SELECT" || field.type === "checkbox" || field.type === "radio") {
        input.disabled = true;
      } else {
        input.readOnly = true;
      }
    }
    if (field.conditions && field.conditions.length) {
      input.classList.add("is-computed");
      if (input.tagName === "SELECT" || field.type === "checkbox" || field.type === "radio") {
        input.disabled = true;
      } else {
        input.readOnly = true;
      }
    }
    style(input);
    page.appendChild(input);
  });
  recomputeConditions(valueMap);
}

function fieldMatchesCondition(sourceField, rule, valueMap) {
  const value = sourceField ? fieldCurrentValue(sourceField, valueMap) : "";
  switch (rule.operator) {
    case "checked":
      return value === "Yes";
    case "not_checked":
      return value !== "Yes";
    case "empty":
      return value === "";
    case "not_empty":
      return value !== "";
    case "not_equals":
      return value !== rule.value;
    case "contains":
      return value.includes(rule.value);
    default:
      return value === rule.value;
  }
}

function recomputeConditions(valueMap = null) {
  const computedFields = state.fields.filter((field) => field.conditions && field.conditions.length);
  if (!computedFields.length) return;
  for (let pass = 0; pass < 5; pass += 1) {
    const byName = new Map(state.fields.map((field) => [field.name, field]));
    let changed = false;
    computedFields.forEach((field) => {
      const match = field.conditions.find((rule) => fieldMatchesCondition(byName.get(rule.source_field), rule, valueMap));
      const next = match ? match.output : field.condition_default || "";
      if (fieldCurrentValue(field, valueMap) !== next) {
        setFieldCurrentValue(field, next, valueMap);
        changed = true;
      }
    });
    if (!changed) break;
  }
  computedFields.forEach((field) => {
    document.querySelectorAll(`.fill-input[data-field-id="${field.id}"]`).forEach((input) => {
      const value = fieldCurrentValue(field, valueMap);
      if (field.type === "checkbox" || field.type === "radio") {
        input.checked = value === "Yes";
      } else if (input.value !== value) {
        input.value = value;
      }
    });
  });
}

function executeButtonAction(field, valueMap, rerender) {
  if (field.button_action === "print") {
    window.print();
    return;
  }
  if (field.button_action === "clear_form" || field.button_action === "reset_page") {
    const targetFields = state.fields.filter((item) => {
      if (isBaseDocumentObject(item)) return false;
      if (item.id === field.id || item.read_only) return false;
      return field.button_action === "clear_form" || item.page === field.page;
    });
    targetFields.forEach((item) => {
      const value = item.type === "checkbox" || item.type === "radio" ? "Off" : "";
      setFieldCurrentValue(item, value, valueMap);
    });
    recomputeConditions(valueMap);
    rerender();
    return;
  }
  if (field.button_action === "submit") {
    alert("Submit actions require a destination URL. Use a custom Acrobat script for a production submit workflow.");
  }
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
    element.addEventListener("contextmenu", (event) => {
      event.preventDefault();
      event.stopPropagation();
      selectOnly(field.id);
      openFieldContextMenu(event, field);
    });
    if ((field.type === "signature" || field.type === "initials") && field.signature_data_url) {
      const image = document.createElement("img");
      image.className = "signature-image";
      image.src = field.signature_data_url;
      element.appendChild(image);
    } else if (field.type === "static_text") {
      const text = document.createElement("span");
      text.className = "static-text-preview";
      text.textContent = field.default_value || field.label || "Static text";
      text.style.fontSize = `${Math.max(7, (field.font_size || 10) * scaleY)}px`;
      text.style.textAlign = field.text_alignment || "left";
      element.appendChild(text);
    }
    if (state.selectedIds.has(field.id)) {
      ["nw", "ne", "sw", "se"].forEach((corner) => {
        const handle = document.createElement("div");
        handle.className = `resize-handle resize-${corner}`;
        handle.addEventListener("pointerdown", (event) => startResize(event, field, corner));
        element.appendChild(handle);
      });
    }
    page.appendChild(element);
  });
}

function openFieldContextMenu(event, field) {
  fieldContextMenu.hidden = false;
  fieldContextMenu.style.left = `${event.clientX}px`;
  fieldContextMenu.style.top = `${event.clientY}px`;
  fieldContextMenu.dataset.fieldId = field.id;
}

function closeFieldContextMenu() {
  fieldContextMenu.hidden = true;
  delete fieldContextMenu.dataset.fieldId;
}

document.addEventListener("pointerdown", (event) => {
  if (!fieldContextMenu.hidden && !fieldContextMenu.contains(event.target)) closeFieldContextMenu();
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !fieldContextMenu.hidden) closeFieldContextMenu();
});

fieldContextMenu.addEventListener("click", (event) => {
  const action = event.target.dataset.action;
  if (!action) return;
  const field = state.fields.find((item) => item.id === fieldContextMenu.dataset.fieldId);
  closeFieldContextMenu();
  if (!field) return;

  if (action === "delete") {
    deleteButton.click();
    return;
  }

  pushHistory();
  if (action === "toggle-required") {
    field.required = !field.required;
    syncInspector();
    renderFields();
  } else if (action === "set-group") {
    // A native prompt() can't show existing group names as suggestions --
    // jump to the Inspector's own Group field instead, which already has
    // datalist-based autocomplete over every group in use.
    syncInspector();
    renderFields();
    inspector.group.scrollIntoView({ block: "center" });
    inspector.group.focus();
  } else if (action === "add-condition") {
    field.conditions = field.conditions || [];
    field.conditions.push({ source_field: "", operator: "equals", value: "", output: "" });
    syncInspector();
    renderFields();
    const rows = conditionRows.querySelectorAll(".condition-row");
    rows[rows.length - 1]?.scrollIntoView({ block: "center" });
  }
});

function startResize(event, field, corner) {
  event.stopPropagation();
  event.preventDefault();
  const element = document.querySelector(`.field[data-id="${field.id}"]`);
  const page = document.querySelector(`.page[data-page="${field.page}"]`);
  const img = page.querySelector("img");
  const [pdfWidth, pdfHeight] = state.pageSizes[field.page];
  const scaleX = img.clientWidth / pdfWidth;
  const scaleY = img.clientHeight / pdfHeight;
  const startX = event.clientX;
  const startY = event.clientY;
  const origin = { x: field.x, y: field.y, width: field.width, height: field.height };
  const MIN_SIZE = 6;
  pushHistory();

  const move = (moveEvent) => {
    const dx = (moveEvent.clientX - startX) / scaleX;
    const dy = (moveEvent.clientY - startY) / scaleY;
    let { x, y, width, height } = origin;
    if (corner.includes("e")) width = Math.max(MIN_SIZE, origin.width + dx);
    if (corner.includes("s")) height = Math.max(MIN_SIZE, origin.height + dy);
    if (corner.includes("w")) {
      width = Math.max(MIN_SIZE, origin.width - dx);
      x = origin.x + origin.width - width;
    }
    if (corner.includes("n")) {
      height = Math.max(MIN_SIZE, origin.height - dy);
      y = origin.y + origin.height - height;
    }
    field.x = Math.max(0, x);
    field.y = Math.max(0, y);
    field.width = width;
    field.height = height;
    element.style.left = `${field.x * scaleX}px`;
    element.style.top = `${field.y * scaleY}px`;
    element.style.width = `${field.width * scaleX}px`;
    element.style.height = `${field.height * scaleY}px`;
  };
  const up = () => {
    document.removeEventListener("pointermove", move);
    document.removeEventListener("pointerup", up);
    syncInspector();
  };
  document.addEventListener("pointermove", move);
  document.addEventListener("pointerup", up);
}

function startDrag(event) {
  event.stopPropagation();
  state.suppressNextPageClick = true;
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

function startPlacing(type, repeat) {
  if (!state.documentId) return;
  state.pendingType = type;
  state.placingRepeat = Boolean(repeat);
  if (type !== "radio" || !state.placingRepeat) {
    endRadioPlacementGroup();
  }
  if (!textSplitAvailable()) {
    state.textSplitCount = 1;
  }
  pages.classList.add("placing");
  document.querySelectorAll("[data-add]").forEach((button) => {
    button.classList.toggle("is-active", button.dataset.add === type);
    button.classList.toggle("is-repeating", button.dataset.add === type && state.placingRepeat);
  });
}

function stopPlacing() {
  state.pendingType = null;
  state.placingRepeat = false;
  endRadioPlacementGroup();
  state.textSplitCount = 1;
  pages.classList.remove("placing");
  document.querySelectorAll("[data-add]").forEach((button) => {
    button.classList.remove("is-active", "is-repeating");
  });
}

function radioGroupingAvailable() {
  return state.pendingType === "radio" && state.placingRepeat;
}

function textSplitAvailable() {
  return state.pendingType === "text" || state.pendingType === "date";
}

function startRadioPlacementGroup() {
  if (!radioGroupingAvailable() || state.radioGroupHotkeyActive) return;
  state.radioGroupHotkeyActive = true;
  state.activeRadioPlacementGroup = `radio_group_${state.nextRadioPlacementGroup}`;
  state.nextRadioPlacementGroup += 1;
}

function endRadioPlacementGroup() {
  state.radioGroupHotkeyActive = false;
  state.radioGroupHotkeyDown = false;
  state.activeRadioPlacementGroup = "";
}

function canAutoFitTextLine(type) {
  return ["text", "date", "dropdown", "button"].includes(type);
}

function pagePointFromEvent(img, pageIndex, event) {
  const rect = img.getBoundingClientRect();
  const [pdfWidth, pdfHeight] = state.pageSizes[pageIndex];
  const scaleX = img.clientWidth / pdfWidth;
  const scaleY = img.clientHeight / pdfHeight;
  return {
    x: Math.max(0, (event.clientX - rect.left) / scaleX),
    y: Math.max(0, (event.clientY - rect.top) / scaleY),
    scaleX,
    scaleY,
    pdfWidth,
    pdfHeight,
  };
}

function isDarkPixel(data, index) {
  const red = data[index];
  const green = data[index + 1];
  const blue = data[index + 2];
  const alpha = data[index + 3];
  if (alpha < 40) return false;
  return red + green + blue < 390;
}

function renderedImageCanvas(img) {
  if (!img.complete || !img.naturalWidth || !img.naturalHeight) return null;
  const canvas = document.createElement("canvas");
  canvas.width = img.naturalWidth;
  canvas.height = img.naturalHeight;
  const context = canvas.getContext("2d", { willReadFrequently: true });
  context.drawImage(img, 0, 0);
  return { canvas, context };
}

function findHorizontalLineRun(img, pageIndex, point) {
  const rendered = renderedImageCanvas(img);
  if (!rendered) return null;
  const { canvas, context } = rendered;
  const pdfToImageX = canvas.width / point.pdfWidth;
  const pdfToImageY = canvas.height / point.pdfHeight;
  const clickX = Math.round(point.x * pdfToImageX);
  const clickY = Math.round(point.y * pdfToImageY);
  const searchUp = Math.round(11 * pdfToImageY);
  const searchDown = Math.round(13 * pdfToImageY);
  const startPadding = Math.round(2 * pdfToImageX);
  const maxGap = Math.max(2, Math.round(3 * pdfToImageX));
  const minRun = Math.max(18, Math.round(30 * pdfToImageX));
  const rightLimit = Math.min(canvas.width - 1, clickX + Math.round(520 * pdfToImageX));
  const leftLimit = Math.max(0, clickX - Math.round(10 * pdfToImageX));
  let best = null;

  for (let y = Math.max(0, clickY - searchUp); y <= Math.min(canvas.height - 1, clickY + searchDown); y += 1) {
    const row = context.getImageData(leftLimit, y, rightLimit - leftLimit + 1, 1).data;
    let runStart = null;
    let runEnd = null;
    let gap = 0;
    for (let x = Math.max(clickX + startPadding, leftLimit); x <= rightLimit; x += 1) {
      const dark = isDarkPixel(row, (x - leftLimit) * 4);
      if (dark) {
        if (runStart === null) runStart = x;
        runEnd = x;
        gap = 0;
      } else if (runStart !== null) {
        gap += 1;
        if (gap > maxGap) break;
      }
    }
    if (runStart === null || runEnd === null) continue;
    const length = runEnd - runStart + 1;
    if (length < minRun) continue;
    const score = length - Math.abs(y - clickY) * 5;
    if (!best || score > best.score) {
      best = { x1: clickX, x2: runEnd, y, length, score };
    }
  }

  if (!best) return null;
  return {
    x: Math.max(0, point.x),
    y: Math.max(0, best.y / pdfToImageY - 14),
    width: Math.max(40, (best.x2 - clickX) / pdfToImageX),
    height: 18,
  };
}

function fieldGeometryForPlacement(type, img, pageIndex, event) {
  const point = pagePointFromEvent(img, pageIndex, event);
  let width = type === "checkbox" || type === "radio" ? 14 : type === "digital_signature" ? 200 : type === "initials" ? 80 : 160;
  let height = type === "checkbox" || type === "radio" ? 14 : type === "digital_signature" ? 60 : type === "initials" ? 28 : type === "listbox" ? 70 : 20;

  if (canAutoFitTextLine(type)) {
    const lineFit = findHorizontalLineRun(img, pageIndex, point);
    if (lineFit) {
      return {
        x: Math.min(lineFit.x, point.pdfWidth - lineFit.width),
        y: Math.min(lineFit.y, point.pdfHeight - lineFit.height),
        width: Math.min(lineFit.width, point.pdfWidth - lineFit.x),
        height: lineFit.height,
      };
    }
  }

  return {
    x: Math.max(0, Math.min(point.x - width / 2, point.pdfWidth - width)),
    y: Math.max(0, Math.min(point.y - height / 2, point.pdfHeight - height)),
    width,
    height,
  };
}

function baseField(type, pageIndex, geometry) {
  const id = generateId();
  const field = {
    id,
    page: pageIndex,
    type,
    name: nextGeneratedFieldName(type),
    x: geometry.x,
    y: geometry.y,
    width: geometry.width,
    height: geometry.height,
    label: "",
    tooltip: "",
    required: false,
    read_only: false,
    hidden: false,
    printable: true,
    no_export: false,
    default_value: "",
    text_alignment: "left",
    border_style: "solid",
    tab_order: 0,
    options: [],
    group: "",
    value: "",
    signature_data_url: "",
    multi_select: false,
    button_action: "",
    button_script: "",
    date_auto_fill: false,
    date_format: "mm/dd/yyyy",
  };
  if (type === "radio" && state.radioGroupHotkeyActive && state.activeRadioPlacementGroup) {
    field.group = state.activeRadioPlacementGroup;
  }
  if (type === "button") {
    field.label = "Button";
    field.tooltip = "Button";
  }
  if (type === "static_text") {
    field.default_value = "Static text";
    field.label = "Static text";
    field.tooltip = "Static text";
    field.border_color = "";
    field.background_color = "";
  }
  if (type === "whiteout") {
    field.label = "Whiteout";
    field.tooltip = "Whiteout";
    field.background_color = "#ffffff";
  }
  if (type === "date") {
    field.format = "date";
  }
  return field;
}

function splitTextFields(type, pageIndex, geometry, count) {
  const gap = count > 1 ? Math.min(6, Math.max(2, geometry.width * 0.015)) : 0;
  const itemWidth = Math.max(8, (geometry.width - gap * (count - 1)) / count);
  const fields = [];
  for (let index = 0; index < count; index += 1) {
    const field = baseField(type, pageIndex, {
      ...geometry,
      x: geometry.x + index * (itemWidth + gap),
      width: itemWidth,
    });
    field.name = nextGeneratedFieldName(type);
    fields.push(field);
    state.fields.push(field);
  }
  return fields;
}

function placeField(type, pageElement, pageIndex, event) {
  const img = pageElement.querySelector("img");
  const geometry = fieldGeometryForPlacement(type, img, pageIndex, event);
  const splitCount = textSplitAvailable() ? Math.max(1, Math.min(9, state.textSplitCount || 1)) : 1;
  pushHistory();
  const fields = splitCount > 1 ? splitTextFields(type, pageIndex, geometry, splitCount) : [baseField(type, pageIndex, geometry)];
  if (splitCount === 1) {
    state.fields.push(fields[0]);
  }
  state.currentPage = pageIndex;
  const id = fields[fields.length - 1].id;
  const selectedIds = new Set(fields.map((field) => field.id));
  if (state.placingRepeat) {
    state.selectedIds = selectedIds;
    state.activeId = id;
    afterSelectionChange();
    startPlacing(type, true);
  } else {
    stopPlacing();
    state.selectedIds = selectedIds;
    state.activeId = id;
    afterSelectionChange();
  }
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
  inspector.default_value.value = field?.default_value || "";
  inspector.button_action.value = field?.button_action || "";
  inspector.button_script.value = field?.button_script || "";
  if (buttonScriptBlock) {
    buttonScriptBlock.hidden = field?.type !== "button";
  }
  inspector.tooltip.value = field?.tooltip || "";
  inspector.required.checked = Boolean(field?.required);
  inspector.read_only.checked = Boolean(field?.read_only);
  inspector.hidden.checked = Boolean(field?.hidden);
  inspector.printable.checked = field ? field.printable !== false : true;
  inspector.no_export.checked = Boolean(field?.no_export);
  inspector.group.value = field?.group || "";
  inspector.font_size.value = field ? field.font_size || 10 : "";
  inspector.max_length.value = field ? field.max_length || 0 : "";
  inspector.auto_fit_text.checked = Boolean(field?.auto_fit_text);
  inspector.multiline.checked = Boolean(field?.multiline);
  inspector.comb.checked = Boolean(field?.comb);
  inspector.multi_select.checked = Boolean(field?.multi_select);
  inspector.text_alignment.value = field?.text_alignment || "left";
  inspector.border_style.value = field?.border_style || "solid";
  inspector.tab_order.value = field ? field.tab_order || 0 : "";
  inspector.border_color_on.checked = Boolean(field?.border_color);
  inspector.border_color.value = field?.border_color || "#1769aa";
  inspector.background_color_on.checked = Boolean(field?.background_color);
  inspector.background_color.value = field?.background_color || "#ffffff";
  inspector.format.value = field?.format || "";
  inspector.date_auto_fill.checked = Boolean(field?.date_auto_fill);
  inspector.date_format.value = field?.date_format || "mm/dd/yyyy";
  inspector.calc_operation.value = field?.calc_operation || "";
  inspector.calc_fields.value = field?.calc_fields?.join(", ") || "";
  inspector.condition_default.value = field?.condition_default || "";
  inspector.custom_script_format.value = field?.custom_script_format || "";
  inspector.custom_script_validate.value = field?.custom_script_validate || "";
  inspector.custom_script_calculate.value = field?.custom_script_calculate || "";
  clearScriptTestResult();
  renderConditionRows(field);

  const groupNames = [...new Set(state.fields.filter((item) => item.type === "radio" && item.group).map((item) => item.group))];
  const datalist = document.querySelector("#group-suggestions");
  datalist.innerHTML = groupNames.map((name) => `<option value="${escapeHtml(name)}"></option>`).join("");
}

const CONDITION_OPERATORS = [
  { value: "equals", label: "equals" },
  { value: "not_equals", label: "does not equal" },
  { value: "contains", label: "contains" },
  { value: "checked", label: "is checked" },
  { value: "not_checked", label: "is not checked" },
  { value: "empty", label: "is empty" },
  { value: "not_empty", label: "is not empty" },
];

function renderConditionRows(field) {
  const conditions = field?.conditions || [];
  const otherFields = state.fields.filter((item) => item.id !== field?.id);
  conditionRows.innerHTML = conditions
    .map(
      (rule, index) => `
    <div class="condition-row">
      <span class="condition-clause">${index === 0 ? "If" : "Else if"}</span>
      <select name="condition_source" aria-label="Condition source field">
        <option value="">Choose field...</option>
        ${otherFields
          .map(
            (item) =>
              `<option value="${escapeHtml(item.name)}"${item.name === rule.source_field ? " selected" : ""}>${escapeHtml(item.name)}</option>`
          )
          .join("")}
      </select>
      <select name="condition_operator" aria-label="Condition operator">
        ${CONDITION_OPERATORS.map(
          (op) => `<option value="${op.value}"${op.value === rule.operator ? " selected" : ""}>${op.label}</option>`
        ).join("")}
      </select>
      <span class="condition-clause">Value</span>
      <input class="condition-value" name="condition_value" value="${escapeHtml(rule.value)}" placeholder="Value" aria-label="Condition value">
      <span class="condition-clause">Then</span>
      <input class="condition-output" name="condition_output" value="${escapeHtml(rule.output)}" placeholder="Output" aria-label="Then output">
      <button type="button" class="remove-condition">Remove</button>
    </div>`
    )
    .join("");
  refreshGeneratedConditionScript(field);
}

addConditionButton.addEventListener("click", () => {
  const field = selectedField();
  if (!field) return;
  if (!state.inspectorDirty) {
    pushHistory();
    state.inspectorDirty = true;
  }
  field.conditions = field.conditions || [];
  field.conditions.push({ source_field: "", operator: "equals", value: "", output: "" });
  renderConditionRows(field);
  const rows = conditionRows.querySelectorAll(".condition-row");
  rows[rows.length - 1]?.scrollIntoView({ block: "center" });
});

conditionRows.addEventListener("click", (event) => {
  if (!event.target.classList.contains("remove-condition")) return;
  const field = selectedField();
  if (!field) return;
  if (!state.inspectorDirty) {
    pushHistory();
    state.inspectorDirty = true;
  }
  const index = [...conditionRows.children].indexOf(event.target.closest(".condition-row"));
  field.conditions.splice(index, 1);
  renderConditionRows(field);
});

function escapeJsString(value) {
  return String(value ?? "").replace(/\\/g, "\\\\").replace(/"/g, '\\"').replace(/\n/g, "\\n");
}

function conditionJsTest(rule) {
  const source = escapeJsString(rule.source_field);
  const value = escapeJsString(rule.value);
  const get = `this.getField("${source}")`;
  let comparison;
  if (rule.operator === "checked") {
    comparison = `${get}.value == "Yes"`;
  } else if (rule.operator === "not_checked") {
    comparison = `${get}.value != "Yes"`;
  } else if (rule.operator === "empty") {
    comparison = `${get}.value == ""`;
  } else if (rule.operator === "not_empty") {
    comparison = `${get}.value != ""`;
  } else if (rule.operator === "not_equals") {
    comparison = `${get}.value != "${value}"`;
  } else if (rule.operator === "contains") {
    comparison = `${get}.value.indexOf("${value}") !== -1`;
  } else {
    comparison = `${get}.value == "${value}"`;
  }
  return `(${get} != null && ${comparison})`;
}

function buildGeneratedConditionScript(field) {
  if (!field?.conditions?.length) return "";
  const lines = field.conditions.map((rule, index) => {
    const keyword = index === 0 ? "if" : "else if";
    return `${keyword} ${conditionJsTest(rule)} { event.value = "${escapeJsString(rule.output)}"; }`;
  });
  lines.push(`else { event.value = "${escapeJsString(field.condition_default)}"; }`);
  return lines.join("\n");
}

function refreshGeneratedConditionScript(field) {
  if (!generatedConditionScript || !useGeneratedConditionScriptButton) return;
  if (!field) {
    generatedConditionScript.value = "Select a field to view generated conditional JavaScript.";
    useGeneratedConditionScriptButton.disabled = true;
    return;
  }
  const script = buildGeneratedConditionScript(field);
  generatedConditionScript.value = script || "No conditional logic is defined for the selected field.";
  useGeneratedConditionScriptButton.disabled = !script;
}

function clearScriptTestResult() {
  if (!scriptTestResult) return;
  scriptTestResult.textContent = "";
  scriptTestResult.classList.remove("is-ok", "is-error");
}

function showScriptTestResult(message, ok) {
  if (!scriptTestResult) return;
  scriptTestResult.textContent = message;
  scriptTestResult.classList.toggle("is-ok", ok);
  scriptTestResult.classList.toggle("is-error", !ok);
}

function acrobatFieldValue(field, valueMap) {
  if (field.type === "checkbox" || field.type === "radio") {
    return (valueMap.get(field.id) || field.value || field.default_value) === "Yes" ? "Yes" : "Off";
  }
  return valueMap.get(field.id) ?? field.value ?? field.default_value ?? "";
}

function createAcrobatFieldFacade(field, valueMap) {
  return {
    name: field.name,
    type: field.type,
    readonly: Boolean(field.read_only),
    required: Boolean(field.required),
    display: field.hidden ? "hidden" : "visible",
    setFocus() {},
    get value() {
      return acrobatFieldValue(field, valueMap);
    },
    set value(nextValue) {
      valueMap.set(field.id, String(nextValue ?? ""));
    },
  };
}

function createAcrobatGroupFacade(groupName, groupedFields, valueMap) {
  return {
    name: groupName,
    type: "radio",
    setFocus() {},
    get value() {
      return groupedFields.some((field) => acrobatFieldValue(field, valueMap) === "Yes") ? "Yes" : "Off";
    },
    set value(nextValue) {
      const selectedValue = String(nextValue ?? "");
      groupedFields.forEach((field, index) => {
        const shouldSelect = selectedValue === "Yes" ? index === 0 : selectedValue === field.name;
        valueMap.set(field.id, shouldSelect ? "Yes" : "Off");
      });
    },
  };
}

function createAcrobatTestContext(selected, initialValue) {
  const valueMap = new Map(state.fields.map((field) => [field.id, field.value || field.default_value || ""]));
  const alerts = [];
  const doc = {
    getField(name) {
      const direct = state.fields.find((field) => field.name === name);
      if (direct) return createAcrobatFieldFacade(direct, valueMap);
      const grouped = state.fields.filter((field) => field.type === "radio" && field.group === name);
      if (grouped.length) return createAcrobatGroupFacade(name, grouped, valueMap);
      return null;
    },
    getFieldNames() {
      return state.fields.map((field) => field.name);
    },
    resetForm(names) {
      const targetNames = Array.isArray(names) ? new Set(names) : null;
      state.fields.forEach((field) => {
        if (field.read_only || field.type === "signature" || field.type === "initials" || field.type === "digital_signature") return;
        if (targetNames && !targetNames.has(field.name)) return;
        valueMap.set(field.id, field.type === "checkbox" || field.type === "radio" ? "Off" : "");
      });
    },
    print() {
      alerts.push("Print requested.");
    },
    submitForm() {
      alerts.push("Submit requested.");
    },
  };
  const event = {
    value: initialValue,
    rc: true,
    target: createAcrobatFieldFacade(selected, valueMap),
    source: null,
  };
  const app = {
    alert(message) {
      alerts.push(String(message));
    },
  };
  const util = {
    printf(format, ...values) {
      let index = 0;
      return String(format).replace(/%[sdif]/g, () => String(values[index++] ?? ""));
    },
  };
  return { event, app, util, doc, valueMap, alerts };
}

function formatChangedFields(valueMap) {
  return state.fields
    .filter((field) => (valueMap.get(field.id) ?? "") !== (field.value || field.default_value || ""))
    .map((field) => `${field.name}: ${valueMap.get(field.id) || ""}`);
}

function testCustomScript(kind) {
  const field = selectedField();
  if (!field) {
    showScriptTestResult("Select a field before testing a script.", false);
    return;
  }
  const scriptField = {
    format: inspector.custom_script_format,
    validate: inspector.custom_script_validate,
    calculate: inspector.custom_script_calculate,
    action: inspector.button_script,
  }[kind];
  const script = scriptField?.value || "";
  if (!script.trim()) {
    showScriptTestResult(`No ${kind} script to test.`, false);
    return;
  }

  let runner;
  try {
    runner = new Function("event", "app", "util", script);
  } catch (error) {
    showScriptTestResult(`Syntax error: ${error.message}`, false);
    return;
  }

  const initialValue = field.value || field.default_value || "";
  const context = createAcrobatTestContext(field, initialValue);
  try {
    runner.call(context.doc, context.event, context.app, context.util);
  } catch (error) {
    showScriptTestResult(`Runtime error: ${error.message}`, false);
    return;
  }

  const changedFields = formatChangedFields(context.valueMap);
  const lines = [
    "Syntax OK. Simulated run completed.",
    `event.value: ${context.event.value ?? ""}`,
    `event.rc: ${context.event.rc === false ? "false" : "true"}`,
  ];
  if (context.alerts.length) lines.push(`Alerts: ${context.alerts.join(" | ")}`);
  if (changedFields.length) lines.push(`Changed fields: ${changedFields.join("; ")}`);
  lines.push("Final behavior still depends on the PDF viewer's Acrobat JavaScript support.");
  showScriptTestResult(lines.join("\n"), true);
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

function openMockSignDialog(field) {
  state.pendingSignField = field.name;
  clearSignature();
  setSignatureMode("type");
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

function confirmMockSign() {
  const field = state.fields.find((item) => item.name === state.pendingSignField);
  if (!field) return;
  if (state.signatureMode === "type" && !signatureText.value.trim()) {
    alert("Type your name to sign.");
    return;
  }
  const dataUrl = state.signatureMode === "type" ? typedSignatureDataUrl() : signatureCanvas.toDataURL("image/png");
  const signerName = state.signatureMode === "type" ? signatureText.value : field.name;
  signatureDialog.close();
  submitFillAndSign(field.name, "mock", { signer_name: signerName, signature_image_data_url: dataUrl });
}

function openEsignDialog(field) {
  state.pendingSignField = field.name;
  esignNameInput.value = "";
  esignReasonInput.value = "";
  esignLocationInput.value = "";
  esignDialog.showModal();
}

function confirmEsign() {
  const field = state.fields.find((item) => item.name === state.pendingSignField);
  if (!field) return;
  esignDialog.close();
  submitFillAndSign(field.name, "esign", {
    signer_name: esignNameInput.value,
    reason: esignReasonInput.value,
    location: esignLocationInput.value,
  });
}

function missingRequiredFields() {
  return state.fields.filter((field) => {
    if (isBaseDocumentObject(field)) return false;
    if (!field.required || field.hidden || field.read_only || field.no_export) return false;
    if (field.type === "signature" || field.type === "initials" || field.type === "digital_signature") {
      return !state.signedFields.has(field.name) && field.name !== state.pendingSignField;
    }
    return !String(field.value || field.default_value || "").trim() || field.value === "Off";
  });
}

function validateRequiredBeforeSign() {
  const missing = missingRequiredFields();
  if (!missing.length) return true;
  alert(`Fill required fields before signing:\n${missing.map((field) => `- ${field.label || field.name}`).join("\n")}`);
  return false;
}

async function submitFillAndSign(fieldName, kind, extra) {
  if (!validateRequiredBeforeSign()) return;
  const response = await fetch(appUrl(`api/documents/${state.documentId}/fill-and-sign`), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      fields: state.fields,
      sign_field_name: fieldName,
      kind,
      signer_name: "",
      reason: "",
      location: "",
      signature_image_data_url: "",
      ...extra,
    }),
  });
  if (!response.ok) {
    alert(await response.text());
    return;
  }
  state.signedFields.add(fieldName);
  state.pendingSignField = null;
  renderFillFields();
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
