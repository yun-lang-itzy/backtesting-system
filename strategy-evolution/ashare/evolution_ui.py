import json
import sqlite3
from contextlib import closing
from datetime import date, datetime
from uuid import uuid4
import pandas as pd
import streamlit as st
from .evolution import evaluate_versions, prepare_period, verdict
from .factors import TEMPLATES

METRICS = {'扣费后累计收益': 'total_return', '夏普': 'sharpe_rf_zero'}


def show_evolution(root, settings, source, params):
    with st.expander('策略演化 · 参数搜索与候选验证'):
        if st.button('发起演化', disabled=params is None):
            st.session_state.evo_setup = True
        folder = root / 'runs' / 'evolution'
        if st.session_state.get('evo_setup'):
            with st.form('evolution_setup'):
                question = st.text_input('研究问题')
                split = st.date_input('研究截止日（之后为独立验证期）',
                                      date.fromisoformat(settings['start']) +
                                      (date.fromisoformat(settings['end']) - date.fromisoformat(settings['start'])) // 2)
                metric = st.selectbox('主指标', list(METRICS))
                limit = st.number_input('允许最大回撤较对照增加（百分点）', 0., 100., 2.)
                budget = st.number_input('候选尝试预算', 1, 100, 10)
                allowed = st.multiselect('允许修改的参数', list(params or {}), default=list(params or {}))
                if st.form_submit_button('锁定口径并计算基线'):
                    try:
                        if not question.strip() or not settings['start'] < str(split) < settings['end'] or params is None:
                            raise ValueError('请填写问题、有效策略参数，并在运行区间内划分研究期')
                        base = dict(params=params, factor=None, parent=None, edit='基线')
                        exp = dict(question=question, split=str(split), settings=settings, source=source,
                                   allowed=allowed, budget=budget, metric=METRICS[metric], dd_limit=limit/100,
                                   versions=[base], stopped=[])
                        exp['fingerprint'], (base['result'],) = evaluate_versions(exp, [base])
                        folder.mkdir(parents=True, exist_ok=True)
                        name = datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+uuid4().hex[:8]
                        save(folder / (name+'.json'), exp)
                        st.session_state.evo_setup = False
                        st.session_state.evo_selected = name
                        st.rerun()
                    except Exception as exc:
                        st.error(str(exc))
        files = sorted(folder.glob('*.json'), reverse=True)
        if not files:
            return
        name = st.selectbox('演化实验', [p.stem for p in files], key='evo_selected')
        path = folder / (name+'.json')
        exp = json.loads(path.read_text())
        st.write(exp['question'])
        st.caption(f"研究截止 {exp['split']} · 主指标 {next(k for k,v in METRICS.items() if v==exp['metric'])} · 已尝试 {len(exp['versions'])-1}/{exp['budget']}")
        if st.checkbox('查看冻结的基线与运行口径'):
            st.json({'参数': exp['versions'][0]['params'], '可调参数': exp['allowed'],
                     '运行配置': exp['settings'], '允许回撤增加': exp['dd_limit']})
        research, validation = st.tabs(['演化研究', '独立验证'])
        with research:
            research_panel(path, exp, 'frozen' not in exp)
        with validation:
            validate_panel(path, exp)
        st.download_button('下载实验记录（含源码与参数）', path.read_bytes(), file_name=path.name)


def save(path, exp):
    with closing(sqlite3.connect(path.parent / 'writes.sqlite3')) as lock:
        lock.execute('BEGIN IMMEDIATE')
        rev = exp.get('revision', 0)
        if path.exists() and json.loads(path.read_text()).get('revision', 0) != rev:
            raise ValueError('实验已在其他窗口更新，请刷新后再试')
        exp['revision'] = rev + 1
        temp = path.with_suffix('.tmp')
        temp.write_text(json.dumps(exp, ensure_ascii=False, indent=2, allow_nan=False))
        temp.replace(path)


def research_panel(path, exp, editable):
    versions = exp['versions']
    baseline = versions[0]['result']
    metric = exp['metric']
    rows = []
    for i, v in enumerate(versions):
        row = {'版本': i, '父版本': v['parent'], '改动': v['edit']}
        if 'result' in v:
            r = v['result']
            if 'factor' in r:
                row.update({'因子 RankIC': r['factor'], '叠加后 RankIC 增量': r['increment'],
                            '与原权重秩相关': r['correlation']})
            parent = versions[v['parent']]['result'] if i else baseline
            row.update({'扣费收益': r['total_return'], '最大回撤': r['max_drawdown'],
                        '年单边换手': r['annual_one_way_turnover'], '主指标较父版本': r[metric]-parent[metric],
                        '主指标较初始基线': r[metric]-baseline[metric],
                        '相对父版本判定': verdict(r, parent, exp) if i else '基线'})
        else:
            row['失败原因'] = v['error']
        if i in exp['stopped']:
            row['状态'] = '已停止'
        rows.append(row)
    st.dataframe(pd.DataFrame(rows), hide_index=True)
    if any(v.get('factor') for v in versions):
        st.caption('RankIC 按调仓日、原目标股票计算，标签为下一开盘起的五日复权收益；等权或有效股票不足时相关性留空。')
    if not editable:
        return
    parents = [i for i,v in enumerate(versions) if 'result' in v and i not in exp['stopped']]
    if not parents:
        return
    parent = st.selectbox('继续探索的父版本', parents)
    if parent and st.button('停止此分支'):
        exp['stopped'].append(parent)
        save(path, exp)
        st.rerun()
    left = exp['budget'] - len(versions) + 1
    if not left:
        return
    kind = st.radio('改动类型', ['参数搜索','因子比较'], horizontal=True)
    original = versions[parent]
    if kind == '参数搜索':
        if not exp['allowed']:
            st.info('本实验未开放参数修改，可选择因子比较。')
            return
        key = st.selectbox('修改一个参数', exp['allowed'])
        values = st.text_input('候选值（JSON 数组）', placeholder='[20, 40, 60]')
    else:
        factors = st.multiselect('比较因子', list(TEMPLATES))
        st.caption('各候选分别按所选因子在原持仓内的排名缩放目标权重，余量留现金；已有因子会被替换。')
    if st.button('评估候选'):
        try:
            choices = json.loads(values) if kind == '参数搜索' else factors
            if not isinstance(choices,list) or not 1 <= len(choices) <= left:
                raise ValueError('候选数量须在剩余预算内')
            prepared = prepare_period(exp)
            added = 0
            for value in choices:
                p = dict(original['params'])
                factor = original['factor']
                if kind == '参数搜索':
                    p[key] = value
                    edit = f'{key}: {original["params"][key]} → {value}'
                else:
                    edit = f'因子：{factor or "无"} → {value}'
                    factor = value
                if any(v['params']==p and v['factor']==factor for v in versions):
                    continue
                v = dict(parent=parent, params=p, factor=factor, edit=edit)
                try:
                    _, (v['result'],) = evaluate_versions(exp, [v], prepared=prepared)
                except Exception as exc:
                    v['error'] = str(exc)
                added += 1
                versions.append(v)
                save(path, exp)
            if not added:
                st.info('这些候选已有记录，请选择其他改动。')
                return
            st.rerun()
        except Exception as exc:
            st.error(str(exc))


def validate_panel(path, exp):
    versions = exp['versions']
    if 'frozen' not in exp:
        ids = [i for i,v in enumerate(versions) if i and 'result' in v and i not in exp['stopped']]
        chosen = st.multiselect('锁定候选版本', ids)
        reason = st.text_input('入选理由')
        if st.button('冻结候选并结束研究', disabled=not (chosen and reason.strip())):
            exp.update(frozen=[0]+chosen, reason=reason)
            save(path, exp)
            st.rerun()
        return
    st.write('冻结版本', exp['frozen'], '入选理由', exp['reason'])
    if 'validation' not in exp:
        if st.button('运行独立验证'):
            try:
                _, exp['validation'] = evaluate_versions(exp, [versions[i] for i in exp['frozen']], True)
                save(path, exp)
                st.rerun()
            except Exception as exc:
                st.error(str(exc))
        return
    base = exp['validation'][0]
    st.caption('本实验的预留区间已使用。')
    rows = [{'版本': i, '扣费收益': r['total_return'], '较基线收益差': r['total_return']-base['total_return'],
             '最大回撤': r['max_drawdown'], '较基线回撤差': r['max_drawdown']-base['max_drawdown'],
             '结论': verdict(r, base, exp) if i else '基线'} for i,r in zip(exp['frozen'], exp['validation'])]
    st.dataframe(pd.DataFrame(rows), hide_index=True)
