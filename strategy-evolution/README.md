# 策演 · 策略演化

本目录为同仓库因子研究工作台的增量模块。研究者指定参数或内置因子，在固定预算内比较候选，冻结候选后再进行样本外回测。研究与验证均在本机执行，无需模型服务或 API 密钥。

## 启动

从仓库根目录执行以下命令，在新的本地目录中启动工作台。请提供一个尚不存在的目标目录。

```sh
mkdir ceyan-local && unzip -q factor-research/factor-research-complete.zip -d ceyan-local
cp strategy-evolution/app.py strategy-evolution/test_evolution.py ceyan-local/factor-research/
cp strategy-evolution/ashare/*.py ceyan-local/factor-research/ashare/
mkdir -p ceyan-local/factor-research/runs/evolution
cp strategy-evolution/examples/*.json ceyan-local/factor-research/runs/evolution/
cd ceyan-local/factor-research
python -m pip install -r requirements.txt
python -m unittest test_evolution
python -m streamlit run app.py
```

在「策略开发与回测」中展开「策略演化 · 参数搜索与候选验证」即可查看示例。运行自己的实验时，在运行配置中指定本地 Feather 行情目录、股票池和回测区间，再点「发起演化」。

## 示例结果

实验使用 2024 年末前 20 个交易日成交额均为正、日均成交额排名前 100 的股票。研究区间为 2025-01-02 至 2026-03-31，比较了 3 个动量窗口和 2 个因子加权版本。与 60 日基线相比，只有 20 日动量同时满足扣费累计收益提高、最大回撤幅度增加不超过 2 个百分点。

| 2026-04-01 至 2026-10-16 样本外 | 60 日基线 | 20 日动量 |
|---|---:|---:|
| 扣费累计收益 | 8.60% | 14.92% |
| 最大回撤 | −17.73% | −13.65% |
| 年化夏普 | 0.68 | 1.15 |

[完整实验记录](examples/20261106-000605-momentum.json)包含固定股票池、基线源码、参数、行情指纹和所有候选结果。该样本外区间已用于验证。仓库仅提供实验结果，重算需自行准备同版本行情。
