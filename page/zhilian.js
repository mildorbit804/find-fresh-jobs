// 智联招聘 职位列表页（/jobs/?pageMode=recommend 或搜索结果）的平台适配。
// 页面是 Vue + Vuex：document.querySelector('#root').__vue__.$store.state
//   positionList：当前列表（number 岗位编号，publishTime 发布时间，firstPublishTime 首次发布时间）
//   hasMore：还能不能加载
// 智联每天凌晨 00:00-02:59 会自动刷新一批老岗位的 publishTime，所以：
//   ①判断一条岗位几天前发布：publishTime 落在凌晨的，改用 firstPublishTime；没有就算「发布时间不明」；
//   ②判断列表是不是已经翻到 N 天以前：不看凌晨刷新的那些，只看列表最后 20 条里其余的。

window.__sZSt = () => { const r = document.querySelector('#root'); return r && r.__vue__ && r.__vue__.$store && r.__vue__.$store.state; };
// 这条岗位真正的发布时间和备注
window.__sZPub = p => {
  const t = p.publishTime || '';
  if (!window.__sRefresh(t)) return { pub: t, note: '' };
  const f = p.firstPublishTime || '';
  if (f) return { pub: f, note: '凌晨自动刷新，按首次发布' };
  return { pub: '', note: '凌晨自动刷新，查不到首次发布' };
};
// 列表里会夹几条很久以前的置顶岗位，所以看最后 20 条：去掉凌晨刷新的还剩至少 10 条，并且超过一半已经超过 N 天，才算翻到头。
// 按列表自己的排序键 publishTime 判断（「最新」就是按它排的）。
window.__sZOld = (L, days, now) => {
  const real = L.slice(-20).filter(p => !window.__sRefresh(p.publishTime));
  if (real.length < 10) return false;
  const old = real.filter(p => { const a = window.__sAge(p.publishTime, now); return a !== null && a > days; }).length;
  return old * 2 > real.length;
};
window.__sP = {
  platform: 'zhilian',
  list: () => { const st = window.__sZSt(); return (st && st.positionList) || []; },
  // 经验、学历、招聘人、技能标签、描述开头给同公司标题相近的岗位比异同用；列表里的 jobDescription 只有开头七十来个字
  row: p => {
    const z = window.__sZPub(p), s = p.staffCard || {};
    return { id: String(p.number || ''), co: p.companyName, job: p.name, sal: p.salary60, pub: z.pub, loc: [p.cityDistrict, p.streetName].filter(Boolean).join('·'),
      exp: p.workingExp || '', deg: p.education || '', hr: [s.staffName, s.hrJob].filter(Boolean).join('/'),
      sk: (p.jobSkillTags || []).map(t => (t && (t.name || t.value)) || t).filter(x => typeof x === 'string').slice(0, 8).join('、'),
      desc: String(p.jobDescription || '').replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim().slice(0, 80), raw: p.publishTime, note: z.note };
  },
  hasMore: () => { const st = window.__sZSt(); return !!(st && st.hasMore); },
  // 登录了没有：页面数据里有用户编号就是登录了；页面写着「登录后可查看」「去登录」，或者跳到了登录页（passport），就是没登录
  login: () => {
    if (/^passport\./.test(location.hostname)) return '没登录';
    const st = window.__sZSt(), u = st && st.user;
    if (u && (u.userId || u.Id)) return 'ok';
    return /登录后可查看|去登录/.test((document.body && document.body.innerText) || '') ? '没登录' : '还在加载';
  },
  problem: () => {
    if (/验证/.test(document.title)) return '安全验证';
    if (window.__sP.login() === '没登录') return '没登录';
    if (!/zhaopin\.com$/.test(location.hostname) || location.pathname.indexOf('/jobs') !== 0) return '离开了列表页（可能要登录或验证）:' + location.pathname;
    if (!window.__sZSt()) return '读不到列表（可能没登录或页面改版）';
    return '';
  },
  // 滚到底等列表变长；没加载出来就来回滚再等，最多 5 次
  more: async () => {
    const st = window.__sZSt(), before = st.positionList.length;
    for (let a = 0; a < 5; a++) {
      const dh = document.documentElement.scrollHeight;
      window.scrollTo(0, Math.max(0, dh - innerHeight - 600)); await ssleep(600);
      window.scrollTo(0, dh);
      const panel = document.querySelector('.job-list-panel'); if (panel) panel.scrollTop = panel.scrollHeight;
      window.dispatchEvent(new Event('scroll'));
      for (let t = 0; t < 50; t++) { if (st.positionList.length > before) return true; await ssleep(300); }
    }
    return false;
  },
  // 顶部求职期望标签。点完核对这个标签真的选中了（外层多出 intention-tabs__item--active），
  // 没选中返回 false，当成找不到标签停下，免得把上一个标签再扫一遍
  switchTag: async name => {
    const el = [...document.querySelectorAll('.intention-tabs__text')].find(e => e.innerText.trim() === name);
    if (!el) return false;
    const active = () => !!(el.parentElement && /intention-tabs__item--active/.test(el.parentElement.className));
    const st = window.__sZSt(), first = st.positionList[0] && st.positionList[0].number;
    el.click();
    for (let t = 0; t < 40; t++) { await ssleep(300); if (active() && st.positionList[0] && st.positionList[0].number !== first) break; }
    await ssleep(2000);
    return active();
  },
  tags: () => window.__sTagNames('.intention-tabs__text', false),
  // 点「最新」，返回这个按钮是不是已经选中。没选中就不按天数停，翻到底。
  sortNewest: async () => {
    const vis = () => [...document.querySelectorAll('button.jobs-list-sort-placeholder__item')].find(e => e.innerText.trim() === '最新' && e.getBoundingClientRect().y > 0);
    const on = () => { const b = vis(); return !!(b && /--active/.test(b.className)); };
    if (on()) return true;
    const b = vis(); if (!b) return false;
    const st = window.__sZSt(), first = st.positionList[0] && st.positionList[0].number;
    b.click();
    for (let t = 0; t < 40; t++) { await ssleep(300); if (st.positionList[0] && st.positionList[0].number !== first) break; }
    await ssleep(2000);
    window.scrollTo(0, 0);
    return on();
  },
  oldEnough: (L, days) => window.__sZOld(L, days),
  link: id => 'https://www.zhaopin.com/jobdetail/' + id + '.htm',
};
