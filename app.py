"""Local strategy workbench. Run only code that you trust on your computer."""
import json
from pathlib import Path
import pandas as pd
import streamlit as st
from ashare.jobs import launch, read_state, cancel

ROOT=Path(__file__).resolve().parent
st.set_page_config(page_title='策演 · 策略开发与回测平台',layout='wide')
st.markdown('''<style>.block-container{padding-top:2rem;max-width:1400px} h1{letter-spacing:-1px} textarea{font-family:monospace!important} [data-testid="stAppViewContainer"]{background:#f7f9fc} [data-testid="stMetric"]{background:white;padding:18px;border:1px solid #e0e6ef;border-radius:12px} .stTabs [data-baseweb="tab-list"]{gap:24px} </style>''',unsafe_allow_html=True)
st.title('策演')
st.caption('策略开发与回测平台')
st.info('工作流程：设置运行配置 → 编写策略 → 运行回测 → 检查订单与账户')
with st.expander('运行配置 · 数据 / 时间 / 资金 / 成交', expanded=False):
    st.subheader('运行配置')
    data=st.text_input('Feather 数据目录','data/feathers')
    start=st.date_input('开始日期',pd.Timestamp('2024-01-02'))
    end=st.date_input('结束日期',pd.Timestamp('2025-12-31'))
    capital=st.number_input('初始资金（元）',min_value=1.,value=1_000_000.,step=10000.)
    pool=st.text_area('股票池（留空为全部沪深代码）',placeholder='000001.SZ,600000.SH,300750.SZ')
    exclusion_path=st.text_input('已有 ST 状态清单 CSV',value='data/exclusions.csv',help='symbol,start_date,end_date,status；支持ST、*ST、NORMAL、UNKNOWN、EXCLUDE。区间含首尾。')
    unknown_policy=st.selectbox('未知状态处理',['allow','block'],format_func=lambda x:'允许参与，明确标记未知' if x=='allow' else '禁止新增买入')
    st.caption('未覆盖日期始终为UNKNOWN；只有显式NORMAL才是非ST。known_date可指定状态最早可知日期，默认生效日开盘前可知。')
    st.selectbox('账户口径',['复权单位研究模式'])
    entry_mode='first_open'
    st.info('强制首日建仓：按前一交易日信号，首个回测交易日必须有买入成交；无目标或全部受阻将报错。成交容量仍可能导致未买足目标仓位。')
    terminal_mode=st.selectbox('结束方式',['hold','liquidate','settle'],format_func=lambda x:{'hold':'保留持仓','liquidate':'结束日尝试清仓','settle':'强制结算（研究假设）'}[x])
    if terminal_mode=='settle': st.warning('剩余持仓按当日收盘或最后有效估值强制现金化，扣卖出费用；忽略成交限制，不代表真实成交。')
    strict=st.checkbox('要求完整逐日交易状态',help='现有数据不支持，勾选后会停止运行。')
    with st.container(border=True):
        fee=st.number_input('双边费用（bps）',min_value=0.,value=3.)
        sell=st.number_input('卖出额外费用（bps）',min_value=0.,value=5.)
        slip=st.number_input('滑点（bps）',min_value=0.,value=5.)
        participation=st.number_input('历史日均成交额参与率',min_value=.00001,max_value=1.,value=.001,format='%.5f')
with st.expander('报告与研究验证', expanded=False):
    equal_weight_comparison=st.checkbox('周度等权模拟对比组合',value=True,help='同股票池及交易约束，95%等权；不使用动量、趋势或波动率排名。新增独立模拟会增加运行时间。')
    benchmark_path=st.text_input('基准CSV路径（可选，date与close列）',help='需覆盖所有回测日期及起始日前一收盘值；建议使用总收益指数。')
    cost_check=st.checkbox('重跑成本敏感性（费用及滑点 ×1.5、×2）',value=True)
    parameter_sets=st.text_area('参数敏感性 JSON 列表',value='[]',help='例如 [{"lookback":10},{"lookback":40}]；策略构造函数须接受这些参数。')
    validation_mode=st.selectbox('时间验证',['none','split','walk_forward'],format_func=lambda x:{'none':'不分段','split':'训练 / 验证 / 测试','walk_forward':'滚动前推（固定参数诊断）'}[x])
    train_end=st.date_input('训练结束日期',pd.Timestamp('2024-12-31'))
    validation_end=st.date_input('验证结束日期',pd.Timestamp('2025-06-30'))
    train_days=st.number_input('前推历史窗口（交易日）',min_value=2,value=252)
    test_days=st.number_input('前推评估窗口（交易日）',min_value=2,value=63)
    st.caption('分段按时间顺序，每段独立资金启动。已观察历史不称为未见样本；不自动选优或使用测试期调参。')
editor, rules = st.tabs(['策略编辑', '接口与执行规则'])
with editor:
    st.subheader('策略编辑')
    templates={'中期动量 · 周度调仓':'momentum.py','低波动 · 周度调仓':'low_volatility.py','趋势动量 · 动态仓位':'dynamic_momentum.py','空仓 · 系统验证':'cash.py'}
    template=st.selectbox('策略起点',list(templates))
    st.caption('选择后点击载入才替换代码；下方参数仅对匹配的内置模板启用。')
    if 'source' not in st.session_state or (st.session_state.get('template_version') != 'weekly-v1' and 'if not context.is_month_end:' in st.session_state.source):
        st.session_state.source=(ROOT/'strategies/momentum.py').read_text()
    st.session_state.template_version='weekly-v1'
    if st.button('载入所选模板（替换编辑区）'):
        st.session_state.source=(ROOT/'strategies'/templates[template]).read_text()
    source=st.text_area('Python 策略代码',key='source',height=540)
    matched=next((name for name in templates.values() if source==(ROOT/'strategies'/name).read_text()),None)
    visual_params={}
    if matched and matched!='cash.py':
        with st.expander('策略参数',expanded=True):
            count=st.selectbox('持股数量',[20,50,100,'自定义'],key='count_'+matched)
            if count=='自定义': count=int(st.number_input('自定义持股数量',min_value=1,value=30,key='custom_'+matched))
            liquidity=st.number_input('20日平均成交额门槛（万元）',min_value=0.,value=5000.,step=1000.,key='adv_'+matched)
            cap=st.number_input('单股目标权重上限（%）',min_value=.01,max_value=100.,value=5.,key='cap_'+matched)
            investment=st.number_input('目标股票仓位（%，动态策略为上限）',min_value=0.,max_value=100.,value=95.,key='invest_'+matched)
            visual_params=dict(top_n=int(count),min_adv=liquidity*10000,max_weight=cap/100)
            if matched=='low_volatility.py':
                visual_params['investment']=investment/100
                visual_params['lookback']=int(st.number_input('波动率窗口（交易日）',min_value=2,value=60,key='vol_'+matched))
            else:
                visual_params['lookback']=int(st.number_input('动量窗口（交易日）',min_value=1,value=60,key='mom_'+matched))
                visual_params['skip']=int(st.number_input('动量跳过最近交易日数',min_value=0,value=5,key='skip_'+matched))
                visual_params['volatility_days']=int(st.number_input('波动率窗口（交易日）',min_value=2,value=20,key='vol_'+matched))
                visual_params['trend_days']=int(st.number_input('趋势均线长度（交易日）',min_value=2,value=120,key='trend_'+matched))
                if matched=='dynamic_momentum.py':
                    floor=st.number_input('动态仓位下限（%）',min_value=0.,max_value=100.,value=0.,key='floor_'+matched)
                    visual_params.update(min_exposure=floor/100,max_exposure=investment/100)
                else: visual_params['investment']=investment/100
            st.caption('单股目标=min(当周目标仓位÷持股数量，单股上限)。选股不足或触及上限的余额留现金；上限是调仓目标约束，价格漂移后实际权重可能超过。基础有效历史至少120日。')
    elif not matched:
        st.info('代码已自定义或为旧模板：使用下方JSON传参。如需可视化参数，请先载入新版模板。')
    strategy_params=st.text_area('策略构造参数 JSON',value='{}',height=80,help='高级覆盖：同名参数优先于上方控件；自定义代码时仅使用此JSON。')
    effective_params=None
    try:
        overrides=json.loads(strategy_params)
        if not isinstance(overrides,dict): raise ValueError('参数JSON必须是对象')
        effective_params={**visual_params,**overrides}
        st.caption('本次运行实际使用的参数（JSON覆盖已合并）')
        st.json(effective_params)
    except (ValueError,TypeError) as exc:
        st.error(str(exc))
    st.download_button('下载策略代码',source,file_name='strategy.py',mime='text/x-python')
with rules:
    st.subheader('接口与执行规则')
    st.markdown('''- 历史接口只返回当前收盘时点及以前的数据。
- 返回权重字典：下一日尝试调仓，遗漏证券目标为零。
- 返回 `None`：继续持有，不重新等权。
- 返回 `{}`：下一日尝试清仓。
- 开盘估算涨停不买、跌停不卖；一字价双向不成交。
- 订单当日失效，资金与历史成交额限制可能导致部分成交。''')
    st.warning('缺少历史 ST、准确交易状态及公司行为，使用近似涨跌停与复权单位账户；不模拟真实整手及分红到账。')
    with st.expander('最小策略接口'):
        st.code('''from ashare import Strategy
class UserStrategy(Strategy):
    def on_close(self, context):
        prices = context.history("adjusted_close", 20)
        # context.date / cash / equity / positions / symbols
        return None''',language='python')
        st.caption('权重非负且合计≤1；history支持open/high/low/close/amt/num_trades/cumadj/adjusted_close。')
    st.caption('Python 代码在本机执行，拥有当前进程权限；只运行自己信任的策略。历史接口不是代码安全沙箱。')
    if st.button('检查语法'):
        try: compile(source,'strategy.py','exec'); st.success('语法检查通过')
        except Exception as exc: st.error(str(exc))
settings=dict(equal_weight_comparison=equal_weight_comparison,exclusions=exclusion_path,unknown_status_policy=unknown_policy,data=data,start=str(start),end=str(end),symbols=[s.strip() for s in pool.replace('\n',',').split(',') if s.strip()],strict=strict,engine=dict(entry_mode=entry_mode,terminal_mode=terminal_mode,initial_cash=capital,fee_bps=fee,sell_extra_bps=sell,slippage_bps=slip,participation=participation))
if st.button('运行回测',type='primary'):
    try:
        settings['benchmark']=benchmark_path
        if effective_params is None: raise ValueError('请修正策略参数JSON')
        settings['strategy_params']=effective_params
        settings['research']=dict(cost_multipliers=[1.5,2] if cost_check else [],parameter_sets=json.loads(parameter_sets),validation=validation_mode,train_end=str(train_end),validation_end=str(validation_end),train_days=int(train_days),test_days=int(test_days))
        if st.session_state.get('active_job') and read_state(st.session_state.active_job)['status']=='running':
            st.warning('已有回测运行中，请先等待或取消。')
        else:
            st.session_state.active_job=launch(settings,source,ROOT)
            st.success('已启动后台回测，可查看进度或取消。')
    except Exception as exc: st.exception(exc)
@st.fragment(run_every=1)
def job_progress():
    if not st.session_state.get('active_job'): return
    job=st.session_state.active_job
    state=read_state(job)
    st.progress(state.get('progress',0),text=state.get('stage',''))
    if state['status']=='running':
        if st.button('取消当前回测',key='cancel_job'):
            cancel(job)
            st.rerun()
    elif state['status']=='complete':
        st.success('回测完成')
        if st.button('查看本次结果'):
            st.session_state.run_path=state['output']
            st.rerun()
    elif state['status']=='cancelled': st.warning('已取消；不完整结果不会列入已完成报告。')
    else: st.error(state.get('stage','运行失败'))
job_progress()
st.divider()
st.header('运行记录与结果')
paths=sorted((ROOT/'runs').glob('*/status.json'),reverse=True) if (ROOT/'runs').exists() else []
completed=[str(p.parent) for p in paths if json.loads(p.read_text()).get('status')=='complete']
if completed:
    selected=st.selectbox('历史运行',completed,index=completed.index(st.session_state.run_path) if st.session_state.get('run_path') in completed else 0,format_func=lambda p:Path(p).name)
    path=Path(selected); summary=json.loads((path/'summary.json').read_text())
    metrics=st.columns(4)
    for col,label,value in zip(metrics,['累计收益','年化收益','最大回撤','最终权益'],[f'{summary["total_return"]:.2%}',f'{summary["cagr"]:.2%}',f'{summary["max_drawdown"]:.2%}',f'{summary["final_equity"]:,.2f}']): col.metric(label,value)
    d=pd.read_csv(path/'daily.csv',parse_dates=['date']).set_index('date')
    nav=(d.equity/summary['initial_cash']).rename('主策略').to_frame()
    if (path/'comparison.csv').exists():
        comparison=pd.read_csv(path/'comparison.csv',parse_dates=['date']).set_index('date')
        nav['周度等权']=comparison.equal_weight_nav
        st.dataframe(pd.read_csv(path/'comparison_metrics.csv'),use_container_width=True)
        st.caption('周度等权模拟对比组合：独立成交、扣除成本；不代表正式市场指数。')
    else:
        st.caption('本次运行无等权对比结果；新运行默认启用。')
    st.line_chart(nav)
    if (path/'comparison.csv').exists():
        st.line_chart(comparison.relative_nav.rename('相对净值（主策略 / 等权）'))
    st.line_chart(nav/nav.cummax().clip(lower=1)-1)
    tabs=st.tabs(['订单','成交','持仓','每日账户','运行配置与策略'])
    for tab,name in zip(tabs[:4],['orders','trades','holdings','daily']):
        with tab:
            st.dataframe(pd.read_csv(path/(name+'.csv')),use_container_width=True)
            st.download_button('下载 '+name,(path/(name+'.csv')).read_bytes(),file_name=name+'.csv')
    with tabs[4]:
        st.json(json.loads((path/'config.json').read_text())); st.code((path/'strategy.py').read_text(),language='python')
    if (path/'status_coverage.csv').exists():
        with st.expander('证券状态覆盖与强制退出'):
            st.dataframe(pd.read_csv(path/'status_coverage.csv'),use_container_width=True)
    if (path/'security_contributions.csv').exists():
        st.subheader('证券贡献与待处理持仓')
        contribution_tab,risk_tab=st.tabs(['证券盈亏贡献','未完成卖出 / 滞后估值'])
        with contribution_tab: st.dataframe(pd.read_csv(path/'security_contributions.csv'),use_container_width=True)
        with risk_tab:
            st.caption('长期阈值：5个观察日；未完成卖出不等于连续每天无法成交。')
            st.dataframe(pd.read_csv(path/'unresolved_holdings.csv'),use_container_width=True)
    st.subheader('完整报告与研究分析')
    if (path/'report.md').exists():
        report_tabs=st.tabs(['完整报告','收益来源','交易质量与容量','稳定性','敏感性与时间验证','基准对照'])
        with report_tabs[0]:
            report_text=(path/'report.md').read_text()
            st.markdown(report_text.split('<!-- exported-charts -->')[0])
            for chart_name in ['chart_nav_drawdown.png','chart_monthly.png','chart_annual.png','chart_contributions.png','chart_costs.png']:
                if (path/chart_name).exists():st.image(str(path/chart_name))
            st.download_button('下载 Markdown 报告',(path/'report.md').read_bytes(),file_name='report.md')
            st.download_button('下载 HTML 报告',(path/'report.html').read_bytes(),file_name='report.html')
            import io,zipfile
            archive=io.BytesIO()
            with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
                for f in path.iterdir():
                    if f.is_file(): z.write(f,f.name)
            st.download_button('下载完整结果包',archive.getvalue(),file_name=path.name+'.zip')
        for tab,files in zip(report_tabs[1:],[['attribution.csv'],['concentration.csv','capacity.csv'],['annual_returns.csv','monthly_returns.csv','rolling_returns.csv'],['sensitivity.csv','validation.csv'],['benchmark.csv']]):
            with tab:
                for name in files:
                    st.caption(name)
                    frame=pd.read_csv(path/name)
                    st.dataframe(frame,use_container_width=True)
                if tab==report_tabs[4]: st.caption('固定参数历史诊断；无自动选优，前推各段独立资金，不能直接拼接为连续账户。')
    else:
        st.info('此历史运行早于完整报告模块；重新运行即可生成新报告，旧结果保留。')
    st.caption('结果目录：'+str(path))
else: st.info('编写或载入策略后点击“运行回测”。')
