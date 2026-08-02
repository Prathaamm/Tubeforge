/**
 * script.js
 *
 * Handles the download form: client-side validation, loading states,
 * submitting to the backend, and triggering the file download.
 *
 * Vanilla JS only -- no frameworks, no build step.
 */

(function () {
    "use strict";

    const form = document.getElementById("download-form");
    const urlInput = document.getElementById("url");
    const submitBtn = document.getElementById("submit-btn");
    const submitLabel = document.getElementById("submit-label");
    const spinner = document.getElementById("spinner");
    const statusEl = document.getElementById("status");
    const qualityWrapper = document.getElementById("quality-wrapper");
    const qualitySelect = document.getElementById("quality");
    const qualityStatus = document.getElementById("quality-status");
    const formatRadios = document.querySelectorAll('input[name="format"]');

    let lastFetchedUrl = null;

    function currentFormat() {
        const checked = form.querySelector('input[name="format"]:checked');
        return checked ? checked.value : "mp4";
    }

    function updateQualityVisibility() {
        const isMp4 = currentFormat() === "mp4";
        qualityWrapper.style.display = isMp4 ? "block" : "none";
        if (!isMp4) {
            qualityStatus.textContent = "";
            qualityStatus.classList.remove("error");
        }
    }

    function resetQualityOptions() {
        qualitySelect.innerHTML = '<option value="">Best available</option>';
    }

    async function fetchQualities() {
        const url = urlInput.value.trim();

        if (!url || !looksLikeYouTubeUrl(url)) {
            return;
        }
        if (url === lastFetchedUrl) {
            return;
        }
        if (currentFormat() !== "mp4") {
            return;
        }

        resetQualityOptions();
        qualitySelect.disabled = true;
        qualityStatus.textContent = "Checking available qualities...";
        qualityStatus.classList.remove("error");

        try {
            const response = await fetch("/formats", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ url: url }),
            });

            resetQualityOptions();

            if (!response.ok) {
                qualityStatus.textContent = "Couldn't check qualities -- best available only.";
                qualityStatus.classList.add("error");
                return;
            }

            const data = await response.json();
            const qualities = data.qualities || [];

            qualities.forEach((height) => {
                const option = document.createElement("option");
                option.value = String(height);
                option.textContent = `${height}p`;
                qualitySelect.appendChild(option);
            });

            qualityStatus.textContent = qualities.length
                ? `${qualities.length} qualities found`
                : "Only best available for this video";

            lastFetchedUrl = url;
        } catch (err) {
            resetQualityOptions();
            qualityStatus.textContent = "Couldn't check qualities -- best available only.";
            qualityStatus.classList.add("error");
        } finally {
            qualitySelect.disabled = false;
        }
    }

    let isSubmitting = false;

    const PROGRESS_STEPS = [
        "Initializing...",
        "Fetching metadata...",
        "Downloading...",
        "Converting...",
        "Preparing download...",
    ];

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
        } catch (err) {
            return false;
        }
    }

    function setStatus(message, kind) {
        statusEl.textContent = message;
        statusEl.classList.remove("success", "error");
        if (kind) {
            statusEl.classList.add(kind);
        }
    }

    function setLoading(loading) {
        isSubmitting = loading;
        submitBtn.disabled = loading;
        spinner.classList.toggle("active", loading);
        submitLabel.textContent = loading ? "Working..." : "Download";
    }

    function startProgressMessages() {
        let index = 0;
        setStatus(PROGRESS_STEPS[index]);
        const intervalId = setInterval(() => {
            index += 1;
            if (index < PROGRESS_STEPS.length) {
                setStatus(PROGRESS_STEPS[index]);
            }
        }, 1400);

        return function stop() {
            clearInterval(intervalId);
        };
    }

    async function handleSubmit(event) {
        event.preventDefault();

        if (isSubmitting) {
            return;
        }

        const url = urlInput.value.trim();
        const format = form.querySelector('input[name="format"]:checked').value;
        const quality = format === "mp4" ? qualitySelect.value : "";

        if (!url) {
            setStatus("Please paste a YouTube URL first.", "error");
            urlInput.focus();
            return;
        }

        if (!looksLikeYouTubeUrl(url)) {
            setStatus("That doesn't look like a valid YouTube URL.", "error");
            urlInput.focus();
            return;
        }

        setLoading(true);
        const stopProgress = startProgressMessages();

        try {
            const response = await fetch("/download", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({ url: url, format: format, quality: quality }),
            });

            stopProgress();

            if (!response.ok) {
                const data = await response.json().catch(() => ({}));
                const message = data.error || "Something went wrong. Please try again.";
                setStatus(message, "error");
                return;
            }

            const blob = await response.blob();

            const disposition = response.headers.get("Content-Disposition") || "";
            const match = disposition.match(/filename="?([^"]+)"?/);
            const filename = match ? match[1] : `download.${format}`;

            const downloadUrl = window.URL.createObjectURL(blob);
            const link = document.createElement("a");
            link.href = downloadUrl;
            link.download = filename;
            document.body.appendChild(link);
            link.click();
            link.remove();
            window.URL.revokeObjectURL(downloadUrl);

            setStatus("Completed. Check your downloads.", "success");
            form.reset();
        } catch (err) {
            stopProgress();
            setStatus("Network error. Is the server still running?", "error");
        } finally {
            setLoading(false);
        }
    }

    form.addEventListener("submit", handleSubmit);

    formatRadios.forEach((radio) => {
        radio.addEventListener("change", () => {
            updateQualityVisibility();
            fetchQualities();
        });
    });

    urlInput.addEventListener("blur", fetchQualities);

    updateQualityVisibility();
})();