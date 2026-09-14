// LexAssist frontend logic.
// No frameworks/build step required -- plain, dependency-free JS that
// talks to the FastAPI backend over fetch(). Keeping this vanilla keeps
// the repo small and avoids a build pipeline for the hackathon demo.

// Use the same hostname the page was loaded from (localhost vs 127.0.0.1)
// so the API call's origin matches the page's origin as closely as
// possible -- avoids a class of CORS mismatches in local development.
const API_BASE = window.LEXASSIST_API_BASE || `http://${window.location.hostname}:8000`;

let currentDocumentId = null;

const uploadForm = document.getElementById("upload-form");
const uploadStatus = document.getElementById("upload-status");
const summarySection = document.getElementById("summary-section");
const summaryText = document.getElementById("summary-text");
const clauseCount = document.getElementById("clause-count");
const askSection = document.getElementById("ask-section");
const askForm = document.getElementById("ask-form");
const answerOutput = document.getElementById("answer-output");
const actionsSection = document.getElementById("actions-section");
const riskButton = document.getElementById("risk-button");
const checklistButton = document.getElementById("checklist-button");
const riskOutput = document.getElementById("risk-output");
const checklistOutput = document.getElementById("checklist-output");

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

uploadForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const fileInput = document.getElementById("file-input");
  const file = fileInput.files[0];
  if (!file) return;

  uploadStatus.textContent = "Analyzing document…";
  const formData = new FormData();
  formData.append("file", file);

  try {
    const response = await fetch(`${API_BASE}/api/documents`, {
      method: "POST",
      body: formData,
    });

    if (!response.ok) {
      const err = await response.json().catch(() => ({}));
      uploadStatus.textContent = `Error: ${err.detail || "Could not analyze document."}`;
      return;
    }

    const data = await response.json();
    currentDocumentId = data.document_id;

    uploadStatus.textContent = `Analyzed "${data.filename}" successfully.`;
    summaryText.textContent = data.plain_summary;
    clauseCount.textContent = `Detected ${data.clause_count} clause(s) in this document.`;
    summarySection.hidden = false;
    askSection.hidden = false;
    actionsSection.hidden = false;
  } catch (err) {
    uploadStatus.textContent = `Could not reach the LexAssist server (${err.message}). Check that the backend is running on port 8000 and that this page's origin is in ALLOWED_ORIGINS.`;
  }
});

askForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!currentDocumentId) return;

  const question = document.getElementById("question-input").value;
  answerOutput.textContent = "Thinking…";

  try {
    const response = await fetch(`${API_BASE}/api/ask`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ document_id: currentDocumentId, question }),
    });

    if (!response.ok) {
      const err = await response.json().catch(() => ({}));
      answerOutput.textContent = `Error: ${err.detail || "Could not get an answer."}`;
      return;
    }

    const data = await response.json();
    let html = `<p>${escapeHtml(data.answer)}</p>`;
    if (data.escalation_notice) {
      html += `<p class="help-text"><strong>Note:</strong> ${escapeHtml(data.escalation_notice)}</p>`;
    }
    if (data.cited_clause_ids.length > 0) {
      html += `<p class="help-text">Grounded in ${data.cited_clause_ids.length} clause(s) from your document.</p>`;
    }
    answerOutput.innerHTML = html;
  } catch (err) {
    answerOutput.textContent = `Could not reach the LexAssist server (${err.message}).`;
  }
});

riskButton.addEventListener("click", async () => {
  if (!currentDocumentId) return;
  riskOutput.textContent = "Scanning for risk indicators…";

  try {
    const response = await fetch(`${API_BASE}/api/documents/${currentDocumentId}/risks`);
    const data = await response.json();

    if (data.items.length === 0) {
      riskOutput.textContent = "No elevated-risk clauses were flagged in the first portion of this document.";
      return;
    }

    riskOutput.innerHTML = data.items
      .map(
        (item) => `
        <div class="risk-item ${item.severity}">
          <strong>${escapeHtml(item.label)}</strong> (${item.severity})
          <p>${escapeHtml(item.explanation)}</p>
        </div>`
      )
      .join("");
  } catch (err) {
    riskOutput.textContent = `Could not load risk report (${err.message}).`;
  }
});

checklistButton.addEventListener("click", async () => {
  if (!currentDocumentId) return;
  checklistOutput.textContent = "Generating checklist…";

  try {
    const response = await fetch(`${API_BASE}/api/documents/${currentDocumentId}/checklist`);
    const data = await response.json();

    const checklistHtml = data.checklist.map((item) => `<li>${escapeHtml(item)}</li>`).join("");
    const questionsHtml = data.questions_for_a_lawyer.map((item) => `<li>${escapeHtml(item)}</li>`).join("");

    checklistOutput.innerHTML = `
      <h3>Before you sign</h3>
      <ul>${checklistHtml}</ul>
      <h3>Questions for a lawyer</h3>
      <ul>${questionsHtml}</ul>
    `;
  } catch (err) {
    checklistOutput.textContent = `Could not generate checklist (${err.message}).`;
  }
});
