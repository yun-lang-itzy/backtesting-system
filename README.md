# 策演 · 策略开发与回测平台

本地运行的 A 股日频策略编辑、交易模拟和报告工具。使用已有 Feather 行情和已有历史 ST 状态清单；**不包含 ST 数据获取、登录、爬取或下载代码，也不分发任何市场数据**。

## 快速启动

建议 Python 3.11–3.13。先在项目目录创建虚拟环境：

```bash
python -m venv .venv
source .venv/bin/activate
# Windows: .venv\Scripts\activate
python -m pip install -r requirements.txt
python -m streamlit run app.py --server.address 127.0.0.1 --server.port 8501 --browser.gatherUsageStats false
```

访问 http://127.0.0.1:8501 。终端关闭会停止服务；可执行 `sh start.sh` 再次启动。

## 准备已有数据

默认本地目录（均已加入Git忽略）：

```text
data/
  feathers/
    open.feather
    high.feather
    low.feather
    close.feather
    amt.feather
    num_trades.feather
    cumadj.feather
  exclusions.csv
```

每个Feather文件含`date`及证券代码列（例如000001.SZ、600000.SH），日期递增唯一，七矩阵日期和证券完全对齐。价格为正，缺失为NaN；成交额暂按元，复权价格暂按原价×cumadj。使用者应先确认供应商定义。界面可修改数据路径。

ST清单使用已准备好的CSV：`symbol,start_date,end_date,status`，可选`known_date,reason`。空模板见exclusions.template.csv。状态支持ST、*ST、EXCLUDE、NORMAL、UNKNOWN，区间含首尾且同证券不重叠。未覆盖日期始终UNKNOWN；仅显式NORMAL表示正常。known_date省略时假设生效日开盘前已知。未知默认允许并标记，也可禁止新增买入。默认路径data/exclusions.csv需要实际文件；未提供时程序会报错，不能声称完成ST排除。

## 策略开发

在编辑区编写或载入strategies/momentum.py：

```python
from ashare import Strategy

class UserStrategy(Strategy):
    def on_close(self, context):
        prices = context.history('adjusted_close', 120)
        return None
```

- None：保持持仓；{}：下一交易日尝试清仓。
- 权重字典：下一交易日尝试调仓，遗漏证券目标为零；非负权重合计≤1。
- context提供date/cash/equity/positions/symbols/security_status/unknown_status_policy/is_week_end。
- history(field,bars)返回截至当前日的副本，字段为七个输入字段及adjusted_close。
- Python策略是受信任的本地代码，不是安全沙箱；不要运行不信任的策略或公开暴露服务。

默认模板仅周度调仓：60日动量跳过最近5日、120日趋势、20日日均成交额≥5000万元、正动量、候选池20日波动率80%分位过滤；先排除ST等证券再取前20，每只4.75%。不足20只保留现金。模板不是投资建议或策略有效性证明。

## 执行与账户模型

收盘形成目标，下一观察日开盘尝试成交。数量按信号日价格计算，次日先卖后买、按资金与历史成交额参与率限制成交；普通未成交订单当日失效。ST排除持仓持续尝试退出。估算开盘涨停拒买、跌停拒卖；一字价/零成交额拒绝；滑点价格越界拒绝。

采用小数复权单位账户，尚非真实股数账户，不精确模拟整手、分红到账、送转配股。历史ST涨跌停价、特殊交易状态及集合竞价容量尚不完整；成交为近似。日线全日信息仅作为事后撮合代理，不能证明开盘可成交。缺失估值沿用最近有效价格，记录滞后。输入日历未独立校验。

## 运行与结果

```bash
python run.py --config config.example.json --strategy strategies/momentum.py
python -m unittest discover -s . -p 'test_*.py' -v
```

界面任务采用独立进程，显示阶段/日期进度并可取消；任务状态和日志位于jobs/。服务重启后的进程取消不按未知PID强制操作。每次结果写入唯一runs/目录，保存策略、配置、代码/数据哈希、状态和逐日账户、订单、成交、持仓CSV。取消或失败的任务不列入完成报告。backtest.py是兼容旧原型的复现入口，日常使用app.py/run.py。

报告包括绩效、收益归因、逐证券贡献对账、未完成卖出/滞后估值持仓（5观察日长期标记）、交易质量、集中度、容量、年度/月度/滚动收益；HTML内嵌净值回撤、月度热力图、年度收益、证券贡献与成本敏感性PNG，可离线查看。Markdown请连同ZIP图片使用。

可选基准CSV(date,close)需覆盖所有日期及开始前一个收盘值；没有基准不生成虚构超额收益或现金机会成本。收益贡献=期末市值+卖出−买入−费用，滑点已含成交价。回加成本的毛损益不是无成本反事实。未完成卖出天数仅依据实际订单，不能证明每天都无法成交。

研究设置支持成本倍数真实重跑、最多10组策略参数、按时间训练/验证/测试和固定参数滚动前推，各分段独立资金、不自动拟合或选优；已观察历史不宣称未见样本外。

## 代码结构

| 目录/文件 | 功能 |
| --- | --- |
| app.py / run.py | 可视化/命令行入口 |
| ashare/data.py / universe.py | 本地数据契约、已有ST清单过滤 |
| ashare/strategy.py / strategies/ | 策略接口与示例 |
| ashare/engine.py / execution.py | 账户、撮合及约束 |
| ashare/runner.py / jobs.py / worker.py | 归档、后台进度及取消 |
| ashare/analytics.py / research.py / contributions.py / charts.py | 报告、研究验证及图表 |
| test_*.py | 合成数据离线测试，无需真实市场数据 |

原始行情、ST文件、运行结果、日志、个人路径和凭证均不应提交到仓库。

### 默认等权对比

新运行默认启用周度等权模拟对比组合，可在报告设置关闭，CLI配置 `equal_weight_comparison: false` 可关闭。独立账户与主策略共用资金、日期、股票池、状态政策及成交成本；120日有效历史、20日平均成交额至少5000万元，先过滤已知ST，然后95%仓位等权，不加动量、趋势、波动率筛选。未知状态不视为NORMAL，沿用配置处理。它采用复权权益份额，不是正式市场指数。报告含净值叠图、指标比较、累计收益差与相对净值，结果包含独立订单、成交和账户证据。旧运行不自动重算。

### 新增周度模板

- 低波动：120日有效历史，20日平均成交额至少5000万元，状态过滤后按60日收益波动率升序取20只，各占95%/20；不足留现金。参数 lookback、top_n、investment、min_adv。
- 趋势动量 · 动态仓位：同基础过滤，先计算站上120日均线的股票比例b，总目标仓位为 min_exposure+(max_exposure-min_exposure)*b，默认0至95%。再沿用正动量、趋势、波动率80%分位过滤，前20只各占总仓位/20。参数另含 lookback、skip、top_n、trend_days、min_adv。宽度基于所配置股票池，不代表全市场指数；未知状态沿用运行配置。
- 模板在周末收盘发信号、下一交易日尝试成交；不足数量留现金；不保证降低回撤。选择后点击“载入所选模板”生效，构造参数JSON须与模板匹配。

### 可视化策略参数

内置模板提供20/50/100及自定义持股数、20日成交额门槛（界面万元）、单股目标上限、目标仓位，另有动量窗口/跳过日、波动窗口和趋势均线。动态模板支持仓位下限及上限。每股目标=min(当周总目标/top_n,max_weight)，不足或受上限约束的份额留现金；实际权重会随价格漂移。高级JSON覆盖同名控件，合并结果显示并归档。自定义或旧代码仅用JSON，需载入新版模板才能使用控件。不改变等权对比组合的固定定义。

### 结束方式

engine.terminal_mode 支持 hold（默认保留）、liquidate（末日开盘尝试全部卖出，禁止买入）、settle（正常尝试后，对剩余持仓按末日复权收盘价强制结算）。价格缺失时采用最后有效复权估值，记录stale_days；无有效估值则报错。强制结算忽略成交约束、扣卖出佣金及税费、不加滑点，仅是研究假设。settlements.csv及trades.execution_type标识假设记账；账户、贡献、换手与交易统计包含它。等权对比使用相同结束规则；研究分段每段独立应用。实际结束日取所选日期范围内最后数据观察日。首日建仓行为不因该选项改变。


### 强制首日建仓

所有新界面/CLI运行强制使用first_open（覆盖旧配置scheduled），在首个回测交易日前一日收盘调用策略进行一次初始化，首日开盘必须至少产生一笔买入成交。历史不足、无合格非零目标或全部买单受阻均报错，不自动推迟。未买足部分仍受容量限制；不保证首日达到目标仓位。等权和独立研究分段共用规则；空仓验证模板不适用于新运行。底层simulate保留scheduled仅用于旧实验兼容测试。历史报告不改写。

## 已核验作业报告

[中期动量报告](reports/momentum/report.md) · [核验记录](reports/momentum/verification.md) · [运行配置与复现说明](reports/momentum/README.md)。10亿元、2025-01-02至2026-09-30，强制首日建仓、末日含假设结算。完整研究限制随报告列示。
