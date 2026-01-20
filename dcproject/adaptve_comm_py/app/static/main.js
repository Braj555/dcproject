let ws = null;

function $(id){ return document.getElementById(id); }
function log(msg){ const el = $("log"); if (el) el.textContent = msg + "\n" + el.textContent; }

function truncateBase64(b64, maxChars=260){
  if (!b64) return "";
  return b64.length > maxChars ? (b64.slice(0, maxChars) + " … ("+b64.length+" chars)") : b64;
}

function setStatus(text, online){
  const el = $("status");
  if (!el) return;
  el.textContent = text;
  if (online === undefined) return;
  el.classList.toggle("online", !!online);
  el.classList.toggle("offline", !online);
}

// --------- Constellation drawing ----------
function drawConstellation(canvasId, points, scheme){
  const cv = $(canvasId);
  if (!cv || !points) return;
  const ctx = cv.getContext("2d");
  const W = cv.width, H = cv.height;
  ctx.clearRect(0,0,W,H);

  // axes
  ctx.strokeStyle = "#334155";
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(0, H/2); ctx.lineTo(W, H/2);
  ctx.moveTo(W/2, 0); ctx.lineTo(W/2, H);
  ctx.stroke();

  // scale – assume symbols roughly in [-1.5, +1.5]
  const minV = -1.6, maxV = +1.6;
  const sx = W/(maxV-minV), sy = H/(maxV-minV);

  // points
  ctx.fillStyle = "#93c5fd";
  const r = 2;
  for (const p of points){
    const i = Array.isArray(p) ? p[0] : p.i;
    const q = Array.isArray(p) ? p[1] : p.q;
    const x = (i - minV)*sx;
    const y = H - (q - minV)*sy;
    ctx.beginPath();
    ctx.arc(x, y, r, 0, Math.PI*2);
    ctx.fill();
  }

  // tiny label
  ctx.fillStyle = "#94a3b8";
  ctx.font = "12px sans-serif";
  ctx.fillText(scheme || "", 6, 14);
}

function drawWaveform(canvasId, series){
  const cv = $(canvasId);
  if (!cv || !series) return;
  const ctx = cv.getContext("2d");
  const W = cv.width, H = cv.height;
  ctx.clearRect(0,0,W,H);
  const I = series.I || [];
  const Q = series.Q || [];
  if (!I.length && !Q.length) return;
  const maxAbs = Math.max(1e-3, ...I.map(v=>Math.abs(v)), ...Q.map(v=>Math.abs(v)));
  const scaleY = (H/2-6)/maxAbs;

  ctx.strokeStyle = "#334155";
  ctx.beginPath();
  ctx.moveTo(0, H/2);
  ctx.lineTo(W, H/2);
  ctx.stroke();

  const drawSeries = (arr, color) => {
    if (!arr.length) return;
    ctx.strokeStyle = color;
    ctx.beginPath();
    arr.forEach((val, idx) => {
      const x = (idx/(arr.length-1 || 1)) * W;
      const y = H/2 - val*scaleY;
      if (idx === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.stroke();
  };

  drawSeries(I, "#93c5fd"); // I in blue
  drawSeries(Q, "#f472b6"); // Q in pink
}

function drawBitChart(canvasId, raw, clean, noisy){
  const cv = $(canvasId);
  if (!cv) return;
  const ctx = cv.getContext("2d");
  const W = cv.width, H = cv.height;
  ctx.clearRect(0,0,W,H);

  ctx.strokeStyle = "#334155";
  ctx.beginPath();
  ctx.moveTo(0, H*0.25);
  ctx.lineTo(W, H*0.25);
  ctx.moveTo(0, H*0.75);
  ctx.lineTo(W, H*0.75);
  ctx.stroke();

  const drawSeries = (arr, color) => {
    if (!arr || !arr.length) return;
    ctx.strokeStyle = color;
    ctx.beginPath();
    arr.forEach((bit, idx) => {
      const x = (idx/(arr.length-1 || 1)) * W;
      const y = bit ? H*0.25 : H*0.75;
      if (idx === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.stroke();
  };

  drawSeries(raw, "#94a3b8");
  drawSeries(clean, "#38bdf8");
  drawSeries(noisy, "#f472b6");

  ctx.fillStyle = "#94a3b8";
  ctx.font = "10px sans-serif";
  ctx.fillText("raw", 6, 12);
  ctx.fillStyle = "#38bdf8";
  ctx.fillText("clean", 50, 12);
  ctx.fillStyle = "#f472b6";
  ctx.fillText("noisy", 110, 12);
}

function connect(room, role){
  const url = (location.protocol === "https:" ? "wss://" : "ws://") + location.host + "/ws";
  ws = new WebSocket(url);
  ws.onopen = () => {
    ws.send(JSON.stringify({ type: "join", room, role }));
    setStatus(`Connected (${role.toUpperCase()})`, true);
  };
  ws.onmessage = async (ev) => {
    const msg = JSON.parse(ev.data);

    if (msg.type === "joined") {
      if ($("snr_val") && typeof msg.snr !== "undefined") $("snr_val").textContent = `${msg.snr} dB`;
      log(`Joined room ${msg.room} as ${msg.role}`);
    }
    if (msg.type === "snr_update") {
      if ($("snr_val")) $("snr_val").textContent = `${msg.snr} dB`;
      log(`SNR update: ${msg.snr} dB`);
    }
    if (msg.type === "tx_ack") {
      log(msg.info);
    }

    // ------- RX receives a frame -------
    if (msg.type === "frame_rx") {
      const pwd = $("pwd") ? $("pwd").value : "";

      // Fill encrypted previews (RX)
      if ($("enc_scheme")) $("enc_scheme").textContent = msg.scheme || "-";
      if ($("enc_snr")) $("enc_snr").textContent = `SNR: ${msg.snr?.toFixed?.(1) ?? "–"} dB`;
      if ($("enc_ber")) $("enc_ber").textContent = `BER: ${Number(msg.ber).toExponential(2)}`;
      if ($("enc_fec")) $("enc_fec").textContent = `FEC: ${msg.fec || "none"}`;

      if ($("enc_raw"))   $("enc_raw").textContent   = truncateBase64(msg.cipher_raw);
      if ($("enc_clean")) $("enc_clean").textContent = truncateBase64(msg.cipher_clean);
      if ($("enc_noisy")) $("enc_noisy").textContent = truncateBase64(msg.cipher);

      // NEW: bitstreams on RX page
      if ($("enc_bits_raw"))   $("enc_bits_raw").textContent   = msg.bits_raw   || "";
      if ($("enc_bits_clean")) $("enc_bits_clean").textContent = msg.bits_clean || "";
      if ($("enc_bits_noisy")) $("enc_bits_noisy").textContent = msg.bits_noisy || "";

      // Draw RX constellations
      drawConstellation("rx_const_clean", msg.const_clean, msg.scheme);
      drawConstellation("rx_const_noisy", msg.const_noisy, msg.scheme);

      log(`RX frame via ${msg.scheme} @SNR=${msg.snr}dB (BER~${Number(msg.ber).toExponential(2)})`);

      // Ask server to FEC-decode (if present) and decrypt (Python-side)
      ws.send(JSON.stringify({
        type: "rx_decrypt",
        password: pwd,
        kind: msg.kind,
        iv: msg.iv,
        salt: msg.salt,
        cipher: msg.cipher,
        fec: msg.fec || null
      }));
    }

    // ------- TX preview for the last sent frame -------
    if (msg.type === "frame_preview") {
      if ($("tx_scheme")) $("tx_scheme").textContent = msg.scheme || "-";
      if ($("tx_snr")) $("tx_snr").textContent = `SNR: ${msg.snr?.toFixed?.(1) ?? "–"} dB`;
      if ($("tx_ber")) $("tx_ber").textContent = `BER: ${Number(msg.ber).toExponential(2)}`;
      if ($("tx_fec")) $("tx_fec").textContent = `FEC: ${msg.fec || "none"}`;

      if ($("tx_raw"))   $("tx_raw").textContent   = truncateBase64(msg.cipher_raw);
      if ($("tx_clean")) $("tx_clean").textContent = truncateBase64(msg.cipher_clean);
      if ($("tx_noisy")) $("tx_noisy").textContent = truncateBase64(msg.cipher);

      // NEW: bitstreams on TX page
      if ($("tx_bits_raw"))   $("tx_bits_raw").textContent   = msg.bits_raw   || "";
      if ($("tx_bits_clean")) $("tx_bits_clean").textContent = msg.bits_clean || "";
      if ($("tx_bits_noisy")) $("tx_bits_noisy").textContent = msg.bits_noisy || "";

      drawConstellation("tx_const_clean", msg.const_clean, msg.scheme);
      drawConstellation("tx_const_noisy", msg.const_noisy, msg.scheme);
      drawWaveform("tx_wave_clean", msg.wave_clean);
      drawWaveform("tx_wave_noisy", msg.wave_noisy);
      drawBitChart("tx_bits_plot", msg.bits_plot_raw, msg.bits_plot_clean, msg.bits_plot_noisy);
    }

    if (msg.type === "rx_result") {
      if (!msg.ok) { log("Decrypt: ❌ AUTH FAIL (too noisy?)"); return; }
      if (msg.kind === "text") {
        log("Decrypt: ✅ TEXT → " + msg.text);
      } else if (msg.kind === "file") {
        const a = document.createElement("a");
        a.textContent = "Download received file";
        a.download = "received.bin";
        a.href = "data:application/octet-stream;base64," + msg.file_b64;
        const d = $("downloads");
        if (d) d.prepend(a);
        log("Decrypt: ✅ FILE ready to download");
      }
    }
  };
  ws.onclose = () => setStatus("Disconnected", false);
}

function asBase64(file){
  return new Promise((res, rej) => {
    const fr = new FileReader();
    fr.onload = () => res(fr.result.split(",")[1]);
    fr.onerror = rej;
    fr.readAsDataURL(file);
  });
}

// ===== TX page bindings =====
if (window.TX_PAGE){
  $("join").onclick = () => connect($("room").value, "tx");
  $("snr").oninput = () => {
    const v = Number($("snr").value);
    $("snr_val").textContent = `${v} dB`;
    ws?.send(JSON.stringify({ type:"set_snr", snr:v }));
  };
  $("send_text").onclick = () => {
    const text = $("msg").value.trim();
    if (!text) return;
    ws?.send(JSON.stringify({ type:"send_text", text, password:$("pwd").value }));
    $("msg").value = "";
  };
  $("send_files").onclick = async () => {
    const files = $("files").files;
    if (!files || !files.length) return;
    for (let f of files){
      const b64 = await asBase64(f);
      ws?.send(JSON.stringify({ type:"send_file", name:f.name, content_b64:b64, password:$("pwd").value }));
    }
  };
}

// ===== RX page bindings =====
if (window.RX_PAGE){
  $("join").onclick = () => connect($("room").value, "rx");
}
