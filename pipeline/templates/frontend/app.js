async function loadManifest() {
  const response = await fetch("./assembly_manifest.json", { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`assembly_manifest.json HTTP ${response.status}`);
  }
  const data = await response.json();
  if (typeof data !== "object" || data === null) {
    throw new Error("assembly_manifest.json root must be object");
  }
  return data;
}

function render(manifest) {
  const title = document.getElementById("tool-title");
  const list = document.getElementById("module-list");
  if (!(title instanceof HTMLElement) || !(list instanceof HTMLElement)) {
    throw new Error("template nodes missing");
  }
  const toolName = manifest.tool_name;
  if (typeof toolName === "string" && toolName.trim() !== "") {
    title.textContent = toolName;
    document.title = toolName;
  }
  const modules = manifest.modules;
  if (!Array.isArray(modules)) {
    throw new Error("manifest.modules must be array");
  }
  list.replaceChildren();
  for (const item of modules) {
    if (typeof item !== "object" || item === null) {
      continue;
    }
    const jobId = item.job_id;
    const moduleName = item.module;
    const path = item.path;
    if (typeof jobId !== "string" || typeof moduleName !== "string") {
      continue;
    }
    const li = document.createElement("li");
    li.textContent =
      typeof path === "string" ? `${jobId}/${moduleName} → ${path}` : `${jobId}/${moduleName}`;
    list.appendChild(li);
  }
}

loadManifest()
  .then(render)
  .catch((error) => {
    const list = document.getElementById("module-list");
    if (list instanceof HTMLElement) {
      const li = document.createElement("li");
      li.textContent = String(error);
      list.replaceChildren(li);
    }
  });
