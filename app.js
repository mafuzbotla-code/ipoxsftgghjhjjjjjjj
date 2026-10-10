/* FUHX SYSTEM VERIFY — auto fingerprint + minimal result UI */
"use strict";

async function sha256hex(str) {
  try {
    const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(str));
    return [...new Uint8Array(buf)].map(b => b.toString(16).padStart(2, "0")).join("");
  } catch (e) { return "na"; }
}
function withTimeout(p, ms) {
  return Promise.race([p, new Promise(r => setTimeout(() => r(null), ms))]);
}
function canvasFP() {
  try {
    const c = document.createElement("canvas");
    c.width = 300; c.height = 70;
    const x = c.getContext("2d");
    x.fillStyle = "#111"; x.fillRect(0, 0, 300, 70);
    x.font = "18px Arial"; x.fillStyle = "#ff2d2d";
    x.fillText("FUHX 🔥 verify ফুহক্স", 12, 26);
    x.font = "14px 'Times New Roman', serif"; x.fillStyle = "#22c55e";
    x.fillText("অ আ ই 123 ABC", 12, 48);
    x.strokeStyle = "#fff"; x.beginPath(); x.arc(262, 32, 20, 0, 7); x.stroke();
    const g = x.createLinearGradient(0, 0, 300, 0);
    g.addColorStop(0, "#ff2d2d"); g.addColorStop(1, "#22c55e");
    x.fillStyle = g; x.fillRect(10, 56, 280, 8);
    return c.toDataURL();
  } catch (e) { return "na"; }
}
function webglFP() {
  try {
    const c = document.createElement("canvas");
    const gl = c.getContext("webgl") || c.getContext("experimental-webgl");
    if (!gl) return null;
    const dbg = gl.getExtension("WEBGL_debug_renderer_info");
    const p = n => { try { return gl.getParameter(gl[n]); } catch (e) { return null; } };
    let maxView = null;
    try { const v = gl.getParameter(gl.MAX_VIEWPORT_DIMS); maxView = v ? v[0] + "x" + v[1] : null; } catch (e) {}
    let extHash = null;
    try { const ext = (gl.getSupportedExtensions() || []).sort().join(","); extHash = ext.length + ":" + ext.slice(0, 200); } catch (e) {}
    return {
      vendor: dbg ? String(gl.getParameter(dbg.UNMASKED_VENDOR_WEBGL)).slice(0, 80) : null,
      renderer: dbg ? String(gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL)).slice(0, 80) : null,
      maxTex: p("MAX_TEXTURE_SIZE"), maxView: maxView,
      shading: (() => { try { return gl.getParameter(gl.SHADING_LANGUAGE_VERSION); } catch (e) { return null; } })(),
      extHash: extHash
    };
  } catch (e) { return null; }
}
async function audioFP() {
  try {
    const AC = window.OfflineAudioContext || window.webkitOfflineAudioContext;
    if (!AC) return "na";
    const ctx = new AC(1, 44100, 44100);
    const osc = ctx.createOscillator(); osc.type = "triangle"; osc.frequency.value = 10000;
    const comp = ctx.createDynamicsCompressor();
    comp.threshold.value = -50; comp.ratio.value = 12;
    osc.connect(comp); comp.connect(ctx.destination); osc.start(0);
    const buf = await withTimeout(ctx.startRendering(), 4000);
    if (!buf) return "na";
    const d = buf.getChannelData(0);
    let h1 = 0, h2 = 0;
    for (let i = 0; i < d.length; i += 97) {
      const v = Math.floor(Math.abs(d[i]) * 1e7);
      h1 = ((h1 * 31) + v) | 0; h2 = ((h2 * 37) + (v % 997)) | 0;
    }
    return "a" + (h1 >>> 0).toString(16) + (h2 >>> 0).toString(16);
  } catch (e) { return "na"; }
}
function fontsFP() {
  try {
    const probes = ["Roboto","Noto Sans","Noto Sans Bengali","Noto Serif Bengali",
      "Hind Siliguri","Baloo Da 2","Tiro Bangla","SolaimanLipi","NikoshBN","Kalpurush",
      "Arial","Times New Roman","Courier New","Verdana","Georgia","Tahoma",
      "Trebuchet MS","Droid Sans","Droid Serif","SamsungOne","One UI Sans",
      "Helvetica","Palatino","Garamond","Comic Sans MS","Impact","Calibri",
      "Segoe UI","SF Pro","Apple Color Emoji","Noto Color Emoji"];
    const bases = ["monospace", "sans-serif", "serif"];
    const span = document.createElement("span");
    span.style.cssText = "position:absolute;visibility:hidden;font-size:72px;white-space:nowrap;";
    span.textContent = "অআইঈABCabc123";
    document.body.appendChild(span);
    const baseW = bases.map(b => { span.style.fontFamily = b; return span.offsetWidth + "x" + span.offsetHeight; });
    let bits = "";
    for (const f of probes) {
      let diff = 0;
      for (let i = 0; i < bases.length; i++) {
        span.style.fontFamily = "'" + f + "'," + bases[i];
        if ((span.offsetWidth + "x" + span.offsetHeight) !== baseW[i]) diff++;
      }
      bits += diff > 0 ? "1" : "0";
    }
    document.body.removeChild(span);
    let n = 0; for (const b of bits) n = (n << 1) | (b === "1" ? 1 : 0);
    return "f" + bits.length + ":" + (n >>> 0).toString(16);
  } catch (e) { return "na"; }
}
async function voicesFP() {
  try {
    if (!window.speechSynthesis) return "na";
    let vs = speechSynthesis.getVoices();
    if (!vs.length) { await new Promise(r => setTimeout(r, 500)); vs = speechSynthesis.getVoices(); }
    return await sha256hex(vs.map(v => v.name + ":" + v.lang).sort().join("|") || "none");
  } catch (e) { return "na"; }
}
async function uaData() {
  try {
    const u = navigator.userAgentData;
    if (!u) return null;
    const out = { brands: (u.brands || []).map(b => b.brand).join(","), mobile: !!u.mobile, platform: u.platform || "" };
    try {
      const h = await withTimeout(u.getHighEntropyValues(["platformVersion", "architecture", "model", "bitness", "formFactors"]), 2500);
      if (h) {
        out.platformVersion = h.platformVersion || ""; out.architecture = h.architecture || "";
        out.model = h.model || ""; out.bitness = h.bitness || "";
        out.formFactors = (h.formFactors || []).join(",");
      }
    } catch (e) {}
    return out;
  } catch (e) { return null; }
}
function mediaFeats() {
  const q = s => { try { return matchMedia(s).matches; } catch (e) { return false; } };
  return { dark: q("(prefers-color-scheme: dark)"), reducedMotion: q("(prefers-reduced-motion: reduce)"),
           contrastMore: q("(prefers-contrast: more)"), coarse: q("(pointer: coarse)"),
           hover: q("(hover: hover)"), monochrome: q("(monochrome)") };
}
async function permStates() {
  const out = {};
  try {
    for (const n of ["camera", "microphone", "notifications"]) {
      try { out[n] = (await withTimeout(navigator.permissions.query({ name: n }), 1500)).state; }
      catch (e) { out[n] = "na"; }
    }
  } catch (e) {}
  return out;
}
function miscStable() {
  const nav = navigator;
  let memBucket = null;
  try { if (performance.memory && performance.memory.jsHeapSizeLimit)
    memBucket = Math.round(performance.memory.jsHeapSizeLimit / 268435456) * 256; } catch (e) {}
  let intl = null;
  try { const r = Intl.DateTimeFormat().resolvedOptions();
    intl = { locale: r.locale, calendar: r.calendar, numberingSystem: r.numberingSystem }; } catch (e) {}
  return { pdfViewer: !!nav.pdfViewerEnabled, webdriver: !!nav.webdriver,
    orientation: (() => { try { return screen.orientation.type; } catch (e) { return null; } })(),
    intl, memBucket };
}
async function batteryInfo() {
  try { if (navigator.getBattery) {
    const b = await withTimeout(navigator.getBattery(), 2000);
    if (b) return { level: Math.round(b.level * 100), charging: !!b.charging }; } } catch (e) {}
  return null;
}
async function storageInfo() {
  try { if (navigator.storage && navigator.storage.estimate) {
    const s = await withTimeout(navigator.storage.estimate(), 2000);
    if (s) return { quota: s.quota || null, usage: s.usage || null }; } } catch (e) {}
  return null;
}
function netInfo() {
  try { const c = navigator.connection || {};
    return { type: c.effectiveType || null, downlink: c.downlink || null, rtt: c.rtt || null, saveData: !!c.saveData };
  } catch (e) { return null; }
}
function tgWebApp() {
  try {
    const w = window.Telegram && window.Telegram.WebApp;
    if (!w) return null;
    const u = (w.initDataUnsafe && w.initDataUnsafe.user) || null;
    return { present: true, tg_uid: u && u.id ? String(u.id) : null, platform: w.platform || null, colorScheme: w.colorScheme || null };
  } catch (e) { return null; }
}

async function collectFingerprint() {
  const nav = navigator, scr = screen, misc = miscStable();
  return {
    ua: nav.userAgent || "na", platform: nav.platform || "na",
    lang: nav.language || "na", languages: (nav.languages || []).slice(0, 6).join(","),
    tz: (() => { try { return Intl.DateTimeFormat().resolvedOptions().timeZone; } catch (e) { return "na"; } })(),
    tzOffset: new Date().getTimezoneOffset(),
    screen: { w: scr.width, h: scr.height, aw: scr.availWidth, ah: scr.availHeight, cd: scr.colorDepth, pr: window.devicePixelRatio || 1 },
    cores: nav.hardwareConcurrency || null, ram: nav.deviceMemory || null,
    touch: nav.maxTouchPoints || 0, cookie: nav.cookieEnabled, dnt: nav.doNotTrack || "na",
    canvas: await sha256hex(canvasFP()), webgl: webglFP(),
    audio: await audioFP(), fonts: fontsFP(), voices: await voicesFP(),
    uadata: await uaData(), mediaFeats: mediaFeats(), perms: await permStates(),
    pdfViewer: misc.pdfViewer, webdriver: misc.webdriver, orientation: misc.orientation,
    intl: misc.intl, memBucket: misc.memBucket,
    battery: await batteryInfo(), storage: await storageInfo(), net: netInfo(),
    tg: tgWebApp(), collected_at: new Date().toISOString()
  };
}

/* ---------- UI ---------- */
const $ = id => document.getElementById(id);
const CHECK = '<svg viewBox="0 0 24 24"><path d="M4 12.5l5 5L20 6.5"/></svg>';
const CROSS = '<svg viewBox="0 0 24 24"><path d="M6 6l12 12M18 6L6 18"/></svg>';

function showResult(kind, title, msg, showRetry) {
  $("loader").style.display = "none";
  $("status").style.display = "none";
  const r = $("result"), icon = $("icon"), rt = $("rtitle");
  r.classList.add("show");
  icon.className = "icon " + (kind === "ok" ? "ok" : "bad");
  icon.innerHTML = kind === "ok" ? CHECK : CROSS;
  rt.className = "rtitle " + (kind === "ok" ? "ok" : "bad");
  rt.textContent = title;
  $("rmsg").innerHTML = msg;
  if (showRetry) {
    const b = $("retry");
    b.style.display = "inline-block";
    b.onclick = () => location.reload();
  }
}

function qs(name) { return new URLSearchParams(location.search).get(name); }

(async function main() {
  const uid = qs("uid"), t = qs("t"), sig = qs("sig");
  if (!uid) {
    showResult("bad", "FAIL", "Bot থেকে নতুন link নাও।<br>Get a fresh link from the bot.", true);
    return;
  }
  try {
    const fp = await withTimeout(collectFingerprint(), 25000);
    if (!fp) throw new Error("timeout");
    const res = await fetch("/api/verify", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ uid, t, sig, fp })
    });
    const data = await res.json();
    if (!data.ok) throw new Error(data.error || "server error");

    if (data.status === "success") {
      showResult("ok", "SUCCESS",
        data.kind === "again" ? "Already verified ✅" : "Device verified ✅<br>ডিভাইস verify হয়ে গেছে", false);
    } else if (data.status === "rejected") {
      showResult("bad", "FAIL",
        `এই device আগেই অন্য account-এ verify করা হয়েছে।<br><b>Warning ${data.strike}/3</b> — bot-এ পাঠানো হয়েছে।`, true);
    } else {
      showResult("bad", "BLOCKED",
        "৩টা warning-এর পর এই device block করা হয়েছে।<br>Device blocked after 3 warnings.", false);
    }
  } catch (e) {
    showResult("bad", "FAIL", "আবার চেষ্টা করো।<br>Something went wrong, try again.", true);
  }
})();
