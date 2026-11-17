"""jobscan.py 的正反用例。jobscan.py 每条命令执行前都会跑 run_all()，不过就停。

run_all 先用现在的 jobscan.py 跑一遍，必须全过；再把 jobscan.py 改成几种错误写法（MUTANTS）各跑一遍，
每种都必须有用例不过——证明这些用例真能抓住这类错误。错误写法的原文找不到时也算不过，提醒用例跟代码对不上了。
"""
import contextlib
import io
import json
import os
import re
import subprocess
import tempfile
import types

NODE_RUN = r"""
const vm = require('vm'), fs = require('fs');
const store = {};
const ctx = { localStorage: { getItem: k => (k in store ? store[k] : null), setItem: (k, v) => { store[k] = String(v); } },
  setTimeout, console, document: { title: '' }, location: { hostname: '', pathname: '' } };
ctx.window = ctx;
vm.createContext(ctx);
const out = [vm.runInContext(fs.readFileSync(process.argv[1], 'utf8'), ctx)];
out.push(vm.runInContext(process.argv[2], ctx));
console.log(JSON.stringify(out));
"""


def call(mod, *argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = mod.dispatch(list(argv))
    return code, buf.getvalue()


def page_text(mod, platform, rows=(), blocked=(), counts=None, cut_end=False, part=(1, 1), when='2030-01-10T04:00:00.000Z', kwd='',
              tag='推荐', why='到底'):
    """按页面 __sText 的格式拼一段结果文字（用 mod 现在的配置算版本号）。when 是这次扫描的开始时间。"""
    cfg = mod.page_cfg(platform)
    c = counts or {}
    head = [platform, tag, why, '最新', cfg['days'], cfg['mode'], c.get('total', len(rows) + len(blocked)),
            c.get('kept', len(rows)), c.get('blocked', len(blocked)), c.get('old', 0), c.get('unknown', 0), c.get('stale', 0), c.get('kw', 0), kwd,
            c.get('seen', 0), c.get('seenn', cfg['seenn']), c.get('seenv', cfg['seenv']), cfg['code'], cfg['cfgv'], when, part[0], part[1]]
    lines = ['@@H|' + '|'.join(map(str, head))]
    lines += ['@@R|' + '|'.join(r) for r in rows] + ['@@B|' + '|'.join(b) for b in blocked]
    if not cut_end:
        lines.append('@@E|%d|%d|%d' % (part[0], part[1], len(rows) + len(blocked)))
    # get_page_text 会把换行变成空格，前面还带标题和网址
    return 'Title: x\nURL: y\n---\n' + ' '.join(lines)


def setup(mod, days='7', mode='company'):
    assert call(mod, 'config', '--days', days, '--mode', mode)[0] == 0


def R(jid, co, job, pub='2030-01-09 10:00:00', sal='6-8K', loc='示例区·示例路', exp='', deg='', hr='', sk='', desc=''):
    return [jid, co, job, sal, pub, loc, exp, deg, hr, sk, desc, '']


def save_rows(mod, d, platform, rows, when, blocked=(), tag='推荐', why='到底'):
    """存一次扫描结果，返回 (退出码, 输出, 留下的编号)。"""
    f = os.path.join(d, 'page_%s_%s.txt' % (platform, when))
    open(f, 'w', encoding='utf-8').write(page_text(mod, platform, rows=rows, blocked=blocked, when=when, tag=tag, why=why))
    code, out = call(mod, 'save', platform, f)
    kept = []
    if code == 0:
        res = re.search(r'结果文件：(.*)\.md', out).group(1) + '.json'
        kept = [r['id'] for r in json.load(open(res, encoding='utf-8'))['rows']]
    return code, out, kept


# ---------- 用例 ----------
def t_inject_stops_without_days(mod, d):
    call(mod, 'config', '--mode', 'company')
    code, out = call(mod, 'inject', 'boss')
    assert code == 2 and '先问使用者' in out and '7 天' in out, out
    assert not os.path.exists(os.path.join(d, 'inject_boss.js')), '没设天数也生成了注入文件'


def t_inject_stops_without_mode(mod, d):
    call(mod, 'config', '--days', '7')
    code, out = call(mod, 'inject', 'zhilian')
    assert code == 2 and '先问使用者' in out and '拦' in out, out
    assert not os.path.exists(os.path.join(d, 'inject_zhilian.js')), '没设拦法也生成了注入文件'


def t_config_rejects_bad_values(mod, d):
    for v in ('0', '-3', 'abc', '7.5'):
        assert call(mod, 'config', '--days', v)[0] == 2, '天数 %s 不该收' % v
    assert call(mod, 'config', '--mode', 'whatever')[0] == 2
    assert call(mod, 'config', '--mode', '拦公司+岗位')[0] == 0, '中文拦法应该认'
    assert json.load(open(os.path.join(d, 'config.json')))['mode'] == 'company_job'
    for word, want in (('拦整家公司', 'company'), ('只拦这一个岗位', 'company_job')):
        assert call(mod, 'config', '--mode', word)[0] == 0, '新叫法「%s」应该认' % word
        assert json.load(open(os.path.join(d, 'config.json')))['mode'] == want, word



def t_config_refresh_old(mod, d):
    setup(mod)
    conf = lambda: json.load(open(os.path.join(d, 'config.json')))
    assert mod.page_cfg('zhilian')['refresh'] == 'latest' and mod.page_cfg('zhilian')['old'] is None, '默认应是按刷新时间、不按首次发布筛'
    assert call(mod, 'config', '--refresh', 'first')[0] == 0 and conf()['refresh'] == 'first'
    assert mod.page_cfg('zhilian')['refresh'] == 'first'
    assert call(mod, 'config', '--refresh', 'latest')[0] == 0 and conf()['refresh'] == 'latest'
    assert call(mod, 'config', '--refresh', 'whatever')[0] == 2
    assert call(mod, 'config', '--old', '30,365')[0] == 0 and conf()['old'] == [30, 365]
    for v in ('365,30', '30', 'abc', '0,30', '30,30'):
        assert call(mod, 'config', '--old', v)[0] == 2, '老岗位范围 %s 不该收' % v
    c = mod.page_cfg('zhilian')
    assert c['refresh'] == 'latest' and c['old'] == [30, 365], c
    code, out = call(mod, 'config')
    assert '按刷新时间' in out and '超过 30 天、不超过 365 天' in out, out
    assert call(mod, 'config', '--old', 'off')[0] == 0 and 'old' not in conf()


def t_config_freq_and_reappear(mod, d):
    setup(mod)
    conf = lambda: json.load(open(os.path.join(d, 'config.json')))
    assert mod.freq_cfg(conf()) == [14, 3] and mod.reappear_days(conf()) == 365
    code, out = call(mod, 'config')
    assert code == 0 and '14 天内观测到刷新达 3 次及以上跳过（未另改，按默认）' in out and '连续 365 天未见再重现时放行提醒（未另改，按默认）' in out, out
    assert call(mod, 'config', '--freq', '14,5')[0] == 0 and conf()['freq'] == [14, 5]
    assert '14 天内观测到刷新达 5 次及以上跳过' in call(mod, 'config')[1]
    assert '未另改，按默认' not in next(l for l in call(mod, 'config')[1].splitlines() if '智联高频刷新过滤' in l)
    for bad in ('0,3', '14,1', '14', 'abc', '366,3'):
        assert call(mod, 'config', '--freq', bad)[0] == 2, bad
    assert call(mod, 'config', '--freq', 'off')[0] == 0 and mod.freq_cfg(conf()) is None
    assert '不按刷新次数筛' in call(mod, 'config')[1]
    assert call(mod, 'config', '--reappear', '180')[0] == 0 and mod.reappear_days(conf()) == 180
    assert '连续 180 天未见再重现时放行提醒' in call(mod, 'config')[1]
    for bad in ('0', '-5', 'abc'):
        assert call(mod, 'config', '--reappear', bad)[0] == 2, bad
    assert call(mod, 'config', '--reappear', 'off')[0] == 0 and mod.reappear_days(conf()) is None
    assert '始终跳过' in call(mod, 'config')[1]


def t_config_boss_active(mod, d):
    setup(mod)
    conf = lambda: json.load(open(os.path.join(d, 'config.json')))
    assert mod.boss_active(conf()) == 'week', '未设置时默认应是一周内活跃（排除 2 周内/本月及更早）'
    code, out = call(mod, 'config')
    assert code == 0 and 'Boss HR 活跃度（开卡复核时）：只留 1 周内活跃的 HR' in out and '按默认' in out, out
    for raw, want, txt in (
        ('3d', '3d', '3 日内活跃'),
        ('两周', '2w', '2 周内活跃'),
        ('本月', 'month', '本月内活跃'),
        ('today', 'today', '今天内活跃'),
        ('不限', 'off', '不按 HR 活跃度排除'),
        ('一周', 'week', '1 周内活跃'),
    ):
        assert call(mod, 'config', '--boss-active', raw)[0] == 0, raw
        assert conf()['boss_active'] == want, (raw, conf())
        c2, o2 = call(mod, 'config')
        line = next(l for l in o2.splitlines() if 'Boss HR 活跃度' in l)
        assert c2 == 0 and txt in line and '未另改，按默认' not in line, line
    assert call(mod, 'config', '--boss-active', 'whatever')[0] == 2


def t_config_boss_rest(mod, d):
    setup(mod)
    conf = lambda: json.load(open(os.path.join(d, 'config.json')))
    assert mod.boss_rest(conf()) == 'ask', '未设置时默认应标待核'
    code, out = call(mod, 'config')
    assert code == 0 and 'Boss 未写明双休处理' in out and '标为待核' in out and '未另改，按默认' in out, out
    for raw, want, txt in (
        ('exclude', 'exclude', '直接排除'),
        ('直接排除', 'exclude', '直接排除'),
        ('ask', 'ask', '标为待核'),
        ('标待核', 'ask', '标为待核'),
    ):
        assert call(mod, 'config', '--boss-rest', raw)[0] == 0, raw
        assert conf()['boss_rest'] == want, (raw, conf())
        c2, o2 = call(mod, 'config')
        line = next(l for l in o2.splitlines() if 'Boss 未写明双休处理' in l)
        assert c2 == 0 and txt in line and '未另改，按默认' not in line, line
    assert call(mod, 'config', '--boss-rest', 'whatever')[0] == 2


def t_save_stale_summary(mod, d):
    setup(mod)
    call(mod, 'config', '--refresh', 'latest', '--old', '30,365')
    txt = page_text(mod, 'zhilian', rows=[R('CC1J1', '庚辛信息', '运营专员')], counts={'total': 9, 'old': 2, 'unknown': 1, 'stale': 4})
    f = os.path.join(d, 'page_zhilian_1.txt')
    open(f, 'w', encoding='utf-8').write(txt)
    code, out = call(mod, 'save', 'zhilian', f)
    assert code == 0, out
    assert '首次发布超过 30 天（365 天以内）的老岗位跳过 4 条' in out, out
    assert '凌晨刷新又查不到首次发布' not in out, '按刷新时间算时，时间不明不是因为凌晨刷新：' + out


def t_inject_ok(mod, d):
    setup(mod, '5', 'company')
    call(mod, 'block', 'add', '甲乙科技')
    code, out = call(mod, 'inject', 'boss')
    assert code == 0, out
    txt = open(os.path.join(d, 'inject_boss.js'), encoding='utf-8').read()
    assert '"days": 5' in txt and '甲乙科技' in txt and 'window.__sInit(CFG)' in txt
    cfg = mod.page_cfg('boss')
    assert ('ready 代码%s 配置%s' % (cfg['code'], cfg['cfgv'])) in out


def t_inject_file_runs_in_page(mod, d):
    setup(mod, '7', 'company_job')
    call(mod, 'block', 'add', '甲乙科技', '运营专员')
    call(mod, 'keyword', 'add', '兼职')
    for p in ('boss', 'zhilian'):
        assert call(mod, 'inject', p)[0] == 0
        cfg = mod.page_cfg(p)
        r = subprocess.run(['node', '-e', NODE_RUN, os.path.join(d, 'inject_%s.js' % p), mod.LOADER],
                           capture_output=True, text=True, timeout=30)
        assert r.returncode == 0, r.stderr
        first, again = json.loads(r.stdout)
        want = 'ready 代码%s 配置%s 看过0条 黑名单1条 天数7 拦法company_job 关键词1个' % (cfg['code'], cfg['cfgv'])
        assert first == want, first
        assert again == want, '从 localStorage 重新装载结果不一样：' + again


def t_block_job_required_in_company_job(mod, d):
    setup(mod, '7', 'company_job')
    code, out = call(mod, 'block', 'add', '甲乙科技')
    assert code == 2 and '岗位' in out, out
    assert call(mod, 'block', 'add', '甲乙科技', '运营专员')[0] == 0
    assert len(json.load(open(os.path.join(d, 'blacklist.json')))) == 1


def t_block_ask_mode_needs_scope(mod, d):
    setup(mod, '7', 'ask')
    code, out = call(mod, 'block', 'add', '甲乙科技', '运营专员')
    assert code == 2 and '--whole' in out and '--only' in out, '每次问的拦法没问范围就加上了：' + out
    assert call(mod, 'block', 'add', '--only', '甲乙科技')[0] == 2, '只拦这一个岗位却没写岗位也加上了'
    assert call(mod, 'block', 'add', '--whole', '--only', '甲乙科技', '运营专员')[0] == 2
    assert call(mod, 'block', 'add', '--only', '甲乙科技', '运营专员')[0] == 0
    assert call(mod, 'block', 'add', '--whole', '丙丁商贸', '数据专员')[0] == 0
    b = json.load(open(os.path.join(d, 'blacklist.json')))
    assert [x['job'] for x in b] == ['运营专员', ''], '整家公司不该记岗位：%r' % b
    code, out = call(mod, 'block', 'list')
    assert '丙丁商贸 / 整家公司' in out, out
    assert call(mod, 'inject', 'boss')[0] == 0, '每次问的拦法下，整家公司的条目不该拦住 inject'
    assert '"mode": "ask"' in open(os.path.join(d, 'inject_boss.js'), encoding='utf-8').read()


def t_scope_flags_only_in_ask_mode(mod, d):
    setup(mod, '7', 'company_job')
    assert call(mod, 'block', 'add', '--whole', '甲乙科技')[0] == 2, '只拦这一个岗位的拦法下不该能加整家公司'
    assert not os.path.exists(os.path.join(d, 'blacklist.json')) or not json.load(open(os.path.join(d, 'blacklist.json')))
    assert call(mod, 'config', '--mode', 'company')[0] == 0
    code, out = call(mod, 'block', 'add', '--only', '甲乙科技', '运营专员')
    assert code == 2 and '每次问' in out, '拦整家公司的拦法下加 --only 应该拦下，免得以为只拦了岗位：' + out
    assert call(mod, 'config', '--mode', '每次问')[0] == 0
    assert json.load(open(os.path.join(d, 'config.json')))['mode'] == 'ask'


def t_block_company_mode_drops_job(mod, d):
    setup(mod, '7', 'company')
    call(mod, 'block', 'add', '甲乙科技', '运营专员')
    b = json.load(open(os.path.join(d, 'blacklist.json')))
    assert b[0]['job'] == '', '拦公司时不该记岗位（记了以后改拦法会悄悄变窄）'


def t_switch_to_company_job_stops_inject(mod, d):
    setup(mod, '7', 'company')
    call(mod, 'block', 'add', '甲乙科技')
    code, out = call(mod, 'config', '--mode', 'company_job')
    assert code == 0 and '没写岗位' in out, out
    code, out = call(mod, 'inject', 'boss')
    assert code == 2 and '第 1 条' in out, out
    call(mod, 'block', 'remove', '1')
    call(mod, 'block', 'add', '甲乙科技', '运营专员')
    assert call(mod, 'inject', 'boss')[0] == 0


def t_block_dup_and_remove(mod, d):
    setup(mod, '7', 'company')
    call(mod, 'block', 'add', '甲乙科技')
    code, out = call(mod, 'block', 'add', ' 甲乙科技 ')
    assert code == 0 and '已经有了' in out, out
    call(mod, 'block', 'add', '丙丁商贸')
    assert call(mod, 'block', 'remove', '3')[0] == 2
    assert call(mod, 'block', 'remove', '1')[0] == 0
    b = json.load(open(os.path.join(d, 'blacklist.json')))
    assert [x['company'] for x in b] == ['丙丁商贸'], b


def t_save_ok(mod, d):
    setup(mod, '7', 'company')
    call(mod, 'block', 'add', '甲乙科技')
    # 两个平台用不同公司：同公司同岗位在另一个平台会被当成看过的跳过（另有用例）
    for p, jid, link, co in (('boss', 'abc123XYZ', 'https://www.zhipin.com/job_detail/abc123XYZ.html', '戊己信息'),
                             ('zhilian', 'CC000111J000222', 'https://www.zhaopin.com/jobdetail/CC000111J000222.htm', '庚辛信息')):
        txt = page_text(mod, p, rows=[R(jid, co, '运营专员', loc='西青区·大寺')],
                        blocked=[['b1', '示例市甲乙科技有限公司', '数据专员', '5-7K', '', '', '甲乙科技']],
                        counts={'total': 12, 'old': 6, 'unknown': 1, 'kw': 3}, kwd='兼职:2,销售:1')
        f = os.path.join(d, 'page_%s.txt' % p)
        open(f, 'w', encoding='utf-8').write(txt)
        code, out = call(mod, 'save', p, f)
        assert code == 0, out
        assert '留下 1 条' in out and '黑名单跳过 1 条' in out, out
        assert '关键词跳过 3 条（兼职 2 条、销售 1 条）' in out, out
        assert '投过的跳过 0 条' in out and '看过的跳过 0 条' in out and '重复的丢掉 0 条' in out, out
        if p == 'zhilian':
            assert '超过 7 天跳过 6 条' in out and '发布时间不明跳过 1 条' in out, out
        else:
            assert '不显示发布时间' in out, out
        md = out.strip().split('结果文件：')[-1]
        body = open(md, encoding='utf-8').read()
        assert link in body and co in body and '示例市甲乙科技有限公司' in body, body
        assert '| 运营专员 | 西青区·大寺 | 6-8K |' in body, '清单里没有地点一列：' + body


def t_save_two_parts(mod, d):
    setup(mod, '7', 'company')
    both = {'total': 2, 'kept': 2}  # 头行里的个数是全部的，不是这一段的
    a = page_text(mod, 'boss', rows=[R('x1', '戊己', '运营', '', '6K', '')], counts=both, part=(1, 2))
    b = page_text(mod, 'boss', rows=[R('x2', '庚辛', '运营', '', '6K', '')], counts=both, part=(2, 2))
    fa, fb = os.path.join(d, 'a.txt'), os.path.join(d, 'b.txt')
    open(fa, 'w', encoding='utf-8').write(a)
    open(fb, 'w', encoding='utf-8').write(b)
    code, out = call(mod, 'save', 'boss', fa)
    assert code == 2 and '还缺第 2 段' in out, out
    code, out = call(mod, 'save', 'boss', fa, fb)
    assert code == 0 and '留下 2 条' in out, out


def t_save_rejects_cut_text(mod, d):
    setup(mod, '7', 'company')
    rows = [R('x%d' % i, '戊己%d' % i, '运营', '', '6K', '') for i in range(3)]
    f = os.path.join(d, 'cut.txt')
    open(f, 'w', encoding='utf-8').write(page_text(mod, 'boss', rows=rows, cut_end=True))
    code, out = call(mod, 'save', 'boss', f)
    assert code == 2 and '没取全' in out, out
    # 末尾行在，但中间丢了一行
    full = page_text(mod, 'boss', rows=rows)
    open(f, 'w', encoding='utf-8').write(full.replace('@@R|x1|戊己1|运营|6K|||||||| ', ''))
    code, out = call(mod, 'save', 'boss', f)
    assert code == 2 and '没取全' in out, out
    assert not os.path.exists(os.path.join(d, 'results')), '没取全也存了结果'


def t_save_rejects_old_config(mod, d):
    setup(mod, '7', 'company')
    txt = page_text(mod, 'zhilian', rows=[R('x1', '戊己', '运营', '2030-01-09', '6K', '')])
    call(mod, 'block', 'add', '丙丁商贸')  # 注入以后黑名单变了
    f = os.path.join(d, 'old.txt')
    open(f, 'w', encoding='utf-8').write(txt)
    code, out = call(mod, 'save', 'zhilian', f)
    assert code == 2 and '配置是旧的' in out, out


def t_save_rejects_wrong_platform(mod, d):
    setup(mod, '7', 'company')
    f = os.path.join(d, 'p.txt')
    open(f, 'w', encoding='utf-8').write(page_text(mod, 'boss', rows=[R('x1', '戊己', '运营', '', '6K', '')]))
    code, out = call(mod, 'save', 'zhilian', f)
    assert code == 2 and '不是 zhilian' in out, out


def t_block_add_by_id(mod, d):
    setup(mod, '7', 'company_job')
    call(mod, 'block', 'add', '占位公司', '占位岗位')
    f = os.path.join(d, 'p.txt')
    open(f, 'w', encoding='utf-8').write(page_text(mod, 'zhilian', rows=[R('CC9J8', '示例市戊己信息有限公司', '运营专员', '2030-01-09', '6K', '')]))
    assert call(mod, 'save', 'zhilian', f)[0] == 0
    code, out = call(mod, 'block', 'add', '--id', 'CC9J8')
    assert code == 0, out
    b = json.load(open(os.path.join(d, 'blacklist.json')))[-1]
    assert (b['company'], b['job'], b['from']) == ('示例市戊己信息有限公司', '运营专员', 'zhilian'), b
    assert call(mod, 'block', 'add', '--id', 'nope')[0] == 2


# ---------- 不想看的关键词 ----------
def t_keyword_add_list_remove(mod, d):
    setup(mod)
    assert mod.page_cfg('boss')['keywords'] == [], '默认应该是空的、不按词拦'
    code, out = call(mod, 'keyword', 'add', '兼职', '销售', '提成')
    assert code == 0, out
    assert call(mod, 'keyword', 'add', '兼职')[0] == 0
    assert mod.page_cfg('boss')['keywords'] == ['兼职', '销售', '提成'], '重复的词又加了一遍'
    for bad in ('兼|职', '销 售', '提成,'):
        assert call(mod, 'keyword', 'add', bad)[0] == 2, '带分隔符的词不该收：' + bad
    assert call(mod, 'keyword', 'remove', '销售')[0] == 0
    assert call(mod, 'keyword', 'remove', '2')[0] == 0
    assert call(mod, 'keyword', 'remove', '没有的词')[0] == 2
    code, out = call(mod, 'keyword', 'list')
    assert '1. 兼职' in out and '销售' not in out and '提成' not in out, out
    assert call(mod, 'inject', 'zhilian')[0] == 0
    txt = open(os.path.join(d, 'inject_zhilian.js'), encoding='utf-8').read()
    assert '"keywords": ["兼职"]' in txt, '关键词没传给页面'


# ---------- 投过记录 ----------
def t_applied_add_by_id_list_remove(mod, d):
    setup(mod)
    assert save_rows(mod, d, 'zhilian', [R('CC1J2', '示例市戊己信息有限公司', '运营专员')], 'T1')[0] == 0
    code, out = call(mod, 'applied', 'add', '--id', 'https://www.zhaopin.com/jobdetail/CC1J2.htm')
    assert code == 0, out
    a = json.load(open(os.path.join(d, 'applied.json'), encoding='utf-8'))
    assert len(a) == 1 and (a[0]['platform'], a[0]['id'], a[0]['company'], a[0]['job']) == (
        'zhilian', 'CC1J2', '示例市戊己信息有限公司', '运营专员'), a
    assert a[0]['link'].endswith('/CC1J2.htm') and a[0]['date'], a
    code, out = call(mod, 'applied', 'add', '--id', 'CC1J2')
    assert '已经记过了' in out and len(json.load(open(os.path.join(d, 'applied.json')))) == 1, out
    assert '示例市戊己信息有限公司' in call(mod, 'applied', 'list')[1]
    assert call(mod, 'applied', 'add', '--id', 'nope')[0] == 2
    assert call(mod, 'applied', 'add', '只写了公司')[0] == 2
    assert call(mod, 'applied', 'add', '甲乙科技', '运营专员', '--platform', 'other')[0] == 2
    assert call(mod, 'applied', 'remove', '2')[0] == 2
    assert call(mod, 'applied', 'remove', '1')[0] == 0
    assert json.load(open(os.path.join(d, 'applied.json'))) == []


def t_applied_skips_both_platforms(mod, d):
    setup(mod)
    code, out = call(mod, 'applied', 'add', '甲乙科技', '行政人事专员', '--platform', 'boss')
    assert code == 0, out
    code, out, kept = save_rows(mod, d, 'zhilian', [
        R('z1', '示例市甲乙科技有限公司', '人事行政专员'),  # 另一个平台、全称、词序不同：投过
        R('z2', '示例市甲乙科技有限公司', '数据专员'),      # 同公司别的岗位：留
        R('z3', '丙丁商贸有限公司', '行政人事专员'),        # 别的公司同名岗位：留
    ], 'T1')
    assert code == 0, out
    assert kept == ['z2', 'z3'], kept
    assert '投过的跳过 1 条' in out and '看过的跳过 0 条' in out, out
    # 投过拦下的不记成看过：删掉投过记录，这条照常列出
    assert call(mod, 'applied', 'remove', '1')[0] == 0
    code, out, kept = save_rows(mod, d, 'zhilian', [R('z1', '示例市甲乙科技有限公司', '人事行政专员')], 'T2')
    assert kept == ['z1'], '投过拦下的被记成了看过：%s %s' % (kept, out)


# ---------- 看过的不再列 ----------
def t_seen_by_id_and_company_job(mod, d):
    setup(mod)
    code, out, kept = save_rows(mod, d, 'boss', [R('b1', '甲乙科技', '运营专员', ''), R('b2', '丙丁商贸', '数据专员', '')], 'T1',
                                blocked=[['b9', '戊己信息', '运营专员', '6K', '', '', '戊己信息']])
    assert kept == ['b1', 'b2'] and '看过的跳过 0 条' in out, out
    code, out, kept = save_rows(mod, d, 'boss', [
        R('b1', '甲乙科技', '运营主管', ''),   # 编号相同（岗位改了名）：看过
        R('b3', '甲乙科技', '运营专员', ''),   # 换编号重发：看过
        R('b4', '丙丁商贸', '数据分析', ''),   # 新岗位：留
        R('b9', '戊己信息', '运营专员', ''),   # 上次被黑名单拦下，没记成看过：留
    ], 'T2')
    assert kept == ['b4', 'b9'], kept
    assert '看过的跳过 2 条' in out, out
    # 另一个平台同公司同岗位（全称、词序不同）也认得
    code, out, kept = save_rows(mod, d, 'zhilian', [R('z1', '示例市甲乙科技有限公司', '专员运营'),
                                                    R('z2', '示例市甲乙科技有限公司', '数据专员')], 'T3')
    assert kept == ['z2'], kept


def t_seen_count_and_clear(mod, d):
    setup(mod)
    save_rows(mod, d, 'boss', [R('b1', '甲乙科技', '运营专员', '')], 'T1')
    assert '共 1 条' in call(mod, 'seen')[1]
    code, out, kept = save_rows(mod, d, 'boss', [R('b1', '甲乙科技', '运营专员', '')], 'T2')
    assert kept == [], kept
    code, out = call(mod, 'seen', 'clear')
    assert code == 0 and '已清空' in out, out
    assert json.load(open(os.path.join(d, 'seen.json'))) == []
    assert len(json.load(open(os.path.join(d, 'seen.bak.json')))) == 1, '清空前没留备份'
    code, out, kept = save_rows(mod, d, 'boss', [R('b1', '甲乙科技', '运营专员', '')], 'T3')
    assert kept == ['b1'], '清空后没重新列出：%s' % kept
    assert call(mod, 'seen', 'whatever')[0] == 2


def t_save_same_scan_twice_refused(mod, d):
    setup(mod)
    assert save_rows(mod, d, 'boss', [R('b1', '甲乙科技', '运营专员', '')], 'T1')[0] == 0
    code, out, kept = save_rows(mod, d, 'boss', [R('b1', '甲乙科技', '运营专员', '')], 'T1')
    assert code == 2 and '已经存过了' in out, out


# ---------- 看过的交给页面先跳过 ----------
def t_seen_code_same_as_page(mod, d):
    # 和 tests/test_page.js 钉的是同两个值；再让页面脚本算一批，两边必须一样
    assert mod.seen_code('abc123XYZ') == 'mshXG9D' and mod.seen_code('中文编号') == '3sj18ez', '短码算法变了'
    ids = ['abc123XYZ', 'CC000111J000222', 'a1', '中文编号', 'x' * 60, '0a5b~~', 'CC120084532J40626573605']
    js = ("const vm=require('vm'),fs=require('fs');const c={setTimeout,console};c.window=c;vm.createContext(c);"
          "vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),c);console.log(JSON.stringify(JSON.parse(process.argv[2]).map(c.__sCode)))")
    r = subprocess.run(['node', '-e', js, os.path.join(os.path.dirname(os.path.abspath(mod.__file__)), 'page', 'common.js'),
                        json.dumps(ids)], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout) == [mod.seen_code(x) for x in ids], '页面和 jobscan.py 算出的短码不一样'
    assert len({mod.seen_code('id%d' % i) for i in range(5000)}) == 5000, '5000 个编号里短码撞了'


def t_inject_carries_seen_codes(mod, d):
    setup(mod)
    v0 = mod.page_cfg('boss')['cfgv']
    save_rows(mod, d, 'boss', [R('b1', '甲乙科技', '运营专员', ''), R('b2', '丙丁商贸', '数据专员', '')], 'T1')
    cfg = mod.page_cfg('boss')
    assert cfg['seen'] == mod.seen_code('b1') + mod.seen_code('b2') and cfg['seenn'] == 2, cfg
    assert mod.page_cfg('zhilian')['seenn'] == 0, '别的平台看过的不该交给这个平台'
    assert cfg['cfgv'] == v0, '看过的记录算进了配置号：每次 save 后页面都会被说成配置是旧的'
    code, out = call(mod, 'inject', 'boss')
    assert code == 0 and 'ready 代码%s 配置%s 看过2条' % (cfg['code'], v0) in out, out
    r = subprocess.run(['node', '-e', NODE_RUN, os.path.join(d, 'inject_boss.js'), '1'], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0 and '看过2条' in json.loads(r.stdout)[0], r.stdout + r.stderr


def t_save_counts_page_seen(mod, d):
    setup(mod)
    save_rows(mod, d, 'boss', [R('b1', '甲乙科技', '运营专员', '')], 'T1')
    f = os.path.join(d, 'page_boss_1.txt')
    open(f, 'w', encoding='utf-8').write(page_text(mod, 'boss', rows=[R('b2', '丙丁商贸', '数据专员', ''), R('b1', '甲乙科技', '运营专员', '')],
                                                   counts={'total': 5, 'seen': 3}, when='T2'))
    code, out = call(mod, 'save', 'boss', f)
    assert code == 0 and '看过的跳过 4 条' in out, '页面先跳过的 3 条加 save 认出的 1 条：' + out


def t_save_rejects_stale_seen(mod, d):
    setup(mod)
    save_rows(mod, d, 'boss', [R('b1', '甲乙科技', '运营专员', '')], 'T1')
    old = page_text(mod, 'boss', rows=[R('b3', '戊己信息', '运营专员', '')], counts={'seen': 1}, when='T2')  # 页面拿着 b1
    save_rows(mod, d, 'boss', [R('b2', '丙丁商贸', '数据专员', '')], 'T3')  # 之后又记了 b2：页面的记录只是旧一点，照收
    f = os.path.join(d, 'page_boss_1.txt')
    open(f, 'w', encoding='utf-8').write(old)
    code, out = call(mod, 'save', 'boss', f)
    assert code == 0, '页面的看过记录只是少了后来记的，不该拒：' + out
    stale = page_text(mod, 'boss', rows=[R('b4', '庚辛科技', '运营专员', '')], counts={'seen': 1}, when='T4')
    assert call(mod, 'seen', 'clear')[0] == 0
    open(f, 'w', encoding='utf-8').write(stale)
    code, out = call(mod, 'save', 'boss', f)
    assert code == 2 and '对不上' in out and 'inject_boss_cfg.js' in out, '清空以后页面还拿着旧记录跳过，必须拒：' + out
    open(f, 'w', encoding='utf-8').write(page_text(mod, 'boss', rows=[R('b4', '庚辛科技', '运营专员', '')], counts={'seen': 0, 'seenn': 2, 'seenv': 'xxxxxx'}, when='T5'))
    assert call(mod, 'save', 'boss', f)[0] == 0, '页面一条都没按看过跳过，记录旧了也没关系'


def t_save_drops_page_files(mod, d):
    setup(mod)
    f = os.path.join(d, 'page_boss_1.txt')
    open(f, 'w', encoding='utf-8').write(page_text(mod, 'boss', rows=[R('x1', '戊己', '运营', '')], cut_end=True))
    assert call(mod, 'save', 'boss', f)[0] == 2
    assert os.path.exists(f), '没存成也删了页面文件（要按提示重取）'
    open(f, 'w', encoding='utf-8').write(page_text(mod, 'boss', rows=[R('x1', '戊己', '运营', '')], when='T1'))
    with tempfile.TemporaryDirectory() as other:
        g = os.path.join(other, 'page_boss_2.txt')
        open(g, 'w', encoding='utf-8').write(page_text(mod, 'boss', rows=[R('x2', '庚辛', '运营', '')], when='T2'))
        code, out = call(mod, 'save', 'boss', f)
        assert code == 0 and not os.path.exists(f), '存完没删 data/ 里读过的页面文件：' + out
        assert call(mod, 'save', 'boss', g)[0] == 0 and os.path.exists(g), '不该删 data/ 以外的文件'


def t_seen_new_id_recorded(mod, d):
    setup(mod)
    save_rows(mod, d, 'boss', [R('b1', '甲乙科技', '运营专员', '')], 'T1')
    # 智联上同公司同岗位、编号不同：按看过跳过，同时把智联的编号记上，下次页面按编号就能先跳过
    code, out, kept = save_rows(mod, d, 'zhilian', [R('z1', '示例市甲乙科技有限公司', '运营专员')], 'T2')
    assert code == 0 and kept == [] and '看过的跳过 1 条' in out, out
    seen = json.load(open(os.path.join(d, 'seen.json'), encoding='utf-8'))
    assert [(e['platform'], e['id']) for e in seen] == [('boss', 'b1'), ('zhilian', 'z1')], seen
    assert mod.page_cfg('zhilian')['seen'] == mod.seen_code('z1'), '补记的编号没交给页面'
    # 同一编号再按看过跳过，不再记一遍
    save_rows(mod, d, 'zhilian', [R('z1', '示例市甲乙科技有限公司', '运营专员')], 'T3')
    assert len(json.load(open(os.path.join(d, 'seen.json'), encoding='utf-8'))) == 2, '同一编号记了两遍'


def t_save_refreshes_page_cfg(mod, d):
    setup(mod)
    code, out, kept = save_rows(mod, d, 'boss', [R('b1', '甲乙科技', '运营专员', '')], 'T1')
    small = open(os.path.join(d, 'inject_boss_cfg.js'), encoding='utf-8').read()
    assert mod.seen_code('b1') in small and '看过1条' in out and 'inject_boss_cfg.js' in out, '存完没重新生成带新看过记录的配置文件：' + out


def t_first_scan_groups_titles(mod, d):
    setup(mod)
    rows = [R('a%d' % i, 'C%02d科技' % i, '行政专员' if i < 20 else ('行政助理（双休）' if i < 32 else '岗位%d' % i), '') for i in range(50)]
    code, out, kept = save_rows(mod, d, 'boss', rows, 'T1')
    assert code == 0 and '按岗位名归类（共 50 条）：行政专员 20 条、行政助理（双休） 12 条' in out and '其他' in out, out
    body = _md(out)
    assert '| 行政专员 | 20 |' in body, '结果文件里没有归类表'
    code, out, kept = save_rows(mod, d, 'boss', [R('c%d' % i, 'D%02d科技' % i, '行政专员', '') for i in range(45)], 'T2')
    assert code == 0 and '按岗位名归类' not in out, '不是第一次扫不该归类：' + out
    code, out, kept = save_rows(mod, d, 'zhilian', [R('z%d' % i, 'E%02d科技' % i, '文员', '2030-01-09') for i in range(10)], 'T3')
    assert code == 0 and '按岗位名归类' not in out, '第一次扫但不多（不超过 40 条），直接列就行：' + out


# ---------- 同公司同岗位只留一条 ----------
def t_dedup_same_company_job(mod, d):
    setup(mod)
    code, out, kept = save_rows(mod, d, 'zhilian', [
        R('z1', '示例市甲乙科技有限公司', '人事行政专员'),
        R('z2', '示例市甲乙科技有限公司', '行政人事专员（双休）', sal='7-9K'),  # 词序、薪资、编号不同：重复
        R('z3', '甲乙科技', '人事行政专员'),                                   # 公司写法不同：重复
        R('z4', '示例市甲乙科技有限公司', '人事行政专员助理'),                  # 名称变体：不合并
        R('z5', '示例市甲乙科技有限公司', '行政专员'),                          # 不同岗位
        R('z6', '丙丁商贸有限公司', '人事行政专员'),                            # 不同公司
    ], 'T1')
    assert code == 0, out
    assert kept == ['z1', 'z4', 'z5', 'z6'], kept
    assert '重复的丢掉 2 条' in out, out
    res = out.strip().split('结果文件：')[-1]
    assert '| 重复 | 示例市甲乙科技有限公司 | 行政人事专员（双休） |' in open(res, encoding='utf-8').read(), '重复丢掉的没列出来核对'


# ---------- Boss 求职期望列表的福利后缀 ----------
def t_boss_welfare_tail(mod, d):
    """Boss 求职期望列表给岗位名加的「-双休」「-五险一金」不算新岗位；横杠后面是别的字的照常算不同岗位。"""
    setup(mod)
    code, out, kept = save_rows(mod, d, 'boss', [R('b1', '甲乙科技', '行政专员', ''), R('b2', '丙丁商贸', '人事行政专员', '')], 'T1')
    assert kept == ['b1', 'b2'], out
    code, out, kept = save_rows(mod, d, 'boss', [
        R('b3', '甲乙科技', '行政专员-双休', ''),               # 推荐里看过，期望标签里换了编号、带后缀：看过
        R('b4', '丙丁商贸', '行政人事专员—双休-五险一金', ''),  # 词序不同、两段后缀：看过
        R('b5', '甲乙科技', '行政专员-出差补助', ''),           # 横杠后面不是福利词：不同岗位，留
        R('b6', '戊己信息', '销售内勤-五险一金', ''),
        R('b7', '戊己信息', '销售内勤', ''),                    # 同一次扫描里一条带后缀一条不带：重复
    ], 'T2', tag='行政专员/助理')
    assert kept == ['b5', 'b6'], (kept, out)
    assert '看过的跳过 2 条' in out and '重复的丢掉 1 条' in out, out



def _md(out):
    return open(re.search(r'结果文件：(.*\.md)', out).group(1), encoding='utf-8').read()


def t_near_titles(mod, d):
    """同公司标题相近的不合并，清单后面注明列表里看得到的几项哪些一样、哪些不同；这次列出的、看过的、投过的都比。"""
    setup(mod)
    J = dict(sal='4-5K', loc='西青区·侯台', deg='大专', hr='于先生/招聘者')
    code, out, kept = save_rows(mod, d, 'boss', [
        R('b1', '杰玛信息', '资质审核', exp='1年以内', **J),
        R('b2', '天津杰玛信息服务有限公司', '资质审核专员', exp='1-3年', **J),
        R('b3', '哈啰普惠', '财务结算', sal='7-9K', hr='达先生/财务BP', sk='初级会计师、集团公司'),
        R('b4', '丙丁商贸', '资质审核专员', exp='1-3年', **J),
        R('b5', '哈啰普惠', '财务主管', sal='7-9K'),
        R('b6', '神州浩天', '税务热线咨询岗-双休', hr='崔先生/招聘主管', sk='其他'),
        R('b7', '神州浩天', '税务热线咨询岗-双休', hr='张女士/招聘专员', sk='税务咨询、财税'),
    ], 'T1')
    assert kept == ['b1', 'b2', 'b3', 'b4', 'b5', 'b6'], (kept, out)
    body = _md(out)
    assert '同公司标题相近的 1 条' in out, out
    assert '| 2 | 天津杰玛信息服务有限公司 | 资质审核专员 | 第 1 条「资质审核」 | 薪资、地点、学历、招聘人 | 经验：1-3年 / 1年以内 |' in body, body
    assert '| 资质审核专员（有相近的，见下表） |' in body, '清单里没标出有相近的：' + body
    assert '丙丁商贸 | 资质审核专员（有相近' not in body and '| 丙丁商贸 | 资质审核专员 | 第' not in body, '别的公司被当成相近：' + body
    assert '财务主管（有相近' not in body, '标题不相近也标了：' + body
    assert '招聘人：张女士/招聘专员 / 崔先生/招聘主管' in body and '技能标签：税务咨询、财税 / 其他' in body, '重复丢掉的没写哪里不一样：' + body
    e = next(x for x in json.load(open(os.path.join(d, 'seen.json'), encoding='utf-8')) if x['id'] == 'b3')
    assert (e.get('salary'), e.get('hr'), e.get('skills')) == ('7-9K', '达先生/财务BP', '初级会计师、集团公司'), '看过记录没存比对用的几项：%s' % e
    # 下一次扫到：和看过的比
    code, out, kept = save_rows(mod, d, 'boss', [
        R('c1', '哈啰普惠', '租车财务结算(J21736)', sal='7-12K', hr='毛女士/招聘HR', sk='集团公司、中级会计师'),
        R('c2', '杰玛信息', '资质审核员', exp='1年以内', **J),
    ], 'T2', tag='销售助理')
    body = _md(out)
    assert kept == ['c1', 'c2'] and '同公司标题相近的 2 条' in out, (kept, out)
    assert '看过的「财务结算」（' in body and '薪资：7-12K / 7-9K；' in body and '招聘人：毛女士/招聘HR / 达先生/财务BP' in body, body
    assert '技能标签：集团公司、中级会计师 / 初级会计师、集团公司' in body, body
    assert '看过的「资质审核」（' in body and '能比的几项都一样，可能只是改了标题' in body, body
    # 投过的、旧的看过记录（没存比对项、别的平台）
    assert call(mod, 'applied', 'add', '--id', 'b3')[0] == 0
    a = json.load(open(os.path.join(d, 'applied.json'), encoding='utf-8'))[0]
    assert a.get('hr') == '达先生/财务BP', '投过记录没带比对用的几项：%s' % a
    seen = json.load(open(os.path.join(d, 'seen.json'), encoding='utf-8'))
    seen.append({'platform': 'zhilian', 'id': 'z9', 'company': '戊己信息有限公司', 'job': '运营专员', 'date': '2030-01-01'})
    json.dump(seen, open(os.path.join(d, 'seen.json'), 'w', encoding='utf-8'), ensure_ascii=False)
    code, out, kept = save_rows(mod, d, 'boss', [
        R('c3', '戊己信息', '运营专员助理', hr='王女士/人事'),
        R('c4', '哈啰普惠', '财务结算岗', sal='7-9K', hr='达先生/财务BP', sk='集团公司、初级会计师'),
    ], 'T3', tag='人力')
    body = _md(out)
    assert '看过的（智联招聘）「运营专员」（2030-01-01） | — | 那条没存详细信息，点链接对比' in body, body
    assert '投过的「财务结算」' in body, body
    assert '| 薪资、地点、招聘人、技能标签 | 能比的几项都一样，可能只是改了标题 |' in body, '技能标签只是顺序不同也该算一样：' + body


# ---------- 一次交代几件事、继续 ----------
def _tasks(d):
    return [(t['platform'], t['tag'], t['status']) for t in json.load(open(os.path.join(d, 'progress.json'), encoding='utf-8'))['items']]


def t_task_set_keeps_order(mod, d):
    setup(mod)
    assert call(mod, 'task', 'set', 'zhilian:标签A', 'boss:推荐')[0] == 0
    assert _tasks(d) == [('zhilian', '标签A', 'todo'), ('boss', '推荐', 'todo')], '没按交代的顺序记：%s' % _tasks(d)
    code, out = call(mod, 'task', 'set', '两边')
    assert code == 2 and '先问使用者' in out and '先扫 Boss直聘，还是先扫智联招聘' in out, '没选先扫哪个平台也排了「两边」：' + out
    assert _tasks(d)[0] == ('zhilian', '标签A', 'todo'), '没选先扫平台时不该动原来的任务'
    call(mod, 'config', '--first', 'boss')
    code, out = call(mod, 'task', 'set', '两边')
    assert code == 0 and '还有 2 件没做完' in out, out
    assert _tasks(d) == [('boss', '*', 'todo'), ('zhilian', '*', 'todo')], '选了先扫 Boss，「两边」应先 Boss 后智联：%s' % _tasks(d)
    assert call(mod, 'task', 'set', '别的平台')[0] == 2
    assert call(mod, 'task', 'set')[0] == 2


def t_first_platform_asked_and_kept(mod, d):
    """先扫哪个平台：第一次问，记进配置，以后「两边」都按它排；使用者说改就改。"""
    setup(mod)
    code, out = call(mod, 'config')
    assert '先扫哪个平台没选' in out and '先问使用者' in out, '没选时 config 没提示要问：' + out
    assert call(mod, 'config', '--first', '智联')[0] == 0
    out = call(mod, 'config')[1]
    assert '两边都扫时：先扫智联招聘' in out and '先扫哪个平台没选' not in out, out
    call(mod, 'task', 'set', '两边')
    assert _tasks(d) == [('zhilian', '*', 'todo'), ('boss', '*', 'todo')], '选了先扫智联，「两边」应先智联后 Boss：%s' % _tasks(d)
    call(mod, 'task', 'set', 'boss:推荐', '两边')
    assert _tasks(d) == [('boss', '推荐', 'todo'), ('zhilian', '*', 'todo'), ('boss', '*', 'todo')], _tasks(d)
    assert call(mod, 'config', '--first', 'Boss')[0] == 0
    call(mod, 'task', 'set', '两边')
    assert _tasks(d) == [('boss', '*', 'todo'), ('zhilian', '*', 'todo')], '改回先扫 Boss 没生效：%s' % _tasks(d)
    assert call(mod, 'config', '--first', '都行')[0] == 2
    assert json.load(open(os.path.join(d, 'config.json')))['first'] == 'boss'


def t_start_scans_all_tags(mod, d):
    """「开始」「两边都扫」= 两边全部标签；轮到时读页面标签名换成一件件；第一次扫通后问以后「开始」是不是直接全扫。"""
    setup(mod)
    call(mod, 'config', '--first', 'zhilian')
    code, out = call(mod, 'task', 'set', '开始')
    assert code == 0 and _tasks(d) == [('zhilian', '*', 'todo'), ('boss', '*', 'todo')], _tasks(d)
    assert '智联招聘 全部标签' in out and 'window.__sTags()' in out and 'task tags 1' in out, '轮到全部标签时没说先读标签名：' + out
    call(mod, 'task', 'set', 'boss:全部')
    assert _tasks(d) == [('boss', '*', 'todo')], _tasks(d)
    call(mod, 'config', '--first', 'boss')
    call(mod, 'task', 'set', '两边')
    assert call(mod, 'task', 'tags', '1')[0] == 2, '一个标签没写也换了'
    code, out = call(mod, 'task', 'tags', '1', '推荐', ' 行政专员/助理 ', '', '推荐')
    assert code == 0, out
    assert _tasks(d) == [('boss', '推荐', 'todo'), ('boss', '行政专员/助理', 'todo'), ('zhilian', '*', 'todo')], '标签没按页面顺序换好（空的、重复的要去掉）：%s' % _tasks(d)
    assert call(mod, 'task', 'tags', '1', '别的')[0] == 2, '已经换过的又换了一次'
    code, out, kept = save_rows(mod, d, 'boss', [], 'T1', tag='推荐', why='到底')
    assert '下一件：第 2 件 Boss直聘 行政专员/助理' in out, out
    code, out, kept = save_rows(mod, d, 'boss', [], 'T2', tag='行政专员/助理', why='到底')
    assert '下一件：第 3 件 智联招聘 全部标签' in out and 'task tags 3' in out, out
    call(mod, 'task', 'tags', '3', '标签B')
    code, out, kept = save_rows(mod, d, 'zhilian', [], 'T3', tag='标签B', why='超过7天')
    assert '都过了一遍：做完 3 件' in out and '以后说『开始』' in out, '全部标签第一次扫通后没提示问使用者：' + out
    assert '还没问过' in call(mod, 'config')[1]
    assert call(mod, 'config', '--start', '随便')[0] == 2
    call(mod, 'config', '--start', 'all')
    assert '两边全部标签直接扫' in call(mod, 'config')[1]
    call(mod, 'task', 'set', 'boss:全部')
    call(mod, 'task', 'tags', '1', '推荐')
    code, out, kept = save_rows(mod, d, 'boss', [], 'T4', tag='推荐', why='到底')
    assert '都过了一遍' in out and '以后说『开始』' not in out, '问过了还在提示：' + out
    call(mod, 'task', 'set', 'boss:推荐')
    code, out, kept = save_rows(mod, d, 'boss', [], 'T5', tag='推荐', why='到底')
    call(mod, 'config', '--start', 'ask')
    assert '先问使用者这次扫哪些' in call(mod, 'config')[1]


def t_task_save_updates_record(mod, d):
    setup(mod)
    call(mod, 'task', 'set', 'boss:推荐', 'zhilian:标签A', 'zhilian')
    code, out, kept = save_rows(mod, d, 'boss', [R('b1', '甲乙科技', '运营专员', '')], 'T1', tag='推荐', why='到底')
    assert '第 1 件 Boss直聘 推荐 做完' in out and '下一件：第 2 件 智联招聘 标签A' in out, out
    code, out, kept = save_rows(mod, d, 'zhilian', [R('z1', '丙丁商贸', '数据专员')], 'T2', tag='标签A', why='加载不出更多（重试过，没翻完）')
    assert '第 2 件 智联招聘 标签A 没做完（加载不出更多' in out, out
    code, out, kept = save_rows(mod, d, 'zhilian', [], 'T3', tag='当前列表', why='超过7天')
    assert _tasks(d) == [('boss', '推荐', 'done'), ('zhilian', '标签A', 'unfinished'), ('zhilian', '', 'done')], _tasks(d)
    assert '都过了一遍：做完 2 件，没做完 1 件' in out, out
    items = json.load(open(os.path.join(d, 'progress.json'), encoding='utf-8'))['items']
    assert all(t['result'].endswith('.md') for t in items), '任务记录里没记结果文件'


def t_task_resume_from_first_unfinished(mod, d):
    setup(mod)
    call(mod, 'task', 'set', 'boss:推荐', 'boss:标签A', 'zhilian:标签B', 'zhilian:标签C')
    call(mod, 'task', 'done', '1')
    call(mod, 'task', 'fail', '2', '找不到标签')
    call(mod, 'task', 'done', '3')
    code, out = call(mod, 'task', 'resume')
    assert code == 0 and '从第 2 件接着做：Boss直聘 标签A' in out, out
    code, out, kept = save_rows(mod, d, 'boss', [], 'T1', tag='标签A', why='到底')
    assert '下一件：第 4 件 智联招聘 标签C' in out, out
    assert call(mod, 'task', 'fail', '4')[0] == 2, '没写原因也记了没做完'
    assert call(mod, 'task', 'done', '9')[0] == 2


def t_task_resume_when_all_done(mod, d):
    setup(mod)
    assert '没有未完成的任务' in call(mod, 'task', 'resume')[1]
    call(mod, 'task', 'set', 'boss')
    call(mod, 'task', 'done', '1')
    code, out = call(mod, 'task', 'resume')
    assert code == 0 and '没有未完成的任务' in out and '都做完了' in out and '接着做' not in out, out


# ---------- 碰到安全验证 ----------
def t_verify_default_skips_platform(mod, d):
    setup(mod)
    assert '先跳过这个平台' in call(mod, 'config')[1], '没选时应按「先跳过这个平台」'
    call(mod, 'task', 'set', 'boss:推荐', 'boss:标签A', 'zhilian:标签B')
    code, out = call(mod, 'task', 'verify', '1')
    assert code == 0 and '下一件：第 3 件 智联招聘 标签B' in out, out
    assert _tasks(d) == [('boss', '推荐', 'unfinished'), ('boss', '标签A', 'unfinished'), ('zhilian', '标签B', 'todo')], _tasks(d)
    code, out, kept = save_rows(mod, d, 'zhilian', [], 'T1', tag='标签B', why='到底')
    assert '做完 1 件，没做完 2 件' in out and '碰到安全验证' in out, out
    assert '从第 1 件接着做' in call(mod, 'task', 'resume')[1], '处理完验证说继续，应从卡住的那件接上'


def t_verify_stop_all(mod, d):
    setup(mod)
    assert call(mod, 'config', '--verify', 'B')[0] == 0
    assert '全部停下' in call(mod, 'config')[1]
    call(mod, 'task', 'set', 'boss:推荐', 'zhilian:标签B')
    code, out = call(mod, 'task', 'verify', '1')
    assert '全部停下' in out and '下一件' not in out, out
    assert _tasks(d) == [('boss', '推荐', 'unfinished'), ('zhilian', '标签B', 'todo')], _tasks(d)
    assert '从第 1 件接着做' in call(mod, 'task', 'resume')[1]
    assert call(mod, 'config', '--verify', '随便')[0] == 2
    assert call(mod, 'config', '--verify', 'A')[0] == 0
    assert json.load(open(os.path.join(d, 'config.json')))['on_verify'] == 'skip'



def t_not_logged_in_stops_all(mod, d):
    """没登录：不管安全验证选哪种都全部停下，后面几件不做；继续前先核实登录。"""
    setup(mod)
    call(mod, 'task', 'set', 'zhilian:标签A', 'boss:推荐', 'zhilian:标签B')
    code, out = call(mod, 'task', 'login', '1')
    assert code == 0 and '全部停下' in out and '不替使用者登录' in out and 'window.__sLogin()' in out, out
    assert '下一件' not in out, '没登录还往下做：' + out
    assert _tasks(d) == [('zhilian', '标签A', 'unfinished'), ('boss', '推荐', 'todo'), ('zhilian', '标签B', 'todo')], _tasks(d)
    code, out = call(mod, 'task', 'resume')
    assert '从第 1 件接着做' in out and '先核实已登录' in out, '继续前没提醒核实登录：' + out
    # 扫到一半掉线：save 存下读到的，记没做完，同样停下
    code, out, kept = save_rows(mod, d, 'zhilian', [R('z1', '戊己', '运营')], 'T1', tag='标签A', why='没登录')
    assert '没做完（没登录）' in out and '全部停下' in out and '下一件' not in out, out
    assert _tasks(d)[0] == ('zhilian', '标签A', 'unfinished'), _tasks(d)
    assert call(mod, 'task', 'login', '9')[0] == 2


# ---------- 和页面脚本用同一套公司名规则 ----------
NODE_MATCH = r"""
const vm = require('vm'), fs = require('fs');
const ctx = { console }; ctx.window = ctx;
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(process.argv[1], 'utf8'), ctx);
console.log(JSON.stringify(JSON.parse(process.argv[2]).map(([a, b]) => [ctx.__sCoNorm(a), ctx.__sCoEq(a, b), ctx.__sJobNorm(a)])));
"""
MATCH_PAIRS = [
    ('甲乙科技', '示例市甲乙科技有限公司'), ('示例省示例市甲乙科技股份有限公司', '甲乙科技有限公司'),
    ('甲乙（示例）科技', '甲乙科技'), ('示例市甲乙丙丁科技...', '示例市甲乙丙丁科技发展有限公司'),
    ('庚辛壬癸信息…', '庚辛壬癸信息技术有限公司'), ('甲乙', '丙甲乙丁科技'), ('庚辛科技', '庚辛商贸'),
    ('甲乙', '甲乙集团'), ('Abc 科技', 'abc科技有限公司'), ('甲', '甲乙'), ('示例集团有限公司', '示例'),
    ('人事行政专员（双休）', '行政人事专员'), ('运营专员/助理', '运营专员'), ('【急招】前台 · 文员', '前台文员'),
    ('甲乙科技', '示例市示例新区甲乙科技有限公司'), ('甲乙科技', '示例省示例区甲乙科技有限公司'),
    ('甲乙科技', '示例县甲乙科技有限公司'), ('甲乙科技', '示例集团下属分支甲乙科技'),
    ('行政专员-双休', '行政专员'), ('项目专员（软件交付）—双休-五险一金', '项目专员'), ('销售助理-双休+五险一金', '销售助理'),
    ('行政专员-出差补助', '行政专员'), ('人事专员（实习）-包吃住', '人事专员'),
]


def t_region_prefix(mod, d):
    """公司全称前面带省、市、区、县的地名，和简称认作同一家；前面一长串不是地名的字不认。"""
    for full in ('示例市示例新区甲乙科技有限公司', '示例省示例区甲乙科技有限公司', '示例县甲乙科技有限公司', '示例市甲乙科技有限公司'):
        assert mod.co_eq('甲乙科技', full), '带地名前缀的全称没认出：' + full
    assert not mod.co_eq('甲乙科技', '示例集团下属分支甲乙科技'), '前面一长串不是地名的字也被当成地名'
    assert not mod.co_eq('甲乙', '丙甲乙丁科技'), '前面只有一个字也被当成地名'


def t_match_same_as_page(mod, d):
    js = os.path.join(os.path.dirname(os.path.abspath(mod.__file__)), 'page', 'common.js')
    r = subprocess.run(['node', '-e', NODE_MATCH, js, json.dumps(MATCH_PAIRS, ensure_ascii=False)],
                       capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    for (a, b), want in zip(MATCH_PAIRS, json.loads(r.stdout)):
        got = [mod.co_norm(a), mod.co_eq(a, b), mod.job_norm(a)]
        assert got == want, '公司/岗位比对和页面脚本不一致：%s / %s → jobscan.py %s，页面 %s' % (a, b, got, want)


def _doc(mod, name):
    return open(os.path.join(os.path.dirname(os.path.abspath(mod.__file__)), name), encoding='utf-8').read()


def _guide(text):
    m = re.search(r'<!-- 新手引导开始.*?-->\n(.*?)<!-- 新手引导结束 -->', text, re.S)
    return m.group(1) if m else None


GUIDE_MUST = ('### 它能做什么', '### 它不做什么', '### 第一次使用时会问你', '### 能改的设置', '黑名单', '推荐 7 天',
              '不打招呼、不投递', '不查看、不回复消息', '看过的不再列', '投过的不再列', '同公司同岗位只留一条', '标题相近', '不想看的关键词',
              '求职期望', '不按关键词搜索', '碰到安全验证', '先跳过这个平台', '全部停下', '「继续」',
              '先扫哪个平台', '「开始」', '「全部开始」', '开始智联', '关注清单', 'watch add', 'watch list', 'watch remove', 'config --days', 'config --boss-active', 'config --boss-rest', '2 周内活跃', 'config --mode', 'config --verify', 'config --first', 'config --start', 'block add', 'block list', 'block remove',
              'keyword add', 'keyword list', 'keyword remove', 'applied add', 'applied list', 'applied remove', 'seen clear',
              '### 扫描时请留意', '没登录会停下', '第一次先试一个标签', '选择允许', '保持页面在前台')


def doc_problems(skill, readme):
    """两份文档该写的写了没有。返回缺的项，空 = 都齐。"""
    g1 = _guide(skill)
    if not g1:
        return ['SKILL.md 里找不到新手引导']
    bad = ['SKILL 新手引导缺少：' + m for m in GUIDE_MUST if m not in g1]
    head = g1.split('### 它能做什么')[0]
    if '求职期望' not in head or '不按关键词搜索' not in head:
        bad.append('新手引导开头没先交代「先在两个平台设好求职期望」')
    if 'Claude in Chrome' not in head or '登录 Boss直聘、智联招聘' not in head:
        bad.append('新手引导开头没交代「准备好浏览器」：Chrome 扩展或 macOS Apple 事件授权、登录两个平台')
    if 'Antigravity' not in head or 'Codex' not in head:
        bad.append('新手引导开头没交代已实测环境与 Codex/ChatGPT 边界')
    if '求职期望' not in readme or '不按关键词搜索' not in readme:
        bad.append('README 没写先设好求职期望、不按关键词搜索')
    support = re.search(r'## 谁能用[^\n]*\n(.*?)\n## ', readme, re.S)
    if not support or not all(k in support.group(1) for k in ('Claude Code', 'Antigravity', 'ChatGPT', 'Codex', '允许 Apple 事件中的 JavaScript')):
        bad.append('README「谁能用」缺实测环境或 ChatGPT/Codex 说明')
    prep = re.search(r'### 2\. 打通你的 Chrome\n(.*?)\n### ', readme, re.S)
    if not prep or not all(k in prep.group(1) for k in ('chromewebstore.google.com', '同一个组织', '/chrome', '允许 Apple 事件中的 JavaScript')):
        bad.append('README 缺「打通你的 Chrome」完整步骤：扩展链接、同一账号同一组织、/chrome、macOS Apple 事件授权')
    if '**Claude 提示浏览器扩展没连上怎么办？**' not in readme:
        bad.append('README 常见问题缺：**Claude 提示浏览器扩展没连上怎么办？**')
    env = re.search(r'## 适用环境\n(.*?)\n## ', skill, re.S)
    if not env or not all(k in env.group(1) for k in ('Claude Code', 'Antigravity', 'Codex', '无登录浏览器面板', '不要改用')):
        bad.append('SKILL.md 缺「适用环境」：已实测环境、Codex 说明、不用无登录内置浏览器、不改用变通办法')
    first_use = re.search(r'## 第一次用[^\n]*\n(.*?)\n## ', skill, re.S)
    if not first_use or 'tabs_context_mcp' not in first_use.group(1) or '打通你的 Chrome' not in first_use.group(1):
        bad.append('SKILL.md「第一次用」没写检查浏览器、没连上按 README「打通你的 Chrome」带使用者连好')
    for q in ('**扫出来的岗位不对口怎么办？**', '**额度用完或对话中断怎么办？**'):
        if q not in readme:
            bad.append('README 常见问题缺：' + q)
    red = re.search(r'## 红线[^\n]*\n(.*?)\n## ', skill, re.S)
    if not red or '求职期望' not in red.group(1):
        bad.append('SKILL.md 红线里没写不替使用者改求职期望和账号设置')
    if '还没设求职期望' not in skill:
        bad.append('SKILL.md 没写找不到期望标签、平台提示没设求职期望时要停下')
    if '复核.md' not in skill or '必须' not in skill.split('## 按使用者自己的规则复核', 1)[-1]:
        bad.append('SKILL.md「按使用者自己的规则复核」没强制要求将复核结果落盘写入复核.md')
    if '待定：无双休标注' not in skill or '手机 App 核对' not in skill:
        bad.append('SKILL.md 缺智联作息「交手机 App 核对」专流程')
    if '1–10' not in skill:
        bad.append('SKILL.md 未同步更新为 1–10 项可选核查经验')
    if 'config --freq' not in skill or 'config --reappear' not in skill:
        bad.append('SKILL.md 设置表缺少 --freq 或 --reappear 配置说明')
    if '顺带问一句是否需要一起开启按首次发布区间跳过长期老岗' in skill:
        bad.append('SKILL.md 仍在智联首次扫完后劝开 --old 一刀切')
    if 'profile' not in skill or 'company check' not in skill or 'review archive' not in skill:
        bad.append('SKILL.md 缺少精炼沉淀命令（profile / company / review）说明')
    if '先拉一下再开扫' not in skill or '同步意向' in skill:
        bad.append('SKILL.md 开扫前确认文案未改用大白话')
    desc = re.search(r'^description:(.*)$', skill, re.M)
    if not desc or '继续扫描' not in desc.group(1) or '接着上次' not in desc.group(1):
        bad.append('SKILL.md 的 description 里没有「继续扫描」「接着上次」，新对话里说继续触发不了')
    return bad


def t_docs_complete(mod, d):
    skill, readme = _doc(mod, 'SKILL.md'), _doc(mod, 'README.md')
    bad = doc_problems(skill, readme)
    assert not bad, '；'.join(bad)
    # 反例：少了下面任何一样，检查都必须报出来
    g = _guide(skill)
    notice = g.split('### 它能做什么')[0]
    for desc, s2, r2 in (
        ('SKILL 新手引导缺少不投递规则', skill.replace('不打招呼、不投递', '支持筛选'), readme),
        ('新手引导开头没交代求职期望', skill.replace(notice, ''), readme),
        ('README 没交代求职期望', skill, readme.replace('求职期望', '筛选条件')),
        ('README 常见问题没有不对口', skill, readme.replace('**扫出来的岗位不对口怎么办？**', '')),
        ('README 常见问题没有中断', skill, readme.replace('**额度用完或对话中断怎么办？**', '')),
        ('SKILL 红线没有不改求职期望', skill.replace('不修改平台上的求职期望', '不修改平台上的设置'), readme),
        ('SKILL 没写没设求职期望要停下', skill.replace('还没设求职期望', '没设期望'), readme),
        ('SKILL description 没有继续扫描', re.sub(r'^(description:.*?)继续扫描', r'\1', skill, flags=re.M), readme),
        ('SKILL 设置表没有验证处理', skill.replace('config --verify', 'config --x'), readme),
        ('SKILL 新手引导没有 Boss HR 活跃度配置', skill.replace('config --boss-active', 'config --y'), readme),
        ('SKILL 新手引导没有 Boss 双休缺失配置', skill.replace('config --boss-rest', 'config --z'), readme),
        ('SKILL 复核阶段未强制写入复核归档', skill.replace('复核.md', '复核记录'), readme),
        ('SKILL 缺智联交手机核对流程', skill.replace('待定：无双休标注', '待核'), readme),
        ('SKILL 经验包编号未更新为 1–10', skill.replace('1–10', '1–8'), readme),
        ('SKILL 缺高频刷新或久别重逢配置', skill.replace('config --freq', 'config --f'), readme),
        ('SKILL 缺久别重逢配置', skill.replace('config --reappear', 'config --r'), readme),
        ('SKILL 没写第一次会问碰到验证怎么办', skill.replace('先跳过这个平台', '先跳过'), readme),
        ('新手引导开头没交代浏览器', skill.replace('Claude in Chrome 扩展', '扩展'), readme),
        ('新手引导开头没提登录两个平台', skill.replace('这个 Chrome 里登录 Boss直聘、智联招聘。', '这个 Chrome 里登录。'), readme),
        ('README 谁能用缺 Codex 说明', skill, readme.replace('Codex', 'Other')),
        ('README 没有打通你的 Chrome 一节', skill, readme.replace('### 2. 打通你的 Chrome\n', '### 2. 浏览器\n')),
        ('README 打通浏览器没写同一个组织', skill, readme.replace('同一个组织', '组织')),
        ('README 常见问题没有扩展没连上', skill, readme.replace('**Claude 提示浏览器扩展没连上怎么办？**', '')),
        ('SKILL 没有适用环境', skill.replace('## 适用环境\n', '## 环境\n'), readme),
        ('SKILL 适用环境没写无登录面板限制', skill.replace('无登录浏览器面板', '其他面板'), readme),
        ('新手引导没有扫描时请留意', skill.replace('### 扫描时请留意', '### 留意'), readme),
        ('新手引导没提先试一个标签', skill.replace('第一次先试一个标签', '先试试'), readme),
        ('第一次用没检查浏览器', skill.replace('4. 检查浏览器：执行 `tabs_context_mcp`', '4. 检查浏览器：看一下'), readme),
    ):
        assert doc_problems(s2, r2), '反例「%s」没被查出来' % desc


def t_version_same(mod, d):
    skill = re.search(r'^description:.*版本 (\d+\.\d+\.\d+)。\s*$', _doc(mod, 'SKILL.md'), re.M)
    readme = re.search(r'\A# .* (\d+\.\d+\.\d+)\n', _doc(mod, 'README.md'))
    log = re.search(r'^## (\d+\.\d+\.\d+) ', _doc(mod, 'CHANGELOG.md'), re.M)
    assert skill and readme and log, '版本号没写全：SKILL.md 描述末尾、README 标题、CHANGELOG 最新一条都要有'
    assert skill.group(1) == readme.group(1) == log.group(1), '三处版本号不一致：%s / %s / %s' % (
        skill.group(1), readme.group(1), log.group(1))


def name_problems(skill, readme):
    """工具名四处一致：SKILL.md 的 name、README 标题、仓库地址、安装路径；中文名在 SKILL 描述开头、SKILL 标题、README 标题一致。"""
    name = re.search(r'^name: *(\S+)\s*$', skill, re.M)
    title = re.search(r'\A# (\S+) ([a-z0-9-]+) \d+\.\d+\.\d+\n', readme)
    if not name or not title:
        return ['SKILL.md 的 name 或 README 标题「# 中文名 英文名 版本」格式不对']
    n, cn = name.group(1), title.group(1)
    bad = [] if title.group(2) == n else ['README 标题的英文名 %s 和 SKILL.md 的 name %s 不一致' % (title.group(2), n)]
    repos = set(re.findall(r'github\.com/[^/\s]+/([A-Za-z0-9_-]+)', readme))
    if repos != {n}:
        bad.append('README 里的仓库地址名字不一致：%s（应为 %s）' % ('、'.join(sorted(repos)) or '没有', n))
    dirs = set(re.findall(r'~/\.claude/skills/([A-Za-z0-9_-]+)', readme))
    if dirs != {n}:
        bad.append('README 里的安装路径名字不一致：%s（应为 %s）' % ('、'.join(sorted(dirs)) or '没有', n))
    if 'Download ZIP' in readme and '改名为 `%s`' % n not in readme:
        bad.append('README 里下载 ZIP 后要改成的文件夹名不是 ' + n)
    if not re.search(r'^description: %s，' % re.escape(cn), skill, re.M) or ('\n# %s\n' % cn) not in skill:
        bad.append('SKILL.md 的描述开头或标题不是中文名「%s」' % cn)
    return bad


def t_name_same(mod, d):
    skill, readme = _doc(mod, 'SKILL.md'), _doc(mod, 'README.md')
    bad = name_problems(skill, readme)
    assert not bad, '；'.join(bad)
    n = re.search(r'^name: *(\S+)', skill, re.M).group(1)
    # 反例：任何一处名字不一样，都必须查出来
    for desc, s2, r2 in (
        ('SKILL 的 name 改了', skill.replace('name: ' + n, 'name: other-name', 1), readme),
        ('README 标题改了', skill, readme.replace(' %s 1.' % n, ' other-name 1.', 1)),
        ('一个仓库地址没改', skill, readme.replace('/%s/issues' % n, '/other-name/issues', 1)),
        ('一个安装路径没改', skill, readme.replace('skills/%s/jobscan.py' % n, 'skills/other-name/jobscan.py', 1)),
        ('ZIP 改名没改', skill, readme.replace('改名为 `%s`' % n, '改名为 `other-name`')),
        ('SKILL 描述开头不是中文名', re.sub(r'^description: [^，]+，', 'description: 别的名字，', skill, flags=re.M), readme),
    ):
        assert name_problems(s2, r2), '反例「%s」没被查出来' % desc


def t_watch_company_and_word(mod, d):
    setup(mod)
    assert '关注清单是空的' in call(mod, 'watch', 'list')[1]
    assert '没设（不额外提醒）' in call(mod, 'config')[1]
    code, out = call(mod, 'watch', 'add', '--company', '甲乙科技', '甲乙科技', '--word', '英语', 'AI', 'ai')
    assert code == 0 and '当前共 1 家公司、2 个词' in out and '公司:甲乙科技' in out and '词:英语' in out and '词:AI' in out, out
    assert '公司：甲乙科技' in call(mod, 'config')[1] and '词：英语、AI' in call(mod, 'config')[1]
    lst = call(mod, 'watch', 'list')[1]
    assert '1. [公司] 甲乙科技' in lst and '2. [词] 英语' in lst and '3. [词] AI' in lst, lst
    rows = [
        R('z1', '示例市甲乙科技有限公司', '行政专员', desc='日常行政工作'),
        R('z2', '丙丁商贸', '销售内勤', sk='Office、AI工具'),
        R('z3', '戊己实业', '人事专员', desc='普通人事工作'),
    ]
    code, out, kept = save_rows(mod, d, 'zhilian', rows, 'T1', tag='推荐', why='超过7天')
    assert code == 0 and kept == ['z1', 'z2', 'z3'], (code, out, kept)
    assert '特别留意命中 2 条' in out, out
    md = open(re.search(r'结果文件：(.*\.md)', out).group(1), encoding='utf-8').read()
    assert '## 特别留意命中' in md and '关注公司：甲乙科技' in md and '关注词：AI' in md, md
    assert md.index('## 特别留意命中') < md.index('| # | 公司 | 岗位 | 地点 | 薪资 | 发布时间 | 链接 |'), md
    assert call(mod, 'watch', 'remove', '2')[0] == 0
    assert '英语' not in call(mod, 'watch', 'list')[1]
    assert call(mod, 'watch', 'remove', '甲乙科技')[0] == 0
    assert '甲乙科技' not in call(mod, 'watch', 'list')[1]


def t_watch_rejects_bad_args(mod, d):
    setup(mod)
    assert call(mod, 'watch', 'add')[0] == 2
    assert call(mod, 'watch', 'add', '甲乙科技')[0] == 2
    assert call(mod, 'watch', 'add', '--word', '有 空格')[0] == 2
    assert call(mod, 'watch', 'add', '--word', 'a|b')[0] == 2
    assert call(mod, 'watch', 'remove', '不存在')[0] == 2
    assert call(mod, 'watch', 'unknown')[0] == 2


def t_start_all_keyword(mod, d):
    setup(mod)
    call(mod, 'config', '--first', 'boss')
    code, out = call(mod, 'task', 'set', '全部开始')
    assert code == 0 and '1. Boss直聘 全部标签' in out and '2. 智联招聘 全部标签' in out, out


def t_alias_add_list_remove_and_match(mod, d):
    setup(mod)
    assert call(mod, 'alias', 'add', '只有一个')[0] == 2
    code, out = call(mod, 'alias', 'add', '品牌甲', '示例市工商全称乙科技有限公司')
    assert code == 0 and '品牌甲 = 示例市工商全称乙科技有限公司' in out, out
    assert call(mod, 'alias', 'add', '品牌甲', '另一家公司')[0] == 2, '重合别名组应拒绝'
    assert '1. 品牌甲 = 示例市工商全称乙科技有限公司' in call(mod, 'alias', 'list')[1]
    assert mod.co_eq('品牌甲', '示例市工商全称乙科技有限公司')
    assert not mod.co_eq('品牌甲', '丙丁商贸')
    assert call(mod, 'block', 'add', '品牌甲')[0] == 0
    assert call(mod, 'applied', 'add', '品牌甲', '行政专员', '--platform', 'boss')[0] == 0
    code, out, kept = save_rows(mod, d, 'zhilian', [R('z1', '示例市工商全称乙科技有限公司', '行政专员'), R('z2', '丙丁商贸', '行政专员')], 'T1')
    assert kept == ['z2'] and '投过的跳过 1 条' in out, (kept, out)
    assert mod.page_cfg('boss')['aliases'] == [['品牌甲', '示例市工商全称乙科技有限公司']]
    assert call(mod, 'alias', 'remove', '1')[0] == 0
    assert not mod.co_eq('品牌甲', '示例市工商全称乙科技有限公司')


def t_keyword_tag_summary_preview(mod, d):
    setup(mod)
    assert save_rows(mod, d, 'zhilian', [
        R('z1', '甲乙科技', '市场推广专员'),
        R('z2', '丙丁商贸', '市场推广助理'),
        R('z3', '戊己信息', '行政专员'),
    ], 'T1', tag='行政')[0] == 0
    code, sum_out = call(mod, 'keyword', 'summary')
    assert code == 0 and '行政（共 3 个不同岗位）' in sum_out and '市场推广专员' in sum_out, sum_out
    code, pre_out = call(mod, 'keyword', 'preview', '--tag', '行政', '推广')
    assert code == 0 and '共命中 2 条' in pre_out and '市场推广专员' in pre_out and '否定表述' in pre_out, pre_out
    code2, pre_out2 = call(mod, 'keyword', 'preview', '--tag', '行政', '推广', '行政')
    assert code2 == 0 and '只读预览「推广」' in pre_out2 and '只读预览「行政」' in pre_out2 and '共命中 1 条' in pre_out2, pre_out2
    assert call(mod, 'keyword', 'add', '--tag', '行政', '推广')[0] == 0
    assert '标签「行政」：1.推广' in call(mod, 'keyword', 'list')[1]
    assert mod.page_cfg('zhilian')['tag_keywords'] == {'行政': ['推广']}
    assert call(mod, 'keyword', 'remove', '--tag', '行政', '推广')[0] == 0
    assert mod.page_cfg('zhilian')['tag_keywords'] == {}


def t_repost_remind_and_sync(mod, d):
    setup(mod)
    assert call(mod, 'config', '--reposts', 'remind')[0] == 0
    assert '照常列出并提醒' in call(mod, 'config')[1]
    # 同步线上名单：总数不符拒绝，总数相符写入
    sync_f = os.path.join(d, 'sync.json')
    json.dump({'total': 9, 'rows': [{'company': '甲乙科技', 'job': '行政专员', 'appliedAt': '2025-05-01'}]}, open(sync_f, 'w', encoding='utf-8'))
    assert call(mod, 'applied', 'sync', sync_f)[0] == 2
    json.dump({'total': 2, 'rows': [
        {'company': '甲乙科技', 'job': '行政专员', 'appliedAt': '2025-05-01'},
        {'company': '丙丁商贸', 'job': '文员'},
    ]}, open(sync_f, 'w', encoding='utf-8'))
    code, out = call(mod, 'applied', 'sync', sync_f)
    assert code == 0 and '新增 2 条' in out, out
    # 投递前先看过旧编号 z0；之后公司在 2025-05-10 重发 z1：应放行并附提醒；同一天 2025-05-01 发布的 z2 仍跳过
    mod.dump('seen.json', [{'platform': 'zhilian', 'id': 'z0', 'company': '甲乙科技', 'job': '行政专员', 'date': '2025-04-20'}])
    code, out, kept = save_rows(mod, d, 'zhilian', [
        R('z1', '示例市甲乙科技有限公司', '行政专员', pub='2025-05-10 10:00:00'),
        R('z2', '示例市甲乙科技有限公司', '行政专员', pub='2025-05-01 20:00:00'),
    ], 'T1')
    assert code == 0 and kept == ['z1'], (kept, out)
    assert '其中 1 条是你以前投过、现在重新发布的' in out and '投过的跳过 1 条' in out, out
    body = _md(out)
    assert '## 投过重发提醒' in body and '2025-05-01 投过' in body, body
    # 这个重发编号 z1 下次再扫应按看过跳过
    code, out, kept = save_rows(mod, d, 'zhilian', [R('z1', '示例市甲乙科技有限公司', '行政专员', pub='2025-05-10 10:00:00')], 'T2')
    assert kept == [] and '看过的跳过 1 条' in out, (kept, out)
    # 用户选择再投：更新日期并保留原日期到 earlier
    assert call(mod, 'applied', 'add', '--id', 'z1', '--date', '2025-05-11')[0] == 0
    al = json.load(open(os.path.join(d, 'applied.json'), encoding='utf-8'))
    assert al[0]['date'] == '2025-05-11' and al[0]['earlier'][0]['date'] == '2025-05-01', al[0]


def t_find_queries_and_limits(mod, d):
    setup(mod)
    assert save_rows(mod, d, 'zhilian', [
        R('z1', '示例市甲乙科技有限公司', '行政专员', sal='6-8K'),
        R('z2', '丙丁商贸', '数据分析师', sal='8-10K'),
        R('z3', '丙丁商贸', '行政专员', sal='5-6K'),
    ], 'T1', tag='行政', why='到底')[0] == 0
    code, out = call(mod, 'find', '--company', '甲乙', '--job', '行政')
    assert code == 0 and '#1 示例市甲乙科技有限公司 / 行政专员' in out and '已翻完' in out, out
    bf = os.path.join(d, 'q.json')
    json.dump({'queries': [{'company': '甲乙', 'job': '行政'}, {'job': '数据分析师'}, {'company': '不存在公司', 'job': '文员'}]}, open(bf, 'w', encoding='utf-8'))
    code, out = call(mod, 'find', '--batch', bf)
    assert code == 0 and '1 条匹配' in out and '0 匹配（没找到）' in out, out
    assert '丙丁商贸 / 行政专员' not in out, '甲乙的行政不能和丙丁交叉匹配：' + out
    json.dump({'queries': [{'job': 'a'}, {'job': 'b'}, {'job': 'c'}, {'job': 'd'}]}, open(bf, 'w', encoding='utf-8'))
    assert call(mod, 'find', '--batch', bf)[0] == 2, '超过 3 个条件必须拒绝'
    call(mod, 'applied', 'add', '--id', 'z1')
    assert '[已投]' in call(mod, 'find', '--company', '甲乙', '--job', '行政')[1]


def t_dump_creates_backups(mod, d):
    setup(mod)
    call(mod, 'config', '--days', '3')
    baks = os.listdir(os.path.join(d, 'backups'))
    assert any(b.endswith('_config.json') for b in baks), '修改配置前没自动留备份：%s' % baks


def t_references_present(mod, d):
    root = os.path.dirname(os.path.abspath(mod.__file__))
    for name, must in (
        ('references/job-review.md', '六项核查'),
        ('references/experience-pack.md', '默认全部关闭'),
        ('references/greetings.md', '当前就业状态'),
        ('references/questions.md', '互斥项校验'),
    ):
        p = os.path.join(root, name)
        assert os.path.exists(p), '缺少参考文档：' + name
        txt = open(p, encoding='utf-8').read()
        assert must in txt and '/Users/' not in txt and 'boss_jobs_log.json' not in txt, name
    ep = open(os.path.join(root, 'references/experience-pack.md'), encoding='utf-8').read()
    for s in ('17 类明确负面问题', '5 类普通吐槽', '手机门店 / 通讯营业厅', '医美 / 保健 / 养老', '待定：无双休标注', '硬性要求「已离职」'):
        assert s in ep, '经验包缺少：' + s
    for bad_s in ('养老行业不算避坑', '不包含「无责底薪」', '卖手机的门店 / 通讯店', '不触发'):
        assert bad_s not in ep, '经验包不应保留工程/旧文案：' + bad_s


def t_zhilian_freq_and_heartbeat(mod, d):
    setup(mod)
    today = mod.datetime.date.today()
    d0 = (today - mod.datetime.timedelta(days=10)).isoformat()
    d1 = (today - mod.datetime.timedelta(days=6)).isoformat()
    d2 = (today - mod.datetime.timedelta(days=2)).isoformat()
    d_old = (today - mod.datetime.timedelta(days=25)).isoformat()
    # 先存第 1 次刷新（d0），同编号再次扫到同一时间戳不重复计数；页面 @@S 心跳回传 d1 新刷新后变成 2 次
    assert save_rows(mod, d, 'zhilian', [R('z1', '示例市甲乙科技有限公司', '行政专员', pub=d0 + ' 01:10:00')], 'T1')[0] == 0
    seen = json.load(open(os.path.join(d, 'seen.json'), encoding='utf-8'))
    assert seen[0]['publishes'] == [d0 + ' 01:10'], seen[0]
    # 模拟页面跳过 z1 并通过 @@S 回传 d1 新刷新，再验证同公司同岗位新编号 z2 带同一天时间戳 d1 不会重复计数
    f2 = os.path.join(d, 'page_zhilian_hb.txt')
    hb_txt = page_text(mod, 'zhilian', rows=[], counts={'total': 1, 'kept': 0, 'seen': 1}, when='T2')
    hb_txt = hb_txt.replace('@@E|1|1|0', '@@S|%s~%s_01:10 @@E|1|1|1' % (mod.seen_code('z1'), d1))
    open(f2, 'w', encoding='utf-8').write(hb_txt)
    code, out = call(mod, 'save', 'zhilian', f2)
    assert code == 0 and '看过的跳过 1 条' in out and '高频刷新' not in out, out
    seen = json.load(open(os.path.join(d, 'seen.json'), encoding='utf-8'))
    assert seen[0]['publishes'] == [d0 + ' 01:10', d1 + ' 01:10'], seen[0]
    code2, out2, kept2 = save_rows(mod, d, 'zhilian', [R('z2', '甲乙科技', '行政专员', pub=d1 + ' 01:10:00')], 'T2b')
    assert code2 == 0 and kept2 == [] and '看过的跳过 1 条' in out2 and '高频刷新' not in out2, out2
    seen = json.load(open(os.path.join(d, 'seen.json'), encoding='utf-8'))
    assert seen[0]['publishes'] == [d0 + ' 01:10', d1 + ' 01:10'], seen[0]
    # 同一天重复扫描相同 publishTime 不算第 3 次；当第 3 个独立刷新时间戳 d2 出现时（14 天内 ≥ 3 次）被高频刷新拦下
    code, out, kept = save_rows(mod, d, 'zhilian', [
        R('z3', '甲乙科技', '行政专员', pub=d2 + ' 09:20:00'),
        R('z_other', '丙丁商贸', '文员', pub=d2 + ' 10:00:00'),
    ], 'T3')
    assert code == 0 and kept == ['z_other'], (kept, out)
    assert '高频刷新老岗跳过 1 条（14 天内刷新达 3 次及以上）' in out, out
    body = _md(out)
    assert '## 高频刷新老岗跳过的' in body and '14 天内观测到刷新 3 次' in body and d2 + ' 09:20' in body, body
    # 调宽到 14,5（> 4 次），或窗口外（25 天前）的旧刷新不算进 14 天内
    assert call(mod, 'config', '--freq', '14,5')[0] == 0
    seen = json.load(open(os.path.join(d, 'seen.json'), encoding='utf-8'))
    seen[0]['publishes'] = [d_old + ' 01:00', d0 + ' 01:10', d1 + ' 01:10', d2 + ' 09:20']
    mod.dump('seen.json', seen)
    code, out, kept = save_rows(mod, d, 'zhilian', [R('z4', '甲乙科技', '行政专员', pub=today.isoformat() + ' 10:00:00')], 'T4')
    assert code == 0 and '看过的跳过 1 条' in out and '高频刷新' not in out, '共4次在14天内应放给普通看过，不应触发14,5：' + out
    # Boss 不受智联高频刷新规则影响
    assert call(mod, 'config', '--freq', '14,3')[0] == 0
    assert save_rows(mod, d, 'boss', [R('b1', '甲乙科技', '行政专员', '')], 'B1')[0] == 0
    code, out, kept = save_rows(mod, d, 'boss', [R('b2', '甲乙科技', '行政专员', '')], 'B2')
    assert code == 0 and '高频刷新' not in out and '看过的跳过 1 条' in out, out


def t_seen_reappear_and_boss_heartbeat(mod, d):
    setup(mod)
    today = mod.datetime.date.today()
    old_d = (today - mod.datetime.timedelta(days=400)).isoformat()
    recent_d = (today - mod.datetime.timedelta(days=10)).isoformat()
    mod.dump('seen.json', [
        {'platform': 'boss', 'id': 'b_gone', 'company': '甲乙科技', 'job': '行政专员', 'date': old_d, 'hr': '旧HR'},
        {'platform': 'boss', 'id': 'b_alive', 'company': '丙丁商贸', 'job': '文员', 'date': old_d},
        {'platform': 'boss', 'id': 'b_mix1', 'company': '戊己信息', 'job': '人事专员', 'date': old_d},
        {'platform': 'boss', 'id': 'b_mix2', 'company': '戊己信息', 'job': '人事专员', 'date': recent_d},
        {'platform': 'boss', 'id': 'b_app', 'company': '庚辛科技', 'job': '助理', 'date': old_d},
    ])
    assert call(mod, 'applied', 'add', '庚辛科技', '助理', '--platform', 'boss')[0] == 0
    # b_gone 已满 400 天 >= 365 天，不应交给页面跳过；b_alive 若被 @@S 更新，则仍在静默期
    codes_before = mod.seen_codes('boss')
    assert mod.seen_code('b_gone') not in codes_before and mod.seen_code('b_mix2') in codes_before, codes_before
    # 先用 @@S 心跳证明 b_alive 今天还在榜（必须先把 b_alive 设成在 365 天内的样本或直接在 seen 里给最近一次出现）
    seen = json.load(open(os.path.join(d, 'seen.json'), encoding='utf-8'))
    seen[1]['last_seen'] = recent_d
    mod.dump('seen.json', seen)
    assert mod.seen_code('b_alive') in mod.seen_codes('boss')
    f = os.path.join(d, 'page_boss_re.txt')
    txt = page_text(mod, 'boss', rows=[
        R('b_gone', '甲乙科技', '行政专员', '', hr='新HR'),
        R('b_mix_new', '戊己信息', '人事专员', ''),  # 虽然 b_mix1 是 400 天前，但 b_mix2 是 10 天前，不能放行！
        R('b_app', '庚辛科技', '助理', ''),          # 已投过的即使超过 365 天也不放行
    ], counts={'total': 4, 'kept': 3, 'seen': 1}, when='R1')
    txt = txt.replace('@@E|1|1|3', '@@S|%s @@E|1|1|4' % mod.seen_code('b_alive'))
    open(f, 'w', encoding='utf-8').write(txt)
    code, out = call(mod, 'save', 'boss', f)
    assert code == 0 and '留下 1 条' in out and '消失很久又重新出现的' in out and '投过的跳过 1 条' in out and '看过的跳过 2 条' in out, out
    body = _md(out)
    assert '## 久别重逢提醒' in body and '上次见于 ' + old_d in body and '招聘人：新HR / 旧HR' in body and '★时隔 400 天重现' in body, body
    # 重现后，b_gone 回到页面跳过名单，b_alive 的 last_seen 被 @@S 更新到今天，下次扫不再重复放行
    seen_after = json.load(open(os.path.join(d, 'seen.json'), encoding='utf-8'))
    b_alive_entry = next(x for x in seen_after if x['id'] == 'b_alive')
    b_gone_entry = next(x for x in seen_after if x['id'] == 'b_gone')
    assert b_alive_entry['last_seen'] == today.isoformat(), b_alive_entry
    assert b_gone_entry['last_seen'] == today.isoformat() and b_gone_entry['date'] == old_d, b_gone_entry
    assert mod.seen_code('b_gone') in mod.seen_codes('boss')
    code2, out2, kept2 = save_rows(mod, d, 'boss', [R('b_gone', '甲乙科技', '行政专员', '')], 'R2')
    assert kept2 == [] and '看过的跳过 1 条' in out2, (kept2, out2)
    # 关闭 --reappear off 后，过期旧记录也进页面跳过名单且不再放行
    mod.dump('seen.json', [{'platform': 'boss', 'id': 'b_old2', 'company': '壬癸科技', 'job': '文员', 'date': old_d}])
    assert mod.seen_code('b_old2') not in mod.seen_codes('boss')
    assert call(mod, 'config', '--reappear', 'off')[0] == 0
    assert mod.seen_code('b_old2') in mod.seen_codes('boss')
    code3, out3, kept3 = save_rows(mod, d, 'boss', [R('b_old2', '壬癸科技', '文员', '')], 'R3')
    assert kept3 == [] and '看过的跳过 1 条' in out3, (kept3, out3)


def t_profile_persists(mod, d):
    setup(mod)
    assert '还没记过' in call(mod, 'profile')[1]
    c, out = call(mod, 'profile', 'set', '--json', json.dumps({
        'rules': {'salary_min': '5000', 'commute': '不跨区'},
        'pack': {'configured': True, 'items': {'1': {'action': 'remind', 'threshold': '100万'}, '10': {'action': 'exclude', 'industries': [1, 6]}}, 'gap_policy': 'ask'},
        'background': {'tasks': ['会议纪要'], 'status': '已离职，目前没有工作', 'available': '随时到岗'},
    }, ensure_ascii=False))
    assert c == 0, out
    c2, out2 = call(mod, 'profile', 'set', '--hard', '双休', '--education', '本科', '--highlight', '3年行政经验')
    assert c2 == 0, out2
    shown = call(mod, 'profile')[1]
    assert '底薪门槛：5000' in shown and '硬条件：双休' in shown and '第1项(仅提醒，阈值 100万)' in shown and '行业序号 1,6' in shown
    assert '学历：本科' in shown and '做过的事：会议纪要' in shown and '3年行政经验' in shown and '轻确认一句' in shown
    assert any(b.endswith('_profile.json') for b in os.listdir(os.path.join(d, 'backups'))), '修改 profile 前没备份'
    assert call(mod, 'profile', 'clear')[0] == 0 and '还没记过' in call(mod, 'profile')[1]


def t_company_cache_and_alias(mod, d):
    setup(mod)
    call(mod, 'alias', 'add', '星河品牌', '示例市宇航科技有限公司')
    c, out = call(mod, 'company', 'save', '--company', '示例市宇航科技有限公司', '--business', '企业软件', '--reg-capital', '500万元', '--rest-clue', '同公司他岗写明双休', '--source', '智联公司页')
    assert c == 0 and '新增 1 家' in out, out
    g_out = call(mod, 'company', 'get', '星河品牌')[1]
    assert '企业软件' in g_out and '500万元' in g_out and '天前' in g_out, g_out
    chk = call(mod, 'company', 'check', '宇航科技', '没查过的甲公司')[1]
    assert '[已核过] 宇航科技' in chk and '[未查过] 没查过的甲公司' in chk, chk
    assert call(mod, 'company', 'remove', '1')[0] == 0 and '还没查过' in call(mod, 'company', 'get', '宇航科技')[1]


def t_review_resume_and_archive(mod, d):
    setup(mod)
    call(mod, 'task', 'set', 'boss:推荐')
    code, out, kept = save_rows(mod, d, 'boss', [R('b1', '甲乙科技', '行政专员', ''), R('b2', '丙丁商贸', '文员', '')], 'T1', tag='推荐', why='到底')
    assert code == 0 and kept == ['b1', 'b2'], out
    res_out = call(mod, 'task', 'resume')[1]
    assert '没有未完成的任务' in res_out and '2 条已扫出的岗位待精炼复核' in res_out, res_out
    nxt = call(mod, 'review', 'next')[1]
    assert '[b1]' in nxt and '[b2]' in nxt, nxt
    assert call(mod, 'review', 'mark', '--id', 'b1', '--status', 'exclude', '--reason', '单休')[0] == 0
    nxt2 = call(mod, 'review', 'next')[1]
    assert '[b1]' not in nxt2 and '[b2]' in nxt2, nxt2
    bad_md = os.path.join(d, 'bad_review.md')
    open(bad_md, 'w', encoding='utf-8').write('# Boss 复核\n\n## 各标签统计\n- 推荐：2 条\n\n## 合格清单\n- 丙丁商贸\n')
    assert call(mod, 'review', 'archive', '--platform', 'boss', '--file', bad_md)[0] == 2
    good_md = os.path.join(d, 'good_review.md')
    open(good_md, 'w', encoding='utf-8').write('# Boss 复核\n\n## 各标签统计\n- 推荐：2 条\n\n## 排除明细\n- 甲乙科技：单休\n\n## 合格清单\n- 丙丁商贸\n')
    ac, aout = call(mod, 'review', 'archive', '--platform', 'boss', '--file', good_md)
    assert ac == 0 and '_boss_复核.md' in aout and os.path.exists(aout.split('：', 1)[1].strip()), aout
    assert '已归档：' in call(mod, 'review', 'status')[1]


CASES = [v for k, v in sorted(globals().items()) if k.startswith('t_')]

# 错误写法：(说明, 原文, 改成)。每种都必须让上面至少一条用例不过。
MUTANTS = [
    ('alias 没传给页面', "'aliases': [list(g) for g in (cfg.get('aliases') or [])],", "'aliases': [],"),
    ('tag_keywords 没传给页面', "'tag_keywords': {k: list(v) for k, v in (cfg.get('tag_keywords') or {}).items() if v},", "'tag_keywords': {},"),
    ('find 超过 3 个条件不拦（默默截断）',
     "    if len(queries) > 3:\n        raise Stop('每批最多查 3 个条件（收到 %d 个），请分批查，不截断。' % len(queries))\n",
     "    queries = queries[:3]\n"),
    ('开启重发提醒后也不放行重发岗位', "            if _is_repost(r, e, cfg):", "            if False:"),
    ('写前不留备份', "    if name in BACKUP_FILES and os.path.exists(target):", "    if False:"),
    ('没设天数也照样生成注入文件',
     "    if not (isinstance(cfg.get('days'), int) and cfg['days'] >= 1):\n        raise Stop(ASK_DAYS)\n", ''),
    ('没设拦法也照样生成注入文件',
     "    if cfg.get('mode') not in MODES:\n        raise Stop(ASK_MODE)\n    return cfg", '    return cfg'),
    ('拦公司+岗位时允许不写岗位',
     "        elif not job.strip():\n            raise Stop('拦法是只拦这一个岗位，要写岗位名：block add 公司 岗位')\n", ''),
    ('改成拦公司+岗位后，没写岗位的旧条目不拦',
     "    return [i + 1 for i, b in enumerate(bl) if cfg.get('mode') == 'company_job' and not b.get('job')]",
     '    return []'),
    ('不核对每段行数（没取全也存）',
     "if f[1] != cur['part'] or f[2] != cur['parts'] or int(f[3]) != cur['_nlines']:", 'if False:'),
    ('不核对页面用的配置版本',
     "    if head['cfgv'] != want['cfgv']:", '    if False:'),
    ('每次问的拦法不问范围就加', "            if not (whole or only):\n                raise Stop(ASK_SCOPE)\n", ''),
    ('每次问的拦法整家公司也记岗位', "            if whole:\n                job = ''\n", "            if whole:\n                pass\n"),
    ('别的拦法也收 --whole', "        if (whole or only) and cfg['mode'] != 'ask':", "        if False:"),
    ('拦公司时也记岗位',
     "        if cfg['mode'] == 'company':\n            job = ''\n", "        if cfg['mode'] == 'company':\n            pass\n"),
    ('关键词没传给页面', "           'keywords': list(cfg.get('keywords') or []),", "           'keywords': [],"),
    ('刷新算法没传给页面', "'refresh': refresh_mode(cfg),", "'refresh': 'latest',"),
    ('凌晨刷新默认没改成 latest', "def refresh_mode(cfg):\n    return cfg.get('refresh') if cfg.get('refresh') in REFRESH else 'latest'", "def refresh_mode(cfg):\n    return cfg.get('refresh') if cfg.get('refresh') in REFRESH else 'first'"),
    ('高频刷新默认不走 14,3', "    return list(FREQ_DEFAULT)", "    return None"),
    ('高频刷新配置保存不起作用', "                cfg['freq'] = [int(m.group(1)), int(m.group(2))]", "                pass"),
    ('久别重逢默认不走 365', "    return REAPPEAR_DEFAULT", "    return None"),
    ('久别重逢配置保存不起作用', "                cfg['reappear'] = int(v)", "                pass"),
    ('久别重逢的过期条目还让页面先跳过',
     "    return [e for e in entries if e.get('platform') == platform and e.get('id') and not _is_reappear_stale(e, reappear, today)]",
     "    return [e for e in entries if e.get('platform') == platform and e.get('id')]"),
    ('久别重逢不看同岗位最近一次记录（混入旧条目误放行）', "                latest = max(matches, key=lambda x: (_last_seen_str(x), x.get('date') or ''))", "                latest = matches[0]"),
    ('@@S 短码心跳不更新在榜时间与刷新时间', "            e['last_seen'] = today_str\n            if platform == 'zhilian' and ts:\n                e['publishes'] = _merge_publishes(e.get('publishes'), [ts])", "            pass"),
    ('Boss HR 活跃度默认不走 week', "    return cfg.get('boss_active') if cfg.get('boss_active') in BOSS_ACTIVE else 'week'", "    return cfg.get('boss_active') if cfg.get('boss_active') in BOSS_ACTIVE else 'off'"),
    ('Boss HR 活跃度设了也不保存', "            cfg['boss_active'] = v", "            pass"),
    ('Boss 双休缺失默认不走 ask', "    return cfg.get('boss_rest') if cfg.get('boss_rest') in BOSS_REST else 'ask'", "    return cfg.get('boss_rest') if cfg.get('boss_rest') in BOSS_REST else 'exclude'"),
    ('Boss 双休缺失设了也不保存', "            cfg['boss_rest'] = v", "            pass"),
    ('老岗位范围没传给页面', "'old': cfg.get('old') or None}", "'old': None}"),
    ('汇报不写老岗位条数', "        if m.get('oldr'):\n", "        if False:\n"),
    ('老岗位范围不查前小后大', " or not 1 <= int(m.group(1)) < int(m.group(2)):", ':'),
    ('词里带分隔符也收', '            if not w or KW_BAD.search(w) or len(w) > 20:', '            if not w:'),
    ('投过的不跳过', "        e = applied.find(platform, r)\n        if e:", "        e = None\n        if e:"),
    ('看过的不跳过', "        if matches:", "        if False:"),
    ('同公司同岗位不去重', "        e = kept.find(platform, r)\n        if e:", "        e = None\n        if e:"),
    ('只按编号认（换编号重发、另一个平台都认不出）',
     "        for ec, x in self.jobs.get(job_key(r.get('job')), []):\n            if co_eq_n(ec, c) and id(x) not in seen_obj:\n                out.append(x)\n                seen_obj.add(id(x))\n", ''),
    ('不按编号认（岗位改了名就认不出）', "        e = self.ids.get((platform, r.get('id')))\n        if e:\n            out.append(e)\n            seen_obj.add(id(e))\n", ''),
    ('岗位名包含就算同一个（模糊合并）', "        for ec, x in self.jobs.get(job_key(r.get('job')), []):",
     "        for ec, x in [y for v in self.jobs.values() for y in v if job_norm(y[1].get('job')) in job_norm(r.get('job'))"
     " or job_norm(r.get('job')) in job_norm(y[1].get('job'))]:"),
    ('公司名只认完全一样（没用黑名单那套规则）', '    if a == b:\n        return True\n', '    return a == b\n'),
    ('公司名不去地名前缀（和页面不一致）', '        if i == 0 or REGION.fullmatch(l[:i]):', '        if i == 0:'),
    ('岗位名不去福利后缀（Boss 期望标签同一岗位又列一次）', "    while JOB_TAIL.search(s):\n        s = JOB_TAIL.sub(r'\\1', s)\n", ''),
    ('福利后缀横杠后面全去掉（不同岗位被当成一个）', "JOB_TAIL = re.compile(r'(.)[-—](?:[+＋]?(?:(?:周末)?双休|[五六]险一金|五险|出差|包吃住|包吃|包住|包餐|无经验|日结|上一休一))+$')",
     "JOB_TAIL = re.compile(r'(.)[-—].+$')"),
    ('清单不写地点', "'published': f[5], 'location': f[6],", "'published': f[5], 'location': '',"),
    ('相近的不看是不是同一家公司', "if co_eq_n(co_norm(rows[j]['company']), c) and near_title(r['job'], rows[j]['job'])]", "if near_title(r['job'], rows[j]['job'])]"),
    ('相近的不和看过的、投过的比', "        for why, by in pools:\n", "        for why, by in []:\n"),
    ('看过记录不存比对项', "entry = dict({'platform': platform, 'id': r['id'], 'company': r['company'], 'job': r['job'], 'date': today}, **cmp_fields(r))", "entry = {'platform': platform, 'id': r['id'], 'company': r['company'], 'job': r['job'], 'date': today}"),
    ('投过记录不存比对项', "'link': r.get('link', '')}, **cmp_fields(r))", "'link': r.get('link', '')})"),
    ('比对不看招聘人', "('hr', '招聘人'), ", ''),
    ('技能标签按顺序比', "if (set(x.split('、')) == set(y.split('、'))) if k == 'skills' else x == y:", 'if x == y:'),
    ('重复丢掉的不写哪里不一样', "        if e:\n            skipped.append(dict(r, why='重复', hit='%s / %s%s' % (e['company'], e['job'], '（%s）' % e['date'] if e.get('date') else ''),\n                                diff=verdict(*compare(r, e))))", "        if e:\n            skipped.append(dict(r, why='重复', hit='%s / %s%s' % (e['company'], e['job'], '（%s）' % e['date'] if e.get('date') else ''),\n                                diff=''))"),
    ('清单不标有相近的', "('（有相近的，见下表）' if r.get('near') else '')", "''"),
    ('留下的行只认旧的 8 段', "(13 if f[0] == 'R' else 8)", '8'),
    ('没登录也往下做', "            if why == '没登录':\n", "            if False:\n"),
    ('继续前不提醒核实登录', "LOGIN_CHECK if '没登录' in (items[k].get('why') or '') else ''", "''"),
    ('task login 不记没做完', "        items[n].update(status='unfinished', why='没登录')\n", ''),
    ('地名前缀不认区县', "REGION = re.compile(r'([一-龥]{2,3}(省|市|自治区|区|县)?){1,2}')", "REGION = re.compile(r'([一-龥]{2,3}(省|市|自治区)?){1,2}')"),
    ('黑名单拦下的也记成看过', '    remember_seen(p, rows, [', '    remember_seen(p, rows + blocked, ['),
    ('投过、重复跳过的也记成看过', "[r for r in skipped if r['why'] == '看过']", 'skipped'),
    ('看过的换了编号不补记（页面下次还认不出）', "    remember_seen(p, rows, [r for r in skipped if r['why'] == '看过'], seen_hits=seen_hits,\n                  freq_hits=[r for r in skipped if r['why'] == '高频刷新'])", '    remember_seen(p, rows, [], seen_hits=seen_hits, freq_hits=[])'),
    ('补记看过不查编号记过没有（同一编号记好几遍）', "    new = list(rows) + [r for r in again if (platform, r['id']) not in have]", '    new = list(rows) + list(again)'),
    ('同一次扫描能存两遍', '    old = saved_before(p, head[\'time\'])\n    if old:', '    old = None\n    if old:'),
    ('任务不按交代的顺序记', '        new = [x for a in args[1:] for x in parse_task(a, first)]', '        new = sorted(x for a in args[1:] for x in parse_task(a, first))'),
    ('「两边」不看配置固定先 Boss', "        return [(first, ALL), ('zhilian' if first == 'boss' else 'boss', ALL)]", "        return [('boss', ALL), ('zhilian', ALL)]"),
    ('「两边」只扫当前列表', "        return [(first, ALL), ('zhilian' if first == 'boss' else 'boss', ALL)]", "        return [(first, ''), ('zhilian' if first == 'boss' else 'boss', '')]"),
    ('「开始」不认', "    if p in ('两边', 'both', '开始', '全部开始'):", "    if p in ('两边', 'both'):"),
    ('「全部开始」不认', "    if p in ('两边', 'both', '开始', '全部开始'):", "    if p in ('两边', 'both', '开始'):"),
    ('关注清单不去重', "        for c in new_c:\n            if not any(norm(c) == norm(x) for x in companies):", "        for c in new_c:\n            if True:"),
    ('关注公司不用同一套公司名认法', "        hits = ['关注公司：' + c for c in companies if co_eq(r.get('company'), c)]",
     "        hits = ['关注公司：' + c for c in companies if r.get('company') == c]"),
    ('关注词不看描述开头', "        blob = norm(' '.join(str(r.get(k) or '') for k in ('job', 'skills', 'desc')))",
     "        blob = norm(r.get('job') or '')"),
    ('命中关注不放到清单最前面', "    watched = [(i, r) for i, r in enumerate(rows, 1) if r.get('watch')]", "    watched = []"),
    ('读到的标签不去空的和重复的', "            if a and a not in tags:", "            if True:"),
    ('换过的全部标签还能再换', "        if items[n]['tag'] != ALL or items[n]['status'] == 'done':", "        if items[n]['status'] == 'done':"),
    ('轮到全部标签不提示读标签名', "    if k is None or items[k]['tag'] != ALL:\n        return ''\n", "    return ''\n"),
    ('全部标签扫通后不问「开始」', "        ask = '\\n' + ASK_START", "        ask = ''"),
    ('问过了还一直问「开始」', "and load('config.json', {}).get('start') not in START:", ":"),
    ('没选先扫平台也排「两边」', "        if first not in PLATFORMS:\n            raise Stop(ASK_FIRST)\n", ''),
    ('config 没选先扫平台不提示', "    if cfg.get('first') not in PLATFORMS:\n        print(ASK_FIRST)\n", ''),
    ('task set 不读先扫平台', "        first = load('config.json', {}).get('first')\n", "        first = None\n"),
    ('save 不更新任务记录', "    note = task_saved(p, head['tag'], head['why'], base + '.md')", "    note = ''"),
    ('没翻完也记成做完', "            whole = why == '到底' or re.fullmatch(r'超过\\d+天', why)", '            whole = True'),
    ('继续时没把没做完的重新排上', "                t['status'] = 'todo'\n", '                pass\n'),
    ('全做完了说继续也不说没有未完成的', "        if k is None:\n            print('没有未完成的任务", "        if k is None and False:\n            print('没有未完成的任务"),
    ('碰到验证不跳过同平台后面的', "                if u['status'] == 'todo' and u['platform'] == t['platform']:", '                if False:'),
    ('没选时默认全部停下', "    return cfg.get('on_verify') if cfg.get('on_verify') in VERIFY else 'skip'",
     "    return cfg.get('on_verify') if cfg.get('on_verify') in VERIFY else 'stop'"),
    ('选了全部停下也接着做', "            if on_verify(load('config.json', {})) == 'stop':", '            if False:'),
    ('短码只用一遍哈希（和页面对不上，也容易撞）', " * 1024 + (fnv('#' + s) & 1023)", ''),
    ('短码按 UTF-8 算（中文编号和页面对不上）', "    b = s.encode('utf-16-le')", "    b = s.encode('utf-8') + b'\\0'"),
    ('看过的不交给页面', "    out.update(seen=''.join(codes), seenn=len(codes), seenv=short_hash(''.join(codes)))",
     "    out.update(seen='', seenn=0, seenv=short_hash(''))"),
    ('看过的算进配置号（每次 save 后都说配置是旧的）', "    out['cfgv'] = short_hash(json.dumps(out, ensure_ascii=False, sort_keys=True))",
     "    out['cfgv'] = short_hash(json.dumps(out, ensure_ascii=False, sort_keys=True) + ''.join(seen_codes(platform)))"),
    ('不核对页面用的看过记录（清空后还按旧记录跳过）', "    if int(head['seen']) and (n > len(codes)", "    if False and (n > len(codes)"),
    ('页面的看过记录旧一点也拒（只认完全一样）', "short_hash(''.join(codes[:n])) != head['seenv']", "short_hash(''.join(codes)) != head['seenv']"),
    ('页面先跳过的看过不算进总结', "    meta['seen'] += int(head['seen'])", '    pass'),
    ('存完不删页面文件', '    gone = drop_page_files(args[1:])', '    gone = 0'),
    ('删页面文件不看在不在 data/ 里', " and os.path.dirname(os.path.realpath(fn)) == os.path.realpath(data_dir())", ''),
    ('存完不重新生成配置文件', '    cfg, _, small = write_inject(p)', "    cfg, _, small = page_cfg(p), '', ''"),
    ('第一次扫不归类', "    if meta['first'] and len(rows) > LIST_MAX:", '    if False:'),
    ('不是第一次也归类', "    if meta['first'] and len(rows) > LIST_MAX:", '    if len(rows) > LIST_MAX:'),
    ('第一次扫不多也归类', "    if meta['first'] and len(rows) > LIST_MAX:", "    if meta['first']:"),
    ('profile 清空前不留备份', "BACKUP_FILES = {'config.json', 'blacklist.json', 'applied.json', 'seen.json', 'progress.json', 'profile.json', 'companies.json', 'review.json'}",
     "BACKUP_FILES = {'config.json', 'blacklist.json', 'applied.json', 'seen.json', 'progress.json', 'companies.json', 'review.json'}"),
    ('已核公司查询不用同公司规则和别名', "        hits = [c for c in cs if co_eq(c.get('company'), name)]",
     "        hits = [c for c in cs if c.get('company') == name]"),
    ('save 后不建待复核队列', "    _review_register(p, head['tag'], base + '.md', rows)", "    pass"),
    ('复核归档缺少排除明细也放行', "        if '排除' not in text:\n            missing.append('排除分组/逐条排除明细')",
     "        if False:\n            missing.append('排除分组/逐条排除明细')"),
]


def load_module(src, real_path, name):
    mod = types.ModuleType(name)
    mod.__file__ = real_path
    exec(compile(src, real_path, 'exec'), mod.__dict__)
    return mod


def run_cases(mod):
    errs = []
    old = os.environ.get('JOBSCAN_DATA')
    try:
        for case in CASES:
            with tempfile.TemporaryDirectory() as d:
                os.environ['JOBSCAN_DATA'] = d
                try:
                    case(mod, d)
                except Exception as e:  # noqa: BLE001 用例里任何异常都算不过
                    errs.append('%s：%s' % (case.__name__, (str(e) or type(e).__name__)[:300]))
    finally:
        if old is None:
            os.environ.pop('JOBSCAN_DATA', None)
        else:
            os.environ['JOBSCAN_DATA'] = old
    return errs


def run_all(real_path):
    src = open(real_path, encoding='utf-8').read()
    errs = ['[现在的写法] ' + e for e in run_cases(load_module(src, real_path, 'jobscan_now'))]
    for desc, old, new in MUTANTS:
        if src.count(old) != 1:
            errs.append('[反例] 「%s」的原文在 jobscan.py 里找不到或不唯一，用例跟代码对不上了，改代码要同步改这里' % desc)
            continue
        if not run_cases(load_module(src.replace(old, new), real_path, 'jobscan_mut')):
            errs.append('[反例] 改成「%s」用例还全过，说明用例抓不住这种错' % desc)
    return errs


if __name__ == '__main__':
    import sys
    here = os.path.dirname(os.path.abspath(__file__))
    e = run_all(os.path.join(os.path.dirname(here), 'jobscan.py'))
    print('\n'.join(e) if e else '命令用例全过（含 %d 种错误写法反例）' % len(MUTANTS))
    sys.exit(1 if e else 0)
