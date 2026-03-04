/* =========================================================
   subhāṣita Explorer — app.js
   ========================================================= */

/* ── Apply all saved preferences immediately (before DOMContentLoaded) ── */
(function () {
  var dark   = localStorage.getItem('subhashita-dark')     === '1';
  var hc     = localStorage.getItem('subhashita-hc')       === '1';
  var motion = localStorage.getItem('subhashita-motion')   === '1';
  var fs     = localStorage.getItem('subhashita-fontsize') || 'normal';
  var script = localStorage.getItem('subhashita-script')   || 'deva';

  if (dark)   document.body.classList.add('dark-mode');
  if (hc)     document.body.classList.add('high-contrast');
  if (motion) document.body.classList.add('reduce-motion');
  document.body.classList.add('fs-' + fs);
  if (script === 'iast') document.body.classList.add('iast-mode');
})();


/* ── Sync UI controls after DOM is ready ──────────────────── */
document.addEventListener('DOMContentLoaded', function () {
  var dark   = localStorage.getItem('subhashita-dark')     === '1';
  var hc     = localStorage.getItem('subhashita-hc')       === '1';
  var motion = localStorage.getItem('subhashita-motion')   === '1';
  var fs     = localStorage.getItem('subhashita-fontsize') || 'normal';
  var script = localStorage.getItem('subhashita-script')   || 'deva';

  // Sync toggle switches
  var dmEl = document.getElementById('dark-mode-toggle');
  if (dmEl) dmEl.checked = dark;
  var ctEl = document.getElementById('contrast-toggle');
  if (ctEl) ctEl.checked = hc;
  var mtEl = document.getElementById('motion-toggle');
  if (mtEl) mtEl.checked = motion;

  // Sync script toggle button labels
  _syncScriptBtns(script);

  // Font size buttons
  document.querySelectorAll('.fs-btn').forEach(function (btn) {
    btn.classList.toggle('active', btn.dataset.size === fs);
    btn.addEventListener('click', function () { setFontSize(btn.dataset.size); });
  });
  _updateFsLabel(fs);

  // Script buttons in a11y panel
  document.querySelectorAll('.script-btn').forEach(function (btn) {
    btn.classList.toggle('active', btn.dataset.script === script);
    btn.addEventListener('click', function () { setScript(btn.dataset.script); });
  });

  // Check favorites for current verse if on a verse page
  var favBtns = document.querySelectorAll('[id^="fav-btn-"]');
  favBtns.forEach(function (btn) {
    var id = parseInt(btn.id.replace('fav-btn-', ''));
    if (id) _updateFavBtn(id);
  });
});


/* ── Script toggle ─────────────────────────────────────────── */
function toggleScript() {
  var isIast = document.body.classList.toggle('iast-mode');
  var s = isIast ? 'iast' : 'deva';
  localStorage.setItem('subhashita-script', s);
  _syncScriptBtns(s);
}

function setScript(script) {
  var isIast = script === 'iast';
  document.body.classList.toggle('iast-mode', isIast);
  localStorage.setItem('subhashita-script', script);
  _syncScriptBtns(script);
}

function _syncScriptBtns(script) {
  var label = script === 'iast' ? '\u0926\u0947\u0935' : 'IAST'; // देव : IAST
  document.querySelectorAll('.script-toggle-btn').forEach(function (btn) {
    btn.textContent = label;
  });
  document.querySelectorAll('.script-btn').forEach(function (btn) {
    btn.classList.toggle('active', btn.dataset.script === script);
  });
}


/* ── Dark mode ─────────────────────────────────────────────── */
function toggleDarkMode(on) {
  document.body.classList.toggle('dark-mode', on);
  localStorage.setItem('subhashita-dark', on ? '1' : '0');
}


/* ── High contrast ─────────────────────────────────────────── */
function toggleHighContrast(on) {
  document.body.classList.toggle('high-contrast', on);
  localStorage.setItem('subhashita-hc', on ? '1' : '0');
}


/* ── Reduce motion ─────────────────────────────────────────── */
function toggleReduceMotion(on) {
  document.body.classList.toggle('reduce-motion', on);
  localStorage.setItem('subhashita-motion', on ? '1' : '0');
}


/* ── Font size ─────────────────────────────────────────────── */
var _fontSizes = ['small', 'normal', 'large', 'xlarge'];
var _fsSizeLabels = { small: 'Small', normal: 'Normal', large: 'Large', xlarge: 'Extra Large' };

function setFontSize(size) {
  _fontSizes.forEach(function (s) { document.body.classList.remove('fs-' + s); });
  document.body.classList.add('fs-' + size);
  localStorage.setItem('subhashita-fontsize', size);
  document.querySelectorAll('.fs-btn').forEach(function (btn) {
    btn.classList.toggle('active', btn.dataset.size === size);
  });
  _updateFsLabel(size);
}

function _updateFsLabel(size) {
  var el = document.getElementById('fs-label-text');
  if (el) el.textContent = _fsSizeLabels[size] || 'Normal';
}


/* ── Toast notification ────────────────────────────────────── */
function showToast(msg, type) {
  type = type || 'success';
  var toastEl = document.getElementById('copy-toast');
  if (!toastEl) return;
  var body = toastEl.querySelector('.toast-body');
  if (body) body.textContent = msg;
  toastEl.className = 'toast align-items-center text-bg-' + type + ' border-0';
  var toast = new bootstrap.Toast(toastEl, { delay: 2500 });
  toast.show();
}


/* ── Copy to clipboard ──────────────────────────────────────── */
function copyVerseText(text) {
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(text).then(function () {
      showToast('Copied to clipboard!');
    }).catch(function () { _fallbackCopy(text); });
  } else {
    _fallbackCopy(text);
  }
}

function _fallbackCopy(text) {
  var tmp = document.createElement('textarea');
  tmp.value = text;
  tmp.style.cssText = 'position:fixed;opacity:0';
  document.body.appendChild(tmp);
  tmp.focus();
  tmp.select();
  try { document.execCommand('copy'); showToast('Copied!'); }
  catch (e) { showToast('Copy failed — please copy manually.', 'danger'); }
  document.body.removeChild(tmp);
}


/* ── Share verse ────────────────────────────────────────────── */
function shareVerse(title, text, url) {
  if (navigator.share) {
    navigator.share({ title: title, text: text, url: url })
      .catch(function (e) {
        // User cancelled or error — silently ignore
        if (e.name !== 'AbortError') {
          navigator.clipboard.writeText(url).then(function () {
            showToast('Link copied!');
          });
        }
      });
  } else {
    // Fallback: copy URL
    navigator.clipboard.writeText(url).then(function () {
      showToast('Link copied to clipboard!');
    }).catch(function () {
      showToast('Share: ' + url);
    });
  }
}


/* ── Favorites (localStorage) ───────────────────────────────── */
function getFavorites() {
  try {
    return JSON.parse(localStorage.getItem('subhashita-favs') || '[]');
  } catch (e) {
    return [];
  }
}

function saveFavorites(favs) {
  localStorage.setItem('subhashita-favs', JSON.stringify(favs));
}

function toggleFavorite(verseId) {
  var favs = getFavorites();
  var idx = favs.indexOf(verseId);
  if (idx === -1) {
    favs.push(verseId);
    showToast('Bookmarked!');
  } else {
    favs.splice(idx, 1);
    showToast('Removed from bookmarks.');
  }
  saveFavorites(favs);
  _updateFavBtn(verseId);
}

function _updateFavBtn(verseId) {
  var favs = getFavorites();
  var isFaved = favs.indexOf(verseId) !== -1;

  // Update all fav icons for this verse (main + mobile bar)
  ['fav-icon-' + verseId, 'fav-icon-mobile-' + verseId].forEach(function (iconId) {
    var icon = document.getElementById(iconId);
    if (!icon) return;
    icon.className = isFaved ? 'bi bi-bookmark-fill' : 'bi bi-bookmark';
    var btn = icon.parentElement;
    if (btn) {
      btn.classList.toggle('btn-warning', isFaved);
      btn.classList.toggle('btn-outline-warning', !isFaved);
    }
  });
}

// Legacy alias used in older templates
function checkFavorite(verseId) { _updateFavBtn(verseId); }
function updateFavIcon(verseId) { _updateFavBtn(verseId); }


/* ── Random verse (AJAX refresh) ────────────────────────────── */
function loadRandomVerse(containerId) {
  fetch('/api/random')
    .then(function (r) { return r.json(); })
    .then(function (data) {
      var el = document.getElementById(containerId);
      if (!el) return;
      var devaEl = el.querySelector('.verse-text-deva');
      var iastEl = el.querySelector('.verse-text-iast');
      if (devaEl) devaEl.textContent = data.deva;
      if (iastEl) iastEl.textContent = data.iast;
      var attrEl = el.querySelector('.attribution-text');
      if (attrEl) attrEl.textContent = data.attribution || '';
      var linkEl = el.querySelector('.verse-detail-link');
      if (linkEl) linkEl.href = data.url;
    })
    .catch(console.error);
}


/* ── Keyboard shortcuts ─────────────────────────────────────── */
document.addEventListener('keydown', function (e) {
  var tag = document.activeElement ? document.activeElement.tagName : '';
  var inInput = tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT';

  if (inInput) {
    if (e.key === 'Escape') document.activeElement.blur();
    return;
  }

  // Don't fire when modifiers are held (except Shift for T/F/J/K)
  if (e.ctrlKey || e.metaKey || e.altKey) return;

  switch (e.key) {
    case 't': case 'T':
      toggleScript();
      break;

    case '/':
      e.preventDefault();
      var searchEl = document.querySelector('input[name="q"]');
      if (searchEl) { searchEl.focus(); searchEl.select(); }
      break;

    case 'f': case 'F': {
      var favBtn = document.querySelector('[id^="fav-btn-"]');
      if (favBtn) {
        var vid = parseInt(favBtn.id.replace('fav-btn-', ''));
        if (vid) toggleFavorite(vid);
      }
      break;
    }

    case 'j': case 'J': {
      var nextBtn = document.querySelector('.next-verse-btn');
      if (nextBtn) nextBtn.click();
      break;
    }

    case 'k': case 'K': {
      var prevBtn = document.querySelector('.prev-verse-btn');
      if (prevBtn) prevBtn.click();
      break;
    }
  }
});
