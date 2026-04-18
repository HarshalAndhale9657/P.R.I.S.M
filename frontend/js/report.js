/**
 * P.R.I.S.M. — Report Renderer
 * Renders the AI-synthesized forensic report.
 *
 * Backend report schema (from GPT-4o or fallback):
 *   {
 *     integrity_score: float (0-10),
 *     verdict: "Clean" | "Suspicious" | "Highly Plagiarized",
 *     executive_summary: string,
 *     evidence_breakdown: {
 *       stylometric_analysis: string,
 *       citation_analysis: string,
 *       source_matches: string
 *     },
 *     conclusion: string
 *   }
 */

const ReportRenderer = (() => {
    function render(analysisData) {
        if (!analysisData || !analysisData.report) return;
        
        const container = document.getElementById('report-content');
        if (!container) return;

        const r = analysisData.report;

        // Map integrity score color
        const score = r.integrity_score != null ? r.integrity_score : 10;
        let scoreColor = '#3fb950'; // Green
        if (score < 4) scoreColor = '#f85149'; // Red
        else if (score < 8) scoreColor = '#d29922'; // Yellow

        // Determine verdict — support both 'verdict' and 'overall_verdict' keys
        const verdict = r.verdict || r.overall_verdict || 'Unknown';
        
        // Determine verdict icon and background
        let verdictIcon = '✅';
        let verdictBg = 'rgba(63, 185, 80, 0.1)';
        if (verdict === 'Highly Plagiarized') {
            verdictIcon = '🚨';
            verdictBg = 'rgba(248, 81, 73, 0.1)';
        } else if (verdict === 'Suspicious') {
            verdictIcon = '⚠️';
            verdictBg = 'rgba(210, 153, 34, 0.1)';
        }
        
        let html = '';
        
        // Degraded mode warning
        if (analysisData.metadata && analysisData.metadata.degraded_mode) {
            html += `
                <div class="alert-banner warning" style="background: rgba(210, 153, 34, 0.15); border: 1px solid #d29922; color: #d29922; padding: 12px; border-radius: 6px; margin-bottom: 20px;">
                    <strong>⚠️ Degraded Mode Notice:</strong> The PDF was too complex or scanned, requiring fallback raw text extraction. Stylometric boundaries may be less precise.
                </div>
            `;
        }

        // Partial results warning
        if (analysisData.partial_results) {
            html += `
                <div class="alert-banner warning" style="background: rgba(210, 153, 34, 0.15); border: 1px solid #d29922; color: #d29922; padding: 12px; border-radius: 6px; margin-bottom: 20px;">
                    <strong>⚠️ Partial Results:</strong> Some pipeline stages encountered errors. Results may be incomplete.
                </div>
            `;
        }
        
        // ─── Score + Verdict Overview ───
        html += `
            <div class="report-overview">
                <div class="score-gauge" style="border-color: ${scoreColor}">
                    <span class="score-value" style="color: ${scoreColor}">${score}/10</span>
                    <span class="score-label">Integrity Score</span>
                </div>
                <div class="verdict-summary" style="background: ${verdictBg}; padding: 16px; border-radius: 8px;">
                    <h3>${verdictIcon} Verdict: ${verdict}</h3>
                    <p style="margin-top: 8px; color: #c9d1d9;">${r.executive_summary || ''}</p>
                </div>
            </div>
        `;

        // ─── Evidence Breakdown ───
        const evidence = r.evidence_breakdown || {};
        if (evidence.stylometric_analysis || evidence.citation_analysis || evidence.source_matches) {
            html += `
                <div class="evidence-section">
                    <h3>Evidence Breakdown</h3>
                    <div style="display: grid; gap: 12px; margin-top: 12px;">
            `;

            if (evidence.stylometric_analysis) {
                html += `
                    <div style="background: rgba(22,27,34,0.5); border: 1px solid #30363d; border-radius: 6px; padding: 14px;">
                        <h4 style="color: #7c3aed; margin: 0 0 8px 0;">🧬 Stylometric Analysis</h4>
                        <p style="color: #c9d1d9; margin: 0;">${evidence.stylometric_analysis}</p>
                    </div>
                `;
            }
            if (evidence.citation_analysis) {
                html += `
                    <div style="background: rgba(22,27,34,0.5); border: 1px solid #30363d; border-radius: 6px; padding: 14px;">
                        <h4 style="color: #06b6d4; margin: 0 0 8px 0;">📚 Citation Analysis</h4>
                        <p style="color: #c9d1d9; margin: 0;">${evidence.citation_analysis}</p>
                    </div>
                `;
            }
            if (evidence.source_matches) {
                html += `
                    <div style="background: rgba(22,27,34,0.5); border: 1px solid #30363d; border-radius: 6px; padding: 14px;">
                        <h4 style="color: #d29922; margin: 0 0 8px 0;">🔍 Source Matches</h4>
                        <p style="color: #c9d1d9; margin: 0;">${evidence.source_matches}</p>
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
                <div class="evidence-section" style="margin-top: 1.5rem;">
                    <h3>Conclusion</h3>
                    <p style="color: #c9d1d9; line-height: 1.6; background: rgba(22,27,34,0.5); border: 1px solid #30363d; border-radius: 6px; padding: 14px;">${r.conclusion}</p>
                </div>
            `;
        }

        // ─── Paragraph Verdicts (if present from GPT) ───
        const paraVerdicts = r.paragraph_verdicts || [];
        if (paraVerdicts.length > 0) {
            html += `
                <div class="paragraph-verdicts">
                    <h3>Section-by-Section Verdicts</h3>
                    <div class="verdicts-list">
            `;
            
            paraVerdicts.forEach(pv => {
                const isFlagged = pv.status === 'flagged';
                html += `
                    <div class="verdict-card ${isFlagged ? 'flagged' : 'clean'}">
                        <div class="verdict-header">
                            <span class="para-label">Section ${pv.paragraph_index + 1}</span>
                            <span class="para-status">${isFlagged ? '🚨 Flagged' : '✅ Clean'}</span>
                        </div>
                        <p class="para-reasoning">${pv.reasoning}</p>
                    </div>
                `;
            });
            
            html += `
                    </div>
                </div>
            `;
        }

        // ─── Quick Stats from analysis data ───
        const clustering = analysisData.clustering || {};
        const citations = analysisData.citations || {};
        const sources = analysisData.sources || [];
        
        html += `
            <div class="evidence-section" style="margin-top: 1.5rem;">
                <h3>Analysis Summary</h3>
                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; margin-top: 12px;">
                    <div style="background: rgba(22,27,34,0.5); border: 1px solid #30363d; border-radius: 6px; padding: 14px; text-align: center;">
                        <div style="font-size: 1.5em; font-weight: bold; color: #e6edf3;">${clustering.estimated_authors || 1}</div>
                        <div style="color: #8b949e; font-size: 0.85em;">Detected Authors</div>
                    </div>
                    <div style="background: rgba(22,27,34,0.5); border: 1px solid #30363d; border-radius: 6px; padding: 14px; text-align: center;">
                        <div style="font-size: 1.5em; font-weight: bold; color: ${(clustering.anomaly_count || 0) > 0 ? '#f85149' : '#3fb950'};">${clustering.anomaly_count || 0}</div>
                        <div style="color: #8b949e; font-size: 0.85em;">Anomalous Sections</div>
                    </div>
                    <div style="background: rgba(22,27,34,0.5); border: 1px solid #30363d; border-radius: 6px; padding: 14px; text-align: center;">
                        <div style="font-size: 1.5em; font-weight: bold; color: #e6edf3;">${citations.total_citations_found || 0}</div>
                        <div style="color: #8b949e; font-size: 0.85em;">Citations Found</div>
                    </div>
                    <div style="background: rgba(22,27,34,0.5); border: 1px solid #30363d; border-radius: 6px; padding: 14px; text-align: center;">
                        <div style="font-size: 1.5em; font-weight: bold; color: ${(Array.isArray(sources) ? sources.length : 0) > 0 ? '#f85149' : '#3fb950'};">${Array.isArray(sources) ? sources.length : 0}</div>
                        <div style="color: #8b949e; font-size: 0.85em;">Source Matches</div>
                    </div>
                </div>
            </div>
        `;
        
        html += `
            <div class="report-actions" style="margin-top: 2rem;">
                <button class="btn-primary" id="btn-export-report">Download Full JSON Report</button>
            </div>
        `;
        
        container.innerHTML = html;
        
        // Export button listener — export the full analysis data
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
             downloadAnchorNode.setAttribute("download", "prism_forensic_report.json");
             document.body.appendChild(downloadAnchorNode);
             downloadAnchorNode.click();
             downloadAnchorNode.remove();
        });
    }

    return { render };
})();
