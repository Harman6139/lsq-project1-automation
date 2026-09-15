# Data Validation Notes

Sample: 2017-01 to 2026-08
Observations: 116

Aug 2026 checks:
- Data source: Spartan monthly performance PDF
- Source file: data/LSQ_latest_spartan.pdf
- Simulation: False
- Source months still marked as estimates: 2026-08
- S&P 500 TR source return: 2.723308%
- S&P 500 TR Yahoo exact return: 2.7233078535142896
- NVIDIA source return: 9.977585%
- NVIDIA Yahoo exact return: 9.977585001332034

The S&P 500 TR benchmark uses ^SP500TR because the paper's benchmark return includes dividend reinvestment.
Market returns use the last trading day's adjusted close for each calendar month.