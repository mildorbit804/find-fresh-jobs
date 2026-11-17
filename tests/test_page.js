// 页面脚本（page/*.js）的正反用例。jobscan.py 每条命令执行前都会跑：node tests/test_page.js
// 先用现在的脚本跑一遍，必须全过；再把脚本改成几种错误写法（MUTANTS）各跑一遍，每种都必须有用例不过。
// 页面用假的 window/document 模拟，计时器立即触发，不连网、不开浏览器。
const vm = require('vm'), fs = require('fs'), path = require('path');
const PAGE = path.join(__dirname, '..', 'page');
const read = f => fs.readFileSync(path.join(PAGE, f), 'utf8');
const NOW = new Date(2030, 0, 10, 12, 0, 0).getTime();  // 2030-01-10 12:00

// ---------- 假页面 ----------
function fakePage(platform, pages, opt) {
  opt = opt || {};
  const list = [], pending = pages.slice(1);
  list.push(...pages[0]);
  const state = { positionList: list, hasMore: pending.length > 0 || !!opt.moreForever, user: opt.user };
  const vmBoss = { jobList: list, hasMore: state.hasMore };
  const push = () => {
    if (!pending.length) return;
    list.push(...pending.shift());
    state.hasMore = vmBoss.hasMore = pending.length > 0 || !!opt.moreForever;
  };
  const sortBtn = { innerText: '最新', className: 'jobs-list-sort-placeholder__item', getBoundingClientRect: () => ({ y: 172 }),
    click() { this.className += ' jobs-list-sort-placeholder__item--active'; } };
  // 标签：点了就把选中标记移到这个标签上（智联是外层多 intention-tabs__item--active，Boss 是它自己多 active）；tabStuck 时点了没反应
  const tabs = (opt.tabs || []).map(t => ({ innerText: t, clicked: 0, className: opt.tabClass || 'expect-item', parentElement: { className: 'intention-tabs__item' },
    click() {
      this.clicked++;
      if (opt.tabStuck) return;
      for (const x of tabs) { x.parentElement.className = 'intention-tabs__item'; x.className = 'expect-item'; }
      this.parentElement.className += ' intention-tabs__item--active';
      this.className += ' active';
    } }));
  const doc = {
    title: opt.title || '职位列表',
    body: { scrollHeight: 5000, appendChild() {}, innerText: opt.bodyText || '' },
    documentElement: { scrollHeight: 5000 },
    getElementById: () => null,
    createElement: () => ({ style: {}, remove() {} }),
    querySelector: sel => {
      if (sel === '#root') return platform === 'zhilian' ? { __vue__: { $store: { state } } } : null;
      if (sel === '.job-detail-box') return platform === 'boss' ? { __vue__: vmBoss, parentElement: null } : null;
      if (sel === '#wrap') return platform === 'boss' && opt.bossUser ? { __vue__: { $store: { state: opt.bossUser } } } : null;
      return null;
    },
    querySelectorAll: sel => {
      if (sel === 'button.jobs-list-sort-placeholder__item') return opt.noSort ? [] : [sortBtn];
      if (sel === '.intention-tabs__text' || sel === '.c-expect-select a, a.expect-item') return tabs;
      return [];
    },
  };
  const win = {
    document: doc, console, Event: function Event() {}, innerHeight: 800,
    location: platform === 'boss' ? { hostname: 'www.zhipin.com', pathname: opt.path || '/web/geek/jobs' } : { hostname: opt.host || 'www.zhaopin.com', pathname: '/jobs/' },
    scrollTo: (x, y) => { if (y >= 5000) push(); },
    dispatchEvent() {},
    setTimeout: (f) => setImmediate(f),
    Date: class extends Date { constructor(...a) { if (a.length) super(...a); else super(NOW); } static now() { return NOW; } },
    Math,
  };
  win.window = win;
  return { win, state, tabs, sortBtn };
}

function load(srcs, platform, pages, opt) {
  const f = fakePage(platform, pages || [[]], opt);
  vm.createContext(f.win);
  vm.runInContext(srcs.common + '\n' + srcs[platform], f.win);
  return f;
}

const cfg = (o) => Object.assign({ platform: 'zhilian', days: 7, mode: 'company', blacklist: [], code: 'c0', cfgv: 'v0' }, o);
const zp = (n, pub, first, co, job) => ({ number: n, publishTime: pub, firstPublishTime: first || pub, companyName: co || '戊己信息有限公司', name: job || '运营专员', salary60: '6000-8000元' });
const bp = (id, co, job) => ({ encryptJobId: id, brandName: co || '戊己信息', jobName: job || '运营专员', salaryDesc: '6-8K' });
const days = d => { const x = new Date(2030, 0, 10 - d, 10, 0, 0); return x.getFullYear() + '-' + String(x.getMonth() + 1).padStart(2, '0') + '-' + String(x.getDate()).padStart(2, '0'); };
const at = (d, hm) => days(d) + ' ' + hm + ':00';
const eq = (a, b, msg) => { if (a !== b) throw new Error((msg || '') + ' 期望 ' + JSON.stringify(b) + ' 实际 ' + JSON.stringify(a)); };
const ok = (v, msg) => { if (!v) throw new Error(msg || '不成立'); };
const settle = async (w) => { for (let i = 0; i < 20000 && w.__sState.stage !== 'done'; i++) await new Promise(r => setImmediate(r)); };

// ---------- 用例 ----------
const CASES = {
  // 黑名单：拦公司
  '拦公司：同公司别的岗位也拦'(S) {
    const { win: w } = load(S, 'boss'); w.__sInit(cfg({ platform: 'boss', mode: 'company', blacklist: [{ company: '甲乙科技', job: '' }] }));
    ok(w.__sBlock('甲乙科技', '数据专员'), '同公司没拦住');
    ok(!w.__sBlock('丙丁商贸', '运营专员'), '别的公司被误拦');
  },
  // 黑名单：拦公司+岗位
  '拦公司+岗位：只拦这个岗位'(S) {
    const { win: w } = load(S, 'boss'); w.__sInit(cfg({ platform: 'boss', mode: 'company_job', blacklist: [{ company: '甲乙科技', job: '运营专员' }] }));
    ok(w.__sBlock('甲乙科技', '运营专员（双休）'), '同岗位没拦住');
    ok(!w.__sBlock('甲乙科技', '数据专员'), '同公司别的岗位被误拦');
    ok(!w.__sBlock('丙丁商贸', '运营专员'), '别的公司同名岗位被误拦');
  },
  '拦公司+岗位：岗位名字顺序不同、多了后缀也认'(S) {
    const { win: w } = load(S, 'boss'); w.__sInit(cfg({ platform: 'boss', mode: 'company_job', blacklist: [{ company: '甲乙科技', job: '市场运营专员' }] }));
    ok(w.__sBlock('甲乙科技', '运营市场专员'), '顺序不同没认出');
    ok(w.__sBlock('甲乙科技', '市场运营专员/助理'), '多了「/助理」没认出');
    ok(!w.__sBlock('甲乙科技', '市场专员'), '短一截的不同岗位不该算');
  },
  '每次问：没写岗位的拦整家，写了岗位的只拦这个'(S) {
    const { win: w } = load(S, 'boss');
    ok(/^ready/.test(w.__sInit(cfg({ platform: 'boss', mode: 'ask', blacklist: [{ company: '甲乙科技', job: '' }, { company: '丙丁商贸', job: '运营专员' }] }))), '每次问的拦法没装上');
    ok(w.__sBlock('甲乙科技', '数据专员'), '整家公司的条目没拦住同公司别的岗位');
    ok(w.__sBlock('丙丁商贸', '运营专员'), '只拦岗位的条目没拦住这个岗位');
    ok(!w.__sBlock('丙丁商贸', '数据专员'), '只拦岗位的条目误拦了同公司别的岗位');
  },
  // 两个平台互相拦
  '在 Boss 拉黑（简称），扫智联（全称）也拦'(S) {
    const { win: w } = load(S, 'zhilian'); w.__sInit(cfg({ blacklist: [{ company: '甲乙科技', job: '' }] }));
    const r = w.__sP.row(zp('CC1J1', at(1, '10:00'), null, '示例市甲乙科技有限公司', '运营专员'));
    eq(w.__sJudge(r, 'zhilian', NOW), '黑名单');
  },
  '在智联拉黑（全称），扫 Boss（简称）也拦'(S) {
    const { win: w } = load(S, 'boss'); w.__sInit(cfg({ platform: 'boss', mode: 'company_job', blacklist: [{ company: '示例市甲乙科技有限公司', job: '运营专员' }] }));
    const r = w.__sP.row(bp('b1', '甲乙科技', '运营专员'));
    eq(w.__sJudge(r, 'boss', NOW), '黑名单');
    eq(w.__sJudge(w.__sP.row(bp('b2', '甲乙科技', '数据专员')), 'boss', NOW), '', '拦公司+岗位时别的岗位被拦');
  },
  '公司名两段地名、括号、公司类型不同也认'(S) {
    const { win: w } = load(S, 'boss'); w.__sInit(cfg({ platform: 'boss', blacklist: [{ company: '示例省示例市甲乙科技股份有限公司', job: '' }] }));
    ok(w.__sBlock('甲乙科技有限公司', 'x'), '去掉地名和公司类型后没认出');
    ok(w.__sBlock('甲乙（示例）科技', 'x'), '括号里的字没去掉');
  },
  'Boss 名字太长被截成「...」也认'(S) {
    const { win: w } = load(S, 'boss'); w.__sInit(cfg({ platform: 'boss', blacklist: [{ company: '示例市甲乙丙丁科技发展有限公司', job: '' }, { company: '庚辛壬癸信息...', job: '' }] }));
    ok(w.__sBlock('示例市甲乙丙丁科技...', 'x'), 'Boss 截断的名字没认出');
    ok(w.__sBlock('庚辛壬癸信息技术有限公司', 'x'), '从 Boss 截断名拉黑的，全称没认出');
  },
  '公司名前面带区、县也认'(S) {
    const { win: w } = load(S, 'zhilian'); w.__sInit(cfg({ blacklist: [{ company: '甲乙科技', job: '' }] }));
    ok(w.__sBlock('示例市示例新区甲乙科技有限公司', 'x'), '市+区的前缀没认出');
    ok(w.__sBlock('示例省示例区甲乙科技有限公司', 'x'), '省+区的前缀没认出');
    ok(w.__sBlock('示例县甲乙科技有限公司', 'x'), '县的前缀没认出');
    ok(!w.__sBlock('示例集团下属分支甲乙科技', 'x'), '前面一长串不是地名的字也被当成地名');
  },
  'Boss 求职期望列表岗位名带福利后缀也拦（只拦这一个岗位）'(S) {
    const { win: w } = load(S, 'boss'); w.__sInit(cfg({ platform: 'boss', mode: 'company_job', blacklist: [{ company: '甲乙科技', job: '人事行政专员' }] }));
    eq(w.__sJudge(w.__sP.row(bp('b1', '甲乙科技', '行政人事专员-双休')), 'boss', NOW), '黑名单', '带「-双休」后缀、词序不同的同一岗位没拦');
    eq(w.__sJudge(w.__sP.row(bp('b2', '甲乙科技', '行政人事专员-出差补助')), 'boss', NOW), '', '横杠后面不是福利词也被当成同一岗位');
  },
  '名字只是碰巧有几个字相同的不拦'(S) {
    const { win: w } = load(S, 'boss'); w.__sInit(cfg({ platform: 'boss', blacklist: [{ company: '甲乙', job: '' }, { company: '庚辛科技', job: '' }] }));
    ok(!w.__sBlock('丙甲乙丁科技', 'x'), '「甲乙」在别人名字中间（前面只有一个字）被误拦');
    ok(!w.__sBlock('庚辛商贸', 'x'), '只有前两个字相同被误拦');
    ok(w.__sBlock('甲乙集团', 'x'), '「甲乙集团」应该拦');
  },
  // 天数
  '天数边界：正好 N 天留，N+1 天跳过'(S) {
    const { win: w } = load(S, 'zhilian'); w.__sInit(cfg({ days: 7 }));
    eq(w.__sJudge(w.__sP.row(zp('a', at(7, '09:00'))), 'zhilian', NOW), '', '7 天前');
    eq(w.__sJudge(w.__sP.row(zp('b', at(8, '23:59'))), 'zhilian', NOW), '超过天数', '8 天前');
    eq(w.__sJudge(w.__sP.row(zp('c', at(0, '11:59'))), 'zhilian', NOW), '', '今天');
  },
  '天数照配置来，不是写死 7 天'(S) {
    const { win: w } = load(S, 'zhilian'); w.__sInit(cfg({ days: 3 }));
    eq(w.__sJudge(w.__sP.row(zp('a', at(4, '10:00'))), 'zhilian', NOW), '超过天数', 'N=3 时 4 天前');
    eq(w.__sJudge(w.__sP.row(zp('b', at(3, '10:00'))), 'zhilian', NOW), '', 'N=3 时 3 天前');
  },
  // 智联凌晨刷新
  '凌晨刷新：默认按最近刷新时间算（refresh=latest），避免刚重挂撞上凌晨轮刷被误杀'(S) {
    const { win: w } = load(S, 'zhilian'); w.__sInit(cfg({}));
    const r = w.__sP.row(zp('a', at(0, '01:15'), at(40, '10:00')));
    eq(r.pub, at(0, '01:15')); eq(r.note, '');
    eq(w.__sJudge(r, 'zhilian', NOW), '', '默认按最近刷新时间，40天前首发的也不误杀');
  },
  '凌晨刷新设为 first：按首次发布时间判断'(S) {
    const { win: w } = load(S, 'zhilian'); w.__sInit(cfg({ days: 7, refresh: 'first' }));
    const r1 = w.__sP.row(zp('a', at(0, '01:15'), at(2, '10:00')));
    eq(w.__sJudge(r1, 'zhilian', NOW), '', '首次发布 2 天前，该留');
    eq(r1.pub, at(2, '10:00')); ok(/凌晨/.test(r1.note), '没标凌晨刷新');
    eq(w.__sJudge(w.__sP.row(zp('b', at(0, '02:59'), at(40, '10:00'))), 'zhilian', NOW), '超过天数', '首次发布 40 天前');
  },
  '凌晨刷新设为 first 又没有首次发布时间：算发布时间不明'(S) {
    const { win: w } = load(S, 'zhilian'); w.__sInit(cfg({ days: 7, refresh: 'first' }));
    const p = zp('a', at(0, '00:05')); delete p.firstPublishTime;
    eq(w.__sJudge(w.__sP.row(p), 'zhilian', NOW), '发布时间不明');
  },
  '首次发布超过甲天、不超过乙天：算老岗位'(S) {
    const { win: w } = load(S, 'zhilian'); w.__sInit(cfg({ refresh: 'latest', old: [30, 365] }));
    const j = (n, first, pub) => w.__sJudge(w.__sP.row(zp(n, pub || at(1, '10:00'), first)), 'zhilian', NOW);
    eq(j('a', at(30, '10:00')), '', '首次发布 30 天前还算新');
    eq(j('b', at(31, '10:00')), '老岗位', '31 天前');
    eq(j('c', at(365, '10:00')), '老岗位', '365 天前');
    eq(j('d', at(366, '10:00')), '', '一年以上的照常列');
    eq(j('e', at(2, '10:00'), at(8, '10:00')), '超过天数', '刷新超过 7 天先按天数排');
    const p = zp('f', at(1, '10:00')); p.firstPublishTime = '';
    eq(w.__sJudge(w.__sP.row(p), 'zhilian', NOW), '', '查不到首次发布的按刷新时间留下');
  },
  '没设老岗位范围：不按首次发布筛；Boss 不按首次发布筛'(S) {
    const { win: w } = load(S, 'zhilian'); w.__sInit(cfg({ refresh: 'latest' }));
    eq(w.__sJudge(w.__sP.row(zp('a', at(1, '10:00'), at(100, '10:00'))), 'zhilian', NOW), '');
    eq(w.__sOldNote({ fp: '', st: '' }, NOW), '', '没设范围不写备注');
    const { win: b } = load(S, 'boss'); b.__sInit(cfg({ platform: 'boss', old: [30, 365] }));
    eq(b.__sOldNote({ fp: '', st: '' }, NOW), '', 'Boss 没有首次发布，不写备注');
  },
  '首次发布备注：查不到的、超过乙天的写明'(S) {
    const { win: w } = load(S, 'zhilian'); w.__sInit(cfg({ old: [30, 365] }));
    eq(w.__sOldNote({ fp: '', st: '' }, NOW), '首次发布日期不明');
    ok(/超过 365 天/.test(w.__sOldNote({ fp: at(400, '10:00'), st: '' }, NOW)), '一年以上的没写明');
    eq(w.__sOldNote({ fp: at(10, '10:00'), st: '' }, NOW), '', '一个月内的不用写');
    eq(w.__sOldNote({ fp: '', st: '老岗位' }, NOW), '', '跳过的不写');
  },
  '重贴配置后按新算法重算发布时间；结果行带首次发布备注，头行带老岗位条数'(S) {
    const { win: w } = load(S, 'zhilian'); w.__sInit(cfg({ refresh: 'first' }));
    const r = w.__sP.row(zp('a', at(0, '01:15'), at(40, '10:00')));
    eq(r.pub, at(40, '10:00'), '设为 first 时按首次发布');
    w.__sInit(cfg({ refresh: 'latest', old: [30, 365] })); w.__sMark(r);
    eq(r.pub, at(0, '01:15'), '改成按刷新时间后没重算');
    w.__sRows = { a: { id: 'a', st: '', note: '', fnote: '首次发布日期不明' }, b: { id: 'b', st: '老岗位' }, c: { id: 'c', st: '老岗位' } };
    const t = w.__sText(0);
    ok(t.indexOf('首次发布日期不明') > 0, '结果行没带备注');
    eq(t.split('\n')[0].split('|')[12], '2', '头行老岗位条数');
  },
  '03:00 以后不算凌晨刷新'(S) {
    const { win: w } = load(S, 'zhilian'); w.__sInit(cfg({ days: 7 }));
    const r = w.__sP.row(zp('a', at(0, '03:00'), at(30, '10:00')));
    eq(r.pub, at(0, '03:00')); eq(r.note, '');
    eq(w.__sJudge(r, 'zhilian', NOW), '');
  },
  '翻页停止：最后 20 条里排除凌晨刷新的再看'(S) {
    const { win: w } = load(S, 'zhilian');
    const L = [];
    for (let i = 0; i < 10; i++) L.push(zp('o' + i, at(9, '10:00')));
    for (let i = 0; i < 10; i++) L.push(zp('r' + i, at(0, '01:10'), at(30, '10:00')));
    ok(w.__sZOld(L, 7, NOW), '10 条真实的全超 7 天，应该停');
    ok(!w.__sZOld(L.slice(1), 7, NOW), '真实的不到 10 条，不该停');
    const M = [];
    for (let i = 0; i < 5; i++) M.push(zp('o' + i, at(9, '10:00')));
    for (let i = 0; i < 5; i++) M.push(zp('n' + i, at(1, '10:00')));
    ok(!w.__sZOld(M, 7, NOW), '正好一半超期，不该停');
    M.push(zp('o9', at(9, '10:00')));
    ok(w.__sZOld(M, 7, NOW), '过半超期，应该停');
  },
  '翻页停止：开头夹着很久以前的置顶岗位不停'(S) {
    const { win: w } = load(S, 'zhilian');
    const L = [zp('top1', at(200, '10:00')), zp('top2', at(150, '10:00'))];
    for (let i = 0; i < 20; i++) L.push(zp('n' + i, at(1, '10:00')));
    ok(!w.__sZOld(L, 7, NOW), '尾部都是新的却停了');
  },
  'Boss 没有发布时间，不按天数跳过；只标出此刻在线，不跳过离线'(S) {
    const { win: w } = load(S, 'boss'); w.__sInit(cfg({ platform: 'boss', days: 1 }));
    const off = w.__sP.row(bp('b1'));
    eq(w.__sJudge(off, 'boss', NOW), ''); eq(off.note, '', '离线不该标在线');
    const on = w.__sP.row(Object.assign(bp('b2'), { bossOnline: true }));
    eq(w.__sJudge(on, 'boss', NOW), ''); eq(on.note, 'HR当前在线', 'bossOnline 没标出在线');
  },
  // 不想看的关键词
  '关键词：岗位标题含词就跳过，公司名含词不算'(S) {
    const { win: w } = load(S, 'zhilian'); w.__sInit(cfg({ keywords: ['兼职', 'SALES'] }));
    const r = w.__sP.row(zp('a', at(1, '10:00'), null, '戊己信息有限公司', '运营专员（可兼职）'));
    eq(w.__sJudge(r, 'zhilian', NOW), '关键词', '标题含「兼职」没拦');
    w.__sMark(r); eq(r.kw, '兼职', '没记下命中的词');
    eq(w.__sJudge(w.__sP.row(zp('b', at(1, '10:00'), null, '示例兼职派遣有限公司', '运营专员')), 'zhilian', NOW), '', '公司名含词被拦了');
    eq(w.__sJudge(w.__sP.row(zp('c', at(1, '10:00'), null, null, 'Sales 助理')), 'zhilian', NOW), '关键词', '大小写不同没认出');
    eq(w.__sJudge(w.__sP.row(zp('d', at(1, '10:00'))), 'zhilian', NOW), '', '不含词的被拦了');
  },
  '关键词：不设就不拦，Boss 也照拦'(S) {
    const { win: w } = load(S, 'boss'); w.__sInit(cfg({ platform: 'boss' }));
    eq(w.__sJudge(w.__sP.row(bp('b1', null, '销售专员')), 'boss', NOW), '', '没设词也拦了');
    ok(/ 关键词0个$/.test(w.__sInit(cfg({ platform: 'boss' }))), '装好时没报关键词个数');
    w.__sInit(cfg({ platform: 'boss', keywords: ['销售'] }));
    eq(w.__sJudge(w.__sP.row(bp('b1', null, '销售专员')), 'boss', NOW), '关键词', 'Boss 没按词拦');
    eq(w.__sJudge(w.__sP.row(bp('b2', '甲乙科技', '销售专员')), 'boss', NOW), '关键词');
  },
  // 配置
  '配置没填：页面拒绝开跑'(S) {
    const { win: w } = load(S, 'zhilian');
    ok(/^cfg-bad/.test(w.__sInit(cfg({ days: undefined }))), '没天数也收了');
    ok(/^cfg-bad/.test(w.__sInit(cfg({ days: 0 }))), '天数 0 也收了');
    ok(/^cfg-bad/.test(w.__sInit(cfg({ mode: undefined }))), '没拦法也收了');
    eq(w.__sRun('x'), 'not-ready 先注入', '没装好配置也开跑了');
    ok(/^ready 代码c0 配置v0/.test(w.__sInit(cfg())), '正常配置没收');
  },
  '重贴配置后，已读到的按新黑名单重判'(S) {
    const { win: w } = load(S, 'zhilian'); w.__sInit(cfg());
    w.__sRows = { a: Object.assign(w.__sP.row(zp('a', at(1, '10:00'), null, '甲乙科技有限公司')), {}) };
    w.__sMark(w.__sRows.a); eq(w.__sRows.a.st, '');
    w.__sInit(cfg({ blacklist: [{ company: '甲乙科技', job: '' }] }));
    eq(w.__sRows.a.st, '黑名单', '重贴配置后没重判');
  },
  '列出的岗位带地点（Boss 区·商圈，智联 区·街道）'(S) {
    const b = load(S, 'boss').win; b.__sInit(cfg({ platform: 'boss' }));
    eq(b.__sP.row(Object.assign(bp('b1'), { areaDistrict: '西青区', businessDistrict: '大寺' })).loc, '西青区·大寺', 'Boss 地点不对');
    const z = load(S, 'zhilian').win; z.__sInit(cfg({}));
    eq(z.__sP.row(Object.assign(zp('a', at(1, '10:00')), { cityDistrict: '南开区', streetName: '鞍山西道' })).loc, '南开区·鞍山西道', '智联地点不对');
    eq(z.__sP.row(zp('c', at(1, '10:00'))).loc, '', '列表里没有地点时不该编出来');
  },
  '列出的岗位带经验、学历、招聘人、技能标签（比相近岗位用）'(S) {
    const b = load(S, 'boss').win; b.__sInit(cfg({ platform: 'boss' }));
    const br = b.__sP.row(Object.assign(bp('b1'), { jobExperience: '1-3年', jobDegree: '大专', bossName: '于先生', bossTitle: '招聘者', skills: ['资质审核', '办公软件'] }));
    eq([br.exp, br.deg, br.hr, br.sk, br.desc].join('|'), '1-3年|大专|于先生/招聘者|资质审核、办公软件|', 'Boss 比对字段不对');
    const z = load(S, 'zhilian').win; z.__sInit(cfg({}));
    const zr = z.__sP.row(Object.assign(zp('a', at(1, '10:00')), { workingExp: '1-3年', education: '本科', staffCard: { staffName: '包女士', hrJob: '人事经理' },
      jobSkillTags: [{ name: '内勤管理' }, { value: '办公软件' }], jobDescription: '<p>一、工作职责：</p>\n<p>1. 协助招聘</p>' }));
    eq([zr.exp, zr.deg, zr.hr, zr.sk, zr.desc].join('|'), '1-3年|本科|包女士/人事经理|内勤管理、办公软件|一、工作职责： 1. 协助招聘', '智联比对字段不对');
    const ze = z.__sP.row(zp('c', at(1, '10:00')));
    eq([ze.exp, ze.deg, ze.hr, ze.sk, ze.desc].join('|'), '||||', '列表里没有的不该编出来');
  },
  // 输出
  '结果文字：格式、分段、特殊字符'(S) {
    const { win: w } = load(S, 'zhilian'); w.__sInit(cfg({ blacklist: [{ company: '甲乙', job: '' }], keywords: ['兼职', '销售', '提成'] }));
    w.__sState = { stage: 'done', tag: '标签A', why: '到底', sorted: true, start: '2030-01-09T23:00:00.000Z' };
    w.__sRows = {};
    for (let i = 0; i < 150; i++) { const r = w.__sP.row(zp('n' + i, at(1, '10:00'), null, '戊己|信息=有;限&公司?', '运营@专员\n二')); w.__sMark(r); w.__sRows[r.id] = r; }
    const b = w.__sP.row(zp('b1', at(1, '10:00'), null, '甲乙有限公司')); w.__sMark(b); w.__sRows.b1 = b;
    const o = w.__sP.row(zp('o1', at(30, '10:00'))); w.__sMark(o); w.__sRows.o1 = o;
    for (const [id, job] of [['k1', '销售代表'], ['k2', '运营（兼职）'], ['k3', '兼职文员']]) { const r = w.__sP.row(zp(id, at(1, '10:00'), null, null, job)); w.__sMark(r); w.__sRows[id] = r; }
    const t1 = w.__sText(0), t2 = w.__sText(1);
    eq(t1.split('\n')[0], '@@H|zhilian|标签A|到底|最新|7|company|155|150|1|1|0|0|3|兼职:2,销售:1|0|0||c0|v0|2030-01-09T23:00:00.000Z|1|2', '头行不对');
    eq(t1.split('\n').filter(l => l.startsWith('@@R')).length, 100, '第一段应 100 行');
    ok(t1.endsWith('@@E|1|2|100'), '第一段结尾行不对');
    ok(t2.includes('@@B|b1|甲乙有限公司|') && t2.endsWith('@@E|2|2|51'), '第二段应有 50 行留下的 + 1 行黑名单');
    ok(!/[=;&?]/.test(t1 + t2), '输出里带了 = ; & ?');
    eq(t1.split('\n')[1].split('|').length, 13, '字段数不对（地点、经验等没输出，或字段里的 | 没换掉）');
    ok(!t1.includes('o1') && !(t1 + t2).includes('k1'), '超过天数、关键词跳过的不该逐条列');
  },
  // 翻页主循环
  async '智联按最新：翻到超过 N 天就停'(S) {
    const p1 = [], p2 = [], p3 = [];
    for (let i = 0; i < 20; i++) p1.push(zp('a' + i, at(1, '10:00')));
    for (let i = 0; i < 20; i++) p2.push(zp('b' + i, at(10, '10:00')));
    for (let i = 0; i < 20; i++) p3.push(zp('c' + i, at(12, '10:00')));
    const { win: w } = load(S, 'zhilian', [p1, p2, p3]); w.__sInit(cfg());
    eq(w.__sRun(), 'started'); await settle(w);
    eq(w.__sState.why, '超过7天'); ok(w.__sState.sorted, '没切到最新');
    const c = w.__sCount(); eq(c.留, 20); eq(c.超过天数, 20, '应该在第 2 屏停下');
  },
  async '智联没切到最新：不按天数停，翻到底'(S) {
    const p1 = [], p2 = [];
    for (let i = 0; i < 20; i++) p1.push(zp('a' + i, at(10, '10:00')));
    for (let i = 0; i < 20; i++) p2.push(zp('b' + i, at(1, '10:00')));
    const { win: w } = load(S, 'zhilian', [p1, p2], { noSort: true }); w.__sInit(cfg());
    w.__sRun(); await settle(w);
    eq(w.__sState.why, '到底'); ok(!w.__sState.sorted);
    eq(w.__sCount().留, 20, '第 2 屏新的没读到');
  },
  async 'Boss 翻到 hasMore=false，黑名单照拦'(S) {
    const { win: w, tabs } = load(S, 'boss', [[bp('a1', '甲乙科技'), bp('a2')], [bp('b1'), bp('b2', '示例市甲乙科技有限公司')]], { tabs: ['推荐', '运营专员(示例)'] });
    w.__sInit(cfg({ platform: 'boss', blacklist: [{ company: '甲乙科技', job: '' }] }));
    eq(w.__sRun('运营专员'), 'started'); await settle(w);
    eq(tabs[1].clicked, 1, '没点对标签');
    eq(w.__sState.why, '到底');
    const c = w.__sCount(); eq(c.留, 2); eq(c.黑名单, 2);
  },
  async '碰到安全验证就停'(S) {
    const { win: w } = load(S, 'boss', [[bp('a1')], [bp('b1')]], { title: '安全验证' }); w.__sInit(cfg({ platform: 'boss' }));
    w.__sRun(); await settle(w);
    eq(w.__sState.why, '安全验证');
  },
  async '手动停：已读到的留着，写明没翻完'(S) {
    const { win: w } = load(S, 'boss', [[bp('a1')], [bp('b1')], [bp('c1')]]); w.__sInit(cfg({ platform: 'boss' }));
    w.__sRun(); eq(w.__sStop(), 'stopping'); await settle(w);
    ok(/没翻完/.test(w.__sState.why), '停的原因没写没翻完：' + w.__sState.why);
    ok(w.__sCount().留 >= 1 && w.__sCount().留 < 3, '应该只读到一部分');
    eq(w.__sStop(), 'not-running');
  },
  '读标签名：去掉空的、重复的，Boss 去掉末尾城市括号'(S) {
    const b = load(S, 'boss', [[]], { tabs: ['推荐', ' 行政专员/助理(天津) ', '', '人力资源专员/助理（天津）', '推荐'] }).win;
    eq(JSON.stringify(b.__sTags()), JSON.stringify(['推荐', '行政专员/助理', '人力资源专员/助理']), 'Boss 标签名不对');
    const z = load(S, 'zhilian', [[]], { tabs: ['行政专员', '', '人事专员(天津)'] }).win;
    eq(JSON.stringify(z.__sTags()), JSON.stringify(['行政专员', '人事专员(天津)']), '智联标签名要原样（它按全名对）');
  },
  '登录了没有：Boss'(S) {
    const L = o => load(S, 'boss', [[bp('a1')]], o).win.__sLogin();
    eq(L({ bossUser: { hasLoadedUser: true, userInfo: { userId: 1 } } }), 'ok', '登录了');
    eq(L({ bossUser: { hasLoadedUser: true, userInfo: {} } }), '没登录', '用户信息加载完了没有编号');
    eq(L({ bossUser: { hasLoadedUser: false, userInfo: null } }), '还在加载', '还没加载完不该算没登录');
    eq(L({}), '还在加载', '页面数据还没出来不该算没登录');
    eq(L({ path: '/web/user/' }), '没登录', '跳到了登录页');
    eq(load(S, 'boss', [[bp('a1')]], { bossUser: { hasLoadedUser: true, userInfo: {} } }).win.__sP.problem(), '没登录', '扫描中掉线没停');
  },
  '登录了没有：智联'(S) {
    const L = o => load(S, 'zhilian', [[zp('a', at(1, '10:00'))]], o).win.__sLogin();
    eq(L({ user: { userId: 1 } }), 'ok', '登录了');
    eq(L({ user: {}, bodyText: '筛选 全部 最新 登录后可查看专属职位推荐 去登录' }), '没登录', '页面写着登录后可查看');
    eq(L({ user: {} }), '还在加载', '还没加载完不该算没登录');
    eq(L({ host: 'passport.zhaopin.com' }), '没登录', '跳到了登录页');
    eq(load(S, 'zhilian', [[]], { user: {}, bodyText: '去登录' }).win.__sP.problem(), '没登录', '扫描中掉线没停');
  },
  async '没登录就停：不点标签、不翻、不留岗位'(S) {
    const { win: w, tabs } = load(S, 'boss', [[bp('a1')], [bp('b1')]], { tabs: ['推荐'], bossUser: { hasLoadedUser: true, userInfo: {} } });
    w.__sInit(cfg({ platform: 'boss' }));
    eq(w.__sRun('推荐'), 'started'); await settle(w);
    eq(w.__sState.why, '没登录'); eq(tabs[0].clicked, 0, '没登录还点了标签'); eq(Object.keys(w.__sRows).length, 0, '没登录还读了岗位');
  },
  async '找不到标签就停，不乱跑'(S) {
    const { win: w } = load(S, 'zhilian', [[zp('a', at(1, '10:00'))]], { tabs: ['标签A'] }); w.__sInit(cfg());
    w.__sRun('标签B'); await settle(w);
    ok(/找不到标签/.test(w.__sState.why)); eq(Object.keys(w.__sRows).length, 0);
  },
  async '智联切标签：选中了才扫，点了没切过去就停'(S) {
    const a = load(S, 'zhilian', [[zp('a', at(1, '10:00'))], [zp('b', at(2, '10:00'))]], { tabs: ['标签A', '标签B'] });
    a.win.__sInit(cfg());
    eq(a.win.__sRun('标签B'), 'started'); await settle(a.win);
    eq(a.tabs[1].clicked, 1, '没点对标签'); eq(a.win.__sState.why, '到底', '切过去了应该照常扫');
    eq(a.win.__sCount().留, 2, '切过去了没读岗位');
    const b = load(S, 'zhilian', [[zp('a', at(1, '10:00'))], [zp('b', at(2, '10:00'))]], { tabs: ['标签A', '标签B'], tabStuck: true });
    b.win.__sInit(cfg());
    b.win.__sRun('标签B'); await settle(b.win);
    eq(b.tabs[1].clicked, 1);
    ok(/找不到标签/.test(b.win.__sState.why), '点了没切过去还往下扫：' + b.win.__sState.why);
    eq(Object.keys(b.win.__sRows).length, 0, '没切过去还读了岗位（读的是上一个标签的列表）');
  },
  async 'Boss 切标签：选中了才扫，点了没切过去就停'(S) {
    const a = load(S, 'boss', [[bp('a1')], [bp('b1')]], { tabs: ['推荐', '销售助理(天津)'] });
    a.win.__sInit(cfg({ platform: 'boss' }));
    eq(a.win.__sRun('销售助理'), 'started'); await settle(a.win);
    eq(a.tabs[1].clicked, 1, '没点对标签'); eq(a.win.__sState.why, '到底', '切过去了应该照常扫');
    eq(a.win.__sCount().留, 2, '切过去了没读岗位');
    const b = load(S, 'boss', [[bp('a1')], [bp('b1')]], { tabs: ['推荐', '销售助理(天津)'], tabStuck: true });
    b.win.__sInit(cfg({ platform: 'boss' }));
    b.win.__sRun('销售助理'); await settle(b.win);
    eq(b.tabs[1].clicked, 1);
    ok(/找不到标签/.test(b.win.__sState.why), '点了没切过去还往下扫：' + b.win.__sState.why);
    eq(Object.keys(b.win.__sRows).length, 0, '没切过去还读了岗位（读的是上一个标签的列表）');
    // class 里只是含有 active 这几个字母（如 inactive）不算选中
    const c = load(S, 'boss', [[bp('a1')], [bp('b1')]], { tabs: ['推荐', '销售助理(天津)'], tabStuck: true, tabClass: 'expect-item inactive' });
    c.win.__sInit(cfg({ platform: 'boss' }));
    c.win.__sRun('销售助理'); await settle(c.win);
    ok(/找不到标签/.test(c.win.__sState.why), 'inactive 被当成选中了：' + c.win.__sState.why);
  },
  async '状态行：Boss 不写按没按最新，智联写'(S) {
    const b = load(S, 'boss', [[bp('a1')]]).win; b.__sInit(cfg({ platform: 'boss' }));
    b.__sRun(); await settle(b);
    ok(!/按最新/.test(b.__sStatus()), 'Boss 没有「最新」排序，不该写：' + b.__sStatus());
    eq(b.__sStatus().split(' / ')[1], '到底', '第二段应是停的原因');
    const z = load(S, 'zhilian', [[zp('a', at(1, '10:00'))]]).win; z.__sInit(cfg());
    z.__sRun(); await settle(z);
    ok(/已按最新/.test(z.__sStatus()), '智联要写按没按最新：' + z.__sStatus());
    const n = load(S, 'zhilian', [[zp('a', at(1, '10:00'))]], { noSort: true }).win; n.__sInit(cfg());
    n.__sRun(); await settle(n);
    ok(/没按最新/.test(n.__sStatus()), '智联没切到最新要写出来：' + n.__sStatus());
  },
  async '看过的页面先按编号跳过，头行带看过的条数和版本'(S) {
    const { win: w } = load(S, 'boss', [[bp('a1'), bp('a2', '甲乙科技'), bp('a3'), bp('a4', null, '兼职文员')]]);
    const seen = w.__sCode('a1') + w.__sCode('a2') + w.__sCode('a4');
    ok(/^[0-9A-Za-z_-]{7}$/.test(w.__sCode('a1')), '短码不是 7 个字符：' + w.__sCode('a1'));
    ok(w.__sCode('a1') !== w.__sCode('a3') && w.__sCode('ab') !== w.__sCode('ba'), '不同编号短码一样了');
    // 和 jobscan.py 的 seen_code 算出来的一样（test_cli.py 里钉的是同两个值）
    eq(w.__sCode('abc123XYZ'), 'mshXG9D', '短码算法和 jobscan.py 对不上'); eq(w.__sCode('中文编号'), '3sj18ez', '非英文编号短码对不上');
    const r = w.__sInit(cfg({ platform: 'boss', blacklist: [{ company: '甲乙科技', job: '' }], keywords: ['兼职'], seen, seenn: 3, seenv: 'sv1' }));
    ok(/^ready 代码c0 配置v0 看过3条 /.test(r), '装好时没报看过几条：' + r);
    w.__sRun(); await settle(w);
    const c = w.__sCount();
    eq(c.看过, 1, '看过的没跳过'); eq(c.黑名单, 1, '黑名单要排在看过前面'); eq(c.关键词, 1, '关键词要排在看过前面'); eq(c.留, 1);
    w.__sState.start = 'T0';
    const head = w.__sText(0).split('\n')[0].split('|');
    eq(head.slice(14, 18).join('|'), '兼职:1|1|3|sv1', '头行没带看过跳过的条数、页面用的看过记录条数和版本');
    ok(!w.__sText(0).includes('|a1|'), '看过的不该逐条列');
    ok(w.__sText(0).includes('@@S|' + w.__sCode('a1')), '看过的没回传 @@S 短码心跳');
    ok(/看过1/.test(w.__sStatus()), '状态行没写看过几条');
    // 智联看过的 @@S 心跳要带原始刷新时间戳（即使设成 refresh=first 也带）
    const { win: zw } = load(S, 'zhilian', [[zp('z1', at(0, '01:15'), at(2, '10:00'))]]);
    zw.__sInit(cfg({ platform: 'zhilian', refresh: 'first', seen: zw.__sCode('z1'), seenn: 1, seenv: 'zv1' }));
    zw.__sRun(); await settle(zw);
    const ztxt = zw.__sText(0);
    ok(ztxt.includes('@@S|' + zw.__sCode('z1') + '~' + days(0) + '_01:15'), '智联 @@S 没带原始刷新时间戳：' + ztxt);
    // 看过的记录清空后只重贴配置：已读到的按新记录重判，那条又列出来
    w.__sInit(cfg({ platform: 'boss', blacklist: [{ company: '甲乙科技', job: '' }], keywords: ['兼职'] }));
    eq(w.__sCount().留, 2, '重贴配置后看过的没重判');
    ok(!w.__sJudge({ id: '', co: '戊己', job: '运营' }, 'boss'), '没有编号的不该当看过');
  },
  async '等扫描：跑完马上返回，没跑完最多看 8 次'(S) {
    const { win: w } = load(S, 'boss', [[bp('a1')]]); w.__sInit(cfg({ platform: 'boss' }));
    let n = 0; w.setTimeout = f => { n++; setImmediate(f); };
    w.__sState = { stage: 'done', why: '到底' };
    ok(/^done \/ 到底/.test(await w.__sWait()), '应返回状态行'); eq(n, 0, '跑完了还在等');
    w.__sState = { stage: 'load', why: '' };
    await w.__sWait(); eq(n, 8, '没跑完应看 8 次（约 40 秒）就返回');
  },
  '别名组：品牌简称和工商全称经确认后互相认出'(S) {
    const { win: w } = load(S, 'boss');
    w.__sInit(cfg({ platform: 'boss', blacklist: [{ company: '甲乙品牌', job: '' }], aliases: [['甲乙品牌', '示例市全称乙信息有限公司']] }));
    ok(w.__sBlock('示例市全称乙信息有限公司', '行政专员'), '别名组里的全称没拦住');
    ok(!w.__sBlock('丙丁商贸', '行政专员'), '别名组误拦了无关公司');
  },
  async '按标签屏蔽关键词：只拦指定标签，不拦其他标签'(S) {
    const a = load(S, 'boss', [[bp('a1', '戊己', '市场推广专员'), bp('a2', '戊己', '行政专员')]], { tabs: ['行政', '运营'] });
    a.win.__sInit(cfg({ platform: 'boss', tag_keywords: { '行政': ['推广'] } }));
    a.win.__sRun('行政'); await settle(a.win);
    eq(a.win.__sCount().关键词, 1, '指定标签下没按标签词跳过');
    eq(a.win.__sCount().留, 1);
    const b = load(S, 'boss', [[bp('b1', '戊己', '市场推广专员'), bp('b2', '戊己', '行政专员')]], { tabs: ['行政', '运营'] });
    b.win.__sInit(cfg({ platform: 'boss', tag_keywords: { '行政': ['推广'] } }));
    b.win.__sRun('运营'); await settle(b.win);
    eq(b.win.__sCount().关键词, 0, '别的标签被误拦了');
    eq(b.win.__sCount().留, 2);
  },
};

// 错误写法：[说明, 文件, 原文, 改成]。每种都必须让上面至少一条用例不过。
const MUTANTS = [
  ['页面别名比对不起作用', 'common', '      if (grp.some(x => window.__sCoEq(a, x, true)) && grp.some(x => window.__sCoEq(b, x, true))) return true;\n', ''],
  ['页面不看按标签屏蔽的关键词', 'common', 'for (const w of (cfg.keywords || []).concat((cfg.tag_keywords || {})[tag] || [])) {', 'for (const w of cfg.keywords || []) {'],
  ['每次问时没写岗位的也只按岗位拦', 'common', "    if (cfg.mode === 'company' || (cfg.mode === 'ask' && !b.job)) return b;\n", "    if (cfg.mode === 'company') return b;\n"],
  ['页面不认每次问的拦法', 'common', " && cfg.mode !== 'ask') return 'cfg-bad", ") return 'cfg-bad"],
  ['拦法不分公司还是公司+岗位', 'common', "    if (cfg.mode === 'company' || (cfg.mode === 'ask' && !b.job)) return b;\n", '    return b;\n'],
  ['不去掉截断的省略号', 'common', ".replace(/(\\.{2,}|…+)$/, '')", ''],
  ['公司名只认完全一样（两个平台互相拦不住）', 'common', '  if (a === b) return true;\n', '  return a === b;\n'],
  ['公司名短的在长的里面就算（不看前面是不是地名）', 'common', "    if (i === 0 || /^([一-龥]{2,3}(省|市|自治区|区|县)?){1,2}$/.test(l.slice(0, i))) return true;", '    return true;'],
  ['地名前缀不认区县（天津市滨海新区这类认不出）', 'common', "/^([一-龥]{2,3}(省|市|自治区|区|县)?){1,2}$/", "/^([一-龥]{2,3}(省|市|自治区)?){1,2}$/"],
  ['岗位名不去福利后缀（Boss 期望标签同一岗位拦不住）', 'common', "  while (window.__sJobTail.test(s)) s = s.replace(window.__sJobTail, '$1');\n", ''],
  ['福利后缀横杠后面全去掉', 'common', "window.__sJobTail = /(.)[-—](?:[+＋]?(?:(?:周末)?双休|[五六]险一金|五险|出差|包吃住|包吃|包住|包餐|无经验|日结|上一休一))+$/;", 'window.__sJobTail = /(.)[-—].+$/;'],
  ['Boss 不带地点', 'boss', "loc: [p.areaDistrict, p.businessDistrict].filter(Boolean).join('·')", "loc: ''"],
  ['智联不带地点', 'zhilian', "loc: [p.cityDistrict, p.streetName].filter(Boolean).join('·')", "loc: ''"],
  ['结果行不输出地点', 'common', '[r.id, r.co, r.job, r.sal, r.pub, r.loc, r.exp', '[r.id, r.co, r.job, r.sal, r.pub, r.exp'],
  ['结果行不输出招聘人', 'common', 'r.deg, r.hr, r.sk', 'r.deg, r.sk'],
  ['Boss 不带招聘人', 'boss', "hr: [p.bossName, p.bossTitle].filter(Boolean).join('/')", "hr: ''"],
  ['Boss 不标当前在线', 'boss', "note: p.bossOnline ? 'HR当前在线' : ''", "note: ''"],
  ['智联不带经验', 'zhilian', "exp: p.workingExp || ''", "exp: ''"],
  ['智联描述不去标签', 'zhilian', ".replace(/<[^>]+>/g, ' ').replace(/\\s+/g, ' ')", ""],
  ['标签名不去空的', 'common', '.filter(Boolean))];', '))];'],
  ['Boss 标签名不去城市括号', 'boss', "a.expect-item', true)", "a.expect-item', false)"],
  ['智联标签名也去括号（按全名对不上）', 'zhilian', "'.intention-tabs__text', false)", "'.intention-tabs__text', true)"],
  ['扫描前不查登录', 'common', "      if (P.login() === '没登录') { S.why = '没登录'; return; }  // 没登录就停，不点标签、不翻\n", ''],
  ['Boss 扫描中不查登录', 'boss', "    if (window.__sP.login() === '没登录') return '没登录';\n", ''],
  ['智联扫描中不查登录', 'zhilian', "    if (window.__sP.login() === '没登录') return '没登录';\n", ''],
  ['Boss 用户信息没加载完就当没登录', 'boss', "    return st && st.hasLoadedUser ? '没登录' : '还在加载';", "    return '没登录';"],
  ['Boss 不认登录页', 'boss', "    if (location.pathname.indexOf('/web/user') === 0) return '没登录';\n", ''],
  ['智联不认「登录后可查看」', 'zhilian', '/登录后可查看|去登录/', '/请先登录后再访问/'],
  ['智联不认登录页', 'zhilian', "    if (/^passport\\./.test(location.hostname)) return '没登录';\n", ''],
  ['天数边界差一天', 'common', "  if (a > cfg.days) return '超过天数';", "  if (a >= cfg.days) return '超过天数';"],
  ['旧写法：天数写死 7 天', 'common', "  if (a > cfg.days) return '超过天数';", "  if (a > 7) return '超过天数';"],
  ['凌晨刷新不处理', 'common', "window.__sRefresh = t => /\\s0[0-2]:\\d\\d/.test(String(t || ''));", 'window.__sRefresh = t => false;'],
  ['凌晨刷新的整条当不明（不看首次发布时间）', 'zhilian', "  if (f) return { pub: f, note: '凌晨自动刷新，按首次发布' };\n", ''],
  ['老岗位边界：甲天当天也算老', 'common', 'f > o[0] && f <= o[1]', 'f >= o[0] && f <= o[1]'],
  ['一年以上的也算老岗位', 'common', 'f > o[0] && f <= o[1]', 'f > o[0]'],
  ['刷新按最近一次算不起作用', 'zhilian', " || (window.__sCfg || {}).refresh !== 'first'", ''],
  ['改回按首次发布（refresh=first）不起作用', 'zhilian', "if (!window.__sRefresh(t) || (window.__sCfg || {}).refresh !== 'first')", 'if (true)'],
  ['看过的不回传 @@S 短码心跳', 'common', "for (const r of Object.values(window.__sRows)) if (r.st === '看过' && r.id) seen.push(window.__sSeenTok(r));\n", ''],
  ['智联 @@S 心跳不带刷新时间戳', 'common', "if ((window.__sP || {}).platform !== 'zhilian') return code;\n", 'if (true) return code;\n'],
  ['重贴配置不重算发布时间', 'common', '  if (P.repub) Object.assign(r, P.repub(r));', ''],
  ['结果行不带首次发布备注', 'common', "[r.note, r.fnote].filter(Boolean).join('；')", 'r.note'],
  ['查不到首次发布不标', 'common', "  if (f === null) return '首次发布日期不明';\n", ''],
  ['头行不带老岗位条数', 'common', 'c.发布时间不明, c.老岗位, c.关键词', 'c.发布时间不明, 0, c.关键词'],
  ['停的判断没排除凌晨刷新', 'zhilian', '  const real = L.slice(-20).filter(p => !window.__sRefresh(p.publishTime));', '  const real = L.slice(-20);'],
  ['配置没填也照跑', 'common', "  if (!(Number.isInteger(days) && days >= 1)) return 'cfg-bad 天数没设，先问使用者';\n", ''],
  ['Boss 也按天数筛', 'common', "  if (platform !== 'boss') {", '  if (true) {'],
  ['关键词不拦', 'common', "  if (window.__sKw(row.job)) return '关键词';\n", ''],
  ['关键词连公司名也查', 'common', "if (window.__sKw(row.job)) return", 'if (window.__sKw(row.co + row.job)) return'],
  ['Boss 不查关键词', 'common', "  if (window.__sKw(row.job)) return '关键词';\n", "  if (platform !== 'boss' && window.__sKw(row.job)) return '关键词';\n"],
  ['关键词不分大小写没做', 'common', "  const t = String(job || '').replace(/\\s/g, '').toLowerCase();", "  const t = String(job || '').replace(/\\s/g, '');"],
  ['头行不按词计数', 'common', "c.关键词, window.__sKwText(), c.看过", "c.关键词, '', c.看过"],
  ['头行时间不是扫描开始时间（同一次扫描认不出）', 'common', "cfg.cfgv, S.start || '', k + 1", 'cfg.cfgv, new Date().toISOString(), k + 1'],
  ['没切到最新也按天数停', 'common', "if (P.platform === 'zhilian' && S.sorted && P.oldEnough(", "if (P.platform === 'zhilian' && P.oldEnough("],
  ['重贴配置不重判', 'common', '  for (const r of Object.values(window.__sRows || {})) window.__sMark(r);\n', ''],
  ['手动停了不说没翻完', 'common', "S.why = '手动停了（没翻完）'", "S.why = '到底'"],
  ['碰到验证不停', 'boss', "    if (/验证/.test(document.title)) return '安全验证';\n", ''],
  ['智联切标签不核对选中（点了没切过去也往下扫）', 'zhilian', '    return active();\n', '    return true;\n'],
  ['Boss 切标签不核对选中（点了没切过去也往下扫）', 'boss', '    return active();\n', '    return true;\n'],
  ['Boss 选中标记认成包含 active 的任何 class', 'boss', '/(^|\\s)active(\\s|$)/', '/active/'],
  ['Boss 状态行也写没按最新', 'common', "  if (P.platform === 'zhilian') a.push(", '  if (true) a.push('],
  ['看过的页面不跳过', 'common', "  if (row.id && window.__sSeen && window.__sSeen.has(window.__sCode(row.id))) return '看过';\n", ''],
  ['看过的排在黑名单前面', 'common', "  if (window.__sBlock(row.co, row.job)) return '黑名单';\n",
    "  if (row.id && window.__sSeen && window.__sSeen.has(window.__sCode(row.id))) return '看过';\n  if (window.__sBlock(row.co, row.job)) return '黑名单';\n"],
  ['头行不带看过跳过的条数', 'common', 'window.__sKwText(), c.看过, cfg.seenn', 'window.__sKwText(), 0, cfg.seenn'],
  ['头行不带页面用的看过记录版本', 'common', "cfg.seenn || 0, cfg.seenv || ''", "cfg.seenn || 0, ''"],
  ['短码只用一遍哈希（位数不够，容易撞）', 'common', " * 1024 + (window.__sFnv('#' + s, 2166136261) & 1023)", ''],
  ['等扫描不看跑完没有，固定等满', 'common', " && window.__sState && window.__sState.stage !== 'done'; i++) await ssleep(5000);", '; i++) await ssleep(5000);'],
];

async function runCases(S) {
  const errs = [];
  for (const [name, fn] of Object.entries(CASES)) {
    try { await fn(S); } catch (e) { errs.push(name + '：' + String(e && e.message).slice(0, 200)); }
  }
  return errs;
}

(async () => {
  const S = { common: read('common.js'), boss: read('boss.js'), zhilian: read('zhilian.js') };
  const out = (await runCases(S)).map(e => '[现在的写法] ' + e);
  for (const [desc, file, from, to] of MUTANTS) {
    if (S[file].split(from).length !== 2) { out.push('[反例] 「' + desc + '」的原文在 ' + file + '.js 里找不到或不唯一，用例跟代码对不上了，改代码要同步改这里'); continue; }
    const M = Object.assign({}, S, { [file]: S[file].replace(from, to) });
    if (!(await runCases(M)).length) out.push('[反例] 改成「' + desc + '」用例还全过，说明用例抓不住这种错');
  }
  if (out.length) { console.log(out.join('\n')); process.exit(1); }
  console.log('页面脚本用例全过（' + Object.keys(CASES).length + ' 条，含 ' + MUTANTS.length + ' 种错误写法反例）');
})();
