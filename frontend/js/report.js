/**
 * P.R.I.S.M. — Report Renderer
 * Renders the AI-synthesized forensic report.
 */

const ReportRenderer = (() => {
    function render(analysisData) {
        if (!analysisData || !analysisData.report) return;
        
        const container = document.getElementById('report-content');
        if (!container) return;

        const r = analysisData.report;

        // Map integrity score color
        let scoreColor = '#3fb950'; // Green
        if (r.integrity_score < 4) scoreColor = '#f85149'; // Red
        else if (r.integrity_score < 8) scoreColor = '#d29922'; // Yellow
        
        let html = `
            <div class="report-overview">
                <div class="score-gauge" style="border-color: ${scoreColor}">
                    <span class="score-value" style="color: ${scoreColor}">${r.integrity_score}/10</span>
                    <span class="score-label">Integrity Score</span>
                </div>
                <div class="verdict-summary">
                    <h3>Overall Verdict</h3>
                    <p>${r.overall_verdict}</p>
                </div>
            </div>
            
            <div class="evidence-section">
                <h3>Primary Evidence</h3>
                <ul>
                    ${r.evidence_summary && r.evidence_summary.length > 0 ? r.evidence_summary.map(item => `<li>${item}</li>`).join('') : '<li>No stylistic anomalies or external matches found.</li>'}
                </ul>
            </div>
            
            <div class="paragraph-verdicts">
                <h3>Section-by-Section Verdicts</h3>
                <div class="verdicts-list">
        `;
        
        if (r.paragraph_verdicts && r.paragraph_verdicts.length > 0) {
            r.paragraph_verdicts.forEach(pv => {
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
        }
        
        html += `
                </div>
            </div>
            
            <div class="report-actions" style="margin-top: 2rem;">
                <button class="btn-primary" id="btn-export-report">Download Full JSON Report</button>
            </div>
        `;
        
        container.innerHTML = html;
        
        // Export button listener
        document.getElementById('btn-export-report').addEventListener('click', () => {
             const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(r, null, 2));
             const downloadAnchorNode = document.createElement('a');
             downloadAnchorNode.setAttribute("href",     dataStr);
             downloadAnchorNode.setAttribute("download", "prism_forensic_report.json");
             document.body.appendChild(downloadAnchorNode);
             downloadAnchorNode.click();
             downloadAnchorNode.remove();
        });
    }

    return { render };
})();
