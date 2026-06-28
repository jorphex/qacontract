// Read-only live state viewer for King of the Hill v4.
// Connects to a real contract via the same-origin /api/rpc proxy.
// Falls back to mock data if no contract is configured.

const ERC20_ABI = [
  'function decimals() view returns (uint8)',
  'function symbol() view returns (string)',
  'function balanceOf(address) view returns (uint256)',
];

const EMPTY_ADDRESS = '0x' + '0'.repeat(40);
const MOCK_GAME_DURATION_S = 5 * 3600;

const THEME = {
  bg: '#08050a',
  grid: 'rgba(255, 251, 245, 0.06)',
  text: '#fffbf5',
  textSecondary: '#9a8b7a',
  accent: '#ff7b00',
  curve: '#ff7b00',
};

let provider = null;
let contract = null;
let tokenContract = null;
let tokenDecimals = 18;
let useMock = false;
let stateDirty = true;

function nowSeconds() {
  return Math.floor(Date.now() / 1000);
}

function buildMockState() {
  const start = nowSeconds() - Math.floor(0.9 * MOCK_GAME_DURATION_S);
  const deadline = start + MOCK_GAME_DURATION_S;
  return {
    startTime: start,
    deadline,
    gameDuration: MOCK_GAME_DURATION_S,
    maxAmount: 200,
    floorAmount: 5,
    curveExponent: 2,
    prizePool: 200n * 10n ** 18n,
    funded: true,
    started: true,
    ended: false,
    currentHolder: '0xAbCDEF1234567890abcdef1234567890ABCDEF12',
    kingSince: start + Math.floor(0.7 * MOCK_GAME_DURATION_S),
    currentPrize: 120n * 10n ** 18n,
    paidAmount: 0n,
    winner: null,
    tokenSymbol: 'TEST',
    reigns: [
      { start: start + 0.00 * MOCK_GAME_DURATION_S, end: start + 0.25 * MOCK_GAME_DURATION_S, player: '0x1111111111111111111111111111111111111111' },
      { start: start + 0.25 * MOCK_GAME_DURATION_S, end: start + 0.55 * MOCK_GAME_DURATION_S, player: '0x2222222222222222222222222222222222222222' },
      { start: start + 0.55 * MOCK_GAME_DURATION_S, end: start + 0.80 * MOCK_GAME_DURATION_S, player: '0x3333333333333333333333333333333333333333' },
      { start: start + 0.80 * MOCK_GAME_DURATION_S, end: null, player: '0xAbCDEF1234567890abcdef1234567890ABCDEF12' },
    ],
  };
}

let state = buildMockState();
let config = null;

async function loadConfig() {
  const [configRes, abiRes] = await Promise.all([
    fetch('/api/config'),
    fetch('/abi.json'),
  ]);
  if (!configRes.ok || !abiRes.ok) throw new Error('config or ABI not available');
  const cfg = await configRes.json();
  const abi = await abiRes.json();
  if (!cfg.contractAddress || cfg.contractAddress.toLowerCase() === EMPTY_ADDRESS) {
    throw new Error('contract address not configured');
  }
  if (!cfg.rpcProxyUrl) throw new Error('RPC proxy not configured');
  return { config: cfg, abi };
}

function formatAddress(addr) {
  if (!addr || addr === EMPTY_ADDRESS) return '-';
  const s = typeof addr === 'string' ? addr : addr.toString();
  return s.length > 12 ? `${s.slice(0, 6)}…${s.slice(-4)}` : s;
}

function formatDuration(seconds) {
  if (seconds <= 0) return '0s';
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  const parts = [];
  if (h) parts.push(`${h}h`);
  if (m) parts.push(`${m}m`);
  if (s || !parts.length) parts.push(`${s}s`);
  return parts.join(' ');
}

function formatToken(value) {
  if (value === undefined || value === null) return '-';
  try {
    const raw = typeof value === 'bigint' ? value : BigInt(value.toString());
    const human = Number(ethers.formatUnits(raw, tokenDecimals));
    return `${human.toLocaleString('en-US', { maximumFractionDigits: 4 })} ${state.tokenSymbol || ''}`.trim();
  } catch {
    return value.toString();
  }
}

function formatAmount(value) {
  if (value === undefined || value === null) return '-';
  return `${Number(value).toFixed(4)} ${state.tokenSymbol || ''}`.trim();
}

function curveValue(elapsedSeconds) {
  const { floorAmount, maxAmount, gameDuration, curveExponent } = state;
  if (!gameDuration || elapsedSeconds <= 0) return floorAmount;
  const p = Math.min(elapsedSeconds / gameDuration, 1);
  let curve = p;
  if (curveExponent === 2) curve = p * p;
  else if (curveExponent === 3) curve = p * p * p;
  return floorAmount + (maxAmount - floorAmount) * curve;
}

function timePct(timestamp) {
  if (!state.gameDuration) return 0;
  return (timestamp - state.startTime) / state.gameDuration;
}

function currentTimePct() {
  return Math.min(timePct(nowSeconds()), 1);
}

function currentPrizeValue() {
  if (!state.currentHolder || state.currentHolder === EMPTY_ADDRESS || !state.started || state.ended) {
    return 0;
  }
  return curveValue(nowSeconds() - state.kingSince);
}

// ── Stats ────────────────────────────────────────────────
function renderStats() {
  const now = nowSeconds();
  const timeLeft = Math.max(0, state.deadline - now);

  let status;
  if (state.ended) status = 'Ended';
  else if (!state.funded) status = 'Not funded';
  else if (!state.started) status = 'Funded · not started';
  else if (state.deadline && now > state.deadline) status = 'Expired · awaiting finalization';
  else status = 'Live';

  const prizeDisplay = state.ended && state.paidAmount && state.paidAmount.toString() !== '0'
    ? formatToken(state.paidAmount)
    : state.started && !state.ended && state.currentHolder && state.currentHolder !== EMPTY_ADDRESS
      ? formatAmount(currentPrizeValue())
      : state.currentPrize !== undefined
        ? formatToken(state.currentPrize)
        : formatAmount(currentPrizeValue());

  const statusEl = document.getElementById('status');
  statusEl.textContent = status;
  if (status === 'Live') statusEl.style.color = THEME.accent;
  else statusEl.style.color = '';

  document.getElementById('pool').textContent = formatToken(state.prizePool);
  document.getElementById('timer').textContent = state.ended ? '—' : formatDuration(timeLeft);
  document.getElementById('prize').textContent = prizeDisplay;

  const kingEl = document.getElementById('king');
  if (state.currentHolder && state.currentHolder !== EMPTY_ADDRESS) {
    kingEl.innerHTML = `
      <div class="king-row">
        <span class="king-address">${formatAddress(state.currentHolder)}</span>
        <span class="king-meta">since ${formatTimestamp(state.kingSince)}</span>
      </div>
    `;
  } else {
    kingEl.innerHTML = '<span class="king-empty">No one holds the hill yet.</span>';
  }
}

function formatTimestamp(ts) {
  const d = new Date(ts * 1000);
  return d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

// ── History ──────────────────────────────────────────────
function renderHistory() {
  const tbody = document.getElementById('history-body');
  tbody.innerHTML = '';

  const rows = (state.reigns || []).slice().reverse();
  if (rows.length === 0) {
    tbody.innerHTML = '<tr class="empty-row"><td colspan="3">No reigns yet.</td></tr>';
    return;
  }

  for (const reign of rows) {
    const isCurrent = reign.end === null;
    const end = isCurrent ? Math.min(nowSeconds(), state.deadline || nowSeconds()) : reign.end;
    const prize = curveValue(end - reign.start);

    const tr = document.createElement('tr');
    if (isCurrent) tr.classList.add('current-king-row');
    tr.innerHTML = `
      <td>${isCurrent ? 'now' : formatTimestamp(end)}</td>
      <td>
        ${isCurrent ? '<span class="king-dot">♔</span>' : ''}
        ${formatAddress(reign.player)}
      </td>
      <td>${formatAmount(prize)}</td>
    `;
    tbody.appendChild(tr);
  }
}

// ── Timeline chart ───────────────────────────────────────
const canvas = document.getElementById('viz');
const ctx = canvas.getContext('2d');
let canvasBounds = { width: 0, height: 0, dpr: 1 };

function setupCanvas() {
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  const rect = canvas.getBoundingClientRect();
  canvas.width = Math.floor(rect.width * dpr);
  canvas.height = Math.floor(rect.height * dpr);
  canvasBounds = { width: canvas.width, height: canvas.height, dpr };
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
}

const PAD = { top: 30, right: 30, bottom: 40, left: 50 };

function toCanvasX(pct) {
  const plotW = canvasBounds.width / canvasBounds.dpr - PAD.left - PAD.right;
  return PAD.left + pct * plotW;
}

function toCanvasY(value) {
  const plotH = canvasBounds.height / canvasBounds.dpr - PAD.top - PAD.bottom;
  const yMax = (state.maxAmount || 200) * 1.1;
  return PAD.top + plotH * (1 - value / yMax);
}

function drawLine(x1, y1, x2, y2, color, width = 2, dash = []) {
  ctx.beginPath();
  ctx.moveTo(x1, y1);
  ctx.lineTo(x2, y2);
  ctx.strokeStyle = color;
  ctx.lineWidth = width;
  ctx.setLineDash(dash);
  ctx.stroke();
  ctx.setLineDash([]);
}

function drawText(text, x, y, opts = {}) {
  ctx.font = opts.font || 'bold 11px "JetBrains Mono", monospace';
  ctx.fillStyle = opts.color || THEME.text;
  ctx.textAlign = opts.align || 'left';
  ctx.textBaseline = opts.baseline || 'middle';
  ctx.fillText(text, x, y);
}

function drawAxes() {
  const w = canvasBounds.width / canvasBounds.dpr;
  const h = canvasBounds.height / canvasBounds.dpr;
  const yMax = (state.maxAmount || 200) * 1.1;
  const step = Math.ceil((yMax / 10) / 10) * 10 || 10;

  for (let v = 0; v <= yMax; v += step) {
    const y = toCanvasY(v);
    drawLine(PAD.left, y, w - PAD.right, y, THEME.grid, 1, [4, 4]);
    drawText(String(Math.round(v)), PAD.left - 10, y, { align: 'right', color: THEME.textSecondary });
  }

  for (let t = 0; t <= 100; t += 20) {
    const x = toCanvasX(t / 100);
    drawLine(x, PAD.top, x, h - PAD.bottom, THEME.grid, 1, [4, 4]);
    drawText(String(t), x, h - PAD.bottom + 20, { align: 'center', color: THEME.textSecondary });
  }

  drawLine(PAD.left, PAD.top, PAD.left, h - PAD.bottom, THEME.textSecondary, 1.5);
  drawLine(PAD.left, h - PAD.bottom, w - PAD.right, h - PAD.bottom, THEME.textSecondary, 1.5);

  drawText('Game Time (%)', (PAD.left + w - PAD.right) / 2, h - 10, {
    align: 'center', color: THEME.textSecondary, font: 'bold 12px "JetBrains Mono", monospace',
  });
  ctx.save();
  ctx.translate(16, (PAD.top + h - PAD.bottom) / 2);
  ctx.rotate(-Math.PI / 2);
  drawText('Prize', 0, 0, { align: 'center', color: THEME.textSecondary, font: 'bold 12px "JetBrains Mono", monospace' });
  ctx.restore();
}

function drawReign(reign) {
  const startPct = timePct(reign.start);
  const endPct = reign.end === null ? currentTimePct() : timePct(reign.end);

  ctx.beginPath();
  const steps = 80;
  for (let i = 0; i <= steps; i++) {
    const pct = startPct + (endPct - startPct) * (i / steps);
    const elapsed = (pct - startPct) * state.gameDuration;
    const v = curveValue(elapsed);
    const x = toCanvasX(pct);
    const y = toCanvasY(v);
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  }
  ctx.strokeStyle = THEME.curve;
  ctx.lineWidth = 4;
  ctx.stroke();

  const endV = curveValue((endPct - startPct) * state.gameDuration);
  const endX = toCanvasX(endPct);
  const endY = toCanvasY(endV);
  ctx.beginPath();
  ctx.arc(endX, endY, 5, 0, Math.PI * 2);
  ctx.fillStyle = THEME.bg;
  ctx.fill();
  ctx.lineWidth = 2;
  ctx.strokeStyle = THEME.curve;
  ctx.stroke();

  if (reign.end !== null) {
    const floorY = toCanvasY(state.floorAmount || 0);
    drawLine(endX, endY, endX, floorY, 'rgba(255,255,255,0.6)', 2, [3, 3]);
    ctx.beginPath();
    ctx.moveTo(endX, endY);
    ctx.lineTo(endX, floorY + 4);
    ctx.strokeStyle = 'rgba(255,255,255,0.7)';
    ctx.lineWidth = 2;
    ctx.stroke();
  }
}

function drawCurrentKing() {
  const reign = state.reigns[state.reigns.length - 1];
  if (!reign) return;
  const startPct = timePct(reign.start);
  const currentPct = currentTimePct();
  const v = curveValue((currentPct - startPct) * state.gameDuration);
  const x = toCanvasX(currentPct);
  const y = toCanvasY(v);

  function drawStar(cx, cy, outer, inner, points) {
    ctx.beginPath();
    for (let i = 0; i < points * 2; i++) {
      const r = i % 2 === 0 ? outer : inner;
      const a = (Math.PI / points) * i - Math.PI / 2;
      const px = cx + Math.cos(a) * r;
      const py = cy + Math.sin(a) * r;
      if (i === 0) ctx.moveTo(px, py);
      else ctx.lineTo(px, py);
    }
    ctx.closePath();
    ctx.fillStyle = '#fff';
    ctx.fill();
  }
  drawStar(x, y, 14, 7, 5);

  const floorY = toCanvasY(state.floorAmount || 0);
  drawLine(x, y + 12, x, floorY, THEME.curve, 2, [5, 5]);
}

function drawReferenceLines() {
  const w = canvasBounds.width / canvasBounds.dpr;
  const floorY = toCanvasY(state.floorAmount || 0);
  const maxY = toCanvasY(state.maxAmount || 200);

  drawLine(PAD.left, floorY, w - PAD.right, floorY, THEME.grid, 2);
  drawLine(PAD.left, maxY, w - PAD.right, maxY, THEME.grid, 2, [6, 6]);
  drawText('FLOOR', PAD.left + 6, floorY - 8, { color: THEME.textSecondary, font: 'bold 10px "JetBrains Mono", monospace' });
  drawText('MAX PRIZE', PAD.left + 6, maxY - 8, { color: THEME.textSecondary, font: 'bold 10px "JetBrains Mono", monospace' });
}

function drawViz() {
  const w = canvasBounds.width / canvasBounds.dpr;
  const h = canvasBounds.height / canvasBounds.dpr;
  ctx.clearRect(0, 0, w, h);

  drawReferenceLines();
  drawAxes();

  for (const reign of state.reigns || []) {
    drawReign(reign);
  }

  drawCurrentKing();
}

function resizeViz() {
  setupCanvas();
  drawViz();
}

window.addEventListener('resize', resizeViz);

// ── WebGL background ─────────────────────────────────────
function initBackground() {
  const canvas = document.getElementById('gl');
  if (!canvas) return;
  const gl = canvas.getContext('webgl', { alpha: true, antialias: false, premultipliedAlpha: false });
  if (!gl) return;

  function resize() {
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = window.innerWidth * dpr;
    canvas.height = window.innerHeight * dpr;
    gl.viewport(0, 0, canvas.width, canvas.height);
  }
  resize();
  window.addEventListener('resize', resize);

  const vsSource = `
    attribute vec2 aPos;
    void main() { gl_Position = vec4(aPos, 0.0, 1.0); }
  `;

  const fsSource = `
    precision mediump float;
    uniform float uTime;
    uniform vec2 uRes;
    uniform vec2 uMouse;
    void main() {
      vec2 uv = gl_FragCoord.xy / uRes;
      vec2 mouse = uMouse / uRes;
      vec3 col = vec3(0.031, 0.02, 0.039);
      float t = uTime * 0.03;
      col += vec3(0.06, 0.02, 0.07) * sin(uv.y * 2.0 + uv.x * 0.8 + t);
      col += vec3(0.03, 0.015, 0.05) * cos(uv.x * 1.5 - uv.y * 1.2 + t * 0.6);
      float dist = length(uv - mouse);
      float glow = smoothstep(0.5, 0.0, dist);
      col += vec3(0.12, 0.05, 0.02) * glow;
      float centerGlow = smoothstep(0.5, 0.0, length(uv - 0.5));
      col += vec3(0.05, 0.02, 0.01) * centerGlow * (0.6 + 0.4 * sin(uTime * 0.12));
      gl_FragColor = vec4(col, 1.0);
    }
  `;

  function compile(src, type) {
    const s = gl.createShader(type);
    gl.shaderSource(s, src);
    gl.compileShader(s);
    if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) {
      console.warn('Shader compile failed:', gl.getShaderInfoLog(s));
      return null;
    }
    return s;
  }

  const vs = compile(vsSource, gl.VERTEX_SHADER);
  const fs = compile(fsSource, gl.FRAGMENT_SHADER);
  if (!vs || !fs) return;

  const prog = gl.createProgram();
  gl.attachShader(prog, vs);
  gl.attachShader(prog, fs);
  gl.linkProgram(prog);
  if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) {
    console.warn('Program link failed:', gl.getProgramInfoLog(prog));
    return;
  }
  gl.useProgram(prog);

  const buf = gl.createBuffer();
  gl.bindBuffer(gl.ARRAY_BUFFER, buf);
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW);
  const aPos = gl.getAttribLocation(prog, 'aPos');
  gl.enableVertexAttribArray(aPos);
  gl.vertexAttribPointer(aPos, 2, gl.FLOAT, false, 0, 0);

  const uTime = gl.getUniformLocation(prog, 'uTime');
  const uRes = gl.getUniformLocation(prog, 'uRes');
  const uMouse = gl.getUniformLocation(prog, 'uMouse');
  if (uTime === null || uRes === null || uMouse === null) return;

  let mx = window.innerWidth / 2;
  let my = window.innerHeight / 2;
  let targetMx = mx;
  let targetMy = my;

  window.addEventListener('mousemove', (e) => {
    targetMx = e.clientX * (window.devicePixelRatio || 1);
    targetMy = e.clientY * (window.devicePixelRatio || 1);
  });

  let start = performance.now();
  function frame() {
    mx += (targetMx - mx) * 0.015;
    my += (targetMy - my) * 0.015;
    const time = (performance.now() - start) / 1000;
    gl.uniform1f(uTime, time);
    gl.uniform2f(uRes, canvas.width, canvas.height);
    gl.uniform2f(uMouse, mx, my);
    gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
    requestAnimationFrame(frame);
  }
  frame();
}

// ── Contract data loading ────────────────────────────────
async function buildReignsFromEvents() {
  const shots = await contract.queryFilter('Shot');
  shots.sort((a, b) => Number(a.args.sequence) - Number(b.args.sequence));

  const reigns = [];
  let lastStart = state.startTime;
  let lastHolder = EMPTY_ADDRESS;

  for (const shot of shots) {
    const capturedAt = Number(shot.args.captured_at);
    const previousKing = shot.args.previous_king.toLowerCase();

    if (previousKing !== EMPTY_ADDRESS) {
      reigns.push({ start: lastStart, end: capturedAt, player: previousKing });
    }

    lastStart = capturedAt;
    lastHolder = shot.args.player.toLowerCase();
  }

  if (state.currentHolder && state.currentHolder !== EMPTY_ADDRESS) {
    reigns.push({ start: lastStart, end: null, player: state.currentHolder });
  }

  return reigns;
}

async function fetchContractState() {
  const tokenAddress = await contract.token();
  if (tokenAddress && tokenAddress !== EMPTY_ADDRESS && (!tokenContract || tokenContract.target !== tokenAddress)) {
    tokenContract = new ethers.Contract(tokenAddress, ERC20_ABI, provider);
    try {
      tokenDecimals = Number(await tokenContract.decimals());
      state.tokenSymbol = await tokenContract.symbol();
    } catch {
      tokenDecimals = 18;
      state.tokenSymbol = '';
    }
  }

  const [
    startTime,
    deadline,
    maxAmount,
    floorAmount,
    curveExponent,
    king,
    kingSince,
    remainingAmount,
    kingPrize,
    funded,
    started,
    ended,
    winner,
    paidAmount,
  ] = await Promise.all([
    contract.start_time(),
    contract.deadline(),
    contract.max_amount(),
    contract.floor_amount(),
    contract.curve_exponent(),
    contract.king(),
    contract.king_since(),
    contract.remaining_amount(),
    contract.king_prize(),
    contract.funded(),
    contract.started(),
    contract.ended(),
    contract.winner(),
    contract.paid_amount(),
  ]);

  state.startTime = Number(startTime);
  state.deadline = Number(deadline);
  state.gameDuration = state.deadline - state.startTime;
  state.maxAmount = Number(ethers.formatUnits(maxAmount, tokenDecimals));
  state.floorAmount = Number(ethers.formatUnits(floorAmount, tokenDecimals));
  state.curveExponent = Number(curveExponent);
  state.prizePool = remainingAmount;
  state.currentHolder = king.toLowerCase();
  state.kingSince = Number(kingSince);
  state.currentPrize = kingPrize;
  state.funded = funded;
  state.started = started;
  state.ended = ended;
  state.winner = winner.toLowerCase() === EMPTY_ADDRESS ? null : winner.toLowerCase();
  state.paidAmount = paidAmount;

  state.reigns = await buildReignsFromEvents();
}

function animate() {
  renderStats();
  drawViz();
  if (stateDirty) {
    renderHistory();
    stateDirty = false;
  }
  requestAnimationFrame(animate);
}

async function tick() {
  if (useMock) return;
  try {
    await fetchContractState();
    stateDirty = true;
  } catch (err) {
    console.error('Failed to fetch contract state:', err);
  }
}

async function init() {
  try {
    const { config: cfg, abi } = await loadConfig();
    config = cfg;

    const linkEl = document.getElementById('basescan-link');
    if (linkEl && config.contractAddress) {
      const explorerBase = config.chainId === 84532
        ? 'https://sepolia.basescan.org'
        : 'https://basescan.org';
      linkEl.href = `${explorerBase}/address/${config.contractAddress}`;
    }

    const rpcUrl = new URL(config.rpcProxyUrl, window.location.href).toString();
    provider = new ethers.JsonRpcProvider(rpcUrl);
    contract = new ethers.Contract(config.contractAddress, abi, provider);

    await contract.start_time();
    console.log('Connected to contract', config.contractAddress);
  } catch (err) {
    console.warn('Running in mock mode:', err.message);
    useMock = true;
    state = buildMockState();
  }

  await tick();
  renderHistory();
  setupCanvas();
  drawViz();
  animate();
  setInterval(tick, 1000);

  try {
    initBackground();
  } catch (err) {
    console.warn('Background init failed:', err);
  }
}

init();