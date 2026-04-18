/**
 * P.R.I.S.M. — Upload Manager
 * Handles drag-and-drop file upload, validation, progress tracking,
 * and triggers the full analysis pipeline.
 */

const UploadManager = (() => {
    // ─── DOM Cache ───
    const dom = {};

    function cacheDom() {
        dom.dropZone = document.getElementById('drop-zone');
        dom.fileInput = document.getElementById('file-input');
        dom.btnBrowse = document.getElementById('btn-browse');
        dom.fileInfo = document.getElementById('file-info');
        dom.fileName = document.getElementById('file-name');
        dom.fileMeta = document.getElementById('file-meta');
        dom.btnRemove = document.getElementById('btn-remove');
        dom.btnAnalyze = document.getElementById('btn-analyze');
        dom.progressContainer = document.getElementById('progress-container');
        dom.progressLabel = document.getElementById('progress-label');
        dom.progressPercent = document.getElementById('progress-percent');
        dom.progressFill = document.getElementById('progress-fill');
        dom.progressSteps = document.getElementById('progress-steps');
        dom.errorCard = document.getElementById('error-card');
        dom.errorMessage = document.getElementById('error-message');
        dom.btnRetry = document.getElementById('btn-retry');
    }

    // ─── Drag & Drop ───
    function setupDragDrop() {
        const zone = dom.dropZone;

        ['dragenter', 'dragover'].forEach(evt => {
            zone.addEventListener(evt, (e) => {
                e.preventDefault();
                e.stopPropagation();
                zone.classList.add('drag-over');
            });
        });

        ['dragleave', 'drop'].forEach(evt => {
            zone.addEventListener(evt, (e) => {
                e.preventDefault();
                e.stopPropagation();
                zone.classList.remove('drag-over');
            });
        });

        zone.addEventListener('drop', (e) => {
            const files = e.dataTransfer.files;
            if (files.length > 0) {
                handleFile(files[0]);
            }
        });

        // Click to browse
        zone.addEventListener('click', (e) => {
            if (e.target.closest('#btn-browse') || e.target === zone || e.target.closest('.drop-zone-inner')) {
                dom.fileInput.click();
            }
        });

        dom.btnBrowse.addEventListener('click', (e) => {
            e.stopPropagation();
            dom.fileInput.click();
        });

        dom.fileInput.addEventListener('change', (e) => {
            if (e.target.files.length > 0) {
                handleFile(e.target.files[0]);
            }
        });
    }

    // ─── File Handling ───
    function handleFile(file) {
        // Validate
        if (!file.name.toLowerCase().endsWith('.pdf')) {
            showError('Please upload a PDF file. Other formats are not supported.');
            return;
        }

        if (file.size > 50 * 1024 * 1024) { // 50MB limit
            showError('File is too large. Please upload a PDF under 50MB.');
            return;
        }

        if (file.size === 0) {
            showError('The uploaded file is empty.');
            return;
        }

        // Store file
        PRISM.setSelectedFile(file);

        // Update UI
        dom.fileName.textContent = file.name;
        dom.fileMeta.textContent = `${PRISM.formatFileSize(file.size)} • PDF`;

        dom.dropZone.style.display = 'none';
        dom.fileInfo.style.display = 'block';
        dom.btnAnalyze.style.display = 'inline-flex';
        dom.errorCard.style.display = 'none';

        // Focus analyze button
        dom.btnAnalyze.focus();
    }

    // ─── Remove File ───
    function removeFile() {
        PRISM.setSelectedFile(null);
        dom.fileInput.value = '';
        dom.dropZone.style.display = 'block';
        dom.fileInfo.style.display = 'none';
        dom.btnAnalyze.style.display = 'none';
        dom.errorCard.style.display = 'none';
    }

    // ─── Progress Tracking ───
    const STEPS = ['parse', 'features', 'cluster', 'reasoning', 'citations', 'sources'];
    const STEP_LABELS = {
        parse: 'Parsing PDF...',
        features: 'Extracting stylometric features...',
        cluster: 'Running HDBSCAN clustering...',
        reasoning: 'AI reasoning on flagged boundaries...',
        citations: 'Analyzing citation patterns...',
        sources: 'Tracing potential sources...',
    };

    function showProgress() {
        dom.progressContainer.style.display = 'block';
        dom.btnAnalyze.style.display = 'none';
        dom.fileInfo.style.display = 'none';
        dom.errorCard.style.display = 'none';
        resetProgressSteps();
    }

    function resetProgressSteps() {
        STEPS.forEach(step => {
            const el = dom.progressSteps.querySelector(`[data-step="${step}"]`);
            if (el) {
                el.classList.remove('active', 'done');
            }
        });
        dom.progressFill.style.width = '0%';
        dom.progressPercent.textContent = '0%';
        dom.progressLabel.textContent = 'Initializing...';
    }

    function updateProgress(stepName, percent) {
        const stepEl = dom.progressSteps.querySelector(`[data-step="${stepName}"]`);

        // Mark previous steps as done
        const stepIndex = STEPS.indexOf(stepName);
        STEPS.forEach((s, i) => {
            const el = dom.progressSteps.querySelector(`[data-step="${s}"]`);
            if (!el) return;
            if (i < stepIndex) {
                el.classList.remove('active');
                el.classList.add('done');
            } else if (i === stepIndex) {
                el.classList.add('active');
                el.classList.remove('done');
            }
        });

        dom.progressFill.style.width = `${percent}%`;
        dom.progressPercent.textContent = `${Math.round(percent)}%`;
        dom.progressLabel.textContent = STEP_LABELS[stepName] || 'Processing...';
    }

    function completeProgress() {
        STEPS.forEach(step => {
            const el = dom.progressSteps.querySelector(`[data-step="${step}"]`);
            if (el) {
                el.classList.remove('active');
                el.classList.add('done');
            }
        });
        dom.progressFill.style.width = '100%';
        dom.progressPercent.textContent = '100%';
        dom.progressLabel.textContent = 'Analysis complete!';
    }

    // ─── Error Handling ───
    function showError(message) {
        dom.errorCard.style.display = 'flex';
        dom.errorMessage.textContent = message;
        dom.progressContainer.style.display = 'none';
    }

    // ─── Analysis Pipeline ───
    async function runAnalysis() {
        const file = PRISM.getSelectedFile();
        if (!file) return;

        PRISM.setAnalyzing(true);
        showProgress();

        try {
            // Stage 1: Upload & Parse
            updateProgress('parse', 5);
            const formData = new FormData();
            formData.append('file', file);

            const parseResp = await fetch(`${PRISM.API_BASE}/api/parse`, {
                method: 'POST',
                body: formData,
            });

            if (!parseResp.ok) {
                const err = await parseResp.json().catch(() => ({}));
                throw new Error(err.detail || `Upload failed (${parseResp.status})`);
            }

            const parseData = await parseResp.json();
            updateProgress('features', 20);

            // Stage 2: Full analysis (cluster endpoint includes features + HDBSCAN)
            const formData2 = new FormData();
            formData2.append('file', file);

            updateProgress('cluster', 35);
            const clusterResp = await fetch(`${PRISM.API_BASE}/api/cluster`, {
                method: 'POST',
                body: formData2,
            });

            if (!clusterResp.ok) {
                const err = await clusterResp.json().catch(() => ({}));
                throw new Error(err.detail || `Clustering failed (${clusterResp.status})`);
            }

            const clusterData = await clusterResp.json();
            updateProgress('reasoning', 50);

            // Stage 3: GPT Reasoning
            const formData3 = new FormData();
            formData3.append('file', file);

            const reasonResp = await fetch(`${PRISM.API_BASE}/api/reasoning`, {
                method: 'POST',
                body: formData3,
            });

            let reasoningData = null;
            if (reasonResp.ok) {
                reasoningData = await reasonResp.json();
            }
            updateProgress('citations', 70);

            // Stage 4: Citation Forensics
            const formData4 = new FormData();
            formData4.append('file', file);

            const citResp = await fetch(`${PRISM.API_BASE}/api/citations`, {
                method: 'POST',
                body: formData4,
            });

            let citationsData = null;
            if (citResp.ok) {
                citationsData = await citResp.json();
            }
            updateProgress('sources', 90);

            // Compose final data object
            const analysisResult = {
                filename: parseData.filename,
                page_count: parseData.page_count,
                extraction_method: parseData.extraction_method,
                degraded_mode: parseData.degraded_mode,
                total_paragraphs: clusterData.total_paragraphs,
                paragraphs: clusterData.paragraphs,
                references: clusterData.references || parseData.references,
                estimated_authors: clusterData.estimated_authors,
                anomaly_count: clusterData.anomaly_count,
                noise_percentage: clusterData.noise_percentage,
                boundaries: clusterData.boundaries,
                cluster_sizes: clusterData.cluster_sizes,
                confidence: clusterData.confidence,
                feature_names: clusterData.feature_names,
                profiles: clusterData.profiles,
                reasoning: reasoningData ? reasoningData.reasoning : null,
                citations: citationsData ? citationsData.citations : null,
            };

            // Store results
            PRISM.setAnalysisData(analysisResult);

            completeProgress();

            // Enable result tabs
            PRISM.enableTabs(['heatmap', 'charts']);
            if (citationsData) PRISM.enableTabs(['citations']);
            // 'sources' and 'report' will be enabled when those modules are built

            // Show new analysis button
            PRISM.showNewAnalysisButton();

            // Render results (heatmap, charts will self-render if available)
            if (typeof HeatmapRenderer !== 'undefined') {
                HeatmapRenderer.render(analysisResult);
            }
            if (typeof ChartsRenderer !== 'undefined') {
                ChartsRenderer.render(analysisResult);
            }
            if (typeof CitationsRenderer !== 'undefined') {
                CitationsRenderer.render(analysisResult);
            }

            // Auto-switch to heatmap after short delay
            setTimeout(() => {
                PRISM.switchPanel('heatmap');
            }, 1200);

        } catch (err) {
            console.error('Analysis failed:', err);
            showError(err.message || 'Analysis failed. Please try again.');
        } finally {
            PRISM.setAnalyzing(false);
        }
    }

    // ─── Reset ───
    function reset() {
        removeFile();
        dom.progressContainer.style.display = 'none';
        dom.errorCard.style.display = 'none';
        resetProgressSteps();
    }

    // ─── Init ───
    function init() {
        cacheDom();
        setupDragDrop();

        // Analyze button
        dom.btnAnalyze.addEventListener('click', runAnalysis);

        // Remove file button
        dom.btnRemove.addEventListener('click', (e) => {
            e.stopPropagation();
            removeFile();
        });

        // Retry button
        dom.btnRetry.addEventListener('click', () => {
            dom.errorCard.style.display = 'none';
            if (PRISM.getSelectedFile()) {
                dom.fileInfo.style.display = 'block';
                dom.btnAnalyze.style.display = 'inline-flex';
            } else {
                dom.dropZone.style.display = 'block';
            }
        });
    }

    document.addEventListener('DOMContentLoaded', init);

    return { reset };
})();
