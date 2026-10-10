# Data Validation Notes

Sample: 2017-01 to 2026-09
Observations: 117

Sept 2026 checks:
- Data source: Spartan monthly performance PDF
- Source file: data/LSQ_latest_spartan.pdf
- Simulation: False
- Source months still marked as estimates: none
- S&P 500 TR source return: -0.345700%
- S&P 500 TR Yahoo exact return: -0.3456998036319825
- NVIDIA source return: 3.558090%
- NVIDIA Yahoo exact return: 3.5580901393536646

The S&P 500 TR benchmark uses ^SP500TR because the paper's benchmark return includes dividend reinvestment.
Market returns use the last trading day's adjusted close for each calendar month.