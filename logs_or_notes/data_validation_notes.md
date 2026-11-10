# Data Validation Notes

Sample: 2017-01 to 2026-10
Observations: 118

Oct 2026 checks:
- Data source: Spartan monthly performance PDF
- Source file: data/LSQ_latest_spartan.pdf
- Simulation: False
- Source months still marked as estimates: none
- S&P 500 TR source return: -0.869848%
- S&P 500 TR Yahoo exact return: -0.8698482722199641
- NVIDIA source return: -10.394958%
- NVIDIA Yahoo exact return: -10.394957958489249

The S&P 500 TR benchmark uses ^SP500TR because the paper's benchmark return includes dividend reinvestment.
Market returns use the last trading day's adjusted close for each calendar month.