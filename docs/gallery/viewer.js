"use strict";

(() => {
  const README_URL = "https://github.com/Yaozhil/mpv-Yaozhi#readme";
  const IMAGE_EXTENSIONS = /\.(?:avif|gif|jpe?g|png|svg|webp)$/i;
  const title = document.getElementById("image-title");
  const canvas = document.getElementById("image-canvas");
  const stage = document.getElementById("stage");
  const loadingPanel = document.getElementById("loading-panel");
  const loadingMessage = document.getElementById("loading-message");
  const errorPanel = document.getElementById("error-panel");
  const errorHeading = document.getElementById("error-heading");
  const errorMessage = document.getElementById("error-message");
  const retryButton = document.getElementById("retry-button");
  const fitButton = document.getElementById("fit-button");
  const actualButton = document.getElementById("actual-button");
  const fullscreenButton = document.getElementById("fullscreen-button");
  const fullscreenLabel = document.getElementById("fullscreen-label");
  const closeButton = document.getElementById("close-button");
  const originalLink = document.getElementById("original-link");
  const previousButton = document.getElementById("previous-button");
  const nextButton = document.getElementById("next-button");
  const positionLabel = document.getElementById("position-label");
  const notice = document.getElementById("notice");
  const imageDirectory = new URL("../images/", document.baseURI);
  const manifestUrl = new URL("./images.json", document.baseURI);

  let images = [];
  let currentIndex = 0;
  let renderSequence = 0;
  let activeImage = null;
  let manifestRequest = null;
  let retryAction = () => loadManifest();
  let viewMode = "fit";
  let closing = false;
  let wasFullscreen = false;
  let leaveFullscreenFromToolbar = false;
  let noticeTimer;

  function currentFullscreenElement() {
    return document.fullscreenElement || document.webkitFullscreenElement;
  }

  function exitFullscreen() {
    const exit = document.exitFullscreen || document.webkitExitFullscreen;
    return exit ? exit.call(document) : Promise.resolve();
  }

  function setBusy(message) {
    stage.setAttribute("aria-busy", "true");
    loadingMessage.textContent = message;
    loadingPanel.hidden = false;
    errorPanel.hidden = true;
  }

  function showError(heading, message, retry) {
    stage.setAttribute("aria-busy", "false");
    loadingPanel.hidden = true;
    errorHeading.textContent = heading;
    errorMessage.textContent = message;
    errorPanel.hidden = false;
    retryAction = retry;
  }

  function showNotice(message) {
    clearTimeout(noticeTimer);
    notice.textContent = message;
    notice.hidden = false;
    noticeTimer = setTimeout(() => { notice.hidden = true; }, 4500);
  }

  function updateSize() {
    const toolbarHeight = document.getElementById("toolbar").getBoundingClientRect().height;
    const navigationHeight = document.getElementById("navigation").getBoundingClientRect().height;
    document.documentElement.style.setProperty("--toolbar-height", `${toolbarHeight}px`);
    document.documentElement.style.setProperty("--navigation-height", `${navigationHeight}px`);
  }

  function setViewMode(mode) {
    viewMode = mode;
    canvas.classList.toggle("mode-fit", mode === "fit");
    canvas.classList.toggle("mode-actual", mode === "actual");
    fitButton.setAttribute("aria-pressed", String(mode === "fit"));
    actualButton.setAttribute("aria-pressed", String(mode === "actual"));
    canvas.scrollTo(0, 0);
  }

  function readHash() {
    try { return decodeURIComponent(location.hash.slice(1)); }
    catch { return ""; }
  }

  function replaceHash(id) {
    const hash = `#${encodeURIComponent(id)}`;
    if (location.hash !== hash) {
      history.replaceState(history.state, "", `${location.pathname}${location.search}${hash}`);
    }
  }

  function imageUrl(entry) {
    return new URL(encodeURIComponent(entry.file), imageDirectory);
  }

  function validateManifest(value) {
    if (!Array.isArray(value) || value.length === 0) throw new Error("Empty image list");
    const ids = new Set();
    return value.map((entry) => {
      if (!entry || typeof entry.id !== "string" || !entry.id.trim() || entry.id.length > 200 || /[\u0000-\u001f\u007f]/.test(entry.id)) {
        throw new Error("Invalid image identifier");
      }
      if (ids.has(entry.id)) throw new Error("Duplicate image identifier");
      if (typeof entry.file !== "string" || !entry.file || entry.file.length > 512 || /[\\/\u0000-\u001f\u007f]/.test(entry.file) || !IMAGE_EXTENSIONS.test(entry.file)) {
        throw new Error("Invalid image filename");
      }
      ids.add(entry.id);
      return {
        id: entry.id,
        file: entry.file,
        title: typeof entry.title === "string" && entry.title.trim() ? entry.title.trim() : entry.file,
      };
    });
  }

  function releaseActiveImage() {
    if (activeImage) {
      activeImage.onload = null;
      activeImage.onerror = null;
      activeImage.removeAttribute("src");
      activeImage = null;
    }
    canvas.replaceChildren();
  }

  function renderImage(index, retry = false) {
    if (!images.length || closing) return;
    currentIndex = ((index % images.length) + images.length) % images.length;
    const entry = images[currentIndex];
    const sequence = ++renderSequence;
    releaseActiveImage();
    setBusy(`正在加载：${entry.title}`);
    title.textContent = entry.title;
    title.title = entry.title;
    document.title = `${entry.title} · mpv-Yaozhi 图库`;
    positionLabel.textContent = `${currentIndex + 1} / ${images.length}`;
    previousButton.disabled = images.length < 2;
    nextButton.disabled = images.length < 2;
    fitButton.disabled = false;
    actualButton.disabled = false;
    const originalUrl = imageUrl(entry);
    originalLink.href = originalUrl.href;
    originalLink.removeAttribute("aria-disabled");
    replaceHash(entry.id);
    setViewMode(viewMode);

    const image = new Image();
    activeImage = image;
    image.className = "viewer-image";
    image.alt = entry.title;
    image.decoding = "async";
    image.draggable = false;
    image.onload = () => {
      if (sequence !== renderSequence || closing) return;
      canvas.replaceChildren(image);
      loadingPanel.hidden = true;
      errorPanel.hidden = true;
      stage.setAttribute("aria-busy", "false");
    };
    image.onerror = () => {
      if (sequence !== renderSequence || closing) return;
      showError("图片暂时未能加载", "请检查网络后重试，也可以使用上方的“原图”链接查看。", () => renderImage(currentIndex, true));
    };
    const requestUrl = new URL(originalUrl);
    if (retry) requestUrl.searchParams.set("retry", String(Date.now()));
    image.src = requestUrl.href;
  }

  function selectFromHash() {
    const id = readHash();
    const index = images.findIndex((entry) => entry.id === id);
    renderImage(index < 0 ? 0 : index);
  }

  async function loadManifest() {
    if (closing) return;
    if (manifestRequest) manifestRequest.abort();
    const request = new AbortController();
    manifestRequest = request;
    setBusy("正在加载图库…");
    retryButton.disabled = true;
    try {
      const response = await fetch(manifestUrl, { cache: "no-cache", signal: request.signal });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const parsed = validateManifest(await response.json());
      if (manifestRequest !== request || closing) return;
      images = parsed;
      selectFromHash();
    } catch (error) {
      if (error.name === "AbortError" || closing) return;
      title.textContent = "界面图库";
      showError("暂时无法打开图库", "图片列表未能加载，请检查网络后重试。", loadManifest);
    } finally {
      if (manifestRequest === request) {
        manifestRequest = null;
        retryButton.disabled = false;
      }
    }
  }

  async function closeViewer() {
    if (closing) return;
    closing = true;
    closeButton.disabled = true;
    if (manifestRequest) manifestRequest.abort();
    if (currentFullscreenElement()) {
      try { await exitFullscreen(); } catch { /* Navigation also leaves fullscreen. */ }
    }
    let fromGitHub = false;
    try { fromGitHub = new URL(document.referrer).origin === "https://github.com"; } catch { /* Direct visit. */ }
    if (fromGitHub && history.length > 1) history.back();
    else location.replace(README_URL);
  }

  async function toggleFullscreen() {
    if (closing) return;
    try {
      if (currentFullscreenElement()) {
        leaveFullscreenFromToolbar = true;
        await exitFullscreen();
      } else {
        leaveFullscreenFromToolbar = false;
        const enter = document.documentElement.requestFullscreen || document.documentElement.webkitRequestFullscreen;
        await enter.call(document.documentElement);
      }
    } catch {
      leaveFullscreenFromToolbar = false;
      showNotice("浏览器暂未允许全屏，可以继续使用适应模式查看。");
      updateFullscreen();
    }
  }

  function updateFullscreen() {
    const fullscreen = Boolean(currentFullscreenElement());
    const leavingByBrowser = wasFullscreen && !fullscreen && !leaveFullscreenFromToolbar;
    fullscreenButton.setAttribute("aria-pressed", String(fullscreen));
    fullscreenButton.setAttribute("aria-label", fullscreen ? "退出全屏" : "进入全屏");
    fullscreenLabel.textContent = fullscreen ? "退出全屏" : "进入全屏";
    wasFullscreen = fullscreen;
    if (!fullscreen) leaveFullscreenFromToolbar = false;
    updateSize();
    // Browsers may consume Escape before keydown while in native fullscreen.
    if (leavingByBrowser && !closing) void closeViewer();
  }

  fitButton.addEventListener("click", () => setViewMode("fit"));
  actualButton.addEventListener("click", () => setViewMode("actual"));
  previousButton.addEventListener("click", () => renderImage(currentIndex - 1));
  nextButton.addEventListener("click", () => renderImage(currentIndex + 1));
  retryButton.addEventListener("click", () => retryAction());
  closeButton.addEventListener("click", () => { void closeViewer(); });
  fullscreenButton.addEventListener("click", () => { void toggleFullscreen(); });
  window.addEventListener("hashchange", () => { if (images.length) selectFromHash(); });
  window.addEventListener("resize", updateSize);
  document.addEventListener("fullscreenchange", updateFullscreen);
  document.addEventListener("webkitfullscreenchange", updateFullscreen);
  document.addEventListener("keydown", (event) => {
    if (event.altKey || event.ctrlKey || event.metaKey || closing) return;
    if (event.key === "Escape") {
      event.preventDefault();
      void closeViewer();
    } else if (images.length && (event.key === "ArrowLeft" || event.key === "ArrowRight")) {
      event.preventDefault();
      renderImage(currentIndex + (event.key === "ArrowLeft" ? -1 : 1));
    }
  });
  window.addEventListener("pagehide", () => {
    if (manifestRequest) manifestRequest.abort();
    clearTimeout(noticeTimer);
    releaseActiveImage();
  });
  window.addEventListener("pageshow", (event) => {
    if (event.persisted) {
      closing = false;
      closeButton.disabled = false;
      updateFullscreen();
      void loadManifest();
    }
  });

  if (!(document.documentElement.requestFullscreen || document.documentElement.webkitRequestFullscreen)) {
    fullscreenButton.disabled = true;
    fullscreenButton.title = "当前浏览器不支持全屏，可使用适应模式查看";
  }
  if (typeof ResizeObserver !== "undefined") {
    const observer = new ResizeObserver(updateSize);
    observer.observe(document.getElementById("toolbar"));
    observer.observe(document.getElementById("navigation"));
  }
  updateSize();
  closeButton.focus({ preventScroll: true });
  void loadManifest();
})();
