// 两个平台共用的部分：配置、黑名单比对、天数、翻页主循环、结果输出。
// 不单独贴进页面：jobscan.py inject 会把它和 boss.js / zhilian.js 拼成一个注入文件。
// 页面里只读列表数据、滚动加载，不点开岗位、不点任何沟通/投递按钮。

var ssleep = ms => new Promise(r => setTimeout(r, ms));

// ---------- 配置 ----------
// cfg = {platform, days, mode, blacklist:[{company, job}], keywords:[词], refresh, old, code, cfgv, seen, seenn, seenv}
// refresh、old 只管智联：refresh='latest' 时凌晨刷新也按刷新时间算天数（默认 'first' 改用首次发布）；
// old=[甲, 乙] 时首次发布超过甲天、不超过乙天的算老岗位跳过（没设就不按首次发布筛）。
// seen 是看过的岗位编号短码连在一起（每条 7 个字符），seenn 条数，seenv 它的版本号，都由 jobscan.py 算好。
// days、mode 没填就拒绝开跑：要先问使用者（Python 那边也会拦）。
window.__sInit = cfg => {
  cfg = cfg || {};
  const days = cfg.days;
  if (!(Number.isInteger(days) && days >= 1)) return 'cfg-bad 天数没设，先问使用者';
  if (cfg.mode !== 'company' && cfg.mode !== 'company_job' && cfg.mode !== 'ask') return 'cfg-bad 拦法没设，先问使用者';
  window.__sCfg = cfg;
  const s = String(cfg.seen || ''), seen = new Set();
  for (let i = 0; i + 7 <= s.length; i += 7) seen.add(s.slice(i, i + 7));
  window.__sSeen = seen;
  // 黑名单、天数或看过的记录改了、只重贴配置时，已经读到的结果按新配置重判，不用重翻
  for (const r of Object.values(window.__sRows || {})) window.__sMark(r);
  return 'ready 代码' + cfg.code + ' 配置' + cfg.cfgv + ' 看过' + (cfg.seenn || 0) + '条 黑名单' + (cfg.blacklist || []).length + '条 天数' + days + ' 拦法' + cfg.mode + ' 关键词' + (cfg.keywords || []).length + '个';
};

// 岗位编号的短码：两遍 FNV-1a 拼成 42 位，写成 7 个字符。和 jobscan.py 的 seen_code 算法一样（用例会两边对照）
window.__sB64 = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz-_';
window.__sFnv = (s, h) => { for (let i = 0; i < s.length; i++) h = Math.imul(h ^ s.charCodeAt(i), 16777619) >>> 0; return h; };
window.__sCode = id => {
  const s = String(id);
  let v = window.__sFnv(s, 2166136261) * 1024 + (window.__sFnv('#' + s, 2166136261) & 1023), out = '';
  for (let i = 0; i < 7; i++) { out = window.__sB64[v % 64] + out; v = Math.floor(v / 64); }
  return out;
};

// ---------- 黑名单比对 ----------
// 公司名整理：去空白和括号里的字（分公司、地区标注），去掉名字太长被截断留下的省略号（Boss 会写成「…...」），去结尾的公司类型，转小写。
window.__sCoNorm = s => {
  s = String(s || '').replace(/\s/g, '').replace(/[（(][^（()）]*[)）]/g, '').replace(/(\.{2,}|…+)$/, '').toLowerCase();
  let prev;
  do { prev = s; s = s.replace(/(股份有限公司|有限责任公司|有限公司|分公司|总公司|集团|公司)$/, ''); } while (s !== prev && s.length > 2);
  return s;
};
// 两个平台写法不同：一边常是简称（甲乙科技），一边是全称（示例市甲乙科技有限公司）。
// 短的那个出现在长的里面，并且前面要么没有字、要么只是地名前缀（2-3 个字，可带省/市/自治区/区/县，最多两段），才算同一家。
window.__sCoEq = (a, b) => {
  a = window.__sCoNorm(a); b = window.__sCoNorm(b);
  if (a.length < 2 || b.length < 2) return false;
  if (a === b) return true;
  const s = a.length <= b.length ? a : b, l = a.length <= b.length ? b : a;
  for (let i = l.indexOf(s); i >= 0; i = l.indexOf(s, i + 1)) {
    if (i === 0 || /^([一-龥]{2,3}(省|市|自治区|区|县)?){1,2}$/.test(l.slice(0, i))) return true;
  }
  return false;
};
// 岗位名整理：去空白、Boss 求职期望列表加的福利后缀（「行政专员-双休」，推荐里同一岗位没有）、括号里的字和标点。
// 一个包含另一个，或者字一样只是顺序不同（如「市场运营」和「运营市场」），算同一个岗位。
window.__sJobTail = /(.)[-—](?:[+＋]?(?:(?:周末)?双休|[五六]险一金|五险|出差|包吃住|包吃|包住|包餐|无经验|日结|上一休一))+$/;
window.__sJobNorm = s => {
  s = String(s || '').replace(/\s/g, '');
  while (window.__sJobTail.test(s)) s = s.replace(window.__sJobTail, '$1');
  return s.replace(/[（(【\[][^（()）】\]]*[)）】\]]/g, '').replace(/[\/、\-—·|,，.。:：]/g, '').toLowerCase();
};
window.__sJobEq = (a, b) => {
  a = window.__sJobNorm(a); b = window.__sJobNorm(b);
  if (a.length < 2 || b.length < 2) return false;
  if (a.indexOf(b) >= 0 || b.indexOf(a) >= 0) return true;
  return a.length === b.length && a.split('').sort().join('') === b.split('').sort().join('');
};
// 拦法 company：公司对上就拦；company_job：公司和岗位都对上才拦（这种拦法下每条都必须有岗位，Python 那边保证）；
// ask（每次问）：每条自己定，没写岗位的拦整家公司，写了岗位的只拦这个岗位。
window.__sBlock = (co, job) => {
  const cfg = window.__sCfg || {};
  for (const b of cfg.blacklist || []) {
    if (!window.__sCoEq(b.company, co)) continue;
    if (cfg.mode === 'company' || (cfg.mode === 'ask' && !b.job)) return b;
    if (b.job && window.__sJobEq(b.job, job)) return b;
  }
  return null;
};

// ---------- 不想看的关键词 ----------
// 岗位标题（不看公司名）含这些词就跳过，去空白、不分大小写。没设就不拦。返回命中的词。
window.__sKw = job => {
  const t = String(job || '').replace(/\s/g, '').toLowerCase();
  for (const w of (window.__sCfg || {}).keywords || []) {
    const k = String(w).replace(/\s/g, '').toLowerCase();
    if (k && t.indexOf(k) >= 0) return w;
  }
  return '';
};

// ---------- 天数 ----------
// 开了按首次发布筛（cfg.old）的智联岗位，留下的在备注里写明：查不到首次发布的，和首次发布超过乙天的
window.__sOldNote = (r, now) => {
  const o = (window.__sCfg || {}).old;
  if (!Array.isArray(o) || r.st || (window.__sP || {}).platform !== 'zhilian') return '';
  const f = window.__sAge(r.fp, now);
  if (f === null) return '首次发布日期不明';
  return f > o[1] ? '首次发布 ' + String(r.fp).slice(0, 10) + '（超过 ' + o[1] + ' 天）' : '';
};
// 按日历日算：今天发布是 0 天，昨天是 1 天。超过 N 天 = 天数 > N。
window.__sAge = (t, now) => {
  const m = String(t || '').match(/(\d{4})-(\d{1,2})-(\d{1,2})/);
  if (!m) return null;
  const n = new Date(now || Date.now());
  const today = new Date(n.getFullYear(), n.getMonth(), n.getDate());
  return Math.round((today - new Date(+m[1], +m[2] - 1, +m[3])) / 864e5);
};
// 智联凌晨 00:00-02:59 的发布时间是平台自动刷新，不是真发布时间。
window.__sRefresh = t => /\s0[0-2]:\d\d/.test(String(t || ''));

// 一条结果该不该留：先看黑名单，再看天数（Boss 没有发布时间，不按天数筛），再看关键词，最后看编号是不是看过的。
// row = {id, co, job, pub}，pub 为空表示不知道发布时间（智联凌晨刷新又没有首次发布时间的）。返回空串 = 留下，否则是跳过原因。
// 看过的这里只按编号先跳过，省得取结果时多取一半；投过、重复、换了编号的看过，jobscan.py save 时按 data/ 里的记录再筛。
window.__sJudge = (row, platform, now) => {
  const cfg = window.__sCfg || {};
  if (window.__sBlock(row.co, row.job)) return '黑名单';
  if (platform !== 'boss') {
    const a = window.__sAge(row.pub, now);
    if (a === null) return '发布时间不明';
    if (a > cfg.days) return '超过天数';
    const o = cfg.old, f = Array.isArray(o) ? window.__sAge(row.fp, now) : null;
    if (f !== null && f > o[0] && f <= o[1]) return '老岗位';
  }
  if (window.__sKw(row.job)) return '关键词';
  if (row.id && window.__sSeen && window.__sSeen.has(window.__sCode(row.id))) return '看过';
  return '';
};

// ---------- 翻页主循环 ----------
// P 是平台适配（boss.js / zhilian.js 提供）：
//   list() 当前列表原始数据，row(p) 转成 {id, co, job, sal, pub, loc（区·商圈/街道）, exp, deg, hr（招聘人）, sk（技能标签）,
//   desc（岗位描述开头，只有智联列表里有）, raw, note}，hasMore()，more() 加载下一屏，
//   login() 登录了没有（'ok'、'没登录'、'还在加载'），problem() 安全验证/没登录/掉线/离开页面时返回原因，switchTag(名字)，sortNewest() 点「最新」并返回是否排好，
//   oldEnough(list, days) 列表尾部是否已经超过 N 天（只有智联有）。
window.__sRows = window.__sRows || {};
window.__sMark = r => {
  const P = window.__sP || {};
  if (P.repub) Object.assign(r, P.repub(r));  // 智联：刷新时间的算法改了（重贴配置）也按新的算
  r.st = window.__sJudge(r, P.platform);
  r.fnote = window.__sOldNote(r);
  const b = r.st === '黑名单' && window.__sBlock(r.co, r.job);
  r.hit = b ? b.company + (b.job ? '/' + b.job : '') : '';
  r.kw = r.st === '关键词' ? window.__sKw(r.job) : '';
};
window.__sTake = () => {
  const P = window.__sP, rows = window.__sRows;
  for (const p of P.list()) {
    const r = P.row(p);
    if (!r.id || rows[r.id]) continue;
    window.__sMark(r);
    rows[r.id] = r;
  }
};
window.__sRun = tag => {
  const P = window.__sP, cfg = window.__sCfg;
  if (!P || !cfg) return 'not-ready 先注入';
  if (window.__sState && window.__sState.stage !== 'done') return 'busy 上一次还没跑完';
  // start 是这次扫描的开始时间，写进头行；Python 靠它认出同一次扫描是不是已经存过
  const S = window.__sState = { tag: tag || '当前列表', stage: 'start', why: '', sorted: false, loads: 0, t: Date.now(), start: new Date().toISOString() };
  window.__sRows = {};
  (async () => {
    try {
      if (P.login() === '没登录') { S.why = '没登录'; return; }  // 没登录就停，不点标签、不翻
      if (tag) { S.stage = 'tag'; if (!(await P.switchTag(tag))) { S.why = '找不到标签:' + tag; return; } }
      S.stage = 'sort'; S.sorted = await P.sortNewest();
      S.looped = true;
      for (let k = 0; k < 200; k++) {
        S.t = Date.now();
        const bad = P.problem(); if (bad) { S.why = bad; return; }
        window.__sTake();
        if (S.stopReq) { S.why = '手动停了（没翻完）'; return; }
        if (P.platform === 'zhilian' && S.sorted && P.oldEnough(P.list(), cfg.days)) { S.why = '超过' + cfg.days + '天'; return; }
        if (!P.hasMore()) { S.why = '到底'; return; }
        S.stage = 'load';
        if (!(await P.more())) { S.why = '加载不出更多（重试过，没翻完）'; return; }
        S.loads++;
        await ssleep(3000 + Math.random() * 3000);
      }
      S.why = '到了加载次数上限（没翻完）';
    } catch (e) {
      S.why = '出错:' + (e && e.message);
    } finally {
      try { if (S.looped && !P.problem()) window.__sTake(); } catch (e) {}  // 最后一屏加载完还没收进来的
      S.stage = 'done'; S.t = Date.now();
    }
  })();
  return 'started';
};

// 等扫描跑完：每 5 秒看一次，跑完马上返回，最多看 n 次（默认 8 次，约 40 秒；工具单次调用超过 45 秒会超时）。返回 __sStatus()
window.__sWait = async n => {
  for (let i = 0; i < (n || 8) && window.__sState && window.__sState.stage !== 'done'; i++) await ssleep(5000);
  return window.__sStatus();
};
// 登录了没有：'ok'、'没登录'、'还在加载'（页面数据还没出来，等几秒再查）。开工时查一次，扫描中每一屏也查
window.__sLogin = () => (window.__sP && window.__sP.login ? window.__sP.login() : '还在加载');
// 使用者说停就停，已经读到的照样能取；停的原因写明没翻完
// 页面顶部的标签名，使用者说「开始」时按它记任务：去空白、去掉空的和重复的；
// cut=true 时去掉末尾的城市括号（Boss 期望标签「行政专员/助理(天津)」，__sRun 按开头对得上）
window.__sTagNames = (sel, cut) => [...new Set([...document.querySelectorAll(sel)]
  .map(e => String(e.innerText || '').trim().replace(cut ? /\s*[（(][^（()）]*[)）]$/ : /$^/, '')).filter(Boolean))];
window.__sTags = () => (window.__sP && window.__sP.tags ? window.__sP.tags() : []);
window.__sStop = () => { const S = window.__sState; if (!S || S.stage === 'done') return 'not-running'; S.stopReq = true; return 'stopping'; };

// ---------- 进度和结果 ----------
window.__sCount = () => {
  const c = { 留: 0, 黑名单: 0, 超过天数: 0, 发布时间不明: 0, 老岗位: 0, 关键词: 0, 看过: 0 };
  for (const r of Object.values(window.__sRows)) c[r.st || '留']++;
  return c;
};
// 输出里不带 = ; & ? 和换行（工具会拦或吞掉），字段里的 | 和 @ 换掉，免得和分隔符混。
window.__sClean = s => String(s == null ? '' : s).replace(/[\r\n|@]/g, ' ').replace(/=/g, '＝').replace(/;/g, '；').replace(/&/g, '＆').replace(/\?/g, '？').trim();
// 「已按最新/没按最新」只有智联有（Boss 没有这个排序），Boss 不写
window.__sStatus = () => {
  const S = window.__sState || {}, c = window.__sCount(), P = window.__sP || {};
  const a = [S.stage || '没开跑', S.why || '', '已读' + Object.keys(window.__sRows).length, '留' + c.留, '黑名单' + c.黑名单,
    '超过天数' + c.超过天数, '时间不明' + c.发布时间不明, '老岗位' + c.老岗位, '关键词' + c.关键词, '看过' + c.看过];
  if (P.platform === 'zhilian') a.push(S.sorted ? '已按最新' : '没按最新');
  a.push(Math.round((Date.now() - (S.t || 0)) / 1000) + '秒前有动静');
  return window.__sClean(a.join(' / '));
};
// 关键词按词计数，按配置里词的顺序写成「词:条数,词:条数」，放进头行
window.__sKwText = () => {
  const c = {};
  for (const r of Object.values(window.__sRows)) if (r.st === '关键词') c[r.kw] = (c[r.kw] || 0) + 1;
  return ((window.__sCfg || {}).keywords || []).filter(w => c[w]).map(w => w + ':' + c[w]).join(',');
};
// 结果放进页面上一个看不见的 <article>，再用 get_page_text 取回（javascript_tool 输出约 1200 字就截断）。
// 每行以 @@ 开头（get_page_text 会把换行变成空格）。留下的和黑名单拦下的逐条列，超过天数、时间不明、老岗位、关键词、看过的只给个数。
// 头行带上页面用的看过记录（条数、版本号），save 用它核对页面没用上清空以前的旧记录。
// 每段最多 100 行（约 1.5 万字），段数写在头行；每段最后一行 @@E 带本段行数，Python 用它核对有没有取全。
window.__sLines = () => {
  const C = window.__sClean, out = [];
  for (const r of Object.values(window.__sRows)) if (!r.st) out.push('@@R|' + [r.id, r.co, r.job, r.sal, r.pub, r.loc, r.exp, r.deg, r.hr, r.sk, r.desc, [r.note, r.fnote].filter(Boolean).join('；')].map(C).join('|'));
  for (const r of Object.values(window.__sRows)) if (r.st === '黑名单') out.push('@@B|' + [r.id, r.co, r.job, r.sal, r.pub, r.loc, r.hit].map(C).join('|'));
  return out;
};
window.__sText = k => {
  const S = window.__sState || {}, cfg = window.__sCfg || {}, P = window.__sP || {}, c = window.__sCount(), C = window.__sClean;
  const L = window.__sLines(), n = Math.max(1, Math.ceil(L.length / 100));
  k = k || 0;
  const part = L.slice(k * 100, k * 100 + 100);
  return ['@@H|' + [P.platform, S.tag, S.why, S.sorted ? '最新' : '默认', cfg.days, cfg.mode, Object.keys(window.__sRows).length,
    c.留, c.黑名单, c.超过天数, c.发布时间不明, c.老岗位, c.关键词, window.__sKwText(), c.看过, cfg.seenn || 0, cfg.seenv || '', cfg.code, cfg.cfgv, S.start || '', k + 1, n].map(C).join('|')]
    .concat(part, ['@@E|' + (k + 1) + '|' + n + '|' + part.length]).join('\n');
};
// k 从 0 开始；返回值里说了一共几段
window.__sShow = k => {
  const S = window.__sState || {};
  if (S.stage !== 'done') return 'not-done ' + window.__sStatus();
  let a = document.getElementById('__sres');
  if (a) a.remove();
  a = document.createElement('article');
  a.id = '__sres';
  a.style.cssText = 'position:fixed;left:0;top:0;width:10px;height:10px;overflow:hidden;opacity:0.01;z-index:-1;pointer-events:none';
  a.textContent = window.__sText(k);
  document.body.appendChild(a);
  setTimeout(() => { const x = document.getElementById('__sres'); if (x) x.remove(); }, 60000);
  const n = Math.max(1, Math.ceil(window.__sLines().length / 100));
  return 'shown 第' + ((k || 0) + 1) + '段/共' + n + '段，现在用 get_page_text 取';
};
