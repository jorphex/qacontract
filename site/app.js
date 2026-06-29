// King of the Hill v5.2 - prototype viewer wired to the live contract.

const ERC20_ABI = [
  'function decimals() view returns (uint8)',
  'function symbol() view returns (string)',
  'function balanceOf(address) view returns (uint256)',
];

const EMPTY_ADDRESS = '0x' + '0'.repeat(40);

let provider, contract, tokenContract;
let useMock = false;
let state = {};
let refreshTimer = null;
let countdownTimer = null;
let lastShotSequence = 0;
let startBlock = null;
const BASE_INTERVAL = 3000;
const ACTIVE_INTERVAL = 1000;
const IDLE_INTERVAL = 10000;
let currentInterval = BASE_INTERVAL;

// ── Helpers ────────────────────────────────────────────────
const $ = (sel) => document.querySelector(sel);
const addrShort = (a) => a && a !== EMPTY_ADDRESS ? `${a.slice(0, 6)}…${a.slice(-4)}` : 'No king';

function fmtTime(ts) {
  const d = new Date(ts * 1000);
  return d.toLocaleString('en-US', {
    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit',
  });
}

function formatDuration(seconds) {
  if (seconds <= 0) return '0s';
  const d = Math.floor(seconds / 86400);
  const h = Math.floor((seconds % 86400) / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  const parts = [];
  if (d) parts.push(`${d}d`);
  if (h) parts.push(`${h}h`);
  if (m) parts.push(`${m}m`);
  if (s || !parts.length) parts.push(`${s}s`);
  return parts.join(' ');
}

function formatToken(raw) {
  if (raw === undefined || raw === null) return '-';
  const val = Number(raw) / Math.pow(10, state.tokenDecimals || 18);
  if (val >= 1000) return `${val.toLocaleString(undefined, { maximumFractionDigits: 0 })} ${state.tokenSymbol || ''}`.trim();
  if (val >= 1) return `${val.toLocaleString(undefined, { maximumFractionDigits: 2 })} ${state.tokenSymbol || ''}`.trim();
  return `${val.toLocaleString(undefined, { maximumFractionDigits: 6 })} ${state.tokenSymbol || ''}`.trim();
}

function nowSeconds() {
  return Math.floor(Date.now() / 1000);
}

function curveValue(elapsed, floor, max, duration, exponent) {
  if (!duration || elapsed <= 0) return floor;
  const p = Math.min(elapsed / duration, 1);
  let curve = p;
  if (exponent === 2) curve = p * p;
  else if (exponent === 3) curve = p * p * p;
  return floor + (max - floor) * curve;
}

// ── Config ─────────────────────────────────────────────────
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

// ── WebGL Background ─────────────────────────────────────
function initBackground() {
  const canvas = $('#gl');
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
      vec3 col = vec3(0.02, 0.012, 0.025);
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
    console.warn('Program link failed:', gl.getShaderInfoLog(prog));
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

// ── Prize Curve Canvas ────────────────────────────────────
function drawCurve(startTime, deadline, originalDeadline, floorAmount, maxAmount, currentPrize, exponent, reigns, paidAmount, ended) {
  const canvas = $('#prize-canvas');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  const dpr = window.devicePixelRatio || 1;
  const rect = canvas.getBoundingClientRect();
  canvas.width = rect.width * dpr;
  canvas.height = rect.height * dpr;
  ctx.scale(dpr, dpr);
  const W = rect.width;
  const H = rect.height;
  const pad = { top: 24, right: 20, bottom: 28, left: 52 };
  const plotW = W - pad.left - pad.right;
  const plotH = H - pad.top - pad.bottom;

  ctx.clearRect(0, 0, W, H);

  const yMax = Math.max(maxAmount, currentPrize, paidAmount || 0) * 1.1 || 1;
  const totalDuration = Math.max(1, deadline - startTime);
  const originalDuration = originalDeadline > startTime ? originalDeadline - startTime : totalDuration;
  const gameDuration = state.gameDuration || originalDuration;
  const capTs = originalDeadline > startTime ? originalDeadline : deadline;

  const toX = (ts) => {
    const x = pad.left + ((ts - startTime) / totalDuration) * plotW;
    return Math.max(pad.left, Math.min(W - pad.right, x));
  };
  const toY = (val) => pad.top + plotH - ((val / yMax) * plotH);
  const clampedElapsed = (ts, reignStart) => Math.max(0, Math.min(ts, capTs) - reignStart);

  // Grid lines
  ctx.strokeStyle = 'rgba(255,251,245,0.04)';
  ctx.lineWidth = 1;
  const gridSteps = 4;
  for (let i = 0; i <= gridSteps; i++) {
    const y = pad.top + (plotH / gridSteps) * i;
    ctx.beginPath();
    ctx.moveTo(pad.left, y);
    ctx.lineTo(W - pad.right, y);
    ctx.stroke();

    const val = yMax - (yMax / gridSteps) * i;
    ctx.fillStyle = 'rgba(255,251,245,0.25)';
    ctx.font = '11px "JetBrains Mono", monospace';
    ctx.textAlign = 'right';
    ctx.textBaseline = 'middle';
    let label;
    if (val === 0) label = '0';
    else if (val < 1) label = val.toFixed(2);
    else if (val < 1000) label = val.toFixed(0);
    else label = `${(val / 1000).toFixed(1)}k`;
    ctx.fillText(label, pad.left - 8, y);
  }

  // Axes
  ctx.strokeStyle = 'rgba(255,251,245,0.2)';
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(pad.left, pad.top);
  ctx.lineTo(pad.left, pad.top + plotH);
  ctx.lineTo(W - pad.right, pad.top + plotH);
  ctx.stroke();

  // X labels
  ctx.textAlign = 'center';
  ctx.textBaseline = 'top';
  for (let i = 0; i <= 4; i++) {
    const pct = i / 4;
    const x = pad.left + pct * plotW;
    ctx.fillStyle = 'rgba(255,251,245,0.25)';
    ctx.fillText(`${Math.round(pct * 100)}%`, x, H - pad.bottom + 10);
  }

  // Reference lines
  const floorY = toY(floorAmount);
  ctx.beginPath();
  ctx.setLineDash([4, 4]);
  ctx.moveTo(pad.left, floorY);
  ctx.lineTo(W - pad.right, floorY);
  ctx.strokeStyle = 'rgba(255, 123, 0, 0.3)';
  ctx.lineWidth = 1;
  ctx.stroke();
  ctx.setLineDash([]);

  const maxY = toY(maxAmount);
  ctx.beginPath();
  ctx.setLineDash([6, 6]);
  ctx.moveTo(pad.left, maxY);
  ctx.lineTo(W - pad.right, maxY);
  ctx.strokeStyle = 'rgba(255, 251, 245, 0.12)';
  ctx.lineWidth = 1;
  ctx.stroke();
  ctx.setLineDash([]);

  ctx.fillStyle = 'rgba(255,251,245,0.25)';
  ctx.font = 'bold 10px "JetBrains Mono", monospace';
  ctx.textAlign = 'left';
  ctx.fillText('FLOOR', pad.left + 6, floorY - 8);
  ctx.fillText('MAX', pad.left + 6, maxY - 8);

  // Overtime shading (drawn behind reign lines)
  let originalX = null;
  if (originalDeadline > startTime && originalDeadline < deadline) {
    originalX = toX(originalDeadline);
    ctx.fillStyle = 'rgba(255, 123, 0, 0.05)';
    ctx.fillRect(originalX, pad.top, (W - pad.right) - originalX, plotH);
  }

  // Ghost curve: shows prize growth before the first shot
  let liveReigns = reigns || [];
  let isGhost = false;
  if (liveReigns.length === 0 && state.started && !state.ended && startTime > 0) {
    const nowTs = Math.min(nowSeconds(), deadline);
    if (nowTs > startTime) {
      liveReigns = [{ start: startTime, end: nowTs, player: null }];
      isGhost = true;
    }
  }

  if (liveReigns.length === 0) return;

  // Gradient fill under each reign segment
  const gradient = ctx.createLinearGradient(0, pad.top, 0, pad.top + plotH);
  gradient.addColorStop(0, 'rgba(255, 123, 0, 0.60)');
  gradient.addColorStop(1, 'rgba(255, 123, 0, 0.12)');

  liveReigns.forEach((reign) => {
    const startX = toX(reign.start);
    const endX = toX(reign.end);
    ctx.beginPath();
    ctx.moveTo(startX, floorY);
    const steps = 40;
    for (let i = 0; i <= steps; i++) {
      const ts = reign.start + ((reign.end - reign.start) * i) / steps;
      const elapsed = clampedElapsed(ts, reign.start);
      const val = curveValue(elapsed, floorAmount, maxAmount, gameDuration, exponent);
      ctx.lineTo(toX(ts), toY(val));
    }
    ctx.lineTo(endX, floorY);
    ctx.closePath();
    ctx.fillStyle = gradient;
    ctx.fill();
  });

  // Draw each reign line
  liveReigns.forEach((reign, idx) => {
    const startX = toX(reign.start);
    const endX = toX(reign.end);

    ctx.beginPath();
    ctx.strokeStyle = isGhost ? 'rgba(255, 123, 0, 0.55)' : '#ff7b00';
    ctx.lineWidth = 2.5;
    if (isGhost) ctx.setLineDash([6, 4]);
    const steps = 60;
    for (let i = 0; i <= steps; i++) {
      const ts = reign.start + ((reign.end - reign.start) * i) / steps;
      const elapsed = clampedElapsed(ts, reign.start);
      const val = curveValue(elapsed, floorAmount, maxAmount, gameDuration, exponent);
      const x = toX(ts);
      const y = toY(val);
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    }
    ctx.stroke();
    ctx.setLineDash([]);

    // End marker + drop line for non-current reigns
    if (idx < liveReigns.length - 1) {
      const endY = toY(curveValue(clampedElapsed(reign.end, reign.start), floorAmount, maxAmount, gameDuration, exponent));
      ctx.beginPath();
      ctx.arc(endX, endY, 4, 0, Math.PI * 2);
      ctx.fillStyle = '#08050a';
      ctx.fill();
      ctx.lineWidth = 2;
      ctx.strokeStyle = '#ff7b00';
      ctx.stroke();

      ctx.beginPath();
      ctx.setLineDash([3, 3]);
      ctx.moveTo(endX, endY);
      ctx.lineTo(endX, floorY);
      ctx.strokeStyle = 'rgba(255, 255, 255, 0.4)';
      ctx.lineWidth = 1;
      ctx.stroke();
      ctx.setLineDash([]);
    }
  });

  // Current king star
  const lastReign = liveReigns[liveReigns.length - 1];
  const now = ended ? deadline : Math.min(nowSeconds(), deadline);
  const markerTs = Math.min(Math.max(now, lastReign.start), deadline);
  const markerElapsed = clampedElapsed(markerTs, lastReign.start);
  const markerVal = ended && paidAmount > 0
    ? paidAmount
    : curveValue(markerElapsed, floorAmount, maxAmount, gameDuration, exponent);
  const markerX = toX(markerTs);
  const markerY = toY(markerVal);

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
  drawStar(markerX, markerY, 10, 5, 5);

  // Vertical guide line
  ctx.beginPath();
  ctx.setLineDash([5, 5]);
  ctx.moveTo(markerX, markerY + 10);
  ctx.lineTo(markerX, floorY);
  ctx.strokeStyle = 'rgba(255, 123, 0, 0.4)';
  ctx.lineWidth = 1;
  ctx.stroke();
  ctx.setLineDash([]);

  // Original deadline marker + label (drawn on top)
  if (originalX != null) {
    ctx.beginPath();
    ctx.setLineDash([3, 3]);
    ctx.moveTo(originalX, pad.top);
    ctx.lineTo(originalX, pad.top + plotH);
    ctx.strokeStyle = 'rgba(255, 123, 0, 0.55)';
    ctx.lineWidth = 1;
    ctx.stroke();
    ctx.setLineDash([]);

    ctx.fillStyle = 'rgba(255, 123, 0, 0.65)';
    ctx.font = 'bold 9px "JetBrains Mono", monospace';
    ctx.textAlign = 'left';
    ctx.textBaseline = 'bottom';
    ctx.fillText('OVERTIME →', originalX + 4, pad.top + plotH - 4);
  }
}

// ── Data Fetching ─────────────────────────────────────────
async function refresh() {
  if (!contract) return;

  const [
    startTime,
    deadline,
    gameDuration,
    maxAmount,
    floorAmount,
    remainingAmount,
    originalDeadline,
    maxDeadline,
    curveExponent,
    maxShots,
    king,
    kingSince,
    shotSequence,
    kingPrize,
    paidAmount,
    funded,
    started,
    ended,
    winner,
    tokenAddr,
  ] = await Promise.all([
    call(contract, 'start_time'),
    call(contract, 'deadline'),
    call(contract, 'game_duration'),
    call(contract, 'max_amount'),
    call(contract, 'floor_amount'),
    call(contract, 'remaining_amount'),
    call(contract, 'original_deadline'),
    call(contract, 'max_deadline'),
    call(contract, 'curve_exponent'),
    call(contract, 'max_shots'),
    call(contract, 'king'),
    call(contract, 'king_since'),
    call(contract, 'shot_sequence'),
    call(contract, 'king_prize'),
    call(contract, 'paid_amount'),
    call(contract, 'funded'),
    call(contract, 'started'),
    call(contract, 'ended'),
    call(contract, 'winner'),
    call(contract, 'token'),
  ]);

  if (tokenAddr && tokenAddr !== EMPTY_ADDRESS && (!tokenContract || tokenContract.target !== tokenAddr)) {
    tokenContract = new ethers.Contract(tokenAddr, ERC20_ABI, provider);
  }
  let decimals = 18;
  let symbol = '';
  if (tokenContract) {
    try { decimals = Number(await tokenContract.decimals()); } catch {}
    try { symbol = await tokenContract.symbol(); } catch {}
  }

  state.tokenDecimals = decimals;
  state.tokenSymbol = symbol;

  const prizePoolRaw = maxAmount || 0n;
  const floorRaw = floorAmount || 0n;
  const paidRaw = paidAmount || 0n;

  state.prizePoolRaw = prizePoolRaw;
  state.remainingAmountRaw = remainingAmount || 0n;
  state.maxAmountRaw = prizePoolRaw;
  state.floorRaw = floorRaw;
  state.paidAmountRaw = paidRaw;
  state.gameDuration = Number(gameDuration || 0) || (state.originalDeadline > state.startTime ? state.originalDeadline - state.startTime : 0);
  state.curveExponent = Number(curveExponent || 1);
  state.startTime = Number(startTime || 0);
  state.deadline = Number(deadline || 0);
  state.originalDeadline = Number(originalDeadline || 0);
  state.maxDeadline = Number(maxDeadline || 0);
  state.started = !!started;
  state.funded = !!funded;
  state.ended = !!ended;
  state.currentHolder = king && king !== EMPTY_ADDRESS ? king.toLowerCase() : null;
  state.kingSince = kingSince ? Number(kingSince) : 0;
  state.winner = winner && winner !== EMPTY_ADDRESS ? winner.toLowerCase() : null;
  state.kingPrizeRaw = kingPrize != null ? kingPrize : 0n;
  state.shotSequence = shotSequence != null ? Number(shotSequence) : 0;

  const now = nowSeconds();
  const timeLeft = Math.max(0, state.deadline - now);
  const prizePoolHuman = Number(prizePoolRaw) / Math.pow(10, decimals);
  const maxAmountHuman = Number(state.maxAmountRaw) / Math.pow(10, decimals);
  const floorHuman = Number(floorRaw) / Math.pow(10, decimals);
  const paidHuman = Number(paidRaw) / Math.pow(10, decimals);

  // Status
  let statusText = '-';
  if (state.ended) statusText = 'Ended';
  else if (!state.funded) statusText = 'Not funded';
  else if (!state.started) statusText = 'Funded · not started';
  else if (timeLeft === 0) statusText = 'Expired · awaiting finalization';
  else statusText = 'Live';

  const statusEl = $('#status');
  statusEl.textContent = statusText;
  statusEl.classList.toggle('live', statusText === 'Live');

  // Stats
  $('#pool').textContent = state.prizePoolRaw != null ? formatToken(state.prizePoolRaw) : '-';
  $('#floor').textContent = state.floorRaw != null ? formatToken(state.floorRaw) : '-';
  $('#max-shots').textContent = maxShots != null ? Number(maxShots).toString() : '-';
  $('#timer').textContent = state.ended ? 'Ended' : formatDuration(timeLeft);
  if (state.ended) {
    stopCountdown();
  } else {
    startCountdown();
  }
  $('#game-start').textContent = state.startTime ? fmtTime(state.startTime) : '-';

  // Current / winner prize
  let currentPrizeHuman = 0;
  if (state.ended && state.paidAmountRaw && state.paidAmountRaw > 0n) {
    currentPrizeHuman = paidHuman;
  } else if (state.kingPrizeRaw != null && state.kingPrizeRaw > 0n) {
    currentPrizeHuman = Number(state.kingPrizeRaw) / Math.pow(10, decimals);
  } else if (state.currentHolder && state.kingSince && state.started && !state.ended) {
    const effectiveUntil = Math.min(now, state.originalDeadline || state.deadline);
    const elapsed = Math.max(0, effectiveUntil - state.kingSince);
    currentPrizeHuman = curveValue(elapsed, floorHuman, maxAmountHuman, state.gameDuration, state.curveExponent);
  }
  const prizeText = currentPrizeHuman > 0
    ? `${currentPrizeHuman.toLocaleString(undefined, { maximumFractionDigits: 4 })} ${symbol}`.trim()
    : '-';
  $('#prize').textContent = prizeText;
  $('#prize-label').textContent = state.ended ? 'Winner Prize' : 'Current Reign Prize';

  const winnerPrizeValue = $('#winner-prize-value');
  if (winnerPrizeValue) {
    winnerPrizeValue.textContent = state.ended && state.paidAmountRaw && state.paidAmountRaw > 0n ? prizeText : '-';
  }

  // King / winner card
  const displayHolder = state.ended && state.winner ? state.winner : state.currentHolder;
  const heading = state.ended ? (state.winner ? 'Winner' : 'No Winner') : 'Current King';
  $('#king-heading').textContent = heading;
  $('#king').textContent = addrShort(displayHolder);
  $('.king-section').classList.toggle('ended', state.ended);
  $('#king-since-label').textContent = state.ended ? 'Won At' : 'Captured';
  $('#king-since').textContent = state.kingSince ? fmtTime(state.kingSince) : '-';

  let heldText = '-';
  if (state.started) {
    const heldStart = state.kingSince || state.startTime;
    const heldEnd = state.ended ? state.deadline : now;
    const heldSeconds = Math.max(0, heldEnd - heldStart);
    if (heldSeconds > 0) heldText = formatDuration(heldSeconds);
  }
  $('#king-held-label').textContent = state.ended ? 'Held For' : 'Time Held';
  $('#king-held').textContent = heldText;

  // Build reigns from Shot events
  if (startBlock == null) {
    try {
      const currentBlock = await provider.getBlockNumber();
      startBlock = Math.max(0, currentBlock - 100000);
    } catch {
      startBlock = 0;
    }
  }
  const shots = await call(contract, 'queryFilter', 'Shot', startBlock);
  const reigns = [];
  const reignEnd = state.ended ? state.deadline : Math.min(now, state.deadline);
  if (shots && shots.length > 0) {
    shots.sort((a, b) => Number(a.args.sequence) - Number(b.args.sequence));
    let lastStart = state.startTime;
    for (const shot of shots) {
      const capturedAt = Number(shot.args.captured_at);
      reigns.push({ start: lastStart, end: capturedAt, player: shot.args.player.toLowerCase() });
      lastStart = capturedAt;
    }
    if (state.currentHolder) {
      reigns.push({ start: lastStart, end: reignEnd, player: state.currentHolder });
    }
  } else if (state.currentHolder) {
    reigns.push({ start: state.kingSince, end: reignEnd, player: state.currentHolder });
  }

  drawCurve(
    state.startTime,
    state.deadline,
    state.originalDeadline,
    floorHuman,
    maxAmountHuman,
    currentPrizeHuman,
    state.curveExponent,
    reigns,
    paidHuman,
    state.ended
  );

  renderHistory(shots);

  const hadNewShot = lastShotSequence > 0 && state.shotSequence > lastShotSequence;
  if (hadNewShot) {
    triggerCrownAnimation();
  }
  lastShotSequence = state.shotSequence;
  adjustRefreshInterval(hadNewShot);
}

async function call(contractObj, fn, ...args) {
  try {
    return await contractObj[fn](...args);
  } catch {
    return null;
  }
}

function prizeAtElapsed(elapsed) {
  const floor = state.floorRaw || 0n;
  const max = state.maxAmountRaw || 0n;
  const duration = state.gameDuration || 0;
  const exponent = state.curveExponent || 1;
  if (!duration || elapsed <= 0) return floor;
  const p = Math.min(elapsed / duration, 1);
  let factor = p;
  if (exponent === 2) factor = p * p;
  else if (exponent === 3) factor = p * p * p;
  const raw = Number(floor) + (Number(max) - Number(floor)) * factor;
  return BigInt(Math.round(raw));
}

function renderHistory(shots) {
  const tbody = $('#history-body');
  if (!tbody) return;

  const rows = [];

  const capTs = state.originalDeadline > state.startTime ? state.originalDeadline : state.deadline;

  const isOt = (ts) => state.originalDeadline > 0 && ts > state.originalDeadline;

  // Completed reigns from Shot events
  if (shots && shots.length > 0) {
    const sorted = shots.slice().sort((a, b) => Number(a.args.sequence) - Number(b.args.sequence));
    for (let i = sorted.length - 1; i >= Math.max(0, sorted.length - 10); i--) {
      const s = sorted[i];
      const capturedAt = Number(s.args.captured_at);
      const reignStart = i === 0 ? state.startTime : Number(sorted[i - 1].args.captured_at);
      const elapsed = Math.max(0, Math.min(capturedAt, capTs) - reignStart);
      const prizeRaw = elapsed > 0 ? prizeAtElapsed(elapsed) : (state.floorRaw || 0n);
      rows.push({ time: fmtTime(capturedAt), player: s.args.player.toLowerCase(), prizeRaw, ot: isOt(capturedAt) });
    }
  }

  if (rows.length === 0) {
    tbody.innerHTML = '<tr class="history-empty"><td colspan="3">No captures yet.</td></tr>';
    return;
  }

  tbody.innerHTML = rows.slice(0, 10).map((r) => `
    <tr>
      <td>${r.time}${r.ot ? ' <span class="ot-badge">OT</span>' : ''}</td>
      <td>${addrShort(r.player)}</td>
      <td class="history-prize">${formatToken(r.prizeRaw)}</td>
    </tr>
  `).join('');
}

// ── Idle Mode ────────────────────────────────────────────
function showIdleState(reason = 'No active game is configured right now. Check back soon.') {
  document.body.classList.add('idle');
  const h2 = $('.hero-text h2');
  const p = $('.hero-text p');
  if (h2) h2.textContent = 'No Active Game';
  if (p) p.textContent = reason;
  const status = $('#status');
  if (status) {
    status.textContent = 'Idle';
    status.classList.remove('live');
  }
}

// ── Mock Mode ─────────────────────────────────────────────
function useMockData() {
  useMock = true;

  const now = nowSeconds();
  state.tokenSymbol = 'ETH';
  state.tokenDecimals = 18;
  state.floorRaw = 5000000000000000000n;
  state.maxAmountRaw = 25000000000000000000n;
  state.prizePoolRaw = state.maxAmountRaw;
  state.paidAmountRaw = 0n;
  state.curveExponent = 2;
  state.started = true;
  state.funded = true;
  state.ended = false;
  state.winner = null;
  state.shotSequence = 8;

  const mockStart = now - 3600 * 6;
  const mockDeadline = now + 3600 * 18;
  state.startTime = mockStart;
  state.deadline = mockDeadline;
  state.gameDuration = mockDeadline - mockStart;
  state.kingSince = mockStart + Math.floor(0.8 * state.gameDuration);
  state.currentHolder = '0xAbCDEF1234567890abcdef1234567890ABCDEF12'.toLowerCase();

  $('#status').textContent = 'Live';
  $('#status').classList.add('live');
  $('#pool').textContent = '25 ETH';
  $('#floor').textContent = '5 ETH';
  $('#max-shots').textContent = '5';
  $('#timer').textContent = formatDuration(state.deadline - now);
  $('#game-start').textContent = fmtTime(mockStart);
  $('#prize-label').textContent = 'Current Reign Prize';
  $('#prize').textContent = '12.45 ETH';
  $('#king-heading').textContent = 'Current King';
  $('#king').textContent = addrShort(state.currentHolder);
  $('#king-since-label').textContent = 'Captured';
  $('#king-since').textContent = fmtTime(state.kingSince);
  $('#king-held-label').textContent = 'Time Held';
  $('#king-held').textContent = formatDuration(now - state.kingSince);

  const mockShots = [];
  const mockReigns = [];
  let lastStart = mockStart;
  for (let i = 0; i < 8; i++) {
    const capturedAt = mockStart + (i + 1) * 3600 * 0.7;
    const addr = `0x${String(i + 1).repeat(40)}`;
    mockShots.push({ args: { sequence: i + 1, player: addr, captured_at: capturedAt } });
    mockReigns.push({ start: lastStart, end: capturedAt, player: addr });
    lastStart = capturedAt;
  }
  mockReigns.push({ start: lastStart, end: now, player: state.currentHolder });

  drawCurve(mockStart, mockDeadline, mockDeadline, 5, 25, 12.45, 2, mockReigns, 0, false);

  renderHistory(mockShots);
}

function triggerCrownAnimation() {
  const wrap = $('#crownWrap');
  const activeCrown = $('#activeCrown');
  const newCrown = $('#newCrown');
  if (!wrap || !activeCrown || !newCrown || wrap.classList.contains('animating')) return;

  newCrown.style.opacity = '0';
  newCrown.style.transform = 'translateY(8px) scale(0.9)';
  wrap.querySelectorAll('.fragment').forEach((f) => {
    f.style.opacity = '0';
    f.style.transform = 'translate(0,0) rotate(0deg) scale(1)';
  });
  activeCrown.style.opacity = '1';
  activeCrown.style.transform = 'none';

  wrap.classList.add('animating');
  setTimeout(() => {
    wrap.classList.remove('animating');
    activeCrown.style.opacity = '1';
    activeCrown.style.transform = 'none';
    newCrown.style.opacity = '0';
    newCrown.style.transform = 'translateY(8px) scale(0.9)';
  }, 1200);
}

// ── Init ──────────────────────────────────────────────────
async function init() {
  initBackground();

  let config;
  try {
    const { config: cfg, abi } = await loadConfig();
    config = cfg;
    const rpcUrl = new URL(config.rpcProxyUrl, window.location.href).toString();
    provider = new ethers.JsonRpcProvider(rpcUrl, undefined, {
      batchMaxCount: 50,
      batchStallTime: 10,
    });
    contract = new ethers.Contract(config.contractAddress, abi, provider);

    // Verify connection
    await contract.start_time();

    // Set Basescan link
    const link = $('#basescan-link');
    if (link && config.contractAddress) {
      const base = config.chainId === 84532 ? 'https://sepolia.basescan.org' : 'https://basescan.org';
      link.href = `${base}/address/${config.contractAddress}`;
    }
  } catch (err) {
    console.warn('Live contract unavailable:', err.message);
    showIdleState();
    return;
  }

  startRefresh();
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) {
      stopRefresh();
    } else {
      startRefresh();
    }
  });
}

function startRefresh() {
  if (refreshTimer) return;
  refresh();
  refreshTimer = setInterval(refresh, currentInterval);
}

function stopRefresh() {
  if (refreshTimer) {
    clearInterval(refreshTimer);
    refreshTimer = null;
  }
}

function adjustRefreshInterval(hadNewShot = false) {
  if (state.ended) {
    stopRefresh();
    stopCountdown();
    return;
  }
  const now = nowSeconds();
  const timeLeft = Math.max(0, state.deadline - now);
  let nextInterval = BASE_INTERVAL;
  if (timeLeft > 0 && timeLeft <= 60) {
    nextInterval = ACTIVE_INTERVAL;
  } else if (!state.started) {
    nextInterval = IDLE_INTERVAL;
  } else if (hadNewShot) {
    nextInterval = ACTIVE_INTERVAL;
  }
  if (nextInterval !== currentInterval) {
    currentInterval = nextInterval;
    if (refreshTimer) {
      clearInterval(refreshTimer);
      refreshTimer = setInterval(refresh, currentInterval);
    }
  }
}

function startCountdown() {
  stopCountdown();
  countdownTimer = setInterval(() => {
    if (state.ended || !state.deadline) {
      stopCountdown();
      return;
    }
    const left = Math.max(0, state.deadline - nowSeconds());
    const timerEl = $('#timer');
    if (timerEl) timerEl.textContent = formatDuration(left);
    if (left === 0) stopCountdown();
  }, 1000);
}

function stopCountdown() {
  if (countdownTimer) {
    clearInterval(countdownTimer);
    countdownTimer = null;
  }
}

document.addEventListener('DOMContentLoaded', init);
