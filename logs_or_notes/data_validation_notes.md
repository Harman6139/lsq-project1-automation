# Data Validation Notes

Sample: 2017-01 to 2026-07
Observations: 115

Jul 2026 checks:
- Data source: Spartan monthly performance PDF
- Source file: data/LSQ_latest_spartan.pdf
- Simulation: False
- Source months still marked as estimates: none
- S&P 500 TR source return: -0.063493%
- S&P 500 TR Yahoo exact return: -0.06349317981017011
- NVIDIA source return: 0.329853%
- NVIDIA Yahoo exact return: 0.3298534030631073

The S&P 500 TR benchmark uses ^SP500TR because the paper's benchmark return includes dividend reinvestment.
Market returns use the last trading day's adjusted close for each calendar month.