/**
 * Playwright helper for Cursor Automations (WSAI Factory).
 *
 * Phases: login | dump | probe | create | finish
 *
 * finish = complete the 4 already-named drafts (instructions + triggers + save + activate)
 */
import { chromium } from "playwright";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO = path.resolve(__dirname, "..");
const PROFILE = path.join(REPO, ".cursor", "playwright-cursor-profile");
const OUT = path.join(REPO, ".cursor", "playwright-out");
const AUTOMATIONS_DIR = path.join(REPO, "automations");

const DRAFTS = [
  {
    id: "inbox",
    name: "WSAI Factory — inbox ingest",
    file: "inbox.md",
    url: "https://cursor.com/automations/dfeb5baa-87ae-11f1-b532-320a589b8025",
    triggerKind: "github-push",
    pathFilter: "pipeline/inbox/**",
  },
  {
    id: "docs",
    name: "WSAI Factory — official docs",
    file: "docs.md",
    url: "https://cursor.com/automations/f625f130-87ae-11f1-b532-320a589b8025",
    triggerKind: "webhook",
    pathFilter: null,
  },
  {
    id: "align",
    name: "WSAI Factory — align",
    file: "align.md",
    url: "https://cursor.com/automations/0da03e35-87af-11f1-b532-320a589b8025",
    triggerKind: "webhook",
    pathFilter: null,
  },
  {
    id: "modularize",
    name: "WSAI Factory — modularize",
    file: "modularize.md",
    url: "https://cursor.com/automations/25abdb28-87af-11f1-b532-320a589b8025",
    triggerKind: "webhook",
    pathFilter: null,
  },
];

function requireArg(name) {
  const idx = process.argv.indexOf(name);
  if (idx < 0 || idx + 1 >= process.argv.length) {
    throw new Error(`missing required arg ${name}`);
  }
  return process.argv[idx + 1];
}

function readPrompt(fileName) {
  const full = path.join(AUTOMATIONS_DIR, fileName);
  if (!fs.existsSync(full)) {
    throw new Error(`missing automation prompt: ${full}`);
  }
  return fs.readFileSync(full, "utf8");
}

async function openContext() {
  fs.mkdirSync(PROFILE, { recursive: true });
  fs.mkdirSync(OUT, { recursive: true });
  const context = await chromium.launchPersistentContext(PROFILE, {
    headless: false,
    viewport: { width: 1440, height: 960 },
    args: ["--disable-blink-features=AutomationControlled"],
  });
  await context.grantPermissions(["clipboard-read", "clipboard-write"], {
    origin: "https://cursor.com",
  });
  const page = context.pages()[0] ?? (await context.newPage());
  return { context, page };
}

async function dump(page, label) {
  const shot = path.join(OUT, `${label}.png`);
  const text = path.join(OUT, `${label}.txt`);
  await page.screenshot({ path: shot, fullPage: true });
  const bodyText = await page.locator("body").innerText().catch(() => "");
  fs.writeFileSync(
    text,
    [`URL: ${page.url()}`, `TITLE: ${await page.title()}`, "", bodyText].join("\n"),
    "utf8",
  );
  console.log(JSON.stringify({ ok: true, label, url: page.url(), shot, text }));
}

async function dismissOverlays(page) {
  for (let i = 0; i < 3; i += 1) {
    await page.keyboard.press("Escape");
    await page.waitForTimeout(250);
  }
  // click inert backdrop if still present
  const backdrop = page.locator(".ui-menu__backdrop").first();
  if ((await backdrop.count()) > 0 && (await backdrop.isVisible().catch(() => false))) {
    await page.keyboard.press("Escape");
    await page.waitForTimeout(300);
  }
}

async function setInstructions(page, prompt) {
  await dismissOverlays(page);
  const box = page.locator(".ui-automations-prompt-editor, [role='textbox'][contenteditable='true']").first();
  await box.waitFor({ state: "visible", timeout: 15000 });
  await box.click({ force: true });
  await page.keyboard.press("Control+A");
  await page.keyboard.press("Backspace");
  await page.evaluate(async (text) => {
    await navigator.clipboard.writeText(text);
  }, prompt);
  await page.keyboard.press("Control+V");
  await page.waitForTimeout(700);
  const current = (await box.innerText()).trim();
  if (current.length < 40) {
    // fallback: type first 200 chars then paste again
    await box.click({ force: true });
    await page.keyboard.insertText(prompt);
    await page.waitForTimeout(500);
  }
  const again = (await box.innerText()).trim();
  if (again.length < 40) {
    throw new Error(`instructions still empty (len=${again.length})`);
  }
}

async function ensureRepo(page) {
  if ((await page.getByText(/wsai-factory/i).count()) > 0) {
    return "present";
  }
  const repoBtn = page.getByRole("button", { name: /select repository/i });
  if ((await repoBtn.count()) === 0) {
    return "missing";
  }
  await repoBtn.first().click();
  await page.waitForTimeout(700);
  await page.keyboard.type("wsai-factory", { delay: 30 });
  await page.waitForTimeout(900);
  const opt = page.getByText(/wsai-factory/i).first();
  if ((await opt.count()) > 0) {
    await opt.click();
    await page.waitForTimeout(500);
    return "selected";
  }
  await dismissOverlays(page);
  return "not-found";
}

async function addGithubPushTrigger(page, pathFilter) {
  await dismissOverlays(page);
  const bodyBefore = await page.locator("body").innerText();
  if (/push to branch/i.test(bodyBefore) && /trigger/i.test(bodyBefore)) {
    return { ok: true, skipped: true };
  }
  await page.getByRole("button", { name: /add trigger/i }).first().click();
  await page.waitForTimeout(700);
  await dump(page, "trig-root");
  const github = page.getByText(/^GitHub$/i).first();
  if ((await github.count()) === 0) {
    await dismissOverlays(page);
    return { ok: false, reason: "github-category-missing" };
  }
  await github.click();
  await page.waitForTimeout(700);
  await dump(page, "trig-github");
  const push = page.getByText(/push to branch/i).first();
  if ((await push.count()) === 0) {
    // alternate labels
    const alt = page.getByText(/push/i).first();
    if ((await alt.count()) === 0) {
      await dismissOverlays(page);
      return { ok: false, reason: "push-trigger-missing" };
    }
    await alt.click();
  } else {
    await push.click();
  }
  await page.waitForTimeout(900);
  await dump(page, "trig-push-form");
  if (pathFilter !== null) {
    const inputs = page.locator("input:visible");
    const n = await inputs.count();
    let filled = false;
    for (let i = 0; i < n; i += 1) {
      const el = inputs.nth(i);
      const ph = ((await el.getAttribute("placeholder")) || "").toLowerCase();
      const al = ((await el.getAttribute("aria-label")) || "").toLowerCase();
      const name = ((await el.getAttribute("name")) || "").toLowerCase();
      if (
        ph.includes("path") ||
        al.includes("path") ||
        name.includes("path") ||
        ph.includes("glob") ||
        al.includes("glob")
      ) {
        await el.fill(pathFilter);
        filled = true;
        break;
      }
    }
    if (!filled && n > 0) {
      // last visible text input often is path filter
      await inputs.nth(n - 1).fill(pathFilter);
    }
  }
  const confirm = page.getByRole("button", {
    name: /^(add|save|done|confirm|create|apply)$/i,
  });
  if ((await confirm.count()) > 0) {
    await confirm.first().click();
  }
  await page.waitForTimeout(600);
  await dismissOverlays(page);
  return { ok: true };
}

async function addWebhookTrigger(page) {
  await dismissOverlays(page);
  const bodyBefore = await page.locator("body").innerText();
  if (/webhook/i.test(bodyBefore) && /Triggers/i.test(bodyBefore)) {
    // may already have one — still ok
  }
  await page.getByRole("button", { name: /add trigger/i }).first().click();
  await page.waitForTimeout(700);
  await dump(page, "trig-root-webhook");
  const webhook = page.getByText(/webhook triggered/i).first();
  if ((await webhook.count()) === 0) {
    const alt = page.getByText(/^Webhook$/i).first();
    if ((await alt.count()) === 0) {
      await dismissOverlays(page);
      return { ok: false, reason: "webhook-missing" };
    }
    await alt.click();
  } else {
    await webhook.click();
  }
  await page.waitForTimeout(900);
  await dump(page, "trig-webhook-form");
  const confirm = page.getByRole("button", {
    name: /^(add|save|done|confirm|create|apply)$/i,
  });
  if ((await confirm.count()) > 0) {
    await confirm.first().click();
  }
  await page.waitForTimeout(600);
  await dismissOverlays(page);
  return { ok: true };
}

async function saveAndActivate(page) {
  await dismissOverlays(page);
  const save = page.getByRole("button", { name: /^save$/i }).first();
  await save.waitFor({ state: "visible", timeout: 10000 });
  // wait until enabled
  const deadline = Date.now() + 20000;
  while (Date.now() < deadline) {
    const disabled = await save.isDisabled();
    if (!disabled) {
      break;
    }
    await page.waitForTimeout(400);
  }
  if (await save.isDisabled()) {
    throw new Error("Save still disabled after setup");
  }
  await save.click();
  await page.waitForTimeout(1200);
  // activate if Inactive
  const inactive = page.getByText("Inactive", { exact: true });
  if ((await inactive.count()) > 0) {
    // click the switch near status
    const sw = page.locator('[role="switch"]').first();
    if ((await sw.count()) > 0) {
      const state = await sw.getAttribute("aria-checked");
      if (state !== "true") {
        await sw.click({ force: true });
        await page.waitForTimeout(500);
        if (!(await save.isDisabled())) {
          await save.click();
          await page.waitForTimeout(800);
        }
      }
    } else {
      // click Inactive label area (often toggles)
      await inactive.first().click({ force: true });
      await page.waitForTimeout(500);
      if (!(await save.isDisabled())) {
        await save.click();
        await page.waitForTimeout(800);
      }
    }
  }
}

async function finishOne(page, draft) {
  await page.goto(draft.url, { waitUntil: "domcontentloaded" });
  await page.getByText("Agent Instructions").first().waitFor({ timeout: 30000 });
  await dump(page, `finish-before-${draft.id}`);
  const repo = await ensureRepo(page);
  await setInstructions(page, readPrompt(draft.file));
  let trigger;
  if (draft.triggerKind === "github-push") {
    trigger = await addGithubPushTrigger(page, draft.pathFilter);
  } else {
    trigger = await addWebhookTrigger(page);
  }
  await saveAndActivate(page);
  await dump(page, `finish-after-${draft.id}`);
  const body = await page.locator("body").innerText();
  return {
    id: draft.id,
    url: page.url(),
    repo,
    trigger,
    hasName: body.includes(draft.name),
    active: /Active/i.test(body) && !/Inactive/i.test(body.split("\n").slice(0, 40).join("\n")),
    bodyHasPromptSnippet: body.includes("Hard rules") || body.includes("Hard rules".toLowerCase()) || body.length > 500,
  };
}

async function phaseFinish() {
  const { context, page } = await openContext();
  const results = [];
  for (const draft of DRAFTS) {
    try {
      const result = await finishOne(page, draft);
      results.push({ ok: true, ...result });
      console.log(JSON.stringify({ step: "finished", ...result }));
    } catch (error) {
      const msg = error instanceof Error ? error.message : String(error);
      await dump(page, `finish-error-${draft.id}`);
      results.push({ ok: false, id: draft.id, error: msg, url: page.url() });
      console.log(JSON.stringify({ step: "error", id: draft.id, error: msg }));
    }
  }
  console.log(JSON.stringify({ ok: results.every((r) => r.ok), results }, null, 2));
  await context.close();
}

async function phaseLogin() {
  const { context, page } = await openContext();
  await page.goto("https://cursor.com/automations", { waitUntil: "domcontentloaded" });
  console.log(JSON.stringify({ ok: true, message: "Connecte-toi si besoin" }));
  const deadline = Date.now() + 10 * 60 * 1000;
  while (Date.now() < deadline) {
    if ((await page.getByText("New Automation").count()) > 0) {
      break;
    }
    await page.waitForTimeout(1500);
  }
  await dump(page, "logged-in");
  await context.close();
}

const phase = requireArg("--phase");
if (phase === "login") {
  await phaseLogin();
} else if (phase === "finish") {
  await phaseFinish();
} else {
  throw new Error(`use --phase login|finish (got ${phase})`);
}
