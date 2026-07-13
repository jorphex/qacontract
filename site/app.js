// King of the Hill v5.2 read-only contract viewer.

const ERC20_ABI = [
  'function decimals() view returns (uint8)',
  'function symbol() view returns (string)',
];

const EMPTY_ADDRESS = `0x${'0'.repeat(40)}`;
const EVENT_LOOKBACK_BLOCKS = 200_000;
const REFRESH_MS = 3_000;
const URGENT_REFRESH_MS = 1_000;
const IDLE_REFRESH_MS = 10_000;
const SETTLED_REFRESH_MS = 30_000;

let provider = null;
let contract = null;
let tokenContract = null;
let tokenMetadata = null;
let config = null;
let explorerBase = 'https://basescan.org';
let viewState = null;
let cachedShots = [];
let cachedShotSequence = -1;
let eventStartBlock = null;
let refreshTimer = null;
let clockTimer = null;
let refreshing = false;

const $ = (selector) => document.querySelector(selector);

function setText(selector, value) {
  const element = $(selector);
  if (element) element.textContent = value;
}

function isAddress(value) {
  return typeof value === 'string' && value.toLowerCase() !== EMPTY_ADDRESS;
}

function shortHex(value, head = 6, tail = 4) {
  if (!value) return '-';
  return `${value.slice(0, head)}...${value.slice(-tail)}`;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}

function formatToken(raw, decimals = 18, symbol = '') {
  if (raw === null || raw === undefined) return '-';
  const numeric = Number(ethers.formatUnits(raw, decimals));
  const maximumFractionDigits = numeric >= 1 ? 2 : 6;
  const amount = numeric.toLocaleString(undefined, { maximumFractionDigits });
  return `${amount}${symbol ? ` ${symbol}` : ''}`;
}

function formatCountdown(seconds) {
  const safe = Math.max(0, Math.floor(seconds));
  const days = Math.floor(safe / 86_400);
  const hours = Math.floor((safe % 86_400) / 3_600);
  const minutes = Math.floor((safe % 3_600) / 60);
  const secs = safe % 60;
  const clock = [hours, minutes, secs].map((part) => String(part).padStart(2, '0')).join(':');
  return days ? `${days}d ${clock}` : clock;
}

function formatDuration(seconds) {
  const safe = Math.max(0, Math.floor(seconds));
  const days = Math.floor(safe / 86_400);
  const hours = Math.floor((safe % 86_400) / 3_600);
  const minutes = Math.floor((safe % 3_600) / 60);
  const secs = safe % 60;
  const parts = [];
  if (days) parts.push(`${days}d`);
  if (hours) parts.push(`${hours}h`);
  if (minutes) parts.push(`${minutes}m`);
  if (secs || parts.length === 0) parts.push(`${secs}s`);
  return parts.join(' ');
}

function formatDateTime(timestamp) {
  if (!timestamp) return '-';
  return new Date(timestamp * 1_000).toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}

function formatTimelineTime(timestamp) {
  if (!timestamp) return '-';
  return new Date(timestamp * 1_000).toLocaleTimeString(undefined, {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}

function chainNow() {
  if (!viewState?.blockTimestamp) return Math.floor(Date.now() / 1_000);
  const elapsed = Math.max(0, Math.floor((Date.now() - viewState.observedAt) / 1_000));
  return viewState.blockTimestamp + elapsed;
}

function prizeForHold(holdSeconds, state = viewState) {
  const duration = BigInt(Math.max(0, state?.gameDuration || 0));
  const floor = state?.floorAmount ?? 0n;
  const max = state?.maxAmount ?? 0n;
  if (duration === 0n) return 0n;
  if (floor === max || BigInt(Math.max(0, holdSeconds)) >= duration) return max;

  const progress = BigInt(Math.max(0, holdSeconds)) * 10_000n / duration;
  let curve = progress;
  if (state.curveExponent >= 2) curve = progress * progress / 10_000n;
  if (state.curveExponent >= 3) curve = curve * progress / 10_000n;
  return floor + (max - floor) * curve / 10_000n;
}

function explorerForChain(chainId) {
  if (chainId === 84532) return 'https://sepolia.basescan.org';
  if (chainId === 11155111) return 'https://sepolia.etherscan.io';
  return 'https://basescan.org';
}

function networkName(chainId) {
  if (chainId === 84532) return 'BASE SEPOLIA';
  if (chainId === 11155111) return 'SEPOLIA';
  if (chainId === 8453) return 'BASE MAINNET';
  return `CHAIN ${chainId}`;
}

function contractUrl(address = config?.contractAddress) {
  return address ? `${explorerBase}/address/${address}` : explorerBase;
}

function txUrl(hash) {
  return `${explorerBase}/tx/${hash}`;
}

function addressUrl(address) {
  return `${explorerBase}/address/${address}`;
}

function setContractLinks(enabled) {
  const navLink = $('#contract-link-nav');
  const actionLink = $('#contract-link');
  const url = enabled ? contractUrl() : explorerBase;
  if (navLink) navLink.href = url;
  if (!actionLink) return;

  actionLink.href = url;
  actionLink.classList.toggle('disabled', !enabled);
  actionLink.setAttribute('aria-disabled', enabled ? 'false' : 'true');
  actionLink.textContent = enabled ? 'Open verified contract ->' : 'Available when a game is configured';
}

function setKicker(text, tone = 'inactive') {
  const kicker = $('#state-kicker');
  if (!kicker) return;
  kicker.classList.remove('inactive', 'warning');
  if (tone) kicker.classList.add(tone);
  setText('#state-kicker-text', text);
}

function setHero({ kicker, tone, heading, holder, holderNeutral = false, label, value, valueTimer = false, copy }) {
  setKicker(kicker, tone);
  setText('#state-heading', heading);
  setText('#holder', holder);
  $('#holder')?.classList.toggle('neutral', holderNeutral);
  setText('#status-label', label);
  setText('#status-value', value);
  $('#status-value')?.classList.toggle('timer', valueTimer);
  setText('#status-copy', copy);
}

function setMetrics(metrics = null) {
  const scoreline = $('#scoreline');
  if (!scoreline) return;
  scoreline.hidden = !metrics;
  if (!metrics) return;

  const slots = ['primary', 'two', 'three', 'four'];
  slots.forEach((slot, index) => {
    setText(`#metric-${slot}-label`, metrics[index].label);
    setText(`#metric-${slot}`, metrics[index].value);
  });
}

function renderEmptyTimeline(message) {
  const timeline = $('#timeline');
  if (!timeline) return;
  timeline.className = 'timeline empty';
  timeline.setAttribute('aria-label', message);
  timeline.innerHTML = `<p class="empty-track-copy">${escapeHtml(message)}</p>`;
  $('#timeline-key').hidden = true;
}

function timelinePosition(timestamp, start, end) {
  if (end <= start) return 0;
  return Math.max(0, Math.min(100, ((timestamp - start) / (end - start)) * 100));
}

function renderTimeline(state, shots, view) {
  if (!state.started || !state.startTime) {
    setText('#timeline-note', 'Confirmed shoot() transactions appear here after a game starts.');
    renderEmptyTimeline(view === 'cancelled' ? 'Game ended before it started' : 'No onchain activity to display');
    return;
  }

  const start = state.startTime;
  const end = Math.max(state.maxDeadline, state.deadline, state.originalDeadline, start + 1);
  const originalPosition = timelinePosition(state.originalDeadline, start, end);
  const deadlinePosition = timelinePosition(state.deadline, start, end);
  const markerTime = ['expired', 'finalized', 'finalized-empty'].includes(view)
    ? state.deadline
    : Math.min(state.blockTimestamp, state.deadline);
  const markerPosition = Math.min(98, timelinePosition(markerTime, start, end));

  const parts = ['<div class="timeline-rail"></div>'];
  if (state.maxDeadline > state.originalDeadline) {
    parts.push(`<div class="overtime-zone" style="left:${originalPosition}%"></div>`);
  }

  const sameDeadline = state.deadline === state.originalDeadline;
  const originalLabel = sameDeadline ? 'LIVE / ORIGINAL DEADLINE' : 'ORIGINAL DEADLINE';
  parts.push(`<div class="timeline-boundary${sameDeadline ? ' live' : ''}" style="left:${originalPosition}%"><span>${originalLabel}</span></div>`);
  if (!sameDeadline) {
    parts.push(`<div class="timeline-boundary live align-left" style="left:${deadlinePosition}%"><span>LIVE DEADLINE</span></div>`);
  }

  shots.forEach((shot, index) => {
    const capturedAt = Number(shot.args.captured_at);
    const position = timelinePosition(capturedAt, start, end);
    const latest = index === shots.length - 1 ? ' latest' : '';
    parts.push(`<i class="shot${latest}" style="left:${position}%" title="Shot ${Number(shot.args.sequence)} at ${escapeHtml(formatDateTime(capturedAt))}"></i>`);
  });

  const endedTimeline = ['expired', 'finalized', 'finalized-empty'].includes(view);
  parts.push(`<div class="playhead${endedTimeline ? ' end' : ''}" style="left:${markerPosition}%" data-label="${endedTimeline ? 'END' : 'NOW'}"></div>`);
  parts.push(`<span class="timeline-start">START / ${escapeHtml(formatTimelineTime(start))}</span>`);
  parts.push(`<span class="timeline-end">LATEST POSSIBLE END / ${escapeHtml(formatTimelineTime(end))}</span>`);

  const timeline = $('#timeline');
  timeline.className = 'timeline';
  timeline.setAttribute('aria-label', `Game timeline with ${shots.length} confirmed shots`);
  timeline.innerHTML = parts.join('');
  $('#timeline-key').hidden = false;

  const extensionCopy = state.deadline > state.originalDeadline
    ? `The live deadline has been extended. The latest possible end is ${formatDateTime(state.maxDeadline)}.`
    : `The live and original deadlines are ${formatDateTime(state.originalDeadline)}. Late shots may extend play.`;
  const shotCopy = shots.length === state.shotSequence
    ? `${shots.length} confirmed shot${shots.length === 1 ? '' : 's'}.`
    : `Showing ${shots.length} of ${state.shotSequence} confirmed shots.`;
  setText('#timeline-note', `${shotCopy} ${extensionCopy}`);
}

function renderHistory(state, shots) {
  const empty = $('#history-empty');
  const wrap = $('#ledger-wrap');
  const tbody = $('#history-body');
  const historyLink = $('#history-link');
  if (!empty || !wrap || !tbody) return;

  if (!shots.length) {
    empty.hidden = false;
    empty.textContent = state?.shotSequence > 0
      ? 'Capture events are temporarily unavailable. Use the verified contract on Basescan for the complete history.'
      : state?.started
        ? 'No captures yet. The hill is open, but no shoot() transaction has been confirmed.'
      : 'No captures yet. Confirmed transactions will be listed here when the hill opens.';
    wrap.hidden = true;
    if (historyLink) historyLink.hidden = true;
    tbody.replaceChildren();
    return;
  }

  const rows = shots.slice(-10).reverse().map((shot) => {
    const sequence = Number(shot.args.sequence);
    const index = shots.findIndex((candidate) => Number(candidate.args.sequence) === sequence);
    const capturedAt = Number(shot.args.captured_at);
    const previousCapture = index > 0 ? Number(shots[index - 1].args.captured_at) : null;
    const hold = previousCapture === null
      ? null
      : Math.max(0, Math.min(capturedAt, state.originalDeadline) - previousCapture);
    const visiblePrize = hold === null ? '-' : formatToken(prizeForHold(hold, state), state.tokenDecimals, state.tokenSymbol);
    const overtime = capturedAt > state.originalDeadline;
    const player = String(shot.args.player);
    const hash = shot.transactionHash || shot.log?.transactionHash || '';
    return `
      <tr>
        <td title="${escapeHtml(formatDateTime(capturedAt))}">${escapeHtml(formatTimelineTime(capturedAt))}${overtime ? ' <span class="ot">OT</span>' : ''}</td>
        <td><a href="${addressUrl(player)}" target="_blank" rel="noopener">${escapeHtml(shortHex(player))}</a></td>
        <td>${hash ? `<a href="${txUrl(hash)}" target="_blank" rel="noopener">${escapeHtml(shortHex(hash))}</a>` : '-'}</td>
        <td>${escapeHtml(visiblePrize)}</td>
      </tr>`;
  });

  tbody.innerHTML = rows.join('');
  empty.hidden = true;
  wrap.hidden = false;
  if (historyLink) historyLink.hidden = false;
}

function classifyState(state) {
  if (state.ended) return state.started ? (state.winner ? 'finalized' : 'finalized-empty') : 'cancelled';
  if (!state.started) return state.funded ? 'ready' : 'unfunded';
  const now = state.blockTimestamp;
  if (now > state.deadline) return 'expired';
  if (now > state.originalDeadline) return 'overtime';
  return state.shotSequence > 0 ? 'live-active' : 'live-open';
}

function metricsFor(state, view) {
  const token = (value) => formatToken(value, state.tokenDecimals, state.tokenSymbol);
  if (view === 'cancelled') {
    return [
      { label: 'Clawed back', value: token(state.clawedBackAmount) },
      { label: 'Prize pool', value: token(state.maxAmount) },
      { label: 'Remaining funds', value: token(state.remainingAmount) },
      { label: 'Total shots', value: String(state.shotSequence) },
    ];
  }
  if (['finalized', 'finalized-empty'].includes(view)) {
    const returned = state.clawedBackAmount > 0n;
    return [
      { label: view === 'finalized' ? 'Winner prize' : 'Prize paid', value: token(state.paidAmount) },
      { label: 'Prize pool', value: token(state.maxAmount) },
      { label: returned ? 'Clawed back' : 'Remaining funds', value: token(returned ? state.clawedBackAmount : state.remainingAmount) },
      { label: 'Total shots', value: String(state.shotSequence) },
    ];
  }
  if (view === 'expired') {
    return [
      { label: 'Last reign prize', value: state.king ? token(state.kingPrize) : '-' },
      { label: 'Prize pool', value: token(state.maxAmount) },
      { label: 'Remaining funds', value: token(state.remainingAmount) },
      { label: 'Total shots', value: String(state.shotSequence) },
    ];
  }
  if (view === 'ready' || view === 'unfunded') {
    return [
      { label: 'Contract funds', value: token(state.remainingAmount) },
      { label: 'Prize pool', value: token(state.maxAmount) },
      { label: 'Prize floor', value: token(state.floorAmount) },
      { label: 'Max shots', value: String(state.maxShots) },
    ];
  }
  return [
    { label: 'Current reign prize', value: state.king ? token(state.kingPrize) : '-' },
    { label: 'Prize pool', value: token(state.maxAmount) },
    { label: 'Prize floor', value: token(state.floorAmount) },
    { label: 'Max shots', value: String(state.maxShots) },
  ];
}

function renderContractState(state, shots = cachedShots) {
  viewState = state;
  const view = classifyState(state);
  document.body.dataset.view = view;
  setContractLinks(true);
  setMetrics(metricsFor(state, view));

  const lastHolder = state.king ? shortHex(state.king) : 'No captures yet';
  const token = (value) => formatToken(value, state.tokenDecimals, state.tokenSymbol);
  const timeLeft = Math.max(0, state.deadline - chainNow());

  if (view === 'unfunded') {
    setHero({
      kicker: 'CONTRACT ATTACHED / UNFUNDED', tone: 'warning', heading: 'A game contract is attached.',
      holder: shortHex(config.contractAddress), holderNeutral: false,
      label: 'Funding status', value: 'Not funded',
      copy: 'The contract exists, but the prize has not been funded and the game cannot start.',
    });
  } else if (view === 'ready') {
    setHero({
      kicker: 'FUNDED / NOT STARTED', tone: 'inactive', heading: 'The hill is ready.',
      holder: shortHex(config.contractAddress), holderNeutral: false,
      label: 'Game status', value: 'Ready',
      copy: 'The prize is funded. Play begins only after the creator calls start_game().',
    });
  } else if (view === 'live-open') {
    setHero({
      kicker: 'LIVE / NO SHOTS', tone: '', heading: 'The hill is open.',
      holder: 'No current holder', holderNeutral: true,
      label: 'Time remaining', value: formatCountdown(timeLeft), valueTimer: true,
      copy: 'No shot has been confirmed. The first shoot(answer) transaction will take the hill.',
    });
  } else if (view === 'live-active') {
    const extended = state.deadline > state.originalDeadline;
    setHero({
      kicker: 'LIVE / SHOTS CONFIRMED', tone: '', heading: 'The hill is occupied.',
      holder: lastHolder, holderNeutral: false,
      label: 'Time remaining', value: formatCountdown(timeLeft), valueTimer: true,
      copy: extended
        ? 'Extended by a late shot. Prize growth continues until the original deadline.'
        : 'No extension. Prize growth continues until the original deadline.',
    });
  } else if (view === 'overtime') {
    setHero({
      kicker: 'LIVE / OVERTIME', tone: '', heading: state.king ? 'The hill is occupied.' : 'The hill is open.',
      holder: lastHolder, holderNeutral: !state.king,
      label: 'Live deadline', value: formatCountdown(timeLeft), valueTimer: true,
      copy: 'Prize growth stopped at the original deadline. Shots remain open until the live deadline.',
    });
  } else if (view === 'expired') {
    setHero({
      kicker: 'GAME ENDED / AWAITING FINALIZE()', tone: 'warning', heading: 'The hill is closed.',
      holder: state.king ? `Last holder: ${shortHex(state.king)}` : 'No final holder', holderNeutral: !state.king,
      label: 'Settlement', value: 'Finalize',
      copy: 'Anyone may call finalize(). The contract alone selects and pays the winner.',
    });
    $('#contract-link').textContent = 'Open contract to finalize() ->';
  } else if (view === 'finalized') {
    setHero({
      kicker: 'FINALIZE() CALLED / PRIZE PAID', tone: 'inactive', heading: 'Winner settled.',
      holder: shortHex(state.winner), holderNeutral: false,
      label: 'Winner prize', value: token(state.paidAmount),
      copy: 'The contract transferred the prize during settlement.',
    });
  } else if (view === 'finalized-empty') {
    setHero({
      kicker: 'FINALIZE() CALLED / NO WINNER', tone: 'inactive', heading: 'No winning reign.',
      holder: 'No prize was paid', holderNeutral: true,
      label: 'Game status', value: 'Finalized',
      copy: 'finalize() completed without a qualifying correct holder.',
    });
  } else {
    setHero({
      kicker: 'CANCELLED', tone: 'inactive', heading: 'The game was cancelled.',
      holder: 'The hill never opened', holderNeutral: true,
      label: 'Game status', value: 'Ended',
      copy: 'The funded game ended before start_game() was called.',
    });
  }

  renderTimeline(state, shots, view);
  renderHistory(state, shots);
  renderFooter(state, view);
}

function renderNoGame() {
  viewState = null;
  document.body.dataset.view = 'empty';
  setContractLinks(false);
  setMetrics(null);
  setHero({
    kicker: 'NO LIVE GAME', tone: 'inactive', heading: 'The hill is quiet.',
    holder: 'No game contract configured', holderNeutral: false,
    label: 'Game status', value: 'None',
    copy: 'There is no active game attached to this viewer.',
  });
  setText('#timeline-note', 'Confirmed shoot() transactions appear here after a game starts.');
  renderEmptyTimeline('No onchain activity to display');
  renderHistory(null, []);
  setText('#footer-state', `${networkName(config?.chainId || 8453)} / READ-ONLY PUBLIC VIEW / NO LIVE GAME`);
}

function renderUnavailable(message) {
  viewState = null;
  document.body.dataset.view = 'unavailable';
  setContractLinks(Boolean(config?.contractAddress));
  setMetrics(null);
  setHero({
    kicker: 'DATA UNAVAILABLE', tone: 'warning', heading: 'The chain view is unavailable.',
    holder: config?.contractAddress ? shortHex(config.contractAddress) : 'No contract connection', holderNeutral: true,
    label: 'Connection', value: 'Retrying',
    copy: message || 'Public contract reads could not be loaded.',
  });
  setText('#timeline-note', 'Capture activity will return when the public RPC connection recovers.');
  renderEmptyTimeline('Unable to load onchain activity');
  renderHistory(null, []);
  setText('#footer-state', `${networkName(config?.chainId || 8453)} / READ-ONLY PUBLIC VIEW / DATA UNAVAILABLE`);
}

function renderFooter(state, view) {
  const network = networkName(config.chainId);
  const block = state.blockNumber ? `BLOCK ${state.blockNumber.toLocaleString()}` : 'LATEST BLOCK';
  const labels = {
    'live-open': 'LIVE / NO SHOTS',
    'live-active': 'LIVE / SHOTS CONFIRMED',
    expired: 'GAME ENDED / AWAITING FINALIZE()',
    finalized: 'FINALIZE() CALLED / WINNER PAID',
    'finalized-empty': 'FINALIZE() CALLED / NO WINNER',
  };
  setText('#network', network);
  setText('#footer-state', `${network} / READ-ONLY PUBLIC VIEW / ${block} / ${labels[view] || view.toUpperCase()}`);
}

async function loadConfigAndAbi() {
  const [configResponse, abiResponse] = await Promise.all([fetch('/api/config'), fetch('/abi.json')]);
  if (!configResponse.ok || !abiResponse.ok) throw new Error('Site configuration is unavailable.');
  return { config: await configResponse.json(), abi: await abiResponse.json() };
}

async function loadShots(sequence) {
  if (sequence === cachedShotSequence) return cachedShots;
  if (sequence === 0) {
    cachedShots = [];
    cachedShotSequence = 0;
    return cachedShots;
  }
  try {
    const shots = await contract.queryFilter(contract.filters.Shot(), eventStartBlock, 'latest');
    cachedShots = shots.sort((a, b) => Number(a.args.sequence) - Number(b.args.sequence));
    cachedShotSequence = sequence;
    if (cachedShots.length < sequence) {
      console.warn(`Only ${cachedShots.length} of ${sequence} Shot events were found in the configured block lookback.`);
    }
  } catch (error) {
    console.warn('Shot event query failed; retaining the last confirmed event set:', error.message);
  }
  return cachedShots;
}

async function readContractState() {
  const [
    latestBlock,
    startTime,
    deadline,
    originalDeadline,
    maxDeadline,
    gameDuration,
    maxAmount,
    floorAmount,
    maxShots,
    curveExponent,
    king,
    kingSince,
    shotSequence,
    kingPrize,
    funded,
    started,
    ended,
    winner,
    paidAmount,
    remainingAmount,
    clawedBackAmount,
    tokenAddress,
  ] = await Promise.all([
    provider.getBlock('latest'),
    contract.start_time(),
    contract.deadline(),
    contract.original_deadline(),
    contract.max_deadline(),
    contract.game_duration(),
    contract.max_amount(),
    contract.floor_amount(),
    contract.max_shots(),
    contract.curve_exponent(),
    contract.king(),
    contract.king_since(),
    contract.shot_sequence(),
    contract.king_prize(),
    contract.funded(),
    contract.started(),
    contract.ended(),
    contract.winner(),
    contract.paid_amount(),
    contract.remaining_amount(),
    contract.clawed_back_amount(),
    contract.token(),
  ]);

  if (!tokenContract || tokenContract.target.toLowerCase() !== tokenAddress.toLowerCase()) {
    tokenContract = new ethers.Contract(tokenAddress, ERC20_ABI, provider);
    tokenMetadata = null;
  }
  if (!tokenMetadata) {
    const [decimals, symbol] = await Promise.all([
      tokenContract.decimals().catch(() => 18),
      tokenContract.symbol().catch(() => ''),
    ]);
    tokenMetadata = { decimals: Number(decimals), symbol: String(symbol) };
  }

  const state = {
    blockNumber: Number(latestBlock.number),
    blockTimestamp: Number(latestBlock.timestamp),
    observedAt: Date.now(),
    startTime: Number(startTime),
    deadline: Number(deadline),
    originalDeadline: Number(originalDeadline),
    maxDeadline: Number(maxDeadline),
    gameDuration: Number(gameDuration),
    maxAmount,
    floorAmount,
    maxShots: Number(maxShots),
    curveExponent: Number(curveExponent),
    king: isAddress(king) ? king : null,
    kingSince: Number(kingSince),
    shotSequence: Number(shotSequence),
    kingPrize,
    funded: Boolean(funded),
    started: Boolean(started),
    ended: Boolean(ended),
    winner: isAddress(winner) ? winner : null,
    paidAmount,
    remainingAmount,
    clawedBackAmount,
    tokenAddress,
    tokenDecimals: tokenMetadata.decimals,
    tokenSymbol: tokenMetadata.symbol,
  };
  if (eventStartBlock === null) {
    eventStartBlock = Math.max(0, state.blockNumber - EVENT_LOOKBACK_BLOCKS);
  }
  const shots = await loadShots(state.shotSequence);
  return { state, shots };
}

function refreshDelay() {
  if (!viewState) return IDLE_REFRESH_MS;
  const view = classifyState(viewState);
  if (['finalized', 'finalized-empty', 'cancelled'].includes(view)) {
    return viewState.remainingAmount === 0n ? 0 : SETTLED_REFRESH_MS;
  }
  if (['ready', 'unfunded'].includes(view)) return IDLE_REFRESH_MS;
  if (view === 'expired') return REFRESH_MS;
  const remaining = Math.max(0, viewState.deadline - chainNow());
  return remaining <= 60 ? URGENT_REFRESH_MS : REFRESH_MS;
}

function scheduleRefresh(delay = refreshDelay()) {
  clearTimeout(refreshTimer);
  if (!delay) return;
  refreshTimer = setTimeout(refresh, delay);
}

async function refresh() {
  if (refreshing || !contract) return;
  refreshing = true;
  try {
    const { state, shots } = await readContractState();
    renderContractState(state, shots);
  } catch (error) {
    console.warn('Contract refresh failed:', error.message);
    if (!viewState) renderUnavailable('Public contract reads could not be loaded. The site will retry automatically.');
  } finally {
    refreshing = false;
    scheduleRefresh();
  }
}

function updateClock() {
  if (!viewState) return;
  const before = document.body.dataset.view;
  const after = classifyState(viewState);
  if (before !== after) {
    refresh();
    return;
  }
  if (after === 'live-open' || after === 'live-active' || after === 'overtime') {
    setText('#status-value', formatCountdown(viewState.deadline - chainNow()));
  }
}

function buildPreview(name) {
  const now = Math.floor(Date.now() / 1_000);
  const unit = 1_000_000n;
  const base = {
    blockNumber: 31_884_219,
    blockTimestamp: now,
    observedAt: Date.now(),
    startTime: now - 3_600,
    originalDeadline: now + 1_800,
    deadline: now + 1_800,
    maxDeadline: now + 2_100,
    gameDuration: 5_400,
    maxAmount: 500n * unit,
    floorAmount: 1n * unit,
    maxShots: 3,
    curveExponent: 2,
    king: '0x7A38db33b76379C9Cf7C54d273F477f4EabAC734',
    kingSince: now - 720,
    shotSequence: 5,
    kingPrize: 9_860_000n,
    funded: true,
    started: true,
    ended: false,
    winner: null,
    paidAmount: 0n,
    remainingAmount: 500n * unit,
    clawedBackAmount: 0n,
    tokenDecimals: 6,
    tokenSymbol: 'USDC',
  };

  const addresses = [
    '0x9b80d9E8122FCA5Ed409974812E07cBa0F7A1CdC',
    '0x6034391c241e7756b0361C9f172aBE05CAfE602D',
    '0x329958C18039e3CAeDd7d40B19e213B40C8f7971',
    '0x1E0B0b73736f946bFc1A3541A1ac2fc4Fc5fDB5c',
    base.king,
  ];
  const makeShots = (times) => times.map((timestamp, index) => ({
    args: { player: addresses[index % addresses.length], sequence: BigInt(index + 1), captured_at: BigInt(timestamp) },
    transactionHash: `0x${String(index + 1).padStart(64, '0')}`,
  }));

  if (name === 'unfunded') return { state: { ...base, startTime: 0, gameDuration: 0, funded: false, started: false, king: null, kingSince: 0, shotSequence: 0, kingPrize: 0n, remainingAmount: 0n }, shots: [] };
  if (name === 'ready') return { state: { ...base, startTime: 0, gameDuration: 0, started: false, king: null, kingSince: 0, shotSequence: 0, kingPrize: 0n }, shots: [] };
  if (name === 'live-open') return { state: { ...base, king: null, kingSince: 0, shotSequence: 0, kingPrize: 0n }, shots: [] };
  if (name === 'cancelled') return { state: { ...base, startTime: 0, gameDuration: 0, started: false, ended: true, king: null, kingSince: 0, shotSequence: 0, kingPrize: 0n, remainingAmount: 0n, clawedBackAmount: 500n * unit }, shots: [] };
  if (name === 'overtime') {
    const state = { ...base, startTime: now - 4_200, originalDeadline: now - 300, deadline: now + 120, maxDeadline: now + 300, gameDuration: 3_900, kingSince: now - 40, kingPrize: 1n * unit, shotSequence: 7 };
    return { state, shots: makeShots([now - 3_500, now - 2_500, now - 1_600, now - 800, now - 360, now - 180, now - 40]) };
  }
  if (name === 'expired') {
    const state = { ...base, startTime: now - 4_200, originalDeadline: now - 600, deadline: now - 60, maxDeadline: now - 300, gameDuration: 3_600, kingSince: now - 200, shotSequence: 6, kingPrize: 1n * unit };
    return { state, shots: makeShots([now - 3_500, now - 2_500, now - 1_600, now - 800, now - 500, now - 200]) };
  }
  if (name === 'finalized' || name === 'finalized-empty') {
    const winner = name === 'finalized' ? addresses[1] : null;
    const paid = name === 'finalized' ? 84_200_000n : 0n;
    const state = { ...base, startTime: now - 4_200, originalDeadline: now - 600, deadline: now - 300, maxDeadline: now - 300, gameDuration: 3_600, kingSince: now - 700, shotSequence: 6, kingPrize: 4_100_000n, ended: true, winner, paidAmount: paid, remainingAmount: 500n * unit - paid };
    return { state, shots: makeShots([now - 3_500, now - 2_500, now - 1_600, now - 1_000, now - 800, now - 700]) };
  }
  return { state: base, shots: makeShots([now - 3_200, now - 2_500, now - 1_800, now - 1_100, now - 720]) };
}

function localPreviewName() {
  const local = ['127.0.0.1', 'localhost'].includes(window.location.hostname);
  return local ? new URLSearchParams(window.location.search).get('preview') : null;
}

async function init() {
  const preview = localPreviewName();
  if (preview) {
    config = { contractAddress: '0x1111111111111111111111111111111111111111', chainId: 8453 };
    explorerBase = explorerForChain(config.chainId);
    setText('#network', networkName(config.chainId));
    if (preview === 'empty') renderNoGame();
    else {
      const fixture = buildPreview(preview);
      renderContractState(fixture.state, fixture.shots);
    }
    clockTimer = setInterval(updateClock, 1_000);
    return;
  }

  try {
    const loaded = await loadConfigAndAbi();
    config = loaded.config;
    explorerBase = explorerForChain(Number(config.chainId || 8453));
    config.chainId = Number(config.chainId || 8453);
    setText('#network', networkName(config.chainId));

    if (!config.contractAddress || config.contractAddress.toLowerCase() === EMPTY_ADDRESS) {
      renderNoGame();
      return;
    }
    if (!config.rpcProxyUrl) throw new Error('Public RPC proxy is not configured.');

    const rpcUrl = new URL(config.rpcProxyUrl, window.location.href).toString();
    provider = new ethers.JsonRpcProvider(rpcUrl, config.chainId, { batchMaxCount: 50, batchStallTime: 10 });
    contract = new ethers.Contract(config.contractAddress, loaded.abi, provider);
    setContractLinks(true);
    await refresh();
    clockTimer = setInterval(updateClock, 1_000);
  } catch (error) {
    console.warn('Site initialization failed:', error.message);
    if (config?.contractAddress && config.contractAddress.toLowerCase() !== EMPTY_ADDRESS) renderUnavailable(error.message);
    else renderNoGame();
  }
}

document.addEventListener('visibilitychange', () => {
  if (document.hidden) {
    clearTimeout(refreshTimer);
    clearInterval(clockTimer);
    refreshTimer = null;
    clockTimer = null;
  } else {
    if (contract) refresh();
    if (!clockTimer) clockTimer = setInterval(updateClock, 1_000);
  }
});

document.addEventListener('DOMContentLoaded', init);
