// Crew map: list of issues sorted by priority, pins on the map, detail card with actions.
(() => {
  const POLL_MS = 4000;
  const STATUS_ACTIONS = ["Verified", "Assigned", "Cleared"];
  const state = { issues: [], filter: "open", selected: null, markers: new Map(), seen: new Set(), first: true };

  const map = L.map("map", { zoomControl: true, preferCanvas: false });
  const base = RT.baseLayer().addTo(map);
  const pins = L.layerGroup().addTo(map);
  const layers = L.control.layers({ "Street map": base }, {}, { collapsed: false, position: "topright" }).addTo(map);
  map.setView([27.9614, -82.458], 17);

  const $list = document.getElementById("list");
  const $detail = document.getElementById("detail");
  const $counts = document.getElementById("counts");

  // ---------- scenes: before / after / detection layers ----------
  RT.json("/api/scenes").then(scenes => {
    if (!scenes.length) return;
    scenes.forEach((s, i) => {
      const before = L.imageOverlay(s.images.before, s.bounds, { opacity: 1 });
      const after = L.imageOverlay(s.images.after, s.bounds, { opacity: 1 });
      const overlay = L.imageOverlay(s.images.overlay, s.bounds, { opacity: 0.85 });
      const tag = scenes.length > 1 ? ` · ${s.name}` : "";
      layers.addOverlay(before, `Before storm${tag}`);
      layers.addOverlay(after, `After storm${tag}`);
      layers.addOverlay(overlay, `Detected new water${tag}`);
      if (i === 0) {
        after.addTo(map);
        overlay.addTo(map);
        map.fitBounds(s.bounds, { padding: [20, 20] });
      }
    });
    pins.eachLayer(m => m.bringToFront && m.bringToFront());
  }).catch(err => console.warn(err));

  // ---------- data ----------
  async function refresh() {
    try {
      state.issues = await RT.json("/api/issues");
    } catch (e) {
      $counts.textContent = "Offline — retrying…";
      return;
    }
    render();
    state.first = false;
  }

  function visible() {
    const f = state.filter;
    return state.issues.filter(i =>
      f === "all" ? true : f === "open" ? i.open : i.source === f && i.open);
  }

  // ---------- render ----------
  function render() {
    const open = state.issues.filter(i => i.open);
    const top = open.filter(i => i.priority === 1).length;
    $counts.innerHTML = `<b>${open.length}</b> open · <b class="p1">${top}</b> highest priority · ${state.issues.length - open.length} closed`;

    const items = visible();
    $list.innerHTML = items.length ? "" : `<li class="empty">Nothing here.</li>`;
    items.forEach((i, idx) => $list.appendChild(card(i, idx === 0 && state.filter !== "all")));

    // markers
    const keep = new Set();
    state.issues.forEach(i => {
      keep.add(i.id);
      let m = state.markers.get(i.id);
      const style = markerStyle(i);
      if (!m) {
        m = L.circleMarker([i.lat, i.lon], style).addTo(pins);
        m.on("click", () => select(i.id, false));
        m.bindTooltip(() => tooltip(state.issues.find(x => x.id === i.id) || i), { direction: "top" });
        state.markers.set(i.id, m);
        if (!state.first && !state.seen.has(i.id)) pulse(m);
      } else {
        m.setStyle(style);
        m.setLatLng([i.lat, i.lon]);
      }
      state.seen.add(i.id);
    });
    for (const [id, m] of state.markers) if (!keep.has(id)) { pins.removeLayer(m); state.markers.delete(id); }

    if (state.selected) {
      const cur = state.issues.find(i => i.id === state.selected);
      if (cur && !$detail.contains(document.activeElement)) showDetail(cur);
    }
  }

  function markerStyle(i) {
    const color = getComputedStyle(document.documentElement).getPropertyValue(`--p${i.priority}`).trim();
    const sel = i.id === state.selected;
    return {
      radius: sel ? 11 : i.source === "resident" ? 8 : 7,
      color: sel ? "#111" : "#fff",
      weight: sel ? 3 : 2,
      fillColor: i.open ? color : "#8a8f98",
      fillOpacity: i.open ? 0.95 : 0.5,
    };
  }

  function tooltip(i) {
    return `<b>${RT.esc(i.category_label)}</b><br>${RT.esc(i.priority_label)} · ${RT.esc(i.status)}`;
  }

  function pulse(m) {
    const el = m.getElement && m.getElement();
    if (el) { el.classList.add("pulse"); setTimeout(() => el.classList.remove("pulse"), 6000); }
  }

  function card(i, isTop) {
    const li = document.createElement("li");
    li.className = `issue p${i.priority}${i.open ? "" : " closed"}${i.id === state.selected ? " selected" : ""}`;
    li.tabIndex = 0;
    li.innerHTML = `
      ${isTop ? `<div class="next-up">Next up</div>` : ""}
      <div class="row">
        <span class="pill p${i.priority}">${RT.esc(i.priority_label)}</span>
        <span class="cat">${RT.esc(i.category_label)}</span>
        <span class="status s-${RT.esc(i.status.toLowerCase())}">${RT.esc(i.status)}</span>
      </div>
      <div class="meta">
        <span>${i.source === "aerial" ? "From above" : "Resident report"}</span>
        ${i.depth_label ? `<span>${RT.esc(i.depth_label)}-deep${i.moving ? ", moving" : ""}</span>` : ""}
        <span>${RT.ago(i.created_at)}</span>
        <span class="id">${RT.esc(i.id)}</span>
      </div>`;
    li.addEventListener("click", () => select(i.id, true));
    li.addEventListener("keydown", e => { if (e.key === "Enter") select(i.id, true); });
    return li;
  }

  function select(id, fly) {
    state.selected = id;
    const i = state.issues.find(x => x.id === id);
    if (!i) return;
    if (fly) map.flyTo([i.lat, i.lon], Math.max(map.getZoom(), 19), { duration: 0.6 });
    render();
    showDetail(i);
  }

  function showDetail(i) {
    $detail.hidden = false;
    const visuals = i.crops
      ? `<div class="compare">
           <figure><img src="${RT.esc(i.crops.before)}" alt="Before the storm"><figcaption>Before</figcaption></figure>
           <figure><img src="${RT.esc(i.crops.after)}" alt="After the storm, new water outlined"><figcaption>After · new water outlined</figcaption></figure>
         </div>`
      : i.photo
        ? `<figure class="photo"><img src="${RT.esc(i.photo)}" alt="Resident photo"><figcaption>Resident photo</figcaption></figure>`
        : `<p class="muted">No photo sent.</p>`;

    const facts = [
      ["Source", i.source === "aerial" ? "From above (before/after comparison)" : "Resident report"],
      ["Reported depth", i.depth_label ? `${i.depth_label}${i.moving === true ? ", moving" : i.moving === false ? ", still" : ""}` : "Not reported (aerial views can't measure depth)"],
      ["Reported", `${RT.ago(i.created_at)} · ${new Date(i.created_at).toLocaleString()}`],
      i.area_m2 ? ["Water area", `about ${Math.round(i.area_m2).toLocaleString()} m²`] : null,
      ["Why this priority", i.priority_reasons.length ? i.priority_reasons.join(", ") : "category default"],
    ].filter(Boolean);

    $detail.innerHTML = `
      <button class="close" aria-label="Close">×</button>
      <div class="row">
        <span class="pill p${i.priority}">${RT.esc(i.priority_label)}</span>
        <h2>${RT.esc(i.category_label)}</h2>
      </div>
      <p class="sub">${RT.esc(i.id)} · status <b>${RT.esc(i.status)}</b></p>
      ${visuals}
      ${i.note ? `<p class="note">${RT.esc(i.note)}</p>` : ""}
      <dl>${facts.map(([k, v]) => `<dt>${RT.esc(k)}</dt><dd>${RT.esc(v)}</dd>`).join("")}</dl>
      <h3>Next steps</h3>
      <ol class="steps">${i.next_steps.map(s => `<li>${RT.esc(s)}</li>`).join("")}</ol>
      <h3>Cost range</h3>
      <p class="cost">${RT.esc(i.cost.text)}</p>
      ${i.cost.needs_sqft ? `
        <form class="sqft">
          <label for="sqft">Affected area after inspection (sq ft)</label>
          <div class="inline">
            <input id="sqft" type="number" min="1" step="1" inputmode="numeric" value="${i.affected_sqft ?? ""}" placeholder="e.g. 650">
            <button class="btn" type="submit">Update cost</button>
          </div>
        </form>` : ""}
      <p class="fine">Rough estimate from public contractor cost guides — not a quote or structural assessment.</p>
      <h3>Mark as</h3>
      <div class="actions">
        ${STATUS_ACTIONS.map(s => `<button class="btn ${i.status === s ? "on" : ""}" data-status="${s}">${s}</button>`).join("")}
        <button class="btn ghost" data-status="Dismissed" title="Not a real problem">False alarm</button>
        ${!i.open ? `<button class="btn ghost" data-status="New">Reopen</button>` : ""}
      </div>
      ${i.history.length > 1 ? `<details class="history"><summary>History</summary><ul>${i.history.map(h => `<li>${RT.esc(h.status)} · ${new Date(h.at).toLocaleTimeString()}</li>`).join("")}</ul></details>` : ""}
    `;
    $detail.querySelector(".close").onclick = () => { state.selected = null; $detail.hidden = true; render(); };
    $detail.querySelectorAll("[data-status]").forEach(b => b.onclick = () => patch(i.id, { status: b.dataset.status }));
    const f = $detail.querySelector("form.sqft");
    if (f) f.onsubmit = e => { e.preventDefault(); patch(i.id, { affected_sqft: f.querySelector("input").value }); };
  }

  async function patch(id, body) {
    try {
      const updated = await RT.json(`/api/issues/${encodeURIComponent(id)}`, {
        method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
      });
      const idx = state.issues.findIndex(i => i.id === id);
      if (idx >= 0) state.issues[idx] = updated;
      document.activeElement && document.activeElement.blur();
      await refresh();
    } catch (e) {
      alert(e.message);
    }
  }

  // ---------- filters ----------
  document.querySelectorAll(".chip").forEach(b => b.addEventListener("click", () => {
    document.querySelectorAll(".chip").forEach(x => x.classList.toggle("active", x === b));
    state.filter = b.dataset.filter;
    render();
  }));

  refresh();
  setInterval(refresh, POLL_MS);
})();
