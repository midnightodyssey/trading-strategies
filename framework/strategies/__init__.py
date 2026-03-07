# Strategies sub-package
# Import all strategies here so users can do:
#   from framework.strategies import EMACrossover, RSIMeanReversion, PriceBreakout

from .crossover import EMACrossover, SMACrossover
from .mean_reversion import RSIMeanReversion, BollingerMeanReversion
from .momentum import PriceBreakout
