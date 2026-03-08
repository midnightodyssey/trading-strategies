# Strategies sub-package
# Import all strategies here so users can do:
#   from framework.strategies import EMACrossover, RSIMeanReversion, PriceBreakout

from .crossover import EMACrossover, SMACrossover, MACDCrossover
from .mean_reversion import RSIMeanReversion, BollingerMeanReversion, TrendFilteredRSI
from .momentum import PriceBreakout, ATRBreakout
