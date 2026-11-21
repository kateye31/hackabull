// Resident report form: pin + what you see + depth + photo -> POST /api/reports
(() => {
  const form = document.getElementById("form");
  const $err = document.getElementById("error");
  const $pinlabel = document.getElementById("pinlabel");
  let pin = null;

  const map = L.map("pinmap").setView([27.9614, -82.458], 17);
  RT.baseLayer().addTo(map);
  RT.json("/api/scenes").then(s => {
    if (!s.length) return;
    L.imageOverlay(s[0].images.after, s[0].bounds, { opacity: 0.9 }).addTo(map);
    map.fitBounds(s[0].bounds);
  }).catch(() => {});

  function setPin(latlng) {
    if (pin) pin.setLatLng(latlng);
    else pin = L.marker(latlng, { draggable: true }).addTo(map).on("dragend", () => setPin(pin.getLatLng()));
    $pinlabel.textContent = `Pin at ${latlng.lat.toFixed(5)}, ${latlng.lng.toFixed(5)}`;
  }
  map.on("click", e => setPin(e.latlng));

  document.getElementById("locate").onclick = () => {
    if (!navigator.geolocation) return showError("Location isn't available on this device. Tap the map instead.");
    $pinlabel.textContent = "Finding you…";
    navigator.geolocation.getCurrentPosition(
      p => { const ll = L.latLng(p.coords.latitude, p.coords.longitude); setPin(ll); map.setView(ll, 18); },
      () => { $pinlabel.textContent = "Couldn't get your location. Tap the map instead."; },
      { enableHighAccuracy: true, timeout: 8000 });
  };

  const photo = document.getElementById("photo");
  const preview = document.getElementById("preview");
  photo.onchange = () => {
    const f = photo.files[0];
    preview.hidden = !f;
    if (f) preview.src = URL.createObjectURL(f);
  };

  function showError(msg) { $err.textContent = msg; $err.hidden = false; }

  form.onsubmit = async e => {
    e.preventDefault();
    $err.hidden = true;
    if (!pin) return showError("Drop a pin on the map first.");
    if (!form.category.value) return showError("Pick what you see.");
    const fd = new FormData(form);
    const ll = pin.getLatLng();
    fd.set("lat", ll.lat);
    fd.set("lon", ll.lng);
    const btn = document.getElementById("submit");
    btn.disabled = true;
    btn.textContent = "Sending…";
    try {
      const r = await RT.json("/api/reports", { method: "POST", body: fd });
      document.getElementById("doneid").textContent = r.id;
      document.getElementById("donecat").textContent = r.category_label.toLowerCase();
      document.getElementById("donepri").textContent = r.priority_label.toLowerCase();
      form.hidden = true;
      document.getElementById("done").hidden = false;
      window.scrollTo(0, 0);
    } catch (err) {
      showError(err.message);
    } finally {
      btn.disabled = false;
      btn.textContent = "Send report";
    }
  };

  document.getElementById("again").onclick = () => {
    form.reset();
    preview.hidden = true;
    if (pin) { map.removeLayer(pin); pin = null; }
    $pinlabel.textContent = "Tap the map to drop a pin.";
    form.hidden = false;
    document.getElementById("done").hidden = true;
  };
})();
