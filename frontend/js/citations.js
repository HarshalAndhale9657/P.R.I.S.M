/**
 * P.R.I.S.M. — Citations Renderer
 * Visualizes citation temporal anomalies and baseline vs noise divergence.
 */

const CitationsRenderer = (() => {
    function render(analysisData) {
        if (!analysisData || !analysisData.citations) return;
        
        const container = document.getElementById('citations-content');
        if (!container) return;

        const data = analysisData.citations;
        
        let html = '';
        
        // Overview Card
        html += `
            <div class="citation-overview">
                <div class="overview-stat">
                    <span class="stat-value">${data.total_citations || 0}</span>
                    <span class="stat-label">Total Citations</span>
                </div>
                <div class="overview-stat">
                    <span class="stat-value">${data.temporal_anomalies_count || 0}</span>
                    <span class="stat-label">Temporal Anomalies</span>
                </div>
            </div>
        `;
        
        // Temporal Baseline Info
        if (data.core_cluster_median_year) {
            html += `
                <div class="baseline-info">
                    <h3>Core Author Baseline: ${data.core_cluster_median_year}</h3>
                    <p>The median citation year for the core author's cluster is ${data.core_cluster_median_year}. Divergence of more than ${data.temporal_threshold || 10} years in isolated clusters implies potential stitched content.</p>
                </div>
            `;
        }

        // Anomalies Timeline
        if (data.anomalies && data.anomalies.length > 0) {
            html += `<h3 class="timeline-title">Flagged Anomalies</h3><div class="timeline">`;
            data.anomalies.forEach((anomaly) => {
                html += `
                    <div class="timeline-item anomaly-item">
                        <div class="timeline-badge">🚨</div>
                        <div class="timeline-content">
                            <h4>Paragraph ${anomaly.paragraph_index + 1}</h4>
                            <p><strong>Median Year:</strong> ${anomaly.median_year} (Diff: ${Math.abs(anomaly.median_year - data.core_cluster_median_year)} years)</p>
                            <p class="citation-extracts">${(anomaly.citations || []).join(', ')}</p>
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

        container.innerHTML = html;
    }

    return { render };
})();
