/**
 * P.R.I.S.M. — Citations Renderer
 * Visualizes citation temporal anomalies and baseline vs noise divergence.
 * Reads data from the /api/analyze response's `citations` object.
 *
 * Backend schema:
 *   citations.total_citations_found
 *   citations.temporal_anomaly_count
 *   citations.temporal_baseline.core_median_year
 *   citations.temporal_baseline.threshold
 *   citations.temporal_anomalies[] -> { paragraph_index, paragraph_median_year, core_baseline_year, year_difference, severity }
 *   citations.per_paragraph[] -> { paragraph_index, citations[], citation_count, years[], median_year }
 *   citations.density_analysis.avg_core_density / avg_noise_density
 */

const CitationsRenderer = (() => {
    /** Render the temporal citation anomaly timeline. */
    function render(analysisData) {
        if (!analysisData || !analysisData.citations) return;
        
        const container = document.getElementById('citations-content');
        if (!container) return;

        const data = analysisData.citations;

        // Handle error case from backend
        if (data.error) {
            container.innerHTML = `
                <div class="no-anomalies">
                    <span class="success-icon">⚠️</span>
                    <p>Citation analysis encountered an error: ${data.error}</p>
                </div>
            `;
            return;
        }
        
        let html = '';

        // ─── Overview Stats ───
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
        
        // ─── Temporal Baseline Info ───
        if (coreMedianYear) {
            html += `
                <div class="baseline-info">
                    <h3>Temporal Baseline Analysis</h3>
                    <p><strong>Core Author Median Year:</strong> ${coreMedianYear}</p>
                    ${noiseMedianYear ? `<p><strong>Noise Cluster Median Year:</strong> ${noiseMedianYear}</p>` : ''}
                    ${baseline.year_difference != null ? `<p><strong>Year Divergence:</strong> ${baseline.year_difference} years ${baseline.is_anomalous ? '<span style="color:#f85149;">⚠️ ANOMALOUS</span>' : '<span style="color:#3fb950;">✅ Normal</span>'}</p>` : ''}
                    <p style="color:#8b949e; font-size:0.9em; margin-top:8px;">Paragraphs citing sources more than ${threshold} years from the core baseline are flagged as temporal anomalies — a strong indicator of stitched content.</p>
                </div>
            `;
        }

        // ─── Density Analysis ───
        if (densityAnalysis.avg_core_density != null) {
            html += `
                <div class="baseline-info" style="margin-top:1rem;">
                    <h3>Citation Density</h3>
                    <p><strong>Core Cluster Density:</strong> ${densityAnalysis.avg_core_density.toFixed(4)} citations per 100 words</p>
                    <p><strong>Noise Cluster Density:</strong> ${densityAnalysis.avg_noise_density ? densityAnalysis.avg_noise_density.toFixed(4) : 'N/A'} citations per 100 words</p>
                    ${densityAnalysis.density_ratio != null ? `<p><strong>Density Ratio (Noise/Core):</strong> ${densityAnalysis.density_ratio}x</p>` : ''}
                </div>
            `;
        }

        // ─── Temporal Anomalies Timeline ───
        const anomalies = data.temporal_anomalies || [];
        if (anomalies.length > 0) {
            html += `<h3 class="timeline-title">Flagged Temporal Anomalies</h3><div class="timeline">`;
            anomalies.forEach((anomaly) => {
                const severityColor = anomaly.severity === 'high' ? '#f85149' : (anomaly.severity === 'medium' ? '#d29922' : '#3fb950');
                const severityIcon = anomaly.severity === 'high' ? '🚨' : (anomaly.severity === 'medium' ? '⚠️' : 'ℹ️');
                
                html += `
                    <div class="timeline-item anomaly-item">
                        <div class="timeline-badge">${severityIcon}</div>
                        <div class="timeline-content">
                            <h4>Paragraph ${anomaly.paragraph_index + 1} <span style="color:${severityColor}; font-size:0.85em; text-transform:uppercase;">[${anomaly.severity}]</span></h4>
                            <p><strong>Median Citation Year:</strong> ${anomaly.paragraph_median_year} (Core Baseline: ${anomaly.core_baseline_year})</p>
                            <p><strong>Year Difference:</strong> ${anomaly.year_difference} years</p>
                            <p style="font-size:0.85em; color:#8b949e;">Cluster: ${anomaly.is_noise_cluster ? 'Noise (anomalous)' : `Cluster ${anomaly.cluster_id}`}</p>
                        </div>
                    </div>
                `;
            });
            html += `</div>`;
        } else {
            html += `
                <div class="no-anomalies">
                    <span class="success-icon">✅</span>
                    <p>No significant temporal citation anomalies detected.</p>
                </div>
            `;
        }

        // ─── Per-Paragraph Citation Summary ───
        const perParagraph = data.per_paragraph || [];
        const paragraphsWithCitations = perParagraph.filter(p => p.citation_count > 0);
        if (paragraphsWithCitations.length > 0) {
            html += `<h3 class="timeline-title" style="margin-top:2rem;">Per-Paragraph Citations (${paragraphsWithCitations.length} paragraphs with citations)</h3>`;
            html += `<div style="max-height: 400px; overflow-y: auto; border: 1px solid #30363d; border-radius: 6px; padding: 12px;">`;
            paragraphsWithCitations.forEach(p => {
                html += `
                    <div style="margin-bottom: 12px; padding: 8px; background: rgba(22,27,34,0.5); border-radius: 4px; border-left: 3px solid ${p.cluster_id === -1 ? '#f85149' : '#3fb950'};">
                        <strong>¶ ${p.paragraph_index + 1}</strong> — ${p.citation_count} citation(s) | Median Year: ${p.median_year || 'N/A'} | Density: ${p.citation_density ? p.citation_density.toFixed(4) : 'N/A'}
                        <div style="color:#8b949e; font-size:0.85em; margin-top:4px;">${p.citations.join(', ')}</div>
                    </div>
                `;
            });
            html += `</div>`;
        }

        // ─── Bibliography Info ───
        const bib = data.bibliography || {};
        if (bib.total_references > 0) {
            html += `
                <div class="baseline-info" style="margin-top:1.5rem;">
                    <h3>Bibliography</h3>
                    <p><strong>Total References:</strong> ${bib.total_references}</p>
                    ${bib.bibliography_median_year ? `<p><strong>Bibliography Median Year:</strong> ${bib.bibliography_median_year}</p>` : ''}
                </div>
            `;
        }

        container.innerHTML = html;
    }

    return { render };
})();
