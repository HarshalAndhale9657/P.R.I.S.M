/**
 * P.R.I.S.M. — Citations Renderer
 * Visualizes citation temporal anomalies and baseline vs noise divergence.
 * Reads from the /api/analyze response `citations` object.
 */

const CitationsRenderer = (() => {
    function sevClass(sev) {
        if (sev === 'high') return 'sev-high';
        if (sev === 'medium') return 'sev-med';
        return 'sev-low';
    }
    function sevIcon(sev) {
        if (sev === 'high') return '🚨';
        if (sev === 'medium') return '⚠️';
        return 'ℹ️';
    }
    function escapeHtml(str) {
        const div = document.createElement('div');
        div.textContent = str == null ? '' : String(str);
        return div.innerHTML;
    }

    function render(analysisData) {
        if (!analysisData || !analysisData.citations) return;
        const container = document.getElementById('citations-content');
        if (!container) return;

        const data = analysisData.citations;

        if (data.error) {
            container.innerHTML = `
                <div class="no-anomalies">
                    <span class="success-icon">⚠️</span>
                    <p class="empty-title">Citation analysis error</p>
                    <p>${escapeHtml(data.error)}</p>
                </div>
            `;
            return;
        }

        let html = '';

        const totalCitations = data.total_citations_found || 0;
        const anomalyCount = data.temporal_anomaly_count || 0;
        const baseline = data.temporal_baseline || {};
        const coreMedianYear = baseline.core_median_year || null;
        const noiseMedianYear = baseline.noise_median_year || null;
        const threshold = baseline.threshold || 10;
        const densityAnalysis = data.density_analysis || {};

        html += `
            <div class="citation-overview">
                <div class="overview-stat">
                    <span class="stat-value">${totalCitations}</span>
                    <span class="stat-label">Total Citations</span>
                </div>
                <div class="overview-stat">
                    <span class="stat-value">${anomalyCount}</span>
                    <span class="stat-label">Temporal Anomalies</span>
                </div>
                <div class="overview-stat">
                    <span class="stat-value">${data.unique_years ? data.unique_years.length : 0}</span>
                    <span class="stat-label">Unique Years</span>
                </div>
            </div>
        `;

        if (coreMedianYear) {
            const div = baseline.year_difference;
            const flag = baseline.is_anomalous
                ? '<span class="pill pill-danger">⚠️ Anomalous</span>'
                : '<span class="pill pill-ok">✅ Normal</span>';
            html += `
                <div class="baseline-info">
                    <h3>Temporal Baseline Analysis</h3>
                    <p><strong>Core Author Median Year:</strong> ${coreMedianYear}</p>
                    ${noiseMedianYear ? `<p><strong>Noise Cluster Median Year:</strong> ${noiseMedianYear}</p>` : ''}
                    ${div != null ? `<p><strong>Year Divergence:</strong> ${div} years ${flag}</p>` : ''}
                    <p class="muted">Paragraphs citing sources more than ${threshold} years from the core baseline
                    are flagged as temporal anomalies — a strong indicator of stitched content.</p>
                </div>
            `;
        }

        if (densityAnalysis.avg_core_density != null) {
            html += `
                <div class="baseline-info" style="margin-top:1rem;">
                    <h3>Citation Density</h3>
                    <p><strong>Core Cluster Density:</strong> ${densityAnalysis.avg_core_density.toFixed(4)} citations / 100 words</p>
                    <p><strong>Noise Cluster Density:</strong> ${densityAnalysis.avg_noise_density != null ? densityAnalysis.avg_noise_density.toFixed(4) : 'N/A'} citations / 100 words</p>
                    ${densityAnalysis.density_ratio != null ? `<p><strong>Density Ratio (Noise/Core):</strong> ${densityAnalysis.density_ratio}×</p>` : ''}
                </div>
            `;
        }

        const anomalies = data.temporal_anomalies || [];
        if (anomalies.length > 0) {
            html += `<h3 class="timeline-title">Flagged Temporal Anomalies</h3><div class="timeline">`;
            anomalies.forEach(a => {
                html += `
                    <div class="timeline-item anomaly-item">
                        <div class="timeline-badge">${sevIcon(a.severity)}</div>
                        <div class="timeline-content">
                            <h4>Paragraph ${a.paragraph_index + 1}
                                <span class="sev-tag ${sevClass(a.severity)}">[${escapeHtml(a.severity || '')}]</span></h4>
                            <p><strong>Median Citation Year:</strong> ${a.paragraph_median_year} (Core Baseline: ${a.core_baseline_year})</p>
                            <p><strong>Year Difference:</strong> ${a.year_difference} years</p>
                            <p class="muted">Cluster: ${a.is_noise_cluster ? 'Noise (anomalous)' : `Cluster ${a.cluster_id}`}</p>
                        </div>
                    </div>
                `;
            });
            html += `</div>`;
        } else {
            html += `
                <div class="no-anomalies">
                    <span class="success-icon">✅</span>
                    <p class="empty-title">No temporal citation anomalies</p>
                    <p>Citation years are temporally consistent across the document.</p>
                </div>
            `;
        }

        const perParagraph = data.per_paragraph || [];
        const withCitations = perParagraph.filter(p => p.citation_count > 0);
        if (withCitations.length > 0) {
            html += `<h3 class="timeline-title" style="margin-top:2rem;">Per-Paragraph Citations
                        <span class="muted">(${withCitations.length} with citations)</span></h3>`;
            html += `<div class="citation-scroll">`;
            withCitations.forEach(p => {
                const anomalous = p.cluster_id === -1;
                html += `
                    <div class="citation-row ${anomalous ? 'anomalous' : ''}">
                        <div class="citation-row-head">
                            <strong>¶ ${p.paragraph_index + 1}</strong>
                            <span>${p.citation_count} citation(s)</span>
                            <span>Median Year: ${p.median_year || 'N/A'}</span>
                            <span>Density: ${p.citation_density != null ? p.citation_density.toFixed(4) : 'N/A'}</span>
                        </div>
                        <div class="citation-list">${escapeHtml((p.citations || []).join(', '))}</div>
                    </div>
                `;
            });
            html += `</div>`;
        }

        const bib = data.bibliography || {};
        if (bib.total_references > 0) {
            html += `
                <div class="baseline-info" style="margin-top:1.5rem;">
                    <h3>Bibliography</h3>
                    <p><strong>Total References:</strong> ${bib.total_references}</p>
                    ${bib.bibliography_median_year ? `<p><strong>Bibliography Median Year:</strong> ${bib.bibliography_median_year}</p>` : ''}
                    ${bib.hallucination_count != null ? `<p><strong>Potentially Hallucinated:</strong> ${bib.hallucination_count}</p>` : ''}
                </div>
            `;
        }

        container.innerHTML = html;
    }

    return { render };
})();
