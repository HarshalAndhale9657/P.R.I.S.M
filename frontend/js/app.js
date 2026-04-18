/**
 * P.R.I.S.M. — App State Controller & Panel Navigation
 * ═══════════════════════════════════════════════════════════
 * Central orchestrator for the single-page application.
 * Manages global app state, panel switching, and cross-module communication.
 *
 * Modules (loaded separately, communicate via PRISM namespace):
 *   - upload.js    → File selection, validation, pipeline trigger
 *   - heatmap.js   → Color-coded authorship cluster visualization
 *   - charts.js    → Chart.js stylometric feature graphs
 *   - citations.js → Temporal citation anomaly timeline
 *   - sources.js   → arXiv/OpenAlex source match cards
 *   - report.js    → Forensic report with radial gauge + AI probability
 *
 * Design decisions:
 *   - IIFE module pattern (no build step, zero bundler required)
 *   - Lazy DOM caching on DOMContentLoaded (avoids null refs)
 *   - HSL color generation for unlimited cluster palette scaling
 *   - API_BASE auto-detects localhost vs production Render URL
 */

const PRISM = (() => {
    // ─── Configuration ───
    const API_BASE = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
        ? 'http://localhost:8000'
        : 'https://p-r-i-s-m.onrender.com';

    // ─── State ───
    const state = {
        currentPanel: 'upload',
        selectedFile: null,
        analysisData: null,
        isAnalyzing: false,
    };

    // ─── DOM Cache ───
    const dom = {};

    function cacheDom() {
        dom.navTabs = document.querySelectorAll('.nav-tab');
        dom.panels = document.querySelectorAll('.panel');
        dom.btnNewAnalysis = document.getElementById('btn-new-analysis');
    }

    // ─── Panel Navigation ───
    function switchPanel(panelId) {
        if (state.isAnalyzing && panelId !== 'upload') return;

        // Deactivate all
        dom.navTabs.forEach(tab => tab.classList.remove('active'));
        dom.panels.forEach(panel => panel.classList.remove('active'));

        // Activate target
        const targetTab = document.querySelector(`.nav-tab[data-panel="${panelId}"]`);
        const targetPanel = document.getElementById(`panel-${panelId}`);

        if (targetTab) targetTab.classList.add('active');
        if (targetPanel) {
            targetPanel.classList.add('active');
            // Re-trigger animation
            targetPanel.style.animation = 'none';
            targetPanel.offsetHeight; // force reflow
            targetPanel.style.animation = '';
        }

        state.currentPanel = panelId;
    }

    function enableTabs(tabIds) {
        tabIds.forEach(id => {
            const tab = document.querySelector(`.nav-tab[data-panel="${id}"]`);
            if (tab) tab.disabled = false;
        });
    }

    function disableAllResultTabs() {
        ['heatmap', 'charts', 'citations', 'sources', 'report'].forEach(id => {
            const tab = document.querySelector(`.nav-tab[data-panel="${id}"]`);
            if (tab) {
                tab.disabled = true;
                tab.classList.remove('active');
            }
        });
    }

    // ─── Analysis State ───
    function setAnalysisData(data) {
        state.analysisData = data;
    }

    function getAnalysisData() {
        return state.analysisData;
    }

    function setAnalyzing(val) {
        state.isAnalyzing = val;
    }

    // ─── File State ───
    function setSelectedFile(file) {
        state.selectedFile = file;
    }

    function getSelectedFile() {
        return state.selectedFile;
    }

    // ─── Reset ───
    function resetApp() {
        state.selectedFile = null;
        state.analysisData = null;
        state.isAnalyzing = false;

        disableAllResultTabs();
        switchPanel('upload');

        // Reset upload UI
        if (typeof UploadManager !== 'undefined') {
            UploadManager.reset();
        }

        dom.btnNewAnalysis.style.display = 'none';
    }

    function showNewAnalysisButton() {
        dom.btnNewAnalysis.style.display = 'flex';
    }

    // ─── Utility: Format File Size ───
    function formatFileSize(bytes) {
        if (bytes === 0) return '0 B';
        const units = ['B', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(1024));
        return (bytes / Math.pow(1024, i)).toFixed(i === 0 ? 0 : 1) + ' ' + units[i];
    }

    // ─── Utility: Dynamic HSL Colors for Clusters ───
    function getClusterColor(clusterIndex, totalClusters) {
        if (clusterIndex === -1) {
            return { bg: 'rgba(239,68,68,0.15)', border: '#ef4444', text: '#b91c1c' };
        }
        const hue = (clusterIndex * (360 / Math.max(totalClusters, 1))) % 360;
        const sat = 65;
        const light = 45; // Darker border for light theme
        return {
            bg: `hsla(${hue}, ${sat}%, ${light + 10}%, 0.12)`,
            border: `hsl(${hue}, ${sat}%, ${light}%)`,
            text: `hsl(${hue}, ${sat + 10}%, ${light - 20}%)`, // Darker text for readability
        };
    }

    // ─── Utility: YIQ Contrast ───
    function getContrastColor(hexOrHsl) {
        // Light theme design usually prefers dark text
        return '#111827';
    }

    // ─── Init ───
    function init() {
        cacheDom();

        // Tab click handlers
        dom.navTabs.forEach(tab => {
            tab.addEventListener('click', () => {
                if (!tab.disabled) {
                    switchPanel(tab.dataset.panel);
                }
            });
        });

        // New Analysis button
        dom.btnNewAnalysis.addEventListener('click', resetApp);

        console.log('%c🔬 P.R.I.S.M. v2 Hybrid', 'color: #7c3aed; font-size: 16px; font-weight: bold;');
        console.log('%cMathematical Proof + AI Reasoning', 'color: #06b6d4; font-size: 12px;');
    }

    // ─── Boot ───
    document.addEventListener('DOMContentLoaded', init);

    // ─── Public API ───
    return {
        API_BASE,
        switchPanel,
        enableTabs,
        disableAllResultTabs,
        setAnalysisData,
        getAnalysisData,
        setAnalyzing,
        setSelectedFile,
        getSelectedFile,
        resetApp,
        showNewAnalysisButton,
        formatFileSize,
        getClusterColor,
        getContrastColor,
    };
})();
