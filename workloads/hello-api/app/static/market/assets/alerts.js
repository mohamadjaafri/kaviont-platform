(() => {
  "use strict";

  const API = "/v1/market/kraken";
  const $ = (selector) => document.querySelector(selector);
  const form = $("#alertForm");
  const pairSelect = $("#alertPair");
  const conditionSelect = $("#alertCondition");
  const thresholdInput = $("#alertThreshold");
  const statusMessage = $("#alertsMessage");

  if (!form || !pairSelect || !conditionSelect || !thresholdInput) return;

  const currencyForPair = (pair) => {
    for (const currency of ["USD", "EUR", "GBP", "JPY", "CAD", "CHF"]) {
      if (pair.endsWith(currency)) return currency;
    }
    return "";
  };

  const formatPrice = (value, pair) => {
    const currency = currencyForPair(pair);
    return Number(value).toLocaleString(undefined, {
      minimumFractionDigits: 2,
      maximumFractionDigits: 8
    }) + (currency ? " " + currency : "");
  };

  const escapeHtml = (value) => String(value).replace(/[&<>"']/g, (character) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  })[character]);

  async function request(path, options) {
    const response = await fetch(API + path, {
      headers: { "Content-Type": "application/json" },
      ...options
    });
    let payload = {};
    try { payload = await response.json(); } catch (_) { /* Empty response body. */ }
    if (!response.ok) throw new Error(payload.detail || "Request failed (" + response.status + ")");
    return payload;
  }

  function showMessage(message, kind) {
    statusMessage.textContent = message;
    statusMessage.dataset.state = kind || "info";
  }

  function updateThresholdHint() {
    const condition = conditionSelect.value;
    const percent = condition === "percent_up" || condition === "percent_down";
    thresholdInput.step = percent ? "0.1" : "any";
    thresholdInput.max = condition === "percent_down" ? "99.9" : "1000000000000";
    thresholdInput.placeholder = percent ? "e.g. 3" : "e.g. 70000";
    $("#thresholdUnit").textContent = percent ? "%" : (currencyForPair(pairSelect.value) || "price");
    $("#thresholdHint").textContent = percent
      ? "Measured from the latest stored price when you create this rule."
      : "The rule triggers when a new stored price reaches this level.";
  }

  function describeCondition(alert) {
    const threshold = Number(alert.threshold);
    if (alert.condition === "above") return "Price above " + formatPrice(threshold, alert.pair);
    if (alert.condition === "below") return "Price below " + formatPrice(threshold, alert.pair);
    const direction = alert.condition === "percent_up" ? "rises" : "falls";
    return direction + " " + threshold + "% from " + formatPrice(alert.reference_price, alert.pair);
  }

  function renderAlerts(alerts) {
    const container = $("#activeAlerts");
    const visible = alerts || [];
    $("#alertCount").textContent = String(visible.filter((item) => item.status === "active").length);
    if (!visible.length) {
      container.innerHTML = '<div class="alerts-empty">No price rules yet. Create your first alert above.</div>';
      return;
    }
    container.innerHTML = visible.map((alert) => {
      const status = String(alert.status);
      const toggleLabel = status === "active" ? "Pause" : "Resume";
      const toggleAction = status === "active" || status === "paused"
        ? '<button type="button" class="alert-action" data-action="toggle" data-id="' + alert.id + '" data-active="' + (status !== "active") + '">' + toggleLabel + '</button>'
        : "";
      const deleteAction = '<button type="button" class="alert-action danger" data-action="delete" data-id="' + alert.id + '">Remove</button>';
      const meta = status === "triggered"
        ? "Triggered " + new Date(alert.triggered_at).toLocaleString()
        : status === "paused" ? "Paused" : "Checking on next market update";
      return '<article class="alert-rule" data-status="' + escapeHtml(status) + '">' +
        '<div class="alert-rule-copy"><div class="alert-rule-title">' + escapeHtml(alert.pair) +
        '<span class="alert-status">' + escapeHtml(status.toUpperCase()) + '</span></div>' +
        '<div class="alert-rule-condition">' + escapeHtml(describeCondition(alert)) + '</div>' +
        '<div class="alert-rule-meta">' + escapeHtml(meta) + '</div></div>' +
        '<div class="alert-rule-actions">' + toggleAction + deleteAction + '</div></article>';
    }).join("");
  }

  function renderEvents(events) {
    const container = $("#alertEvents");
    if (!events || !events.length) {
      container.innerHTML = '<div class="alerts-empty">Triggered alerts will appear here.</div>';
      return;
    }
    container.innerHTML = events.map((event) => {
      const description = event.condition === "above"
        ? "crossed above " + formatPrice(event.threshold, event.pair)
        : event.condition === "below"
          ? "crossed below " + formatPrice(event.threshold, event.pair)
          : (event.condition === "percent_up" ? "rose " : "fell ") +
            Number(event.threshold) + "% from its reference price";
      return '<article class="alert-event"><div><strong>' + escapeHtml(event.pair) +
        '</strong><span>' + escapeHtml(description) + '</span></div><time>' +
        escapeHtml(new Date(event.triggered_at).toLocaleString()) + '</time><b>' +
        escapeHtml(formatPrice(event.observed_price, event.pair)) + '</b></article>';
    }).join("");
  }

  async function loadMarkets() {
    const payload = await request("/tickers");
    const previous = pairSelect.value;
    const pairs = (payload.tickers || []).map((ticker) => ticker.pair);
    pairSelect.innerHTML = pairs.map((pair) =>
      '<option value="' + escapeHtml(pair) + '">' + escapeHtml(pair) + '</option>'
    ).join("");
    if (pairs.includes(previous)) pairSelect.value = previous;
    updateThresholdHint();
  }

  async function loadAlerts() {
    const results = await Promise.all([
      request("/alerts"),
      request("/alerts/events?limit=20")
    ]);
    renderAlerts(results[0].alerts);
    renderEvents(results[1].events);
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const submit = form.querySelector('button[type="submit"]');
    submit.disabled = true;
    showMessage("Creating rule…", "info");
    try {
      await request("/alerts", {
        method: "POST",
        body: JSON.stringify({
          pair: pairSelect.value,
          condition: conditionSelect.value,
          threshold: Number(thresholdInput.value)
        })
      });
      thresholdInput.value = "";
      showMessage("Price rule created. It will be evaluated on the next market snapshot.", "success");
      await loadAlerts();
    } catch (error) {
      showMessage(error.message, "error");
    } finally {
      submit.disabled = false;
    }
  });

  $("#activeAlerts").addEventListener("click", async (event) => {
    const button = event.target.closest("button[data-action]");
    if (!button) return;
    button.disabled = true;
    try {
      if (button.dataset.action === "toggle") {
        await request("/alerts/" + button.dataset.id, {
          method: "PATCH",
          body: JSON.stringify({ is_active: button.dataset.active === "true" })
        });
      } else {
        await request("/alerts/" + button.dataset.id, { method: "DELETE" });
      }
      await loadAlerts();
      showMessage("Alert rules updated.", "success");
    } catch (error) {
      showMessage(error.message, "error");
      button.disabled = false;
    }
  });

  conditionSelect.addEventListener("change", updateThresholdHint);
  pairSelect.addEventListener("change", updateThresholdHint);

  async function refresh() {
    try {
      if (!pairSelect.options.length) await loadMarkets();
      await loadAlerts();
    } catch (error) {
      showMessage(error.message, "error");
    }
  }

  updateThresholdHint();
  refresh();
  window.setInterval(refresh, 15000);
})();
