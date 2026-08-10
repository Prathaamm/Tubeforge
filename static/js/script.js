/**
 * TubeForge - script.js
 *
 * Frontend controller for the redesigned TubeForge interface.
 * Backend endpoints remain unchanged:
 *   POST /formats
 *   POST /jobs
 *   GET  /jobs/<id>/progress
 *   GET  /jobs/<id>/result
 */

(function () {
    "use strict";

    // -------------------------------------------------------------------------
    // DOM
    // -------------------------------------------------------------------------

    const form = document.getElementById("download-form");
    const urlInput = document.getElementById("url");

    const submitBtn = document.getElementById("submit-btn");
    const submitLabel = document.getElementById("submit-label");
    const spinner = document.getElementById("spinner");

    const statusEl = document.getElementById("status");

    const progressContainer = document.getElementById("progress-container");
    const progressFill = document.getElementById("progress-fill");
    const progressText = document.getElementById("progress-text");
    const progressStage = document.getElementById("progress-stage");
    const progressPercent = document.getElementById("progress-percent");

    const qualityWrapper = document.getElementById("quality-wrapper");
    const qualitySelect = document.getElementById("quality");
    const qualityStatus = document.getElementById("quality-status");

    const formatRadios = document.querySelectorAll('input[name="format"]');
    const checkBtn = document.getElementById("check-btn");

    const previewCard = document.getElementById("preview-card");
    const previewThumb = document.getElementById("preview-thumb");
    const previewTitle = document.getElementById("preview-title");


    // -------------------------------------------------------------------------
    // STATE
    // -------------------------------------------------------------------------

    let lastFetchedUrl = null;
    let currentVideo = null;
    let isSubmitting = false;

    let checkController = null;
    let checkRequestId = 0;


    // -------------------------------------------------------------------------
    // HELPERS
    // -------------------------------------------------------------------------

    function currentFormat() {
        const checked = form.querySelector('input[name="format"]:checked');
        return checked ? checked.value : "mp4";
    }


    function setStatus(message, kind) {
        statusEl.textContent = message || "";
        statusEl.classList.remove("success", "error");

        if (kind) {
            statusEl.classList.add(kind);
        }
    }


    function looksLikeYouTubeUrl(value) {
        try {
            const parsed = new URL(value);
            const host = parsed.hostname.toLowerCase();

            return (
                host === "youtube.com" ||
                host === "www.youtube.com" ||
                host === "m.youtube.com" ||
                host === "youtu.be"
            );
        } catch {
            return false;
        }
    }


    // -------------------------------------------------------------------------
    // QUALITY
    // -------------------------------------------------------------------------

    function resetQualityOptions() {
        qualitySelect.innerHTML =
            '<option value="">Best available</option>';
    }


    function updateQualityVisibility() {
        const isMp4 = currentFormat() === "mp4";
        qualityWrapper.style.display = isMp4 ? "block" : "none";

        if (!isMp4) {
            qualityStatus.textContent = "";
            qualityStatus.classList.remove("error");
        }
    }


    // -------------------------------------------------------------------------
    // PREVIEW
    // -------------------------------------------------------------------------

    function hidePreview() {
        previewCard.style.display = "none";
        previewThumb.src = "";
        previewThumb.alt = "";
        previewTitle.textContent = "";
    }


    function showPreview(title, thumbnail) {
        previewTitle.textContent = title || "YouTube Video";

        if (thumbnail) {
            previewThumb.src = thumbnail;
            previewThumb.alt = title
                ? `Thumbnail for ${title}`
                : "Video thumbnail";
        } else {
            previewThumb.src = "";
            previewThumb.alt = "";
        }

        previewCard.style.display = "flex";
    }


    // -------------------------------------------------------------------------
    // VIDEO STATE
    // -------------------------------------------------------------------------

    function resetVideoState() {
        currentVideo = null;
        lastFetchedUrl = null;

        resetQualityOptions();

        qualityStatus.textContent = "";
        qualityStatus.classList.remove("error");

        qualitySelect.disabled = true;

        hidePreview();
    }


    function handleUrlInputChange() {
        const currentUrl = urlInput.value.trim();

        if (currentUrl === lastFetchedUrl) {
            return;
        }

        if (checkController) {
            checkController.abort();
            checkController = null;
        }

        checkRequestId++;

        currentVideo = null;
        lastFetchedUrl = null;

        resetQualityOptions();
        qualitySelect.disabled = true;

        qualityStatus.textContent = "";
        qualityStatus.classList.remove("error");

        hidePreview();

        setStatus("");

        // Subtle visual feedback that the current input is not checked yet.
        urlInput.closest(".input-wrap")?.classList.remove("is-valid");
    }


    // -------------------------------------------------------------------------
    // CHECK VIDEO
    // -------------------------------------------------------------------------

    async function fetchQualities() {
        const url = urlInput.value.trim();

        if (!url) {
            resetVideoState();
            setStatus("Please paste a YouTube URL first.", "error");
            urlInput.focus();
            return;
        }

        if (!looksLikeYouTubeUrl(url)) {
            resetVideoState();
            setStatus("That doesn't look like a valid YouTube URL.", "error");
            urlInput.focus();
            return;
        }

        if (url === lastFetchedUrl && currentVideo) {
            setStatus("Video information is already loaded.", "success");
            return;
        }

        if (checkController) {
            checkController.abort();
        }

        checkController = new AbortController();
        const controller = checkController;
        const requestId = ++checkRequestId;

        currentVideo = null;
        lastFetchedUrl = null;

        resetQualityOptions();
        hidePreview();

        qualitySelect.disabled = true;

        qualityStatus.textContent = "Checking available qualities...";
        qualityStatus.classList.remove("error");

        setStatus("Checking video...");

        checkBtn.disabled = true;
        checkBtn.innerHTML = '<span class="btn-icon">◌</span><span>Checking...</span>';

        try {
            const response = await fetch("/formats", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "Cache-Control": "no-cache"
                },
                body: JSON.stringify({ url }),
                signal: controller.signal,
                cache: "no-store"
            });

            if (requestId !== checkRequestId) {
                return;
            }

            let data = {};

            try {
                data = await response.json();
            } catch {
                data = {};
            }

            if (!response.ok) {
                resetQualityOptions();

                currentVideo = null;
                lastFetchedUrl = null;

                hidePreview();

                qualityStatus.textContent =
                    data.error || "Couldn't check this video.";
                qualityStatus.classList.add("error");

                setStatus(
                    data.error || "Unable to load video information.",
                    "error"
                );

                return;
            }

            const qualities = Array.isArray(data.qualities)
                ? data.qualities
                : [];

            currentVideo = {
                ...data,
                qualities
            };

            resetQualityOptions();

            qualities.forEach((height) => {
                const option = document.createElement("option");
                option.value = String(height);
                option.textContent = `${height}p`;
                qualitySelect.appendChild(option);
            });

            if (qualities.length > 0) {
                qualityStatus.textContent =
                    `${qualities.length} qualities found`;
            } else {
                qualityStatus.textContent =
                    "Best available quality will be used.";
            }

            qualityStatus.classList.remove("error");

            if (data.title) {
                showPreview(data.title, data.thumbnail);
            } else {
                hidePreview();
            }

            lastFetchedUrl = url;

            urlInput.closest(".input-wrap")?.classList.add("is-valid");

            setStatus(
                "Video information loaded successfully.",
                "success"
            );

        } catch (err) {
            if (err?.name === "AbortError") {
                return;
            }

            if (requestId !== checkRequestId) {
                return;
            }

            currentVideo = null;
            lastFetchedUrl = null;

            resetQualityOptions();
            hidePreview();

            qualityStatus.textContent =
                "Couldn't check the video. Please try again.";
            qualityStatus.classList.add("error");

            setStatus(
                "Network error while checking the video.",
                "error"
            );

        } finally {
            if (requestId === checkRequestId) {
                qualitySelect.disabled = false;
                checkBtn.disabled = false;
                checkBtn.innerHTML =
                    '<span class="btn-icon">⌁</span><span>Check Video</span>';
                checkController = null;
            }
        }
    }


    // -------------------------------------------------------------------------
    // LOADING
    // -------------------------------------------------------------------------

    function setLoading(loading) {
        isSubmitting = loading;
        submitBtn.disabled = loading;

        spinner.classList.toggle("active", loading);

        submitLabel.textContent = loading
            ? "Working..."
            : "Download Media";
    }


    // -------------------------------------------------------------------------
    // PROGRESS
    // -------------------------------------------------------------------------

    function showProgress(percent, label, stage) {
        progressContainer.style.display = "block";

        const clamped = Math.min(
            100,
            Math.max(0, Number(percent) || 0)
        );

        progressFill.style.width = `${clamped}%`;
        progressPercent.textContent = `${Math.round(clamped)}%`;
        progressText.textContent = label || "";
        progressStage.textContent = stage || "Downloading";
    }


    function hideProgress() {
        progressContainer.style.display = "none";
        progressFill.style.width = "0%";
        progressPercent.textContent = "0%";
        progressText.textContent = "";
        progressStage.textContent = "Downloading";
    }


    // -------------------------------------------------------------------------
    // JOB POLLING
    // -------------------------------------------------------------------------

    function pollJob(jobId) {
        return new Promise((resolve) => {
            let stopped = false;

            const stop = () => {
                if (!stopped) {
                    stopped = true;
                    clearInterval(intervalId);
                }
            };

            const intervalId = setInterval(async () => {
                if (stopped) {
                    return;
                }

                try {
                    const res = await fetch(
                        `/jobs/${jobId}/progress`,
                        { cache: "no-store" }
                    );

                    if (!res.ok) {
                        stop();

                        setStatus(
                            "Lost track of this download. Please try again.",
                            "error"
                        );

                        hideProgress();
                        setLoading(false);
                        resolve(null);
                        return;
                    }

                    const data = await res.json();

                    if (data.status === "queued") {
                        showProgress(
                            0,
                            "Preparing your download...",
                            "Preparing"
                        );

                    } else if (data.status === "downloading") {
                        const percent = Number(data.percent) || 0;

                        showProgress(
                            percent,
                            `Downloading media... ${Math.round(percent)}%`,
                            "Downloading"
                        );

                    } else if (data.status === "converting") {
                        const percent = Number(data.percent) || 0;

                        showProgress(
                            Math.max(percent, 99),
                            "Merging and converting media...",
                            "Converting"
                        );

                    } else if (data.status === "done") {
                        stop();

                        showProgress(
                            100,
                            "Preparing your file...",
                            "Complete"
                        );

                        resolve(jobId);

                    } else if (data.status === "error") {
                        stop();

                        setStatus(
                            data.error || "Download failed.",
                            "error"
                        );

                        hideProgress();
                        setLoading(false);

                        resolve(null);
                    }

                } catch (err) {
                    stop();

                    setStatus(
                        "Network error while checking progress.",
                        "error"
                    );

                    hideProgress();
                    setLoading(false);

                    resolve(null);
                }
            }, 1000);
        });
    }


    // -------------------------------------------------------------------------
    // RESULT
    // -------------------------------------------------------------------------

    async function fetchResult(jobId, format) {
        try {
            const response = await fetch(
                `/jobs/${jobId}/result`,
                { cache: "no-store" }
            );

            if (!response.ok) {
                const data =
                    await response.json().catch(() => ({}));

                setStatus(
                    data.error || "Failed to retrieve the file.",
                    "error"
                );

                return;
            }

            const blob = await response.blob();

            const disposition =
                response.headers.get("Content-Disposition") || "";

            const match =
                disposition.match(/filename="?([^"]+)"?/);

            const filename =
                match
                    ? match[1]
                    : `download.${format}`;

            const downloadUrl =
                window.URL.createObjectURL(blob);

            const link =
                document.createElement("a");

            link.href = downloadUrl;
            link.download = filename;

            document.body.appendChild(link);
            link.click();
            link.remove();

            window.URL.revokeObjectURL(downloadUrl);

            setStatus(
                "Download complete — your file is ready.",
                "success"
            );

        } catch {
            setStatus(
                "Network error while downloading the file.",
                "error"
            );

        } finally {
            hideProgress();
            setLoading(false);
        }
    }


    // -------------------------------------------------------------------------
    // DOWNLOAD
    // -------------------------------------------------------------------------

    async function handleSubmit(event) {
        event.preventDefault();

        if (isSubmitting) {
            return;
        }

        const url = urlInput.value.trim();

        const selectedFormat =
            form.querySelector('input[name="format"]:checked');

        const format =
            selectedFormat
                ? selectedFormat.value
                : "mp4";

        const quality =
            format === "mp4"
                ? qualitySelect.value
                : "";

        if (!url) {
            setStatus(
                "Please paste a YouTube URL first.",
                "error"
            );
            urlInput.focus();
            return;
        }

        if (!looksLikeYouTubeUrl(url)) {
            setStatus(
                "That doesn't look like a valid YouTube URL.",
                "error"
            );
            urlInput.focus();
            return;
        }

        setLoading(true);
        setStatus("");

        showProgress(
            0,
            "Starting your download...",
            "Preparing"
        );

        try {
            const startResponse = await fetch(
                "/jobs",
                {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                        "Cache-Control": "no-cache"
                    },
                    body: JSON.stringify({
                        url,
                        format,
                        quality
                    }),
                    cache: "no-store"
                }
            );

            if (!startResponse.ok) {
                const data =
                    await startResponse
                        .json()
                        .catch(() => ({}));

                setStatus(
                    data.error ||
                    "Something went wrong. Please try again.",
                    "error"
                );

                hideProgress();
                setLoading(false);
                return;
            }

            const result = await startResponse.json();
            const jobId = result.job_id;

            if (!jobId) {
                setStatus(
                    "The server did not return a download job.",
                    "error"
                );

                hideProgress();
                setLoading(false);
                return;
            }

            const finishedJobId =
                await pollJob(jobId);

            if (finishedJobId) {
                await fetchResult(
                    finishedJobId,
                    format
                );
            }

        } catch {
            setStatus(
                "Network error. Is the server still running?",
                "error"
            );

            hideProgress();
            setLoading(false);
        }
    }


    // -------------------------------------------------------------------------
    // EVENTS
    // -------------------------------------------------------------------------

    if (form) {
        form.addEventListener("submit", handleSubmit);
    }

    if (checkBtn) {
        checkBtn.addEventListener("click", (event) => {
            event.preventDefault();
            fetchQualities();
        });
    }

    formatRadios.forEach((radio) => {
        radio.addEventListener("change", () => {
            updateQualityVisibility();
        });
    });

    if (urlInput) {
        urlInput.addEventListener(
            "input",
            handleUrlInputChange
        );

        urlInput.addEventListener("keydown", (event) => {
            if (
                event.key === "Enter" &&
                !event.shiftKey
            ) {
                event.preventDefault();
                fetchQualities();
            }
        });
    }


    // -------------------------------------------------------------------------
    // INITIALIZE
    // -------------------------------------------------------------------------

    updateQualityVisibility();
    qualitySelect.disabled = true;
    hidePreview();
    hideProgress();

})();
