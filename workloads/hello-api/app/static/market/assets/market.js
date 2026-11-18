(() => {
  "use strict";

  const API = "/v1/market/kraken";
  const REFRESH_MS = 15000;
  const RANGE_LABELS = { "1h": "1 hour", "24h": "24 hours", "7d": "7 days" };
  const state = {
    pair: safeGet("kaviont.market.pair"),
    range: "24h",
    tickers: [],
    history: [],
    summary: null,
    worker: null,
    busy: false,
    autoRefresh: true,
    chartPoints: [],
    lastUpdated: null
  };

  const $ = (selector) => document.querySelector(selector);
  const safeGet = (key) => {
    try { return window.localStorage.getItem(key) || ""; } catch (_) { return ""; }
  };
  const safeSet = (key, value) => {
    try { window.localStorage.setItem(key, value); } catch (_) { /* Storage is optional. */ }
  };

  async function getJson(url) {
    const response = await fetch(url, {
      headers: { "Accept": "application/json" },
      cache: "no-store"
    });
    if (!response.ok) {
      let detail = "Request failed (" + response.status + ")";
      try {
        const payload = await response.json();
        detail = payload.detail || detail;
      } catch (_) { /* Keep the HTTP fallback. */ }
      throw new Error(detail);
    }
    return response.json();
  }

  function quoteCurrency(pair) {
    if (pair.endsWith("EUR")) return "EUR";
    if (pair.endsWith("GBP")) return "GBP";
    return "USD";
  }

  function displayPair(pair) {
    if (!pair) return "—";
    const known = { XBTUSD: "BTC / USD", XXBTZUSD: "BTC / USD", XBTZEUR: "BTC / EUR", ETHUSD: "ETH / USD" };
    if (known[pair]) return known[pair];
    const quote = ["USD", "EUR", "GBP"].find((suffix) => pair.endsWith(suffix));
    if (quote) return pair.slice(0, -quote.length) + " / " + quote;
    return pair;
  }

  function assetName(pair) {
    const base = displayPair(pair).split(" / ")[0];
    const names = { BTC: "Bitcoin", ETH: "Ethereum", SOL: "Solana", XRP: "XRP", ADA: "Cardano" };
    return names[base] || base;
  }

  function assetMark(pair) {
    const base = displayPair(pair).split(" / ")[0];
    const marks = { BTC: "₿", ETH: "Ξ", SOL: "◎", XRP: "✕", ADA: "₳" };
    return marks[base] || base.slice(0, 1) || "K";
  }

  function formatPrice(value, pair = state.pair) {
    if (value === null || value === undefined || !Number.isFinite(Number(value))) return "—";
    const number = Number(value);
    const decimals = number >= 100 ? 2 : number >= 1 ? 3 : 6;
    try {
      return new Intl.NumberFormat("en-US", {
        style: "currency",
        currency: quoteCurrency(pair),
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals
      }).format(number);
    } catch (_) {
      return number.toFixed(decimals);
    }
  }

  function formatCompact(value) {
    if (value === null || value === undefined || !Number.isFinite(Number(value))) return "—";
    return new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 2 }).format(Number(value));
  }

  function formatNumber(value, digits = 2) {
    if (value === null || value === undefined || !Number.isFinite(Number(value))) return "—";
    return new Intl.NumberFormat("en-US", { maximumFractionDigits: digits }).format(Number(value));
  }

  function formatDate(value, withSeconds = false) {
    if (!value) return "—";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "—";
    return new Intl.DateTimeFormat(undefined, {
      month: "short", day: "2-digit", hour: "2-digit", minute: "2-digit",
      ...(withSeconds ? { second: "2-digit" } : {})
    }).format(date);
  }

  function formatAge(seconds) {
    if (seconds === null || seconds === undefined || !Number.isFinite(Number(seconds))) return "—";
    const value = Math.max(0, Math.floor(Number(seconds)));
    if (value < 60) return value + "s ago";
    if (value < 3600) return Math.floor(value / 60) + "m ago";
    return Math.floor(value / 3600) + "h ago";
  }

  function setConnection(stateName, label) {
    $("#connectionPill").dataset.state = stateName;
    $("#connectionLabel").textContent = label;
  }

  function setNotice(message, isError = false) {
    $("#noticeText").textContent = message;
    $("#noticeBar").dataset.state = isError ? "error" : "normal";
  }

  function selectedTicker() {
    return state.tickers.find((item) => item.pair === state.pair) || null;
  }

  function setEmptyState(message) {
    $("#marketList").innerHTML = '<div class="empty-copy"></div>';
    $("#marketList .empty-copy").textContent = message;
    $("#trackedCount").textContent = "0";
    $("#lastPrice").textContent = "—";
    $("#changeBadge").textContent = "No snapshot";
    $("#changeBadge").className = "change-badge neutral";
    $("#high24").textContent = "—";
    $("#low24").textContent = "—";
    $("#volume24").textContent = "—";
    $("#bidAsk").textContent = "—";
    $("#periodChange").textContent = "—";
    $("#periodHigh").textContent = "—";
    $("#periodLow").textContent = "—";
    $("#sampleCount").textContent = "0";
    $("#priceChart").innerHTML = '<text x="500" y="150" text-anchor="middle" class="chart-placeholder">No historical market data available yet.</text>';
    $("#chartPoints").textContent = "0 data points";
  }

  function renderHeader(ticker) {
    const pair = state.pair;
    $("#instrumentName").innerHTML = "";
    const name = document.createElement("span");
    name.textContent = assetName(pair);
    const symbol = document.createElement("span");
    symbol.textContent = " / " + displayPair(pair).split(" / ")[0];
    $("#instrumentName").append(name, symbol);
    $("#coinMark").textContent = assetMark(pair);
    $("#pairCode").textContent = pair;
    $("#chartTitle").textContent = assetName(pair) + " / " + quoteCurrency(pair);
    $("#lastPrice").textContent = ticker ? formatPrice(ticker.last_price, pair) : "—";
    $("#chartLatest").textContent = ticker ? formatPrice(ticker.last_price, pair) : "—";
    const stale = !ticker || ticker.stale === true;
    $("#freshnessBadge").textContent = stale ? "DELAYED" : "FRESH";
    $("#freshnessBadge").dataset.state = stale ? "stale" : "fresh";
    $("#freshnessLabel").textContent = ticker ? "Snapshot " + formatAge(ticker.cache_age_seconds) : "Waiting for snapshot";
    $("#priceCaption").textContent = ticker ? "Last stored observation · " + formatDate(ticker.fetched_at, true) : "No stored snapshot";
    $("#high24").textContent = ticker ? formatPrice(ticker.high_24h, pair) : "—";
    $("#low24").textContent = ticker ? formatPrice(ticker.low_24h, pair) : "—";
    $("#volume24").textContent = ticker ? formatCompact(ticker.volume_24h) + " " + quoteCurrency(pair) : "—";
    $("#bidAsk").textContent = ticker ? formatPrice(ticker.bid, pair) + " / " + formatPrice(ticker.ask, pair) : "—";
    $("#lastSync").textContent = ticker ? formatDate(ticker.fetched_at, true) : "Waiting for data";
  }

  function renderSummary() {
    const summary = state.summary;
    const percent = summary && summary.price_change_percent;
    const absolute = summary && summary.price_change_absolute;
    const hasChange = percent !== null && percent !== undefined && Number.isFinite(Number(percent));
    const badge = $("#changeBadge");
    badge.className = "change-badge " + (!hasChange ? "neutral" : Number(percent) >= 0 ? "positive" : "negative");
    badge.textContent = hasChange ? (Number(percent) >= 0 ? "+" : "") + Number(percent).toFixed(2) + "%" : "No period data";
    $("#periodChange").textContent = hasChange ? (Number(percent) >= 0 ? "+" : "") + Number(percent).toFixed(2) + "%" : "—";
    $("#periodChange").style.color = !hasChange ? "var(--text)" : Number(percent) >= 0 ? "var(--green)" : "var(--red)";
    $("#periodCaption").textContent = hasChange ? (Number(absolute) >= 0 ? "+" : "") + formatPrice(absolute, state.pair) + " in " + RANGE_LABELS[state.range] : "No observations in this range";
    $("#periodHigh").textContent = summary && summary.high_price !== null ? formatPrice(summary.high_price, state.pair) : "—";
    $("#periodLow").textContent = summary && summary.low_price !== null ? formatPrice(summary.low_price, state.pair) : "—";
    $("#sampleCount").textContent = summary ? formatNumber(summary.sample_count, 0) : "—";
    $("#periodHighCaption").textContent = RANGE_LABELS[state.range] + " high";
    $("#periodLowCaption").textContent = RANGE_LABELS[state.range] + " low";
    $("#chartSubtitle").textContent = RANGE_LABELS[state.range] + " · historical snapshots stored by Kaviont";
    $("#chartWindow").textContent = summary && summary.window_start ? formatDate(summary.window_start) + " — " + formatDate(summary.window_end) : "—";
  }

  function renderWorker() {
    const worker = state.worker;
    if (!worker) {
      $("#workerBadge").textContent = "UNKNOWN";
      $("#workerBadge").dataset.state = "unknown";
      $("#pollInterval").textContent = "—";
      $("#lastSuccess").textContent = "—";
      $("#heartbeatAge").textContent = "—";
      $("#workerMessage").textContent = "Worker status is unavailable.";
      return;
    }
    const workerState = worker.worker_status || "unknown";
    $("#workerBadge").textContent = workerState.toUpperCase();
    $("#workerBadge").dataset.state = workerState;
    $("#pollInterval").textContent = formatNumber(worker.poll_interval_seconds, 0) + " sec";
    $("#lastSuccess").textContent = formatDate(worker.last_successful_update, true);
    $("#heartbeatAge").textContent = formatAge(worker.heartbeat_age_seconds);
    const message = worker.running
      ? "Market-data worker is running and persisting snapshots."
      : worker.last_error
        ? "Last provider result: " + worker.last_error
        : workerState === "not_started"
          ? "No successful worker run has been recorded yet."
          : "Worker is not currently reporting a healthy heartbeat.";
    $("#workerMessage").textContent = message;
  }

  function renderMarkets() {
    const list = $("#marketList");
    $("#trackedCount").textContent = String(state.tickers.length);
    if (!state.tickers.length) {
      list.innerHTML = '<div class="empty-copy">No market snapshots have been stored yet. Start the market-data worker to populate this list.</div>';
      return;
    }
    list.innerHTML = state.tickers.map((ticker) => {
      const active = ticker.pair === state.pair ? " active" : "";
      const label = displayPair(ticker.pair);
      const freshness = ticker.stale ? "DELAYED" : formatAge(ticker.cache_age_seconds);
      return `<button class="market-row${active}" type="button" data-pair="${escapeHtml(ticker.pair)}" aria-pressed="${ticker.pair === state.pair}">
        <span class="market-row-main"><strong>${escapeHtml(label)}</strong><small>${escapeHtml(ticker.pair)} · Kraken</small></span>
        <span class="market-row-price"><strong>${formatPrice(ticker.last_price, ticker.pair)}</strong><small>${escapeHtml(freshness)}</small></span>
      </button>`;
    }).join("");
  }

  function escapeHtml(value) {
    return String(value).replace(/[&<>"']/g, (character) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
    })[character]);
  }

  function renderChart() {
    const svg = $("#priceChart");
    const points = (state.history || []).filter((point) => Number.isFinite(Number(point.price)));
    state.chartPoints = [];
    if (!points.length) {
      svg.innerHTML = '<text x="500" y="150" text-anchor="middle" class="chart-placeholder">No observations in this selected time range.</text>';
      $("#chartPoints").textContent = "0 data points";
      return;
    }

    const width = 1000, height = 310;
    const margin = { left: 76, right: 24, top: 18, bottom: 38 };
    const plotWidth = width - margin.left - margin.right;
    const plotHeight = height - margin.top - margin.bottom;
    const prices = points.map((point) => Number(point.price));
    let min = Math.min(...prices), max = Math.max(...prices);
    if (min === max) {
      const pad = Math.max(Math.abs(min) * .002, .000001);
      min -= pad; max += pad;
    } else {
      const pad = (max - min) * .12;
      min -= pad; max += pad;
    }
    const xAt = (index) => margin.left + (points.length === 1 ? .5 : index / (points.length - 1)) * plotWidth;
    const yAt = (price) => margin.top + ((max - price) / (max - min)) * plotHeight;
    const coordinates = points.map((point, index) => ({
      x: xAt(index), y: yAt(Number(point.price)), price: Number(point.price), timestamp: point.timestamp
    }));
    state.chartPoints = coordinates;

    const line = coordinates.map((point, index) => (index ? "L" : "M") + point.x.toFixed(2) + "," + point.y.toFixed(2)).join(" ");
    const area = line + " L" + coordinates[coordinates.length - 1].x.toFixed(2) + "," + (margin.top + plotHeight) +
      " L" + coordinates[0].x.toFixed(2) + "," + (margin.top + plotHeight) + " Z";
    const grid = Array.from({ length: 5 }, (_, index) => {
      const y = margin.top + (plotHeight / 4) * index;
      const value = max - ((max - min) / 4) * index;
      return `<line class="chart-grid" x1="${margin.left}" y1="${y}" x2="${width - margin.right}" y2="${y}"></line>
        <text class="chart-axis" x="${margin.left - 12}" y="${y + 4}" text-anchor="end">${formatAxisPrice(value, state.pair)}</text>`;
    }).join("");
    const xIndexes = [...new Set([0, Math.floor((points.length - 1) / 2), points.length - 1])];
    const xLabels = xIndexes.map((index) => {
      const x = xAt(index);
      return `<text class="chart-axis" x="${x}" y="${height - 9}" text-anchor="${index === 0 ? "start" : index === points.length - 1 ? "end" : "middle"}">${formatChartDate(points[index].timestamp)}</text>`;
    }).join("");
    const first = coordinates[0], last = coordinates[coordinates.length - 1];
    svg.innerHTML = `
      <defs>
        <linearGradient id="chartFill" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stop-color="#67d6a3" stop-opacity=".22"></stop>
          <stop offset="100%" stop-color="#67d6a3" stop-opacity="0"></stop>
        </linearGradient>
      </defs>
      ${grid}
      <path class="chart-area" d="${area}"></path>
      <path class="chart-line" d="${line}"></path>
      <circle class="chart-point" cx="${first.x}" cy="${first.y}" r="3"></circle>
      <circle class="chart-point" cx="${last.x}" cy="${last.y}" r="4.5"></circle>
      <line id="chartCrosshair" class="crosshair" x1="${last.x}" y1="${margin.top}" x2="${last.x}" y2="${margin.top + plotHeight}" opacity="0"></line>
      <circle id="chartHoverPoint" class="chart-point" cx="${last.x}" cy="${last.y}" r="5" opacity="0"></circle>
      ${xLabels}
    `;
    $("#chartPoints").textContent = points.length + " data points" + (state.summary && state.summary.downsampled ? " · sampled" : "");
    $("#chartStage").dataset.plot = JSON.stringify({ width, height, margin, plotWidth, plotHeight });
  }

  function formatAxisPrice(value, pair) {
    const number = Number(value);
    const decimals = Math.abs(number) >= 100 ? 0 : 2;
    return new Intl.NumberFormat("en-US", { maximumFractionDigits: decimals }).format(number);
  }

  function formatChartDate(value) {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "";
    return new Intl.DateTimeFormat(undefined, { hour: "2-digit", minute: "2-digit", month: "short", day: "2-digit" }).format(date);
  }

  function updateHover(event) {
    if (!state.chartPoints.length) return;
    const stage = $("#chartStage");
    const svg = $("#priceChart");
    const rect = svg.getBoundingClientRect();
    if (!rect.width || !rect.height) return;
    const viewX = ((event.clientX - rect.left) / rect.width) * 1000;
    const point = state.chartPoints.reduce((best, candidate) =>
      Math.abs(candidate.x - viewX) < Math.abs(best.x - viewX) ? candidate : best
    , state.chartPoints[0]);
    const crosshair = $("#chartCrosshair");
    const marker = $("#chartHoverPoint");
    if (crosshair) {
      crosshair.setAttribute("x1", point.x);
      crosshair.setAttribute("x2", point.x);
      crosshair.setAttribute("opacity", "1");
    }
    if (marker) {
      marker.setAttribute("cx", point.x);
      marker.setAttribute("cy", point.y);
      marker.setAttribute("opacity", "1");
    }
    const tooltip = $("#chartTooltip");
    const stageRect = stage.getBoundingClientRect();
    const relativeX = event.clientX - stageRect.left;
    const relativeY = event.clientY - stageRect.top;
    tooltip.style.display = "block";
    tooltip.style.left = Math.max(70, Math.min(stageRect.width - 70, relativeX)) + "px";
    tooltip.style.top = Math.max(12, relativeY - 8) + "px";
    tooltip.textContent = formatPrice(point.price, state.pair) + " · " + formatDate(point.timestamp, true);
  }

  async function loadMarket() {
    if (state.busy) return;
    state.busy = true;
    $("#refreshButton").classList.add("is-loading");
    setConnection("loading", "Syncing");
    try {
      const [tickerPayload, worker] = await Promise.all([
        getJson(API + "/tickers"),
        getJson(API + "/status")
      ]);
      state.tickers = Array.isArray(tickerPayload.tickers) ? tickerPayload.tickers : [];
      state.worker = worker;
      if (!state.tickers.length) {
        state.pair = "";
        state.history = [];
        state.summary = null;
        renderMarkets();
        renderWorker();
        setEmptyState("No market data yet.");
        setConnection("online", "API connected");
        setNotice("The API is available, but the worker has not stored a market snapshot yet.");
        return;
      }
      if (!state.tickers.some((ticker) => ticker.pair === state.pair)) {
        state.pair = state.tickers[0].pair;
        safeSet("kaviont.market.pair", state.pair);
      }
      const params = new URLSearchParams({ pair: state.pair, range: state.range, limit: "500" });
      const [history, summary] = await Promise.all([
        getJson(API + "/history?" + params.toString()),
        getJson(API + "/summary?" + new URLSearchParams({ pair: state.pair, range: state.range }).toString())
      ]);
      state.history = Array.isArray(history.data) ? history.data : [];
      state.summary = summary;
      state.lastUpdated = new Date();
      renderHeader(selectedTicker());
      renderSummary();
      renderWorker();
      renderMarkets();
      renderChart();
      setConnection("online", "API connected");
      const ticker = selectedTicker();
      setNotice("Market values are read from persisted Kraken snapshots. The browser refreshes every 15 seconds; the worker polls Kraken every " +
        formatNumber(tickerPayload.poll_interval_seconds, 0) + " seconds.");
    } catch (error) {
      setConnection("error", "Data unavailable");
      setNotice(error.message || "Market data could not be loaded.", true);
      if (!state.tickers.length) setEmptyState("Market API is not available. Check the API and PostgreSQL services.");
    } finally {
      state.busy = false;
      $("#refreshButton").classList.remove("is-loading");
    }
  }

  function changeRange(range) {
    if (!["1h", "24h", "7d"].includes(range) || state.range === range) return;
    state.range = range;
    document.querySelectorAll("[data-range]").forEach((button) => {
      const active = button.dataset.range === range;
      button.classList.toggle("active", active);
      button.setAttribute("aria-pressed", String(active));
    });
    if (!state.tickers.length || !state.pair) return;
    loadSelectedRange();
  }

  async function loadSelectedRange() {
    if (state.busy) return;
    state.busy = true;
    setConnection("loading", "Updating chart");
    try {
      const params = new URLSearchParams({ pair: state.pair, range: state.range, limit: "500" });
      const [history, summary] = await Promise.all([
        getJson(API + "/history?" + params.toString()),
        getJson(API + "/summary?" + new URLSearchParams({ pair: state.pair, range: state.range }).toString())
      ]);
      state.history = Array.isArray(history.data) ? history.data : [];
      state.summary = summary;
      renderSummary();
      renderChart();
      setConnection("online", "API connected");
    } catch (error) {
      setNotice(error.message || "Selected time range could not be loaded.", true);
      setConnection("error", "Data unavailable");
    } finally {
      state.busy = false;
    }
  }

  function selectPair(pair) {
    if (!state.tickers.some((ticker) => ticker.pair === pair) || pair === state.pair) return;
    state.pair = pair;
    safeSet("kaviont.market.pair", pair);
    renderMarkets();
    loadMarket();
  }

  function toggleAutoRefresh() {
    state.autoRefresh = !state.autoRefresh;
    const button = $("#autoRefreshButton");
    button.classList.toggle("is-on", state.autoRefresh);
    button.setAttribute("aria-pressed", String(state.autoRefresh));
    setNotice(state.autoRefresh
      ? "Automatic refresh is enabled. Market data is re-read every 15 seconds."
      : "Automatic refresh is paused. Use the refresh button to request updated market data.");
  }

  $("#refreshButton").addEventListener("click", loadMarket);
  $("#autoRefreshButton").addEventListener("click", toggleAutoRefresh);
  $("#marketList").addEventListener("click", (event) => {
    const button = event.target.closest("[data-pair]");
    if (button) selectPair(button.dataset.pair);
  });
  document.querySelectorAll("[data-range]").forEach((button) => {
    button.addEventListener("click", () => changeRange(button.dataset.range));
  });
  $("#priceChart").addEventListener("pointermove", updateHover);
  $("#priceChart").addEventListener("pointerleave", () => {
    const crosshair = $("#chartCrosshair");
    const marker = $("#chartHoverPoint");
    if (crosshair) crosshair.setAttribute("opacity", "0");
    if (marker) marker.setAttribute("opacity", "0");
    $("#chartTooltip").style.display = "none";
  });

  $("#currentYear").textContent = String(new Date().getFullYear());
  loadMarket();
  window.setInterval(() => {
    if (state.autoRefresh) loadMarket();
  }, REFRESH_MS);
})();
