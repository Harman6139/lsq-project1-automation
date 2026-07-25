# Data Validation Notes

Sample: 2017-01 to 2026-06
Observations: 114

Jun 2026 checks:
- Data source: Spartan monthly performance PDF
- Source file: data/LSQ_latest_spartan.pdf
- Simulation: False
- S&P 500 TR source return: -0.952323%
- S&P 500 TR Yahoo exact return: -0.9523233980697987
- NVIDIA source return: -5.123049%
- NVIDIA Yahoo exact return: -5.123049341072095

The S&P 500 TR benchmark uses ^SP500TR because the paper's benchmark return includes dividend reinvestment.
Market returns use the last trading day's adjusted close for each calendar month.