# 策演 · 因子研究

因子研究代码与个人研究成果，2026-10-24 网页发布。

## 下载与运行

[下载完整研究包](factor-research-complete.zip)（约 5.6 MB）。解压后进入 factor-research 目录，按包内 README.md 操作。包内保留完整代码目录、57 项自动化测试、99 个研究成果文件，以及运行配置与哈希清单。

```bash
cd factor-research
python -m pip install -r requirements.txt
python -m streamlit run app.py --server.port 8502
```

在左侧选择“因子研究”。行情和历史 ST 清单需自行提供；不包含原始行情、ST 明细或 ST 获取代码。

## 个人研究成果

- 基础评价：2025 年一季度全市场中期动量，12 个采样日。
- 扩展诊断：2025 年固定排序前 200 只沪深股票，49 个采样日，含相关性、增量信号、分层、延迟、置信区间、参数尝试。
- 扩展样例包含 group_1、group_5、pool_equal 三个独立模拟账户的订单、成交、持仓及净值账本，期末保留持仓。
- 两份完整报告（Markdown、离线 HTML）及图表均在 ZIP 的 reports 目录内。

这些是功能联调与历史研究样例，不是样本外有效性证明；基础分组收益不等于计成本的可交易收益。历史报告数值不改写，仅将五份配置的本机路径替换为通用路径。运行时源码哈希与当前更新后的代码可能不同。

[发布核验](VERIFICATION.md) · [成果文件哈希清单](publication_manifest.json) · [压缩包 SHA-256](SHA256SUMS.txt)
