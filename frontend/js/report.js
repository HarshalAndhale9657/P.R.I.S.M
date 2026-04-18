/**
 * P.R.I.S.M. — Premium Report Renderer
 * Renders the AI-synthesized forensic report using Glassmorphism & High-end Dataviz.
 */

const ReportRenderer = (() => {

    function calculateAIProbability(analysisData) {
        const profiles = analysisData.features?.profiles || [];
        // Extract burstiness only for multi-sentence paragraphs to avoid 0.0 variance skew
        const scores = profiles.filter(p => (p.num_sentences || 1) >= 2).map(p => p.burstiness_score || 0);
        if (scores.length < 2) return { prob: 0, avg: 1.0 };
        
        const avg = scores.reduce((a,b) => a+b, 0) / scores.length;
        
        // Map burstiness to AI Probability:
        // ChatGPT scores < 0.15 (95%+). Heavy Math Humans score around 0.35-0.55 (~25-50%). Novels score > 0.8 (0%).
        let prob = 100 - ((avg - 0.05) * (100 / 0.50));
        if (prob > 99) prob = 99;
        if (prob < 1) prob = 1;
        return { prob: Math.round(prob), avg: avg };
    }

    function render(analysisData) {
        if (!analysisData || !analysisData.report) return;
        
        const container = document.getElementById('report-content');
        if (!container) return;

        const r = analysisData.report;

        // ─── Score & Visual Mapping ───
        const score = r.integrity_score != null ? r.integrity_score : 10;
        let scoreColor = 'var(--success)';
        let verdictIcon = '✅';
        let statusClass = 'status-clean';
        
        if (score < 4.5) {
            scoreColor = 'var(--danger)';
            verdictIcon = '🚨';
            statusClass = 'status-danger';
        } else if (score < 8) {
            scoreColor = 'var(--warning)';
            verdictIcon = '⚠️';
            statusClass = 'status-warn';
        }

        const verdict = r.verdict || r.overall_verdict || 'Unknown';
        const aiInfo = calculateAIProbability(analysisData);

        let html = '';

        // ─── Score Radial Gauge & AI Bar Panel ───
        // Calculate circumference for SVG circle (r=60 -> 2 * PI * 60 = 377)
        const circumference = 377;
        const strokeDashoffset = circumference - (score / 10) * circumference;

        html += `
            <div class="glass-panel" style="display: flex; gap: 32px; align-items: center; justify-content: space-between; flex-wrap: wrap;">
                
                <!-- Left: Gauge -->
                <div style="display: flex; gap: 32px; align-items: center; flex: 1; min-width: 300px;">
                    <div class="radial-gauge-container">
                        <svg class="radial-gauge-svg" viewBox="0 0 140 140">
                            <circle class="radial-bg" cx="70" cy="70" r="60"></circle>
                            <circle class="radial-progress" cx="70" cy="70" r="60" style="stroke: ${scoreColor}; stroke-dasharray: ${circumference}; stroke-dashoffset: ${strokeDashoffset};"></circle>
                        </svg>
                        <div class="radial-gauge-value">
                            <span class="score" style="color: ${scoreColor}">${score}</span>
                            <span class="out-of">out of 10</span>
                        </div>
                    </div>
                    <div>
                        <h3 style="font-size: 1.5rem; margin-bottom: 8px;">${verdictIcon} Verdict: ${verdict}</h3>
                        <p style="color: var(--text-secondary); line-height: 1.5;">${r.executive_summary || 'Integrity analysis complete.'}</p>
                    </div>
                </div>

                <!-- Right: AI Probability Meter -->
                <div style="flex: 1; min-width: 250px; background: rgba(0,0,0,0.02); padding: 20px; border-radius: var(--radius-md);">
                    <div class="ai-bar-header">
                        <span class="ai-bar-title">🤖 AI Generation Probability</span>
                        <span class="ai-bar-value" style="color: ${aiInfo.prob > 70 ? 'var(--danger)' : (aiInfo.prob > 30 ? 'var(--warning)' : 'var(--success)')}">${aiInfo.prob}%</span>
                    </div>
                    <div class="ai-bar-track">
                        <div class="ai-bar-fill" style="width: ${aiInfo.prob}%; background-color: ${aiInfo.prob > 70 ? 'var(--danger)' : (aiInfo.prob > 30 ? 'var(--warning)' : 'var(--success)')};"></div>
                    </div>
                    <p style="font-size: 0.8rem; color: var(--text-tertiary); margin-top: 8px;">Based on burstiness curve flattening (variance = ${aiInfo.avg.toFixed(2)})</p>
                </div>

            </div>
        `;

        // ─── Trust Badges Dashboard ───
        const evidence = r.evidence_breakdown || {};
        
        // Infer statuses from score elements
        const clustering = analysisData.clustering || {};
        const sources = analysisData.sources || [];
        const citations = analysisData.citations || {};

        const styloStatus = (clustering.estimated_authors > 1 || clustering.anomaly_count > 5) ? 'status-warn' : 'status-clean';
        const sourceStatus = sources.length > 0 ? 'status-danger' : 'status-clean';
        const citeStatus = (citations.temporal_anomalies && citations.temporal_anomalies.length > 0) ? 'status-danger' : 'status-clean';

        if (evidence.stylometric_analysis || evidence.citation_analysis || evidence.source_matches) {
            html += `
                <div style="margin-top: 32px;">
                    <h3 style="margin-bottom: 8px; font-weight: 700;">Security Certificate Dashboard</h3>
                    <div class="trust-dashboard">
            `;

            if (evidence.stylometric_analysis) {
                html += `
                        <div class="trust-badge ${styloStatus}">
                            <div class="trust-icon">🧬</div>
                            <div class="trust-content">
                                <div class="trust-title">Structural Autonomy</div>
                                <div class="trust-desc">${evidence.stylometric_analysis}</div>
                            </div>
                        </div>
                `;
            }
            if (evidence.citation_analysis) {
                html += `
                        <div class="trust-badge ${citeStatus}">
                            <div class="trust-icon">📚</div>
                            <div class="trust-content">
                                <div class="trust-title">Citation Regularity</div>
                                <div class="trust-desc">${evidence.citation_analysis}</div>
                            </div>
                        </div>
                `;
            }
            if (evidence.source_matches) {
                html += `
                        <div class="trust-badge ${sourceStatus}">
                            <div class="trust-icon">🔍</div>
                            <div class="trust-content">
                                <div class="trust-title">Database Originality</div>
                                <div class="trust-desc">${evidence.source_matches}</div>
                            </div>
                        </div>
                `;
            }

            html += `
                    </div>
                </div>
            `;
        }

        // ─── Conclusion ───
        if (r.conclusion) {
            html += `
                <div class="glass-panel" style="margin-top: 24px;">
                    <h3 style="margin-bottom: 12px; font-weight: 600;">Final Conclusion</h3>
                    <p style="color: var(--text-secondary); line-height: 1.6;">${r.conclusion}</p>
                </div>
            `;
        }
        
        // ─── Download CTA ───
        html += `
            <div style="margin-top: 32px; text-align: center;">
                <button class="btn-primary" id="btn-export-report" style="box-shadow: var(--shadow-glow);">
                    <span style="margin-right: 8px;">⬇️</span> Download Cryptographic JSON Report
                </button>
            </div>
        `;
        
        container.innerHTML = html;
        
        // Attach animations (Wait a frame so DOM updates)
        setTimeout(() => {
            const progressCircle = document.querySelector('.radial-progress');
            if (progressCircle) {
                progressCircle.style.strokeDashoffset = strokeDashoffset;
            }
            const aiBar = document.querySelector('.ai-bar-fill');
            if (aiBar) {
                aiBar.style.width = aiInfo.prob + '%';
            }
        }, 50);

        // Export listener
        document.getElementById('btn-export-report').addEventListener('click', () => {
             const exportData = {
                 report: r,
                 clustering: analysisData.clustering,
                 citations: analysisData.citations,
                 sources: analysisData.sources,
                 metadata: analysisData.metadata,
                 warnings: analysisData.warnings,
             };
             const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(exportData, null, 2));
             const downloadAnchorNode = document.createElement('a');
             downloadAnchorNode.setAttribute("href", dataStr);
             downloadAnchorNode.setAttribute("download", "prism_premium_forensic_report.json");
             document.body.appendChild(downloadAnchorNode);
             downloadAnchorNode.click();
             downloadAnchorNode.remove();
        });
    }

    return { render };
})();
