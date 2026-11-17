// Boss直聘 职位列表页（/web/geek/jobs）的平台适配。
// 页面是 Vue 2：.job-detail-box 往上找有 jobList 的组件，jobList 是当前列表，hasMore 是还能不能加载。
// Boss 网页不公开岗位发布时间（列表和详情都没有），所以这里不按天数筛，翻到 hasMore=false 为止。
// 红线：不开 CDP Runtime（不用 read_console_messages），不 fetch /wapi/zpgeek/job/detail.json，不点开岗位卡片。

window.__sBossVm = () => {
  let el = document.querySelector('.job-detail-box') || document.querySelector('.job-card-box');
  for (let k = 0; el && k < 10; k++, el = el.parentElement) if (el.__vue__ && el.__vue__.jobList) return el.__vue__;
  return null;
};
window.__sP = {
  platform: 'boss',
  list: () => { const vm = window.__sBossVm(); return (vm && vm.jobList) || []; },
  // 地点只有区和商圈（列表数据就这两项）；门牌地址、岗位描述都在岗位详情里，不点开。
  // 经验、学历、招聘人、技能标签给同公司标题相近的岗位比异同用
  row: p => ({ id: p.encryptJobId, co: p.brandName, job: p.jobName, sal: p.salaryDesc, pub: '', loc: [p.areaDistrict, p.businessDistrict].filter(Boolean).join('·'),
    exp: p.jobExperience || '', deg: p.jobDegree || '', hr: [p.bossName, p.bossTitle].filter(Boolean).join('/'), sk: (p.skills || []).slice(0, 8).join('、'), desc: '', note: p.bossOnline ? 'HR当前在线' : '' }),
  hasMore: () => { const vm = window.__sBossVm(); return !!(vm && vm.hasMore); },
  // 登录了没有：页面数据里有用户编号就是登录了；用户信息加载完了还没有编号，或者跳到了登录页（/web/user），就是没登录
  login: () => {
    if (location.pathname.indexOf('/web/user') === 0) return '没登录';
    const w = document.querySelector('#wrap'), st = w && w.__vue__ && w.__vue__.$store && w.__vue__.$store.state;
    if (st && st.userInfo && st.userInfo.userId) return 'ok';
    return st && st.hasLoadedUser ? '没登录' : '还在加载';
  },
  problem: () => {
    if (/验证/.test(document.title)) return '安全验证';
    if (window.__sP.login() === '没登录') return '没登录';
    if (location.pathname.indexOf('/web/geek/jobs') < 0) return '离开了列表页（可能要登录或验证）:' + location.pathname;
    if (!window.__sBossVm()) return '读不到列表（可能没登录或页面改版）';
    return '';
  },
  // 滚到底等列表变长；没加载出来就上下抖一下再滚，最多 5 次
  more: async () => {
    const vm = window.__sBossVm(), n = vm.jobList.length;
    for (let r = 0; r < 5; r++) {
      window.scrollTo(0, Math.max(0, document.body.scrollHeight - 900 - r * 300)); await ssleep(600);
      window.scrollTo(0, document.body.scrollHeight);
      for (let t = 0; t < 40 && vm.jobList.length === n; t++) await ssleep(300);
      if (vm.jobList.length > n) return true;
      await ssleep(3000);
    }
    return false;
  },
  // 顶部标签：「推荐」（.c-expect-select 里的 a）和自己设的求职期望（a.expect-item，文字后面可能带城市括号，按开头对）。
  // 点完核对这个标签真的选中了（它自己的 class 里多出 active），没选中返回 false，当成找不到标签停下，免得把上一个标签再扫一遍
  switchTag: async name => {
    const find = () => [...document.querySelectorAll('.c-expect-select a, a.expect-item')].find(e => { const t = e.innerText.trim(); return t === name || t.indexOf(name) === 0; });
    const a = find();
    if (!a) return false;
    const active = () => { const e = find(); return !!(e && /(^|\s)active(\s|$)/.test(e.className)); };
    const vm = window.__sBossVm(), first = vm && vm.jobList[0] && vm.jobList[0].encryptJobId;
    a.click();
    for (let t = 0; t < 40; t++) { await ssleep(300); const v = window.__sBossVm(); if (active() && v && v.jobList[0] && v.jobList[0].encryptJobId !== first) break; }
    await ssleep(1500);
    window.scrollTo(0, 0);
    return active();
  },
  tags: () => window.__sTagNames('.c-expect-select a, a.expect-item', true),
  sortNewest: async () => false,
  oldEnough: () => false,
  link: id => 'https://www.zhipin.com/job_detail/' + id + '.html',
};
