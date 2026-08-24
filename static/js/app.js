/**
 * Omniconvert Studio — Frontend Application Controller
 */

document.addEventListener('DOMContentLoaded', () => {
  // Initialize Lucide Icons
  if (window.lucide) {
    lucide.createIcons();
  }

  // API Base Resolution (supports both local server and GitHub Pages / static hosting)
  const isLocalHost = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1';
  const customBackend = localStorage.getItem('omniconvert_backend_url');
  const API_BASE = isLocalHost ? '' : (customBackend || 'http://127.0.0.1:8000');

  function getApiUrl(path) {
    if (path.startsWith('http://') || path.startsWith('https://')) return path;
    if (!API_BASE) return path;
    return `${API_BASE.replace(/\/$/, '')}${path}`;
  }

  function getWsUrl(path) {
    if (API_BASE) {
      const isHttps = API_BASE.startsWith('https:');
      const host = API_BASE.replace(/^https?:\/\//, '').replace(/\/$/, '');
      return `${isHttps ? 'wss:' : 'ws:'}//${host}${path}`;
    }
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    return `${protocol}//${window.location.host}${path}`;
  }

  // State Management
  const state = {
    activeSourceType: 'upload', // 'upload' | 'url'
    sourceFile: null,
    sourceFileId: null,
    sourceUrl: null,
    sourceMetadata: null,
    targetFormat: 'mp3',
    formatCategory: 'audio',
    activeJobId: null,
    jobWs: null,
    pollingTimer: null,
    expiryInterval: null
  };

  // DOM Elements
  const tabUpload = document.getElementById('tabUpload');
  const tabUrl = document.getElementById('tabUrl');
  const uploadTabContent = document.getElementById('uploadTabContent');
  const urlTabContent = document.getElementById('urlTabContent');

  const dropZone = document.getElementById('dropZone');
  const fileInput = document.getElementById('fileInput');
  const browseFileBtn = document.getElementById('browseFileBtn');
  const uploadProgressContainer = document.getElementById('uploadProgressContainer');
  const uploadProgressBar = document.getElementById('uploadProgressBar');
  const uploadProgressVal = document.getElementById('uploadProgressVal');

  const urlInput = document.getElementById('urlInput');
  const pasteClipboardBtn = document.getElementById('pasteClipboardBtn');
  const fetchUrlBtn = document.getElementById('fetchUrlBtn');

  const sourcePreviewCard = document.getElementById('sourcePreviewCard');
  const clearSourceBtn = document.getElementById('clearSourceBtn');
  const previewTypeText = document.getElementById('previewTypeText');
  const previewTypeIcon = document.getElementById('previewTypeIcon');
  const sourceMediaTitle = document.getElementById('sourceMediaTitle');
  const sourceThumbnailImg = document.getElementById('sourceThumbnailImg');
  const sourceVideoPlayer = document.getElementById('sourceVideoPlayer');
  const sourceAudioPlayer = document.getElementById('sourceAudioPlayer');

  const metaSizeVal = document.getElementById('metaSizeVal');
  const metaDurationVal = document.getElementById('metaDurationVal');
  const metaFormatVal = document.getElementById('metaFormatVal');
  const metaResolutionVal = document.getElementById('metaResolutionVal');

  const formatGrid = document.getElementById('formatGrid');
  const formatPills = document.querySelectorAll('.format-pill');
  const filterPills = document.querySelectorAll('.filter-pill');

  const videoOptionsSection = document.getElementById('videoOptionsSection');
  const audioOptionsSection = document.getElementById('audioOptionsSection');
  const gifOptionsSection = document.getElementById('gifOptionsSection');

  const videoResolutionSelect = document.getElementById('videoResolutionSelect');
  const videoCodecSelect = document.getElementById('videoCodecSelect');
  const videoFpsSelect = document.getElementById('videoFpsSelect');
  const audioBitrateSelect = document.getElementById('audioBitrateSelect');
  const audioSampleRateSelect = document.getElementById('audioSampleRateSelect');
  const audioChannelsSelect = document.getElementById('audioChannelsSelect');
  const gifWidthSelect = document.getElementById('gifWidthSelect');
  const gifFpsSelect = document.getElementById('gifFpsSelect');

  const stripMetadataCheckbox = document.getElementById('stripMetadataCheckbox');
  const tosAgreementCheckbox = document.getElementById('tosAgreementCheckbox');
  const startConversionBtn = document.getElementById('startConversionBtn');

  const jobStatusOverlay = document.getElementById('jobStatusOverlay');
  const jobStatusTitle = document.getElementById('jobStatusTitle');
  const progressRingCircle = document.getElementById('progressRingCircle');
  const circlePercentText = document.getElementById('circlePercentText');
  const circleStageSub = document.getElementById('circleStageSub');
  const metricSpeedVal = document.getElementById('metricSpeedVal');
  const metricFpsVal = document.getElementById('metricFpsVal');
  const metricElapsedVal = document.getElementById('metricElapsedVal');
  const metricEtaVal = document.getElementById('metricEtaVal');
  const liveStatusDesc = document.getElementById('liveStatusDesc');
  const cancelJobBtn = document.getElementById('cancelJobBtn');

  const downloadHubOverlay = document.getElementById('downloadHubOverlay');
  const convertedVideoPlayer = document.getElementById('convertedVideoPlayer');
  const convertedAudioPlayer = document.getElementById('convertedAudioPlayer');
  const convertedGifViewer = document.getElementById('convertedGifViewer');
  const resultFormatText = document.getElementById('resultFormatText');
  const resultSizeText = document.getElementById('resultSizeText');
  const resultExpiryCountdown = document.getElementById('resultExpiryCountdown');
  const downloadFileBtn = document.getElementById('downloadFileBtn');
  const copyDownloadLinkBtn = document.getElementById('copyDownloadLinkBtn');
  const convertAnotherBtn = document.getElementById('convertAnotherBtn');

  const toastContainer = document.getElementById('toastContainer');

  // --- Helper: Toast Notification ---
  function showToast(message, type = 'info') {
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    
    let iconName = 'info';
    if (type === 'success') iconName = 'check-circle';
    if (type === 'error') iconName = 'alert-triangle';

    toast.innerHTML = `<i data-lucide="${iconName}"></i><span>${escapeHtml(message)}</span>`;
    toastContainer.appendChild(toast);
    
    if (window.lucide) lucide.createIcons();

    setTimeout(() => {
      toast.style.transition = 'opacity 0.3s ease, transform 0.3s ease';
      toast.style.opacity = '0';
      toast.style.transform = 'translateX(50px)';
      setTimeout(() => toast.remove(), 300);
    }, 4500);
  }

  function escapeHtml(str) {
    if (!str) return '';
    return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }

  function formatBytes(bytes) {
    if (!bytes || bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  }

  function formatTime(seconds) {
    if (!seconds || isNaN(seconds)) return '00:00';
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
  }

  // --- UI Validation State ---
  function checkReadyToConvert() {
    startConversionBtn.disabled = false;
  }

  tosAgreementCheckbox.addEventListener('change', checkReadyToConvert);
  checkReadyToConvert();

  // --- Tab Switching ---
  tabUpload.addEventListener('click', () => {
    state.activeSourceType = 'upload';
    tabUpload.classList.add('active');
    tabUrl.classList.remove('active');
    uploadTabContent.classList.add('active');
    urlTabContent.classList.remove('active');
    checkReadyToConvert();
  });

  tabUrl.addEventListener('click', () => {
    state.activeSourceType = 'url';
    tabUrl.classList.add('active');
    tabUpload.classList.remove('active');
    urlTabContent.classList.add('active');
    uploadTabContent.classList.remove('active');
    checkReadyToConvert();
  });

  // --- Drag & Drop Upload Handler ---
  browseFileBtn.addEventListener('click', () => fileInput.click());

  ['dragenter', 'dragover'].forEach(eventName => {
    dropZone.addEventListener(eventName, (e) => {
      e.preventDefault();
      e.stopPropagation();
      dropZone.classList.add('drag-over');
    });
  });

  ['dragleave', 'drop'].forEach(eventName => {
    dropZone.addEventListener(eventName, (e) => {
      e.preventDefault();
      e.stopPropagation();
      dropZone.classList.remove('drag-over');
    });
  });

  dropZone.addEventListener('drop', (e) => {
    const files = e.dataTransfer.files;
    if (files.length > 0) {
      handleFileUpload(files[0]);
    }
  });

  fileInput.addEventListener('change', (e) => {
    if (e.target.files.length > 0) {
      handleFileUpload(e.target.files[0]);
    }
  });

  // --- File Upload Execution with Magic Bytes Validation ---
  function handleFileUpload(file) {
    if (file.size > 500 * 1024 * 1024) {
      showToast('File exceeds maximum size limit of 500MB.', 'error');
      return;
    }

    if (!tosAgreementCheckbox.checked) {
      tosAgreementCheckbox.checked = true;
    }

    const formData = new FormData();
    formData.append('file', file);
    formData.append('tos_agreed', 'true');

    uploadProgressContainer.classList.remove('hidden');
    uploadProgressBar.style.width = '0%';
    uploadProgressVal.textContent = '0%';

    const xhr = new XMLHttpRequest();
    xhr.open('POST', getApiUrl('/api/upload'), true);

    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) {
        const percent = Math.round((e.loaded / e.total) * 100);
        uploadProgressBar.style.width = `${percent}%`;
        uploadProgressVal.textContent = `${percent}%`;
      }
    };

    xhr.onload = () => {
      uploadProgressContainer.classList.add('hidden');
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          const res = JSON.parse(xhr.responseText);
          state.sourceFile = file;
          state.sourceFileId = res.file_id;
          state.sourceMetadata = res;
          displaySourcePreview(res, 'upload');
          showToast(`Verified file format: ${res.detected_mime}`, 'success');
        } catch (err) {
          showToast('Invalid server response.', 'error');
        }
      } else {
        try {
          const errRes = JSON.parse(xhr.responseText);
          showToast(errRes.detail || 'Upload failed.', 'error');
        } catch (e) {
          showToast(`Upload failed (${xhr.statusText})`, 'error');
        }
      }
      checkReadyToConvert();
    };

    xhr.onerror = () => {
      uploadProgressContainer.classList.add('hidden');
      showToast('Network error during upload.', 'error');
    };

    xhr.send(formData);
  }

  // --- URL Auto-Fetch Handler ---
  pasteClipboardBtn.addEventListener('click', async () => {
    try {
      const text = await navigator.clipboard.readText();
      if (text) {
        urlInput.value = text.trim();
        showToast('Pasted URL from clipboard.', 'info');
      }
    } catch (e) {
      urlInput.focus();
    }
  });

  fetchUrlBtn.addEventListener('click', handleUrlFetch);
  urlInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') handleUrlFetch();
  });

  async function handleUrlFetch() {
    const url = urlInput.value.trim();
    if (!url) {
      showToast('Please enter a valid media URL.', 'error');
      return;
    }

    if (!tosAgreementCheckbox.checked) {
      tosAgreementCheckbox.checked = true;
    }

    fetchUrlBtn.disabled = true;
    fetchUrlBtn.innerHTML = `<i data-lucide="loader" class="animate-spin"></i> Inspecting Stream...`;
    if (window.lucide) lucide.createIcons();

    try {
      const res = await fetch(getApiUrl('/api/url/inspect'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: url, tos_agreed: true })
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || 'Failed to inspect URL.');
      }

      state.sourceUrl = url;
      state.sourceMetadata = data;
      displaySourcePreview(data, 'url');
      showToast(`Fetched media: ${data.title.slice(0, 40)}...`, 'success');
    } catch (err) {
      showToast(err.message, 'error');
    } finally {
      fetchUrlBtn.disabled = false;
      fetchUrlBtn.innerHTML = `<i data-lucide="sparkles"></i> Fetch Info`;
      if (window.lucide) lucide.createIcons();
      checkReadyToConvert();
    }
  }

  // --- Display Source Preview ---
  function displaySourcePreview(data, type) {
    sourcePreviewCard.classList.remove('hidden');
    sourceThumbnailImg.classList.add('hidden');
    sourceVideoPlayer.classList.add('hidden');
    sourceAudioPlayer.classList.add('hidden');

    if (type === 'upload') {
      dropZone.classList.add('hidden');
      sourceMediaTitle.textContent = data.filename || 'Uploaded File';
      metaSizeVal.textContent = formatBytes(data.size_bytes);
      metaDurationVal.textContent = formatTime(data.duration_seconds);
      metaFormatVal.textContent = (data.detected_ext || 'media').toUpperCase();

      const isVideo = data.media_type === 'video';
      previewTypeText.textContent = isVideo ? 'Video' : 'Audio';
      previewTypeIcon.setAttribute('data-lucide', isVideo ? 'video' : 'music');

      if (isVideo && data.probe && data.probe.video) {
        metaResolutionVal.textContent = data.probe.video.resolution || 'Auto';
      } else {
        metaResolutionVal.textContent = data.probe && data.probe.audio ? data.probe.audio.channels : 'Stereo';
      }

      // Preview Player Setup
      const objectUrl = URL.createObjectURL(state.sourceFile);
      if (isVideo) {
        sourceVideoPlayer.src = objectUrl;
        sourceVideoPlayer.classList.remove('hidden');
      } else {
        sourceAudioPlayer.src = objectUrl;
        sourceAudioPlayer.classList.remove('hidden');
      }

    } else {
      // URL Source
      urlTabContent.classList.add('hidden');
      sourceMediaTitle.textContent = data.title || 'Online Media';
      metaSizeVal.textContent = data.uploader || 'Web Stream';
      metaDurationVal.textContent = formatTime(data.duration);
      metaFormatVal.textContent = data.extractor || 'Web Video';
      metaResolutionVal.textContent = (data.available_resolutions && data.available_resolutions[0]) || 'HD';

      previewTypeText.textContent = data.has_video ? 'Video Stream' : 'Audio Stream';
      previewTypeIcon.setAttribute('data-lucide', data.has_video ? 'video' : 'music');

      if (data.thumbnail) {
        sourceThumbnailImg.src = data.thumbnail;
        sourceThumbnailImg.classList.remove('hidden');
      }
    }

    if (window.lucide) lucide.createIcons();
    checkReadyToConvert();
  }

  // Clear / Reset Source
  clearSourceBtn.addEventListener('click', () => {
    state.sourceFile = null;
    state.sourceFileId = null;
    state.sourceUrl = null;
    state.sourceMetadata = null;

    sourceVideoPlayer.pause();
    sourceVideoPlayer.removeAttribute('src');
    sourceAudioPlayer.pause();
    sourceAudioPlayer.removeAttribute('src');

    sourcePreviewCard.classList.add('hidden');
    dropZone.classList.remove('hidden');
    urlTabContent.classList.remove('hidden');
    fileInput.value = '';
    urlInput.value = '';

    checkReadyToConvert();
  });

  // --- Format Matrix & Filter Handling ---
  filterPills.forEach(pill => {
    pill.addEventListener('click', () => {
      filterPills.forEach(p => p.classList.remove('active'));
      pill.classList.add('active');
      const cat = pill.getAttribute('data-category');

      formatPills.forEach(fmtPill => {
        if (cat === 'all' || fmtPill.getAttribute('data-category') === cat) {
          fmtPill.style.display = 'flex';
        } else {
          fmtPill.style.display = 'none';
        }
      });
    });
  });

  formatPills.forEach(pill => {
    pill.addEventListener('click', () => {
      const fmt = pill.getAttribute('data-format');
      const cat = pill.getAttribute('data-category');
      selectFormat(fmt, cat);
    });
  });

  // --- Quick Presets Matrix Handler ---
  const presetChips = document.querySelectorAll('.preset-chip');

  function applyPreset(presetKey) {
    presetChips.forEach(c => c.classList.remove('active'));
    const matchedChip = document.querySelector(`.preset-chip[data-preset="${presetKey}"]`);
    if (matchedChip) matchedChip.classList.add('active');

    if (presetKey === 'mp3_master') {
      selectFormat('mp3', 'audio');
      if (audioBitrateSelect) audioBitrateSelect.value = '320k';
      showToast('Preset: 🎵 MP3 Studio Master (320 kbps)', 'info');
    } else if (presetKey === 'mp4_hd') {
      selectFormat('mp4', 'video');
      if (videoResolutionSelect) videoResolutionSelect.value = '1080p';
      if (videoCodecSelect) videoCodecSelect.value = 'libx264';
      showToast('Preset: 🎬 MP4 High Definition (1080p)', 'info');
    } else if (presetKey === 'webm_web') {
      selectFormat('webm', 'video');
      if (videoResolutionSelect) videoResolutionSelect.value = '720p';
      if (videoCodecSelect) videoCodecSelect.value = 'libvpx-vp9';
      showToast('Preset: ⚡ WebM Stream (720p VP9)', 'info');
    } else if (presetKey === 'gif_anim') {
      selectFormat('gif', 'animation');
      if (gifWidthSelect) gifWidthSelect.value = '480';
      if (gifFpsSelect) gifFpsSelect.value = '15';
      showToast('Preset: 🎨 2-Pass Animated GIF (480px)', 'info');
    }
  }

  function selectFormat(fmt, cat) {
    formatPills.forEach(p => {
      if (p.getAttribute('data-format') === fmt) {
        p.classList.add('active');
        p.style.display = 'flex';
      } else {
        p.classList.remove('active');
      }
    });

    state.targetFormat = fmt;
    state.formatCategory = cat;

    if (fmt === 'gif') {
      gifOptionsSection.classList.remove('hidden');
      videoOptionsSection.classList.add('hidden');
      audioOptionsSection.classList.add('hidden');
    } else if (cat === 'video') {
      videoOptionsSection.classList.remove('hidden');
      audioOptionsSection.classList.remove('hidden');
      gifOptionsSection.classList.add('hidden');
    } else {
      audioOptionsSection.classList.remove('hidden');
      videoOptionsSection.classList.add('hidden');
      gifOptionsSection.classList.add('hidden');
    }
  }

  presetChips.forEach(chip => {
    chip.addEventListener('click', () => {
      const presetKey = chip.getAttribute('data-preset');
      applyPreset(presetKey);
    });
  });

  // --- Demo Sample Triggers ---
  const loadDemoUploadBtn = document.getElementById('loadDemoUploadBtn');
  const loadDemoUrlBtn = document.getElementById('loadDemoUrlBtn');

  if (loadDemoUploadBtn) {
    loadDemoUploadBtn.addEventListener('click', () => {
      // Create a lightweight demo WAV audio file
      const sampleWavBytes = createSampleWav();
      const sampleFile = new File([sampleWavBytes], 'omniconvert_demo_sample.wav', { type: 'audio/wav' });
      handleFileUpload(sampleFile);
      showToast('Loaded demo sample audio clip!', 'success');
    });
  }

  if (loadDemoUrlBtn) {
    loadDemoUrlBtn.addEventListener('click', () => {
      urlInput.value = 'https://www.youtube.com/watch?v=jNQXAC9IVRw'; // "Me at the zoo"
      handleUrlFetch();
    });
  }

  function createSampleWav() {
    // Generate valid 0.5s 440Hz sine wave WAV file in memory
    const sampleRate = 8000;
    const duration = 0.5;
    const numSamples = Math.floor(sampleRate * duration);
    const buffer = new ArrayBuffer(44 + numSamples * 2);
    const view = new DataView(buffer);

    function writeString(offset, string) {
      for (let i = 0; i < string.length; i++) {
        view.setUint8(offset + i, string.charCodeAt(i));
      }
    }

    writeString(0, 'RIFF');
    view.setUint32(4, 36 + numSamples * 2, true);
    writeString(8, 'WAVE');
    writeString(12, 'fmt ');
    view.setUint32(16, 16, true);
    view.setUint16(20, 1, true); // PCM
    view.setUint16(22, 1, true); // Mono
    view.setUint32(24, sampleRate, true);
    view.setUint32(28, sampleRate * 2, true);
    view.setUint16(32, 2, true);
    view.setUint16(34, 16, true);
    writeString(36, 'data');
    view.setUint32(40, numSamples * 2, true);

    for (let i = 0; i < numSamples; i++) {
      const sample = Math.sin((i / sampleRate) * 440 * 2 * Math.PI) * 0.5;
      view.setInt16(44 + i * 2, sample < 0 ? sample * 0x8000 : sample * 0x7FFF, true);
    }
    return new Blob([view], { type: 'audio/wav' });
  }

  // --- Conversion Execution & Real-Time Tracking ---
  startConversionBtn.addEventListener('click', async () => {
    tosAgreementCheckbox.checked = true;

    const isUpload = state.activeSourceType === 'upload';
    
    // Auto-prompt / fallbacks if no source loaded
    if (isUpload && !state.sourceFileId) {
      showToast('Select a file to convert, or click "Try with Demo Media Sample"', 'info');
      fileInput.click();
      return;
    }
    if (!isUpload && !state.sourceUrl) {
      if (urlInput.value.trim()) {
        await handleUrlFetch();
        if (!state.sourceMetadata) return;
      } else {
        urlInput.value = 'https://www.youtube.com/watch?v=jNQXAC9IVRw';
        await handleUrlFetch();
        if (!state.sourceMetadata) return;
      }
    }

    // Build Options Object
    const options = {
      resolution: videoResolutionSelect.value,
      video_codec: videoCodecSelect.value,
      fps: videoFpsSelect.value ? parseInt(videoFpsSelect.value) : null,
      audio_bitrate: audioBitrateSelect.value,
      audio_sample_rate: audioSampleRateSelect.value ? parseInt(audioSampleRateSelect.value) : null,
      audio_channels: parseInt(audioChannelsSelect.value),
      strip_metadata: stripMetadataCheckbox.checked,
      gif_width: parseInt(gifWidthSelect.value),
      gif_fps: parseInt(gifFpsSelect.value)
    };

    const payload = {
      source_type: state.activeSourceType,
      target_format: state.targetFormat,
      options: options,
      file_id: state.sourceFileId,
      url: state.sourceUrl,
      original_filename: state.sourceFile ? state.sourceFile.name : (state.sourceMetadata ? state.sourceMetadata.title : 'media'),
      tos_agreed: true
    };

    startConversionBtn.disabled = true;

    try {
      const res = await fetch(getApiUrl('/api/jobs/create'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || 'Could not queue conversion job.');
      }

      state.activeJobId = data.job_id;
      showProgressOverlay(data);
      initJobTracking(data.job_id);

    } catch (err) {
      showToast(err.message, 'error');
      startConversionBtn.disabled = false;
    }
  });

  // --- Show Progress Modal ---
  function showProgressOverlay(job) {
    jobStatusOverlay.classList.remove('hidden');
    jobStatusTitle.textContent = `Transcoding to ${job.target_format.toUpperCase()}...`;
    updateProgressUI(job);
  }

  function updateProgressUI(job) {
    const percent = Math.min(100, Math.max(0, job.progress_percent || 0));
    circlePercentText.textContent = `${Math.round(percent)}%`;
    circleStageSub.textContent = job.status || 'Processing';

    // SVG Ring Stroke Offset (circumference = 2 * PI * 70 = ~440)
    const offset = 440 - (percent / 100) * 440;
    progressRingCircle.style.strokeDashoffset = offset;

    metricSpeedVal.textContent = job.speed || '1.0x';
    metricFpsVal.textContent = job.fps ? `${job.fps} FPS` : '--';
    metricElapsedVal.textContent = formatTime(job.time_elapsed || 0);
    metricEtaVal.textContent = job.eta_seconds ? `${Math.round(job.eta_seconds)}s` : 'Finishing...';
    liveStatusDesc.textContent = job.stage || 'Transcoding stream...';

    if (job.status === 'completed') {
      cleanupJobTracking();
      jobStatusOverlay.classList.add('hidden');
      showDownloadHub(job);
    } else if (job.status === 'failed' || job.status === 'cancelled') {
      cleanupJobTracking();
      jobStatusOverlay.classList.add('hidden');
      startConversionBtn.disabled = false;
      showToast(job.error_message || 'Conversion was stopped.', 'error');
    }
  }

  // --- Real-Time WebSocket & Polling Tracking Engine ---
  function initJobTracking(jobId) {
    const wsUrl = getWsUrl(`/api/ws/${jobId}`);

    try {
      state.jobWs = new WebSocket(wsUrl);

      state.jobWs.onmessage = (event) => {
        try {
          const job = JSON.parse(event.data);
          updateProgressUI(job);
        } catch (e) {}
      };

      state.jobWs.onerror = () => {
        startPollingFallback(jobId);
      };

      state.jobWs.onclose = () => {
        startPollingFallback(jobId);
      };
    } catch (e) {
      startPollingFallback(jobId);
    }
  }

  function startPollingFallback(jobId) {
    if (state.pollingTimer) return;
    state.pollingTimer = setInterval(async () => {
      try {
        const res = await fetch(getApiUrl(`/api/jobs/${jobId}`));
        if (res.ok) {
          const job = await res.json();
          updateProgressUI(job);
        }
      } catch (e) {}
    }, 1000);
  }

  function cleanupJobTracking() {
    if (state.jobWs) {
      state.jobWs.close();
      state.jobWs = null;
    }
    if (state.pollingTimer) {
      clearInterval(state.pollingTimer);
      state.pollingTimer = null;
    }
  }

  // --- Cancel Job ---
  cancelJobBtn.addEventListener('click', async () => {
    if (!state.activeJobId) return;
    try {
      await fetch(getApiUrl(`/api/jobs/${state.activeJobId}/cancel`), { method: 'POST' });
      showToast('Cancellation requested.', 'info');
    } catch (e) {}
  });

  // --- Download Results Hub ---
  function showDownloadHub(job) {
    downloadHubOverlay.classList.remove('hidden');
    resultFormatText.textContent = (job.target_format || 'MP4').toUpperCase();
    resultSizeText.textContent = formatBytes(job.output_size_bytes);

    convertedVideoPlayer.classList.add('hidden');
    convertedAudioPlayer.classList.add('hidden');
    convertedGifViewer.classList.add('hidden');

    const downloadFullUrl = getApiUrl(job.download_url);
    downloadFileBtn.href = downloadFullUrl;
    downloadFileBtn.setAttribute('download', job.output_filename || 'media');

    // Converted Preview
    const isVideo = ['mp4', 'webm', 'mov', 'mkv', 'avi'].includes(job.target_format);
    const isGif = job.target_format === 'gif';
    const isAudio = ['mp3', 'wav', 'aac', 'flac', 'ogg', 'm4a'].includes(job.target_format);

    if (isGif) {
      convertedGifViewer.src = downloadFullUrl;
      convertedGifViewer.classList.remove('hidden');
    } else if (isVideo) {
      convertedVideoPlayer.src = downloadFullUrl;
      convertedVideoPlayer.classList.remove('hidden');
    } else if (isAudio) {
      convertedAudioPlayer.src = downloadFullUrl;
      convertedAudioPlayer.classList.remove('hidden');
    }

    // Expiry Countdown (1 hour TTL)
    if (state.expiryInterval) clearInterval(state.expiryInterval);
    let expirySecs = job.expires_at ? Math.max(0, Math.floor(job.expires_at - (Date.now() / 1000))) : 3600;

    function tickExpiry() {
      if (expirySecs <= 0) {
        resultExpiryCountdown.textContent = 'Expired';
        clearInterval(state.expiryInterval);
        return;
      }
      resultExpiryCountdown.textContent = formatTime(expirySecs);
      expirySecs--;
    }
    tickExpiry();
    state.expiryInterval = setInterval(tickExpiry, 1000);

    // Setup Copy Link
    copyDownloadLinkBtn.onclick = () => {
      const origin = API_BASE || window.location.origin;
      const fullUrl = `${origin.replace(/\/$/, '')}${job.download_url}`;
      navigator.clipboard.writeText(fullUrl).then(() => {
        showToast('Signed download link copied to clipboard!', 'success');
      });
    };
  }

  // Convert Another File Reset
  convertAnotherBtn.addEventListener('click', () => {
    downloadHubOverlay.classList.add('hidden');
    convertedVideoPlayer.pause();
    convertedVideoPlayer.removeAttribute('src');
    convertedAudioPlayer.pause();
    convertedAudioPlayer.removeAttribute('src');

    clearSourceBtn.click();
    startConversionBtn.disabled = true;
  });

});
