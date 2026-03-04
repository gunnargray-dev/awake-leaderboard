/* app.js — Awake Leaderboard */
(function () {
  'use strict';

  // ===== STATE =====
  let allProjects = [];
  let filteredProjects = [];
  let currentSort = { key: 'rank', dir: 'asc' };
  let currentCategory = null;
  let currentSearch = '';

  // ===== DOM REFS =====
  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => document.querySelectorAll(sel);

  const tableBody = $('#tableBody');
  const searchInput = $('#searchInput');
  const categoryList = $('#categoryList');
  const categorySidebar = $('#categorySidebar');
  const categoryPills = $('#categoryPills');
  const resultCount = $('#resultCount');
  const emptyState = $('#emptyState');
  const tableScroll = $('.table-scroll');
  const resetFiltersBtn = $('#resetFilters');
  const modalOverlay = $('#modalOverlay');
  const modalClose = $('#modalClose');

  // ===== THEME TOGGLE =====
  (function initTheme() {
    const toggle = $('[data-theme-toggle]');
    const root = document.documentElement;
    let theme = 'dark'; // default dark
    root.setAttribute('data-theme', theme);

    if (toggle) {
      toggle.addEventListener('click', () => {
        theme = theme === 'dark' ? 'light' : 'dark';
        root.setAttribute('data-theme', theme);
        toggle.setAttribute('aria-label', `Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`);
        toggle.innerHTML = theme === 'dark'
          ? '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="5"/><path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/></svg>'
          : '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>';
      });
    }
  })();

  // ===== HELPERS =====
  function getGradeClass(grade) {
    const g = grade.charAt(0).toUpperCase();
    if (g === 'A') return 'grade-a';
    if (g === 'B') return 'grade-b';
    if (g === 'C') return 'grade-c';
    if (g === 'D') return 'grade-d';
    return 'grade-f';
  }

  function getBarColor(score) {
    if (score >= 90) return 'var(--color-grade-a)';
    if (score >= 80) return 'var(--color-grade-b)';
    if (score >= 70) return 'var(--color-grade-c)';
    if (score >= 60) return 'var(--color-grade-d)';
    return 'var(--color-grade-f)';
  }

  function formatStars(n) {
    if (n >= 1000) return (n / 1000).toFixed(n >= 10000 ? 0 : 1) + 'k';
    return n.toString();
  }

  function formatNumber(n) {
    return n.toLocaleString();
  }

  function getGradeExplanation(grade, score) {
    const explanations = {
      'A+': `An A+ grade (score ${score}) indicates an exceptional project with excellent health, low complexity, strong security, minimal dead code, and comprehensive test coverage.`,
      'A': `An A grade (score ${score}) indicates a very well-maintained project with strong fundamentals across all dimensions. Minor areas for improvement may exist.`,
      'B+': `A B+ grade (score ${score}) indicates a healthy project with good practices. Some dimensions could benefit from additional attention.`,
      'B': `A B grade (score ${score}) indicates a solid project with room for improvement in certain areas such as test coverage or code complexity.`,
      'C+': `A C+ grade (score ${score}) indicates a project with notable areas for improvement. The project is functional but would benefit from refactoring or better testing.`,
      'C': `A C grade (score ${score}) indicates significant room for improvement across multiple dimensions. Consider prioritizing security and test coverage.`,
      'D': `A D grade (score ${score}) indicates a project that needs substantial attention. Multiple dimensions fall below recommended thresholds.`,
      'F': `An F grade (score ${score}) indicates critical issues across most dimensions. Immediate action recommended for security and maintainability.`
    };
    return explanations[grade] || `Score: ${score}/100. This project has been analyzed across five key dimensions.`;
  }

  // ===== ANIMATE COUNTER =====
  function animateCounter(el, target, duration) {
    if (!el || isNaN(target)) return;
    duration = duration || 800;
    const start = 0;
    const isDecimal = target !== Math.round(target);
    let startTime = null;
    el._animating = true;

    function update(currentTime) {
      if (!el._animating) return;
      if (!startTime) startTime = currentTime;
      const elapsed = currentTime - startTime;
      const progress = Math.min(elapsed / duration, 1);
      const eased = 1 - Math.pow(1 - progress, 3);
      const current = start + (target - start) * eased;
      el.textContent = isDecimal ? current.toFixed(1) : Math.round(current);
      if (progress < 1) {
        requestAnimationFrame(update);
      } else {
        el.textContent = isDecimal ? target.toFixed(1) : Math.round(target);
        el._animating = false;
      }
    }
    requestAnimationFrame(update);
  }

  // ===== DATA LOADING =====
  async function loadData() {
    try {
      const resp = await fetch('./data/leaderboard.json');
      if (!resp.ok) throw new Error('HTTP ' + resp.status);
      const data = await resp.json();
      allProjects = data.projects;
      filteredProjects = [...allProjects];
    } catch (err) {
      console.error('Failed to load leaderboard data:', err);
      if (tableBody) tableBody.innerHTML = '<tr><td colspan="6" style="text-align:center;padding:32px;color:var(--color-text-muted);">Failed to load data.</td></tr>';
      return;
    }
    try {
      init();
    } catch (err2) {
      console.error('Failed to initialize:', err2);
    }
  }

  // ===== INIT =====
  function init() {
    buildCategories();
    renderTable();
    renderStats();
    animateHeroStats();
    bindEvents();
  }

  // ===== CATEGORIES =====
  function buildCategories() {
    const cats = {};
    allProjects.forEach(p => {
      cats[p.category] = (cats[p.category] || 0) + 1;
    });
    const sorted = Object.entries(cats).sort((a, b) => b[1] - a[1]);

    // Sidebar
    categoryList.innerHTML = `
      <li class="category-item active" data-category="">
        <span class="cat-name">All</span>
        <span class="cat-count">${allProjects.length}</span>
      </li>
      ${sorted.map(([cat, count]) => `
        <li class="category-item" data-category="${cat}">
          <span class="cat-name">${cat}</span>
          <span class="cat-count">${count}</span>
        </li>
      `).join('')}
    `;

    // Mobile pills
    categoryPills.innerHTML = `
      <button class="category-pill active" data-category="" role="tab" aria-selected="true">All</button>
      ${sorted.map(([cat, count]) => `
        <button class="category-pill" data-category="${cat}" role="tab" aria-selected="false">${cat} (${count})</button>
      `).join('')}
    `;
  }

  // ===== RENDER TABLE =====
  function renderTable() {
    const html = filteredProjects.map((p, i) => `
      <tr data-index="${allProjects.indexOf(p)}">
        <td class="cell-rank">${p.rank}</td>
        <td>
          <div class="cell-project">
            <span class="cell-project-name">${p.name}</span>
            <span class="cell-project-owner">${p.owner}</span>
          </div>
        </td>
        <td class="cell-score">${p.score.toFixed(1)}</td>
        <td style="text-align:center"><span class="grade-badge ${getGradeClass(p.grade)}">${p.grade}</span></td>
        <td class="cell-stars">${formatStars(p.stars)} \u2605</td>
        <td class="cell-category hide-mobile">${p.category}</td>
      </tr>
    `).join('');

    tableBody.innerHTML = html;

    // Update count
    resultCount.textContent = `${filteredProjects.length} project${filteredProjects.length !== 1 ? 's' : ''}`;

    // Show/hide empty state
    if (filteredProjects.length === 0) {
      emptyState.style.display = 'flex';
      tableScroll.style.display = 'none';
    } else {
      emptyState.style.display = 'none';
      tableScroll.style.display = 'block';
    }

    // Show/hide clear filter
    resetFiltersBtn.style.display = (currentCategory || currentSearch) ? 'inline-block' : 'none';
  }

  // ===== SORTING =====
  function sortProjects(key, dir) {
    filteredProjects.sort((a, b) => {
      let va = a[key];
      let vb = b[key];
      if (typeof va === 'string') va = va.toLowerCase();
      if (typeof vb === 'string') vb = vb.toLowerCase();
      if (dir === 'asc') return va < vb ? -1 : va > vb ? 1 : 0;
      return va > vb ? -1 : va < vb ? 1 : 0;
    });
  }

  function handleSort(key) {
    if (currentSort.key === key) {
      currentSort.dir = currentSort.dir === 'asc' ? 'desc' : 'asc';
    } else {
      currentSort.key = key;
      currentSort.dir = key === 'score' || key === 'stars' ? 'desc' : 'asc';
    }
    applyFilters();
    updateSortUI();
  }

  function updateSortUI() {
    $$('.sort-btn').forEach(btn => {
      const th = btn.closest('th');
      const key = th?.dataset.sort;
      const arrow = btn.querySelector('.sort-arrow');
      if (key === currentSort.key) {
        btn.classList.add('active');
        arrow.textContent = currentSort.dir === 'asc' ? '\u2191' : '\u2193';
      } else {
        btn.classList.remove('active');
        arrow.textContent = '';
      }
    });
  }

  // ===== FILTERING =====
  function applyFilters() {
    filteredProjects = allProjects.filter(p => {
      const matchCategory = !currentCategory || p.category === currentCategory;
      const matchSearch = !currentSearch ||
        p.name.toLowerCase().includes(currentSearch) ||
        p.owner.toLowerCase().includes(currentSearch) ||
        p.description.toLowerCase().includes(currentSearch);
      return matchCategory && matchSearch;
    });
    sortProjects(currentSort.key, currentSort.dir);
    renderTable();
  }

  function setCategory(cat) {
    currentCategory = cat || null;
    // Update sidebar
    $$('.category-item').forEach(el => {
      el.classList.toggle('active', el.dataset.category === (cat || ''));
    });
    // Update pills
    $$('.category-pill').forEach(el => {
      const isActive = el.dataset.category === (cat || '');
      el.classList.toggle('active', isActive);
      el.setAttribute('aria-selected', isActive);
    });
    applyFilters();
  }

  window.resetAll = function () {
    currentCategory = null;
    currentSearch = '';
    searchInput.value = '';
    currentSort = { key: 'rank', dir: 'asc' };
    setCategory('');
    updateSortUI();
  };

  // ===== MODAL =====
  function openModal(projectIndex) {
    const p = allProjects[projectIndex];
    if (!p) return;

    $('#modalTitle').textContent = `${p.owner}/${p.name}`;
    const gradeEl = $('#modalGrade');
    gradeEl.textContent = p.grade;
    gradeEl.className = 'modal-grade grade-badge ' + getGradeClass(p.grade);

    $('#modalDesc').textContent = p.description;

    const dateStr = new Date(p.last_analyzed).toLocaleDateString('en-US', {
      year: 'numeric', month: 'short', day: 'numeric'
    });

    $('#modalMeta').innerHTML = `
      <div class="modal-meta-item">
        <span class="modal-meta-value">${formatNumber(p.stars)}</span>
        <span class="modal-meta-label">Stars</span>
      </div>
      <div class="modal-meta-item">
        <span class="modal-meta-value">${formatNumber(p.forks)}</span>
        <span class="modal-meta-label">Forks</span>
      </div>
      <div class="modal-meta-item">
        <span class="modal-meta-value">${p.language}</span>
        <span class="modal-meta-label">Language</span>
      </div>
      <div class="modal-meta-item">
        <span class="modal-meta-value">${p.category}</span>
        <span class="modal-meta-label">Category</span>
      </div>
      <div class="modal-meta-item">
        <span class="modal-meta-value">${dateStr}</span>
        <span class="modal-meta-label">Analyzed</span>
      </div>
    `;

    $('#modalScoreMain').innerHTML = `
      <span class="modal-score-number">${p.score.toFixed(1)}</span>
      <span class="modal-score-max">/ 100</span>
    `;

    const dims = [
      { key: 'health', label: 'Health', weight: '30%' },
      { key: 'complexity', label: 'Complexity', weight: '20%' },
      { key: 'security', label: 'Security', weight: '25%' },
      { key: 'dead_code', label: 'Dead Code', weight: '10%' },
      { key: 'coverage', label: 'Coverage', weight: '15%' }
    ];

    $('#modalBars').innerHTML = dims.map(d => `
      <div class="modal-bar-row">
        <div>
          <span class="modal-bar-label">${d.label}</span>
          <span class="modal-bar-weight">${d.weight}</span>
        </div>
        <div class="modal-bar-track">
          <div class="modal-bar-fill" style="width:0%;background:${getBarColor(p.dimensions[d.key])}"></div>
        </div>
        <span class="modal-bar-value">${p.dimensions[d.key]}</span>
      </div>
    `).join('');

    $('#modalGradeExplain').textContent = getGradeExplanation(p.grade, p.score);
    $('#modalGithub').href = `https://github.com/${p.owner}/${p.name}`;

    // Show modal
    modalOverlay.style.display = 'flex';
    requestAnimationFrame(() => {
      modalOverlay.classList.add('visible');
      // Animate bars
      $$('.modal-bar-fill').forEach((bar, i) => {
        const key = dims[i].key;
        setTimeout(() => {
          bar.style.width = p.dimensions[key] + '%';
        }, 50 + i * 60);
      });
    });
    document.body.style.overflow = 'hidden';
  }

  function closeModal() {
    modalOverlay.classList.remove('visible');
    setTimeout(() => {
      modalOverlay.style.display = 'none';
    }, 220);
    document.body.style.overflow = '';
  }

  // ===== STATS =====
  function renderStats() {
    const scores = allProjects.map(p => p.score).sort((a, b) => a - b);
    const avg = scores.reduce((a, b) => a + b, 0) / scores.length;
    const median = scores.length % 2 === 0
      ? (scores[scores.length / 2 - 1] + scores[scores.length / 2]) / 2
      : scores[Math.floor(scores.length / 2)];
    const highest = scores[scores.length - 1];

    $('#statTotal').textContent = allProjects.length;
    $('#statAvg').textContent = avg.toFixed(1);
    $('#statHighest').textContent = highest.toFixed(1);
    $('#statMedian').textContent = median.toFixed(1);

    // Grade distribution
    const gradeCounts = { 'A+': 0, 'A': 0, 'B+': 0, 'B': 0, 'C+': 0, 'C': 0, 'D': 0, 'F': 0 };
    allProjects.forEach(p => { gradeCounts[p.grade] = (gradeCounts[p.grade] || 0) + 1; });
    const maxGrade = Math.max(...Object.values(gradeCounts));

    const gradeChart = $('#gradeChart');
    gradeChart.innerHTML = Object.entries(gradeCounts).map(([grade, count]) => {
      const pct = maxGrade > 0 ? (count / maxGrade * 100) : 0;
      const cls = getGradeClass(grade);
      return `
        <div class="grade-bar-row">
          <span class="grade-bar-label ${cls}" style="color:var(--color-${cls});">${grade}</span>
          <div class="grade-bar-track">
            <div class="grade-bar-fill" style="width:${pct}%;background:var(--color-${cls});opacity:0.35;"></div>
          </div>
          <span class="grade-bar-count">${count}</span>
        </div>
      `;
    }).join('');

    // Category chart
    const cats = {};
    allProjects.forEach(p => { cats[p.category] = (cats[p.category] || 0) + 1; });
    const sortedCats = Object.entries(cats).sort((a, b) => b[1] - a[1]);
    const maxCat = sortedCats[0]?.[1] || 1;

    const catChart = $('#categoryChart');
    catChart.innerHTML = sortedCats.map(([cat, count]) => {
      const pct = (count / maxCat * 100);
      return `
        <div class="cat-bar-row">
          <span class="cat-bar-label">${cat}</span>
          <div class="cat-bar-track"><div class="cat-bar-fill" style="width:${pct}%"></div></div>
          <span class="cat-bar-count">${count}</span>
        </div>
      `;
    }).join('');
  }

  // ===== HERO STATS ANIMATION =====
  function animateHeroStats() {
    const heroStatsEl = $('#heroStats');
    if (!heroStatsEl) return;

    const scores = allProjects.map(p => p.score);
    const avg = scores.reduce((a, b) => a + b, 0) / scores.length;
    const aCount = allProjects.filter(p => p.grade.startsWith('A')).length;

    // Update data attributes with real values
    const statEls = $$('.hero-stat-value');
    if (statEls[0]) statEls[0].dataset.count = '50';
    if (statEls[1]) statEls[1].dataset.count = avg.toFixed(1);
    if (statEls[2]) statEls[2].dataset.count = String(aCount);

    let animated = false;
    function triggerOnce() {
      if (animated) return;
      animated = true;
      statEls.forEach(el => {
        const target = parseFloat(el.dataset.count);
        if (!isNaN(target)) animateCounter(el, target);
      });
    }

    // Trigger immediately — hero is always above fold
    setTimeout(triggerOnce, 300);
  }

  // ===== EVENT BINDINGS =====
  function bindEvents() {
    // Search
    let searchTimeout;
    searchInput.addEventListener('input', () => {
      clearTimeout(searchTimeout);
      searchTimeout = setTimeout(() => {
        currentSearch = searchInput.value.trim().toLowerCase();
        applyFilters();
      }, 150);
    });

    // Sort
    $$('th[data-sort]').forEach(th => {
      th.addEventListener('click', () => handleSort(th.dataset.sort));
    });

    // Category sidebar
    categoryList.addEventListener('click', (e) => {
      const item = e.target.closest('.category-item');
      if (item) setCategory(item.dataset.category);
    });

    // Category pills
    categoryPills.addEventListener('click', (e) => {
      const pill = e.target.closest('.category-pill');
      if (pill) setCategory(pill.dataset.category);
    });

    // Reset filters
    resetFiltersBtn.addEventListener('click', window.resetAll);

    // Table row click -> modal
    tableBody.addEventListener('click', (e) => {
      const row = e.target.closest('tr');
      if (row) openModal(parseInt(row.dataset.index));
    });

    // Modal close
    modalClose.addEventListener('click', closeModal);
    modalOverlay.addEventListener('click', (e) => {
      if (e.target === modalOverlay) closeModal();
    });
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && modalOverlay.style.display !== 'none') closeModal();
    });
  }

  // ===== BOOT =====
  loadData();
})();
