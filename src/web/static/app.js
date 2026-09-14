document.addEventListener('DOMContentLoaded', () => {
  // Elements
  const form = document.getElementById('generate-form');
  const promptInput = document.getElementById('prompt-input');
  const toneSelect = document.getElementById('tone-select');
  const voiceSelect = document.getElementById('voice-select');
  const sceneDurationSelect = document.getElementById('scene-duration-select');
  const maxScenesSelect = document.getElementById('max-scenes-select');
  const maxVideoDurationSelect = document.getElementById('max-video-duration-select');
  const autoPublishToggle = document.getElementById('auto-publish-toggle');
  const generateBtn = document.getElementById('generate-btn');

  const geminiModelLabel = document.getElementById('gemini-model-label');
  const tiktokStatusLabel = document.getElementById('tiktok-status-label');

  const progressContainer = document.getElementById('progress-container');
  const progressFill = document.getElementById('progress-fill');
  const progressPct = document.getElementById('progress-pct');
  const currentStageName = document.getElementById('current-stage-name');
  const currentStageMsg = document.getElementById('current-stage-msg');

  const previewPlaceholder = document.getElementById('preview-placeholder');
  const videoWrapper = document.getElementById('video-wrapper');
  const renderedVideo = document.getElementById('rendered-video');

  const metadataPanel = document.getElementById('metadata-panel');
  const metaTitle = document.getElementById('meta-title');
  const metaCaption = document.getElementById('meta-caption');
  const metaTags = document.getElementById('meta-tags');
  const metaHook = document.getElementById('meta-hook');
  const downloadBtn = document.getElementById('download-btn');
  const postTiktokBtn = document.getElementById('post-tiktok-btn');
  const deleteVideoBtn = document.getElementById('delete-video-btn');
  const cleanAllBtn = document.getElementById('clean-all-btn');
  const publishStatusBox = document.getElementById('publish-status-box');

  let activeJobId = null;
  let isJobCompleted = false;

  // 1. Initial Status Check
  fetch('/api/status')
    .then(r => r.json())
    .then(data => {
      geminiModelLabel.textContent = data.gemini_configured ? `${data.gemini_model} + ${data.video_model}` : 'Simulated / Ready';
      tiktokStatusLabel.textContent = data.tiktok_dry_run ? 'Dry-Run (Active)' : 'Direct API';

      // If a completed video already exists on the server, load and display it immediately
      if (data.latest_video && previewPlaceholder.style.display !== 'none' && !activeJobId) {
        const lv = data.latest_video;
        activeJobId = lv.video_id;
        previewPlaceholder.style.display = 'none';
        videoWrapper.style.display = 'block';

        const directStreamUrl = `/api/video/${lv.video_id}`;
        const staticUrl = `/static/output/${lv.video_id}/${lv.filename}`;

        renderedVideo.innerHTML = `
          <source src="${directStreamUrl}" type="video/mp4">
          <source src="${staticUrl}" type="video/mp4">
          Your browser does not support HTML5 video playback.
        `;
        renderedVideo.load();

        downloadBtn.href = directStreamUrl;
        downloadBtn.download = lv.filename;
        metadataPanel.style.display = 'flex';
        metaTitle.textContent = `Latest Render (${lv.video_id})`;
        metaCaption.textContent = `Pre-rendered video loaded from output directory (${lv.size_mb} MB).`;
      }
    })
    .catch(err => {
      console.warn('Status check failed:', err);
      geminiModelLabel.textContent = 'Active';
      tiktokStatusLabel.textContent = 'Dry-Run';
    });

  // 2. Chip click handlers
  document.querySelectorAll('.chip').forEach(chip => {
    chip.addEventListener('click', () => {
      promptInput.value = chip.dataset.prompt;
      promptInput.focus();
    });
  });

  // Stage mapping for stepper
  const stageOrder = ['SCRIPTING', 'AUDIO', 'VISUALS', 'COMPOSITING', 'PUBLISHING'];

  function updateStepper(currentStage) {
    let passedCurrent = false;
    stageOrder.forEach(stageKey => {
      const el = document.getElementById(`step-${stageKey}`);
      if (!el) return;

      if (stageKey === currentStage) {
        el.className = 'stage-step active';
        passedCurrent = true;
      } else if (!passedCurrent) {
        el.className = 'stage-step completed';
      } else {
        el.className = 'stage-step';
      }
    });
  }

  // 3. Form Submit
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const prompt = promptInput.value.trim();
    if (!prompt) return;

    // Reset UI
    isJobCompleted = false;
    generateBtn.disabled = true;
    generateBtn.querySelector('.btn-text').textContent = 'Pipeline Running...';
    progressContainer.style.display = 'block';
    progressFill.style.width = '5%';
    progressPct.textContent = '5%';
    currentStageName.textContent = 'INITIALIZING';
    currentStageMsg.textContent = 'Starting generation pipeline...';
    publishStatusBox.style.display = 'none';

    try {
      const maxSceneDuration = sceneDurationSelect ? parseFloat(sceneDurationSelect.value) : 4.0;
      const maxScenes = maxScenesSelect ? parseInt(maxScenesSelect.value, 10) : 5;
      const maxVideoDuration = maxVideoDurationSelect ? parseFloat(maxVideoDurationSelect.value) : 30.0;

      const response = await fetch('/api/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          prompt,
          tone: toneSelect.value,
          voice: voiceSelect.value,
          max_scene_duration: maxSceneDuration,
          max_scenes: maxScenes,
          max_video_duration: maxVideoDuration,
          auto_publish: autoPublishToggle.checked,
        }),
      });

      if (!response.ok) {
        throw new Error(`Failed to start job: ${response.statusText}`);
      }

      const { job_id } = await response.json();
      activeJobId = job_id;
      connectToProgressStream(job_id);

    } catch (err) {
      console.error(err);
      alert(`Error starting pipeline: ${err.message}`);
      generateBtn.disabled = false;
      generateBtn.querySelector('.btn-text').textContent = 'Generate Video Pipeline';
    }
  });

  // 4. SSE Progress Stream with Polling Fallback
  function connectToProgressStream(jobId) {
    const eventSource = new EventSource(`/api/progress/${jobId}`);

    eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        const { stage, percent, message, result, error } = data;

        if (percent !== undefined) {
          progressFill.style.width = `${percent}%`;
          progressPct.textContent = `${percent}%`;
        }

        if (stage) {
          currentStageName.textContent = stage;
          updateStepper(stage);
        }

        if (message) {
          currentStageMsg.textContent = message;
        }

        if (stage === 'COMPLETED') {
          isJobCompleted = true;
          eventSource.close();
          if (result) {
            onPipelineCompleted(result);
          } else {
            pollJobStatus(jobId);
          }
        } else if (stage === 'FAILED') {
          eventSource.close();
          generateBtn.disabled = false;
          generateBtn.querySelector('.btn-text').textContent = 'Generate Video Pipeline';
          currentStageMsg.textContent = `Pipeline failed: ${error || 'Unknown error'}`;
        }
      } catch (e) {
        console.error('Error parsing SSE event:', e);
      }
    };

    eventSource.onerror = (err) => {
      console.warn('SSE stream disconnected or ended, checking job status...', err);
      eventSource.close();
      if (!isJobCompleted) {
        pollJobStatus(jobId);
      }
    };
  }

  // Polling fallback if SSE connection closes or drops
  async function pollJobStatus(jobId, attempts = 0) {
    if (isJobCompleted || attempts > 30) return;
    try {
      const res = await fetch(`/api/job/${jobId}`);
      if (res.ok) {
        const job = await res.json();
        if (job.status === 'COMPLETED' && job.result) {
          isJobCompleted = true;
          onPipelineCompleted(job.result);
          return;
        } else if (job.status === 'COMPLETED') {
          // If result not directly attached, construct it from job_id
          isJobCompleted = true;
          onPipelineCompleted({
            video_id: jobId,
            video_url: `/api/video/${jobId}`,
            plan: job.meta && job.meta.plan ? job.meta.plan : {
              tiktok_title: 'AI Generated Video',
              tiktok_caption: 'Check out this generated video!',
              hook: 'Hook generated',
              hashtags: ['#fyp', '#viral'],
            }
          });
          return;
        } else if (job.status === 'FAILED') {
          generateBtn.disabled = false;
          generateBtn.querySelector('.btn-text').textContent = 'Generate Video Pipeline';
          currentStageMsg.textContent = `Pipeline failed: ${job.error || 'Unknown error'}`;
          return;
        } else if (job.percent !== undefined) {
          progressFill.style.width = `${job.percent}%`;
          progressPct.textContent = `${job.percent}%`;
          if (job.stage) {
            currentStageName.textContent = job.stage;
            updateStepper(job.stage);
          }
          if (job.last_message) {
            currentStageMsg.textContent = job.last_message;
          }
        }
      }
    } catch (e) {
      console.warn('Polling error:', e);
    }

    if (!isJobCompleted) {
      setTimeout(() => pollJobStatus(jobId, attempts + 1), 3000);
    }
  }

  // 5. Completion Handler
  function onPipelineCompleted(result) {
    isJobCompleted = true;
    generateBtn.disabled = false;
    generateBtn.querySelector('.btn-text').textContent = 'Generate Video Pipeline';
    progressFill.style.width = '100%';
    progressPct.textContent = '100%';
    currentStageName.textContent = 'READY';
    currentStageMsg.textContent = 'Video rendering finished! Ready to preview.';

    // Set all steps to completed
    stageOrder.forEach(stageKey => {
      const el = document.getElementById(`step-${stageKey}`);
      if (el) el.className = 'stage-step completed';
    });

    // Ensure robust video playback URL
    const videoStreamUrl = result.video_url.startsWith('/api/video/')
      ? `${result.video_url}?t=${Date.now()}`
      : `/api/video/${result.video_id}?t=${Date.now()}`;

    // Mount Video & Metadata
    const vidId = result.video_id;
    activeJobId = vidId;

    // Prefer direct stream URL, fallback to static output path if needed
    const primaryUrl = `/api/video/${vidId}?t=${Date.now()}`;
    const fallbackStaticUrl = result.video_url && result.video_url.startsWith('/static/')
      ? result.video_url
      : `/static/output/${vidId}/${vidId}_final.mp4`;

    previewPlaceholder.style.display = 'none';
    videoWrapper.style.display = 'block';

    // Re-create or reset video source elements cleanly
    renderedVideo.pause();
    renderedVideo.removeAttribute('src');
    renderedVideo.innerHTML = `
      <source src="${primaryUrl}" type="video/mp4">
      <source src="${fallbackStaticUrl}" type="video/mp4">
      Your browser does not support HTML5 video playback.
    `;
    renderedVideo.load();

    // Auto-play when ready
    renderedVideo.oncanplay = () => {
      renderedVideo.play().catch(e => console.log('Autoplay deferred until user interaction:', e));
    };
    renderedVideo.onerror = (e) => {
      console.warn('Video tag stream notice, attempting direct fallback src...', e);
      renderedVideo.src = fallbackStaticUrl;
      renderedVideo.load();
    };

    // Populate Metadata
    const plan = result.plan;
    metaTitle.textContent = plan.tiktok_title || 'AI Generated Video';
    metaCaption.textContent = plan.tiktok_caption || '';
    metaHook.textContent = `"${plan.hook}"`;

    // Tags
    metaTags.innerHTML = '';
    (plan.hashtags || []).forEach(tag => {
      const span = document.createElement('span');
      span.className = 'tag-badge';
      span.textContent = tag.startsWith('#') ? tag : `#${tag}`;
      metaTags.appendChild(span);
    });

    // Download Link
    downloadBtn.href = videoStreamUrl;
    downloadBtn.download = `${result.video_id}_tiktok.mp4`;

    metadataPanel.style.display = 'flex';

    // If auto-published, display publish notice
    if (result.publish_result) {
      displayPublishResult(result.publish_result);
    }
  }

  // 6. Manual Publish to TikTok
  postTiktokBtn.addEventListener('click', async () => {
    if (!activeJobId) return;

    postTiktokBtn.disabled = true;
    postTiktokBtn.textContent = 'Posting to TikTok...';
    publishStatusBox.style.display = 'none';

    try {
      const res = await fetch(`/api/publish/${activeJobId}`, { method: 'POST' });
      const pubResult = await res.json();
      displayPublishResult(pubResult);
    } catch (err) {
      displayPublishResult({
        success: false,
        message: `Publishing error: ${err.message}`,
      });
    } finally {
      postTiktokBtn.disabled = false;
      postTiktokBtn.innerHTML = `
        <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
          <path d="M19.59 6.69a4.83 4.83 0 0 1-3.77-4.25V2h-3.45v13.67a2.89 2.89 0 0 1-5.2 1.74 2.89 2.89 0 0 1 2.31-4.64c.29 0 .58.04.85.12V9.41a6.33 6.33 0 0 0-.85-.06 6.34 6.34 0 0 0-6.34 6.34 6.34 6.34 0 0 0 6.34 6.34 6.34 6.34 0 0 0 6.34-6.34V8.53a8.28 8.28 0 0 0 4.77 1.52V6.69z"/>
        </svg>
        Post to TikTok
      `;
    }
  });

  // 7. Delete Active Video Output Files
  if (deleteVideoBtn) {
    deleteVideoBtn.addEventListener('click', async () => {
      if (!activeJobId) return;

      const confirmed = confirm("Are you sure you want to delete all output files for this video from disk?");
      if (!confirmed) return;

      deleteVideoBtn.disabled = true;
      deleteVideoBtn.textContent = 'Deleting...';

      try {
        const res = await fetch(`/api/output/${activeJobId}`, { method: 'DELETE' });
        const data = await res.json();

        if (data.success) {
          // Reset Preview
          if (renderedVideo) {
            renderedVideo.pause();
            renderedVideo.removeAttribute('src');
            renderedVideo.load();
          }
          videoWrapper.style.display = 'none';
          previewPlaceholder.style.display = 'block';
          metadataPanel.style.display = 'none';

          // Reset Progress
          progressContainer.style.display = 'none';
          stageOrder.forEach(stageKey => {
            const el = document.getElementById(`step-${stageKey}`);
            if (el) el.className = 'stage-step';
          });

          activeJobId = null;
          alert(data.message || "Video files deleted from output directory.");
        } else {
          alert(`Could not delete files: ${data.detail || 'Unknown error'}`);
        }
      } catch (err) {
        alert(`Error deleting files: ${err.message}`);
      } finally {
        deleteVideoBtn.disabled = false;
        deleteVideoBtn.innerHTML = `
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polyline points="3 6 5 6 21 6"></polyline>
            <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
            <line x1="10" y1="11" x2="10" y2="17"></line>
            <line x1="14" y1="11" x2="14" y2="17"></line>
          </svg>
          Delete Files
        `;
      }
    });
  }

  // 8. Clean Entire Output Directory
  if (cleanAllBtn) {
    cleanAllBtn.addEventListener('click', async () => {
      const confirmed = confirm("Are you sure you want to delete ALL generated videos and assets in the output folder?");
      if (!confirmed) return;

      cleanAllBtn.disabled = true;
      const originalText = cleanAllBtn.querySelector('span').textContent;
      cleanAllBtn.querySelector('span').textContent = 'Cleaning...';

      try {
        const res = await fetch('/api/output/clean-all', { method: 'POST' });
        const data = await res.json();

        // Reset Preview
        if (renderedVideo) {
          renderedVideo.pause();
          renderedVideo.removeAttribute('src');
          renderedVideo.load();
        }
        videoWrapper.style.display = 'none';
        previewPlaceholder.style.display = 'block';
        metadataPanel.style.display = 'none';
        progressContainer.style.display = 'none';

        stageOrder.forEach(stageKey => {
          const el = document.getElementById(`step-${stageKey}`);
          if (el) el.className = 'stage-step';
        });

        activeJobId = null;
        alert(data.message || "All output files purged.");
      } catch (err) {
        alert(`Error cleaning output directory: ${err.message}`);
      } finally {
        cleanAllBtn.disabled = false;
        cleanAllBtn.querySelector('span').textContent = originalText;
      }
    });
  }

  function displayPublishResult(pubResult) {
    publishStatusBox.style.display = 'block';
    if (pubResult.success) {
      publishStatusBox.className = 'publish-status-box success';
      publishStatusBox.innerHTML = `<strong>Success (${pubResult.status}):</strong> ${pubResult.message}`;
    } else {
      publishStatusBox.className = 'publish-status-box error';
      publishStatusBox.innerHTML = `<strong>Notice:</strong> ${pubResult.message}`;
    }
  }
});
