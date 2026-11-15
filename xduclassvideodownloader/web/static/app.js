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
    const releasesUrl = data.releases_url || "https://github.com/lsy223622/XDUClassVideoDownloader/releases";
    state.appMessage = message;
    $("versionBadge").textContent = `v${version}`;
    $("versionBadge").href = releasesUrl;
    $("pageHint").textContent = message;

    const notice = $("updateNotice");
    if (data.update_available && data.latest_version) {
      notice.textContent = `有更新版本${data.latest_version}，请点击这里前往下载页面`;
      notice.href = releasesUrl;
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


function downloadNotice(message = "", error = false) {
  $("downloadNotice").textContent = message;
  $("downloadNotice").dataset.error = String(error);
  setHidden("downloadNotice", !message);
}

function batchParameters() {
  return {uid: $("batchUid").value.trim(), year: $("batchYear").value,
    term: $("batchTerm").value, video_type: $("batchVideoType").value};
}

function renderCourses(courses) {
  state.automationCourses = courses;
  $("courseList").replaceChildren(...courses.map((course, index) => {
    const row = document.createElement("label");
    row.className = "course-row";
    row.innerHTML = '<input type="checkbox"><span class="download-course-line"><span class="course-name"></span> <span class="course-meta"></span></span>';
    const checkbox = row.querySelector("input");
    checkbox.checked = course.selected;
    checkbox.dataset.index = index;
    row.querySelector(".course-name").textContent = course.course_name || "未命名课程";
    row.querySelector(".course-meta").textContent = [course.course_code, "LiveID " + course.live_id].filter(Boolean).join(" · ");
    row.title = row.querySelector(".download-course-line").textContent;
    return row;
  }));
  $("courseList").scrollTop = 0;
  setText("courseCount", courses.length + " 门课程");
  updateCourseSelection();
}

function selectedCourses() {
  return $$("input:checked", $("courseList")).map(box => state.automationCourses[Number(box.dataset.index)]);
}

function updateCourseSelection() {
  const count = selectedCourses().length;
  setText("selectedCount", "已选 " + count + " 门");
  $("startBatch").disabled = count === 0;
  $("saveCourseSelection").disabled = !state.automationCourses.length;
}

async function loadAutomation() {
  try {
    const data = await apiJson("/api/automation/config");
    const defaults = data.defaults;
    for (const [field, value] of Object.entries({
      batchUid: defaults.user_id, batchYear: defaults.term_year,
      batchTerm: defaults.term_id, batchVideoType: defaults.video_type,
    })) {
      if (value && (field !== "batchUid" || !state.batchUidTouched)) $(field).value = value;
    }
    state.scannedTerm = {
      uid: defaults.user_id || $("batchUid").value, year: defaults.term_year, term: defaults.term_id,
    };
    renderCourses(data.courses);
    downloadNotice();
  } catch (error) {
    downloadNotice("读取配置失败：" + error.message, true);
  }
}

async function scanCourses(event) {
  event.preventDefault();
  const params = batchParameters();
  const button = $("scanButton");
  button.disabled = true;
  $("reloadAutomation").disabled = true;
  button.textContent = "扫描中…";
  downloadNotice();
  try {
    const data = await apiJson("/api/download/courses", {
      method: "POST", body: JSON.stringify(params),
    });
    state.scannedTerm = params;
    renderCourses(data.courses);
  } catch (error) {
    downloadNotice("扫描课程失败：" + error.message, true);
  } finally {
    button.disabled = false;
    $("reloadAutomation").disabled = false;
    button.textContent = "扫描课程";
  }
}

async function saveCourseSelection() {
  const selection = new Set(selectedCourses());
  const courses = state.automationCourses.map(course => ({...course, selected: selection.has(course)}));
  try {
    await apiJson("/api/automation/config", {
      method: "POST", body: JSON.stringify({...state.scannedTerm, video_type: $("batchVideoType").value, courses}),
    });
    downloadNotice("已保存配置");
  } catch (error) {
    downloadNotice("保存配置失败：" + error.message, true);
  }
}

const trackLabels = {pptVideo: "课件画面", teacherTrack: "教师画面", subtitle: "字幕"};
const lessonStatus = {waiting: "未下载", omitted: "未选择", unavailable: "无可用字幕", downloading: "下载中", done: "已下载", failed: "失败"};
const jobStatus = {pending: "排队中", running: "下载中", paused: "已暂停", stopping: "正在停止", stopped: "已停止", success: "已完成", failed: "失败"};
const downloadCards = new Map();
const mergeAnimations = new Map();

function lessonLabel(lesson, start = lesson.period, end = start) {
  const periods = start === end ? start : start + "-" + end;
  return lesson.year + "年" + lesson.month + "月" + lesson.day + "日 第" + lesson.week +
    "周 星期" + lesson.weekday + " 第" + periods + "节";
}

function matchesMerge(lesson, merge) {
  const day = merge.lesson;
  return lesson.year === day.year && lesson.month === day.month && lesson.day === day.day &&
    lesson.week === day.week && lesson.weekday === day.weekday &&
    lesson.period >= merge.start && lesson.period <= merge.end;
}

function makeDownloadCard(id) {
  const card = document.createElement("article");
  card.className = "download-job";
  card.innerHTML = '<div class="download-job-title"><strong></strong><span class="download-job-state"></span></div>' +
    '<div class="download-tracks"><div class="download-track-labels"><span>课件</span><span>教师</span><span>字幕</span></div>' +
    '<div class="download-track-rows"><div class="download-track" aria-label="课件画面" role="group"></div>' +
    '<div class="download-track" aria-label="教师画面" role="group"></div>' +
    '<div class="download-track download-track-subtitle" aria-label="字幕" role="group"></div></div></div>' +
    '<div class="download-job-foot"><span></span><span class="download-speed"></span>' +
    '<button class="ghost-btn" type="button" hidden>重试</button></div>' +
    '<details class="download-errors" hidden><summary></summary><ul></ul></details>';
  card.querySelector("button").onclick = async () => {
    try {
      await updateJobs("/api/download/jobs/" + id + "/retry", "POST");
    } catch (error) {
      downloadNotice("重试失败：" + error.message, true);
    }
  };
  $("downloadJobs").append(card);
  downloadCards.set(id, card);
  return card;
}

function lessonIdentity(lesson) {
  return [lesson.year, lesson.month, lesson.day, lesson.week, lesson.weekday, lesson.period].join("/");
}

function renderTrack(row, job, track) {
  const oldTiles = new Map([...row.children].map(tile => [tile.dataset.lesson, tile]));
  const merges = job.merges.filter(item => item.track === track).reverse();
  const tiles = job.lessons.map((lesson, index) => {
    const id = lessonIdentity(lesson);
    let tile = oldTiles.get(id);
    if (!tile) {
      tile = document.createElement("span");
      tile.className = "download-lesson";
      tile.dataset.lesson = id;
      tile.setAttribute("role", "img");
      tile.innerHTML = '<span class="download-lesson-shape"><span class="download-lesson-fill"></span></span>';
    }
    const merge = merges.find(item => matchesMerge(lesson, item));
    const progress = lesson.tracks[track] || {};
    const status = merge ? "done" : progress.status || (track === "subtitle" || job.tracks.includes(track) ? "waiting" : "omitted");
    const fraction = status === "done" || status === "failed" ? 1 :
      (progress.total ? Math.min(1, progress.completed / progress.total) : 0);
    const percent = progress.total && status === "downloading" ? " " + Math.floor(fraction * 100) + "%" : "";
    tile.dataset.state = status;
    tile.classList.toggle("unknown-size", status === "downloading" && !progress.total && progress.completed > 0);
    tile.style.setProperty("--fill", fraction);
    tile.title = lessonLabel(lesson, merge?.start, merge?.end) + " · " +
      (progress.message || (merge ? "已合并" : lessonStatus[status])) + percent;
    tile.setAttribute("aria-label", trackLabels[track] + " · " + tile.title);
    const joins = (other, step) => Boolean(merge && other && other.period === lesson.period + step && matchesMerge(other, merge));
    tile.classList.toggle("join-next", joins(job.lessons[index + 1], 1));
    tile.classList.toggle("join-prev", joins(job.lessons[index - 1], -1));
    return tile;
  });
  if (tiles.length !== row.children.length || tiles.some((tile, index) => row.children[index] !== tile)) {
    row.replaceChildren(...tiles);
  }
}

function renderJobTracks(card, job, merges) {
  const rows = $$(".download-track", card);
  Object.keys(trackLabels).forEach((track, index) => renderTrack(rows[index], {...job, merges}, track));
}

function updateJobTracks(card, job) {
  let animation = mergeAnimations.get(job.id);
  if (!animation) {
    animation = {job, count: job.merges.length, timer: null};
    mergeAnimations.set(job.id, animation);
  }
  animation.job = job;
  const advance = () => {
    const current = animation.job;
    const merges = current.merges;
    while (merges[animation.count]?.existing) animation.count++;
    if (animation.count < merges.length) {
      animation.count++;
      animation.timer = window.setTimeout(() => {
        animation.timer = null;
        advance();
      }, 560);
    }
    renderJobTracks(card, current, merges.slice(0, animation.count));
  };
  if (animation.timer === null) advance();
  else renderJobTracks(card, job, job.merges.slice(0, animation.count));
}

function renderDownloadJobs(jobs, paused) {
  const active = jobs.some(job => ["running", "pending", "paused", "stopping"].includes(job.status));
  const mayControl = jobs.some(job => ["running", "pending", "paused"].includes(job.status));
  const pauseButton = $("pauseDownloads");
  pauseButton.disabled = !mayControl && !paused;
  $("stopDownloads").disabled = !mayControl && !paused;
  const pauseLabel = paused ? "继续下载" : "暂停下载";
  pauseButton.title = pauseLabel;
  pauseButton.setAttribute("aria-label", pauseLabel);
  pauseButton.firstElementChild.hidden = paused;
  pauseButton.lastElementChild.hidden = !paused;
  state.downloadPaused = paused;
  const renderedIds = new Set(jobs.map(job => job.id));
  for (const [id, card] of downloadCards) {
    if (!renderedIds.has(id)) {
      card.remove();
      downloadCards.delete(id);
      window.clearTimeout(mergeAnimations.get(id)?.timer);
      mergeAnimations.delete(id);
    }
  }
  $("downloadJobs").style.setProperty("--lesson-columns", Math.max(1, ...jobs.map(job => job.lessons.length)));
  setHidden("emptyDownloadJobs", jobs.length > 0);
  $("clearCompleted").disabled = !jobs.some(job => job.status === "success" || job.status === "stopped");
  for (const job of jobs) {
    const card = downloadCards.get(job.id) || makeDownloadCard(job.id);
    card.dataset.state = job.status;
    card.querySelector("strong").textContent = [job.code, job.name].filter(Boolean).join(" ");
    card.querySelector(".download-job-state").textContent = (job.status === "running" && job.phase) || jobStatus[job.status];
    updateJobTracks(card, job);
    card.querySelector(".download-tracks").hidden = !job.lessons.length;
    const complete = job.lessons.reduce((total, lesson) => total + job.tracks
      .filter(track => lesson.tracks[track]?.status === "done").length, 0);
    const total = job.lessons.length * job.tracks.length;
    card.querySelector(".download-job-foot > span").textContent = total ? complete + " / " + total + " 个视频" : "";
    card.querySelector(".download-speed").textContent = job.speed > 0
      ? (job.speed >= 1e6 ? (job.speed / 1e6).toFixed(1) + " MB/s" : (job.speed / 1e3).toFixed(1) + " KB/s") : "";
    card.querySelector("button").hidden = !["failed", "stopped"].includes(job.status);
    const details = card.querySelector("details");
    details.hidden = !job.errors.length;
    details.querySelector("summary").textContent = job.errors.length + " 条错误";
    const errors = details.querySelector("ul");
    if (errors.children.length !== job.errors.length) {
      errors.replaceChildren(...job.errors.map(error => {
        const li = document.createElement("li");
        li.textContent = (error.lesson ? lessonLabel(error.lesson, error.start, error.end) + " · " +
          trackLabels[error.track] + " · " : "") + error.message;
        return li;
      }));
    }
  }
  if (state.downloadActive && !active) loadLibrary();
  if (active || state.downloadActive) setStatus(paused ? "下载已暂停" : active ? "下载中" : "空闲", active && !paused ? "running" : "");
  state.downloadActive = active;
}

let downloadPoll;
let downloadRequest = Promise.resolve();
function updateJobs(url = "/api/download/jobs", method = "GET", payload) {
  window.clearTimeout(downloadPoll);
  const load = async () => {
    if (method !== "GET") {
      await apiJson(url, {method, body: payload && JSON.stringify(payload)});
    }
    const data = await apiJson("/api/download/jobs");
    renderDownloadJobs(data.jobs, data.paused);
  };
  const request = downloadRequest.then(load);
  downloadRequest = request.catch(() => {}).then(() => {
    window.clearTimeout(downloadPoll);
    downloadPoll = window.setTimeout(() => updateJobs().catch(error => {
      downloadNotice("刷新下载任务失败：" + error.message, true);
    }), state.downloadActive ? 400 : 2000);
  });
  return request;
}

async function startDownload(payload, button) {
  button.disabled = true;
  try {
    await updateJobs("/api/download/start", "POST", payload);
    downloadNotice();
  } catch (error) {
    downloadNotice("启动失败：" + error.message, true);
  } finally {
    button.disabled = false;
    updateCourseSelection();
  }
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
  const cue = findSubtitleCue(subtitleTime);
  $("subtitleBlock").textContent = cue ? cue.text : "";
}

function findSubtitleCue(subtitleTime) {
  let left = 0;
  let right = state.subtitles.length - 1;
  while (left <= right) {
    const mid = Math.floor((left + right) / 2);
    const cue = state.subtitles[mid];
    if (subtitleTime < cue.start) {
      right = mid - 1;
    } else if (subtitleTime > cue.end) {
      left = mid + 1;
    } else {
      return cue;
    }
  }
  return null;
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
    setStatus(`读取登录配置失败: ${err.message}`, "error");
  }
}

async function loadWebuiPasswordSettings() {
  try {
    const data = await apiJson("/api/settings/webui-password");
    state.webuiPasswordEnabled = Boolean(data.enabled);
    state.webuiPasswordChangeAllowed = data.allow_password_change !== false;
    updateWebuiPasswordState();
  } catch (err) {
    setStatus(`读取 WebUI 访问密码设置失败: ${err.message}`, "error");
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
    setStatus(`保存 WebUI 访问密码失败: ${err.message}`, "error");
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
    setStatus(`清除 WebUI 访问密码失败: ${err.message}`, "error");
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
    setStatus(`保存登录配置失败: ${err.message}`, "error");
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

function switchDownloadMode(batch) {
  setHidden("batchDownload", !batch);
  setHidden("singleDownload", batch);
  $("batchMode").setAttribute("aria-pressed", String(batch));
  $("liveMode").setAttribute("aria-pressed", String(!batch));
}

on("batchMode", "click", () => switchDownloadMode(true));
on("liveMode", "click", () => switchDownloadMode(false));
on("reloadAutomation", "click", () => { state.batchUidTouched = false; loadAutomation(); });
on("scanCourses", "submit", scanCourses);
on("batchUid", "input", () => { state.batchUidTouched = true; });
on("singleDownload", "submit", event => {
  event.preventDefault();
  startDownload({
    mode: "single",
    live_id: $("singleLiveId").value.trim(),
    single: Number($("singleMode").value),
    merge: $("singleMerge").checked,
    video_type: $("singleVideoType").value,
    skip_weeks: $("singleSkipWeeks").value.trim(),
  }, $("startSingle"));
});
on("startBatch", "click", () => startDownload({
  mode: "batch", courses: selectedCourses(), video_type: $("batchVideoType").value,
}, $("startBatch")));
on("courseList", "change", updateCourseSelection);
for (const [id, checked] of [["selectAllCourses", true], ["selectNoCourses", false]]) {
  on(id, "click", () => {
    $$("input[type=checkbox]", $("courseList")).forEach(box => { box.checked = checked; });
    updateCourseSelection();
  });
}
on("saveCourseSelection", "click", saveCourseSelection);
function controlDownloads(action) {
  return updateJobs("/api/download/jobs/control", "POST", {action}).catch(error => {
    downloadNotice("下载操作失败：" + error.message, true);
  });
}
on("pauseDownloads", "click", () => controlDownloads(state.downloadPaused ? "resume" : "pause"));
on("stopDownloads", "click", () => controlDownloads("stop"));
on("clearCompleted", "click", () => updateJobs("/api/download/jobs", "DELETE").catch(error => {
  downloadNotice("清除任务失败：" + error.message, true);
}));

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
  updateJobs().catch(error => downloadNotice("读取下载任务失败：" + error.message, true));
}

checkWebuiAccess();
