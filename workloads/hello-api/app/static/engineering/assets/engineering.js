(() => {
  "use strict";

  const API = "/v1/engineering";
  const $ = (selector) => document.querySelector(selector);
  const state = {
    repositories: [],
    selectedRepository: "",
    currentView: "overview",
    overview: null,
    security: null,
    pipelines: null,
    toastTimer: null,
    searchTimer: null
  };

  const escapeHtml = (value) => String(value ?? "").replace(/[&<>"']/g, (character) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  })[character]);

  const safeUrl = (value) => {
    try {
      const url = new URL(String(value || ""));
      return url.protocol === "https:" ? url.href : "#";
    } catch (_) {
      return "#";
    }
  };

  const formatDate = (value) => {
    if (!value) return "—";
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? "—" : date.toLocaleString();
  };

  const formatRelative = (value) => {
    if (!value) return "—";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "—";
    const seconds = Math.max(0, Math.floor((Date.now() - date.getTime()) / 1000));
    if (seconds < 60) return "just now";
    if (seconds < 3600) return Math.floor(seconds / 60) + "m ago";
    if (seconds < 86400) return Math.floor(seconds / 3600) + "h ago";
    if (seconds < 30 * 86400) return Math.floor(seconds / 86400) + "d ago";
    return date.toLocaleDateString();
  };

  const pairFromName = (repo) => String(repo || "").split("/").pop() || "";
  const splitRepository = (fullName) => {
    const separator = String(fullName || "").indexOf("/");
    if (separator < 1) return null;
    return [fullName.slice(0, separator), fullName.slice(separator + 1)];
  };

  async function request(path) {
    const response = await fetch(API + path, {
      headers: { "Accept": "application/json" },
      credentials: "same-origin"
    });
    let payload = {};
    try { payload = await response.json(); } catch (_) { /* Non-JSON response. */ }
    if (!response.ok) {
      const error = new Error(payload.detail || "Request failed (" + response.status + ")");
      error.status = response.status;
      throw error;
    }
    return payload;
  }

  function toast(message, type) {
    const element = $("#toast");
    if (!element) return;
    element.textContent = message;
    element.className = "toast show" + (type === "error" ? " error" : "");
    if (state.toastTimer) window.clearTimeout(state.toastTimer);
    state.toastTimer = window.setTimeout(() => element.classList.remove("show"), 3600);
  }

  function setLastRefresh() {
    $("#lastRefresh").textContent = "Synced " + new Date().toLocaleTimeString();
  }

  function setConnection(connected, label) {
    const card = $("#githubConnection");
    card.dataset.state = connected ? "connected" : "error";
    $("#githubConnectionText").textContent = label;
    $("#platformStatus").textContent = connected ? "OPERATIONAL" : "CONFIGURATION NEEDED";
    $("#setupBanner").hidden = connected;
  }

  function go(view) {
    if (!document.getElementById("view-" + view)) return;
    state.currentView = view;
    document.querySelectorAll(".portal-view").forEach((panel) => {
      panel.classList.toggle("active", panel.id === "view-" + view);
    });
    document.querySelectorAll(".nav-item").forEach((item) => {
      item.classList.toggle("active", item.dataset.view === view);
    });
    const active = document.querySelector('.nav-item[data-view="' + view + '"]');
    $("#breadcrumbCurrent").textContent = active ? active.textContent.trim() : view;
    loadView(view);
  }

  function renderLanguageList(languages) {
    const items = languages || [];
    const total = items.reduce((sum, item) => sum + Number(item.count || 0), 0) || 1;
    $("#languageList").innerHTML = items.length ? items.slice(0, 8).map((item) => {
      const percent = Math.max(3, Math.round((Number(item.count || 0) / total) * 100));
      return '<div class="language-row"><div class="language-label"><span>' +
        escapeHtml(item.language) + '</span><small>' + item.count + ' repos</small></div>' +
        '<div class="language-track"><span style="width:' + percent + '%"></span></div></div>';
    }).join("") : '<div class="empty-state">No language metadata available.</div>';
  }

  function renderRecentRepositories(items) {
    const container = $("#recentRepos");
    if (!items || !items.length) {
      container.innerHTML = '<tr><td colspan="4" class="table-empty">No repositories were returned by GitHub.</td></tr>';
      return;
    }
    container.innerHTML = items.slice(0, 8).map((item) =>
      '<tr data-repo="' + escapeHtml(item.full_name) + '">' +
      '<td><div class="repo-name"><span class="repo-symbol">⌘</span><span><strong>' +
      escapeHtml(item.full_name) + '</strong><small>' + escapeHtml(item.description || "No description") +
      '</small></span></div></td>' +
      '<td>' + (item.language ? '<span class="language-pill">' + escapeHtml(item.language) + '</span>' : "—") + '</td>' +
      '<td><span class="visibility-pill ' + (item.archived ? "archived" : item.private ? "private" : "") + '">' +
      (item.archived ? "Archived" : item.private ? "Private" : "Public") + '</span></td>' +
      '<td>' + escapeHtml(formatRelative(item.pushed_at)) + '</td></tr>'
    ).join("");
  }

  function updateRepoSelectors() {
    const options = state.repositories.map((item) =>
      '<option value="' + escapeHtml(item.full_name) + '">' + escapeHtml(item.full_name) + '</option>'
    ).join("");
    ["#securityRepo", "#pipelineRepo"].forEach((selector) => {
      const element = $(selector);
      const previous = element.value || state.selectedRepository;
      element.innerHTML = '<option value="">Select repository</option>' + options;
      if (state.repositories.some((item) => item.full_name === previous)) {
        element.value = previous;
      } else if (state.repositories.length) {
        element.value = state.repositories[0].full_name;
      }
    });
  }

  function renderRepositories(items) {
    const filtered = items || [];
    $("#repoTotal").textContent = filtered.length + " repositories";
    $("#navRepoCount").textContent = String(state.repositories.length);
    const container = $("#repoTable");
    if (!filtered.length) {
      container.innerHTML = '<tr><td colspan="6" class="table-empty">No repositories match this filter.</td></tr>';
      return;
    }
    container.innerHTML = filtered.map((item) => {
      const topics = (item.topics || []).slice(0, 3).join(" · ");
      return '<tr data-repo="' + escapeHtml(item.full_name) + '">' +
        '<td><div class="repo-name"><span class="repo-symbol">⌘</span><span><strong>' +
        escapeHtml(item.full_name) + '</strong><small>' + escapeHtml(item.description || topics || "No description") +
        '</small></span></div></td>' +
        '<td>' + (item.language ? '<span class="language-pill">' + escapeHtml(item.language) + '</span>' : "—") + '</td>' +
        '<td>' + escapeHtml(item.default_branch || "—") + '</td>' +
        '<td>' + Number(item.open_issues_count || 0) + '</td>' +
        '<td>' + escapeHtml(formatRelative(item.updated_at)) + '</td>' +
        '<td><span class="finding-link">Inspect →</span></td></tr>';
    }).join("");
  }

  function renderRepositoryDetail(payload) {
    const repository = payload.repository || {};
    $("#repoDetailName").textContent = repository.full_name || "Repository";
    const external = $("#repoExternalLink");
    external.href = safeUrl(repository.html_url);
    external.hidden = external.href === "#";
    const pulls = payload.open_pull_requests || [];
    const issues = payload.open_issues || [];
    const topics = (repository.topics || []).slice(0, 7);
    $("#repoDetailBody").className = "";
    $("#repoDetailBody").innerHTML =
      '<div class="detail-content">' +
      '<div class="detail-stat"><span>VISIBILITY</span><strong>' + (repository.private ? "Private" : "Public") + '</strong></div>' +
      '<div class="detail-stat"><span>DEFAULT BRANCH</span><strong>' + escapeHtml(repository.default_branch || "—") + '</strong></div>' +
      '<div class="detail-stat"><span>LANGUAGE</span><strong>' + escapeHtml(repository.language || "—") + '</strong></div>' +
      '<div class="detail-stat"><span>OPEN ISSUES</span><strong>' + Number(repository.open_issues_count || 0) + '</strong></div>' +
      '</div>' +
      '<div class="detail-lists">' +
      '<div class="detail-list"><h3>Open pull requests · ' + pulls.length + '</h3>' +
      (pulls.length ? pulls.slice(0, 5).map((item) =>
        '<div class="detail-list-item"><span><a href="' + safeUrl(item.html_url) + '" target="_blank" rel="noreferrer">#' +
        item.number + ' ' + escapeHtml(item.title) + '</a></span><small>' +
        (item.draft ? "Draft" : escapeHtml(item.head || "—")) + '</small></div>'
      ).join("") : '<div class="empty-state">No open pull requests.</div>') +
      '</div>' +
      '<div class="detail-list"><h3>Open issues · ' + issues.length + '</h3>' +
      (issues.length ? issues.slice(0, 5).map((item) =>
        '<div class="detail-list-item"><span><a href="' + safeUrl(item.html_url) + '" target="_blank" rel="noreferrer">#' +
        item.number + ' ' + escapeHtml(item.title) + '</a></span><small>' +
        escapeHtml(item.user || "—") + '</small></div>'
      ).join("") : '<div class="empty-state">No open issues.</div>') +
      '</div></div>' +
      (topics.length ? '<div class="service-meta" style="padding:0 18px 16px">' +
        topics.map((topic) => '<span>' + escapeHtml(topic) + '</span>').join("") + '</div>' : "");
  }

  async function loadRepositoryDetail(fullName) {
    const parts = splitRepository(fullName);
    if (!parts) return;
    $("#repoDetailName").textContent = fullName;
    $("#repoDetailBody").className = "empty-state";
    $("#repoDetailBody").textContent = "Loading repository details…";
    try {
      const payload = await request("/repositories/" + encodeURIComponent(parts[0]) + "/" + encodeURIComponent(parts[1]));
      renderRepositoryDetail(payload);
    } catch (error) {
      $("#repoDetailBody").className = "empty-state";
      $("#repoDetailBody").textContent = error.message;
    }
  }

  async function loadOverview() {
    try {
      const payload = await request("/overview");
      state.overview = payload;
      $("#metricRepos").textContent = payload.repository_count;
      $("#metricPrivate").textContent = payload.private_count;
      $("#metricReposHint").textContent = payload.archived_count + " archived repositories";
      renderRecentRepositories(payload.recent_repositories);
      renderLanguageList(payload.languages);
    } catch (error) {
      $("#metricRepos").textContent = "—";
      $("#recentRepos").innerHTML = '<tr><td colspan="4" class="table-empty">' + escapeHtml(error.message) + '</td></tr>';
      throw error;
    }
  }

  async function loadRepositories(search) {
    const query = search ? "?search=" + encodeURIComponent(search) + "&per_page=100" : "?per_page=100";
    const payload = await request("/repositories" + query);
    state.repositories = payload.repositories || [];
    renderRepositories(state.repositories);
    updateRepoSelectors();
    $("#repoTotal").textContent = payload.count + " repositories";
    if (!state.selectedRepository && state.repositories.length) {
      state.selectedRepository = state.repositories[0].full_name;
    }
    if (state.selectedRepository) {
      $("#securityRepo").value = state.selectedRepository;
      $("#pipelineRepo").value = state.selectedRepository;
    }
    return state.repositories;
  }

  function renderSecurity(payload) {
    const counts = payload.counts || {};
    $("#countCritical").textContent = counts.critical || 0;
    $("#countHigh").textContent = counts.high || 0;
    $("#countMedium").textContent = counts.medium || 0;
    $("#countLow").textContent = counts.low || 0;
    $("#findingTotal").textContent = payload.total_open + " findings";
    $("#metricFindings").textContent = payload.total_open;
    $("#navFindings").textContent = String(payload.total_open);
    const sourceLabels = Object.entries(payload.sources || {}).map(([key, value]) =>
      key.replace("_", " ") + ": " + value.status
    );
    $("#securitySourceStatus").textContent = sourceLabels.length
      ? sourceLabels.join(" · ")
      : "No security sources returned";
    const findings = payload.findings || [];
    const container = $("#findingTable");
    if (!findings.length) {
      container.innerHTML = '<tr><td colspan="5" class="table-empty">No open findings returned by the connected GitHub security APIs. This does not mean the repository has no vulnerabilities: run the Kaviont security workflow and enable the relevant GitHub security features.</td></tr>';
      return;
    }
    container.innerHTML = findings.map((item) => {
      const location = item.file ? item.file + (item.line ? ":" + item.line : "") : (item.package || item.manifest || "—");
      const title = item.summary || item.rule_id || item.cve_id || item.ghsa_id || "Security finding";
      const identifiers = [item.cve_id, item.ghsa_id, item.rule_id].filter(Boolean).join(" · ");
      return '<tr><td><span class="severity-pill ' + escapeHtml(String(item.severity || "unknown").toLowerCase()) + '">' +
        escapeHtml(String(item.severity || "unknown").toUpperCase()) + '</span></td>' +
        '<td><div class="finding-title"><strong>' + escapeHtml(title) + '</strong><small>' + escapeHtml(identifiers || item.package || "No identifier") + '</small></div></td>' +
        '<td>' + escapeHtml(item.source || "—") + '</td>' +
        '<td>' + (item.owasp_mapping ? '<span class="owasp-tag">' + escapeHtml(item.owasp_mapping) + '</span>' : '<span class="finding-link">Manual review</span>') + '</td>' +
        '<td>' + (item.html_url ? '<a class="finding-link" href="' + safeUrl(item.html_url) + '" target="_blank" rel="noreferrer">' + escapeHtml(location) + ' ↗</a>' : escapeHtml(location)) + '</td></tr>';
    }).join("");
  }

  async function loadSecurity(fullName) {
    const selected = fullName || $("#securityRepo").value || state.selectedRepository;
    if (!selected) {
      $("#findingTable").innerHTML = '<tr><td colspan="5" class="table-empty">Select a repository first.</td></tr>';
      return;
    }
    const parts = splitRepository(selected);
    if (!parts) return;
    $("#securitySourceStatus").textContent = "Loading security sources…";
    $("#findingTable").innerHTML = '<tr><td colspan="5" class="table-empty">Loading code scanning and Dependabot alerts…</td></tr>';
    try {
      const payload = await request("/repositories/" + encodeURIComponent(parts[0]) + "/" + encodeURIComponent(parts[1]) + "/security");
      state.security = payload;
      renderSecurity(payload);
      const securityUrl = "https://github.com/" + encodeURIComponent(parts[0]) + "/" + encodeURIComponent(parts[1]) + "/security";
      $("#securityExternal").href = securityUrl;
      $("#securityExternal").hidden = false;
    } catch (error) {
      $("#securitySourceStatus").textContent = error.message;
      $("#findingTable").innerHTML = '<tr><td colspan="5" class="table-empty">' + escapeHtml(error.message) + '</td></tr>';
      throw error;
    }
  }

  function renderPipelines(payload) {
    const runs = payload.runs || [];
    $("#pipelineRuns").textContent = runs.length;
    $("#pipelineSuccess").textContent = payload.successful;
    $("#pipelineFailed").textContent = payload.failed;
    $("#metricPipelines").textContent = payload.failed;
    $("#metricPipelinesHint").textContent = runs.length + " latest runs inspected";
    if (!runs.length) {
      $("#pipelineTable").innerHTML = '<tr><td colspan="6" class="table-empty">No workflow runs found for this repository.</td></tr>';
      return;
    }
    $("#pipelineTable").innerHTML = runs.map((run) =>
      '<tr><td><strong>' + escapeHtml(run.name || run.workflow_name || "Workflow") + '</strong></td>' +
      '<td>' + escapeHtml(run.head_branch || "—") + '</td>' +
      '<td><span class="status-pill ' + escapeHtml(run.status || "unknown") + '">' + escapeHtml(run.status || "unknown") + '</span></td>' +
      '<td><span class="status-pill ' + escapeHtml(run.conclusion || run.status || "unknown") + '">' + escapeHtml(run.conclusion || "—") + '</span></td>' +
      '<td>' + escapeHtml(formatRelative(run.created_at)) + '</td>' +
      '<td><a class="finding-link" href="' + safeUrl(run.html_url) + '" target="_blank" rel="noreferrer">Open ↗</a></td></tr>'
    ).join("");
  }

  async function loadPipelines(fullName) {
    const selected = fullName || $("#pipelineRepo").value || state.selectedRepository;
    if (!selected) return;
    const parts = splitRepository(selected);
    if (!parts) return;
    $("#pipelineTable").innerHTML = '<tr><td colspan="6" class="table-empty">Loading workflow runs…</td></tr>';
    try {
      const payload = await request("/repositories/" + encodeURIComponent(parts[0]) + "/" + encodeURIComponent(parts[1]) + "/pipelines");
      state.pipelines = payload;
      renderPipelines(payload);
    } catch (error) {
      $("#pipelineTable").innerHTML = '<tr><td colspan="6" class="table-empty">' + escapeHtml(error.message) + '</td></tr>';
      throw error;
    }
  }

  function renderServices(services) {
    $("#serviceTotal").textContent = services.length + " entries";
    if (!services.length) {
      $("#serviceGrid").innerHTML = '<div class="empty-state">No repositories available.</div>';
      return;
    }
    $("#serviceGrid").innerHTML = services.map((service) => {
      const topics = (service.topics || []).slice(0, 5);
      return '<article class="service-card"><div class="service-card-head"><span class="service-icon">▦</span><span class="language-pill">' +
        escapeHtml(service.service_type) + '</span></div><h3>' + escapeHtml(service.full_name) + '</h3>' +
        '<p>' + escapeHtml(service.description || "No service description registered.") + '</p>' +
        '<div class="service-meta"><span>' + escapeHtml(service.language || "Unspecified language") + '</span>' +
        '<span>' + (service.private ? "Private" : "Public") + '</span>' +
        topics.map((topic) => '<span>' + escapeHtml(topic) + '</span>').join("") + '</div>' +
        '<div class="service-meta"><span>Owner: not registered</span><span>Criticality: unclassified</span></div>' +
        '<a class="service-link" href="' + safeUrl(service.html_url) + '" target="_blank" rel="noreferrer">Open repository ↗</a></article>';
    }).join("");
  }

  async function loadServices() {
    try {
      const payload = await request("/services");
      renderServices(payload.services || []);
    } catch (error) {
      $("#serviceGrid").innerHTML = '<div class="empty-state">' + escapeHtml(error.message) + '</div>';
      throw error;
    }
  }

  async function loadCloud() {
    const payload = await request("/cloud");
    const providers = payload.provider_configuration || {};
    const labels = { azure: "Azure", aws: "AWS", gcp: "Google Cloud" };
    $("#cloudProviderCards").innerHTML = Object.entries(providers).map(([key, provider]) =>
      '<article class="integration-card"><div class="integration-logo cloud-logo">' +
      escapeHtml(key.toUpperCase()) + '</div><div><h3>' + escapeHtml(labels[key] || key) +
      '</h3><p>' + (provider.configuration_present
        ? "Cloud configuration variables are present. Identity and inventory access have not yet been verified."
        : "No cloud identity configuration detected.") +
      '</p><span class="integration-state pending">' + escapeHtml(provider.inventory_status || "not connected") +
      '</span></div></article>'
    ).join("");

    const repositories = payload.infrastructure_repositories || [];
    $("#cloudRepoCount").textContent = repositories.length + " repositories";
    $("#cloudRepoTable").innerHTML = repositories.length
      ? repositories.map((item) =>
        '<tr data-repo="' + escapeHtml(item.full_name) + '">' +
        '<td><div class="repo-name"><span class="repo-symbol">IaC</span><span><strong>' +
        escapeHtml(item.full_name) + '</strong><small>' + escapeHtml(item.description || "Infrastructure codebase") +
        '</small></span></div></td><td>' + escapeHtml(item.language || "—") +
        '</td><td>' + escapeHtml(formatRelative(item.pushed_at)) +
        '</td><td><span class="visibility-pill ' + (item.private ? "private" : "") + '">' +
        (item.private ? "Private" : "Public") + '</span></td></tr>'
      ).join("")
      : '<tr><td colspan="4" class="table-empty">No repositories with IaC language or topics were detected.</td></tr>';
  }

  async function loadKubernetes() {
    const ids = ["#kubeDeployments", "#kubePods", "#kubeNotReady", "#kubeRestarts"];
    ids.forEach((selector) => { $(selector).textContent = "…"; });
    try {
      const payload = await request("/kubernetes");
      $("#kubeNamespace").textContent = "Namespace " + (payload.namespace || "—");
      if (!payload.configured || payload.authorized === false) {
        ids.forEach((selector) => { $(selector).textContent = "—"; });
        const message = payload.message || "Kubernetes read-only access is not configured.";
        $("#deploymentTable").innerHTML = '<tr><td colspan="4" class="table-empty">' + escapeHtml(message) + '</td></tr>';
        $("#podTable").innerHTML = '<tr><td colspan="5" class="table-empty">' + escapeHtml(message) + '</td></tr>';
        return;
      }
      $("#kubeDeployments").textContent = payload.deployment_count;
      $("#kubePods").textContent = payload.pod_count;
      $("#kubeNotReady").textContent = payload.not_ready_pods;
      $("#kubeRestarts").textContent = payload.restart_count;
      $("#deploymentTable").innerHTML = (payload.deployments || []).length
        ? payload.deployments.map((item) => '<tr><td>' + escapeHtml(item.name) + '</td><td>' +
          Number(item.ready_replicas || 0) + ' / ' + Number(item.replicas || 0) + '</td><td>' +
          Number(item.available_replicas || 0) + '</td><td>' + escapeHtml(item.image || "—") + '</td></tr>').join("")
        : '<tr><td colspan="4" class="table-empty">No deployments found in this namespace.</td></tr>';
      $("#podTable").innerHTML = (payload.pods || []).length
        ? payload.pods.map((item) => '<tr><td>' + escapeHtml(item.name) + '</td><td>' +
          '<span class="status-pill ' + (item.phase === "Running" ? "success" : "failure") + '">' + escapeHtml(item.phase || "unknown") + '</span></td><td>' +
          (item.ready ? "Ready" : "Not ready") + '</td><td>' + Number(item.restarts || 0) +
          '</td><td>' + escapeHtml(item.node || "—") + '</td></tr>').join("")
        : '<tr><td colspan="5" class="table-empty">No pods found in this namespace.</td></tr>';
      $("#kubeEventTable").innerHTML = (payload.events || []).length
        ? payload.events.map((item) => '<tr><td><span class="status-pill ' + (item.type === "Warning" ? "failure" : "success") + '">' + escapeHtml(item.type || "—") + '</span></td><td>' +
          escapeHtml(item.reason || "—") + '</td><td>' + escapeHtml(item.object || "—") + '</td><td style="white-space:normal;min-width:240px;max-width:460px">' +
          escapeHtml(item.message || "—") + '</td><td>' + escapeHtml(formatRelative(item.last_timestamp)) + '</td></tr>').join("")
        : '<tr><td colspan="5" class="table-empty">No recent events found.</td></tr>';
    } catch (error) {
      ids.forEach((selector) => { $(selector).textContent = "—"; });
      $("#deploymentTable").innerHTML = '<tr><td colspan="4" class="table-empty">' + escapeHtml(error.message) + '</td></tr>';
      $("#podTable").innerHTML = '<tr><td colspan="5" class="table-empty">Kubernetes connection unavailable.</td></tr>';
      $("#kubeEventTable").innerHTML = '<tr><td colspan="5" class="table-empty">Kubernetes connection unavailable.</td></tr>';
      throw error;
    }
  }

  async function loadKnowledge() {
    try {
      const payload = await request("/knowledge");
      const docs = payload.documents || [];
      $("#knowledgeGrid").innerHTML = docs.length ? docs.map((doc) =>
        '<article class="knowledge-card"><div class="knowledge-card-head"><span class="knowledge-icon">▤</span><span class="language-pill">Markdown</span></div>' +
        '<h3>' + escapeHtml(doc.name) + '</h3><p>Repository engineering documentation and operating guidance.</p>' +
        '<div class="knowledge-path">' + escapeHtml(doc.path) + '</div>' +
        '<a href="' + safeUrl(doc.html_url) + '" target="_blank" rel="noreferrer">Read document ↗</a></article>'
      ).join("") : '<div class="empty-state">No Markdown documents found in the configured knowledge repository.</div>';
    } catch (error) {
      $("#knowledgeGrid").innerHTML = '<div class="empty-state">' + escapeHtml(error.message) + '</div>';
      throw error;
    }
  }

  async function loadTemplates() {
    try {
      const payload = await request("/templates");
      const templates = payload.templates || [];
      $("#templateGrid").innerHTML = templates.map((template) =>
        '<article class="template-card"><span class="template-icon">✳</span><span class="language-pill">' +
        escapeHtml(template.category) + '</span><h3>' + escapeHtml(template.name) + '</h3><p>' +
        escapeHtml(template.description) + '</p><div class="template-stack">' +
        (template.stack || []).map((stack) => '<span>' + escapeHtml(stack) + '</span>').join("") +
        '</div><button type="button" class="button button-secondary template-download" data-template-download="' + escapeHtml(template.id) + '">Download blueprint ↓</button></article>'
      ).join("");
    } catch (error) {
      $("#templateGrid").innerHTML = '<div class="empty-state">' + escapeHtml(error.message) + '</div>';
      throw error;
    }
  }

  async function loadView(view) {
    try {
      if (view === "overview") await Promise.all([loadOverview(), loadRepositories()]);
      if (view === "repositories") await loadRepositories($("#repoSearch").value);
      if (view === "security") {
        await loadRepositories();
        await loadSecurity();
      }
      if (view === "pipelines") {
        await loadRepositories();
        await loadPipelines();
      }
      if (view === "services") await loadServices();
      if (view === "runtime") await loadKubernetes();
      if (view === "cloud") await loadCloud();
      if (view === "knowledge") await loadKnowledge();
      if (view === "templates") await loadTemplates();
      setLastRefresh();
    } catch (error) {
      if (error.status === 503 && String(error.message).includes("GitHub integration is not configured")) {
        setConnection(false, "Token not configured");
        $("#setupBanner").hidden = false;
      } else {
        toast(error.message, "error");
      }
    }
  }

  async function bootstrap() {
    try {
      const status = await request("/status");
      if (!status.github_configured) {
        setConnection(false, "Token not configured");
        return;
      }
      setConnection(true, "Read-only connection");
      await Promise.all([loadOverview(), loadRepositories()]);
      if (state.selectedRepository) {
        try { await loadSecurity(state.selectedRepository); } catch (_) { /* Security permissions are optional. */ }
        try { await loadPipelines(state.selectedRepository); } catch (_) { /* Actions permissions are optional. */ }
      }
      setLastRefresh();
    } catch (error) {
      setConnection(false, "Connection unavailable");
      toast(error.message, "error");
    }
  }

  document.querySelectorAll("[data-view]").forEach((button) => {
    button.addEventListener("click", () => go(button.dataset.view));
  });
  document.querySelectorAll("[data-go]").forEach((button) => {
    button.addEventListener("click", () => go(button.dataset.go));
  });
  $("#recentRepos").addEventListener("click", (event) => {
    const row = event.target.closest("tr[data-repo]");
    if (!row) return;
    state.selectedRepository = row.dataset.repo;
    go("repositories");
    loadRepositoryDetail(state.selectedRepository);
  });
  $("#repoTable").addEventListener("click", (event) => {
    const row = event.target.closest("tr[data-repo]");
    if (!row) return;
    state.selectedRepository = row.dataset.repo;
    $("#securityRepo").value = state.selectedRepository;
    $("#pipelineRepo").value = state.selectedRepository;
    loadRepositoryDetail(state.selectedRepository);
  });
  $("#repoSearch").addEventListener("input", () => {
    if (state.searchTimer) window.clearTimeout(state.searchTimer);
    state.searchTimer = window.setTimeout(() => {
      loadRepositories($("#repoSearch").value).catch((error) => toast(error.message, "error"));
    }, 250);
  });
  $("#repoVisibility").addEventListener("change", () => {
    const filter = $("#repoVisibility").value;
    const filtered = state.repositories.filter((item) => {
      if (filter === "private") return item.private;
      if (filter === "public") return !item.private && !item.archived;
      if (filter === "archived") return item.archived;
      return true;
    });
    renderRepositories(filtered);
  });
  $("#repoReload").addEventListener("click", () => loadRepositories($("#repoSearch").value).catch((error) => toast(error.message, "error")));
  $("#securityRepo").addEventListener("change", () => {
    state.selectedRepository = $("#securityRepo").value;
    loadSecurity(state.selectedRepository).catch((error) => toast(error.message, "error"));
  });
  $("#pipelineRepo").addEventListener("change", () => {
    state.selectedRepository = $("#pipelineRepo").value;
    loadPipelines(state.selectedRepository).catch((error) => toast(error.message, "error"));
  });
  $("#pipelineReload").addEventListener("click", () => loadPipelines().catch((error) => toast(error.message, "error")));
  $("#runtimeReload").addEventListener("click", () => loadKubernetes().catch((error) => toast(error.message, "error")));
  $("#templateGrid").addEventListener("click", async (event) => {
    const button = event.target.closest("button[data-template-download]");
    if (!button) return;
    const templateId = button.dataset.templateDownload;
    button.disabled = true;
    try {
      const response = await fetch(API + "/templates/" + encodeURIComponent(templateId) + "/download", {
        credentials: "same-origin",
        headers: { "Accept": "application/zip" }
      });
      if (!response.ok) {
        let payload = {};
        try { payload = await response.json(); } catch (_) { /* Non-JSON response. */ }
        throw new Error(payload.detail || "Template download failed.");
      }
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = "kaviont-" + templateId + ".zip";
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      window.URL.revokeObjectURL(url);
      toast("Blueprint archive created.");
    } catch (error) {
      toast(error.message, "error");
    } finally {
      button.disabled = false;
    }
  });

  $("#refreshAll").addEventListener("click", async () => {
    try {
      await bootstrap();
      toast("Engineering workspace refreshed.");
    } catch (error) {
      toast(error.message, "error");
    }
  });

  if ("serviceWorker" in navigator && (window.location.protocol === "https:" || window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1")) {
    window.addEventListener("load", () => {
      navigator.serviceWorker.register("/engineering/service-worker.js", { scope: "/engineering/" })
        .catch(() => toast("Offline shell could not be prepared. Live portal use is unaffected.", "error"));
    });
  }

  bootstrap();
})();
