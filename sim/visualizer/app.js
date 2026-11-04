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

const WATCH_ORDER = [
  [0x50, "AMMT light / LED var"],
  [0x70, "LightToggle counter"],
  [0x74, "maxIterations"],
  [0x14, "MT[1]"],
  [0x18, "MT[2]"],
  [0x10, "LED snoop 0x10"],
];

const state = {
  traces: { blink2: null, blink3: null },
  programs: { blink2: [], blink3: [] },
  image: "blink2",
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

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

function currentTrace() { return state.traces[state.image]; }
function currentProgram() { return state.programs[state.image] || []; }

function renderSource(modLines) {
  const ol = $("source");
  ol.innerHTML = "";
  (modLines || []).forEach((line) => {
    const li = document.createElement("li");
    li.textContent = line || " ";
    if (String(line).startsWith("----- ")) li.classList.add("hdr");
    ol.appendChild(li);
  });
}

function tagFor(mark) {
  if (mark === "failure-bl") return '<span class="tag tag-fail">BROKEN BL</span>';
  if (mark === "call-bl") return '<span class="tag tag-ok">BL → TOGGLE</span>';
  if (mark === "wrong-land") return '<span class="tag tag-wrong">LANDS HERE</span>';
  if (mark === "expected-target") return '<span class="tag tag-ok">TOGGLE</span>';
  if (mark === "return-addr") return '<span class="tag tag-wrong">SHOULD RETURN HERE</span>';
  if (mark === "module-init") return '<span class="tag tag-ok">AMMT BEGIN</span>';
  if (mark === "init-store") return '<span class="tag tag-ok">light := 0</span>';
  return "";
}

function renderAsm(program) {
  const root = $("asm");
  root.innerHTML = "";
  program.forEach((e) => {
    const row = document.createElement("div");
    row.className = "row" + (e.mark ? ` ${e.mark}` : "");
    row.dataset.addr = String(e.addr);
    row.innerHTML = `
      <span class="arrow"></span>
      <span class="addr">${hex32(e.addr).replace("0x", "")}</span>
      <span class="hex">${e.hex}</span>
      <span class="mn">${escapeHtml(e.disasm)}${tagFor(e.mark)}</span>`;
    root.appendChild(row);
    if (e.src || e.note) {
      const src = document.createElement("div");
      src.className = "src";
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
    d.className = "reg" + (i === 15 ? " lnk" : "");
    d.id = `reg-${i}`;
    d.innerHTML = `<div class="n">${REG_NAMES[i]}</div><div class="v">—</div>`;
    root.appendChild(d);
  }
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

function scrollPane(el, block) {
  const pane = el && el.closest(".code");
  if (!el || !pane) return;
  const er = el.getBoundingClientRect();
  const pr = pane.getBoundingClientRect();
  if (block === "nearest" && er.top >= pr.top && er.bottom <= pr.bottom) return;
  const mid = block === "center";
  const elY = er.top + (mid ? er.height / 2 : 0);
  const paneY = pr.top + (mid ? pr.height / 2 : 0);
  pane.scrollTop += elY - paneY;
}

function highlight(pc, srcLine) {
  document.querySelectorAll("#source li.current").forEach((n) => n.classList.remove("current"));
  if (srcLine) {
    const li = $("source").children[srcLine - 1];
    if (li) {
      li.classList.add("current");
      scrollPane(li, "nearest");
    }
  }
  document.querySelectorAll("#asm .current").forEach((n) => n.classList.remove("current"));
  document.querySelectorAll("#asm .arrow").forEach((n) => { n.textContent = ""; });
  const rows = document.querySelectorAll(`#asm [data-addr="${pc}"]`);
  rows.forEach((n) => n.classList.add("current"));
  const row = document.querySelector(`#asm .row[data-addr="${pc}"]`);
  if (row) {
    row.querySelector(".arrow").textContent = "▶";
    scrollPane(row, "center");
  }
}

function renderDmem(dmem) {
  const root = $("dmem");
  root.innerHTML = "";
  WATCH_ORDER.forEach(([addr, fallback]) => {
    const rec = dmem && (dmem[String(addr)] || dmem[addr]);
    const cell = document.createElement("div");
    cell.className = "cell";
    const name = rec ? rec.name : fallback;
    const val = rec ? hex32(rec.value) : "—";
    if (addr === 0x50 && rec && rec.value === 0) cell.classList.add("zeroed");
    cell.innerHTML = `<span>${hex32(addr)}</span><span>${escapeHtml(name)}</span><span class="val">${val}</span>`;
    root.appendChild(cell);
  });
}

function failBannerHtml(f) {
  if (!f) return "";
  const r15ok = f.r15_written;
  const landed = f.actual_target === f.expected_target;
  const where = landed
    ? `landed on Toggle at <code>${hex32(f.actual_target)}</code> (loader matches Modules.Mod).`
    : `jumped to <code>${hex32(f.actual_target)}</code>, not Toggle at <code>${hex32(f.expected_target)}</code>.`;
  return `BL at <code>${hex32(f.bl_pc)}</code> ${where}
    R15 ${r15ok ? "was written" : "stayed " + hex32(f.r15_after) + " — CPU never saved PC+4 (" + hex32(f.r15_expected) + ")"}.`;
}

function initBannerText(init) {
  if (!init) return "";
  const light = init.light_after === 0
    ? "dmem[0x50] light is 0"
    : `dmem[0x50] light is ${init.light_after}`;
  return `BEGIN body at ${hex32(init.begin_pc)} executes; STW at ${hex32(init.store_pc)} writes 0. ${light}.`;
}

function applyCycle() {
  const t = currentTrace();
  if (!t || !t.cycles.length) return;
  const i = Math.max(0, Math.min(state.i, t.cycles.length - 1));
  state.i = i;
  const c = t.cycles[i];
  $("stepn").textContent = String(i);
  $("steptotal").textContent = String(t.cycles.length - 1);
  $("cycle").textContent = String(c.cycle);
  $("pc").textContent = hex32(c.pc);
  setLed(!!c.led);
  $("instr-line").textContent = c.disasm
    ? `${hex32(c.pc)}  ${c.disasm}${c.src ? "   // " + c.src : (c.note ? "   // " + c.note : "")}`
    : "—";
  highlight(c.pc, c.srcLine);
  renderDmem(c.dmem);

  for (let r = 0; r < 16; r++) {
    const el = $(`reg-${r}`);
    const val = (typeof c["r" + r] === "number") ? c["r" + r] : undefined;
    const text = (typeof val === "number") ? hex32(val) : "—";
    const v = el.querySelector(".v");
    el.classList.toggle("changed", state.lastRegs[r] !== undefined && state.lastRegs[r] !== text);
    v.textContent = text;
    if (typeof val === "number") state.lastRegs[r] = text;
  }

  const f = t.failure;
  const atFail = !!(f && (i === f.step_index || i === f.landing_step_index));
  // Highlight R15 whenever we are on the BL or its landing, because the CPU
  // still does not write LNK. Target may already be Toggle (loader fixed).
  $("reg-15").classList.toggle("stale", !!(f && !f.r15_written && atFail));
  $("fail-banner").classList.toggle("here", atFail);
  const init = t.init;
  const atInit = !!(init && (i === init.begin_step_index || i === init.store_step_index));
  $("init-banner").classList.toggle("here", atInit);
  $("brand-dot").classList.toggle("fail", state.image === "blink3");

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

function tick(dir) {
  const t = currentTrace();
  if (!t) return;
  const next = state.i + (dir || 1);
  if (next < 0 || next >= t.cycles.length) {
    if (dir > 0) stop();
    return;
  }
  state.i = next;
  applyCycle();
}

function play() {
  if (!currentTrace()) return;
  if (state.i >= currentTrace().cycles.length - 1) state.i = 0;
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
      for (let n = 0; n < 8 && state.running; n++) tick(1);
      if (state.running) requestAnimationFrame(pump);
    };
    requestAnimationFrame(pump);
    return;
  }
  state.timer = setInterval(() => tick(1), ms);
}

function selectImage(name) {
  stop();
  state.image = name;
  state.i = 0;
  state.lastRegs = {};
  $("btn-blink2").classList.toggle("active", name === "blink2");
  $("btn-blink3").classList.toggle("active", name === "blink3");
  const t = currentTrace();
  const p = currentProgram();
  if (!t) {
    $("instr-line").textContent = `No ${name} trace. Run make -C sim traces`;
    return;
  }
  $("title").textContent = t.title || name;
  $("subtitle").textContent = t.subtitle || "";
  $("mod-file").textContent = t.mod_file || "";
  $("btn-fail").classList.toggle("hidden", !t.failure);
  $("btn-init").classList.toggle("hidden", !t.init);
  $("btn-light").classList.toggle("hidden", !t.init);
  $("fail-banner").classList.toggle("hidden", !t.failure);
  $("init-banner").classList.toggle("hidden", !t.init);
  if (t.failure) $("fail-text").innerHTML = failBannerHtml(t.failure);
  if (t.init) $("init-text").textContent = initBannerText(t.init);
  renderSource(t.mod_source || []);
  renderAsm(p);
  applyCycle();
}

function jumpToFailure() {
  const t = currentTrace();
  if (!t || !t.failure) return;
  stop();
  state.i = t.failure.step_index;
  applyCycle();
}

function jumpToInit() {
  const t = currentTrace();
  if (!t || !t.init) return;
  stop();
  state.i = t.init.begin_step_index;
  applyCycle();
}

function jumpToLight() {
  const t = currentTrace();
  if (!t || !t.init) return;
  stop();
  state.i = t.init.store_step_index;
  applyCycle();
}

function bind() {
  $("btn-run").onclick = () => (state.running ? stop() : play());
  $("btn-step").onclick = () => { stop(); tick(1); };
  $("btn-back").onclick = () => { stop(); tick(-1); };
  $("btn-reset").onclick = () => { stop(); state.i = 0; state.lastRegs = {}; applyCycle(); };
  $("btn-fail").onclick = jumpToFailure;
  $("btn-init").onclick = jumpToInit;
  $("btn-light").onclick = jumpToLight;
  $("btn-blink2").onclick = () => selectImage("blink2");
  $("btn-blink3").onclick = () => selectImage("blink3");
  $("speed").oninput = () => {
    $("speed-label").textContent = SPEEDS[Number($("speed").value)].label;
    if (state.running) schedule();
  };
  $("speed-label").textContent = SPEEDS[Number($("speed").value)].label;
  document.addEventListener("keydown", (ev) => {
    if (ev.target.tagName === "INPUT") return;
    if (ev.code === "Space") { ev.preventDefault(); state.running ? stop() : play(); }
    else if (ev.key === "s" || ev.key === "S" || ev.key === "ArrowRight") { stop(); tick(1); }
    else if (ev.key === "a" || ev.key === "A" || ev.key === "ArrowLeft") { stop(); tick(-1); }
    else if (ev.key === "r" || ev.key === "R") { $("btn-reset").click(); }
    else if (ev.key === "f" || ev.key === "F") { jumpToFailure(); }
    else if (ev.key === "i" || ev.key === "I") { jumpToInit(); }
    else if (ev.key === "l" || ev.key === "L") { jumpToLight(); }
    else if (ev.key === "2") selectImage("blink2");
    else if (ev.key === "3") selectImage("blink3");
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
    const [b2, b3, p2, p3] = await Promise.all([
      loadJson("./traces/blink2.json"),
      loadJson("./traces/blink3.json"),
      loadJson("./traces/blink2_program.json").catch(() => null),
      loadJson("./traces/blink3_program.json").catch(() => null),
    ]);
    state.traces.blink2 = b2;
    state.traces.blink3 = b3;
    state.programs.blink2 = (p2 && p2.entries) || [];
    state.programs.blink3 = (p3 && p3.entries) || [];
    const params = new URLSearchParams(location.search);
    const want = params.get("p") === "blink3" ? "blink3" : "blink2";
    selectImage(want);
    if (params.get("fail") != null || params.get("step") === "fail") {
      jumpToFailure();
    } else if (params.get("light") != null) {
      jumpToLight();
    } else if (params.get("init") != null) {
      jumpToInit();
    } else if (params.get("i") != null) {
      state.i = Number(params.get("i")) || 0;
      applyCycle();
    }
  } catch (err) {
    $("instr-line").textContent = "Failed to load traces. On Bee: make -C sim traces && tools/run_visualizer.sh";
    console.error(err);
  }
}

main();
