# 中期动量作业报告

运行标识：20261020-111829-2cdbec7a。

- [图文报告（Markdown）](report.md)
- [离线HTML报告](report.html)（下载后用浏览器打开）
- [核验记录](verification.md) · [机器可读核验结果](verification.json)
- [可移植配置](config.json) · [策略](strategy.py)

报告包包含关键结果、输入/代码哈希和图表，不包含原始Feather、历史ST清单及ST获取代码；完整逐笔账本保留本地。

在仓库根目录提供自己的 data/feathers 与 data/exclusions.csv 后运行：

```bash
python run.py --config reports/momentum/config.json --strategy reports/momentum/strategy.py
```

必须使用与data_audit.json哈希一致的输入才能比较复现结果。数据路径仅为移植而改写，资金、费用、日期和策略参数未改。末日假设结算金额不代表可执行成交，详见核验记录。
