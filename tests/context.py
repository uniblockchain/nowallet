import sys
import os
sys.path.append(os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.path.pardir, "nowallet")))
from nowallet import exchange_rate, scrape, socks_http