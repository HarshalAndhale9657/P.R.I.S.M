/**
 * P.R.I.S.M. — Originality Checker (Phase 1)
 * ═══════════════════════════════════════════════════════════
 * Upload a paper + reference sources → POST /api/check → render an originality
 * report: overall %, in-context highlighting, and side-by-side source comparison.
 * Self-contained (no dependency on the legacy authorship modules).
 */

(() => {
    'use strict';

    const API_BASE =
        window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
            ? 'http://localhost:8000'
            : 'https://p-r-i-s-m.onrender.com';

    const MAX_FILE_MB = 20;

    const state = {
        paper: null,        // File | null
        refs: [],           // File[]
        useAcademic: false, // also search OpenAlex
        result: null,       // last API result
        analyzing: false,
    };

    const dom = {};

    // ─── Utilities ───
    function esc(s) {
        const d = document.createElement('div');
        d.textContent = s == null ? '' : String(s);
        return d.innerHTML;
    }
    function fmtBytes(bytes) {
        if (!bytes) return '0 B';
        const u = ['B', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(1024));
        return (bytes / Math.pow(1024, i)).toFixed(i === 0 ? 0 : 1) + ' ' + u[i];
    }
    function isSupported(file) {
        const n = (file.name || '').toLowerCase();
        return n.endsWith('.pdf') || n.endsWith('.txt');
    }
    function trim(s, n) {
        s = s || '';
        return s.length > n ? s.slice(0, n).trimEnd() + '…' : s;
    }
    function pctInt(x) { return Math.round((x || 0) * 100); }
    function band(pct) { return pct >= 20 ? 'band-danger' : (pct >= 8 ? 'band-warn' : 'band-ok'); }

    // ─── File handling ───
    function setPaper(file) {
        if (!file) return;
        if (!isSupported(file)) return showError('Your paper must be a PDF or TXT file.');
        if (file.size > MAX_FILE_MB * 1024 * 1024) return showError(`Your paper exceeds the ${MAX_FILE_MB} MB limit.`);
        if (file.size === 0) return showError('That file is empty.');
        state.paper = file;
        hideError();
        renderPaperChip();
        updateButton();
    }

    function addRefs(files) {
        let added = 0;
        for (const f of files) {
            if (!isSupported(f) || f.size === 0 || f.size > MAX_FILE_MB * 1024 * 1024) continue;
            if (state.refs.some(r => r.name === f.name && r.size === f.size)) continue; // dedup
            state.refs.push(f);
            added++;
        }
        if (added) hideError();
        renderRefChips();
        updateButton();
    }

    function renderPaperChip() {
        if (!state.paper) { dom.paperChip.innerHTML = ''; return; }
        dom.paperChip.innerHTML = fileChipHtml(state.paper, 'paper', 0);
        dom.paperChip.querySelector('.chip-x').addEventListener('click', (e) => {
            e.stopPropagation();
            state.paper = null;
            renderPaperChip();
            updateButton();
        });
    }

    function renderRefChips() {
        dom.refsList.innerHTML = state.refs.map((f, i) => fileChipHtml(f, 'ref', i)).join('');
        dom.refsList.querySelectorAll('.chip-x').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                const i = parseInt(btn.dataset.i, 10);
                state.refs.splice(i, 1);
                renderRefChips();
                updateButton();
            });
        });
    }

    function fileChipHtml(file, kind, i) {
        return `
            <div class="file-chip">
                <svg class="chip-ico" viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/></svg>
                <span class="chip-name" title="${esc(file.name)}">${esc(file.name)}</span>
                <span class="chip-size">${fmtBytes(file.size)}</span>
                <button class="chip-x" type="button" data-i="${i}" title="Remove" aria-label="Remove ${esc(file.name)}">
                    <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M18 6L6 18M6 6l12 12"/></svg>
                </button>
            </div>`;
    }

    function updateButton() {
        dom.btnCheck.disabled = !(state.paper && (state.refs.length > 0 || state.useAcademic)) || state.analyzing;
    }

    function originTag(origin) {
        if (origin === 'openalex') return '<span class="origin-tag">OpenAlex</span>';
        if (origin === 'arxiv') return '<span class="origin-tag origin-arxiv">arXiv</span>';
        return '';
    }

    function sourceNameHtml(m) {
        const name = esc(m.source_name || '');
        return m.source_url
            ? `<a class="cmp-src" href="${esc(m.source_url)}" target="_blank" rel="noopener" title="${name}">${name}</a>`
            : `<span class="cmp-src" title="${name}">${name}</span>`;
    }

    function typeMeta(t) {
        if (t === 'verbatim') return { cls: 'mtag-verbatim', label: 'Verbatim' };
        if (t === 'translated') return { cls: 'mtag-translated', label: 'Translated' };
        return { cls: 'mtag-paraphrase', label: 'Paraphrase' };
    }
    function typeBadge(t) {
        const m = typeMeta(t);
        return `<span class="mtag ${m.cls}">${m.label}</span>`;
    }
    function langPair(m) {
        return (m.match_type === 'translated' && m.source_lang && m.doc_lang)
            ? `<span class="lang-pair">${esc(m.source_lang.toUpperCase())}→${esc(m.doc_lang.toUpperCase())}</span>`
            : '';
    }
    // A match in the inconclusive band (similarity between the reporting floor and
    // the confidence cutoff) must never be shown as a confirmed copy — ADR-0017.
    function isReview(m) { return m && m.confidence === 'review'; }
    function reviewBadge(m) {
        return isReview(m)
            ? `<span class="mtag mtag-review" title="Below the confidence cutoff — this passage is similar, but similar wording can also arise independently. Check it yourself; it is not a confirmed match.">Needs review</span>`
            : '';
    }

    // ─── Drag & drop wiring ───
    function wireDropzone(zone, input, onFiles, opts = {}) {
        ['dragenter', 'dragover'].forEach(ev =>
            zone.addEventListener(ev, e => { e.preventDefault(); e.stopPropagation(); zone.classList.add('drag-over'); }));
        ['dragleave', 'drop'].forEach(ev =>
            zone.addEventListener(ev, e => { e.preventDefault(); e.stopPropagation(); zone.classList.remove('drag-over'); }));
        zone.addEventListener('drop', e => {
            const files = e.dataTransfer && e.dataTransfer.files;
            if (files && files.length) onFiles(opts.multiple ? Array.from(files) : files[0]);
        });
        zone.addEventListener('click', () => input.click());
        input.addEventListener('change', e => {
            const files = e.target.files;
            if (files && files.length) onFiles(opts.multiple ? Array.from(files) : files[0]);
            input.value = ''; // allow re-selecting the same file
        });
    }

    // ─── Errors / progress ───
    function showError(msg) {
        dom.error.style.display = 'flex';
        dom.errorMsg.textContent = msg;
        dom.progress.style.display = 'none';
    }
    function hideError() { dom.error.style.display = 'none'; }
    function showProgress(on) {
        dom.progress.style.display = on ? 'block' : 'none';
        if (on) { hideError(); dom.btnCheck.style.display = 'none'; }
        else { dom.btnCheck.style.display = 'inline-flex'; }
    }

    // ─── Run ───
    function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

    /** Poll a submitted job until it finishes; resolves with the result or throws. */
    async function pollJob(jobId) {
        const TIMEOUT_MS = 180000;   // 3 minutes
        const started = Date.now();
        while (Date.now() - started < TIMEOUT_MS) {
            await sleep(1000);
            const r = await fetch(`${API_BASE}/api/check/${jobId}`);
            if (!r.ok) throw new Error(`Could not retrieve the check (${r.status}).`);
            const d = await r.json();
            if (d.status === 'done') return d.result;
            if (d.status === 'error') throw new Error(d.error || 'Check failed.');
            // queued / running → keep polling
        }
        throw new Error('The check timed out. Please try again.');
    }

    async function runCheck() {
        if (!state.paper || (state.refs.length === 0 && !state.useAcademic)) return;
        state.analyzing = true;
        updateButton();
        showProgress(true);
        const label = document.getElementById('check-progress-label');
        if (label) label.textContent = state.useAcademic ? 'Searching academic databases…' : 'Analyzing…';

        try {
            const fd = new FormData();
            fd.append('file', state.paper);
            state.refs.forEach(r => fd.append('references', r));
            fd.append('use_academic', state.useAcademic ? 'true' : 'false');

            const submit = await fetch(`${API_BASE}/api/check`, { method: 'POST', body: fd });
            if (!submit.ok) {
                const err = await submit.json().catch(() => ({}));
                throw new Error(err.detail || `Check failed (${submit.status})`);
            }
            const { job_id } = await submit.json();
            const result = await pollJob(job_id);
            state.result = result;
            renderResults(result);
            showView('results');
        } catch (err) {
            console.error('Originality check failed:', err);
            showError(err.message || 'Check failed. Please try again.');
        } finally {
            state.analyzing = false;
            showProgress(false);
            updateButton();
        }
    }

    // ─── Results rendering ───
    function renderResults(data) {
        const ov = data.overall || {};
        const matches = data.matches || [];
        const pct = ov.similarity_pct || 0;
        const hasTranslated = matches.some(m => m.match_type === 'translated');

        const reviewCount = ov.review_count || matches.filter(isReview).length;
        const reviewPct = ov.review_pct || 0;

        const disclaimer =
            `<p class="results-disclaimer">Self-check aid — not a determination of misconduct. Review each highlighted passage in context; legitimate quotation and common phrasing can also match.</p>`;

        // The inconclusive band, stated plainly rather than folded into the headline number.
        const reviewNote = reviewCount > 0
            ? `<p class="results-review-note"><b>${reviewCount}</b> of these ${reviewCount === 1 ? 'is a' : 'are'}
               <span class="mtag mtag-review">Needs review</span> match${reviewCount === 1 ? '' : 'es'}
               (${reviewPct.toFixed(1)}% of the document): similar wording, but below our confidence cutoff —
               such overlap can also happen by coincidence in shared terminology or standard phrasing.
               <b>Not counted as confirmed copying.</b></p>`
            : '';

        let summary = `
            <div class="check-summary">
                <div class="cs-score ${band(pct)}">
                    <div class="cs-num">${pct.toFixed(1)}<span>%</span></div>
                    <div class="cs-label">overall similarity</div>
                </div>
                <div class="cs-breakdown">
                    ${bar('Verbatim', ov.verbatim_pct || 0, 'hl-verbatim')}
                    ${bar('Paraphrase', ov.paraphrase_pct || 0, 'hl-paraphrase')}
                    ${(ov.translated_pct || 0) > 0 ? bar('Translated', ov.translated_pct, 'hl-translated') : ''}
                    ${reviewPct > 0 ? bar('Needs review', reviewPct, 'hl-review') : ''}
                    <div class="cs-stats">
                        <span class="cs-chip"><b>${ov.match_count || 0}</b> matches</span>
                        ${reviewCount > 0 ? `<span class="cs-chip cs-chip-review"><b>${reviewCount}</b> need review</span>` : ''}
                        <span class="cs-chip"><b>${ov.source_count || 0}</b> sources</span>
                        <span class="cs-chip"><b>${ov.matched_words || 0}</b>/${ov.total_words || 0} words</span>
                    </div>
                </div>
            </div>${reviewNote}`;

        const warnings = (data.warnings || []).length
            ? `<div class="results-warnings">${data.warnings.map(w => `<span>⚠ ${esc(w)}</span>`).join('')}</div>`
            : '';

        let layout;
        if (matches.length === 0) {
            layout = `
                <div class="no-anomalies" style="margin-top:24px;">
                    <span class="success-icon">✓</span>
                    <p class="empty-title">No overlap found</p>
                    <p>None of your passages closely matched the reference sources you provided.</p>
                </div>`;
        } else {
            layout = `
                <div class="results-layout">
                    <div class="doc-panel">
                        <div class="rp-title">Your document
                            <span class="rp-legend">
                                <span class="lg"><span class="sw hl-verbatim"></span>Verbatim</span>
                                <span class="lg"><span class="sw hl-paraphrase"></span>Paraphrase</span>
                                ${hasTranslated ? '<span class="lg"><span class="sw hl-translated"></span>Translated</span>' : ''}
                                ${reviewCount > 0 ? '<span class="lg"><span class="sw sw-review"></span>Needs review</span>' : ''}
                            </span>
                        </div>
                        <div class="doc-view" id="doc-view">${buildHighlightHtml(data.document_text || '', matches)}</div>
                    </div>
                    <div class="side-panel">
                        <div class="rp-title">Comparison</div>
                        <div class="match-detail" id="match-detail">
                            <p class="detail-empty">Select a highlighted passage to compare it with its source.</p>
                        </div>
                        <div class="rp-title">Matches <span class="muted">(${matches.length})</span></div>
                        <div class="match-list" id="match-list">${matches.map(matchRowHtml).join('')}</div>
                    </div>
                </div>`;
        }

        const toolbar = `
            <div class="results-toolbar">
                <button class="btn btn-secondary" id="btn-download-report" type="button">
                    <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="M7 10l5 5 5-5"/><path d="M12 15V3"/></svg>
                    Download report
                </button>
                <button class="btn btn-ghost" id="btn-print-report" type="button">Print / Save PDF</button>
            </div>`;
        dom.resultsContent.innerHTML = toolbar + summary + disclaimer + warnings + layout;

        const dl = document.getElementById('btn-download-report');
        const pr = document.getElementById('btn-print-report');
        if (dl) dl.addEventListener('click', downloadReport);
        if (pr) pr.addEventListener('click', printReport);

        if (matches.length > 0) {
            const docView = document.getElementById('doc-view');
            const matchList = document.getElementById('match-list');
            docView.querySelectorAll('mark.hl').forEach(mk =>
                mk.addEventListener('click', () => selectMatch(parseInt(mk.dataset.match, 10))));
            matchList.querySelectorAll('.match-row').forEach(row =>
                row.addEventListener('click', () => selectMatch(parseInt(row.dataset.match, 10))));
        }
    }

    function bar(label, pct, cls) {
        return `
            <div class="cs-row">
                <div class="cs-row-head"><span>${label}</span><span class="cs-row-val">${pct.toFixed(1)}%</span></div>
                <div class="cs-bar"><div class="cs-bar-fill ${cls}" style="width:${Math.min(pct, 100)}%"></div></div>
            </div>`;
    }

    function matchRowHtml(m) {
        return `
            <button class="match-row${isReview(m) ? ' is-review' : ''}" type="button" data-match="${m.id}">
                <span class="mr-top">${typeBadge(m.match_type)}${reviewBadge(m)}<span class="mr-sim">${pctInt(m.similarity)}%</span>${langPair(m)}${originTag(m.source_origin)}<span class="mr-src" title="${esc(m.source_name)}">${esc(trim(m.source_name, 24))}</span></span>
                <span class="mr-text">${esc(trim(m.doc_excerpt, 96))}</span>
            </button>`;
    }

    function buildHighlightHtml(text, matches) {
        const spans = matches
            .map(m => ({ start: m.doc_start, end: m.doc_end, id: m.id, type: m.match_type, review: isReview(m) }))
            .filter(s => Number.isInteger(s.start) && Number.isInteger(s.end) && s.end > s.start)
            .sort((a, b) => a.start - b.start || (a.type === 'verbatim' ? -1 : 1));

        // Resolve overlaps → clean non-overlapping segments (verbatim wins on ties).
        const kept = [];
        let cursor = 0;
        for (const s of spans) {
            const st = Math.max(s.start, cursor);
            if (st >= s.end) continue;
            kept.push({ start: st, end: s.end, id: s.id, type: s.type, review: s.review });
            cursor = s.end;
        }

        let html = '';
        let pos = 0;
        for (const s of kept) {
            html += esc(text.slice(pos, s.start));
            // Review-band spans get a distinct (dashed, muted) treatment so an
            // inconclusive hit never looks like a confirmed copy.
            html += `<mark class="hl hl-${s.type}${s.review ? ' hl-review' : ''}" data-match="${s.id}">${esc(text.slice(s.start, s.end))}</mark>`;
            pos = s.end;
        }
        html += esc(text.slice(pos));
        return html;
    }

    function selectMatch(id) {
        if (!state.result) return;
        const m = state.result.matches.find(x => x.id === id);
        if (!m) return;

        document.querySelectorAll('#doc-view mark.hl').forEach(el =>
            el.classList.toggle('active', parseInt(el.dataset.match, 10) === id));
        document.querySelectorAll('#match-list .match-row').forEach(el =>
            el.classList.toggle('active', parseInt(el.dataset.match, 10) === id));

        document.getElementById('match-detail').innerHTML = renderDetail(m);

        const mk = document.querySelector(`#doc-view mark.hl[data-match="${id}"]`);
        if (mk) mk.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }

    function renderDetail(m) {
        const para = m.paragraph_index != null ? `Paragraph ${m.paragraph_index + 1}` : '';
        const reviewCallout = isReview(m)
            ? `<p class="cmp-review-note"><b>Inconclusive — needs your review.</b> This passage is similar to the
               source but falls below our confidence cutoff. Independently written text on the same topic (shared
               terminology, standard methods phrasing) can look like this too. Compare them yourself before
               treating it as reuse.</p>`
            : '';
        return `
            ${reviewCallout}
            <div class="cmp">
                <div class="cmp-col">
                    <div class="cmp-head">Your paper <span class="cmp-sub">${esc(para)}</span></div>
                    <div class="cmp-body">${esc(m.doc_excerpt || '')}</div>
                </div>
                <div class="cmp-col">
                    <div class="cmp-head">${typeBadge(m.match_type)}${reviewBadge(m)}${langPair(m)}${originTag(m.source_origin)}${sourceNameHtml(m)}<span class="cmp-sub">${pctInt(m.similarity)}% match</span></div>
                    <div class="cmp-body">${highlightExcerpt(m.source_context || m.source_excerpt || '', m.source_excerpt || '')}</div>
                </div>
            </div>`;
    }

    function highlightExcerpt(context, excerpt) {
        const ctx = esc(context);
        const exc = esc(excerpt);
        if (!exc) return ctx;
        const idx = ctx.indexOf(exc);
        if (idx === -1) return ctx;
        return ctx.slice(0, idx) + `<mark class="hl hl-verbatim">${exc}</mark>` + ctx.slice(idx + exc.length);
    }

    // ─── Downloadable / printable report ───
    function reportOrigin(origin) {
        if (origin === 'openalex') return ' <span class="oa">OpenAlex</span>';
        if (origin === 'arxiv') return ' <span class="oa oa-arxiv">arXiv</span>';
        return '';
    }

    function baseName(name) {
        return (name || 'document').replace(/\.[^.]+$/, '').replace(/[^\w.-]+/g, '_').slice(0, 60) || 'document';
    }

    function reportStyles() {
        return `
            *{box-sizing:border-box} body{font-family:'Inter',-apple-system,Segoe UI,sans-serif;color:#10131a;line-height:1.6;margin:0;background:#f6f7f9}
            .wrap{max-width:860px;margin:0 auto;padding:40px 28px}
            h1{font-size:24px;margin:0 0 4px} h2{font-size:16px;margin:28px 0 10px;border-bottom:1px solid #e7e9ef;padding-bottom:6px}
            h3{font-size:14px;margin:0 0 6px}
            .meta{color:#6b7280;font-size:12px}
            .rep-score{margin-top:20px;padding:20px;border-radius:14px;border:1px solid #e7e9ef;text-align:center}
            .rep-score.band-ok{background:#f0fdf4;border-color:#bbf7d0} .rep-score.band-warn{background:#fffbeb;border-color:#fde68a} .rep-score.band-danger{background:#fef2f2;border-color:#fecaca}
            .rep-score .big{font-size:40px;font-weight:800;font-family:'JetBrains Mono',monospace;line-height:1}
            .rep-score.band-ok .big{color:#059669} .rep-score.band-warn .big{color:#d97706} .rep-score.band-danger .big{color:#dc2626}
            .rep-score .lbl{font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:#6b7280;font-weight:600}
            .rep-score .sub{margin-top:8px;font-size:12px;color:#4b5563}
            ul.src{font-size:13px;padding-left:18px} ul.src a{color:#4f46e5}
            .legend{font-size:12px;color:#4b5563;margin-bottom:6px}
            .legend .sw{display:inline-block;width:11px;height:11px;border-radius:3px;vertical-align:middle;margin:0 4px 0 10px}
            .legend .sw.v{background:#dc2626} .legend .sw.p{background:#d97706} .legend .sw.t{background:#0d9488}
            .legend .sw.r{background:transparent;border:1.5px dashed #6b7280}
            .rep-score .sub.rev{color:#6b7280;font-style:italic}
            .doc{white-space:pre-wrap;word-break:break-word;font-size:13px;background:#fff;border:1px solid #e7e9ef;border-radius:12px;padding:18px}
            mark.hl{border-radius:3px;padding:0 1px}
            mark.hl-verbatim{background:rgba(220,38,38,.16);border-bottom:2px solid rgba(220,38,38,.55)}
            mark.hl-paraphrase{background:rgba(217,119,6,.18);border-bottom:2px solid rgba(217,119,6,.55)}
            mark.hl-translated{background:rgba(13,148,136,.16);border-bottom:2px solid rgba(13,148,136,.6)}
            /* Inconclusive band: muted fill + dashed underline so it reads as "unconfirmed". */
            mark.hl.hl-review{background:rgba(107,114,128,.10);border-bottom:2px dashed rgba(107,114,128,.7)}
            .m{border:1px solid #e7e9ef;border-radius:10px;padding:12px;margin-bottom:10px;background:#fff}
            .m.m-review{border-style:dashed;background:#fcfcfd}
            .m-note{font-size:11px;color:#6b7280;font-style:italic;margin:-4px 0 8px}
            .m-h{font-size:12px;font-weight:600;margin-bottom:8px}
            .m-badge{font-size:10px;font-weight:700;text-transform:uppercase;padding:2px 7px;border-radius:999px;margin-right:6px}
            .m-badge.verbatim{color:#dc2626;background:rgba(220,38,38,.1)} .m-badge.paraphrase{color:#d97706;background:rgba(217,119,6,.1)} .m-badge.translated{color:#0d9488;background:rgba(13,148,136,.1)}
            .m-badge.review{color:#4b5563;background:transparent;border:1px dashed #9ca3af}
            .lp{font-size:10px;color:#0d9488;font-weight:700;margin-right:4px}
            .m-h a{color:#4f46e5} .oa{font-size:10px;color:#0369a1;background:rgba(14,165,233,.12);padding:1px 6px;border-radius:999px;font-weight:700} .oa.oa-arxiv{color:#b31b1b;background:rgba(179,27,27,.1)}
            .m-b{display:grid;grid-template-columns:1fr 1fr;gap:10px}
            .m-lab{font-size:10px;text-transform:uppercase;letter-spacing:.05em;color:#6b7280;font-weight:700;margin-bottom:3px}
            .m-x{font-size:12px;color:#374151;background:#f1f3f7;border-radius:6px;padding:8px;white-space:pre-wrap;word-break:break-word}
            .rep-foot{margin-top:30px;border-top:1px solid #e7e9ef;padding-top:14px;color:#6b7280;font-size:12px}
            .none{color:#6b7280}
            @media print{body{background:#fff}.wrap{padding:0}.m,.doc,.rep-score{break-inside:avoid}}
        `;
    }

    function generateReportHtml(data) {
        const ov = data.overall || {};
        const matches = data.matches || [];
        const docName = esc((state.paper && state.paper.name) || data.filename || 'document');
        const when = esc(new Date().toLocaleString());
        const scoreBand = band(ov.similarity_pct || 0);

        const sources = (data.sources || []).map(s => {
            const nm = esc(s.name || '');
            const link = s.url ? `<a href="${esc(s.url)}">${nm}</a>` : nm;
            const oa = reportOrigin(s.origin);
            return `<li>${link}${oa}</li>`;
        }).join('');

        const docHtml = buildHighlightHtml(data.document_text || '', matches);

        const hasTranslated = matches.some(m => m.match_type === 'translated');
        const matchesHtml = matches.map(m => {
            const label = typeMeta(m.match_type).label;
            const lp = (m.match_type === 'translated' && m.source_lang && m.doc_lang)
                ? `<span class="lp">${esc(m.source_lang.toUpperCase())}→${esc(m.doc_lang.toUpperCase())}</span>` : '';
            const src = m.source_url ? `<a href="${esc(m.source_url)}">${esc(m.source_name || '')}</a>` : esc(m.source_name || '');
            const oa = reportOrigin(m.source_origin);
            const para = m.paragraph_index != null ? ` · ¶${m.paragraph_index + 1}` : '';
            const rev = isReview(m) ? `<span class="m-badge review">Needs review</span>` : '';
            return `
                <div class="m${isReview(m) ? ' m-review' : ''}">
                    <div class="m-h"><span class="m-badge ${m.match_type}">${label}</span>${rev}${lp}${pctInt(m.similarity)}% — ${src}${oa}${para}</div>
                    ${isReview(m) ? `<div class="m-note">Below the confidence cutoff — similar wording that can also arise independently. Not a confirmed copy; verify in context.</div>` : ''}
                    <div class="m-b">
                        <div><div class="m-lab">Your paper</div><div class="m-x">${esc(m.doc_excerpt || '')}</div></div>
                        <div><div class="m-lab">Source</div><div class="m-x">${highlightExcerpt(m.source_context || m.source_excerpt || '', m.source_excerpt || '')}</div></div>
                    </div>
                </div>`;
        }).join('');

        return `<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>Originality Report — ${docName}</title><style>${reportStyles()}</style></head>
<body><div class="wrap">
    <header><h1>Originality Report</h1>
        <div class="meta">Document: <b>${docName}</b> · Generated: ${when} · Engine: P.R.I.S.M. (offline · n-gram + MiniLM)</div>
    </header>
    <section class="rep-score ${scoreBand}">
        <div class="big">${(ov.similarity_pct || 0).toFixed(1)}%</div>
        <div class="lbl">overall similarity</div>
        <div class="sub">Verbatim ${(ov.verbatim_pct || 0).toFixed(1)}% · Paraphrase ${(ov.paraphrase_pct || 0).toFixed(1)}%${(ov.translated_pct || 0) > 0 ? ` · Translated ${(ov.translated_pct || 0).toFixed(1)}%` : ''} · ${ov.match_count || 0} matches · ${ov.source_count || 0} sources · ${ov.matched_words || 0}/${ov.total_words || 0} words</div>
        ${(ov.review_count || 0) > 0 ? `<div class="sub rev">${ov.review_count} match${ov.review_count === 1 ? '' : 'es'} (${(ov.review_pct || 0).toFixed(1)}% of the document) fall below the confidence cutoff and are marked <b>Needs review</b> — not counted as confirmed copying.</div>` : ''}
    </section>
    ${sources ? `<h2>Sources checked</h2><ul class="src">${sources}</ul>` : ''}
    <h2>Document</h2>
    <div class="legend"><span class="sw v"></span>Verbatim<span class="sw p"></span>Paraphrase${hasTranslated ? '<span class="sw t"></span>Translated' : ''}${(ov.review_count || 0) > 0 ? '<span class="sw r"></span>Needs review (inconclusive)' : ''}</div>
    <div class="doc">${docHtml}</div>
    ${matches.length ? `<h2>Matches (${matches.length})</h2>${matchesHtml}` : '<p class="none">No matching passages were found.</p>'}
    <footer class="rep-foot"><h3>Method &amp; limitations</h3>
        <p>Verbatim matches are contiguous identical word sequences; paraphrase matches are sentence-level
        semantic similarity (local MiniLM cosine). Matches at/above a cosine of <b>0.78</b> are reported as
        confident; those between <b>0.66 and 0.78</b> are reported as <b>“Needs review”</b> — an explicit
        inconclusive band, because independently written text on the same topic can reach that range.
        This is a self-check aid and <b>not a determination of misconduct</b>. Legitimate quotation, common
        phrasing, shared terminology and citations can also match. Academic-database matches are compared
        against paper <i>abstracts</i>, not full text. Review every flagged passage in context.</p>
        <p><b>Coverage:</b> your uploaded references plus (if enabled) OpenAlex and arXiv — <b>not</b> the full
        web or subscription journal databases. A clean result here is not a guarantee of passing a publisher’s
        similarity check.</p>
    </footer>
</div></body></html>`;
    }

    function downloadReport() {
        if (!state.result) return;
        const html = generateReportHtml(state.result);
        const blob = new Blob([html], { type: 'text/html' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `originality-report-${baseName(state.paper && state.paper.name)}.html`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        setTimeout(() => URL.revokeObjectURL(url), 2000);
    }

    function printReport() {
        if (!state.result) return;
        const w = window.open('', '_blank');
        if (!w) { showError('Enable pop-ups to print the report, or use "Download report".'); return; }
        w.document.write(generateReportHtml(state.result));
        w.document.close();
        setTimeout(() => { w.focus(); w.print(); }, 350);
    }

    // ─── View switching ───
    function showView(view) {
        const isResults = view === 'results';
        dom.viewUpload.classList.toggle('active', !isResults);
        dom.viewResults.classList.toggle('active', isResults);
        dom.navCheck.classList.toggle('active', !isResults);
        dom.navResults.classList.toggle('active', isResults);
        dom.navResults.disabled = !state.result;
        dom.btnNewCheck.style.display = isResults ? 'inline-flex' : 'none';
        dom.topTitle.textContent = isResults ? 'Originality Report' : 'Originality Check';
        dom.topDesc.textContent = isResults
            ? 'Matched passages and their sources'
            : 'Find copied & paraphrased passages and their sources';
        window.scrollTo({ top: 0, behavior: 'smooth' });
    }

    function reset() {
        state.paper = null;
        state.refs = [];
        state.useAcademic = false;
        state.result = null;
        if (dom.academicToggle) dom.academicToggle.checked = false;
        renderPaperChip();
        renderRefChips();
        dom.resultsContent.innerHTML = '';
        hideError();
        showProgress(false);
        updateButton();
        showView('upload');
    }

    // ─── Init ───
    function init() {
        dom.paperDrop = document.getElementById('paper-drop');
        dom.paperInput = document.getElementById('paper-input');
        dom.paperChip = document.getElementById('paper-chip');
        dom.refsDrop = document.getElementById('refs-drop');
        dom.refsInput = document.getElementById('refs-input');
        dom.refsList = document.getElementById('refs-list');
        dom.academicToggle = document.getElementById('academic-toggle');
        dom.btnCheck = document.getElementById('btn-check');
        dom.progress = document.getElementById('check-progress');
        dom.error = document.getElementById('check-error');
        dom.errorMsg = document.getElementById('check-error-msg');
        dom.btnRetry = document.getElementById('btn-check-retry');
        dom.viewUpload = document.getElementById('view-upload');
        dom.viewResults = document.getElementById('view-results');
        dom.resultsContent = document.getElementById('results-content');
        dom.navCheck = document.getElementById('nav-check');
        dom.navResults = document.getElementById('nav-results');
        dom.btnNewCheck = document.getElementById('btn-new-check');
        dom.topTitle = document.getElementById('topbar-title');
        dom.topDesc = document.getElementById('topbar-desc');

        wireDropzone(dom.paperDrop, dom.paperInput, setPaper, { multiple: false });
        wireDropzone(dom.refsDrop, dom.refsInput, addRefs, { multiple: true });

        dom.academicToggle.addEventListener('change', () => {
            state.useAcademic = dom.academicToggle.checked;
            updateButton();
        });
        dom.btnCheck.addEventListener('click', runCheck);
        dom.btnRetry.addEventListener('click', () => { hideError(); });
        dom.btnNewCheck.addEventListener('click', reset);
        dom.navCheck.addEventListener('click', () => { if (!state.analyzing) showView('upload'); });
        dom.navResults.addEventListener('click', () => { if (state.result) showView('results'); });

        console.log('%c🔎 P.R.I.S.M. Originality Checker', 'color:#4f46e5;font-weight:bold;font-size:14px;');
    }

    document.addEventListener('DOMContentLoaded', init);
})();
