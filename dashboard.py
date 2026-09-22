import json
import logging
import threading
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from typing import Optional
from storage import Storage

logger = logging.getLogger("dashboard")

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="fr" class="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Xena // TypeSafe Jev & Gemini Telemetry</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
  <script src="https://unpkg.com/lucide@latest"></script>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600;700&family=Inter:wght@400;500;600;700;800&display=swap');
    body { font-family: 'Inter', sans-serif; }
    .mono { font-family: 'JetBrains Mono', monospace; }
    .glow-purple { box-shadow: 0 0 25px -5px rgba(168, 85, 247, 0.25); }
    .glow-emerald { box-shadow: 0 0 25px -5px rgba(16, 185, 129, 0.25); }
    .glow-cyan { box-shadow: 0 0 25px -5px rgba(56, 189, 248, 0.25); }
  </style>
</head>
<body class="bg-[#090d16] text-slate-100 min-h-screen flex flex-col antialiased selection:bg-purple-500 selection:text-white">

  <!-- TOP HEADER -->
  <header class="border-b border-slate-800/80 bg-[#0d1322]/80 backdrop-blur-md sticky top-0 z-30 px-6 py-4">
    <div class="max-w-7xl mx-auto flex flex-wrap items-center justify-between gap-4">
      <div class="flex items-center gap-3">
        <div class="w-10 h-10 rounded-xl bg-gradient-to-tr from-purple-600 to-cyan-500 flex items-center justify-center font-black text-white shadow-lg shadow-purple-500/20">
          X
        </div>
        <div>
          <div class="flex items-center gap-2">
            <h1 class="font-bold text-lg tracking-tight text-white">XENA // HYBRID TELEMETRY</h1>
            <span class="px-2 py-0.5 rounded text-[10px] font-semibold bg-purple-500/20 text-purple-300 border border-purple-500/30">System 1 + 2</span>
          </div>
          <p class="text-xs text-slate-400">TypeSafe AI (Jev) &amp; Google Gemini Live Cost &amp; Latency Tracker</p>
        </div>
      </div>

      <div class="flex items-center gap-4">
        <div class="flex items-center gap-2 px-3 py-1.5 rounded-full bg-slate-900/90 border border-slate-800 text-xs text-slate-300">
          <span class="w-2 h-2 rounded-full bg-emerald-400 animate-ping"></span>
          <span class="w-2 h-2 rounded-full bg-emerald-400 -ml-4"></span>
          <span>LIVE • Refresh 3s</span>
        </div>
        <button onclick="fetchData()" class="px-3 py-1.5 rounded-lg bg-purple-600/20 hover:bg-purple-600/30 border border-purple-500/30 text-purple-300 text-xs font-medium transition-all flex items-center gap-1.5">
          <i data-lucide="refresh-cw" class="w-3.5 h-3.5"></i> Actualiser
        </button>
      </div>
    </div>
  </header>

  <main class="max-w-7xl mx-auto w-full px-6 py-8 flex-1 space-y-8">

    <!-- KPI CARDS -->
    <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-5">

      <!-- KPI 1 : Économies -->
      <div class="bg-slate-900/80 border border-slate-800 rounded-2xl p-5 glow-emerald hover:border-emerald-500/40 transition-all">
        <div class="flex items-center justify-between text-slate-400 mb-3">
          <span class="text-xs font-semibold uppercase tracking-wider">Économie Token Réalisée</span>
          <div class="w-8 h-8 rounded-lg bg-emerald-500/10 text-emerald-400 flex items-center justify-center">
            <i data-lucide="dollar-sign" class="w-4 h-4"></i>
          </div>
        </div>
        <div class="flex items-baseline gap-2">
          <span id="kpi-savings" class="text-3xl font-extrabold text-emerald-400 mono">$0.0000</span>
          <span id="kpi-savings-pct" class="text-xs px-2 py-0.5 rounded-full bg-emerald-500/20 text-emerald-300 font-semibold">+0%</span>
        </div>
        <div class="mt-3 pt-3 border-t border-slate-800/80 flex justify-between text-xs text-slate-400">
          <span>Coût Hybride : <b id="kpi-cost-hybrid" class="text-slate-200 mono">$0.00</b></span>
          <span>Sans Jev : <b id="kpi-cost-without" class="text-slate-200 mono">$0.00</b></span>
        </div>
      </div>

      <!-- KPI 2 : Vitesse Jev -->
      <div class="bg-slate-900/80 border border-slate-800 rounded-2xl p-5 glow-purple hover:border-purple-500/40 transition-all">
        <div class="flex items-center justify-between text-slate-400 mb-3">
          <span class="text-xs font-semibold uppercase tracking-wider">Vitesse d'Exécution Jev</span>
          <div class="w-8 h-8 rounded-lg bg-purple-500/10 text-purple-400 flex items-center justify-center">
            <i data-lucide="zap" class="w-4 h-4"></i>
          </div>
        </div>
        <div class="flex items-baseline gap-2">
          <span id="kpi-jev-speed" class="text-3xl font-extrabold text-purple-400 mono">0 ms</span>
          <span id="kpi-speedup" class="text-xs px-2 py-0.5 rounded-full bg-purple-500/20 text-purple-300 font-semibold">1x</span>
        </div>
        <div class="mt-3 pt-3 border-t border-slate-800/80 flex justify-between text-xs text-slate-400">
          <span>Jev moyen : <b id="kpi-avg-jev" class="text-slate-200 mono">0 ms</b></span>
          <span>Gemini moyen : <b id="kpi-avg-gemini" class="text-slate-200 mono">0 ms</b></span>
        </div>
      </div>

      <!-- KPI 3 : Taux de Filtrage Jev -->
      <div class="bg-slate-900/80 border border-slate-800 rounded-2xl p-5 glow-cyan hover:border-cyan-500/40 transition-all">
        <div class="flex items-center justify-between text-slate-400 mb-3">
          <span class="text-xs font-semibold uppercase tracking-wider">Taux de Filtrage Jev</span>
          <div class="w-8 h-8 rounded-lg bg-cyan-500/10 text-cyan-400 flex items-center justify-center">
            <i data-lucide="filter" class="w-4 h-4"></i>
          </div>
        </div>
        <div class="flex items-baseline gap-2">
          <span id="kpi-filter-rate" class="text-3xl font-extrabold text-cyan-400 mono">0.0%</span>
          <span class="text-xs text-slate-400">du bruit éliminé</span>
        </div>
        <div class="mt-3 pt-3 border-t border-slate-800/80 flex justify-between text-xs text-slate-400">
          <span>Rejetés par Jev : <b id="kpi-rejected-count" class="text-rose-400 mono">0</b></span>
          <span>Qualifiés : <b id="kpi-qualified-count" class="text-emerald-400 mono">0</b></span>
        </div>
      </div>

      <!-- KPI 4 : Total Articles -->
      <div class="bg-slate-900/80 border border-slate-800 rounded-2xl p-5 hover:border-slate-700 transition-all">
        <div class="flex items-center justify-between text-slate-400 mb-3">
          <span class="text-xs font-semibold uppercase tracking-wider">Articles Analysés</span>
          <div class="w-8 h-8 rounded-lg bg-slate-800 text-slate-300 flex items-center justify-center">
            <i data-lucide="layers" class="w-4 h-4"></i>
          </div>
        </div>
        <div class="flex items-baseline gap-2">
          <span id="kpi-total-articles" class="text-3xl font-extrabold text-white mono">0</span>
          <span class="text-xs text-slate-400">évaluations</span>
        </div>
        <div class="mt-3 pt-3 border-t border-slate-800/80 flex justify-between text-xs text-slate-400">
          <span>Modèle Jev : <b class="text-purple-300 mono">jev-1.13.0</b></span>
          <span>Modèle LLM : <b class="text-cyan-300 mono">gemini-3.6-flash</b></span>
        </div>
      </div>

    </div>

    <!-- CHARTS ROW -->
    <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
      
      <!-- Chart 1 : Répartition des décisions -->
      <div class="bg-slate-900/80 border border-slate-800 rounded-2xl p-6">
        <div class="flex items-center justify-between mb-4">
          <h2 class="font-bold text-sm text-slate-200">Répartition des Décisions Jev</h2>
          <span class="text-xs text-slate-400">Filtrage Étage 1</span>
        </div>
        <div class="h-56 relative flex items-center justify-center">
          <canvas id="decisionsChart"></canvas>
        </div>
        <div class="mt-4 flex justify-around text-xs text-slate-400 border-t border-slate-800 pt-3">
          <div class="flex items-center gap-1.5"><span class="w-2.5 h-2.5 rounded-full bg-emerald-400"></span> Qualifiés Gemini</div>
          <div class="flex items-center gap-1.5"><span class="w-2.5 h-2.5 rounded-full bg-rose-500"></span> Rejetés par Jev</div>
        </div>
      </div>

      <!-- Chart 2 : Comparatif Latence Jev vs Gemini -->
      <div class="lg:col-span-2 bg-slate-900/80 border border-slate-800 rounded-2xl p-6">
        <div class="flex items-center justify-between mb-4">
          <div>
            <h2 class="font-bold text-sm text-slate-200">Vitesse d'Exécution par Article (ms)</h2>
            <p class="text-xs text-slate-400">Latence TypeSafe Jev (~100-200ms) vs Google Gemini (~1000-2000ms)</p>
          </div>
          <span class="text-xs font-mono px-2 py-1 rounded bg-purple-500/10 text-purple-400 border border-purple-500/20">Ratio ~12x</span>
        </div>
        <div class="h-56 relative">
          <canvas id="latencyChart"></canvas>
        </div>
      </div>

    </div>

    <!-- LIVE TABLE ROW -->
    <div class="bg-slate-900/80 border border-slate-800 rounded-2xl overflow-hidden">
      <div class="px-6 py-4 border-b border-slate-800 flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 class="font-bold text-base text-slate-100">Flux d'Évaluation en Direct</h2>
          <p class="text-xs text-slate-400">Chaque publication évaluée par Jev avec métriques de coût et probabilités</p>
        </div>
        
        <div class="flex items-center gap-2">
          <select id="filter-select" onchange="applyFilter()" class="bg-slate-800 border border-slate-700 text-xs text-slate-200 rounded-lg px-3 py-1.5 focus:outline-none focus:border-purple-500">
            <option value="all">Tous les articles</option>
            <option value="QUALIFIED">Qualifiés Gemini uniquement</option>
            <option value="REJECTED">Rejetés par Jev uniquement</option>
          </select>
        </div>
      </div>

      <div class="overflow-x-auto">
        <table class="w-full text-left text-xs text-slate-300">
          <thead class="bg-slate-950/60 text-slate-400 uppercase tracking-wider text-[11px] font-semibold border-b border-slate-800">
            <tr>
              <th class="py-3 px-4">Statut / Décision</th>
              <th class="py-3 px-4">Article &amp; Source</th>
              <th class="py-3 px-4">Probabilités Jev</th>
              <th class="py-3 px-4">Temps d'Exécution</th>
              <th class="py-3 px-4">Économie Token</th>
              <th class="py-3 px-4 text-right">Détails</th>
            </tr>
          </thead>
          <tbody id="logs-tbody" class="divide-y divide-slate-800/60">
            <tr>
              <td colspan="6" class="py-8 text-center text-slate-500">
                <i data-lucide="loader-2" class="w-6 h-6 animate-spin mx-auto mb-2 text-purple-400"></i>
                Chargement des métriques en direct...
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

  </main>

  <!-- MODAL DETAILS -->
  <div id="modal" class="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm hidden items-center justify-center p-4">
    <div class="bg-slate-900 border border-slate-700 rounded-2xl max-w-2xl w-full p-6 shadow-2xl space-y-4 max-h-[90vh] overflow-y-auto">
      <div class="flex items-start justify-between">
        <div>
          <span id="modal-badge" class="px-2 py-0.5 rounded text-[10px] font-bold uppercase"></span>
          <h3 id="modal-title" class="font-bold text-base text-white mt-1"></h3>
          <p id="modal-source" class="text-xs text-slate-400"></p>
        </div>
        <button onclick="closeModal()" class="text-slate-400 hover:text-white p-1 rounded-lg hover:bg-slate-800">
          <i data-lucide="x" class="w-5 h-5"></i>
        </button>
      </div>

      <div class="grid grid-cols-2 gap-3 py-2 border-y border-slate-800 text-xs">
        <div class="p-3 bg-slate-950/60 rounded-xl border border-slate-800/80">
          <span class="text-slate-400 block mb-1">Probabilité Scoop (Jev) :</span>
          <span id="modal-p-scoop" class="text-lg font-extrabold text-purple-400 mono"></span>
        </div>
        <div class="p-3 bg-slate-950/60 rounded-xl border border-slate-800/80">
          <span class="text-slate-400 block mb-1">Parti pris / Promo (Jev) :</span>
          <span id="modal-p-opinion" class="text-lg font-extrabold text-rose-400 mono"></span>
        </div>
      </div>

      <div>
        <h4 class="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-1">Motif / Décision Jev :</h4>
        <p id="modal-reason" class="text-xs text-slate-200 bg-slate-950 p-3 rounded-xl border border-slate-800/80"></p>
      </div>

      <div id="modal-tweet-container">
        <h4 class="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-1">Tweet Généré par Gemini :</h4>
        <p id="modal-tweet" class="text-xs text-cyan-200 bg-cyan-950/30 p-3 rounded-xl border border-cyan-800/40 font-mono"></p>
      </div>

      <div class="flex justify-end pt-2">
        <button onclick="closeModal()" class="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-white text-xs font-semibold">Fermer</button>
      </div>
    </div>
  </div>

  <script>
    let rawLogs = [];
    let decisionsChart = null;
    let latencyChart = null;

    function initCharts() {
      const ctxD = document.getElementById('decisionsChart').getContext('2d');
      decisionsChart = new Chart(ctxD, {
        type: 'doughnut',
        data: {
          labels: ['Qualifiés Gemini', 'Rejetés par Jev'],
          datasets: [{
            data: [1, 1],
            backgroundColor: ['#10b981', '#f43f5e'],
            borderWidth: 0
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          cutout: '75%',
          plugins: { legend: { display: false } }
        }
      });

      const ctxL = document.getElementById('latencyChart').getContext('2d');
      latencyChart = new Chart(ctxL, {
        type: 'bar',
        data: {
          labels: [],
          datasets: [
            {
              label: 'TypeSafe Jev (ms)',
              data: [],
              backgroundColor: '#a855f7',
              borderRadius: 6
            },
            {
              label: 'Google Gemini (ms)',
              data: [],
              backgroundColor: '#38bdf8',
              borderRadius: 6
            }
          ]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          scales: {
            x: { grid: { display: false }, ticks: { color: '#64748b', font: { size: 10 } } },
            y: { grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#64748b', font: { size: 10 } } }
          },
          plugins: {
            legend: { labels: { color: '#94a3b8', font: { size: 11 } } }
          }
        }
      });
    }

    async function fetchData() {
      try {
        const resp = await fetch('/api/data');
        if (!resp.ok) return;
        const data = await resp.json();

        updateKPIs(data.stats);
        rawLogs = data.logs || [];
        renderTable(rawLogs);
        updateCharts(data.stats, rawLogs);
        lucide.createIcons();
      } catch (err) {
        console.error('Error fetching dashboard data:', err);
      }
    }

    function updateKPIs(stats) {
      document.getElementById('kpi-savings').textContent = '$' + (stats.total_savings || 0).toFixed(4);
      document.getElementById('kpi-savings-pct').textContent = '+' + (stats.savings_pct || 0).toFixed(1) + '%';
      document.getElementById('kpi-cost-hybrid').textContent = '$' + (stats.total_cost_hybrid || 0).toFixed(4);
      document.getElementById('kpi-cost-without').textContent = '$' + (stats.total_cost_without_jev || 0).toFixed(4);

      document.getElementById('kpi-jev-speed').textContent = Math.round(stats.avg_jev_latency_ms || 0) + ' ms';
      document.getElementById('kpi-speedup').textContent = (stats.speedup_factor || 1).toFixed(1) + 'x plus rapide';
      document.getElementById('kpi-avg-jev').textContent = Math.round(stats.avg_jev_latency_ms || 0) + ' ms';
      document.getElementById('kpi-avg-gemini').textContent = Math.round(stats.avg_gemini_latency_ms || 0) + ' ms';

      document.getElementById('kpi-filter-rate').textContent = (stats.filter_rate_pct || 0).toFixed(1) + '%';
      document.getElementById('kpi-rejected-count').textContent = stats.rejected_count || 0;
      document.getElementById('kpi-qualified-count').textContent = stats.qualified_count || 0;

      document.getElementById('kpi-total-articles').textContent = stats.total_count || 0;
    }

    function updateCharts(stats, logs) {
      if (decisionsChart) {
        decisionsChart.data.datasets[0].data = [stats.qualified_count || 0, stats.rejected_count || 0];
        decisionsChart.update();
      }

      if (latencyChart && logs.length > 0) {
        const sample = logs.slice(0, 10).reverse();
        latencyChart.data.labels = sample.map(l => l.title ? l.title.substring(0, 15) + '...' : 'Art');
        latencyChart.data.datasets[0].data = sample.map(l => l.jev_latency_ms || 0);
        latencyChart.data.datasets[1].data = sample.map(l => l.gemini_latency_ms || 0);
        latencyChart.update();
      }
    }

    function renderTable(logs) {
      const tbody = document.getElementById('logs-tbody');
      const filter = document.getElementById('filter-select').value;
      const filtered = filter === 'all' ? logs : logs.filter(l => l.jev_decision === filter);

      if (filtered.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" class="py-8 text-center text-slate-500">Aucune analyse enregistrée pour le moment.</td></tr>';
        return;
      }

      tbody.innerHTML = filtered.map((l, idx) => {
        const isQual = l.jev_decision === 'QUALIFIED';
        const badge = isQual
          ? '<span class="px-2 py-1 rounded text-[10px] font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 flex items-center gap-1 w-fit"><i data-lucide="check-circle" class="w-3 h-3"></i> QUALIFIÉ GEMINI</span>'
          : '<span class="px-2 py-1 rounded text-[10px] font-bold bg-rose-500/20 text-rose-300 border border-rose-500/30 flex items-center gap-1 w-fit"><i data-lucide="shield-alert" class="w-3 h-3"></i> REJETÉ PAR JEV</span>';

        const pScoop = Math.round((l.jev_p_scoop || 0) * 100);
        const pOp = Math.round((l.jev_p_opinion || 0) * 100);
        const savingsStr = l.savings > 0 ? `<span class="text-emerald-400 font-bold mono">+$${l.savings.toFixed(5)}</span>` : `<span class="text-slate-400 mono">-$${Math.abs(l.savings).toFixed(5)}</span>`;

        return `
          <tr class="hover:bg-slate-800/40 transition-colors">
            <td class="py-3 px-4">${badge}</td>
            <td class="py-3 px-4 max-w-sm">
              <a href="${l.url || '#'}" target="_blank" class="font-semibold text-slate-100 hover:text-purple-300 transition-colors line-clamp-1">${escapeHtml(l.title)}</a>
              <span class="text-[11px] text-slate-400">${escapeHtml(l.source)} • <span class="mono">${(l.created_at || '').split(' ')[1] || ''}</span></span>
            </td>
            <td class="py-3 px-4">
              <div class="flex items-center gap-2 text-[10px] mono">
                <span class="text-purple-400">Scoop: ${pScoop}%</span>
                <span class="text-slate-600">|</span>
                <span class="text-rose-400">Biais: ${pOp}%</span>
              </div>
              <div class="w-24 h-1.5 bg-slate-800 rounded-full mt-1 overflow-hidden flex">
                <div class="bg-purple-500 h-full" style="width: ${pScoop}%"></div>
                <div class="bg-rose-500 h-full" style="width: ${pOp}%"></div>
              </div>
            </td>
            <td class="py-3 px-4 mono">
              <div class="text-purple-300 font-medium">${l.jev_latency_ms || 0} ms <span class="text-[10px] text-slate-500">(Jev)</span></div>
              ${l.gemini_called ? `<div class="text-cyan-400 font-medium">${l.gemini_latency_ms || 0} ms <span class="text-[10px] text-slate-500">(Gemini)</span></div>` : '<div class="text-[10px] text-slate-600">Gemini évité</div>'}
            </td>
            <td class="py-3 px-4">${savingsStr}</td>
            <td class="py-3 px-4 text-right">
              <button onclick="openModal(${idx})" class="p-1.5 rounded-lg hover:bg-slate-800 text-slate-400 hover:text-slate-200 transition-colors">
                <i data-lucide="eye" class="w-4 h-4"></i>
              </button>
            </td>
          </tr>
        `;
      }).join('');
    }

    function applyFilter() {
      renderTable(rawLogs);
      lucide.createIcons();
    }

    function openModal(index) {
      const filter = document.getElementById('filter-select').value;
      const filtered = filter === 'all' ? rawLogs : rawLogs.filter(l => l.jev_decision === filter);
      const log = filtered[index];
      if (!log) return;

      const isQual = log.jev_decision === 'QUALIFIED';
      const badge = document.getElementById('modal-badge');
      badge.textContent = isQual ? 'Qualifié Étage 2 (Gemini)' : 'Rejeté Étage 1 (Jev)';
      badge.className = isQual
        ? 'px-2 py-0.5 rounded text-[10px] font-bold uppercase bg-emerald-500/20 text-emerald-300 border border-emerald-500/30'
        : 'px-2 py-0.5 rounded text-[10px] font-bold uppercase bg-rose-500/20 text-rose-300 border border-rose-500/30';

      document.getElementById('modal-title').textContent = log.title;
      document.getElementById('modal-source').textContent = (log.source || '') + ' • ' + (log.created_at || '');
      document.getElementById('modal-p-scoop').textContent = Math.round((log.jev_p_scoop || 0) * 100) + ' %';
      document.getElementById('modal-p-opinion').textContent = Math.round((log.jev_p_opinion || 0) * 100) + ' %';
      document.getElementById('modal-reason').textContent = log.jev_reason || 'Aucun motif renseigné';

      const tweetCont = document.getElementById('modal-tweet-container');
      if (log.gemini_called && log.gemini_tweet) {
        tweetCont.classList.remove('hidden');
        document.getElementById('modal-tweet').textContent = log.gemini_tweet;
      } else {
        tweetCont.classList.add('hidden');
      }

      document.getElementById('modal').classList.remove('hidden');
      document.getElementById('modal').classList.add('flex');
      lucide.createIcons();
    }

    function closeModal() {
      document.getElementById('modal').classList.add('hidden');
      document.getElementById('modal').classList.remove('flex');
    }

    function escapeHtml(str) {
      if (!str) return '';
      return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
    }

    window.addEventListener('DOMContentLoaded', () => {
      initCharts();
      fetchData();
      setInterval(fetchData, 3000);
    });
  </script>
</body>
</html>
"""

class DashboardHandler(BaseHTTPRequestHandler):
    storage: Optional[Storage] = None

    def log_message(self, format, *args):
        # Silence standard HTTP access logging to keep console clean
        return

    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(DASHBOARD_HTML.encode("utf-8"))

        elif self.path == "/api/data" or self.path == "/api/stats":
            if not self.storage:
                self.send_response(500)
                self.end_headers()
                return

            stats = self.storage.get_hybrid_stats()
            logs = self.storage.get_hybrid_logs(limit=50)

            data = {
                "stats": stats,
                "logs": logs
            }

            resp = json.dumps(data).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(resp)

        else:
            self.send_response(404)
            self.end_headers()

def start_dashboard_server(storage: Storage, host: str = "0.0.0.0", port: int = 8080) -> ThreadingHTTPServer:
    """
    Démarre le serveur web de télémétrie en tâche de fond (thread daemon).
    """
    class CustomHandler(DashboardHandler):
        pass

    CustomHandler.storage = storage

    server = ThreadingHTTPServer((host, port), CustomHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    logger.info(f"🌐 Dashboard de télémétrie hybride démarré sur http://{host}:{port}")
    return server

if __name__ == "__main__":
    import time
    from config import DATABASE_PATH
    logging.basicConfig(level=logging.INFO)
    s = Storage(DATABASE_PATH)
    srv = start_dashboard_server(s, port=8080)
    print("Dashboard listening on http://0.0.0.0:8080. Press Ctrl+C to stop.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        srv.shutdown()
