#!/usr/bin/env python3
"""寻找新岗位（find-fresh-jobs）：管配置、黑名单、关键词、投过记录、看过记录、查找清单，生成页面注入文件，保存扫描结果。

用法（代码或用例有改动时自动先跑全部用例，未改动时复用通过指纹；不过就停，没有跳过的办法）：
  python3 jobscan.py config                          看配置；没填的会提示要问使用者什么
  python3 jobscan.py config --days 7 --mode company  设天数和拦法（company=拦整家公司，company_job=只拦这一个岗位）
  python3 jobscan.py config --verify skip|stop        碰到安全验证时：skip=先跳过这个平台做下一件（默认），stop=全部停下
  python3 jobscan.py config --first boss|zhilian      「两边都扫」时先扫哪个平台
  python3 jobscan.py config --start all|ask           说「开始」时：all=两边全部标签直接扫，ask=先问这次扫哪些
  python3 jobscan.py config --refresh first|latest    智联凌晨刷新的岗位：first=按首次发布算天数（默认），latest=按刷新时间算
  python3 jobscan.py config --old 30,365|off          智联首次发布超过 30 天、不超过 365 天的算老岗位跳过（off=不按首次发布筛，默认）
  python3 jobscan.py config --reposts skip|remind     投过的岗位重新发布：skip=始终跳过（默认），remind=照常列出并提醒
  python3 jobscan.py block list                      列黑名单
  python3 jobscan.py block add 公司 [岗位]            加一条（拦法是 company_job 时必须写岗位）
  python3 jobscan.py block add --id 岗位编号或链接     从保存过的结果里找公司和岗位，加一条
  python3 jobscan.py block remove 序号               删一条（序号看 block list）
  python3 jobscan.py alias list|add|remove           管理同公司别名组（品牌名与工商全称对不上时用）
  python3 jobscan.py keyword list                    列不想看的词（岗位标题含这些词就跳过）
  python3 jobscan.py keyword add [--tag 标签] 词…     加词（不写 --tag 为全部标签共用）
  python3 jobscan.py keyword remove [--tag 标签] 词或序号   删词
  python3 jobscan.py keyword summary|preview         汇总已有标题或只读预览一个或多个词会命中哪些岗位
  python3 jobscan.py watch list                      列关注清单（帮盯某些公司和关键词，命中仅高亮提醒，不替代筛选）
  python3 jobscan.py watch add --company 公司…       加关注公司（或 --word 词…，支持同时传）
  python3 jobscan.py watch remove 序号或名称          删关注项（序号看 watch list）
  python3 jobscan.py applied list                    列投过记录
  python3 jobscan.py applied add --id 岗位编号或链接   从保存过的结果里找公司和岗位，记为投过
  python3 jobscan.py applied add 公司 岗位 [--platform boss|zhilian] [--link 链接] [--date YYYY-MM-DD]   手动记一条
  python3 jobscan.py applied sync 文件.json          从只读导出的投递名单同步已投记录
  python3 jobscan.py applied remove 序号             删一条（记错了时用）
  python3 jobscan.py find [--company 公司] [--job 岗位] | --batch 条件.json   在已保存结果里查找（每批最多 3 个条件）
  python3 jobscan.py seen                            看过的记录有多少条
  python3 jobscan.py seen clear                      清空看过的记录（想全部重新看一遍时用）
  python3 jobscan.py task set 项 [项…]               记下使用者交代的几件事，按顺序做（项：boss:标签、zhilian:标签、boss:全部、两边；两边按 --first 的先后）
  python3 jobscan.py task tags 序号 标签 [标签…]       把「全部标签」那件换成页面上读到的各个标签（window.__sTags()）
  python3 jobscan.py task                            看任务记录和各件状态
  python3 jobscan.py task resume                     使用者说「继续」时用：从第一件没做完的接着做
  python3 jobscan.py task done|fail|verify 序号 [原因] 手动记一件做完 / 没做完 / 碰到安全验证（save 会自动记做完）
  python3 jobscan.py task login 序号                  这件的平台没登录：全部停下，等使用者登录好、核实了再继续
  python3 jobscan.py inject boss|zhilian             生成注入文件，打印页面应返回的版本
  python3 jobscan.py save boss|zhilian 文件 [文件…]   把 get_page_text 取回的文字存成结果
  python3 jobscan.py test                            只跑用例

数据都在 data/ 下（config.json、blacklist.json、applied.json、seen.json、progress.json、backups/、inject_*.js、results/），不提交到仓库。
"""
import datetime
import glob
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PLATFORMS = {'boss': 'Boss直聘', 'zhilian': '智联招聘'}
PLATFORM_ALIAS = {'boss': 'boss', 'boss直聘': 'boss', 'zhilian': 'zhilian', '智联': 'zhilian', '智联招聘': 'zhilian'}
MODES = {'company': '拦整家公司', 'company_job': '只拦这一个岗位', 'ask': '每次拉黑时问：整家公司，还是只这一个岗位'}
MODE_ALIAS = {'company': 'company', 'company_job': 'company_job', '公司': 'company', '拦公司': 'company',
              '整家公司': 'company', '拦整家公司': 'company', '这一个岗位': 'company_job', '只拦这一个岗位': 'company_job',
              '公司+岗位': 'company_job', '拦公司+岗位': 'company_job',
              'ask': 'ask', '每次问': 'ask', '每次拉黑时问': 'ask', '问我': 'ask'}
LINK = {'boss': 'https://www.zhipin.com/job_detail/{}.html', 'zhilian': 'https://www.zhaopin.com/jobdetail/{}.htm'}
ASK_DAYS = '天数没设：先问使用者「只看几天内发布的岗位？」（推荐 7 天），再执行 config --days N'
ASK_MODE = ('拦法没设：先问使用者「拉黑时拦整家公司，还是只拦这家公司的这个岗位，还是每次拉黑时再问？」，'
            '再执行 config --mode company（拦整家公司）、config --mode company_job（只拦这一个岗位）或 config --mode ask（每次问）')
# 拦法是「每次问」时，每加一条都要先问使用者范围，再带 --only 或 --whole；不带就不加（免得没问就替使用者定了范围）。
ASK_SCOPE = ('拦法是每次问：先问使用者「是只不看这一个岗位，还是这家公司都不看？」，'
             '再执行 block add --only 公司 岗位（只拦这一个岗位）或 block add --whole 公司（整家公司）')
# 碰到安全验证时怎么办，使用者第一次用时选；没选、说不知道或「你定」都按 skip。两种都不替使用者过验证。
VERIFY = {'skip': '先跳过这个平台，做下一件，最后一起说明哪件没做完', 'stop': '全部停下，等使用者处理完验证再继续'}
VERIFY_ALIAS = {'skip': 'skip', 'stop': 'stop', 'a': 'skip', 'b': 'stop', '跳过': 'skip', '先跳过': 'skip',
                '停下': 'stop', '全部停下': 'stop'}
ASK_FIRST = ('先扫哪个平台没选：先问使用者「两边都扫的时候，先扫 Boss直聘，还是先扫智联招聘？」，再执行 config --first boss 或 zhilian'
             '（使用者说你定、都行，写 boss）')
REFRESH = {'first': '凌晨自动刷新的改按首次发布时间算天数', 'latest': '凌晨自动刷新的也按刷新时间算天数'}
REPOSTS = {'skip': '投过的同公司同岗位始终跳过（默认）', 'remind': '投递之后重新发布的照常列出并提醒'}
START = {'all': '两边全部标签直接扫（按先扫平台的先后）', 'ask': '先问使用者这次扫哪些'}
ASK_START = ('全部标签第一次扫通了：问使用者「以后说『开始』，就把两边全部标签都扫完，不再一件件问，行不行？」'
             '，同意执行 config --start all，不同意执行 config --start ask')
BACKUP_FILES = {'config.json', 'blacklist.json', 'applied.json', 'seen.json', 'progress.json'}


class Stop(Exception):
    """要停下来问使用者或重来的情况，退出码 2。"""


def data_dir():
    return os.environ.get('JOBSCAN_DATA') or os.path.join(HERE, 'data')


def path(*parts):
    return os.path.join(data_dir(), *parts)


def load(name, default):
    try:
        with open(path(name), encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return default


def dump(name, obj):
    os.makedirs(data_dir(), exist_ok=True)
    target = path(name)
    if name in BACKUP_FILES and os.path.exists(target):
        bdir = path('backups')
        os.makedirs(bdir, exist_ok=True)
        stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
        shutil.copy2(target, os.path.join(bdir, '%s_%s' % (stamp, name)))
        old_baks = sorted(glob.glob(os.path.join(bdir, '*_' + name)))
        for p in old_baks[:-30]:
            os.remove(p)
    tmp = path(name + '.tmp')
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
    os.replace(tmp, target)


def norm(s):
    return re.sub(r'\s', '', str(s or '')).lower()


def need_config():
    cfg = load('config.json', {})
    if not (isinstance(cfg.get('days'), int) and cfg['days'] >= 1):
        raise Stop(ASK_DAYS)
    if cfg.get('mode') not in MODES:
        raise Stop(ASK_MODE)
    return cfg


def jobless(cfg, bl):
    return [i + 1 for i, b in enumerate(bl) if cfg.get('mode') == 'company_job' and not b.get('job')]


# ---------- 公司、岗位比对 ----------
# co_norm、co_eq、job_norm 和 page/common.js 的 __sCoNorm、__sCoEq、__sJobNorm 是同一套规则（用例会两边对照），
# 投过、看过、重复都用它认「同一家公司」，和黑名单一致。
CO_TYPE = re.compile(r'(股份有限公司|有限责任公司|有限公司|分公司|总公司|集团|公司)$')
REGION = re.compile(r'([一-龥]{2,3}(省|市|自治区|区|县)?){1,2}')


def co_norm(s):
    s = re.sub(r'\s', '', str(s or ''))
    s = re.sub(r'[（(][^（()）]*[)）]', '', s)
    s = re.sub(r'(\.{2,}|…+)$', '', s).lower()
    while True:
        prev, s = s, CO_TYPE.sub('', s, count=1)
        if s == prev or len(s) <= 2:
            return s


def co_eq_n(a, b, _no_alias=False):
    """两个整理过的公司名是不是同一家：短的在长的开头，或者前面只是地名，或者属于已确认的别名组。"""
    if len(a) < 2 or len(b) < 2:
        return False
    if a == b:
        return True
    s, l = (a, b) if len(a) <= len(b) else (b, a)
    i = l.find(s)
    while i >= 0:
        if i == 0 or REGION.fullmatch(l[:i]):
            return True
        i = l.find(s, i + 1)
    if not _no_alias:
        for grp in load('config.json', {}).get('aliases') or []:
            if any(co_eq_n(a, co_norm(x), True) for x in grp) and any(co_eq_n(b, co_norm(x), True) for x in grp):
                return True
    return False


def co_eq(a, b):
    return co_eq_n(co_norm(a), co_norm(b))


# Boss 的求职期望列表会在岗位名后面加福利后缀（「行政专员-双休」「销售内勤-五险一金」），推荐列表里同一个岗位没有。
# 比对前去掉，不然换个标签同一个岗位又列一次。只去这几种词，横杠后面是别的字（「行政专员-出差补助」）不动。
JOB_TAIL = re.compile(r'(.)[-—](?:[+＋]?(?:(?:周末)?双休|[五六]险一金|五险|出差|包吃住|包吃|包住|包餐|无经验|日结|上一休一))+$')


def job_norm(s):
    s = re.sub(r'\s', '', str(s or ''))
    while JOB_TAIL.search(s):
        s = JOB_TAIL.sub(r'\1', s)
    s = re.sub(r'[（(【\[][^（()）】\]]*[)）】\]]', '', s)
    return re.sub(r'[/、\-—·|,，.。:：]', '', s).lower()


def job_key(s):
    """同一个岗位：整理后字完全一样，只是顺序不同也算（「人事行政专员」=「行政人事专员」）。不做别的模糊匹配，宁可多列一条。"""
    n = job_norm(s)
    return ''.join(sorted(n)) if len(n) >= 2 else ''


class Index:
    """投过的、看过的、这次已经留下的：按平台岗位编号找，或按同公司同岗位找。"""

    def __init__(self, entries=()):
        self.ids, self.jobs = {}, {}
        for e in entries:
            self.add(e)

    def add(self, e):
        if e.get('id'):
            self.ids[(e.get('platform'), e['id'])] = e
        k = job_key(e.get('job'))
        if k:
            self.jobs.setdefault(k, []).append((co_norm(e.get('company')), e))

    def find(self, platform, r):
        e = self.ids.get((platform, r.get('id')))
        if e:
            return e
        c = co_norm(r.get('company'))
        for ec, e in self.jobs.get(job_key(r.get('job')), []):
            if co_eq_n(ec, c):
                return e
        return None


def job_id(s):
    """岗位编号；给的是岗位链接就从链接里取出编号。"""
    m = re.search(r'job_?detail/([^/?#]+?)\.html?', s)
    return m.group(1) if m else s.strip()


# ---------- config ----------
def cmd_config(args):
    cfg = load('config.json', {})
    i = 0
    changed = False
    while i < len(args):
        if args[i] == '--days' and i + 1 < len(args):
            v = args[i + 1]
            if not re.fullmatch(r'\d+', v) or int(v) < 1:
                raise Stop('天数要是 1 以上的整数，收到：' + v)
            cfg['days'] = int(v)
        elif args[i] == '--mode' and i + 1 < len(args):
            v = MODE_ALIAS.get(args[i + 1])
            if not v:
                raise Stop('拦法只能是 company（拦整家公司）、company_job（只拦这一个岗位）或 ask（每次问），收到：' + args[i + 1])
            cfg['mode'] = v
        elif args[i] == '--verify' and i + 1 < len(args):
            v = VERIFY_ALIAS.get(args[i + 1].strip().lower())
            if not v:
                raise Stop('碰到验证的处理只能是 skip（先跳过这个平台）或 stop（全部停下），收到：' + args[i + 1])
            cfg['on_verify'] = v
        elif args[i] == '--first' and i + 1 < len(args):
            v = PLATFORM_ALIAS.get(args[i + 1].strip().lower())
            if not v:
                raise Stop('先扫的平台只能是 boss 或 zhilian，收到：' + args[i + 1])
            cfg['first'] = v
        elif args[i] == '--start' and i + 1 < len(args):
            v = args[i + 1].strip().lower()
            if v not in START:
                raise Stop('说「开始」时的做法只能是 all（全部标签直接扫）或 ask（先问扫哪些），收到：' + args[i + 1])
            cfg['start'] = v
        elif args[i] == '--refresh' and i + 1 < len(args):
            v = args[i + 1].strip().lower()
            if v not in REFRESH:
                raise Stop('凌晨刷新的算法只能是 first（按首次发布）或 latest（按刷新时间），收到：' + args[i + 1])
            cfg['refresh'] = v
        elif args[i] == '--old' and i + 1 < len(args):
            v = args[i + 1].strip().lower().replace('，', ',')
            if v == 'off':
                cfg.pop('old', None)
            else:
                m = re.fullmatch(r'(\d+),(\d+)', v)
                if not m or not 1 <= int(m.group(1)) < int(m.group(2)):
                    raise Stop('老岗位的范围要写成「甲,乙」两个整数、甲小于乙（比如 30,365），或 off，收到：' + args[i + 1])
                cfg['old'] = [int(m.group(1)), int(m.group(2))]
        elif args[i] == '--reposts' and i + 1 < len(args):
            v = {'skip': 'skip', '跳过': 'skip', 'remind': 'remind', '提醒': 'remind'}.get(args[i + 1].strip().lower())
            if not v:
                raise Stop('投过的岗位重新发布只能设 skip（始终跳过）或 remind（照常列出并提醒），收到：' + args[i + 1])
            cfg['reposts'] = v
        else:
            raise Stop('不认识的参数：' + args[i])
        changed = True
        i += 2
    if changed:
        dump('config.json', cfg)
    print('天数：' + (str(cfg['days']) + ' 天内' if cfg.get('days') else '没设'))
    print('拦法：' + MODES.get(cfg.get('mode'), '没设'))
    tk_map = cfg.get('tag_keywords') or {}
    tk_text = '；'.join('%s：%s' % (t, '、'.join(ws)) for t, ws in tk_map.items() if ws)
    print('不想看的词：' + ('、'.join(cfg.get('keywords') or []) or '没设（不按词拦）') + ('；按标签：' + tk_text if tk_text else ''))
    w = cfg.get('watch') or {}
    wc, ww = w.get('companies') or [], w.get('words') or []
    wparts = ([] if not wc else ['公司：' + '、'.join(wc)]) + ([] if not ww else ['词：' + '、'.join(ww)])
    print('关注清单：' + ('；'.join(wparts) if wparts else '没设（不额外提醒）'))
    aliases = cfg.get('aliases') or []
    print('同公司别名：' + ('；'.join(' = '.join(g) for g in aliases) if aliases else '没设'))
    print('碰到安全验证：' + VERIFY[on_verify(cfg)] + ('' if cfg.get('on_verify') in VERIFY else '（没选，按默认）'))
    print('两边都扫时：' + ('先扫' + PLATFORMS[cfg['first']] if cfg.get('first') in PLATFORMS else '先扫哪个平台没选'))
    print('说「开始」时：' + START.get(cfg.get('start'), '还没问过（全部标签第一次扫通后再问）'))
    print('智联凌晨刷新：' + REFRESH[cfg.get('refresh') if cfg.get('refresh') in REFRESH else 'first'])
    print('智联老岗位：' + ('首次发布超过 %d 天、不超过 %d 天的跳过' % tuple(cfg['old']) if cfg.get('old') else '不按首次发布筛'))
    rep = cfg.get('reposts') if cfg.get('reposts') in REPOSTS else 'skip'
    print('投过的岗位重新发布：' + REPOSTS[rep])
    if not cfg.get('days'):
        print(ASK_DAYS)
    if cfg.get('mode') not in MODES:
        print(ASK_MODE)
    if cfg.get('first') not in PLATFORMS:
        print(ASK_FIRST)
    bad = jobless(cfg, load('blacklist.json', []))
    if bad:
        print('注意：拦法是只拦这一个岗位，黑名单第 %s 条没写岗位。问使用者：补上岗位（先 remove 再 add），还是删掉。不处理的话 inject 会停。'
              % '、'.join(map(str, bad)))
    return 0


# ---------- block ----------
def find_result_row(jid):
    jid = job_id(jid)
    for f in sorted(glob.glob(path('results', '*.json')), reverse=True):
        with open(f, encoding='utf-8') as fh:
            d = json.load(fh)
        for r in d.get('rows', []) + d.get('blocked', []) + d.get('skipped', []):
            if r['id'] == jid:
                return d['platform'], r
    return None, None


def cmd_block(args):
    bl = load('blacklist.json', [])
    sub = args[0] if args else 'list'
    if sub == 'list':
        if not bl:
            print('黑名单是空的')
        whole = ' / 整家公司' if load('config.json', {}).get('mode') == 'ask' else ''
        for i, b in enumerate(bl, 1):
            print('%d. %s%s%s' % (i, b['company'], ' / ' + b['job'] if b.get('job') else whole,
                                  '（' + b['note'] + '）' if b.get('note') else ''))
        return 0
    if sub == 'add':
        cfg = load('config.json', {})
        if cfg.get('mode') not in MODES:
            raise Stop(ASK_MODE)
        rest, note, src = args[1:], '', 'manual'
        whole, only = '--whole' in rest, '--only' in rest
        rest = [a for a in rest if a not in ('--whole', '--only')]
        if (whole or only) and cfg['mode'] != 'ask':
            raise Stop('--whole、--only 只在拦法是「每次问」时用；现在的拦法是：' + MODES[cfg['mode']])
        if whole and only:
            raise Stop('--whole 和 --only 只能选一个')
        if '--note' in rest:
            k = rest.index('--note')
            note = ' '.join(rest[k + 1:k + 2])
            rest = rest[:k] + rest[k + 2:]
        if rest[:1] == ['--id']:
            if len(rest) < 2:
                raise Stop('--id 后面要跟岗位编号')
            src, r = find_result_row(rest[1])
            if not r:
                raise Stop('在保存过的结果里找不到这个编号：' + rest[1])
            company, job = r['company'], r['job']
        else:
            if not rest:
                raise Stop('要写公司名')
            company, job = rest[0], (rest[1] if len(rest) > 1 else '')
        if cfg['mode'] == 'company':
            job = ''
        elif cfg['mode'] == 'ask':
            if not (whole or only):
                raise Stop(ASK_SCOPE)
            if whole:
                job = ''
            elif not job.strip():
                raise Stop('只拦这一个岗位，要写岗位名：block add --only 公司 岗位')
        elif not job.strip():
            raise Stop('拦法是只拦这一个岗位，要写岗位名：block add 公司 岗位')
        for i, b in enumerate(bl, 1):
            if norm(b['company']) == norm(company) and norm(b.get('job')) == norm(job):
                print('已经有了：第 %d 条 %s%s' % (i, b['company'], ' / ' + job if job else ''))
                return 0
        bl.append({'company': company.strip(), 'job': job.strip(), 'note': note, 'from': src,
                   'added': datetime.date.today().isoformat()})
        dump('blacklist.json', bl)
        print('已加：%s%s（共 %d 条）。页面上要重新贴配置：python3 jobscan.py inject 平台' % (company, ' / ' + job if job else '', len(bl)))
        return 0
    if sub == 'remove':
        if len(args) < 2 or not re.fullmatch(r'\d+', args[1]) or not 1 <= int(args[1]) <= len(bl):
            raise Stop('要写 block list 里的序号（1-%d）' % len(bl))
        b = bl.pop(int(args[1]) - 1)
        dump('blacklist.json', bl)
        print('已删：%s%s（剩 %d 条）' % (b['company'], ' / ' + b['job'] if b.get('job') else '', len(bl)))
        return 0
    raise Stop('block 后面只能是 list、add、remove')


# ---------- alias ----------
# 用户确认的同主体别名组：例如品牌简称与工商登记全称完全不同时手动关联。不靠包含关系猜测，只按用户明确加的组认。
def cmd_alias(args):
    cfg = load('config.json', {})
    aliases = [list(g) for g in (cfg.get('aliases') or [])]
    sub = args[0] if args else 'list'
    if sub == 'list':
        if not aliases:
            print('同公司别名：没设')
        for i, g in enumerate(aliases, 1):
            print('%d. %s' % (i, ' = '.join(g)))
        return 0
    if sub == 'add':
        names = []
        for a in args[1:]:
            a = a.strip()
            if a and co_norm(a) not in [co_norm(x) for x in names]:
                names.append(a)
        if len(names) < 2 or any(len(co_norm(x)) < 2 for x in names):
            raise Stop('至少写两个不同的公司名称（每个整理后不少于 2 个字）：alias add 品牌简称 公司全称')
        for i, g in enumerate(aliases, 1):
            if any(co_eq_n(co_norm(x), co_norm(y), True) for x in names for y in g):
                raise Stop('和第 %d 组别名（%s）有重合；要合并请先 alias remove %d 再重新 add' % (i, ' = '.join(g), i))
        aliases.append(names)
        cfg['aliases'] = aliases
        dump('config.json', cfg)
        print('已加同公司别名：%s（共 %d 组）。页面上要重新贴配置：python3 jobscan.py inject 平台' % (' = '.join(names), len(aliases)))
        return 0
    if sub == 'remove':
        if len(args) < 2 or not re.fullmatch(r'\d+', args[1]) or not 1 <= int(args[1]) <= len(aliases):
            raise Stop('要写 alias list 里的序号（1-%d）' % len(aliases))
        g = aliases.pop(int(args[1]) - 1)
        cfg['aliases'] = aliases
        dump('config.json', cfg)
        print('已删同公司别名：%s（剩 %d 组）。页面上要重新贴配置：python3 jobscan.py inject 平台' % (' = '.join(g), len(aliases)))
        return 0
    raise Stop('alias 后面只能是 list、add、remove')


# ---------- keyword ----------
# 不想看的词：岗位标题含这些词就跳过（页面里判断，不看公司名）。默认空，不按词拦。
# 词里不许有空白和输出用的分隔符，否则页面头行里的按词计数会对不上。
KW_BAD = re.compile(r'[\s|@=;&?:：,，]')


def _result_files(file_arg=None, all_files=False):
    """取要查阅的保存结果 json 路径列表（新保存的在前）。默认只取最新扫描日期那一轮的文件。"""
    if file_arg:
        p = file_arg[:-3] + '.json' if file_arg.endswith('.md') else file_arg
        if not os.path.exists(p):
            raise Stop('找不到结果文件：' + file_arg)
        return [p]
    files = sorted(glob.glob(path('results', '*.json')), reverse=True)
    if not files:
        raise Stop('还没有保存过扫描结果，先扫完并 save')
    if all_files:
        return files
    latest_day = os.path.basename(files[0])[:8]
    return [f for f in files if os.path.basename(f)[:8] == latest_day]


def _pop_opt(args, flag, needs_val=True):
    """从参数列表中弹出 --flag [val]，返回 (val_or_bool, 剩余参数)。"""
    if flag not in args:
        return (None if needs_val else False), args
    k = args.index(flag)
    if not needs_val:
        return True, args[:k] + args[k + 1:]
    if k + 1 >= len(args):
        raise Stop(flag + ' 后面要写内容')
    return args[k + 1].strip(), args[:k] + args[k + 2:]


def cmd_keyword(args):
    cfg = load('config.json', {})
    kws = list(cfg.get('keywords') or [])
    tmap = {k: list(v) for k, v in (cfg.get('tag_keywords') or {}).items() if v}
    sub = args[0] if args else 'list'
    rest = args[1:]
    tag, rest = _pop_opt(rest, '--tag')
    fn, rest = _pop_opt(rest, '--file')
    if sub == 'list':
        if tag:
            tws = tmap.get(tag, [])
            if not tws:
                print('标签「%s」下没有屏蔽词' % tag)
            for i, w in enumerate(tws, 1):
                print('%d. %s' % (i, w))
            return 0
        if not kws and not tmap:
            print('不想看的词：没设，不按词拦')
        for i, w in enumerate(kws, 1):
            print('%d. %s' % (i, w))
        for t, tws in tmap.items():
            print('标签「%s」：%s' % (t, '、'.join('%d.%s' % (i, w) for i, w in enumerate(tws, 1))))
        return 0
    if sub == 'summary':
        files = _result_files(fn)
        by_tag = {}
        for f in files:
            d = json.load(open(f, encoding='utf-8'))
            t = d.get('tag') or '当前列表'
            bucket = by_tag.setdefault(t, {'seen': set(), 'titles': {}})
            for r in d.get('rows', []):
                key = (co_norm(r.get('company')), job_norm(r.get('job')))
                if key in bucket['seen']:
                    continue
                bucket['seen'].add(key)
                title = r.get('job') or ''
                grp = bucket['titles'].setdefault(title, [])
                grp.append(r.get('company') or '')
        print('标题分布汇总（来源：%s）：' % '、'.join(os.path.basename(f) for f in files))
        for t, info in by_tag.items():
            ranked = sorted(info['titles'].items(), key=lambda kv: (-len(kv[1]), kv[0]))[:15]
            print('- %s（共 %d 个不同岗位）：%s' % (
                t, len(info['seen']),
                '；'.join('%s（%d条，如 %s）' % (ttl, len(cs), cs[0]) for ttl, cs in ranked) or '无'))
        return 0
    if sub == 'preview':
        words = [w.strip() for w in rest if w.strip()]
        if not words:
            raise Stop('要写想预览的词：keyword preview [--tag 标签] 词 [词…]')
        files = _result_files(fn)
        docs = [json.load(open(f, encoding='utf-8')) for f in files]
        for w in words:
            hits, seen_ids = [], set()
            for d in docs:
                t = d.get('tag') or '当前列表'
                if tag and t != tag:
                    continue
                for r in d.get('rows', []):
                    if norm(w) in norm(r.get('job')) and (d.get('platform'), r.get('id')) not in seen_ids:
                        seen_ids.add((d.get('platform'), r.get('id')))
                        hits.append((t, r['company'], r['job']))
            print('只读预览「%s」%s：共命中 %d 条（仅按岗位标题字面包含，不含公司名；否定表述如“非%s”也会命中）。' % (
                w, '（限标签「%s」）' % tag if tag else '（全部标签）', len(hits), w))
            for t, co, jb in hits[:5]:
                print('  - [%s] %s / %s' % (t, co, jb))
        return 0
    if sub == 'add':
        words = [w.strip() for w in rest]
        if not words:
            raise Stop('要写词：keyword add [--tag 标签] 词 [词…]')
        for w in words:
            if not w or KW_BAD.search(w) or len(w) > 20:
                raise Stop('词里不能有空格和 | @ = ; & ? : , 这些符号，也不能超过 20 个字，收到：' + w)
        target = list(tmap.get(tag, [])) if tag else kws
        added = []
        for w in words:
            if not any(norm(w) == norm(x) for x in target):
                target.append(w)
                added.append(w)
        if tag:
            tmap[tag] = target
            cfg['tag_keywords'] = tmap
        else:
            cfg['keywords'] = target
        dump('config.json', cfg)
        scope = '标签「%s」' % tag if tag else '全局'
        print('已加（%s）：%s（共 %d 个：%s）。页面上要重新贴配置：python3 jobscan.py inject 平台'
              % (scope, '、'.join(added) or '没有新词', len(target), '、'.join(target)))
        return 0
    if sub == 'remove':
        if not rest:
            raise Stop('要写词或 keyword list 里的序号')
        t = rest[0].strip()
        target = list(tmap.get(tag, [])) if tag else kws
        hit = [x for x in target if norm(x) == norm(t)]
        if hit:
            w = hit[0]
        elif re.fullmatch(r'\d+', t) and 1 <= int(t) <= len(target):
            w = target[int(t) - 1]
        else:
            raise Stop('没有这个词：%s（看 keyword list）' % t)
        target.remove(w)
        if tag:
            if target:
                tmap[tag] = target
            else:
                tmap.pop(tag, None)
            if tmap:
                cfg['tag_keywords'] = tmap
            else:
                cfg.pop('tag_keywords', None)
        else:
            cfg['keywords'] = target
        dump('config.json', cfg)
        print('已删：%s（剩 %d 个）。页面上要重新贴配置：python3 jobscan.py inject 平台' % (w, len(target)))
        return 0
    raise Stop('keyword 后面只能是 list、add、remove、summary、preview')


# ---------- watch ----------
# 关注清单：帮盯特定公司（沿用 co_eq 比对）和特定词（匹配岗位名、技能标签、描述开头）。
# 默认空；只高亮提醒、不替代筛选，也不会绕过黑名单/投过/看过。
WATCH_WORD_BAD = re.compile(r'[\s|]')


def _watch_items(cfg):
    w = cfg.get('watch') or {}
    return list(w.get('companies') or []), list(w.get('words') or [])


def cmd_watch(args):
    cfg = load('config.json', {})
    companies, words = _watch_items(cfg)
    sub = args[0] if args else 'list'
    if sub == 'list':
        items = [('公司', c) for c in companies] + [('词', w) for w in words]
        if not items:
            print('关注清单是空的')
            return 0
        for i, (kind, val) in enumerate(items, 1):
            print('%d. [%s] %s' % (i, kind, val))
        return 0
    if sub == 'add':
        mode, new_c, new_w = None, [], []
        for a in args[1:]:
            if a in ('--company', '--word'):
                mode = a
            elif mode == '--company':
                new_c.append(a.strip())
            elif mode == '--word':
                new_w.append(a.strip())
            else:
                raise Stop('要写 --company 公司名 或 --word 关键词：watch add --company 公司 --word 词')
        if not new_c and not new_w:
            raise Stop('要写关注的公司或词：watch add --company 公司 [公司…] 或 watch add --word 词 [词…]')
        for c in new_c:
            if not c or len(c) > 60:
                raise Stop('公司名不能为空且不能超过 60 个字')
        for w in new_w:
            if not w or WATCH_WORD_BAD.search(w) or len(w) > 20:
                raise Stop('关注词里不能有空格或 |，也不能超过 20 个字，收到：' + w)
        added = []
        for c in new_c:
            if not any(norm(c) == norm(x) for x in companies):
                companies.append(c)
                added.append('公司:' + c)
        for w in new_w:
            if not any(norm(w) == norm(x) for x in words):
                words.append(w)
                added.append('词:' + w)
        cfg['watch'] = {'companies': companies, 'words': words}
        dump('config.json', cfg)
        print('已加关注：%s（当前共 %d 家公司、%d 个词）。下次 save 生效。'
              % ('、'.join(added) or '没有新增', len(companies), len(words)))
        return 0
    if sub == 'remove':
        if len(args) < 2:
            raise Stop('要写序号或名称（看 watch list）')
        t = args[1].strip()
        items = [('companies', c) for c in companies] + [('words', w) for w in words]
        if re.fullmatch(r'\d+', t) and 1 <= int(t) <= len(items):
            kind, val = items[int(t) - 1]
            (companies if kind == 'companies' else words).remove(val)
        else:
            hit = [(k, v) for k, v in items if norm(v) == norm(t)]
            if not hit:
                raise Stop('关注清单里找不到：%s（看 watch list）' % t)
            for kind, val in hit:
                (companies if kind == 'companies' else words).remove(val)
            val = '、'.join(v for _, v in hit)
        cfg['watch'] = {'companies': companies, 'words': words}
        dump('config.json', cfg)
        print('已取消关注：%s（剩 %d 家公司、%d 个词）' % (val, len(companies), len(words)))
        return 0
    raise Stop('watch 后面只能是 list、add、remove')


# ---------- applied ----------
# 投过记录：使用者说投了哪个，就记下来；之后两个平台扫到同公司同岗位跳过（开启重发提醒时，投后重发的照常列出并提醒）。
def _parse_date(s):
    if not s or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', str(s).strip()):
        raise Stop('日期要写成 YYYY-MM-DD（比如 2026-11-16），收到：' + str(s))
    try:
        d = datetime.date.fromisoformat(str(s).strip())
    except ValueError:
        raise Stop('日期无效：' + str(s))
    if d > datetime.date.today():
        raise Stop('投递日期不能晚于今天：' + str(s))
    return d.isoformat()


def cmd_applied(args):
    al = load('applied.json', [])
    sub = args[0] if args else 'list'
    if sub == 'list':
        if not al:
            print('投过记录是空的')
        for i, a in enumerate(al, 1):
            print('%d. %s %s %s / %s%s' % (i, a['date'], PLATFORMS.get(a.get('platform'), '平台没写'), a['company'], a['job'],
                                           '  ' + a['link'] if a.get('link') else ''))
        return 0
    if sub == 'add':
        rest = args[1:]
        dt_val, rest = _pop_opt(rest, '--date')
        use_date = _parse_date(dt_val) if dt_val is not None else datetime.date.today().isoformat()
        if rest[:1] == ['--id']:
            if len(rest) < 2:
                raise Stop('--id 后面要跟岗位编号或岗位链接')
            p, r = find_result_row(rest[1])
            if not r:
                raise Stop('在保存过的结果里找不到这个编号：' + rest[1])
            e = dict({'platform': p, 'id': r['id'], 'company': r['company'], 'job': r['job'], 'link': r.get('link', '')}, **cmp_fields(r))
        else:
            opt = {}
            for k in ('--platform', '--link'):
                if k in rest:
                    i = rest.index(k)
                    opt[k] = ' '.join(rest[i + 1:i + 2]).strip()
                    rest = rest[:i] + rest[i + 2:]
            if len(rest) < 2 or not rest[0].strip() or not rest[1].strip():
                raise Stop('要写公司和岗位：applied add 公司 岗位（或 applied add --id 岗位编号）')
            p = opt.get('--platform', '')
            if p and p not in PLATFORMS:
                raise Stop('平台只能是 boss 或 zhilian，收到：' + p)
            link = opt.get('--link', '')
            e = {'platform': p, 'id': job_id(link) if link else '', 'company': rest[0].strip(), 'job': rest[1].strip(), 'link': link}
        old = Index(al).find(e['platform'], e)
        if old:
            cfg = load('config.json', {})
            is_new_apply = cfg.get('reposts') == 'remind' and (
                (e.get('id') and e.get('id') != old.get('id')) or use_date > (old.get('date') or ''))
            if not is_new_apply:
                print('已经记过了：第 %d 条 %s / %s（%s）' % (al.index(old) + 1, old['company'], old['job'], old['date']))
                return 0
            prev = {k: old[k] for k in ('date', 'platform', 'id', 'link') if old.get(k)}
            old.setdefault('earlier', []).append(prev)
            old.update(date=use_date, **{k: e[k] for k in ('platform', 'id', 'link') if e.get(k)})
            dump('applied.json', al)
            print('已更新再投日期：%s / %s（%s；原有 %s 记录已保留）。' % (old['company'], old['job'], use_date, prev.get('date', '之前')))
            return 0
        e['date'] = use_date
        al.append(e)
        dump('applied.json', al)
        print('已记为投过：%s / %s（共 %d 条）。以后两个平台扫到同公司同岗位%s。' % (
            e['company'], e['job'], len(al),
            '按重发策略提醒' if load('config.json', {}).get('reposts') == 'remind' else '都跳过'))
        return 0
    if sub == 'sync':
        if len(args) < 2:
            raise Stop('要写导出的投递名单 json 文件：applied sync 名单.json')
        try:
            payload = json.load(open(args[1], encoding='utf-8'))
        except (OSError, json.JSONDecodeError) as err:
            raise Stop('读取名单失败：' + str(err))
        rows = payload.get('rows') if isinstance(payload, dict) else None
        if not isinstance(rows, list) or (isinstance(payload.get('total'), int) and payload['total'] != len(rows)):
            raise Stop('名单格式不对或分页总数与行数不符，整批未导入')
        idx = Index(al)
        added = updated = 0
        today = datetime.date.today().isoformat()
        for row in rows:
            if not isinstance(row, dict) or not str(row.get('company') or '').strip() or not str(row.get('job') or '').strip():
                raise Stop('名单每条都要有非空的 company 和 job')
            dt_raw = row.get('appliedAt') or row.get('date')
            dt_clean = _parse_date(str(dt_raw)[:10]) if dt_raw else ''
            p = row.get('platform') if row.get('platform') in PLATFORMS else ''
            link = str(row.get('link') or '').strip()
            item = {'platform': p, 'id': job_id(link) if link else '', 'company': row['company'].strip(), 'job': row['job'].strip(),
                    'link': link, 'date': dt_clean or today, 'dated': bool(dt_clean)}
            old = idx.find(p, item)
            if not old:
                al.append(item)
                idx.add(item)
                added += 1
            elif dt_clean and (not old.get('dated', True) or dt_clean > (old.get('date') or '')):
                old['date'] = dt_clean
                old['dated'] = True
                updated += 1
        dump('applied.json', al)
        print('已同步投递名单：读入 %d 条，新增 %d 条，补全/更新日期 %d 条（共 %d 条）。' % (len(rows), added, updated, len(al)))
        return 0
    if sub == 'remove':
        if len(args) < 2 or not re.fullmatch(r'\d+', args[1]) or not 1 <= int(args[1]) <= len(al):
            raise Stop('要写 applied list 里的序号（1-%d）' % len(al))
        a = al.pop(int(args[1]) - 1)
        dump('applied.json', al)
        print('已删：%s / %s（剩 %d 条）' % (a['company'], a['job'], len(al)))
        return 0
    raise Stop('applied 后面只能是 list、add、sync、remove')


# ---------- find ----------
# 按公司+岗位或单岗位查找已保存结果清单（最多 3 个独立条件，绝不交叉拼接，不搜全站、不改记录）。
def _query_matches(q, r):
    qc, qj = (q.get('company') or '').strip(), (q.get('job') or '').strip()
    if qc:
        if not (norm(qc) in norm(r.get('company')) or co_eq(qc, r.get('company'))):
            return False
    if qj:
        if not (norm(qj) in norm(r.get('job')) or (job_key(qj) and job_key(qj) == job_key(r.get('job')))):
            return False
    return True


def _query_label(q):
    qc, qj = (q.get('company') or '').strip(), (q.get('job') or '').strip()
    return '%s + %s' % (qc, qj) if qc and qj else (qc or qj)


def cmd_find(args):
    fn, rest = _pop_opt(args, '--file')
    use_all, rest = _pop_opt(rest, '--all', needs_val=False)
    batch_fn, rest = _pop_opt(rest, '--batch')
    q_co, rest = _pop_opt(rest, '--company')
    q_job, rest = _pop_opt(rest, '--job')
    if rest:
        raise Stop('不认识的参数：' + ' '.join(rest))
    if batch_fn:
        if q_co or q_job:
            raise Stop('--batch 不能和 --company / --job 同时写')
        try:
            queries = json.load(open(batch_fn, encoding='utf-8')).get('queries')
        except (OSError, json.JSONDecodeError) as err:
            raise Stop('读取查找条件失败：' + str(err))
        if not isinstance(queries, list):
            raise Stop('条件文件里要有 queries 数组')
    else:
        queries = [dict({'company': q_co} if q_co else {}, **({'job': q_job} if q_job else {}))]
    if not queries or any(not isinstance(q, dict) or not ((q.get('company') or '').strip() or (q.get('job') or '').strip()) for q in queries):
        raise Stop('至少写一个条件（--company 或 --job，或 --batch 条件.json）')
    if len(queries) > 3:
        raise Stop('每批最多查 3 个条件（收到 %d 个），请分批查，不截断。' % len(queries))
    files = _result_files(fn, all_files=use_all)
    applied_idx = Index(load('applied.json', []))
    bl = load('blacklist.json', [])
    cfg = load('config.json', {})
    per_q = [0] * len(queries)
    hits, by_key = [], {}
    sources = []
    for f in files:
        d = json.load(open(f, encoding='utf-8'))
        stamp = os.path.basename(f)[:8]
        date_str = '%s-%s-%s' % (stamp[:4], stamp[4:6], stamp[6:8]) if stamp.isdigit() else stamp
        p = d.get('platform', '')
        why = d.get('why') or ''
        whole = why == '到底' or bool(re.fullmatch(r'超过\d+天', why))
        src_desc = '%s · %s（%s，%s）' % (PLATFORMS.get(p, p), d.get('tag') or '当前列表', date_str, '已翻完' if whole else '未翻完：' + (why or '未知'))
        sources.append(src_desc)
        for idx_row, r in enumerate(d.get('rows', []), 1):
            matched = [_query_label(q) for qi, q in enumerate(queries) if _query_matches(q, r)]
            if not matched:
                continue
            for qi, q in enumerate(queries):
                if _query_matches(q, r):
                    per_q[qi] += 1
            k = (p, r.get('id') or (co_norm(r.get('company')), job_norm(r.get('job'))))
            if k in by_key:
                for m in matched:
                    if m not in by_key[k]['matched']:
                        by_key[k]['matched'].append(m)
                continue
            flags = []
            if applied_idx.find(p, r):
                flags.append('已投')
            for b in bl:
                if co_eq(b.get('company'), r.get('company')) and (cfg.get('mode') == 'company' or (cfg.get('mode') == 'ask' and not b.get('job')) or (b.get('job') and job_key(b['job']) == job_key(r.get('job')))):
                    flags.append('已拉黑')
                    break
            item = dict(r, seq=idx_row, source=src_desc, matched=matched, flags=flags)
            by_key[k] = item
            hits.append(item)
    print('查找来源：%s' % '；'.join(sources))
    for q, n in zip(queries, per_q):
        print('条件「%s」：%s' % (_query_label(q), '%d 条匹配' % n if n else '0 匹配（没找到）'))
    for item in hits:
        mark = (' [' + '、'.join(item['flags']) + ']') if item['flags'] else ''
        print('- #%d %s / %s | %s | %s | %s | 来源：%s | 命中：%s%s' % (
            item['seq'], item['company'], item['job'], item.get('salary') or '—', item.get('location') or '—',
            item.get('link') or '—', item['source'], '、'.join(item['matched']), mark))
    return 0


# ---------- seen ----------
# 看过的记录：save 时把列给使用者的岗位记下（平台、编号、公司、岗位），下次扫描不再列。
# 被黑名单、关键词、投过拦下的不记。
def cmd_seen(args):
    seen = load('seen.json', [])
    if not args:
        n = ['%s %d 条' % (PLATFORMS[p], sum(1 for s in seen if s.get('platform') == p)) for p in PLATFORMS]
        print('看过的记录：共 %d 条（%s）%s' % (len(seen), '，'.join(n), '，最早一条记于 ' + min(s['date'] for s in seen) if seen else ''))
        return 0
    if args[0] == 'clear':
        if seen:
            dump('seen.bak.json', seen)
        dump('seen.json', [])
        print('已清空看过的记录（原有 %d 条%s）。下次扫描，符合条件的岗位会全部重新列出。'
              '已经开着的列表页要先 inject，再执行 inject_平台_cfg.js（页面里存着清空以前的看过记录）。'
              % (len(seen), '，备份在 ' + path('seen.bak.json') if seen else ''))
        return 0
    raise Stop('seen 后面只能不写（看有多少条）或写 clear（清空）')


def on_verify(cfg):
    return cfg.get('on_verify') if cfg.get('on_verify') in VERIFY else 'skip'


# ---------- task ----------
# 任务记录：使用者一次交代的几件事，每件是一个平台的一个标签（标签空 = 当前列表），按交代的顺序做。
# 每件做完立即更新（save 自动记）。额度用完、对话断了，说「继续」就 task resume，从第一件没做完的接着做。
STATUS = {'todo': '没开始', 'done': '做完', 'unfinished': '没做完'}
ALL = '*'  # 这个平台的全部标签：轮到它时读页面上的标签名，task tags 换成一件件
ALL_WORDS = ('全部', '全部标签', '*')
# 没登录：不管安全验证选的是哪种，都全部停下，不做后面的；使用者说登录好了，先核实再接着做
LOGIN_STOP = ('全部停下，后面几件也先不做。请使用者在 Chrome 里自己登录%s（不替使用者登录），登录好了说一声。'
              '使用者说登录好了：重新打开列表页、装好脚本，执行 window.__sLogin()，返回 ok 才 task resume 接着做；'
              '还是「没登录」就照实告诉使用者，继续等。')
LOGIN_CHECK = '（这件上次是没登录停下的：先核实已登录，列表页执行 window.__sLogin() 返回 ok 再扫；不是 ok 就停下告诉使用者）'


def parse_task(s, first=None):
    """「boss」「zhilian:标签」「boss:全部」「两边」→ [(平台, 标签)]。
    「两边」（「开始」「两边都扫」）= 两边全部标签，按使用者选的先扫平台排，没选就停下先问。"""
    p, _, tag = s.replace('：', ':').partition(':')
    p, tag = p.strip().lower(), tag.strip()
    if p in ('两边', 'both', '开始', '全部开始'):
        if tag:
            raise Stop('「两边」后面不能带标签，要分开写：boss:标签 zhilian:标签')
        if first not in PLATFORMS:
            raise Stop(ASK_FIRST)
        return [(first, ALL), ('zhilian' if first == 'boss' else 'boss', ALL)]
    if p not in PLATFORM_ALIAS:
        raise Stop('任务的平台只能是 boss、zhilian 或「两边」，收到：' + s)
    return [(PLATFORM_ALIAS[p], ALL if tag in ALL_WORDS else tag)]


def task_label(t):
    return '%s %s' % (PLATFORMS[t['platform']], '全部标签' if t['tag'] == ALL else t['tag'] or '当前列表')


def all_hint(items, k):
    """轮到「全部标签」那件时，先读标签名换成一件件。"""
    if k is None or items[k]['tag'] != ALL:
        return ''
    return ('（先打开%s列表页、装好脚本，执行 window.__sTags() 读出标签名，再 python3 jobscan.py task tags %d 标签1 标签2 …，'
            '按页面上的顺序写）' % (PLATFORMS[items[k]['platform']], k + 1))


def next_todo(items):
    return next((i for i, t in enumerate(items) if t['status'] == 'todo'), None)


def task_after(items):
    """一件做完或没做完之后，说下一件做什么；这一轮都过了一遍，就说做完几件、没做完的卡在哪。"""
    k = next_todo(items)
    if k is not None:
        return '下一件：第 %d 件 %s%s' % (k + 1, task_label(items[k]), all_hint(items, k))
    left = ['第 %d 件 %s：%s' % (i + 1, task_label(t), t.get('why') or '没做完') for i, t in enumerate(items) if t['status'] != 'done']
    ask = ''
    if not left and any(t.get('from_all') for t in items) and load('config.json', {}).get('start') not in START:
        ask = '\n' + ASK_START
    return '这次交代的 %d 件都过了一遍：做完 %d 件%s。可以给总结果了。%s' % (
        len(items), len(items) - len(left), '，没做完 %d 件（%s）' % (len(left), '；'.join(left)) if left else '', ask)


def show_tasks(items):
    if not items:
        print('没有任务记录：使用者还没交代过要扫什么')
        return
    for i, t in enumerate(items, 1):
        print('%d. %s：%s%s%s' % (i, task_label(t), STATUS[t['status']], '（%s）' % t['why'] if t.get('why') else '',
                                 '  结果：' + t['result'] if t.get('result') else ''))


def task_saved(platform, tag, why, result):
    """save 之后更新任务记录：找第一件同平台同标签、还没做完的，翻完记做完，没翻完记没做完。"""
    prog = load('progress.json', {})
    items = prog.get('items', [])
    for i, t in enumerate(items):
        if t['status'] != 'done' and t['platform'] == platform and (t['tag'] or '当前列表') == tag:
            whole = why == '到底' or re.fullmatch(r'超过\d+天', why)
            t.update(status='done' if whole else 'unfinished', why='' if whole else why, result=result)
            dump('progress.json', prog)
            if why == '没登录':
                return '任务记录：第 %d 件 %s 没做完（没登录）。%s' % (i + 1, task_label(t), LOGIN_STOP % PLATFORMS[platform])
            return '任务记录：第 %d 件 %s %s。%s' % (i + 1, task_label(t), '做完' if whole else '没做完（%s）' % why, task_after(items))
    return ''


def cmd_task(args):
    prog = load('progress.json', {})
    items = prog.get('items', [])
    sub = args[0] if args else 'show'
    if sub == 'show':
        show_tasks(items)
        return 0
    if sub == 'set':
        first = load('config.json', {}).get('first')
        new = [x for a in args[1:] for x in parse_task(a, first)]
        if not new:
            raise Stop('要写任务：task set boss:推荐 zhilian（「两边」按 config --first 选的平台先扫）')
        left = [task_label(t) for t in items if t['status'] != 'done']
        prog = {'set': datetime.datetime.now().strftime('%Y-%m-%d %H:%M'),
                'items': [{'platform': p, 'tag': tag, 'status': 'todo', 'why': '', 'result': ''} for p, tag in new]}
        dump('progress.json', prog)
        if left:
            print('注意：上次的任务还有 %d 件没做完（%s），已换成这次交代的。' % (len(left), '、'.join(left)))
        show_tasks(prog['items'])
        print('先做：第 1 件 ' + task_label(prog['items'][0]) + all_hint(prog['items'], 0))
        return 0
    if sub == 'resume':
        for t in items:
            if t['status'] == 'unfinished':
                t['status'] = 'todo'
                t['why'] = '上次没做完：' + t['why'] if t.get('why') and not t['why'].startswith('上次没做完') else t.get('why', '')
        k = next_todo(items)
        if k is None:
            print('没有未完成的任务：%s' % ('上次交代的 %d 件都做完了' % len(items) if items else '还没交代过任务'))
            return 0
        dump('progress.json', prog)
        show_tasks(items)
        print('从第 %d 件接着做：%s（做到一半断掉的标签从头重翻，已经列过的岗位记为看过，不会再列）%s%s' % (
            k + 1, task_label(items[k]), all_hint(items, k), LOGIN_CHECK if '没登录' in (items[k].get('why') or '') else ''))
        return 0
    if sub == 'tags':
        if len(args) < 2 or not re.fullmatch(r'\d+', args[1]) or not 1 <= int(args[1]) <= len(items):
            raise Stop('要写任务序号（1-%d，看 python3 jobscan.py task）' % len(items))
        n = int(args[1]) - 1
        if items[n]['tag'] != ALL or items[n]['status'] == 'done':
            raise Stop('第 %d 件是 %s，不是没做的「全部标签」，不用换' % (n + 1, task_label(items[n])))
        tags = []
        for a in args[2:]:
            a = a.strip()
            if a and a not in tags:
                tags.append(a)
        if not tags:
            raise Stop('一个标签也没写。页面上读不到标签，多半是还没设求职期望：task fail %d 没设求职期望，请使用者先去平台设好' % (n + 1))
        p = items[n]['platform']
        items[n:n + 1] = [{'platform': p, 'tag': x, 'status': 'todo', 'why': '', 'result': '', 'from_all': True} for x in tags]
        dump('progress.json', prog)
        show_tasks(items)
        print('%s 全部标签换成了 %d 件：%s。下一件：第 %d 件 %s' % (PLATFORMS[p], len(tags), '、'.join(tags), n + 1, task_label(items[n])))
        return 0
    if sub == 'login':
        if len(args) < 2 or not re.fullmatch(r'\d+', args[1]) or not 1 <= int(args[1]) <= len(items):
            raise Stop('要写任务序号（1-%d，看 python3 jobscan.py task）' % len(items))
        n = int(args[1]) - 1
        items[n].update(status='unfinished', why='没登录')
        dump('progress.json', prog)
        print('第 %d 件 %s 记为没做完（%s没登录）。%s' % (n + 1, task_label(items[n]), PLATFORMS[items[n]['platform']],
                                                 LOGIN_STOP % PLATFORMS[items[n]['platform']]))
        return 0
    if sub in ('done', 'fail', 'verify'):
        if len(args) < 2 or not re.fullmatch(r'\d+', args[1]) or not 1 <= int(args[1]) <= len(items):
            raise Stop('要写任务序号（1-%d，看 python3 jobscan.py task）' % len(items))
        n = int(args[1]) - 1
        t = items[n]
        if sub == 'done':
            t.update(status='done', why='')
            msg = '第 %d 件 %s 记为做完。' % (n + 1, task_label(t))
        elif sub == 'fail':
            why = ' '.join(args[2:]).strip()
            if not why:
                raise Stop('要写没做完的原因：task fail 序号 原因')
            t.update(status='unfinished', why=why)
            msg = '第 %d 件 %s 记为没做完（%s）。' % (n + 1, task_label(t), why)
        else:
            t.update(status='unfinished', why='碰到安全验证')
            msg = '第 %d 件 %s 记为没做完（碰到安全验证）。不替使用者过验证。' % (n + 1, task_label(t))
            if on_verify(load('config.json', {})) == 'stop':
                dump('progress.json', prog)  # 后面几件保持「没开始」，说「继续」时从这一件接着做
                print(msg + '按设置全部停下：请使用者在浏览器里完成验证，处理好后说「继续」。')
                return 0
            skipped = []
            for i, u in enumerate(items):
                if u['status'] == 'todo' and u['platform'] == t['platform']:
                    u.update(status='unfinished', why='%s碰到安全验证，先跳过' % PLATFORMS[t['platform']])
                    skipped.append(str(i + 1))
            msg += '按设置先跳过 %s%s，做下一件。' % (PLATFORMS[t['platform']], '（第 %s 件也先不做）' % '、'.join(skipped) if skipped else '')
        dump('progress.json', prog)
        print(msg + task_after(items))
        return 0
    raise Stop('task 后面只能是 set、resume、tags、done、fail、verify、login，或不写（看任务记录）')


# ---------- inject ----------
def code_src(platform):
    parts = []
    for name in ('common.js', platform + '.js'):
        with open(os.path.join(HERE, 'page', name), encoding='utf-8') as f:
            parts.append(f.read())
    return '\n'.join(parts)


def short_hash(s):
    return hashlib.sha1(s.encode('utf-8')).hexdigest()[:6]


# 看过的岗位编号交给页面先跳过，取结果时少取一半左右。编号原样太长（上千条就是几万字），每条压成 7 个字符的短码：
# 两遍 FNV-1a 拼成 42 位，几千条里新岗位撞上旧短码的机会约为几亿分之一。和 page/common.js 的 __sCode 算法一样（用例两边对照）。
B64 = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz-_'


def fnv(s, h=2166136261):
    b = s.encode('utf-16-le')  # 和 JS 的 charCodeAt 一样按 UTF-16 码元算
    for i in range(0, len(b), 2):
        h = ((h ^ (b[i] | b[i + 1] << 8)) * 16777619) & 0xFFFFFFFF
    return h


def seen_code(jid):
    s = str(jid)
    v = fnv(s) * 1024 + (fnv('#' + s) & 1023)
    out = ''
    for _ in range(7):
        out = B64[v % 64] + out
        v //= 64
    return out


def seen_codes(platform):
    """这个平台看过的岗位编号短码，按记下的先后、去重。"""
    out, have = [], set()
    for e in load('seen.json', []):
        if e.get('platform') == platform and e.get('id'):
            c = seen_code(e['id'])
            if c not in have:
                have.add(c)
                out.append(c)
    return out


def page_cfg(platform):
    cfg = need_config()
    bl = load('blacklist.json', [])
    bad = jobless(cfg, bl)
    if bad:
        raise Stop('拦法是只拦这一个岗位，黑名单第 %s 条没写岗位。先问使用者补岗位还是删掉，处理完再 inject。' % '、'.join(map(str, bad)))
    out = {'platform': platform, 'days': cfg['days'], 'mode': cfg['mode'],
           'blacklist': [{'company': b['company'], 'job': b.get('job', '')} for b in bl],
           'keywords': list(cfg.get('keywords') or []),
           'tag_keywords': {k: list(v) for k, v in (cfg.get('tag_keywords') or {}).items() if v},
           'aliases': [list(g) for g in (cfg.get('aliases') or [])],
           'refresh': cfg.get('refresh') if cfg.get('refresh') in REFRESH else 'first', 'old': cfg.get('old') or None}
    out['cfgv'] = short_hash(json.dumps(out, ensure_ascii=False, sort_keys=True))
    out['code'] = short_hash(code_src(platform))
    # 看过的记录不算进配置号：每次 save 都会变，页面上的旧一点只是少跳过几条，save 照样再筛；清空过的由 save 核对 seenv 拦下
    codes = seen_codes(platform)
    out.update(seen=''.join(codes), seenn=len(codes), seenv=short_hash(''.join(codes)))
    return out


LOADER = ("(function(){var s=localStorage.getItem('__jss_src'),c=localStorage.getItem('__jss_cfg');"
          "if(!s||!c)return 'no-cache 贴完整注入文件';(0,eval)(s);return window.__sInit(JSON.parse(c));})()")


def cmd_inject(args):
    if not args or args[0] not in PLATFORMS:
        raise Stop('要写平台：inject boss 或 inject zhilian')
    p = args[0]
    cfg, full, small = write_inject(p)
    print('页面应返回：ready 代码%s 配置%s 看过%d条' % (cfg['code'], cfg['cfgv'], cfg['seenn']))
    print('第一步先在页面执行这一行（用上次存在页面里的脚本）：')
    print(LOADER)
    print('返回的代码号不对，或者是 no-cache → 贴完整文件：%s（%d 字）' % (path('inject_%s.js' % p), len(full)))
    print('只有配置号或看过条数不对 → 贴小文件：%s（%d 字）' % (path('inject_%s_cfg.js' % p), len(small)))
    return 0


def write_inject(p):
    """生成两个注入文件：完整的（代码+配置）和只换配置的。返回 (配置, 完整文件, 小文件)。"""
    cfg = page_cfg(p)
    # 贴进页面的版本去掉整行注释，省额度（行尾注释和代码不动）
    src = '\n'.join(l for l in code_src(p).split('\n') if l.strip() and not l.lstrip().startswith('//'))
    j = json.dumps(cfg, ensure_ascii=False)
    full = ('// jobscan.py inject 生成，别手改。代码 %s 配置 %s\n'
            "(function(){var SRC=%s;var CFG=%s;try{localStorage.setItem('__jss_src',SRC);"
            "localStorage.setItem('__jss_cfg',JSON.stringify(CFG));}catch(e){}(0,eval)(SRC);return window.__sInit(CFG);})()\n"
            % (cfg['code'], cfg['cfgv'], json.dumps(src, ensure_ascii=False), j))
    small = ('// jobscan.py inject 生成，只换配置。配置 %s\n'
             "(function(){var CFG=%s;try{localStorage.setItem('__jss_cfg',JSON.stringify(CFG));}catch(e){}"
             "return window.__sInit?window.__sInit(CFG):'not-ready 先贴完整注入文件';})()\n" % (cfg['cfgv'], j))
    os.makedirs(data_dir(), exist_ok=True)
    for name, text in (('inject_%s.js' % p, full), ('inject_%s_cfg.js' % p, small)):
        with open(path(name), 'w', encoding='utf-8') as f:
            f.write(text)
    return cfg, full, small


# ---------- save ----------
H_FIELDS = ['platform', 'tag', 'why', 'sort', 'days', 'mode', 'total', 'kept', 'blocked', 'old', 'unknown', 'stale', 'kw', 'kwd',
            'seen', 'seenn', 'seenv', 'code', 'cfgv', 'time', 'part', 'parts']


def parse_parts(text):
    """把 get_page_text 的文字切回各段。返回 {段号: (头, 行列表)}。"""
    segs = [s.strip() for s in text.split('@@')[1:]]
    parts, cur = {}, None
    for s in segs:
        f = [x.strip() for x in s.split('|')]
        if f[0] == 'H':
            if len(f) != len(H_FIELDS) + 1:
                raise Stop('头行格式不对：页面上的脚本可能是旧版（重新 inject，贴完整文件，再跑一遍），或者取的不是本工具的结果')
            cur = dict(zip(H_FIELDS, f[1:]))
            cur['_rows'] = []
        elif f[0] in ('R', 'B'):
            if cur is None or len(f) != (13 if f[0] == 'R' else 8):
                raise Stop('结果行格式不对：' + s[:60])
            cur['_rows'].append(f)
        elif f[0] == 'E':
            m = re.match(r'E\|(\d+)\|(\d+)\|(\d+)', s)  # 后面可能跟着下一个文件开头的标题、网址
            if cur is None or not m:
                raise Stop('结尾行格式不对')
            f = ['E'] + list(m.groups())
            if f[1] != cur['part'] or f[2] != cur['parts'] or int(f[3]) != len(cur['_rows']):
                raise Stop('第 %s 段没取全（应有 %s 行，取到 %d 行）。重新 __sShow(%d) 再 get_page_text。'
                           % (cur['part'], f[3], len(cur['_rows']), int(cur['part']) - 1))
            parts[int(cur['part'])] = cur
            cur = None
    if cur is not None:
        raise Stop('第 %s 段没有结尾行，没取全。重新 __sShow(%d) 再 get_page_text。' % (cur['part'], int(cur['part']) - 1))
    return parts


def cmd_save(args):
    if len(args) < 2 or args[0] not in PLATFORMS:
        raise Stop('用法：save boss|zhilian 文件 [文件…]')
    p = args[0]
    text = ''
    for fn in args[1:]:
        with open(fn, encoding='utf-8') as f:
            text += '\n' + f.read()
    parts = parse_parts(text)
    if not parts:
        raise Stop('文件里没有扫描结果（找不到 @@H 开头的行）')
    head = parts[min(parts)]
    n = int(head['parts'])
    miss = [k for k in range(1, n + 1) if k not in parts]
    if miss:
        raise Stop('一共 %d 段，还缺第 %s 段：页面执行 __sShow(段号-1) 再 get_page_text' % (n, '、'.join(map(str, miss))))
    if head['platform'] != p:
        raise Stop('这是 %s 的结果，不是 %s 的' % (head['platform'], p))
    want = page_cfg(p)
    if head['code'] != want['code']:
        raise Stop('页面上的脚本是旧版（代码 %s，现在是 %s）：重新 inject，贴完整文件，再跑一遍' % (head['code'], want['code']))
    if head['cfgv'] != want['cfgv']:
        raise Stop('页面用的配置是旧的（配置 %s，现在是 %s，黑名单或天数改过）：贴 %s，'
                   '页面会按新配置重判，再 __sShow() 取一次' % (head['cfgv'], want['cfgv'], path('inject_%s_cfg.js' % p)))
    old = saved_before(p, head['time'])
    if old:
        raise Stop('这次扫描已经存过了：%s。看结果直接读这个文件；要重新扫，就对这个标签重跑 __sRun。'
                   '（同一次扫描不存第二遍：第一遍已把列出的岗位记为看过，再存会全被当成看过的跳过）' % old)
    # 页面按它手里的看过记录先跳过了一些。那份记录只能比现在的少（之后又记了新的），不能是清空或改过以前的，不然会漏列
    codes, n = seen_codes(p), int(head['seenn'] or 0)
    if int(head['seen']) and (n > len(codes) or short_hash(''.join(codes[:n])) != head['seenv']):
        raise Stop('页面用的看过记录和现在的对不上（看过的记录清空或改过）：先 python3 jobscan.py inject %s，'
                   '页面执行 %s（页面会按新记录重判已读到的），再从 __sShow() 第 1 段重新取' % (p, path('inject_%s_cfg.js' % p)))
    page_rows, blocked = [], []
    for k in sorted(parts):
        for f in parts[k]['_rows']:
            r = {'id': f[1], 'company': f[2], 'job': f[3], 'salary': f[4], 'published': f[5], 'location': f[6],
                 'link': LINK[p].format(f[1])}
            if f[0] == 'R':
                r.update(exp=f[7], degree=f[8], hr=f[9], skills=f[10], desc=f[11], note=f[12])
                page_rows.append(r)
            else:
                r['hit'] = f[7]
                blocked.append(r)
    if len(page_rows) != int(head['kept']) or len(blocked) != int(head['blocked']):
        raise Stop('行数和头行对不上（留下 %d/%s，黑名单 %d/%s），重新取' % (len(page_rows), head['kept'], len(blocked), head['blocked']))
    meta = {k: head[k] for k in H_FIELDS if k not in ('part', 'parts', 'seenn', 'seenv')}
    meta['days'] = int(head['days'])
    for k in ('total', 'blocked', 'old', 'unknown', 'stale', 'kw'):
        meta[k] = int(head[k])
    meta['kwd'] = parse_kwd(head['kwd'])
    meta['refresh'], meta['oldr'] = want['refresh'], want['old']
    # 这个平台还没有看过的记录（第一次扫，或清空过）：一个标签就会列出几百条，报告按岗位名归类给个数
    meta['first'] = not any(e.get('platform') == p for e in load('seen.json', []))
    rows, skipped = sift(p, page_rows)
    meta['kept'] = len(rows)
    meta['repost'] = sum(1 for r in rows if r.get('repost'))
    meta['near'] = find_near(p, rows)
    meta['watch'] = find_watch(rows, load('config.json', {}))
    for why, k in (('投过', 'applied'), ('看过', 'seen'), ('重复', 'dup')):
        meta[k] = sum(1 for r in skipped if r['why'] == why)
    meta['seen'] += int(head['seen'])  # 页面按编号先跳过的看过的
    if meta['first'] and len(rows) > LIST_MAX:
        meta['groups'] = title_groups(rows)
    stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    tag = re.sub(r'[\\/:*?"<>|\s]+', '_', head['tag'])[:30] or '列表'
    base = path('results', '%s_%s_%s' % (stamp, p, tag))
    k = 1
    while os.path.exists(base + '.json'):
        k += 1
        base = path('results', '%s_%s_%s-%d' % (stamp, p, tag, k))
    os.makedirs(path('results'), exist_ok=True)
    with open(base + '.json', 'w', encoding='utf-8') as f:
        json.dump(dict(meta, rows=rows, blocked=blocked, skipped=skipped), f, ensure_ascii=False, indent=1)
    with open(base + '.md', 'w', encoding='utf-8') as f:
        f.write(render_md(meta, rows, blocked, skipped))
    remember_seen(p, rows, [r for r in skipped if r['why'] == '看过'])
    print(summary(meta))
    if meta.get('groups'):
        print(groups_text(meta['groups'], len(rows)))
    gone = drop_page_files(args[1:])
    if gone:
        print('读过的页面文字文件已删（%d 个），下一个标签照样存 page_%s_1.txt' % (gone, p))
    cfg, _, small = write_inject(p)
    print('看过的记录更新了（%s共 %d 条）。接着扫%s的下一个标签前，页面先执行 %s（%d 字），返回「看过%d条」再开扫'
          % (PLATFORMS[p], cfg['seenn'], PLATFORMS[p], path('inject_%s_cfg.js' % p), len(small), cfg['seenn']))
    print('结果文件：' + base + '.md')
    note = task_saved(p, head['tag'], head['why'], base + '.md')
    if note:
        print(note)
    return 0


def drop_page_files(files):
    """save 成功后删掉读过的页面文字文件（只删 data/ 里 page_ 开头的）：下一个标签还存同样的名字，Claude 的 Write 不能覆盖没读过的旧文件。"""
    n = 0
    for fn in files:
        if os.path.basename(fn).startswith('page_') and os.path.dirname(os.path.realpath(fn)) == os.path.realpath(data_dir()):
            os.remove(fn)
            n += 1
    return n


# 报告里一次最多列多少条；第一次扫超过这么多，按岗位名归类给个数
LIST_MAX = 40


def title_groups(rows, top=15):
    """按岗位名归类（整理后一样的算一类，名字用第一次出现的写法），条数多的在前。返回 [(岗位名, 条数)]，最后一项可能是 ('其他', 条数)。"""
    by = {}
    for r in rows:
        k = job_norm(r['job']) or r['job']
        name, n = by.get(k, (r['job'], 0))
        by[k] = (name, n + 1)
    g = sorted(by.values(), key=lambda x: -x[1])
    rest = sum(n for _, n in g[top:])
    return g[:top] + ([('其他', rest)] if rest else [])


def groups_text(groups, total):
    return ('这个平台的看过记录原来是空的（第一次扫，或清空过），所以列得多；以后只列新冒出来的。'
            '按岗位名归类（共 %d 条）：%s' % (total, '、'.join('%s %d 条' % g for g in groups)))


def saved_before(platform, when):
    """同一次扫描（页面头行里的开始时间）存过没有，存过就返回那份 md。"""
    for f in glob.glob(path('results', '*.json')):
        with open(f, encoding='utf-8') as fh:
            d = json.load(fh)
        if when and d.get('platform') == platform and d.get('time') == when:
            return f[:-5] + '.md'
    return None


def parse_kwd(s):
    """头行里的按词计数「词:条数,词:条数」。"""
    out = {}
    for x in filter(None, s.split(',')):
        w, _, n = x.rpartition(':')
        if not w or not n.isdigit():
            raise Stop('头行里关键词的计数格式不对：' + s)
        out[w] = int(n)
    return out


def _parse_pub_dt(s):
    m = re.match(r'(\d{4})-(\d{1,2})-(\d{1,2})(?:[ T](\d{1,2}):(\d{2})(?::(\d{2}))?)?', str(s or '').strip())
    if not m:
        return None
    y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    hh, mm, ss = int(m.group(4) or 0), int(m.group(5) or 0), int(m.group(6) or 0)
    try:
        return datetime.datetime(y, mo, d, hh, mm, ss)
    except ValueError:
        return None


def _applied_bound(e):
    d_str = str(e.get('date') or '').strip()
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', d_str):
        return None
    d = datetime.date.fromisoformat(d_str)
    return datetime.datetime.combine(d, datetime.time(23, 59, 59))


def _is_repost(r, applied_entry, cfg):
    if cfg.get('reposts') != 'remind':
        return False
    pub_dt = _parse_pub_dt(r.get('published'))
    bound_dt = _applied_bound(applied_entry)
    return bool(pub_dt and bound_dt and pub_dt > bound_dt)


def sift(platform, rows):
    """页面留下的岗位，再按投过、看过、这次重复筛一遍。返回 (留下的, 跳过的)。"""
    cfg = load('config.json', {})
    applied = Index(load('applied.json', []))
    seen = Index(load('seen.json', []))
    kept = Index()
    keep, skipped = [], []
    for r in rows:
        repost_info = None
        for why, idx in (('投过', applied), ('看过', seen), ('重复', kept)):
            e = idx.find(platform, r)
            if e:
                if why == '投过' and _is_repost(r, e, cfg):
                    when = e.get('date') if e.get('dated', True) else '之前（日期未详，在 %s 之前）' % e.get('date', '')
                    repost_info = {'applied_date': e.get('date') or '',
                                   'reminder': '这个岗位你 %s 投过，现在重新发布了，再投不投由你决定' % when}
                    continue
                if why == '看过' and repost_info and e.get('id') != r.get('id'):
                    # 重发的新编号不能被投递前看过的旧编号吃掉；但如果这个重发编号自身或当天之后已看过则照常跳过
                    pub_day = str(r.get('published') or '')[:10]
                    if e.get('date') and pub_day > e['date']:
                        continue
                skipped.append(dict(r, why=why, hit='%s / %s%s' % (e['company'], e['job'], '（%s）' % e['date'] if e.get('date') else ''),
                                    diff='' if why == '看过' else verdict(*compare(r, e))))
                break
        else:
            if repost_info:
                r = dict(r, repost=repost_info)
            keep.append(r)
            kept.add(dict(r, platform=platform))
    return keep, skipped


def remember_seen(platform, rows, again=()):
    """列给使用者的岗位记为看过；列表里看得到的几项也存下，以后扫到同公司标题相近的好比异同。
    again 是按同公司同岗位认出的看过：这次的编号还没记过（换了编号重发，或以前是在另一个平台记的），也记上，
    下次页面按编号就能先跳过，不用每次取回来再由 save 去掉。"""
    seen = load('seen.json', [])
    have = {(e.get('platform'), e.get('id')) for e in seen}
    today = datetime.date.today().isoformat()
    new = list(rows) + [r for r in again if (platform, r['id']) not in have]
    seen += [dict({'platform': platform, 'id': r['id'], 'company': r['company'], 'job': r['job'], 'date': today}, **cmp_fields(r)) for r in new]
    dump('seen.json', seen)


# 同公司标题相近的岗位：只注明列表里看得到的几项哪些一样、哪些不同，不合并（宁可多列一条）。
# 岗位描述 Boss 列表里没有，智联只有开头七十来个字；全文在岗位页里，工具不点开，要细比请使用者点链接。
CMP = (('salary', '薪资'), ('location', '地点'), ('exp', '经验'), ('degree', '学历'), ('hr', '招聘人'), ('skills', '技能标签'),
       ('desc', '描述开头'))


def cmp_fields(r):
    return {k: r[k] for k, _ in CMP if r.get(k)}


def compare(a, b):
    """返回 (一样的几项, 不一样的几项)。哪边没有这一项就不比。"""
    same, diff = [], []
    for k, name in CMP:
        x, y = str(a.get(k) or '').strip(), str(b.get(k) or '').strip()
        if not x or not y:
            continue
        if (set(x.split('、')) == set(y.split('、'))) if k == 'skills' else x == y:
            same.append(name)
        else:
            diff.append('描述开头不同' if k == 'desc' else '%s：%s / %s' % (name, x[:40], y[:40]))
    return same, diff


def verdict(same, diff, near=False):
    if diff:
        return '；'.join(diff)
    if same:
        return '能比的几项都一样' + ('，可能只是改了标题' if near else '')
    return '那条没存详细信息，点链接对比'


def near_title(a, b):
    """标题相近：整理后一个包含另一个，但不算同一个岗位（同一个岗位已按重复、看过、投过跳过）。"""
    x, y = job_norm(a), job_norm(b)
    if len(x) < 2 or len(y) < 2 or job_key(a) == job_key(b):
        return False
    return x in y or y in x


def find_near(platform, rows):
    """留下的岗位里，和这次前面列出的、看过的、投过的同公司标题相近的，记在 r['near']。返回有相近的条数。"""
    pools = []
    for why, entries in (('投过的', load('applied.json', [])), ('看过的', load('seen.json', []))):
        by = {}
        for e in entries:
            by.setdefault(co_norm(e.get('company')), []).append(e)
        pools.append((why, by))
    n = 0
    for i, r in enumerate(rows):
        c = co_norm(r['company'])
        hits = [('第 %d 条「%s」' % (j + 1, rows[j]['job']), rows[j]) for j in range(i)
                if co_eq_n(co_norm(rows[j]['company']), c) and near_title(r['job'], rows[j]['job'])]
        for why, by in pools:
            for ec, es in by.items():
                if co_eq_n(ec, c):
                    for e in reversed(es):  # 新记的在前
                        if near_title(r['job'], e['job']):
                            other = e.get('platform') and e['platform'] != platform
                            hits.append(('%s%s「%s」%s' % (why, '（%s）' % PLATFORMS[e['platform']] if other else '', e['job'],
                                                         '（%s）' % e['date'] if e.get('date') else ''), e))
        out, labels = [], set()
        for label, o in hits:
            if label not in labels and len(out) < 3:
                labels.add(label)
                same, diff = compare(r, o)
                out.append({'with': label, 'same': '、'.join(same) or '—', 'diff': verdict(same, diff, near=True)})
        if out:
            r['near'] = out
            n += 1
    return n


def find_watch(rows, cfg):
    """用关注清单匹配留下的岗位（仅高亮提醒，不筛选）。返回命中的条数。"""
    companies, words = _watch_items(cfg)
    if not companies and not words:
        return 0
    n = 0
    for r in rows:
        hits = ['关注公司：' + c for c in companies if co_eq(r.get('company'), c)]
        blob = norm(' '.join(str(r.get(k) or '') for k in ('job', 'skills', 'desc')))
        hits += ['关注词：' + w for w in words if norm(w) in blob]
        if hits:
            r['watch'] = hits
            n += 1
    return n


def summary(m):
    p = m['platform']
    s = '%s · %s：翻到「%s」，共读 %d 条，留下 %d 条。黑名单跳过 %d 条' % (PLATFORMS[p], m['tag'], m['why'], m['total'], m['kept'], m['blocked'])
    if p == 'zhilian':
        s += '，超过 %d 天跳过 %d 条，发布时间不明跳过 %d 条' % (m['days'], m['old'], m['unknown'])
        if m.get('refresh') != 'latest':
            s += '（凌晨刷新又查不到首次发布）'
        if m.get('oldr'):
            s += '，首次发布超过 %d 天（%d 天以内）的老岗位跳过 %d 条' % (m['oldr'][0], m['oldr'][1], m['stale'])
    s += '，关键词跳过 %d 条' % m['kw']
    if m['kwd']:
        s += '（%s）' % '、'.join('%s %d 条' % (w, n) for w, n in m['kwd'].items())
    s += '，投过的跳过 %d 条，看过的跳过 %d 条，重复的丢掉 %d 条' % (m['applied'], m['seen'], m['dup'])
    if m.get('repost'):
        s += '。其中 %d 条是你以前投过、现在重新发布的（已标出提醒）' % m['repost']
    if m.get('watch'):
        s += '。特别留意命中 %d 条，已列在清单最前面' % m['watch']
    if m.get('near'):
        s += '。同公司标题相近的 %d 条，没合并，异同列在清单后面' % m['near']
    if p == 'zhilian':
        if m['sort'] != '最新':
            s += '。注意：没能切到「最新」排序，所以没按天数提前停，一直翻到了底'
    else:
        s += '。Boss 网页不显示发布时间，没按天数筛'
    return s


def render_md(m, rows, blocked, skipped=()):
    p = m['platform']
    cell = lambda s: str(s).replace('|', '／')
    out = ['# %s · %s · %s' % (PLATFORMS[p], m['tag'], datetime.datetime.now().strftime('%Y-%m-%d %H:%M')), '',
           summary(m) + '。拦法：' + MODES.get(m['mode'], m['mode']) + '。', '']
    if m.get('groups'):
        out += [groups_text(m['groups'], len(rows)), '', '| 岗位名 | 条数 |', '|---|---|'] + \
               ['| %s | %d |' % (cell(name), n) for name, n in m['groups']] + ['']
    watched = [(i, r) for i, r in enumerate(rows, 1) if r.get('watch')]
    if watched:
        out += ['## 特别留意命中', '', '| # | 公司 | 岗位 | 地点 | 薪资 | 发布时间 | 命中关注 | 链接 |', '|---|---|---|---|---|---|---|---|']
        for i, r in watched:
            pub = r['published'] or ('不显示' if p == 'boss' else '不明')
            if r.get('note'):
                pub += '（' + r['note'] + '）'
            out.append('| %d | %s | %s | %s | %s | %s | %s | [打开](%s) |' % (
                i, cell(r['company']), cell(r['job']), cell(r.get('location') or '—'),
                cell(r['salary']), cell(pub), cell('、'.join(r['watch'])), r['link']))
        out.append('')
    reposted = [(i, r) for i, r in enumerate(rows, 1) if r.get('repost')]
    if reposted:
        out += ['## 投过重发提醒', '', '| # | 公司 | 岗位 | 薪资 | 发布时间 | 提醒 | 链接 |', '|---|---|---|---|---|---|---|']
        for i, r in reposted:
            pub = r['published'] or ('不显示' if p == 'boss' else '不明')
            if r.get('note'):
                pub += '（' + r['note'] + '）'
            out.append('| %d | %s | %s | %s | %s | %s | [打开](%s) |' % (
                i, cell(r['company']), cell(r['job']), cell(r['salary']), cell(pub), cell(r['repost']['reminder']), r['link']))
        out.append('')
    out += ['| # | 公司 | 岗位 | 地点 | 薪资 | 发布时间 | 链接 |', '|---|---|---|---|---|---|---|']
    for i, r in enumerate(rows, 1):
        pub = r['published'] or ('不显示' if p == 'boss' else '不明')
        if r.get('note'):
            pub += '（' + r['note'] + '）'
        rep_mark = '（★投后重发：%s 投过）' % (r['repost']['applied_date'] or '之前') if r.get('repost') else ''
        job = r['job'] + ('（★留意：' + '、'.join(r['watch']) + '）' if r.get('watch') else '') + rep_mark + ('（有相近的，见下表）' if r.get('near') else '')
        out.append('| %d | %s | %s | %s | %s | %s | [打开](%s) |' % (i, cell(r['company']), cell(job), cell(r.get('location') or '—'),
                                                         cell(r['salary']), cell(pub), r['link']))
    near = [(i, r, x) for i, r in enumerate(rows, 1) for x in r.get('near', [])]
    if near:
        out += ['', '## 同公司标题相近的', '',
                '没合并，比的是列表里看得到的几项（薪资、地点、经验、学历、招聘人、技能标签，智联还有描述开头）；'
                '岗位描述全文在岗位页里，要细比请点两条的链接。', '',
                '| # | 公司 | 岗位 | 相近的 | 一样的 | 不一样的 |', '|---|---|---|---|---|---|']
        out += ['| %d | %s | %s | %s | %s | %s |' % (i, cell(r['company']), cell(r['job']), cell(x['with']), cell(x['same']), cell(x['diff']))
                for i, r, x in near]
    if blocked:
        out += ['', '## 黑名单拦下的', '', '| 公司 | 岗位 | 命中的黑名单 |', '|---|---|---|']
        out += ['| %s | %s | %s |' % (cell(r['company']), cell(r['job']), cell(r['hit'])) for r in blocked]
    # 看过的只给个数（可能很多）；投过的、重复的逐条列，方便核对有没有认错
    few = [r for r in skipped if r['why'] != '看过']
    if few:
        out += ['', '## 投过、重复跳过的', '', '| 原因 | 公司 | 岗位 | 薪资 | 对上的 | 和对上的那条比 |', '|---|---|---|---|---|---|']
        out += ['| %s | %s | %s | %s | %s | %s |' % (r['why'], cell(r['company']), cell(r['job']), cell(r['salary']), cell(r['hit']),
                                                 cell(r.get('diff') or '—')) for r in few]
    return '\n'.join(out) + '\n'


# ---------- 用例闸门 ----------
_GATE_RAN = False


def _code_hash():
    """计算主脚本、页面脚本与全部用例的内容指纹，用于跳过未改动时的重复跑测。"""
    h = hashlib.sha256()
    files = [os.path.abspath(__file__)]
    for sub in ('page', 'tests'):
        base = os.path.join(HERE, sub)
        for root, dirs, names in os.walk(base):
            dirs[:] = sorted(d for d in dirs if d != '__pycache__')
            for n in sorted(names):
                if not n.endswith('.pyc'):
                    files.append(os.path.join(root, n))
    for p in sorted(files):
        h.update(os.path.relpath(p, HERE).encode('utf-8') + b'\0')
        with open(p, 'rb') as f:
            h.update(f.read())
        h.update(b'\0')
    return h.hexdigest()


def gate(force=False):
    """跑全部用例（页面脚本 + 本文件，各带错误写法反例）。代码与用例未改且上次已通过时复用指纹；不过就退出，不往下走。"""
    global _GATE_RAN
    if _GATE_RAN and not force:
        return
    stamp = path('.gate_hash')
    sig = _code_hash()
    if not force:
        try:
            with open(stamp, encoding='utf-8') as f:
                if f.read().strip() == sig:
                    _GATE_RAN = True
                    return
        except FileNotFoundError:
            pass
    _GATE_RAN = True
    bad = []
    try:
        r = subprocess.run(['node', os.path.join(HERE, 'tests', 'test_page.js')], capture_output=True, text=True, timeout=120)
        if r.returncode != 0:
            bad.append('页面脚本用例没过：\n' + (r.stdout + r.stderr).strip()[-3000:])
    except FileNotFoundError:
        bad.append('找不到 node：页面脚本用例要用 Node.js 跑（见 README 安装）')
    sys.path.insert(0, os.path.join(HERE, 'tests'))
    import test_cli
    errs = test_cli.run_all(os.path.abspath(__file__))
    if errs:
        bad.append('命令用例没过：\n' + '\n'.join(errs))
    if bad:
        try:
            if os.path.exists(stamp):
                os.remove(stamp)
        except OSError:
            pass
        print('\n\n'.join(bad))
        print('\n用例没过，命令没有执行。')
        sys.exit(1)
    os.makedirs(data_dir(), exist_ok=True)
    with open(stamp, 'w', encoding='utf-8') as f:
        f.write(sig)


def dispatch(argv):
    if not argv:
        print(__doc__)
        return 0
    cmd, args = argv[0], argv[1:]
    try:
        if cmd == 'test':
            print('全部用例通过')
            return 0
        fn = {'config': cmd_config, 'block': cmd_block, 'alias': cmd_alias, 'keyword': cmd_keyword, 'watch': cmd_watch,
              'applied': cmd_applied, 'find': cmd_find, 'seen': cmd_seen, 'task': cmd_task, 'inject': cmd_inject, 'save': cmd_save}.get(cmd)
        if not fn:
            raise Stop('不认识的命令：%s（看 python3 jobscan.py 的说明）' % cmd)
        return fn(args)
    except Stop as e:
        print(str(e))
        return 2


def main(argv):
    gate(force=(bool(argv) and argv[0] == 'test'))
    return dispatch(argv)


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
