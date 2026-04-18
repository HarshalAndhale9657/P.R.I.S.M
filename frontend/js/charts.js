/**
 * P.R.I.S.M. — Charts Renderer
 * Visualizes stylometric features using Chart.js
 */

const ChartsRenderer = (() => {
    // Shared chart options for dark theme
    const commonOptions = {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
            legend: {
                labels: { color: '#e6edf3', font: { family: 'Inter' } }
            },
            tooltip: {
                backgroundColor: 'rgba(22, 27, 34, 0.9)',
                titleColor: '#e6edf3',
                bodyColor: '#c9d1d9',
                borderColor: '#30363d',
                borderWidth: 1,
            }
        },
        scales: {
            x: {
                ticks: { color: '#8b949e' },
                grid: { color: '#21262d' }
            },
            y: {
                ticks: { color: '#8b949e' },
                grid: { color: '#21262d' }
            }
        }
    };

    let featureChart = null;
    let ratioChart = null;
    let clusterChart = null;

    function render(analysisData) {
        if (!analysisData || !analysisData.profiles || !analysisData.paragraphs) return;

        const profiles = analysisData.profiles;
        const paragraphs = analysisData.paragraphs;
        
        // Find indices for specific features (referencing feature_names)
        const featureNames = analysisData.feature_names || [
            "avg_sentence_length", "avg_word_length", "pronoun_ratio", 
            "preposition_ratio", "conjunction_ratio", "passive_voice_pct", "yules_k"
        ];
        
        const yulesKIdx = featureNames.indexOf("yules_k");
        const sentLenIdx = featureNames.indexOf("avg_sentence_length");
        
        const labels = paragraphs.map((_, i) => `¶ ${i + 1}`);
        const clusters = paragraphs.map(p => p.cluster_id);
        
        // Colors mapping
        const pointColors = clusters.map(c => PRISM.getClusterColor(c, analysisData.estimated_authors).border);

        renderFeatureChart(labels, profiles, yulesKIdx, sentLenIdx, pointColors);
        renderRatioChart(labels, profiles, featureNames);
        renderClusterChart(paragraphs, profiles, yulesKIdx, sentLenIdx, pointColors);
    }

    function renderFeatureChart(labels, profiles, yulesKIdx, sentLenIdx, pointColors) {
        const ctx = document.getElementById('chart-features');
        if (!ctx) return;
        
        if (featureChart) featureChart.destroy();
        
        // If indices invalid, fallback to 0 and 1
        const id1 = yulesKIdx >= 0 ? yulesKIdx : 0;
        const id2 = sentLenIdx >= 0 ? sentLenIdx : 1;

        const data1 = profiles.map(p => p[id1]);
        const data2 = profiles.map(p => p[id2]);

        featureChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: labels,
                datasets: [
                    {
                        label: 'Lexical Richness (Yule\'s K)',
                        data: data1,
                        borderColor: '#7c3aed',
                        backgroundColor: 'transparent',
                        borderWidth: 2,
                        tension: 0.3,
                        pointBackgroundColor: pointColors,
                        pointBorderColor: pointColors,
                        pointRadius: 4,
                        yAxisID: 'y'
                    },
                    {
                        label: 'Sentence Length',
                        data: data2,
                        borderColor: '#06b6d4',
                        backgroundColor: 'transparent',
                        borderWidth: 2,
                        borderDash: [5, 5],
                        tension: 0.3,
                        pointBackgroundColor: pointColors,
                        pointBorderColor: pointColors,
                        pointRadius: 4,
                        yAxisID: 'y1'
                    }
                ]
            },
            options: {
                ...commonOptions,
                scales: {
                    x: commonOptions.scales.x,
                    y: {
                        type: 'linear',
                        display: true,
                        position: 'left',
                        ticks: { color: '#8b949e' },
                        grid: { color: '#21262d' }
                    },
                    y1: {
                        type: 'linear',
                        display: true,
                        position: 'right',
                        ticks: { color: '#8b949e' },
                        grid: { drawOnChartArea: false }
                    }
                }
            }
        });
    }

    function renderRatioChart(labels, profiles, featureNames) {
        const ctx = document.getElementById('chart-ratios');
        if (!ctx) return;
        
        if (ratioChart) ratioChart.destroy();

        const proIdx = featureNames.indexOf("pronoun_ratio");
        const prepIdx = featureNames.indexOf("preposition_ratio");
        const conjIdx = featureNames.indexOf("conjunction_ratio");
        
        const dataPro = profiles.map(p => p[proIdx >= 0 ? proIdx : 2]);
        const dataPrep = profiles.map(p => p[prepIdx >= 0 ? prepIdx : 3]);
        const dataConj = profiles.map(p => p[conjIdx >= 0 ? conjIdx : 4]);

        ratioChart = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: labels,
                datasets: [
                    {
                        label: 'Pronouns',
                        data: dataPro,
                        backgroundColor: 'rgba(124, 58, 237, 0.7)',
                    },
                    {
                        label: 'Prepositions',
                        data: dataPrep,
                        backgroundColor: 'rgba(6, 182, 212, 0.7)',
                    },
                    {
                        label: 'Conjunctions',
                        data: dataConj,
                        backgroundColor: 'rgba(167, 139, 250, 0.7)',
                    }
                ]
            },
            options: {
                ...commonOptions,
                scales: {
                    x: { stacked: true, ...commonOptions.scales.x },
                    y: { stacked: true, ...commonOptions.scales.y }
                }
            }
        });
    }

    function renderClusterChart(paragraphs, profiles, yulesKIdx, sentLenIdx, pointColors) {
        const ctx = document.getElementById('chart-clusters');
        if (!ctx) return;
        
        if (clusterChart) clusterChart.destroy();

        const id1 = yulesKIdx >= 0 ? yulesKIdx : 0;
        const id2 = sentLenIdx >= 0 ? sentLenIdx : 1;

        const scatterData = paragraphs.map((p, i) => ({
            x: profiles[i][id1],
            y: profiles[i][id2],
            label: `¶ ${i + 1}`,
            cluster: p.cluster_id
        }));

        clusterChart = new Chart(ctx, {
            type: 'scatter',
            data: {
                datasets: [{
                    label: 'Paragraphs',
                    data: scatterData,
                    backgroundColor: pointColors,
                    borderColor: pointColors,
                    pointRadius: paragraphs.map(p => p.cluster_id === -1 ? 8 : 6),
                    pointHoverRadius: 10,
                }]
            },
            options: {
                ...commonOptions,
                plugins: {
                    ...commonOptions.plugins,
                    tooltip: {
                        ...commonOptions.plugins.tooltip,
                        callbacks: {
                            label: (context) => {
                                const pt = context.raw;
                                const clusterName = pt.cluster === -1 ? 'ANOMALY' : `Cluster ${pt.cluster}`;
                                return `${pt.label} (${clusterName}) - x: ${pt.x.toFixed(2)}, y: ${pt.y.toFixed(2)}`;
                            }
                        }
                    }
                },
                scales: {
                    x: {
                        ...commonOptions.scales.x,
                        title: { display: true, text: 'Lexical Richness', color: '#8b949e' }
                    },
                    y: {
                        ...commonOptions.scales.y,
                        title: { display: true, text: 'Sentence Length', color: '#8b949e' }
                    }
                }
            }
        });
    }

    return { render };
})();
