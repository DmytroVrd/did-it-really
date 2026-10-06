const form = document.getElementById("check-form");
const button = document.getElementById("check-btn");
const result = document.getElementById("result");
const formError = document.getElementById("form-error");

const presets = document.querySelectorAll(".preset");
let session = "auto";

const BUTTON_LABEL = "▶ RUN CHECK";
const BADGES = { done: "✓ VERIFIED", not_done: "✗ NOT FOUND", unverifiable: "! UNVERIFIABLE" };
const SUMMARY_LABELS = { done: "verified", not_done: "not found", unverifiable: "unverifiable" };

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function renderEvidence(text) {
  const pre = el("pre", "evidence");
  for (const line of text.split("\n")) {
    const kind = line.startsWith("###") ? "file" : line.startsWith("+") ? "add" : line.startsWith("-") ? "del" : "";
    pre.append(el("span", kind, line + "\n"));
  }
  return pre;
}

function renderSummary(summary) {
  // pytest style: ==== 1 verified · 2 not found · 1 unverifiable ====
  const line = el("p", "summary", "==== ");
  Object.keys(SUMMARY_LABELS).forEach((verdict, i) => {
    if (i) line.append(" · ");
    line.append(el("span", verdict, `${summary[verdict]} ${SUMMARY_LABELS[verdict]}`));
  });
  line.append(" ====");
  return line;
}

function clearErrors() {
  document.querySelectorAll(".field-error").forEach((p) => (p.textContent = ""));
  formError.hidden = true;
}

function renderResult(data) {
  result.replaceChildren(renderSummary(data.summary), el("p", "mode", `Compared: ${data.mode}`));
  for (const w of data.warnings) result.append(el("p", "warning", w));

  const list = el("ol", "claims");
  for (const c of data.claims) {
    const item = el("li", `claim ${c.verdict}`);
    item.append(
      el("span", "badge", BADGES[c.verdict]),
      el("p", "claim-text", c.claim),
      el("p", "explanation", c.explanation),
    );
    if (c.evidence) item.append(renderEvidence(c.evidence));
    list.append(item);
  }
  result.append(list);

  if (data.unmentioned.length) {
    const block = el("div", "unmentioned");
    block.append(el("h2", "", "Changes the agent didn't mention"));
    const files = el("ul");
    for (const u of data.unmentioned) {
      const row = el("li");
      row.append(el("span", "file", u.file), " ", el("span", "add", `+${u.added}`), " ", el("span", "del", `-${u.removed}`));
      files.append(row);
    }
    block.append(files);
    result.append(block);
  }
  result.hidden = false;
}

for (const preset of presets) {
  preset.addEventListener("click", () => {
    session = preset.dataset.session;
    presets.forEach((p) => p.setAttribute("aria-pressed", String(p === preset)));
  });
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  clearErrors();
  result.hidden = true;
  button.disabled = true;
  button.textContent = "Checking…";
  try {
    const response = await fetch("/api/check", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        report: form.report.value,
        repo_path: form.repo_path.value,
        session,
      }),
    });
    const data = await response.json();
    if (!response.ok) {
      const target = data.field && document.querySelector(`.field-error[data-for="${data.field}"]`);
      if (target) target.textContent = data.error;
      else { formError.textContent = data.error; formError.hidden = false; }
      return;
    }
    renderResult(data);
  } catch (err) {
    formError.textContent = `Request failed: ${err.message}`;
    formError.hidden = false;
  } finally {
    button.disabled = false;
    button.textContent = BUTTON_LABEL;
  }
});
