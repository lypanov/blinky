const SPEEDS = [
  { label: "step", ms: Infinity },
  { label: "1/16×", ms: 400 },
  { label: "1/8×", ms: 200 },
  { label: "1/4×", ms: 100 },
  { label: "1×", ms: 40 },
  { label: "2×", ms: 20 },
  { label: "4×", ms: 8 },
  { label: "16×", ms: 2 },
  { label: "max", ms: 0 },
];

const REG_NAMES = [
  "R0", "R1", "R2", "R3", "R4", "R5", "R6", "R7",
  "R8", "R9", "R10", "R11", "MT/R12", "SB/R13", "SP/R14", "LNK/R15",
];

const state = {
  trace: null,
  program: [],
  i: 0,
  running: false,
  timer: null,
  lastRegs: {},
};

function $(id) { return document.getElementById(id); }

async function loadJson(path) {
  const r = await fetch(path, { cache: "no-store" });
  if (!r.ok) throw new Error(`${path}: ${r.status}`);
  return r.json();
}

function hex32(v) {
  return "0x" + (Number(v) >>> 0).toString(16).padStart(8, "0");
}

function renderSource(modLines) {
  const ol = $("source");
  ol.innerHTML = "";
  modLines.forEach((line) => {
    const li = document.createElement("li");
    li.textContent = line || " ";
    ol.appendChild(li);
  });
}

function renderAsm(program) {
  const root = $("asm");
  root.innerHTML = "";
  program.forEach((e) => {
    const row = document.createElement("div");
    row.className = "row";
    row.dataset.addr = String(e.addr);
    row.innerHTML = `
      <span class="arrow"></span>
      <span class="addr">${hex32(e.addr).replace("0x", "")}</span>
      <span class="hex">${e.hex}</span>
      <span class="mn">${escapeHtml(e.disasm)}</span>`;
    root.appendChild(row);
    if (e.src || e.note) {
      const src = document.createElement("div");
      src.className = "src";
      src.style.padding = "0 10px 4px 98px";
      src.textContent = e.src ? `; ${e.src}` : `; ${e.note}`;
      src.dataset.addr = String(e.addr);
      root.appendChild(src);
    }
  });
}

function renderRegsGrid() {
  const root = $("regs");
  root.innerHTML = "";
  for (let i = 0; i < 16; i++) {
    const d = document.createElement("div");
    d.className = "reg";
    d.id = `reg-${i}`;
    d.innerHTML = `<div class="n">${REG_NAMES[i]}</div><div class="v">—</div>`;
    root.appendChild(d);
  }
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

function setLed(on) {
  const halo = $("led-halo");
  const body = $("led-body");
  const core = $("led-core");
  const label = $("led-state");
  const caption = $("led-caption");
  if (on) {
    halo.setAttribute("opacity", "0.7");
    halo.setAttribute("filter", "url(#glow)");
    body.setAttribute("fill", "#39ff88");
    body.setAttribute("stroke", "#b6ffd4");
    core.setAttribute("fill", "#f4ffe8");
    label.textContent = "ON";
    label.style.color = "#39ff88";
    if (caption) {
      caption.textContent = "ON";
      caption.setAttribute("fill", "#39ff88");
    }
  } else {
    halo.setAttribute("opacity", "0");
    halo.removeAttribute("filter");
    body.setAttribute("fill", "#14331f");
    body.setAttribute("stroke", "#2a5a3c");
    core.setAttribute("fill", "#1a3d28");
    label.textContent = "OFF";
    label.style.color = "";
    if (caption) {
      caption.textContent = "OFF";
      caption.setAttribute("fill", "#7fbf96");
    }
  }
}

function highlight(pc, srcLine) {
  document.querySelectorAll("#source li.current").forEach((n) => n.classList.remove("current"));
  if (srcLine) {
    const li = $("source").children[srcLine - 1];
    if (li) {
      li.classList.add("current");
      li.scrollIntoView({ block: "nearest" });
    }
  }
  document.querySelectorAll("#asm .current").forEach((n) => n.classList.remove("current"));
  document.querySelectorAll("#asm .arrow").forEach((n) => { n.textContent = ""; });
  const rows = document.querySelectorAll(`#asm [data-addr="${pc}"]`);
  rows.forEach((n) => n.classList.add("current"));
  const row = document.querySelector(`#asm .row[data-addr="${pc}"]`);
  if (row) {
    row.querySelector(".arrow").textContent = "▶";
    row.scrollIntoView({ block: "nearest" });
  }
}

function applyCycle() {
  const t = state.trace;
  if (!t || !t.cycles.length) return;
  const i = Math.max(0, Math.min(state.i, t.cycles.length - 1));
  state.i = i;
  const c = t.cycles[i];
  $("cycle").textContent = String(c.cycle);
  $("pc").textContent = hex32(c.pc);
  setLed(!!c.led);
  $("instr-line").textContent = c.disasm
    ? `${hex32(c.pc)}  ${c.disasm}${c.src ? "   // " + c.src : (c.note ? "   // " + c.note : "")}`
    : "—";
  highlight(c.pc, c.srcLine);

  const regs = [c.r0, c.r1, c.r2, c.r3];
  for (let r = 0; r < 16; r++) {
    const el = $(`reg-${r}`);
    const val = (typeof c["r" + r] === "number") ? c["r" + r]
              : (r < 4 ? regs[r] : undefined);
    const text = (typeof val === "number") ? hex32(val) : "—";
    const v = el.querySelector(".v");
    el.classList.toggle("changed", state.lastRegs[r] !== undefined && state.lastRegs[r] !== text);
    v.textContent = text;
    if (typeof val === "number") state.lastRegs[r] = text;
  }

  const edges = t.led_toggles || (t.summary && t.summary.toggle_cycles) || [];
  const periods = [];
  for (let k = 1; k < edges.length; k++) periods.push(edges[k] - edges[k - 1]);
  const mean = periods.length ? (periods.reduce((a, b) => a + b, 0) / periods.length) : null;
  $("period").textContent = mean == null ? "—" : `${mean.toFixed(1)} cyc`;

  document.querySelectorAll("#flags span").forEach((el) => {
    const bit = c[el.dataset.flag];
    el.classList.toggle("on", bit === 1 || bit === true);
  });
}

function stop() {
  state.running = false;
  if (state.timer) {
    clearInterval(state.timer);
    state.timer = null;
  }
  const btn = $("btn-run");
  btn.textContent = "Run";
  btn.classList.remove("running");
}

function tick() {
  if (state.i >= state.trace.cycles.length - 1) {
    stop();
    return;
  }
  state.i += 1;
  applyCycle();
}

function play() {
  if (!state.trace) return;
  if (state.i >= state.trace.cycles.length - 1) state.i = 0;
  state.running = true;
  const btn = $("btn-run");
  btn.textContent = "Pause";
  btn.classList.add("running");
  schedule();
}

function schedule() {
  if (state.timer) {
    clearInterval(state.timer);
    state.timer = null;
  }
  if (!state.running) return;
  const idx = Number($("speed").value);
  const ms = SPEEDS[idx].ms;
  if (!Number.isFinite(ms)) {
    stop();
    return;
  }
  if (ms === 0) {
    const pump = () => {
      if (!state.running) return;
      for (let n = 0; n < 8 && state.running; n++) tick();
      if (state.running) requestAnimationFrame(pump);
    };
    requestAnimationFrame(pump);
    return;
  }
  state.timer = setInterval(tick, ms);
}

function bind() {
  $("btn-run").onclick = () => (state.running ? stop() : play());
  $("btn-step").onclick = () => { stop(); tick(); };
  $("btn-reset").onclick = () => { stop(); state.i = 0; state.lastRegs = {}; applyCycle(); };
  $("speed").oninput = () => {
    $("speed-label").textContent = SPEEDS[Number($("speed").value)].label;
    if (state.running) schedule();
  };
  $("speed-label").textContent = SPEEDS[Number($("speed").value)].label;
  document.addEventListener("keydown", (ev) => {
    if (ev.target.tagName === "INPUT") return;
    if (ev.code === "Space") { ev.preventDefault(); state.running ? stop() : play(); }
    else if (ev.key === "s" || ev.key === "S") { stop(); tick(); }
    else if (ev.key === "r" || ev.key === "R") { $("btn-reset").click(); }
    else if (ev.key === "[") {
      $("speed").value = Math.max(0, Number($("speed").value) - 1);
      $("speed").dispatchEvent(new Event("input"));
    } else if (ev.key === "]") {
      $("speed").value = Math.min(SPEEDS.length - 1, Number($("speed").value) + 1);
      $("speed").dispatchEvent(new Event("input"));
    }
  });
}

async function main() {
  bind();
  renderRegsGrid();
  try {
    const [trace, programDoc] = await Promise.all([
      loadJson("./trace.json"),
      loadJson("./program.json").catch(() => null),
    ]);
    state.trace = trace;
    const program = (programDoc && programDoc.entries) || [];
    state.program = program;
    $("mod-file").textContent = trace.mod_file || "tests/Blink2test.Mod";
    renderSource(trace.mod_source || []);
    renderAsm(program);
    applyCycle();
  } catch (err) {
    $("instr-line").textContent = "Failed to load trace.json. Run tools/run_verilator_sim.sh first, then tools/run_visualizer.sh.";
    console.error(err);
  }
}

main();
