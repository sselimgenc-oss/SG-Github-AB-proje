/* panel.js
 * KOPYA/UYARLAMA kaynagi: /home/user/sselimgenc-oss/1l3a-proje/motor/canli/pano.py, JS dizgisi (satir 329-380; 1L3A kullanicinin kendi projesi,
 * 2026-11-16): tema dugmesi (K tema anahtari), tablo siralama (th tiklama, data-v), yenile/yazdir dugmesi.
 * Bu depoya ozgu: fetch ile kismi yenileme, sekmeler, tum cizimler. Her metin textContent ile basilir; innerHTML yok.
 * Canli kipte bayatlik sunucudan gelir (§5); anlik goruntu kipinde ek olarak uretim damgasindan istemci tarafinda hesaplanir (§13). Dis URL yok.
 */
(function () {
  'use strict';
  var TOP_MS = 10000, TAB_MS = 30000;                       // spec §10.8: ust serit 10 sn, gerisi 30 sn
  var TABS = [['ozet', 'ÖZET'], ['pozisyonlar', 'POZİSYONLAR'], ['islemler', 'İŞLEMLER'], ['butce', 'BÜTÇE'],
              ['ders', 'DERS'], ['saglik', 'SAĞLIK']];
  var BOT_AD = {learner: 'öğrenen', twin: 'ikiz'};
  var S = {bot: 'learner', tab: 'ozet', status: null, conn: true, gen: null, day: null, trades: null};
  var $ = function (i) { return document.getElementById(i); };

  /* ---------- DOM yardimcilari (yalniz textContent) ---------- */
  function el(tag, cls, txt) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (txt !== undefined && txt !== null) e.textContent = String(txt);
    return e;
  }
  function add(p) {
    for (var i = 1; i < arguments.length; i++) { if (arguments[i]) p.appendChild(arguments[i]); }
    return p;
  }
  function clear(p) { while (p.firstChild) p.removeChild(p.firstChild); return p; }
  var NS = 'http' + '://www.w3.org/2000/svg';            // SVG ad alani kimligi: ag istegi degil
  function sv(tag, attrs) {
    var e = document.createElementNS(NS, tag);
    for (var k in attrs) e.setAttribute(k, attrs[k]);
    return e;
  }

  /* ---------- bicim ---------- */
  function num(x) { return typeof x === 'number' && isFinite(x); }
  function f2(x, d) { return num(x) ? x.toFixed(d === undefined ? 2 : d) : '—'; }
  function sgn(x, d) { return num(x) ? (x > 0 ? '+' : '') + x.toFixed(d === undefined ? 2 : d) : '—'; }
  function usd(x, s) { return num(x) ? (s ? sgn(x) : f2(x)) + ' $' : '—'; }
  function pct(x, d, s) { return num(x) ? (s && x > 0 ? '+' : '') + (x * 100).toFixed(d === undefined ? 2 : d) + ' %' : '—'; }
  function cls(x) { return !num(x) || x === 0 ? '' : (x > 0 ? 'iyi' : 'kotu'); }
  function kzTxt(p) {                                         // "+7.61 (+2.96%)"; unrealized_pct zaten yuzde
    return num(p.unrealized_pnl_usd) ? sgn(p.unrealized_pnl_usd) + (num(p.unrealized_pct) ? ' (' + sgn(p.unrealized_pct) + '%)' : '') : '—';
  }
  function tsi(iso) {                                         // UTC ...Z -> TSİ (sabit UTC+3), yalniz bicim
    var t = Date.parse(iso);
    return isFinite(t) ? new Date(t + 3 * 3600000).toISOString().replace('T', ' ').slice(0, 16) : '—';
  }
  function tsiDay(iso) { var t = Date.parse(iso); return isFinite(t) ? new Date(t + 3 * 3600000).toISOString().slice(0, 10) : null; }
  function ago(s) {
    if (!num(s)) return '—';
    if (s < 90) return Math.round(s) + ' sn';
    if (s < 5400) return Math.round(s / 60) + ' dk';
    return (s / 3600).toFixed(1) + ' sa';
  }
  function bytes(b) { return num(b) ? (b / 1048576 >= 1024 ? (b / 1073741824).toFixed(2) + ' GiB' : Math.round(b / 1048576) + ' MiB') : '—'; }

  /* ---------- ag ---------- */
  var SNAP = window.__SNAPSHOT__ || null;                      // anlik goruntu kipi: veri gomulu, ag yok
  var SNAP_STALE_S = 600;                                      // gorunumun kendisi 10 dk'dan eskiyse bayat
  function snapBanner() {
    var b = $('snap-bant');
    if (!SNAP || !b) return;
    var age = (Date.now() - Date.parse(SNAP.generated_at)) / 1000;
    if (!isFinite(age) || age > SNAP_STALE_S) {
      b.textContent = 'BAYAT GÖRÜNÜM: bu sayfa ' + (isFinite(age) ? ago(age) : 'bilinmeyen süre') + ' önce üretildi (yayın durmuş olabilir); Yenile ile tekrar yükleyin.';
      b.style.display = '';
    } else { b.style.display = 'none'; }
  }
  function get(path) {
    if (SNAP) {
      var v = SNAP.data[path];
      S.conn = true;
      return Promise.resolve(v === undefined ? {ok: false, code: 'anlik_goruntude_yok'} : v);
    }
    return fetch(path, {cache: 'no-store'}).then(function (r) { return r.json(); }).then(function (j) { S.conn = true; return j; },
      function () { S.conn = false; return {ok: false, code: 'baglanti'}; });
  }
  function nodata(code) {
    var d = el('div', 'yok');
    add(d, el('b', '', 'Veri yok'), document.createTextNode(' — okunamadı: ' + (code || 'bilinmiyor')));
    return d;
  }
  function panel(title, right, extra) {
    var p = el('div', 'p' + (extra ? ' ' + extra : ''));
    var pb = el('div', 'pb', title);
    add(pb, el('span', '', right || ''));
    var pi = el('div', 'pi');
    add(p, pb, pi);
    p._body = pi; p._right = pb.lastChild;
    return p;
  }
  function box(label, val, vcls) {
    var k = el('div', 'kart');
    var d = el('div', 'd' + (vcls ? ' ' + vcls : ''), val);
    return add(k, el('div', 'e', label), d);
  }
  function row(label, val, vcls) {
    var r = el('div', 'sat');
    return add(r, el('span', '', label), el('b', vcls || '', val));
  }
  function table(head, rows, opts) {                            // rows: [[text | {t, v, c}]]
    var w = el('div', 'tw'), t = el('table', 'sirala'), th = el('thead'), hr = el('tr'), tb = el('tbody');
    head.forEach(function (h, i) {
      var c = el('th', opts && opts.right && opts.right.indexOf(i) >= 0 ? 'sg' : '', h);
      hr.appendChild(c);
    });
    th.appendChild(hr);
    rows.forEach(function (r) {
      var tr = el('tr');
      r.forEach(function (c, i) {
        var o = (c !== null && typeof c === 'object') ? c : {t: c};
        var td = el('td', (opts && opts.right && opts.right.indexOf(i) >= 0 ? 'sg ' : '') + (o.c || ''), o.t);
        if (o.v !== undefined && o.v !== null) td.setAttribute('data-v', String(o.v));
        tr.appendChild(td);
      });
      tb.appendChild(tr);
    });
    add(t, th, tb);
    sortable(t);
    return add(w, t);
  }
  // pano.py JS: tablo siralama (th tiklama, data-v) — uyarlandi
  function sortable(t) {
    var hs = t.tBodies[0];
    Array.prototype.forEach.call(t.tHead.rows[0].cells, function (th) {
      th.addEventListener('click', function () {
        var i = th.cellIndex, y = th.getAttribute('data-yon') === '-1' ? 1 : -1;
        Array.prototype.forEach.call(t.tHead.rows[0].cells, function (x) { x.removeAttribute('data-yon'); });
        th.setAttribute('data-yon', String(y));
        var sat = Array.prototype.slice.call(hs.rows), sy = sat.every(function (r) {
          var v = r.cells[i] && r.cells[i].getAttribute('data-v'); return v !== null && v !== '' && isFinite(Number(v));
        });
        var g = function (r) { var c = r.cells[i]; return sy ? Number(c.getAttribute('data-v')) : (c.getAttribute('data-v') || c.textContent).toLowerCase(); };
        sat.sort(function (a, b) { var x = g(a), z = g(b); return (x < z ? -1 : x > z ? 1 : 0) * (-y); });
        sat.forEach(function (r) { hs.appendChild(r); });
      });
    });
  }

  /* ---------- grafikler (satir ici SVG, kendi cizimimiz) ---------- */
  function lineChart(ys, o) {                                   // ys: sayilar; o.area, o.neg
    var W = 1000, H = 300, n = ys.length, mn = Math.min.apply(null, ys), mx = Math.max.apply(null, ys);
    if (o.zero) { mn = Math.min(mn, 0); mx = Math.max(mx, 0); }
    if (mx === mn) { mx += 1; mn -= 1; }
    var X = function (i) { return n < 2 ? W / 2 : i * W / (n - 1); }, Y = function (v) { return H - (v - mn) / (mx - mn) * H; };
    var svg = sv('svg', {viewBox: '0 0 ' + W + ' ' + H, preserveAspectRatio: 'none', role: 'img', 'aria-label': o.label});
    [0, 0.5, 1].forEach(function (f) { svg.appendChild(sv('line', {x1: 0, x2: W, y1: f * H, y2: f * H, 'class': 'izg'})); });
    if (o.base !== undefined && o.base >= mn && o.base <= mx) svg.appendChild(sv('line', {x1: 0, x2: W, y1: Y(o.base), y2: Y(o.base), 'class': 'baz'}));
    var d = ys.map(function (v, i) { return (i ? 'L' : 'M') + X(i).toFixed(1) + ' ' + Y(v).toFixed(1); }).join(' ');
    var yb = o.zero ? Y(0) : H;
    svg.appendChild(sv('path', {d: d + ' L' + X(n - 1).toFixed(1) + ' ' + yb.toFixed(1) + ' L' + X(0).toFixed(1) + ' ' + yb.toFixed(1) + ' Z', 'class': 'alan' + (o.neg ? ' k' : '')}));
    svg.appendChild(sv('path', {d: d, 'class': 'cizgi' + (o.neg ? ' k' : '')}));
    return {svg: svg, min: mn, max: mx};
  }
  function chartBox(c, fmt, t0, t1, extra) {
    var g = el('div', 'gk' + (extra ? ' ' + extra : ''));
    var yt = el('div', 'yt');
    add(yt, el('span', '', fmt(c.max)), el('span', '', fmt(c.min)));
    var ek = el('div', 'ek');
    add(ek, el('span', '', t0), el('span', '', t1));
    return add(g, yt, c.svg, ek);
  }
  function barChart(vals) {                                     // gunluk K/Z cubuklari
    var W = 1000, H = 300, n = vals.length, mx = Math.max.apply(null, vals.map(Math.abs).concat([1e-9]));
    var svg = sv('svg', {viewBox: '0 0 ' + W + ' ' + H, preserveAspectRatio: 'none', role: 'img', 'aria-label': 'Günlük K/Z'});
    svg.appendChild(sv('line', {x1: 0, x2: W, y1: H / 2, y2: H / 2, 'class': 'taban'}));
    var bw = W / Math.max(n, 1);
    vals.forEach(function (v, i) {
      var h = Math.abs(v) / mx * (H / 2 - 4);
      svg.appendChild(sv('rect', {x: (i * bw + bw * 0.15).toFixed(1), width: (bw * 0.7).toFixed(1), y: (v >= 0 ? H / 2 - h : H / 2).toFixed(1),
        height: Math.max(h, 0.5).toFixed(1), 'class': v >= 0 ? 'bi' : 'bk'}));
    });
    return {svg: svg, min: -mx, max: mx};
  }

  /* ---------- ust serit, bantlar ---------- */
  function renderTop(st) {
    var b = $('bantlar'); clear(b);
    if (!S.conn) add(b, el('div', 'uyari bayat-bant', 'Panel bağlantısı yok: sunucuya ulaşılamıyor, ekrandaki değerler güncel değil.'));
    if (!st || !st.ok) {
      if (st) add(b, el('div', 'uyari kritik', 'Durum okunamadı: ' + (st.code || '?')));
      return;
    }
    var kill = st.kill_file_exists === true;
    ['learner', 'twin'].forEach(function (k) {
      var x = st.bots[k];
      if (x.state !== 'live') add(b, el('div', 'uyari bayat-bant', BOT_AD[k] + ' — ' + x.banner));
      else if (x.data.kill) kill = true;
    });
    if (kill) add(b, el('div', 'uyari kritik', 'KILL AKTİF: yeni giriş yok (kill dosyası/durum).'));
    var cur = st.bots[S.bot], z = $('serit'); clear(z);
    var ro = $('rozet');
    if (cur.state === 'live') {
      var d = cur.data;
      ro.hidden = false; ro.textContent = String(d.mode || '').toUpperCase(); ro.className = 'rozet r-' + String(d.mode || '');
      var gate = d.entries_open ? 'giriş açık' : 'giriş kapalı' + (d.entries_blocked_reason ? ' (' + d.entries_blocked_reason + ')' : '');
      var st2 = d.strategy && typeof d.strategy === 'object' ? (d.strategy.name || '') + ' ' + (d.strategy.version || '') : '';
      add(z, box('Equity', usd(d.equity)), box('Gün başı equity', usd(d.day_start_equity)),
        box('Açık pozisyon', String((d.open_positions || []).length)),
        box('AÇIK K/Z', num(d.unrealized_pnl_usd) ? sgn(d.unrealized_pnl_usd) + ' $' : '—', cls(d.unrealized_pnl_usd)),
        box('Kapı', (d.gate_code || '—'), d.gate_code === 'ok' ? 'iyi' : 'kotu'),
        box('Giriş', gate, d.entries_open ? 'iyi' : 'uyarir'),
        box('Sürüm', 'v' + (d.param_version_id === null || d.param_version_id === undefined ? '—' : d.param_version_id) + ' · ' + (d.trigger_tf || '—') + ' · ' + st2));
    } else {
      ro.hidden = true;
      add(z, box('Durum', 'veri yok: ' + (cur.code || '?'), 'kotu'), box('Son döngü', cur.loop_at ? tsi(cur.loop_at) : '—'));
    }
  }

  /* ---------- sekmeler ---------- */
  function statusCur() { return S.status && S.status.ok ? S.status.bots[S.bot] : null; }

  function tabOzet(root) {
    clear(root);
    var ig = el('div', 'ig'), bot = S.bot;
    var pCurve = panel('Özsermaye eğrisi', '', 'g2 yuk'), pRisk = panel('Risk payı', 'limitler risk kilidi oranlarıyla'),
        pHealth = panel('Sağlık', ''), pDd = panel('Zirveden düşüş', ''), pKz = panel('Günlük K/Z', ''),
        pCal = panel('Takvim (günlük K/Z ısı haritası)', 'gün seç: işlemler', 'g3'),
        pCmp = panel('Öğrenen ↔ ikiz karşılaştırması', 'bugün · kapalı bölüm', 'g3');
    var sag = el('div', 'sag s1');
    add(sag, pRisk, pHealth);
    add(ig, pCurve, sag, pDd, pKz, pCal, pCmp);
    add(root, ig);
    [pCurve, pRisk, pHealth, pDd, pKz, pCal, pCmp].forEach(function (p) { add(p._body, el('div', 'yok', 'yükleniyor…')); });

    get('/api/curve?bot=' + bot).then(function (c) {
      [pCurve, pDd, pKz, pCal].forEach(function (p) { clear(p._body); });
      if (!c.ok) { [pCurve, pDd, pKz, pCal].forEach(function (p) { add(p._body, nodata(c.code)); }); return; }
      S.gen = c.generated_at;
      var pts = c.points, last = pts.length ? pts[pts.length - 1] : null;
      pCurve._right.textContent = c.base === 'equity' && last ? usd(last[1]) : (last ? 'K/Z ' + usd(last[1], true) : '');
      if (pts.length) {
        var ch = lineChart(pts.map(function (p) { return p[1]; }), {label: 'Özsermaye eğrisi', base: c.start === null ? 0 : c.start});
        add(pCurve._body, chartBox(ch, function (v) { return f2(v, 0); }, tsi(pts[0][0]), tsi(pts[pts.length - 1][0])));
      } else add(pCurve._body, el('div', 'yok', 'Henüz kapanan işlem yok.'));
      if (c.truncated) add(pCurve._body, el('div', 'alt', 'Eğri son ' + c.total_closed + ' işlemle sınırlı.'));
      add(pCurve._body, el('div', 'bol'));
      var hb = el('div', 'izgara c4');
      add(hb, box('Max düşüş', c.max_dd_pct === null ? usd(c.max_dd_abs) : pct(c.max_dd_pct)),
        box('Başlangıç', c.start === null ? 'okunamadı' : usd(c.start)),
        box('Zirve özsermaye', c.peak === null ? 'okunamadı' : usd(c.peak)), box('Kapanan işlem', String(c.total_closed)));
      add(pCurve._body.lastChild, hb);
      pCurve._body.lastChild.setAttribute('title', 'Hesap: başlangıç (motor yapılandırması wallet_start) + kapanan işlemlerin gerçekleşen K/Z toplamı.');
      if (pts.length) {
        var key = c.max_dd_pct === null ? 2 : 3, dd = lineChart(pts.map(function (p) { return p[key]; }), {label: 'Zirveden düşüş', neg: true, zero: true, base: 0});
        pDd._right.textContent = c.max_dd_pct === null ? usd(last[2]) : pct(last[3]);
        add(pDd._body, chartBox(dd, function (v) { return c.max_dd_pct === null ? f2(v, 0) : pct(v, 1); }, tsi(pts[0][0]), tsi(pts[pts.length - 1][0]), 'dus'));
      } else add(pDd._body, el('div', 'yok', 'Henüz kapanan işlem yok.'));
      if (c.daily.length) {
        var bc = barChart(c.daily.map(function (d) { return d.pnl; }));
        pKz._right.textContent = usd(c.daily[c.daily.length - 1].pnl, true);
        add(pKz._body, chartBox(bc, function (v) { return f2(v, 1); }, c.daily[0].day, c.daily[c.daily.length - 1].day, 'kz'));
      } else add(pKz._body, el('div', 'yok', 'Henüz kapanan işlem yok.'));
      renderCalendar(pCal._body, c.daily);
    });

    get('/api/risk?bot=' + bot).then(function (r) {
      clear(pRisk._body);
      if (!r.ok) { add(pRisk._body, nodata(r.code)); return; }
      r.rows.forEach(function (x) {
        var m = el('div', 'mr'), over = num(x.pct) && x.pct >= 80;
        add(m, row(x.label, usd(x.used) + ' / ' + usd(x.limit) + ' (' + (num(x.pct) ? x.pct.toFixed(0) + ' %' : '—') + ')'));
        var cb = el('div', 'cubuk' + (num(x.pct) && x.pct >= 100 ? ' k' : over ? ' u' : '')), i = el('i');
        i.style.width = (num(x.pct) ? Math.min(100, Math.max(0, x.pct)) : 0) + '%';
        add(m, add(cb, i));
        add(pRisk._body, m);
      });
    });

    get('/api/health').then(function (h) {
      clear(pHealth._body);
      if (!h.ok) { add(pHealth._body, nodata(h.code)); }
      else {
        pHealth._right.textContent = h.overall || '—';
        add(pHealth._body, row('Son denetim', h.check_stale ? 'çalışmıyor (' + ago(h.age_s) + ' önce)' : ago(h.age_s) + ' önce', h.check_stale ? 'kotu' : 'iyi'),
          row('Açık uyarı', String(h.alerts.length), h.alerts.length ? 'uyarir' : 'iyi'));
      }
      var sc = S.status && S.status.ok ? S.status.bots : null;
      if (sc) ['learner', 'twin'].forEach(function (k) {
        add(pHealth._body, row('Döngü ' + BOT_AD[k], sc[k].state === 'live' ? ago(sc[k].age_s) + ' önce' : 'BAYAT/yok', sc[k].state === 'live' ? 'iyi' : 'kotu'));
      });
    });

    get('/api/compare').then(function (c) {
      clear(pCmp._body);
      if (!c.ok) { add(pCmp._body, nodata(c.code)); return; }
      var det = el('details', 'ince'), sm = el('summary', '', 'Öğrenen ↔ ikiz — göster');
      var L = c.learner, T = c.twin;
      var rows = [];
      function cell(o, f) { return o.ok ? f(o.summary) : 'okunamadı: ' + o.code; }
      rows.push(['Kapanan işlem', cell(L, function (s) { return String(s.closed); }), cell(T, function (s) { return String(s.closed); }), '']);
      rows.push(['PnL', cell(L, function (s) { return usd(s.pnl, true); }), cell(T, function (s) { return usd(s.pnl, true); }),
        c.diff_pnl === null ? '—' : usd(c.diff_pnl, true)]);
      rows.push(['R', cell(L, function (s) { return sgn(s.r); }), cell(T, function (s) { return sgn(s.r); }), '']);
      rows.push(['Kazanan / kaybeden', cell(L, function (s) { return s.win + ' / ' + s.loss; }), cell(T, function (s) { return s.win + ' / ' + s.loss; }), '']);
      rows.push(['Açık', cell(L, function (s) { return String(s.open); }), cell(T, function (s) { return String(s.open); }), '']);
      add(det, sm, table(['Gün ' + c.day, 'Öğrenen', 'İkiz', 'Fark (öğrenen − ikiz)'], rows, {right: [1, 2, 3]}));
      add(pCmp._body, det);
    });
  }

  function renderCalendar(body, daily) {
    var map = {}; daily.forEach(function (d) { map[d.day] = d; });
    var end = S.gen ? tsiDay(S.gen) : null;
    if (!end) { add(body, el('div', 'yok', 'Takvim için zaman yok.')); return; }
    var mx = Math.max.apply(null, daily.map(function (d) { return Math.abs(d.pnl); }).concat([1e-9]));
    var e = new Date(end + 'T00:00:00Z'), dow = (e.getUTCDay() + 6) % 7;           // Pazartesi = 0
    var start = new Date(e.getTime() - (41 - (6 - dow)) * 86400000);
    var tk = el('div', 'tkv'), g = el('div', 'tkg');
    ['Pzt', 'Sal', 'Çar', 'Per', 'Cum', 'Cmt', 'Paz'].forEach(function (x) { add(g, el('div', 'bsl', x)); });
    var det = el('div', 'gd');
    for (var i = 0; i < 42; i++) {
      var dt = new Date(start.getTime() + i * 86400000), ds = dt.toISOString().slice(0, 10), v = map[ds];
      if (dt > e) break;
      if (!v) { var b0 = el('div', 'tkb'); add(b0, el('span', 'gn', ds.slice(8) + '.' + ds.slice(5, 7))); add(g, b0); continue; }
      var b = el('button', 'tk');
      add(b, el('span', 'gn', ds.slice(8) + '.' + ds.slice(5, 7)), el('span', 'pn ' + cls(v.pnl), sgn(v.pnl, 1)));
      var a = Math.min(0.55, 0.08 + Math.abs(v.pnl) / mx * 0.47);
      b.style.background = 'color-mix(in srgb,' + (v.pnl >= 0 ? 'var(--iyi)' : 'var(--kotu)') + ' ' + Math.round(a * 100) + '%,var(--bg))';
      b.setAttribute('data-gun', ds);
      b.addEventListener('click', (function (day, btn) { return function () {
        Array.prototype.forEach.call(g.querySelectorAll('.tk'), function (x) { x.classList.toggle('sec', x === btn); });
        showDay(det, day);
      }; })(ds, b));
      add(g, b);
    }
    add(tk, g); add(body, tk, det);
  }
  function showDay(box_, day) {
    clear(box_); box_.classList.add('ac');
    add(box_, el('h4', '', day + ' — o günün işlemleri'), el('div', 'yok', 'yükleniyor…'));
    get('/api/ledger?bot=' + S.bot + '&day=' + day).then(function (r) {
      clear(box_); add(box_, el('h4', '', day + ' — o günün işlemleri'));
      if (!r.ok) { add(box_, nodata(r.code)); return; }
      if (!r.closed.length) { add(box_, el('div', 'yok', 'Bu gün kapanan işlem yok.')); return; }
      add(box_, tradesTable(r.closed));
    });
  }

  function tradesTable(list) {
    var rows = list.map(function (t) {
      return [{t: tsi(t.exit_ts), v: Date.parse(t.exit_ts)}, t.pair, t.side === 'long' ? 'long' : 'short', t.setup || '',
        {t: f2(t.entry_price, 4), v: t.entry_price}, {t: f2(t.exit_price, 4), v: t.exit_price},
        {t: sgn(t.realized_pnl), v: t.realized_pnl, c: cls(t.realized_pnl)}, {t: sgn(t.r_multiple), v: t.r_multiple, c: cls(t.r_multiple)},
        {t: f2((t.fee_entry || 0) + (t.fee_exit || 0), 3), v: (t.fee_entry || 0) + (t.fee_exit || 0)}, t.exit_reason || ''];
    });
    return table(['Çıkış (TSİ)', 'Sembol', 'Yön', 'Kurulum', 'Giriş', 'Çıkış', 'K/Z $', 'R', 'Ücret', 'Neden'], rows, {right: [4, 5, 6, 7, 8]});
  }

  function tabPoz(root) {
    clear(root);
    var cur = statusCur(), p1 = panel('Açık pozisyonlar (motor durumu)', '', 'g2'), p2 = panel('Açık işlemler (defter)', ''), ig = el('div', 'ig');
    add(ig, p1, p2); add(root, ig);
    if (!cur || cur.state !== 'live') add(p1._body, nodata('bayat: ' + (cur ? cur.code : 'status')));
    else {
      var ps = cur.data.open_positions || [];
      if (!ps.length) add(p1._body, el('div', 'yok', 'Açık pozisyon yok.'));
      else add(p1._body, table(['İşlem', 'Sembol', 'Yön', 'Miktar', 'Giriş', 'Mark', 'Tutar $', 'K/Z', 'Stop'], ps.map(function (p) {
        return [String(p.trade_id), p.pair, p.side, {t: f2(p.qty, 4), v: p.qty}, {t: f2(p.entry_price, 4), v: p.entry_price},
          {t: f2(p.mark, 4), v: p.mark}, {t: f2(p.notional_usd), v: p.notional_usd},
          {t: kzTxt(p), v: p.unrealized_pnl_usd, c: cls(p.unrealized_pnl_usd)}, {t: f2(p.stop, 4), v: p.stop}];
      }), {right: [3, 4, 5, 6, 7, 8]}));
    }
    get('/api/ledger?bot=' + S.bot).then(function (r) {
      clear(p2._body);
      if (!r.ok) { add(p2._body, nodata(r.code)); return; }
      if (!r.open.length) add(p2._body, el('div', 'yok', 'Açık işlem yok.'));
      else add(p2._body, table(['İşlem', 'Sembol', 'Yön', 'Kaldıraç', 'Giriş zamanı (TSİ)', 'Planlanan risk'], r.open.map(function (t) {
        return [String(t.trade_id), t.pair, t.side, {t: String(t.leverage) + 'x', v: t.leverage}, {t: tsi(t.entry_ts), v: Date.parse(t.entry_ts)},
          {t: usd(t.planned_risk), v: t.planned_risk}];
      }), {right: [3, 5]}));
      if (cur && cur.state === 'live') {
        var a = (cur.data.open_positions || []).map(function (p) { return p.trade_id; }).sort().join(','), b = r.open.map(function (t) { return t.trade_id; }).sort().join(',');
        if (a !== b) { p2._right.textContent = ''; add(p2._body, el('div', 'cip kotu', 'Uyuşmazlık: motor durumu ile defter açık işlemleri aynı değil')); }
      }
    });
  }

  function tabIslem(root) {
    clear(root);
    var p = panel('Son kapanan işlemler', 'son 200'), pd = panel('Karar olayları (bugün)', 'atlama nedenleri'), ig = el('div', 'ig');
    add(ig, add(el('div', 'g2'), p), pd); add(root, ig);
    var fb = el('div', 'fbar2'), selS = el('select'), selY = el('select'), say = el('span', 'so');
    add(selS, new Option('tüm semboller', '')); add(selY, new Option('tüm yönler', ''), new Option('long', 'long'), new Option('short', 'short'));
    add(fb, selS, selY, say);
    var tb = el('div');
    add(p._body, fb, tb);
    function draw() {
      clear(tb);
      var l = (S.trades || []).filter(function (t) { return (!selS.value || t.pair === selS.value) && (!selY.value || t.side === selY.value); });
      say.textContent = l.length + ' işlem';
      add(tb, l.length ? tradesTable(l) : el('div', 'yok', 'Eşleşen işlem yok.'));
    }
    selS.addEventListener('change', draw); selY.addEventListener('change', draw);
    get('/api/ledger?bot=' + S.bot).then(function (r) {
      if (!r.ok) { clear(p._body); add(p._body, nodata(r.code)); clear(pd._body); add(pd._body, nodata(r.code)); return; }
      S.trades = r.closed;
      var seen = {};
      r.closed.forEach(function (t) { seen[t.pair] = 1; });
      Object.keys(seen).sort().forEach(function (k) { add(selS, new Option(k, k)); });
      draw();
      var d = r.decisions, s = r.summary;
      add(pd._body, row('Gün', r.day), row('Karar', String(d.total)), row('Girilen', String(d.entered)), row('Atlanan', String(d.skipped)),
        row('Günün kapanan işlemi', s.closed + ' · K/Z ' + usd(s.pnl, true)));
      var ks = Object.keys(d.skip_reasons);
      if (ks.length) add(pd._body, table(['Atlama nedeni', 'Sayı'], ks.map(function (k) { return [k, {t: String(d.skip_reasons[k]), v: d.skip_reasons[k]}]; }), {right: [1]}));
      else add(pd._body, el('div', 'yok', 'Atlanan karar yok.'));
    });
  }

  function tabButce(root) {
    clear(root);
    var p = panel('Yapay zekâ bütçesi', ''); add(root, add(el('div', 'ig'), p));
    get('/api/budget').then(function (b) {
      clear(p._body);
      if (!b.ok) { add(p._body, nodata(b.code)); return; }
      p._right.textContent = b.day;
      add(p._body, row('Ay', usd(b.month_used_usd) + ' / ' + usd(b.monthly_cap_usd) + ' (' + b.month_state + ')', b.month_state === 'ok' ? 'iyi' : 'uyarir'));
      Object.keys(b.services).forEach(function (k) {
        var v = b.services[k], m = el('div', 'mr'), cb = el('div', 'cubuk' + (v.state === 'ok' ? '' : ' k')), i = el('i');
        i.style.width = Math.min(100, v.pct || 0) + '%';
        add(m, row({veto: 'veto', lesson: 'ders'}[k] || k, usd(v.used_usd) + ' / ' + usd(v.cap_usd) + ' (' + v.state + ')'), add(cb, i));
        add(p._body, m);
      });
      if (!b.prices_verified) add(p._body, el('div', 'cip uyari', 'Fiyatlar doğrulanmadı'));
      if (b.provider_blocked_until) add(p._body, el('div', 'cip kotu', 'Sağlayıcı engelli: ' + tsi(b.provider_blocked_until) + ' TSİ\'ye kadar'));
    });
  }

  function tabDers(root) {
    clear(root);
    var p = panel('Ders önerileri', ''); add(root, add(el('div', 'ig'), p));
    get('/api/lesson').then(function (r) {
      clear(p._body);
      if (!r.ok) { add(p._body, nodata(r.code)); return; }
      p._right.textContent = r.open_count ? r.open_count + ' bekleyen' : 'bekleyen yok';
      if (r.open_requests.length) {
        r.open_requests.forEach(function (q) {
          var c = el('div', 'koc uyari');
          add(c, el('div', '', (q.param || '?') + ': ' + (q.from === null ? '?' : q.from) + ' → ' + (q.to === null ? '?' : q.to) + ' (' + (q.scope || '?') + ')'),
            el('div', 'alt', 'Onay Telegram\'dan: /onayla ' + q.request_id));
          add(p._body, c);
        });
      } else add(p._body, el('div', 'yok', 'Bekleyen öneri yok.'));
      add(p._body, row('Gölge dönem', r.shadow ? 'gün ' + r.shadow.day + '/' + (r.shadow.total === null ? '?' : r.shadow.total) + ' (bitiş ' + r.shadow.end + ')' : 'başlamadı'));
      add(p._body, row('Son çalışma', r.last_run ? r.last_run.day + ' ' + (r.last_run.status || 'olay yok') + (r.last_run.code ? '/' + r.last_run.code : '') : 'yok'));
      if (Array.isArray(r.proposals) && r.proposals.length) {
        add(p._body, el('h4', '', 'Defterdeki öneriler'));
        add(p._body, table(['No', 'Durum', 'Değişiklik'], r.proposals.map(function (x) { return [String(x.id), x.status, JSON.stringify(x.changes)]; })));
      } else if (r.proposals && r.proposals.code) add(p._body, nodata(r.proposals.code));
    });
  }

  function tabSaglik(root) {
    clear(root);
    var p = panel('Sağlık', ''), ps = panel('Süreç / kaynak', ''), ig = el('div', 'ig');
    add(ig, p, ps); add(root, ig);
    get('/api/health').then(function (h) {
      clear(p._body);
      if (!h.ok) { add(p._body, nodata(h.code)); return; }
      p._right.textContent = h.overall || '—';
      if (h.check_stale) add(p._body, el('div', 'uyari kritik', 'Sağlık denetimi çalışmıyor: son çalışma ' + (h.last_run_at ? tsi(h.last_run_at) + ' TSİ' : 'bilinmiyor')));
      add(p._body, row('Son denetim', h.last_run_at ? tsi(h.last_run_at) + ' TSİ' : '—'));
      if (h.alerts.length) add(p._body, table(['Kontrol', 'Kod', 'İlk görülme', 'Ardışık', 'Bildirildi'], h.alerts.map(function (a) {
        return [a.name, a.code, a.first_seen ? tsi(a.first_seen) : '—', String(a.consecutive === null ? '—' : a.consecutive), a.alerted ? 'evet' : 'hayır'];
      })));
      else add(p._body, el('div', 'yok', 'Açık uyarı yok.'));
      var rc = Object.keys(h.restart_counts);
      if (rc.length) add(p._body, el('h4', '', 'Yeniden başlatma sayaçları'), table(['Birim', 'Sayı'], rc.map(function (k) { return [k, String(h.restart_counts[k])]; })));
    });
    get('/api/system').then(function (s) {
      clear(ps._body);
      if (!s.ok) { add(ps._body, nodata(s.code)); return; }
      add(ps._body, row('Boş bellek', bytes(s.mem_available) + ' / ' + bytes(s.mem_total), s.mem_level),
        row('Takas', bytes(s.swap_used) + ' / ' + bytes(s.swap_total), s.swap_level),
        row('Boş disk', bytes(s.disk_free) + ' / ' + bytes(s.disk_total), s.disk_level || ''));
    });
  }

  var RENDER = {ozet: tabOzet, pozisyonlar: tabPoz, islemler: tabIslem, butce: tabButce, ders: tabDers, saglik: tabSaglik};

  /* ---------- sekme rozetleri (2026-11-18): acik pozisyon, kapanan islem, bekleyen ders, acik uyari ---------- */
  function badge(t, n, kotu) {
    var b = document.querySelector('.tabs button[data-t="' + t + '"]');
    if (!b) return;
    var e = b.querySelector('em');
    if (!num(n)) { if (e) b.removeChild(e); return; }
    if (!e) { e = el('em'); b.appendChild(e); }
    e.textContent = String(n);
    e.className = kotu && n > 0 ? 'k' : '';
  }
  function refreshBadges() {
    var cur = statusCur();
    badge('pozisyonlar', cur && cur.state === 'live' ? (cur.data.open_positions || []).length : null);
    get('/api/ledger?bot=' + S.bot).then(function (r) {
      if (!r.ok) { badge('islemler', null); return; }
      if (!(cur && cur.state === 'live')) badge('pozisyonlar', r.open.length);
      badge('islemler', r.closed.length);
    });
    get('/api/lesson').then(function (r) { badge('ders', r.ok ? r.open_count || 0 : null); });
    get('/api/health').then(function (h) { badge('saglik', h.ok ? h.alerts.length : null, true); });
  }

  /* ---------- dongu ---------- */
  function setGen(st) {
    if (st && st.ok) { S.gen = st.generated_at; $('uretim').textContent = 'sunucu: ' + tsi(st.generated_at) + ' TSİ'; }
  }
  function refreshTop() {
    return get('/api/status').then(function (st) { S.status = st; setGen(st); renderTop(st); });
  }
  function refreshTab() {
    var root = $('sek-' + S.tab);
    RENDER[S.tab](root);
  }
  function showTab(t) {
    S.tab = t;
    Array.prototype.forEach.call(document.querySelectorAll('.tabs button'), function (b) { b.classList.toggle('on', b.getAttribute('data-t') === t); });
    Array.prototype.forEach.call(document.querySelectorAll('.sek'), function (s) { s.classList.toggle('on', s.id === 'sek-' + t); });
    try { localStorage.setItem('trader-sekme', t); } catch (e) { /* yok say */ }
    refreshTab();
  }
  function setBot(b) {
    S.bot = b;
    $('bot-learner').classList.toggle('on', b === 'learner'); $('bot-twin').classList.toggle('on', b === 'twin');
    renderTop(S.status); refreshTab(); refreshBadges();
  }

  function init() {
    var nav = $('tabs');
    TABS.forEach(function (t) {
      var b = el('button', '', t[1]); b.type = 'button'; b.setAttribute('data-t', t[0]);
      b.addEventListener('click', function () { showTab(t[0]); });
      nav.appendChild(b);
    });
    $('bot-learner').addEventListener('click', function () { setBot('learner'); });
    $('bot-twin').addEventListener('click', function () { setBot('twin'); });
    $('yenile').addEventListener('click', function () { if (SNAP) { location.reload(); return; } refreshTop(); refreshTab(); refreshBadges(); });
    snapBanner(); setInterval(snapBanner, 30000);
    // pano.py JS: tema dugmesi (uyarlandi)
    (function () {
      var k = 'trader-tema', h = document.documentElement;
      try { var t = localStorage.getItem(k); if (t) h.setAttribute('data-theme', t); } catch (e) { /* yok say */ }
      $('tema').addEventListener('click', function () {
        var m = h.getAttribute('data-theme'), koyu = m ? m === 'dark' : true, y = koyu ? 'light' : 'dark';
        h.setAttribute('data-theme', y);
        try { localStorage.setItem(k, y); } catch (e) { /* yok say */ }
      });
    })();
    var first = 'ozet';
    try { var s = localStorage.getItem('trader-sekme'); if (s && RENDER[s]) first = s; } catch (e) { /* yok say */ }
    refreshTop().then(function () { showTab(first); refreshBadges(); });
    setInterval(function () { if (!document.hidden) refreshTop(); }, TOP_MS);
    setInterval(function () { if (!document.hidden) { refreshTab(); refreshBadges(); } }, TAB_MS);
    document.addEventListener('visibilitychange', function () { if (!document.hidden) { refreshTop(); refreshTab(); refreshBadges(); } });
  }
  init();
})();
