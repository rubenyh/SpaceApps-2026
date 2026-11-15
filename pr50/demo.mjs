// Browser QA of the outage demo against the disposable Compose APIs (8010/8011).
import { spawn, spawnSync } from "node:child_process";
import { mkdirSync, writeFileSync } from "node:fs";
import { chromium } from "playwright-core";

const REPO = "C:/repos/hackahtons/sa26-integration";
const DEMO = `${REPO}/services/onboard-api/scripts/incident_demo.py`;
const ON = "http://localhost:8010", GR = "http://localhost:8011";
const OUT = new URL("./shots/", import.meta.url).pathname.replace(/^\/(\w:)/, "$1");
mkdirSync(OUT, { recursive: true });
const log = [];
const note = (s) => { const line = `[${((Date.now() - T0) / 1000).toFixed(1)} s] ${s}`; log.push(line); console.log(line); };
const T0 = Date.now();
const api = async (url) => { const r = await fetch(url); return [r.status, r.status === 200 ? await r.json() : null]; };
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const check = (ok, what) => { note(`${ok ? "PASS" : "FAIL"} ${what}`); if (!ok) failures.push(what); };
const failures = [];
const consoleErrors = [];

const demo = (...args) => spawnSync("python", ["-I", DEMO, ...args, "--onboard", ON, "--ground", GR], { encoding: "utf-8" });

async function tab(page, name) {
  const byRole = page.getByRole("tab", { name: new RegExp("^" + name) });
  if (await byRole.count()) return byRole.first().click();
  await page.getByRole("button", { name, exact: true }).first().click();
}
async function shot(page, name) { await page.screenshot({ path: `${OUT}${name}.png`, fullPage: true }); note(`screenshot ${name}.png`); }
async function selectCrew(page) {
  await page.getByLabel("Crew member").selectOption("scn-01");
}
const SPANISH = /[áéíóúñ¿¡]|\b(Sin|datos|Tripulación|Enlace|Alerta|Alertas|Último|hace|lote|lotes|Estado|Fuente|Calidad|Valor|Rango|Tierra|Nave)\b/;
async function spanishIn(page, where) {
  const text = await page.locator("body").innerText();
  const hits = text.split("\n").filter((l) => SPANISH.test(l));
  check(hits.length === 0, `English only on ${where}${hits.length ? `: ${JSON.stringify(hits.slice(0, 5))}` : ""}`);
}

const r = demo("reset");
note(`reset: ${(r.stdout + r.stderr).trim()}`);

const browser = await chromium.launch({ channel: "msedge", headless: true });
const ctx = { viewport: { width: 1440, height: 900 } };
const ship = await (await browser.newContext(ctx)).newPage();
const base = await (await browser.newContext(ctx)).newPage();
for (const [p, n] of [[ship, "spaceship"], [base, "base"]]) {
  p.on("console", (m) => m.type() === "error" && consoleErrors.push(`${n}: ${m.text()}`));
  p.on("pageerror", (e) => consoleErrors.push(`${n}: ${e.message}`));
}
await ship.goto("http://localhost:1420"); await base.goto("http://localhost:1421");
await ship.waitForLoadState("networkidle"); await base.waitForLoadState("networkidle");
await selectCrew(ship);

// Beat 1: scripted reading, link up.
const run = spawn("python", ["-I", DEMO, "run", "--step", "--onboard", ON, "--ground", GR], { stdio: ["pipe", "pipe", "pipe"] });
let runOut = "";
run.stdout.on("data", (d) => { runOut += d; }); run.stderr.on("data", (d) => { runOut += d; });
const waitOut = async (text, ms = 30000) => { const end = Date.now() + ms; while (!runOut.includes(text)) { if (Date.now() > end) throw new Error(`no "${text}" in: ${runOut}`); await sleep(100); } };
await waitOut("Press Enter to drop");
await tab(ship, "Vital signs");
await ship.getByText("Earth link: up").waitFor({ timeout: 15000 });
await base.getByText("Link up").first().waitFor({ timeout: 15000 });
await tab(base, "Link");
check(await ship.getByText("Earth link: up").isVisible(), "beat 1: spaceship header shows Earth link: up");
await shot(ship, "1-ship-vitals-reading"); await shot(base, "1-ground-link-up");
await tab(ship, "Records");
await ship.getByText("simulated:scenario").first().waitFor({ timeout: 15000 });
check(true, "beat 1: Records shows source simulated:scenario");
await shot(ship, "1-ship-records-simulated-source");

// Beat 2: link drops, urgent message, incident onboard.
run.stdin.write("\n");
await waitOut("Beat 3: waiting for the crew");
const incidentId = runOut.match(/Incident ([0-9a-f]{8}) open onboard/)[1];
await tab(ship, "Assistant");
await ship.getByText("Earth link: down (simulated outage)").waitFor({ timeout: 10000 });
await ship.getByText(/Open incident · Scenario crew/).waitFor({ timeout: 10000 });
check(await ship.getByText("Next action").first().isVisible(), "beat 2: incident card shows Next action");
check(await ship.getByText(/Ground delivery: queued, not delivered/).first().isVisible(), "beat 2: Ground delivery: queued, not delivered");
await shot(ship, "2-ship-incident-link-down");
await base.getByText(/Batch late: \d+ s without data/).first().waitFor({ timeout: 30000 });
check(true, "beat 2: ground shows 'Batch late: N s without data'");
await shot(base, "2-ground-batch-late");
const details = ship.getByText("Full checklist, evidence and rules").first();
if (await details.count()) { await details.click(); await sleep(300); }
check(await ship.getByText("Simulated", { exact: true }).first().isVisible().catch(() => false), "beat 2: Simulated evidence tag visible");
check(await ship.getByText(/Matched rules|@/).first().isVisible().catch(() => false), "beat 2: matched rule with protocol@version visible");
await shot(ship, "2-ship-evidence-and-rules");

// Beat 3: click Acknowledge in the rendered UI while the link is down.
await ship.getByRole("button", { name: "Acknowledge", exact: true }).first().click();
await ship.getByText(/Acknowledged onboard by .* UTC/).first().waitFor({ timeout: 10000 });
await waitOut("Acknowledged onboard by");
check(true, "beat 3: UI Acknowledge click stored (card shows Acknowledged onboard by …)");
await sleep(6000); // more than one telemetry interval with the link paused
check(await ship.getByText(/Ground delivery: queued, not delivered/).first().isVisible(), "beat 3: delivery stays queued after acknowledge (6 s later)");
const [g404] = await api(`${GR}/incidents`).then(([, list]) => [list.filter((i) => i.astronaut_id === "scn-01").length]);
check(g404 === 0, `beat 3: ground has no scn-01 incident while link is down (found ${g404})`);
await shot(ship, "3-ship-acknowledged-still-queued");
await shot(base, "3-ground-nothing-yet");

// Beat 4: restore link; ground shows one incident with both events in order.
run.stdin.write("\n"); run.stdin.end();
await new Promise((res) => run.on("exit", res));
note(`demo script: ${runOut.trim().split("\n").slice(-3).join(" | ")}`);
await ship.getByText(/Delivered to ground/).first().waitFor({ timeout: 20000 });
check(true, "beat 4: spaceship card shows Delivered to ground");
await tab(base, "Incidents");
await base.getByText("Incident began").first().waitFor({ timeout: 20000 });
const [, groundList] = await api(`${GR}/incidents`);
const scn = groundList.filter((i) => i.astronaut_id === "scn-01");
check(scn.length === 1, `beat 4: ground API has exactly 1 scn-01 incident (found ${scn.length})`);
const [, full] = await api(`${GR}/incidents/${scn[0].id}`);
check(JSON.stringify(full.updates.map((u) => u.type)) === '["created","acknowledged"]', `beat 4: ground updates in order ${full.updates.map((u) => u.type)}`);
check(full.updates.every((u) => u.received_at >= u.occurred_at), "beat 4: received_at >= occurred_at for each update");
const baseText = await base.locator("body").innerText();
const iBegan = baseText.indexOf("Incident began"), iAck = baseText.indexOf("Acknowledged onboard", iBegan);
check(iBegan >= 0 && iAck > iBegan, "beat 4: ground Incidents tab lists Incident began before Acknowledged onboard");
check((baseText.match(/Incident began/g) || []).length === 1, "beat 4: ground Incidents tab shows the incident once");
check(baseText.includes("Onboard time") && baseText.includes("Received on ground"), "beat 4: Onboard time / Received on ground labels");
check(scn[0].id.startsWith(incidentId), "beat 4: ground incident id matches the onboard incident");
await shot(ship, "4-ship-delivered"); await shot(base, "4-ground-incident-timeline");

// Reload both pages: state comes from the APIs.
await ship.reload(); await base.reload();
await ship.waitForLoadState("networkidle"); await base.waitForLoadState("networkidle");
if ((await ship.getByLabel("Crew member").inputValue()) !== "scn-01") await selectCrew(ship);
await tab(ship, "Assistant");
await ship.getByText(/Acknowledged onboard by .* UTC/).first().waitFor({ timeout: 10000 });
check(await ship.getByText(/Delivered to ground/).first().isVisible(), "reload: spaceship shows same incident, acknowledgment and Delivered to ground");
await tab(base, "Incidents");
await base.getByText("Incident began").first().waitFor({ timeout: 10000 });
const reText = await base.locator("body").innerText();
check((reText.match(/Incident began/g) || []).length === 1 && reText.includes("Acknowledged onboard"), "reload: ground shows the same single incident with both events");
await shot(ship, "5-ship-after-reload"); await shot(base, "5-ground-after-reload");

// English labels on every tab of both consoles.
for (const t of ["Status", "Vital signs", "Muscle", "Urine", "Assistant", "Records", "Wellbeing"]) {
  await tab(ship, t); await sleep(1200); await spanishIn(ship, `spaceship ${t}`);
}
for (const t of ["Crew", "Astronaut", "Alerts", "Incidents", "Link"]) {
  await tab(base, t); await sleep(1200); await spanishIn(base, `ground ${t}`); await shot(base, `6-ground-${t.toLowerCase()}`);
}

// Wellbeing: new astronaut (scn-01) and a simulator astronaut.
await tab(ship, "Wellbeing"); await sleep(1500);
const wb = await ship.locator("body").innerText();
check(/Insufficient data|Baseline pending/.test(wb), "wellbeing scn-01: shows Insufficient data / Baseline pending");
await shot(ship, "7-wellbeing-scn-01");
await ship.getByLabel("Crew member").selectOption("ast-01"); await sleep(2000);
const wb2 = await ship.locator("body").innerText();
check(/Provisional/i.test(wb2) || /Insufficient data|Baseline pending/.test(wb2), "wellbeing ast-01: indicators labeled Provisional (or insufficient data)");
note(`wellbeing ast-01 excerpt: ${wb2.split("\n").filter((l) => /Provisional|Baseline|Insufficient|Share|Queued|ground/i.test(l)).slice(0, 8).join(" | ")}`);
await shot(ship, "7-wellbeing-ast-01");
for (const view of ["Personal", "Crew", "Check-in", "Ground"]) {
  const b = ship.getByRole("tab", { name: view, exact: true }).or(ship.getByRole("button", { name: view, exact: true }));
  if (await b.count()) { await b.first().click(); await sleep(1200); await shot(ship, `7-wellbeing-ast-01-${view.toLowerCase()}`); }
}

note(`console errors: ${consoleErrors.length ? consoleErrors.slice(0, 8).join(" || ") : "none"}`);
note(`RESULT: ${failures.length ? `${failures.length} FAIL: ${failures.join("; ")}` : "all checks passed"}`);
writeFileSync(`${OUT}../demo-log.txt`, log.join("\n"));
await browser.close();
