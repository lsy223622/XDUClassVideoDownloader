const state = {
  appMessage: "欢迎使用！如有问题请联系作者。",
  automationCourses: [],
  subtitles: [],
  activeVideos: [],
  subtitleDriver: null,
  syncing: false,
  desiredPlaying: false,
  syncTimer: null,
  syncSource: null,
  pptOffset: 0,
  playbackRate: 1,
  subtitleOffset: 0,
  subtitleFontSize: 18,
  subtitleBold: false,
  audioTrack: null,
  lastAudioTrack: null,
  progressDragging: false,
  suppressMediaEventsUntil: 0,
  outputSource: null,
  terminalLines: [""],
  terminalRow: 0,
  terminalCol: 0,
  pendingAnsi: "",
  programmaticSeekUntil: new WeakMap(),
  programmaticPlayUntil: new WeakMap(),
  lastPlayAttempt: new WeakMap(),
  qrTimer: null,
  initialSetupRequired: false,
  qrJobId: null,
  batchUidTouched: false,
  webuiPasswordEnabled: false,
  webuiPasswordChangeAllowed: true,
  viewerControlsReady: false,
  videoLayoutObserver: null,
};

const $ = (id) => document.getElementById(id);
const $$ = (selector, scope = document) => Array.from(scope.querySelectorAll(selector));

function on(id, eventName, handler, options) {
  $(id).addEventListener(eventName, handler, options);
}

function setHidden(target, hidden) {
  const el = typeof target === "string" ? $(target) : target;
  el?.classList.toggle("hidden", hidden);
}

function setText(id, text) {
  $(id).textContent = text;
}

function setStatus(text, kind = "") {
  const el = $("globalStatus");
  el.textContent = text;
  el.dataset.kind = kind;
}

function appendOutput(text) {
  const out = $("terminalOutput");
  if (out.textContent === "等待任务启动...") out.textContent = "";
  const value = state.pendingAnsi + String(text);
  state.pendingAnsi = "";
  for (let index = 0; index < value.length; index += 1) {
    const char = value[index];
    const ansi = consumeAnsiSequence(value, index);
    if (ansi.incomplete) {
      state.pendingAnsi = value.slice(index);
      break;
    }
    if (ansi.length > 0) {
      index += ansi.length - 1;
      continue;
    }
    if (char === "\r") {
      state.terminalCol = 0;
    } else if (char === "\n") {
      state.terminalRow += 1;
      state.terminalCol = 0;
      ensureTerminalLine();
    } else if (char === "\b") {
      state.terminalCol = Math.max(0, state.terminalCol - 1);
    } else {
      writeTerminalChar(char);
    }
  }
  renderOutput();
  out.scrollTop = out.scrollHeight;
}

function consumeAnsiSequence(value, index) {
  const esc = value[index];
  if (esc !== "\x1b" && esc !== "\uFFFD") return { length: 0, incomplete: false };
  if (index + 1 >= value.length) return { length: 0, incomplete: true };
  if (value[index + 1] !== "[") return { length: 1, incomplete: false };
  let end = index + 2;
  while (end < value.length && !/[\x40-\x7E]/.test(value[end])) end += 1;
  if (end >= value.length) return { length: 0, incomplete: true };
  const command = value[end];
  const params = value.slice(index + 2, end);
  const numbers = params
    .replace(/^\?/, "")
    .split(";")
    .map((part) => Number.parseInt(part, 10));
  const amount = numbers[0] || 1;
  if (command === "A" || command === "F") {
    state.terminalRow = Math.max(0, state.terminalRow - amount);
    if (command === "F") state.terminalCol = 0;
    ensureTerminalLine();
  } else if (command === "B" || command === "E") {
    state.terminalRow += amount;
    if (command === "E") state.terminalCol = 0;
    ensureTerminalLine();
  } else if (command === "K") {
    eraseTerminalLine(params);
  } else if (command === "G") {
    state.terminalCol = Math.max(0, amount - 1);
  } else if (command === "C") {
    state.terminalCol += amount;
  } else if (command === "D") {
    state.terminalCol = Math.max(0, state.terminalCol - amount);
  } else if (command === "H" || command === "f") {
    state.terminalRow = Math.max(0, (numbers[0] || 1) - 1);
    state.terminalCol = Math.max(0, (numbers[1] || 1) - 1);
    ensureTerminalLine();
  } else if (command === "J") {
    eraseTerminalScreen(amount);
  }
  return { length: end - index + 1, incomplete: false };
}

function ensureTerminalLine() {
  while (state.terminalLines.length <= state.terminalRow) state.terminalLines.push("");
}

function writeTerminalChar(char) {
  ensureTerminalLine();
  const line = state.terminalLines[state.terminalRow];
  const padded = line.padEnd(state.terminalCol, " ");
  state.terminalLines[state.terminalRow] = padded.slice(0, state.terminalCol) + char + padded.slice(state.terminalCol + 1);
  state.terminalCol += 1;
}

function eraseTerminalLine(params) {
  ensureTerminalLine();
  const mode = Number.parseInt(params.replace(/^\?/, ""), 10) || 0;
  const line = state.terminalLines[state.terminalRow];
  if (mode === 2) {
    state.terminalLines[state.terminalRow] = "";
    state.terminalCol = 0;
  } else if (mode === 1) {
    state.terminalLines[state.terminalRow] = " ".repeat(Math.min(state.terminalCol, line.length)) + line.slice(state.terminalCol);
  } else {
    state.terminalLines[state.terminalRow] = line.slice(0, state.terminalCol);
  }
}

function eraseTerminalScreen(mode) {
  if (mode === 2) {
    state.terminalLines = [""];
    state.terminalRow = 0;
    state.terminalCol = 0;
  } else if (mode === 1) {
    for (let row = 0; row < state.terminalRow; row += 1) state.terminalLines[row] = "";
    eraseTerminalLine("1");
  } else {
    eraseTerminalLine("0");
    for (let row = state.terminalRow + 1; row < state.terminalLines.length; row += 1) state.terminalLines[row] = "";
  }
}

function renderOutput() {
  let lines = state.terminalLines.slice(-1200);
  while (lines.length > 1 && lines[lines.length - 1].trim() === "") lines.pop();
  $("terminalOutput").textContent = lines.join("\n");
}

function resetOutput() {
  state.terminalLines = [""];
  state.terminalRow = 0;
  state.terminalCol = 0;
  state.pendingAnsi = "";
  $("terminalOutput").textContent = "";
}

function setStreamIndicator(status) {
  const el = $("streamIndicator");
  el.classList.toggle("streaming", status === "streaming");
  el.classList.toggle("broken", status === "broken");
}

async function apiJson(url, options = {}) {
  const res = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const data = await res.json();
  if (!res.ok || data.ok === false) {
    throw new Error(data.error || `请求失败: ${res.status}`);
  }
  return data;
}

function showAccessGate(message = "") {
  document.body.classList.remove("access-checking", "access-granted");
  document.body.classList.add("access-locked");
  setHidden("accessGate", false);
  setText("accessError", message);
  setHidden("accessError", !message);
  setTimeout(() => $("accessPassword")?.focus(), 0);
}

function showAppShell() {
  document.body.classList.remove("access-checking", "access-locked");
  document.body.classList.add("access-granted");
  setHidden("accessGate", true);
}

async function checkWebuiAccess() {
  try {
    const data = await apiJson("/api/webui/access/status");
    state.webuiPasswordEnabled = Boolean(data.enabled);
    updateWebuiPasswordState();
    if (data.unlocked) {
      showAppShell();
      await initializeApp();
    } else {
      showAccessGate();
    }
  } catch (err) {
    showAccessGate(err.message);
  }
}

async function submitAccessPassword(event) {
  event.preventDefault();
  setHidden("accessError", true);
  try {
    const data = await apiJson("/api/webui/access/login", {
      method: "POST",
      body: JSON.stringify({ password: $("accessPassword").value }),
    });
    if (data.unlocked) {
      $("accessPassword").value = "";
      showAppShell();
      await initializeApp();
    }
  } catch (err) {
    showAccessGate(err.message);
  }
}

function switchPage(pageName) {
  if (pageName !== "viewer") pauseAllVideos(false);
  if (pageName !== "settings") stopQrPolling(true);
  $$(".nav-item").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.page === pageName);
  });
  $$(".page").forEach((page) => page.classList.remove("active"));
  $(`${pageName}Page`).classList.add("active");
  setText("pageHint", state.appMessage);
}

async function loadAppInfo() {
  try {
    const data = await apiJson("/api/app/info");
    const version = data.version || "--";
    const message = data.message || "欢迎使用！如有问题请联系作者。检查更新失败。";
    state.appMessage = message;
    $("versionBadge").textContent = `v${version}`;
    $("pageHint").textContent = message;

    const notice = $("updateNotice");
    if (data.update_available && data.latest_version) {
      notice.textContent = `有更新版本${data.latest_version}，请点击这里前往下载页面`;
      notice.href = data.releases_url || "https://github.com/lsy223622/XDUClassVideoDownloader/releases";
      setHidden(notice, false);
    } else {
      notice.textContent = "";
      setHidden(notice, true);
    }
  } catch (error) {
    const message = "欢迎使用！如有问题请联系作者。检查更新失败。";
    state.appMessage = message;
    setText("pageHint", message);
    setText("versionBadge", "v--");
    setHidden("updateNotice", true);
  }
}

function renderAutomation(data) {
  if (data.defaults?.user_id && (!state.batchUidTouched || !$("batchUid").value.trim())) {
    $("batchUid").value = data.defaults.user_id;
  }
  if (!data.exists) {
    setHidden("automationMissing", false);
    setHidden("automationReady", true);
    if (data.defaults) {
      if (data.defaults.user_id && (!state.batchUidTouched || !$("batchUid").value.trim())) {
        $("batchUid").value = data.defaults.user_id;
      }
      $("batchYear").value = data.defaults.term_year || "";
      $("batchTerm").value = data.defaults.term_id || "1";
      $("batchInitVideoType").value = data.defaults.video_type || "both";
    }
    return;
  }
  setHidden("automationMissing", true);
  setHidden("automationReady", false);
  state.automationCourses = data.courses || [];
  if (data.defaults?.video_type) $("batchVideoType").value = data.defaults.video_type;
  const list = $("courseList");
  list.innerHTML = "";
  for (const course of state.automationCourses) {
    const row = document.createElement("label");
    row.className = "course-row";
    row.innerHTML = `
      <input type="checkbox" data-section="${course.section}" ${course.selected ? "checked" : ""}>
      <span>
        <span class="course-name">${escapeHtml(course.course_name || "未命名课程")}</span>
        <span class="course-meta">${escapeHtml(course.course_code || "")} · LiveID ${escapeHtml(course.live_id || "")}</span>
      </span>
      <span class="course-meta">${course.download === "yes" ? "配置: 下载" : "配置: 不下载"}</span>
    `;
    list.appendChild(row);
  }
}

async function loadAutomation() {
  setStatus("读取配置");
  try {
    const data = await apiJson("/api/automation/config");
    renderAutomation(data);
    setStatus("空闲");
  } catch (err) {
    appendOutput(`读取批量配置失败: ${err.message}\n`);
    setStatus("配置错误", "error");
  }
}

async function refreshAutomation() {
  setStatus("刷新课程");
  try {
    const data = await apiJson("/api/automation/config?refresh=1");
    renderAutomation(data);
    setStatus("空闲");
  } catch (err) {
    appendOutput(`刷新课程失败: ${err.message}\n`);
    setStatus("刷新失败", "error");
  }
}

async function initAutomation() {
  setStatus("扫描课程");
  setInitLoading(true);
  try {
    const data = await apiJson("/api/automation/config/init", {
      method: "POST",
      body: JSON.stringify({
        uid: $("batchUid").value.trim(),
        year: $("batchYear").value,
        term: $("batchTerm").value,
        video_type: $("batchInitVideoType").value,
      }),
    });
    renderAutomation(data);
    setStatus("空闲");
  } catch (err) {
    appendOutput(`生成 automation_config.ini 失败: ${err.message}\n`);
    setStatus("生成失败", "error");
  } finally {
    setInitLoading(false);
  }
}

function setInitLoading(loading) {
  $("initAutomation").disabled = loading;
  setHidden("initAutomationSpinner", !loading);
}

async function startDownload(payload) {
  resetOutput();
  setStreamIndicator("");
  setStatus("启动任务");
  try {
    const data = await apiJson("/api/download/start", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    connectDownloadStream(data.stream_url, true);
  } catch (err) {
    appendOutput(`启动失败: ${err.message}\n`);
    setStatus("启动失败", "error");
    setStreamIndicator("broken");
  }
}

function connectDownloadStream(streamUrl, resetOutput = false) {
  if (state.outputSource) state.outputSource.close();
  if (resetOutput) $("terminalOutput").textContent = "";
  setStatus("运行中", "running");
  setStreamIndicator("streaming");
  const source = new EventSource(streamUrl);
  state.outputSource = source;
  source.onmessage = (event) => {
    const item = JSON.parse(event.data);
    appendOutput(item.text || "");
  };
  source.addEventListener("done", (event) => {
    const item = JSON.parse(event.data);
    appendOutput(`\n任务结束：${item.status}\n`);
    setStatus(item.success ? "完成" : "失败", item.success ? "success" : "error");
    setStreamIndicator("");
    source.close();
    if (state.outputSource === source) state.outputSource = null;
    loadLibrary();
  });
  source.onerror = () => {
    appendOutput("\n输出流连接中断\n");
    source.close();
    if (state.outputSource === source) state.outputSource = null;
    setStatus("输出中断", "error");
    setStreamIndicator("broken");
  };
}

async function restoreActiveDownloadStream() {
  try {
    const data = await apiJson("/api/download/active");
    if (!data.active) return;
    appendOutput("检测到正在运行的下载任务，已恢复输出串流。\n");
    connectDownloadStream(data.stream_url, false);
  } catch (err) {
    appendOutput(`恢复下载输出失败: ${err.message}\n`);
  }
}

async function saveCourseSelection() {
  setStatus("保存选择");
  try {
    const data = await apiJson("/api/automation/config/selection", {
      method: "POST",
      body: JSON.stringify({
        selected_sections: selectedCourseSections(),
        video_type: $("batchVideoType").value,
      }),
    });
    renderAutomation(data);
    appendOutput("已保存当前课程选择到 automation_config.ini\n");
    setStatus("配置已保存", "success");
  } catch (err) {
    appendOutput(`保存课程选择失败: ${err.message}\n`);
    setStatus("保存失败", "error");
  }
}

function selectedCourseSections() {
  return $$("input[type=checkbox]:checked", $("courseList")).map((box) => box.dataset.section);
}

async function loadLibrary() {
  const list = $("libraryList");
  list.innerHTML = "正在扫描本地视频...";
  try {
    const data = await apiJson("/api/library");
    list.innerHTML = "";
    if (!data.courses.length) {
      list.innerHTML = '<div class="notice">未发现本地已下载视频。</div>';
      return;
    }
    for (const course of data.courses) {
      const wrap = document.createElement("div");
      wrap.className = "library-course";
      const title = document.createElement("button");
      title.className = "library-course-title";
      title.type = "button";
      title.textContent = course.title;
      title.addEventListener("click", () => wrap.classList.toggle("expanded"));
      const lessonList = document.createElement("div");
      lessonList.className = "lesson-list";
      wrap.appendChild(title);
      for (const item of course.items) {
        const btn = document.createElement("button");
        btn.className = "lesson-btn";
        btn.textContent = item.title;
        btn.addEventListener("click", () => selectLesson(btn, item));
        lessonList.appendChild(btn);
      }
      wrap.appendChild(lessonList);
      list.appendChild(wrap);
    }
  } catch (err) {
    list.innerHTML = `<div class="notice">扫描失败：${escapeHtml(err.message)}</div>`;
  }
}

function videoRatio(video) {
  const width = Number(video.videoWidth);
  const height = Number(video.videoHeight);
  if (width > 0 && height > 0) return width / height;
  return video.dataset.track === "pptVideo" ? 4 / 3 : 16 / 9;
}

function updateVideoLayout() {
  const grid = $("videoGrid");
  if (!grid) return;
  const cards = $$(".video-card", grid);
  if (!cards.length) return;

  const gridStyle = getComputedStyle(grid);
  const stacked = gridStyle.flexDirection === "column";
  const gap = Number.parseFloat(gridStyle.columnGap || gridStyle.gap) || 14;
  const availableWidth = Math.max(240, grid.clientWidth);
  const playerPanel = document.querySelector(".player-panel");
  const maximized = playerPanel?.classList.contains("maximized");
  const maxHeight = maximized ? Math.max(260, window.innerHeight - 280) : Math.min(460, Math.max(220, window.innerHeight * 0.52));
  const ratios = cards.map((card) => videoRatio(card.querySelector("video")));

  if (stacked || cards.length === 1) {
    cards.forEach((card, index) => {
      const ratio = ratios[index];
      const height = Math.max(120, availableWidth / ratio);
      card.style.width = "100%";
      const frame = card.querySelector(".video-frame");
      frame.style.width = "100%";
      frame.style.height = `${height.toFixed(3)}px`;
    });
    return;
  }

  const totalRatio = ratios.reduce((sum, ratio) => sum + ratio, 0);
  const usableWidth = Math.max(240, availableWidth - gap * (cards.length - 1));
  const rowHeight = Math.min(maxHeight, usableWidth / totalRatio);
  cards.forEach((card, index) => {
    const width = rowHeight * ratios[index];
    card.style.width = `${width.toFixed(3)}px`;
    const frame = card.querySelector(".video-frame");
    frame.style.width = "100%";
    frame.style.height = `${rowHeight.toFixed(3)}px`;
  });
}

function ensureVideoLayoutObserver() {
  if (state.videoLayoutObserver || typeof ResizeObserver === "undefined") return;
  state.videoLayoutObserver = new ResizeObserver(() => updateVideoLayout());
  state.videoLayoutObserver.observe($("videoGrid"));
  state.videoLayoutObserver.observe(document.querySelector(".player-panel"));
}

function resetViewerState() {
  state.activeVideos = [];
  state.subtitleDriver = null;
  state.syncSource = null;
  state.subtitles = [];
  state.desiredPlaying = false;
  state.audioTrack = null;
  state.lastAudioTrack = null;
  state.progressDragging = false;
  state.programmaticSeekUntil = new WeakMap();
  state.programmaticPlayUntil = new WeakMap();
  state.lastPlayAttempt = new WeakMap();
}

async function selectLesson(button, item) {
  $$(".lesson-btn").forEach((btn) => btn.classList.remove("active"));
  button.classList.add("active");
  setText("viewerTitle", item.title);
  const grid = $("videoGrid");
  grid.innerHTML = "";
  resetViewerState();
  stopSyncLoop();
  updatePlayerControls();

  const order = ["pptVideo", "teacherTrack"];
  const availableTracks = order.filter((track) => item.tracks[track]);
  grid.classList.toggle("single-track", availableTracks.length <= 1);
  for (const track of availableTracks) {
    const card = document.createElement("div");
    card.className = "video-card";
    card.innerHTML = `
      <div class="video-card-title">
        <span class="video-card-title-text">${track === "pptVideo" ? "pptVideo" : "teacherTrack"}</span>
        <div class="video-title-actions">
          <button class="icon-btn small-icon-btn video-mute-btn" type="button" data-video-action="mute" title="静音/取消静音" aria-label="静音/取消静音">
            <svg class="volume-icon" viewBox="0 0 24 24"><path d="M4 9v6h4l5 4V5L8 9H4Z"/><path d="M16 9.5a4 4 0 0 1 0 5"/><path d="M18.5 7a7 7 0 0 1 0 10"/></svg>
            <svg class="muted-icon" viewBox="0 0 24 24"><path d="M4 9v6h4l5 4V5L8 9H4Z"/><path d="m20 9.5-5 5m0-5 5 5"/></svg>
          </button>
          <button class="icon-btn small-icon-btn" type="button" data-video-action="fullscreen" title="全屏" aria-label="全屏">
            <svg viewBox="0 0 24 24"><path d="M8 3H3v5M16 3h5v5M8 21H3v-5M21 16v5h-5"/></svg>
          </button>
        </div>
      </div>
      <div class="video-frame">
        <video preload="metadata" playsinline src="${item.tracks[track].url}"></video>
      </div>
    `;
    grid.appendChild(card);
    const video = card.querySelector("video");
    video.dataset.track = track;
    video.playbackRate = state.playbackRate;
    video.muted = true;
    state.activeVideos.push(video);
    card.querySelector('[data-video-action="mute"]').addEventListener("click", () => toggleVideoMute(video));
    card.querySelector('[data-video-action="fullscreen"]').addEventListener("click", () => toggleVideoFullscreen(video, card));
  }

  const preferredAudio = state.activeVideos.find((video) => video.dataset.track === "teacherTrack") || state.activeVideos[0] || null;
  if (preferredAudio) setAudioVideo(preferredAudio);
  state.subtitleDriver = preferredAudio || state.activeVideos[0] || null;
  state.syncSource = state.subtitleDriver;
  wireVideoSync();
  updateVideoLayout();
  setText("subtitleBlock", "字幕将在这里显示");
  applySubtitleStyle();
  updatePlayerControls();
  const subtitleUrls = item.subtitle_urls?.length ? item.subtitle_urls : (item.subtitle_url ? [item.subtitle_url] : []);
  if (subtitleUrls.length) {
    state.subtitles = await loadSubtitles(subtitleUrls);
  }
}

async function loadSubtitles(urls) {
  const cues = [];
  let offset = 0;
  for (const url of urls) {
    const text = await fetch(url).then((res) => res.text());
    const parsed = parseSrt(text).map((cue) => ({
      ...cue,
      start: cue.start + offset,
      end: cue.end + offset,
    }));
    cues.push(...parsed);
    if (parsed.length) offset = Math.max(...parsed.map((cue) => cue.end));
  }
  cues.sort((left, right) => left.start - right.start || left.end - right.end);
  return cues;
}

function syncRangeAndNumber(range, input, value) {
  if (!range || !input) return;
  const normalized = formatNumber(value);
  input.value = normalized;
  const min = Number(range.min);
  const max = Number(range.max);
  range.value = String(Math.max(min, Math.min(max, Number(value) || 0)));
}

function setPptOffset(value) {
  state.pptOffset = clampNumber(value, -3600, 3600, 0);
  const range = $("pptOffsetRange");
  const input = $("pptOffsetInput");
  if (range && input) syncRangeAndNumber(range, input, state.pptOffset);
  const master = getMasterVideo();
  if (master) {
    alignFollowers(master, true);
    updateSubtitle(getBaselineTime(master));
    updateProgress();
  }
}

function setSubtitleOffset(value) {
  state.subtitleOffset = clampNumber(value, -3600, 3600, 0);
  syncRangeAndNumber($("subtitleOffsetRange"), $("subtitleOffsetInput"), state.subtitleOffset);
  const master = getMasterVideo();
  if (master) updateSubtitle(getBaselineTime(master));
}

function setSubtitleFontSize(value) {
  state.subtitleFontSize = clampNumber(value, 10, 72, 18);
  syncRangeAndNumber($("subtitleFontRange"), $("subtitleFontInput"), state.subtitleFontSize);
  applySubtitleStyle();
}

function setSubtitleBold(enabled) {
  state.subtitleBold = Boolean(enabled);
  applySubtitleStyle();
}

function setPlaybackRate(value) {
  state.playbackRate = clampNumber(value, 0.25, 4, 1);
  syncRangeAndNumber($("playbackSpeedRange"), $("playbackSpeedInput"), state.playbackRate);
  $("playbackSpeedSettings").textContent = `${formatNumber(state.playbackRate)}x`;
  for (const video of state.activeVideos) video.playbackRate = state.playbackRate;
}

function playAllVideos() {
  const master = getMasterVideo();
  if (!master) return;
  state.desiredPlaying = true;
  alignFollowers(master, true);
  startSyncLoop();
  const audibleTrack = state.activeVideos.find((video) => !video.muted)?.dataset.track || null;
  for (const video of state.activeVideos) video.muted = true;
  const playPromises = [];
  for (const video of state.activeVideos) {
    markProgrammaticPlay(video);
    video.playbackRate = state.playbackRate;
    playPromises.push(video.play().catch(() => {}));
  }
  Promise.allSettled(playPromises).then(() => {
    const audible = audibleTrack ? state.activeVideos.find((video) => video.dataset.track === audibleTrack) : null;
    if (audible) setAudioVideo(audible);
    if (state.desiredPlaying) {
      for (const video of state.activeVideos) {
        if (video.paused) {
          markProgrammaticPlay(video);
          video.play().catch(() => {});
        }
      }
    }
    window.setTimeout(updatePlayerControls, 200);
  });
  updatePlayerControls();
}

function togglePlayback() {
  if (!state.activeVideos.length) return;
  if (state.desiredPlaying || state.activeVideos.some((video) => !video.paused)) {
    pauseAllVideos(true);
  } else {
    playAllVideos();
  }
}

function setAudioVideo(source) {
  if (!source) return;
  state.audioTrack = source.dataset.track;
  state.lastAudioTrack = state.audioTrack;
  state.subtitleDriver = source;
  for (const video of state.activeVideos) video.muted = video !== source;
  updatePlayerControls();
}

function toggleVideoMute(video) {
  if (!video) return;
  if (video.muted) {
    setAudioVideo(video);
  } else {
    video.muted = true;
    state.lastAudioTrack = video.dataset.track;
    if (state.audioTrack === video.dataset.track) state.audioTrack = null;
    updatePlayerControls();
  }
}

function toggleGlobalMute() {
  const audible = state.activeVideos.find((video) => !video.muted);
  if (audible) {
    toggleVideoMute(audible);
    return;
  }
  const target =
    state.activeVideos.find((video) => video.dataset.track === state.lastAudioTrack) ||
    state.activeVideos.find((video) => video.dataset.track === "teacherTrack") ||
    state.activeVideos[0];
  if (target) setAudioVideo(target);
}

function toggleVideoFullscreen(video, card) {
  const target = video || card;
  if (!target) return;
  if (document.fullscreenElement) {
    document.exitFullscreen?.();
  } else {
    (target.requestFullscreen || card?.requestFullscreen)?.call(target);
  }
}

function getTimelineDuration() {
  const durations = state.activeVideos
    .filter((video) => Number.isFinite(video.duration) && video.duration > 0)
    .map((video) => Math.max(0, video.duration - getTrackOffset(video)));
  return durations.length ? Math.max(...durations) : 0;
}

function setTimelineTime(baselineTime, forcePlayState = false) {
  const duration = getTimelineDuration();
  const targetBaseline = Math.max(0, Math.min(duration || baselineTime, baselineTime));
  const master = getMasterVideo() || state.activeVideos[0];
  if (master) {
    setSyncSource(master);
    markProgrammaticSeek(master);
    master.currentTime = Math.max(0, getTrackTime(master, targetBaseline));
  }
  for (const video of state.activeVideos) {
    if (video === master || video.readyState < 1) continue;
    markProgrammaticSeek(video);
    video.currentTime = Math.max(0, getTrackTime(video, targetBaseline));
  }
  updateSubtitle(targetBaseline);
  updateProgress(targetBaseline);
  if (forcePlayState && state.desiredPlaying) playAllVideos();
}

function setProgressFill(ratio) {
  const progress = $("playerProgress");
  if (!progress) return;
  const clampedRatio = Math.max(0, Math.min(1, Number.isFinite(ratio) ? ratio : 0));
  progress.style.setProperty("--progress-fill", `${clampedRatio * 100}%`);
}

function updateProgress(baselineTime = null) {
  const duration = getTimelineDuration();
  const master = getMasterVideo();
  const current = baselineTime ?? (master ? getBaselineTime(master) : 0);
  const ratio = duration ? Math.max(0, Math.min(1, current / duration)) : 0;
  if (!state.progressDragging) {
    $("playerProgress").value = String(Math.round(ratio * 1000));
  }
  setProgressFill(state.progressDragging ? Number($("playerProgress").value) / 1000 : ratio);
  $("playerCurrentTime").textContent = formatTime(Math.max(0, current));
  $("playerDuration").textContent = formatTime(duration);
}

function updatePlayerControls() {
  const playing = state.desiredPlaying || state.activeVideos.some((video) => !video.paused);
  $("playerPlayPause").classList.toggle("playing", playing);
  const allMuted = !state.activeVideos.some((video) => !video.muted);
  $("playerMute").classList.toggle("muted", allMuted);
  $$(".video-card").forEach((card) => {
    const video = card.querySelector("video");
    card.querySelector(".video-mute-btn")?.classList.toggle("muted", !video || video.muted);
  });
  updateProgress();
}

function formatTime(value) {
  if (!Number.isFinite(value) || value < 0) return "0:00";
  const total = Math.floor(value);
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const seconds = total % 60;
  if (hours) return `${hours}:${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}

function applySubtitleStyle() {
  const block = $("subtitleBlock");
  block.style.fontSize = `${state.subtitleFontSize}px`;
  block.style.fontWeight = state.subtitleBold ? "800" : "400";
  $("subtitleBoldToggle").classList.toggle("active", state.subtitleBold);
}

function clampNumber(value, min, max, fallback) {
  const num = Number.parseFloat(value);
  if (!Number.isFinite(num)) return fallback;
  return Math.max(min, Math.min(max, num));
}

function formatNumber(value) {
  const num = Number(value) || 0;
  return Number.isInteger(num) ? String(num) : String(Number(num.toFixed(2)));
}

function attachDefaultSnap(range, setter) {
  if (!range) return;
  const defaultValue = Number(range.dataset.defaultValue || range.value || 0);
  const min = Number(range.min);
  const max = Number(range.max);
  const defaultRatio = max === min ? 0 : (defaultValue - min) / (max - min);
  range.parentElement?.style.setProperty("--default-ratio", String(defaultRatio));
  let snapCandidate = false;
  let moved = false;
  range.addEventListener("pointerdown", (event) => {
    const rect = range.getBoundingClientRect();
    const thumbSize = Number.parseFloat(getComputedStyle(range).getPropertyValue("--range-thumb-size")) || 16;
    const trackStart = rect.left + thumbSize / 2;
    const trackWidth = Math.max(1, rect.width - thumbSize);
    const clickRatio = (event.clientX - trackStart) / trackWidth;
    const currentRatio = max === min ? 0 : (Number(range.value) - min) / (max - min);
    const currentIsDefault = Math.abs(currentRatio - defaultRatio) <= 0.006;
    snapCandidate = Math.abs(clickRatio - defaultRatio) <= 0.045 && !currentIsDefault;
    moved = false;
  });
  range.addEventListener("pointermove", () => {
    moved = true;
  });
  range.addEventListener("pointerup", () => {
    if (snapCandidate && !moved) {
      setter(defaultValue);
    }
    snapCandidate = false;
    moved = false;
  });
}

function wireVideoSync() {
  for (const video of state.activeVideos) {
    const takeControl = () => {
      setSyncSource(video);
      setSubtitleDriver(video);
    };
    video.addEventListener("pointerdown", takeControl);
    video.addEventListener("keydown", takeControl);
    video.addEventListener("play", () => {
      if (!isProgrammaticPlay(video)) {
        setSyncSource(video);
        setSubtitleDriver(video);
      }
      state.desiredPlaying = true;
      startSyncLoop();
      maintainVideoSync(true);
      updatePlayerControls();
    });
    video.addEventListener("pause", () => {
      if (!state.desiredPlaying) {
        updatePlayerControls();
        return;
      }
      if (state.desiredPlaying && (video.seeking || video.readyState < 3)) return;
      state.desiredPlaying = false;
      pauseAllVideos(true);
    });
    video.addEventListener("seeking", () => {
      if (isProgrammaticSeek(video)) return;
      setSyncSource(video);
      setSubtitleDriver(video);
      if (!video.paused) state.desiredPlaying = true;
      alignFollowers(video, true);
      if (state.desiredPlaying) startSyncLoop();
    });
    video.addEventListener("seeked", () => {
      if (isProgrammaticSeek(video)) return;
      setSyncSource(video);
      setSubtitleDriver(video);
      alignFollowers(video, true);
      if (state.desiredPlaying) startSyncLoop();
    });
    video.addEventListener("ratechange", () => {
      if (shouldSuppressMediaEvent()) return;
      propagatePlaybackRate(video);
    });
    video.addEventListener("waiting", () => {
      if (video === getMasterVideo()) maintainVideoSync(false);
    });
    video.addEventListener("canplay", () => maintainVideoSync(true));
    video.addEventListener("volumechange", () => handleAudioFocus(video));
    video.addEventListener("timeupdate", () => {
      if (video === state.subtitleDriver) updateSubtitle(getBaselineTime(video));
      if (video === getMasterVideo()) updateProgress();
    });
    video.addEventListener("loadedmetadata", () => {
      updatePlayerControls();
      updateVideoLayout();
    });
  }
}

function shouldSuppressMediaEvent() {
  return Date.now() < state.suppressMediaEventsUntil;
}

function suppressMediaEvents(durationMs = 500) {
  state.suppressMediaEventsUntil = Date.now() + durationMs;
}

function setSubtitleDriver(video) {
  state.subtitleDriver = video || state.subtitleDriver || state.activeVideos[0] || null;
}

function setSyncSource(video) {
  if (video && state.activeVideos.includes(video)) state.syncSource = video;
}

function isProgrammaticSeek(video) {
  return Date.now() < (state.programmaticSeekUntil.get(video) || 0);
}

function markProgrammaticSeek(video) {
  state.programmaticSeekUntil.set(video, Date.now() + 900);
}

function isProgrammaticPlay(video) {
  return Date.now() < (state.programmaticPlayUntil.get(video) || 0);
}

function markProgrammaticPlay(video) {
  state.programmaticPlayUntil.set(video, Date.now() + 900);
}

function handleAudioFocus(source) {
  if (source.muted || source.volume === 0) return;
  setSubtitleDriver(source);
  for (const video of state.activeVideos) {
    if (video !== source) video.muted = true;
  }
}

function getMasterVideo() {
  if (state.syncSource && state.activeVideos.includes(state.syncSource)) return state.syncSource;
  return state.subtitleDriver || state.activeVideos.find((video) => !video.muted) || state.activeVideos[0] || null;
}

function getTrackOffset(video) {
  return video?.dataset.track === "pptVideo" ? state.pptOffset : 0;
}

function getBaselineTime(video) {
  return video.currentTime - getTrackOffset(video);
}

function getTrackTime(video, baselineTime) {
  return baselineTime + getTrackOffset(video);
}

function startSyncLoop() {
  if (state.syncTimer) return;
  state.syncTimer = window.setInterval(() => maintainVideoSync(false), 160);
}

function stopSyncLoop() {
  if (state.syncTimer) {
    window.clearInterval(state.syncTimer);
    state.syncTimer = null;
  }
  for (const video of state.activeVideos) video.playbackRate = state.playbackRate;
}

function maintainVideoSync(forceExact) {
  const master = getMasterVideo();
  if (!master || state.syncing) return;
  if (!state.desiredPlaying) {
    alignFollowers(master, true);
    stopSyncLoop();
    return;
  }
  alignFollowers(master, forceExact);
  for (const video of state.activeVideos) {
    maybeStartFollower(video);
  }
  updateSubtitle(getBaselineTime(master));
}

function alignFollowers(source, forceExact) {
  if (!source) return;
  if (state.syncing) return;
  state.syncing = true;
  const baselineTime = getBaselineTime(source);
  for (const video of state.activeVideos) {
    if (video === source) continue;
    if (video.readyState < 1) continue;
    const targetTime = Math.max(0, getTrackTime(video, baselineTime));
    const diff = targetTime - video.currentTime;
    if (forceExact || Math.abs(diff) > 0.22) {
      markProgrammaticSeek(video);
      video.currentTime = targetTime;
      video.playbackRate = state.playbackRate;
    } else if (Math.abs(diff) > 0.06 && state.desiredPlaying) {
      const correction = Math.max(-0.12, Math.min(0.12, diff * 0.18));
      video.playbackRate = Math.max(0.25, Math.min(4, state.playbackRate + correction));
    } else {
      video.playbackRate = state.playbackRate;
    }
  }
  updateSubtitle(baselineTime);
  state.syncing = false;
}

function propagatePlaybackRate(source) {
  if (!source) return;
  if (Math.abs((source.playbackRate || state.playbackRate) - state.playbackRate) > 0.01) {
    source.playbackRate = state.playbackRate;
  }
}

function maybeStartFollower(video) {
  if (!state.desiredPlaying || !video.paused || video.readyState < 3) return;
  const now = Date.now();
  const lastAttempt = state.lastPlayAttempt.get(video) || 0;
  if (now - lastAttempt < 1200) return;
  state.lastPlayAttempt.set(video, now);
  markProgrammaticPlay(video);
  video.play().catch(() => {});
}

function pauseAllVideos(syncFollowers) {
  state.desiredPlaying = false;
  const master = getMasterVideo();
  if (syncFollowers && master) alignFollowers(master, true);
  for (const video of state.activeVideos) {
    if (!video.paused) video.pause();
  }
  stopSyncLoop();
}

function parseSrt(text) {
  return text
    .replace(/\r/g, "")
    .split(/\n\n+/)
    .map((block) => {
      const lines = block.split("\n").filter(Boolean);
      const timeLine = lines.find((line) => line.includes("-->"));
      if (!timeLine) return null;
      const [start, end] = timeLine.split("-->").map((part) => parseTimestamp(part.trim().split(/\s+/)[0]));
      const index = lines.indexOf(timeLine);
      return { start, end, text: lines.slice(index + 1).join("\n") };
    })
    .filter(Boolean);
}

function parseTimestamp(value) {
  const [hms, ms = "0"] = value.replace(",", ".").split(".");
  const parts = hms.split(":").map(Number);
  const seconds = parts.length === 3 ? parts[0] * 3600 + parts[1] * 60 + parts[2] : parts[0] * 60 + parts[1];
  return seconds + Number(`0.${ms}`);
}

function updateSubtitle(currentTime) {
  const subtitleTime = currentTime + state.subtitleOffset;
  const cue = state.subtitles.find((item) => subtitleTime >= item.start && subtitleTime <= item.end);
  $("subtitleBlock").textContent = cue ? cue.text : "";
}

const AUTH_FIELD_IDS = [
  "idsUsername",
  "idsPassword",
  "chaoxingUsername",
  "chaoxingPassword",
  "cookieD",
  "cookieUid",
  "cookieVc3",
];

function setCredentialField(id, configured) {
  const input = $(id);
  input.value = configured ? "********" : "";
  input.placeholder = configured ? "输入新值" : "";
  input.dataset.credentialConfigured = configured ? "true" : "false";
  input.dataset.credentialTouched = "false";
}

function clearCredentialMask(input) {
  if (input.dataset.credentialConfigured !== "true" || input.dataset.credentialTouched === "true") return;
  input.value = "";
  input.dataset.credentialTouched = "true";
  input.dataset.credentialConfigured = "false";
}

function credentialValue(id) {
  const input = $(id);
  if (input.dataset.credentialConfigured === "true" && input.dataset.credentialTouched !== "true") return null;
  return input.value;
}

function setupCredentialFields() {
  for (const id of AUTH_FIELD_IDS) {
    on(id, "focus", () => clearCredentialMask($(id)));
    on(id, "pointerdown", () => clearCredentialMask($(id)));
  }
}

async function loadAuth() {
  try {
    const data = await apiJson("/api/settings/auth");
    state.initialSetupRequired = !data.auth_ready;
    $("authMethod").value = data.auth_ready ? (data.auth_method || "ids") : "chaoxing_qr";
    $("saveAuthInfo").checked = Boolean(data.save_auth_info);
    setCredentialField("idsUsername", Boolean(data.ids?.username_configured));
    setCredentialField("idsPassword", Boolean(data.ids?.password_configured));
    setCredentialField("chaoxingUsername", Boolean(data.chaoxing?.username_configured));
    setCredentialField("chaoxingPassword", Boolean(data.chaoxing?.password_configured));
    setCredentialField("cookieD", Boolean(data.cookies?._d_configured));
    setCredentialField("cookieUid", Boolean(data.cookies?.UID_configured));
    setCredentialField("cookieVc3", Boolean(data.cookies?.vc3_configured));
    if (data.uid && (!state.batchUidTouched || !$("batchUid").value.trim())) {
      $("batchUid").value = data.uid;
    }
    updateAuthBlocks();
    updateInitialSetupGuide();
    if (!data.auth_ready) switchPage("settings");
  } catch (err) {
    appendOutput(`读取登录配置失败: ${err.message}\n`);
  }
}

async function loadWebuiPasswordSettings() {
  try {
    const data = await apiJson("/api/settings/webui-password");
    state.webuiPasswordEnabled = Boolean(data.enabled);
    state.webuiPasswordChangeAllowed = data.allow_password_change !== false;
    updateWebuiPasswordState();
  } catch (err) {
    appendOutput(`读取 WebUI 访问密码设置失败: ${err.message}\n`);
  }
}

function updateWebuiPasswordState() {
  const el = $("webuiPasswordState");
  const panel = $("webuiPasswordPanel");
  if (panel) panel.classList.toggle("hidden", !state.webuiPasswordChangeAllowed);
  if (el) el.textContent = state.webuiPasswordEnabled ? "已启用" : "未设置";
}

async function saveWebuiPassword() {
  try {
    if (!state.webuiPasswordChangeAllowed) {
      setStatus("禁止修改", "error");
      return;
    }
    const password = $("webuiPassword").value;
    const confirm = $("webuiPasswordConfirm").value;
    const data = await apiJson("/api/settings/webui-password", {
      method: "POST",
      body: JSON.stringify({ password, confirm }),
    });
    state.webuiPasswordEnabled = Boolean(data.enabled);
    $("webuiPassword").value = "";
    $("webuiPasswordConfirm").value = "";
    updateWebuiPasswordState();
    setStatus("访问密码已保存", "success");
  } catch (err) {
    setStatus("保存失败", "error");
    appendOutput(`保存 WebUI 访问密码失败: ${err.message}\n`);
  }
}

async function clearWebuiPassword() {
  try {
    if (!state.webuiPasswordChangeAllowed) {
      setStatus("禁止修改", "error");
      return;
    }
    const data = await apiJson("/api/settings/webui-password", {
      method: "POST",
      body: JSON.stringify({ clear: true }),
    });
    state.webuiPasswordEnabled = Boolean(data.enabled);
    $("webuiPassword").value = "";
    $("webuiPasswordConfirm").value = "";
    updateWebuiPasswordState();
    setStatus("访问密码已清除", "success");
  } catch (err) {
    setStatus("清除失败", "error");
    appendOutput(`清除 WebUI 访问密码失败: ${err.message}\n`);
  }
}

function updateAuthBlocks() {
  const method = $("authMethod").value;
  $$(".auth-block").forEach((block) => {
    const blockName = block.dataset.authBlock;
    const visible = blockName === method;
    setHidden(block, !visible);
  });
}

function updateInitialSetupGuide() {
  setHidden("initialSetupGuide", !state.initialSetupRequired);
}

async function saveAuth() {
  try {
    await apiJson("/api/settings/auth", {
      method: "POST",
      body: JSON.stringify({
        auth_method: $("authMethod").value,
        save_auth_info: $("saveAuthInfo").checked,
        ids: { username: credentialValue("idsUsername"), password: credentialValue("idsPassword") },
        chaoxing: { username: credentialValue("chaoxingUsername"), password: credentialValue("chaoxingPassword") },
        cookies: { _d: credentialValue("cookieD"), UID: credentialValue("cookieUid"), vc3: credentialValue("cookieVc3") },
      }),
    });
    state.initialSetupRequired = false;
    updateInitialSetupGuide();
    setStatus("配置已保存", "success");
  } catch (err) {
    setStatus("保存失败", "error");
    appendOutput(`保存登录配置失败: ${err.message}\n`);
  }
}

function setQrLoading(message) {
  setHidden("qrBox", false);
  setHidden("qrLoading", false);
  setHidden("qrImage", true);
  $("qrImage").removeAttribute("src");
  setText("qrStatus", message);
}

function showQrImage(url) {
  const img = $("qrImage");
  img.onload = () => {
    setHidden("qrLoading", true);
    setHidden(img, false);
  };
  img.onerror = () => {
    setHidden("qrLoading", false);
    setHidden(img, true);
  };
  img.src = `${url}?t=${Date.now()}`;
}

function stopQrPolling(cancelRemote = false) {
  if (state.qrTimer) {
    clearInterval(state.qrTimer);
    state.qrTimer = null;
  }
  const jobId = state.qrJobId;
  state.qrJobId = null;
  if (cancelRemote && jobId) {
    fetch(`/api/settings/qr/${jobId}/cancel`, { method: "POST", keepalive: true }).catch(() => {});
  }
}

async function startQr() {
  try {
    stopQrPolling(true);
    setQrLoading("二维码生成中...");
    const data = await apiJson("/api/settings/qr/start", { method: "POST", body: "{}" });
    state.qrJobId = data.id;
    if (state.qrTimer) clearInterval(state.qrTimer);
    const pollQrStatus = async () => {
      const status = await apiJson(`/api/settings/qr/${data.id}`);
      setText("qrStatus", status.message || status.status);
      if (status.status === "waiting" && $("qrImage").classList.contains("hidden")) {
        showQrImage(data.image_url);
      }
      if (["success", "failed", "cancelled"].includes(status.status)) {
        stopQrPolling(false);
        if (status.status !== "success") {
          setHidden("qrLoading", true);
          setHidden("qrImage", true);
        }
        if (status.status === "success") {
          setHidden("qrLoading", true);
          await loadAuth();
        }
        return true;
      }
      return false;
    };
    const done = await pollQrStatus();
    if (!done) state.qrTimer = setInterval(pollQrStatus, 1000);
  } catch (err) {
    setHidden("qrBox", false);
    setHidden("qrLoading", true);
    setHidden("qrImage", true);
    stopQrPolling(false);
    setText("qrStatus", `二维码登录失败：${err.message}`);
  }
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (ch) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#039;",
  })[ch]);
}

function togglePopover(menuId) {
  const menu = $(menuId);
  const willOpen = menu.classList.contains("hidden");
  closePopovers();
  if (willOpen) {
    setHidden(menu, false);
    requestAnimationFrame(() => positionPopover(menu));
  }
}

function closePopovers() {
  $$(".control-popover").forEach((menu) => {
    setHidden(menu, true);
    menu.style.setProperty("--popover-shift-x", "0px");
  });
}

function positionPopover(menu) {
  menu.style.setProperty("--popover-shift-x", "0px");
  const margin = 12;
  const rect = menu.getBoundingClientRect();
  let shift = 0;
  if (rect.left < margin) {
    shift = margin - rect.left;
  } else if (rect.right > window.innerWidth - margin) {
    shift = window.innerWidth - margin - rect.right;
  }
  menu.style.setProperty("--popover-shift-x", `${shift}px`);
}

function bindPairedControl(rangeId, inputId, setter, initialValue) {
  const range = $(rangeId);
  const input = $(inputId);
  attachDefaultSnap(range, setter);
  range.addEventListener("input", () => setter(range.value));
  input.addEventListener("input", () => setter(input.value));
  syncRangeAndNumber(range, input, initialValue);
}

function getProgressRatio() {
  return Math.max(0, Math.min(1, Number($("playerProgress").value) / 1000));
}

function commitProgressDrag(forcePlayState = false) {
  state.progressDragging = false;
  const duration = getTimelineDuration();
  const ratio = getProgressRatio();
  setProgressFill(ratio);
  setTimelineTime(ratio * duration, forcePlayState);
}

function setupViewerControls() {
  on("playerPlayPause", "click", togglePlayback);
  on("playerMute", "click", toggleGlobalMute);
  on("playbackSpeedSettings", "click", (event) => {
    event.stopPropagation();
    togglePopover("playbackSpeedMenu");
  });
  on("videoOffsetSettings", "click", (event) => {
    event.stopPropagation();
    togglePopover("videoOffsetMenu");
  });
  on("subtitleSettings", "click", (event) => {
    event.stopPropagation();
    togglePopover("subtitleSettingsMenu");
  });
  bindPairedControl("playbackSpeedRange", "playbackSpeedInput", setPlaybackRate, state.playbackRate);
  bindPairedControl("pptOffsetRange", "pptOffsetInput", setPptOffset, state.pptOffset);
  bindPairedControl("subtitleOffsetRange", "subtitleOffsetInput", setSubtitleOffset, state.subtitleOffset);
  bindPairedControl("subtitleFontRange", "subtitleFontInput", setSubtitleFontSize, state.subtitleFontSize);
  on("subtitleBoldToggle", "click", () => setSubtitleBold(!state.subtitleBold));
  on("playerProgress", "pointerdown", () => {
    state.progressDragging = true;
  });
  on("playerProgress", "input", () => {
    const duration = getTimelineDuration();
    const ratio = getProgressRatio();
    setProgressFill(ratio);
    setTimelineTime(ratio * duration);
  });
  on("playerProgress", "change", () => commitProgressDrag(true));
  on("playerProgress", "pointerup", () => commitProgressDrag(true));
  on("playerProgress", "pointercancel", () => {
    state.progressDragging = false;
    updateProgress();
  });
  setPlaybackRate(state.playbackRate);
  applySubtitleStyle();
  updatePlayerControls();
}

$$(".nav-item").forEach((btn) => {
  btn.addEventListener("click", () => switchPage(btn.dataset.page));
});

document.addEventListener("click", (event) => {
  const toggle = event.target.closest("[data-popover-toggle]");
  if (toggle) {
    event.stopPropagation();
    togglePopover(toggle.dataset.popoverToggle);
    return;
  }
  if (!event.target.closest(".control-popover")) closePopovers();
});

on("menuToggle", "click", () => {
  document.querySelector(".app-shell").classList.toggle("sidebar-collapsed");
  setTimeout(updateVideoLayout, 240);
});
on("reloadAutomation", "click", loadAutomation);
on("refreshAutomation", "click", refreshAutomation);
on("initAutomation", "click", initAutomation);
on("batchUid", "input", () => {
  state.batchUidTouched = true;
});
on("startSingle", "click", () => startDownload({
  mode: "single",
  live_id: $("singleLiveId").value.trim(),
  single: Number($("singleMode").value),
  merge: $("singleMerge").checked,
  video_type: $("singleVideoType").value,
  skip_weeks: $("singleSkipWeeks").value.trim(),
}));
on("startBatch", "click", () => startDownload({
  mode: "batch",
  selected_sections: selectedCourseSections(),
  video_type: $("batchVideoType").value,
}));
on("selectAllCourses", "click", () => {
  $$("input[type=checkbox]", $("courseList")).forEach((box) => { box.checked = true; });
});
on("selectNoCourses", "click", () => {
  $$("input[type=checkbox]", $("courseList")).forEach((box) => { box.checked = false; });
});
on("saveCourseSelection", "click", saveCourseSelection);
on("clearOutput", "click", resetOutput);
on("reloadLibrary", "click", loadLibrary);
on("maximizePlayer", "click", () => {
  const panel = document.querySelector(".player-panel");
  const maximized = panel.classList.toggle("maximized");
  document.body.classList.toggle("player-maximized", maximized);
  $("maximizePlayer").title = maximized ? "退出最大化" : "最大化视频块";
  $("maximizePlayer").setAttribute("aria-label", maximized ? "退出最大化" : "最大化视频块");
  setTimeout(updateVideoLayout, 0);
});
on("reloadAuth", "click", loadAuth);
on("authMethod", "change", updateAuthBlocks);
on("saveAuth", "click", saveAuth);
on("startQr", "click", startQr);
on("saveWebuiPassword", "click", saveWebuiPassword);
on("clearWebuiPassword", "click", clearWebuiPassword);
on("accessForm", "submit", submitAccessPassword);
window.addEventListener("resize", () => {
  updateVideoLayout();
  $$(".control-popover:not(.hidden)").forEach(positionPopover);
});
window.addEventListener("beforeunload", () => stopQrPolling(true));

function initializeApp() {
  if (!state.viewerControlsReady) {
    setupViewerControls();
    setupCredentialFields();
    ensureVideoLayoutObserver();
    state.viewerControlsReady = true;
  }
  loadAppInfo();
  loadAutomation();
  loadLibrary();
  loadAuth();
  loadWebuiPasswordSettings();
  restoreActiveDownloadStream();
}

checkWebuiAccess();
