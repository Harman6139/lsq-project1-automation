# Data Validation Notes

Sample: 2017-01 to 2026-05
Observations: 113

May 2026 checks:
- Data source: Spartan monthly performance PDF
- Source file: data\LSQ_latest_spartan.pdf
- Simulation: False
- S&P 500 TR source return: 5.263305%
- S&P 500 TR Yahoo exact return: 5.263305489604209
- NVIDIA source return: 5.797466%
- NVIDIA Yahoo exact return: 5.797465881657349

The S&P 500 TR benchmark uses ^SP500TR because the paper's benchmark return includes dividend reinvestment.
Market returns use the last trading day's adjusted close for each calendar month.