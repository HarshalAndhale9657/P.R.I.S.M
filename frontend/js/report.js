/**
 * P.R.I.S.M. — Premium Report Renderer v3
 * ═══════════════════════════════════════════════════════════
 * Renders the forensic report with dual-engine boundary evidence,
 * 4-tier verdicts, and sub-score breakdown.
 *
 * Components:
 *   1. Radial SVG Gauge — integrity score 0.0–10.0 with animated arc
 *   2. Sub-Score Breakdown — boundary, coherence, citation, burstiness bars
 *   3. Trust Badge Dashboard — per-engine evidence cards
 *   4. Conclusion Panel — GPT-4o final forensic statement
 *   5. Export Button — downloads full JSON forensic report
 *
 * v3 Changes:
 *   - 4-tier verdict (Clean/Suspicious/Flagged/Critical)
 *   - Sub-scores from deterministic scoring engine
 *   - Removed AI probability meter (burstiness is now a soft signal only)
 *   - Added topic coherence + boundary fusion trust badges
 */

const ReportRenderer = (() => {

    /** Map verdict to visual properties. */
    function getVerdictVisuals(verdict, score) {
        const map = {
            'Clean':      { color: 'var(--success)', icon: '✅', class: 'status-clean' },
            'Suspicious': { color: 'var(--warning)', icon: '⚠️', class: 'status-warn' },
            'Flagged':    { color: 'var(--danger)',  icon: '🚩', class: 'status-flagged' },
            'Critical':   { color: '#ff1744',        icon: '🚨', class: 'status-danger' },
        };
        // Fallback by score if verdict string doesn't match
        if (map[verdict]) return map[verdict];
        if (score >= 8) return map['Clean'];
        if (score >= 5) return map['Suspicious'];
        if (score >= 2) return map['Flagged'];
        return map['Critical'];
    }

    /** Render a small horizontal bar for a sub-score. */
    function renderSubScoreBar(label, value, maxVal) {
        const pct = Math.min((value / maxVal) * 100, 100);
        let barColor = 'var(--success)';
        if (value < 4) barColor = 'var(--danger)';
        else if (value < 7) barColor = 'var(--warning)';

        return `
            <div style="margin-bottom: 10px;">
                <div style="display: flex; justify-content: space-between; font-size: 0.85rem; margin-bottom: 3px;">
                    <span style="color: var(--text-secondary);">${label}</span>
                    <span style="font-weight: 600; color: ${barColor};">${value.toFixed(1)}/10</span>
                </div>
                <div style="height: 6px; background: rgba(255,255,255,0.08); border-radius: 3px; overflow: hidden;">
                    <div style="width: ${pct}%; height: 100%; background: ${barColor}; border-radius: 3px; transition: width 0.8s ease;"></div>
                </div>
            </div>
        `;
    }

    /** Render the forensic integrity report dashboard. */
    function render(analysisData) {
        if (!analysisData || !analysisData.report) return;
        
        const container = document.getElementById('report-content');
        if (!container) return;

        const r = analysisData.report;
        const scoring = analysisData.scoring || {};
        const subScores = scoring.sub_scores || {};

        // ─── Score & Visual Mapping ───
        const score = scoring.integrity_score != null ? scoring.integrity_score : (r.integrity_score != null ? r.integrity_score : 10);
        const verdict = scoring.verdict || r.verdict || r.overall_verdict || 'Unknown';
        const visuals = getVerdictVisuals(verdict, score);

        let html = '';

        // ─── Score Radial Gauge + Sub-scores Panel ───
        const circumference = 377;
        const strokeDashoffset = circumference - (score / 10) * circumference;

        html += `
            <div class="glass-panel" style="display: flex; gap: 32px; align-items: center; justify-content: space-between; flex-wrap: wrap;">
                
                <!-- Left: Gauge + Verdict -->
                <div style="display: flex; gap: 32px; align-items: center; flex: 1; min-width: 300px;">
                    <div class="radial-gauge-container">
                        <svg class="radial-gauge-svg" viewBox="0 0 140 140">
                            <circle class="radial-bg" cx="70" cy="70" r="60"></circle>
                            <circle class="radial-progress" cx="70" cy="70" r="60" style="stroke: ${visuals.color}; stroke-dasharray: ${circumference}; stroke-dashoffset: ${strokeDashoffset};"></circle>
                        </svg>
                        <div class="radial-gauge-value">
                            <span class="score" style="color: ${visuals.color}">${score}</span>
                            <span class="out-of">out of 10</span>
                        </div>
                    </div>
                    <div>
                        <h3 style="font-size: 1.5rem; margin-bottom: 8px;">${visuals.icon} Verdict: ${verdict}</h3>
                        <p style="color: var(--text-secondary); line-height: 1.5;">${r.executive_summary || 'Integrity analysis complete.'}</p>
                    </div>
                </div>

                <!-- Right: Sub-Score Breakdown -->
                <div style="flex: 1; min-width: 250px; background: rgba(0,0,0,0.02); padding: 20px; border-radius: var(--radius-md);">
                    <div style="font-weight: 600; margin-bottom: 12px; font-size: 0.95rem;">Evidence Sub-Scores</div>
                    ${renderSubScoreBar('Boundary Detection', subScores.boundary != null ? subScores.boundary : 10, 10)}
                    ${renderSubScoreBar('Topic Coherence', subScores.coherence != null ? subScores.coherence : 10, 10)}
                    ${renderSubScoreBar('Citation Forensics', subScores.citation != null ? subScores.citation : 10, 10)}
                    ${renderSubScoreBar('Burstiness Signal', subScores.burstiness != null ? subScores.burstiness : 10, 10)}
                </div>

            </div>
        `;

        // ─── Boundary Fusion Info ───
        const fusion = analysisData.fusion || {};
        const highBoundaries = fusion.high_confidence_count || 0;
        const medBoundaries = fusion.medium_confidence_count || 0;
        const totalBoundaries = fusion.total_boundaries || 0;
        const agreementRate = fusion.agreement_rate != null ? (fusion.agreement_rate * 100).toFixed(0) : 'N/A';

        if (totalBoundaries > 0) {
            html += `
                <div class="glass-panel" style="margin-top: 24px;">
                    <h3 style="margin-bottom: 12px; font-weight: 600;">Dual-Engine Boundary Fusion</h3>
                    <div style="display: flex; gap: 24px; flex-wrap: wrap;">
                        <div style="text-align: center; flex: 1; min-width: 100px;">
                            <div style="font-size: 2rem; font-weight: 700; color: var(--danger);">${highBoundaries}</div>
                            <div style="font-size: 0.85rem; color: var(--text-secondary);">HIGH Confidence</div>
                            <div style="font-size: 0.75rem; color: var(--text-tertiary);">Both engines agree</div>
                        </div>
                        <div style="text-align: center; flex: 1; min-width: 100px;">
                            <div style="font-size: 2rem; font-weight: 700; color: var(--warning);">${medBoundaries}</div>
                            <div style="font-size: 0.85rem; color: var(--text-secondary);">MEDIUM Confidence</div>
                            <div style="font-size: 0.75rem; color: var(--text-tertiary);">One engine only</div>
                        </div>
                        <div style="text-align: center; flex: 1; min-width: 100px;">
                            <div style="font-size: 2rem; font-weight: 700; color: var(--text-primary);">${agreementRate}%</div>
                            <div style="font-size: 0.85rem; color: var(--text-secondary);">Agreement Rate</div>
                            <div style="font-size: 0.75rem; color: var(--text-tertiary);">HDBSCAN vs PELT</div>
                        </div>
                    </div>
                </div>
            `;
        }

        // ─── Trust Badges Dashboard ───
        const evidence = r.evidence_breakdown || {};
        const clustering = analysisData.clustering || {};
        const sources = analysisData.sources || [];
        const citations = analysisData.citations || {};

        const styloStatus = (clustering.estimated_authors > 1 || clustering.anomaly_count > 5) ? 'status-warn' : 'status-clean';
        const sourceStatus = sources.length > 0 ? 'status-danger' : 'status-clean';
        const citeStatus = (citations.temporal_anomalies && citations.temporal_anomalies.length > 0) ? 'status-danger' : 'status-clean';
        const coherenceStatus = subScores.coherence != null && subScores.coherence < 7 ? 'status-warn' : 'status-clean';

        const hasBadges = evidence.stylometric_analysis || evidence.topic_coherence || evidence.citation_analysis || evidence.source_matches;

        if (hasBadges) {
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
            if (evidence.topic_coherence) {
                html += `
                        <div class="trust-badge ${coherenceStatus}">
                            <div class="trust-icon">🔗</div>
                            <div class="trust-content">
                                <div class="trust-title">Topic Coherence</div>
                                <div class="trust-desc">${evidence.topic_coherence}</div>
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
        }, 50);

        // Export listener
        document.getElementById('btn-export-report').addEventListener('click', () => {
             const exportData = {
                 report: r,
                 scoring: scoring,
                 fusion: fusion,
                 clustering: analysisData.clustering,
                 citations: analysisData.citations,
                 sources: analysisData.sources,
                 metadata: analysisData.metadata,
                 warnings: analysisData.warnings,
             };
             const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(exportData, null, 2));
             const downloadAnchorNode = document.createElement('a');
             downloadAnchorNode.setAttribute("href", dataStr);
             downloadAnchorNode.setAttribute("download", "prism_forensic_report_v3.json");
             document.body.appendChild(downloadAnchorNode);
             downloadAnchorNode.click();
             downloadAnchorNode.remove();
        });
    }

    return { render };
})();
