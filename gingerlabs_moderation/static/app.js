const fileInput = document.querySelector("#file-input");
const dropZone = document.querySelector("#drop-zone");
const selection = document.querySelector("#selection");
const selectionCount = document.querySelector("#selection-count");
const fileChips = document.querySelector("#file-chips");
const clearButton = document.querySelector("#clear-button");
const analyzeButton = document.querySelector("#analyze-button");
const status = document.querySelector("#status");
const resultsSection = document.querySelector("#results-section");
const resultsGrid = document.querySelector("#results-grid");
const resultTemplate = document.querySelector("#result-template");

const thresholdControls = [
  ["exact-threshold", "exact-output"],
  ["buttocks-threshold", "buttocks-output"],
  ["candidate-threshold", "candidate-output"],
];

let selectedFiles = [];
let previewUrls = [];

function setFiles(files) {
  const acceptable = Array.from(files).filter((file) =>
    ["image/jpeg", "image/png", "image/webp"].includes(file.type),
  );
  selectedFiles = [...selectedFiles, ...acceptable].slice(0, 12);
  renderSelection();
}

function renderSelection() {
  fileChips.replaceChildren();
  selection.hidden = selectedFiles.length === 0;
  analyzeButton.disabled = selectedFiles.length === 0;
  selectionCount.textContent = `${selectedFiles.length} ${selectedFiles.length === 1 ? "image" : "images"}`;

  selectedFiles.forEach((file, index) => {
    const chip = document.createElement("div");
    chip.className = "file-chip";
    const name = document.createElement("span");
    name.textContent = file.name;
    const remove = document.createElement("button");
    remove.type = "button";
    remove.setAttribute("aria-label", `Remove ${file.name}`);
    remove.textContent = "×";
    remove.addEventListener("click", () => {
      selectedFiles.splice(index, 1);
      renderSelection();
    });
    chip.append(name, remove);
    fileChips.append(chip);
  });
}

function clearPreviews() {
  previewUrls.forEach((url) => URL.revokeObjectURL(url));
  previewUrls = [];
}

function makeText(className, text) {
  const node = document.createElement("p");
  node.className = className;
  node.textContent = text;
  return node;
}

function addDetectionBox(frame, detection, result) {
  const [x1, y1, x2, y2] = detection.box;
  const box = document.createElement("span");
  box.className = `detection-box ${detection.role}`;
  box.title = `${detection.label} · ${Math.round(detection.score * 100)}%`;
  box.style.left = `${(x1 / result.width) * 100}%`;
  box.style.top = `${(y1 / result.height) * 100}%`;
  box.style.width = `${((x2 - x1) / result.width) * 100}%`;
  box.style.height = `${((y2 - y1) / result.height) * 100}%`;
  frame.append(box);
}

function renderResult(result) {
  const card = resultTemplate.content.firstElementChild.cloneNode(true);
  const file = selectedFiles[result.index];
  const stage = card.querySelector(".image-stage");
  const frame = stage.querySelector(".image-frame");
  const image = frame.querySelector("img");
  const verdict = card.querySelector(".verdict");
  const reasons = card.querySelector(".reason-list");
  const details = card.querySelector(".detection-details");
  const detectionList = card.querySelector(".detection-list");

  card.querySelector(".result-name").textContent = result.filename;
  if (file) {
    const url = URL.createObjectURL(file);
    previewUrls.push(url);
    image.src = url;
    image.alt = `Preview of ${result.filename}`;
  }

  if (result.error) {
    verdict.textContent = "ERROR";
    verdict.className = "verdict error";
    card.querySelector(".result-size").textContent = "Not analyzed";
    reasons.append(makeText("reason", result.error));
    details.hidden = true;
    return card;
  }

  card.querySelector(".result-size").textContent = `${result.width} × ${result.height}`;
  verdict.textContent = result.decision.toUpperCase();
  verdict.className = `verdict ${result.decision}`;

  if (result.reasons.length) {
    result.reasons.forEach((reason) => reasons.append(makeText("reason", reason)));
  } else {
    reasons.append(makeText("reason", "No configured blocking category was confirmed."));
  }

  const candidates = result.detections.filter((detection) => detection.role === "candidate");
  if (candidates.length) {
    reasons.append(
      makeText(
        "reason candidate-note",
        "NudeNet found a broad exposed-breast candidate, but the nipple-specific detector did not confirm a blocking result.",
      ),
    );
  }

  result.detections.forEach((detection) => {
    addDetectionBox(frame, detection, result);
    const row = document.createElement("div");
    row.className = "detection-row";
    const label = document.createElement("div");
    const name = document.createElement("strong");
    name.textContent = detection.label;
    const source = document.createElement("span");
    source.textContent = `${detection.detector === "exact_parts" ? "Exact-parts detector" : "NudeNet"} · ${detection.role}`;
    const score = document.createElement("div");
    score.className = "detection-score";
    score.textContent = `${Math.round(detection.score * 100)}%`;
    label.append(name, source);
    row.append(label, score);
    detectionList.append(row);
  });

  if (!result.detections.length) {
    detectionList.append(makeText("reason", "Neither detector returned a result above the configured thresholds."));
  }
  return card;
}

async function analyze() {
  analyzeButton.disabled = true;
  analyzeButton.textContent = "Analyzing…";
  status.textContent = "The first run may take longer while the CPU models load.";
  const form = new FormData();
  selectedFiles.forEach((file) => form.append("files", file));
  form.append("exact_parts_threshold", document.querySelector("#exact-threshold").value);
  form.append("buttocks_threshold", document.querySelector("#buttocks-threshold").value);
  form.append("candidate_threshold", document.querySelector("#candidate-threshold").value);

  try {
    const response = await fetch("/api/analyze", { method: "POST", body: form });
    if (!response.ok) throw new Error("The local tester could not analyze these images.");
    const payload = await response.json();
    if (payload.error) throw new Error(payload.error);
    clearPreviews();
    resultsGrid.replaceChildren(...payload.results.map(renderResult));
    resultsSection.hidden = false;
    resultsSection.scrollIntoView({ behavior: "smooth", block: "start" });
    status.textContent = `${payload.results.length} ${payload.results.length === 1 ? "image" : "images"} analyzed locally.`;
  } catch (error) {
    status.textContent = error instanceof Error ? error.message : "Analysis failed.";
  } finally {
    analyzeButton.disabled = selectedFiles.length === 0;
    analyzeButton.textContent = "Analyze images";
  }
}

dropZone.addEventListener("click", () => fileInput.click());
dropZone.addEventListener("keydown", (event) => {
  if (event.key === "Enter" || event.key === " ") {
    event.preventDefault();
    fileInput.click();
  }
});
dropZone.addEventListener("dragover", (event) => {
  event.preventDefault();
  dropZone.classList.add("is-dragging");
});
dropZone.addEventListener("dragleave", () => dropZone.classList.remove("is-dragging"));
dropZone.addEventListener("drop", (event) => {
  event.preventDefault();
  dropZone.classList.remove("is-dragging");
  setFiles(event.dataTransfer.files);
});
fileInput.addEventListener("change", () => {
  setFiles(fileInput.files);
  fileInput.value = "";
});
clearButton.addEventListener("click", () => {
  selectedFiles = [];
  renderSelection();
});
analyzeButton.addEventListener("click", analyze);

thresholdControls.forEach(([inputId, outputId]) => {
  const input = document.querySelector(`#${inputId}`);
  const output = document.querySelector(`#${outputId}`);
  input.addEventListener("input", () => {
    output.textContent = `${Math.round(Number(input.value) * 100)}%`;
  });
});
