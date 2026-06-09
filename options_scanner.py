#!/usr/bin/env python3
"""
Automated Options Opportunity Scanner for Cash-Secured Put Selling
Research and screening tool only - does not place trades.

Scans S&P 500, Nasdaq 100, and user watchlist stocks for cash-secured put opportunities.
"""

import os
import sys
import json
import csv
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional, Tuple
import pandas as pd
import numpy as np

# Try to import required packages, provide helpful error messages if missing
try:
    import yfinance as yf
except ImportError:
    print("ERROR: yfinance package not installed. Install with: pip install yfinance")
    sys.exit(1)

# Shared browser-impersonating session — prevents Yahoo 429 rate limiting.
from scanner.yf_session import ticker as yf_ticker

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import wraps

from scanner.indicators import calculate_greeks, fetch_risk_free_rate, reset_risk_free_rate_cache
from scanner.technicals import get_technicals, tech_score, reset_tech_cache
from scanner.data_providers import (
    get_stock_price_and_volume,
    get_ohlcv_history,
    get_option_expirations,
    get_puts_chain,
    is_tradier_configured,
    is_alpaca_configured,
)


def _is_rate_limit(exc: Exception) -> bool:
    """True if an exception looks like a Yahoo 429 rate-limit error."""
    return "too many requests" in str(exc).lower() or "rate limit" in str(exc).lower()


def with_retry(fn, *, attempts: int = 4, base_delay: float = 2.0):
    """
    Call *fn* with exponential backoff on Yahoo rate-limit (429) errors.

    Backoff: base_delay, 2×, 4×, … with small jitter. Non-rate-limit
    exceptions propagate immediately (no point retrying a bad symbol).
    Returns whatever *fn* returns, or re-raises the last error.
    """
    import random

    last_exc = None
    for i in range(attempts):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if not _is_rate_limit(exc) or i == attempts - 1:
                raise
            delay = base_delay * (2 ** i) + random.uniform(0, 0.75)
            time.sleep(delay)
    if last_exc:
        raise last_exc


def retry(exception_to_check, tries=3, delay=2, backoff=2):
    """Retry decorator for handling transient errors.
    Retries the function up to `tries` times with exponential backoff.
    """
    def deco_retry(f):
        @wraps(f)
        def f_retry(*args, **kwargs):
            mtries, mdelay = tries, delay
            while mtries > 1:
                try:
                    return f(*args, **kwargs)
                except exception_to_check as e:
                    logger.warning(f"{f.__name__} failed with {e}, retrying in {mdelay}s...")
                    time.sleep(mdelay)
                    mtries -= 1
                    mdelay *= backoff
            return f(*args, **kwargs)
        return f_retry
    return deco_retry

try:
    import requests
except ImportError:
    print("ERROR: requests package not installed. Install with: pip install requests")
    sys.exit(1)

_LOG_DIR = Path(__file__).parent / "logs"
_LOG_DIR.mkdir(exist_ok=True)
_OUTPUT_DIR = Path(__file__).parent / "outputs"
_OUTPUT_DIR.mkdir(exist_ok=True)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(_LOG_DIR / 'options_scanner.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

class OptionsScanner:
    def __init__(self):
        """Initialize the options scanner."""
        # Alpaca API credentials (for future trade execution integration)
        self.alpaca_api_key = os.getenv('APCA_API_KEY_ID')
        self.alpaca_api_secret = os.getenv('APCA_API_SECRET_KEY')
        self.alpaca_base_url = os.getenv('APCA_API_BASE_URL', 'https://paper-api.alpaca.markets')

        # If Alpaca credentials are available, we could use them for stock data too
        # For now, using yfinance which is free and reliable for research

        # Scanner configuration
        self.dte_min = 1        # minimum days to expiration (overridden by run_scan)
        self.dte_max = 730      # maximum days to expiration
        self.min_open_interest = 100
        self.min_avg_volume = 1_000_000  # 1 million shares
        self.max_bid_ask_spread_pct = 0.10  # 10% of premium

        # Filter ranges
        self.delta_min = -0.30
        self.delta_max = -0.10

        # Flags for exceptional opportunities
        self.flag_min_risk_adjusted_yield = 10.0  # %
        self.flag_min_distance_otm = 15.0  # %
        self.flag_delta_max = -0.20  # Delta > -0.20 (less negative)
        self.flag_min_open_interest = 500

        logger.info("OptionsScanner initialized")

    @retry(Exception, tries=3, delay=2)
    def get_sp500_stocks(self) -> List[str]:
        """Get list of S&P 500 stock symbols."""
        local = Path(__file__).parent / "symbol_lists" / "sp500.json"
        if local.is_file():
            try:
                with local.open() as f:
                    symbols = [entry["symbol"] for entry in json.load(f)]
                logger.info(f"Loaded {len(symbols)} S&P 500 symbols from {local}")
                return symbols
            except Exception as e:
                logger.warning(f"Could not load local S&P 500 list: {e}")
        try:
            url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
            tables = pd.read_html(url)
            sp500_table = tables[0]
            symbols = sp500_table['Symbol'].str.replace('.', '-').tolist()
            logger.info(f"Retrieved {len(symbols)} S&P 500 symbols")
            return symbols
        except Exception as e:
            logger.error(f"Error retrieving S&P 500 list: {e}")
            return ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'META', 'NVDA', 'BRK-B', 'UNH', 'JNJ']

    @retry(Exception, tries=3, delay=2)
    def get_nasdaq100_stocks(self) -> List[str]:
        """Get list of Nasdaq 100 stock symbols."""
        local = Path(__file__).parent / "symbol_lists" / "nasdaq100.json"
        if local.is_file():
            try:
                with local.open() as f:
                    data = json.load(f)
                symbols = [entry["symbol"] for entry in data.get("nasdaq100", data)]
                logger.info(f"Loaded {len(symbols)} Nasdaq 100 symbols from {local}")
                return symbols
            except Exception as e:
                logger.warning(f"Could not load local Nasdaq 100 list: {e}")
        try:
            url = "https://en.wikipedia.org/wiki/Nasdaq-100"
            tables = pd.read_html(url)
            nasdaq100_table = tables[3]
            symbols = nasdaq100_table['Ticker'].str.replace('.', '-').tolist()
            logger.info(f"Retrieved {len(symbols)} Nasdaq 100 symbols")
            return symbols
        except Exception as e:
            logger.error(f"Error retrieving Nasdaq 100 list: {e}")
            return ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'META', 'NVDA', 'PEP', 'COST', 'ADBE']

    def get_watchlist_stocks(self, watchlist_file: str = "watchlist.txt") -> List[str]:
        """Get user-defined watchlist stocks from a file."""
        watchlist = []
        try:
            if os.path.exists(watchlist_file):
                with open(watchlist_file, 'r') as f:
                    for line in f:
                        symbol = line.strip().upper()
                        if symbol and not line.startswith('#'):  # Skip empty lines and comments
                            watchlist.append(symbol)
                logger.info(f"Loaded {len(watchlist)} symbols from watchlist file: {watchlist_file}")
            else:
                logger.info(f"Watchlist file {watchlist_file} not found, using empty watchlist")
                # Create a sample watchlist file
                with open(watchlist_file, 'w') as f:
                    f.write("# Add your stock symbols here, one per line\n")
                    f.write("# Example: AAPL\n")
                    f.write("# Example: MSFT\n")
        except Exception as e:
            logger.error(f"Error reading watchlist file {watchlist_file}: {e}")

        return watchlist

    def get_stock_data(self, symbol: str) -> Optional[Dict]:
        """
        Get current price and 30-day average volume for *symbol*.

        Provider order: Alpaca → yfinance (history endpoint, lighter than .info).
        Wrapped in exponential backoff so a transient 429 is retried rather
        than dropping the symbol entirely.
        """
        try:
            result = get_stock_price_and_volume(symbol)
            if result:
                return {
                    "symbol": symbol,
                    "current_price": result["current_price"],
                    "average_volume": result["average_volume"],
                    "currency": result.get("currency", "USD"),
                }
            logger.warning(f"Could not get stock data for {symbol}")
            return None
        except Exception as e:
            logger.warning(f"Error getting stock data for {symbol}: {e}")
            return None

    def _get_next_earnings(self, symbol: str) -> Optional[datetime]:
        """Return the next earnings date for symbol, or None if unavailable."""
        try:
            cal = yf_ticker(symbol).calendar
            if cal is None:
                return None
            # calendar is a dict with 'Earnings Date' key (list of Timestamps)
            if isinstance(cal, dict):
                dates = cal.get("Earnings Date") or cal.get("earningsDate") or []
                if not dates:
                    return None
                # may be a list or a single value
                if not hasattr(dates, '__iter__') or isinstance(dates, str):
                    dates = [dates]
                today = datetime.utcnow()
                future = [pd.Timestamp(d).to_pydatetime().replace(tzinfo=None)
                          for d in dates if pd.Timestamp(d).to_pydatetime().replace(tzinfo=None) >= today]
                return min(future) if future else None
        except Exception:
            return None

    def get_options_chain(self, symbol: str) -> Optional[pd.DataFrame]:
        """
        Fetch PUT option chains across ALL expirations within the DTE window.

        Provider order: Tradier → yfinance fallback.
        """
        try:
            today     = datetime.utcnow()
            min_date  = today + timedelta(days=self.dte_min)
            max_date  = today + timedelta(days=self.dte_max)

            # Get expiration dates (Tradier first, yfinance fallback)
            all_expirations = get_option_expirations(symbol)
            if not all_expirations:
                logger.warning(f"No options data available for {symbol}")
                return None

            valid_expirations = [
                exp for exp in all_expirations
                if min_date <= datetime.strptime(exp[:10], '%Y-%m-%d') <= max_date
            ]
            if not valid_expirations:
                logger.info(f"No expirations in DTE {self.dte_min}–{self.dte_max} for {symbol}")
                return None

            # Fetch chains for valid expirations (Tradier first, yfinance fallback)
            combined = get_puts_chain(symbol, valid_expirations)
            if combined is None or combined.empty:
                logger.warning(f"No PUT data retrieved for {symbol}")
                return None

            # Normalise 'expiration' column (may come as 'expiry' from Tradier path)
            if "expiry" in combined.columns and "expiration" not in combined.columns:
                combined = combined.rename(columns={"expiry": "expiration"})
            elif "expiration_date" in combined.columns and "expiration" not in combined.columns:
                combined = combined.rename(columns={"expiration_date": "expiration"})

            logger.info(f"Retrieved {len(combined)} PUTs across {len(valid_expirations)} expirations for {symbol}")
            return combined

        except Exception as e:
            logger.warning(f"Error getting options chain for {symbol}: {e}")
            return None

    def _enrich_with_greeks(self, options_df: pd.DataFrame, stock_price: float) -> pd.DataFrame:
        """Compute Black-Scholes Greeks when yfinance omits delta."""
        df = options_df.copy()
        df["option_type"] = "put"
        if "implied_volatility" not in df.columns and "impliedVolatility" in df.columns:
            df["implied_volatility"] = df["impliedVolatility"]
        if "open_interest" not in df.columns and "openInterest" in df.columns:
            df["open_interest"] = df["openInterest"]
        df["expiration"] = pd.to_datetime(df["expiration"])
        return calculate_greeks(df, underlying_price=stock_price)

    def calculate_metrics(self, row: pd.Series, stock_price: float) -> Dict:
        """Calculate all required metrics for an options contract."""
        try:
            # Extract basic data
            strike = float(row['strike'])
            premium = (float(row['bid']) + float(row['ask'])) / 2  # Mid-price
            bid = float(row['bid'])
            ask = float(row['ask'])
            delta = float(row["delta"]) if "delta" in row and not pd.isna(row["delta"]) else None
            if delta is None:
                return {}
            theta_raw = float(row["theta"]) if "theta" in row and not pd.isna(row["theta"]) else 0.0
            iv = float(row["implied_volatility"]) if "implied_volatility" in row and not pd.isna(row["implied_volatility"]) else 0.0
            oi_col = 'open_interest' if 'open_interest' in row else 'openInterest'
            open_interest = int(row[oi_col]) if oi_col in row and not pd.isna(row[oi_col]) else 0
            exp_raw = row['expiration'] if 'expiration' in row else row.name[1] if isinstance(row.name, tuple) else None
            if exp_raw is None or pd.isna(exp_raw):
                return {}
            if isinstance(exp_raw, (pd.Timestamp, datetime)):
                expiration_date = pd.Timestamp(exp_raw).to_pydatetime().replace(tzinfo=None)
                expiration_str = expiration_date.strftime('%Y-%m-%d')
            else:
                expiration_str = str(exp_raw)[:10]
                expiration_date = datetime.strptime(expiration_str, '%Y-%m-%d')
            days_to_expiration = (expiration_date - datetime.utcnow()).days
            years_to_expiration = max(days_to_expiration / 365.0, 0.001)  # Avoid division by zero

            # Calculate metrics
            # Annualized Yield = (Premium / Strike) / YearsToExpiration * 100
            annualized_yield = (premium / strike) / years_to_expiration * 100 if strike > 0 else 0

            # Risk-Adjusted Yield = (Premium / (Strike - Premium)) / YearsToExpiration * 100
            risk_adjusted_yield = (premium / (strike - premium)) / years_to_expiration * 100 if strike > premium else 0

            # Distance OTM % = ((CurrentPrice - Strike) / CurrentPrice) * 100
            distance_otm = ((stock_price - strike) / stock_price) * 100 if stock_price > 0 else 0

            # Bid-ask spread % of premium
            bid_ask_spread = ask - bid
            bid_ask_spread_pct = bid_ask_spread / premium if premium > 0 else float('inf')

            # Probability-weighted realistic yield: RAY × P(expire worthless) = RAY × (1 + delta)
            # delta is negative for puts, so (1 + delta) is the P(OTM at expiry)
            realistic_yield = risk_adjusted_yield * (1 + delta)

            # Capital required to secure this put (per contract)
            capital_required = strike * 100

            # Theta per contract per day (theta is per-share, ×100 for contract)
            theta_per_contract = theta_raw * 100

            return {
                'strike': strike,
                'premium': premium,
                'bid': bid,
                'ask': ask,
                'delta': delta,
                'theta_per_contract': round(theta_per_contract, 2),
                'implied_volatility': round(iv * 100, 2),  # as percentage
                'open_interest': open_interest,
                'expiration': expiration_str,
                'days_to_expiration': days_to_expiration,
                'years_to_expiration': years_to_expiration,
                'annualized_yield': annualized_yield,
                'risk_adjusted_yield': risk_adjusted_yield,
                'realistic_yield': realistic_yield,
                'distance_otm': distance_otm,
                'bid_ask_spread': bid_ask_spread,
                'bid_ask_spread_pct': bid_ask_spread_pct,
                'capital_required': capital_required,
            }
        except Exception as e:
            logger.warning(f"Error calculating metrics for option: {e}")
            return {}

    def filter_options(self, options_df: pd.DataFrame, stock_data: Dict) -> List[Dict]:
        """Filter options based on all criteria."""
        if options_df is None or options_df.empty:
            return []

        symbol = stock_data['symbol']
        stock_price = stock_data['current_price']
        avg_volume = stock_data['average_volume']

        # Filter 1: Exclude stocks with average daily volume below 1 million shares
        if avg_volume < self.min_avg_volume:
            logger.info(f"Excluding {symbol}: average volume {avg_volume} < {self.min_avg_volume}")
            return []

        options_df = self._enrich_with_greeks(options_df, stock_price)
        filtered_options = []

        for idx, row in options_df.iterrows():
            try:
                metrics = self.calculate_metrics(row, stock_price)
                if not metrics:
                    continue

                # Apply filters
                # 1. DTE must be within the configured window
                dte = metrics['days_to_expiration']
                if not (self.dte_min <= dte <= self.dte_max):
                    continue

                # 2. Strike price below current stock price
                if metrics['strike'] >= stock_price:
                    continue

                # 3. Delta between -0.10 and -0.30
                if not (self.delta_min <= metrics['delta'] <= self.delta_max):
                    continue

                # 4. Open interest greater than 100
                if metrics['open_interest'] < self.min_open_interest:
                    continue

                # 5. Bid-ask spread less than 10% of premium
                if metrics['bid_ask_spread_pct'] >= self.max_bid_ask_spread_pct:
                    continue

                # All filters passed - add to results
                option_result = {
                    'symbol': symbol,
                    'current_price': stock_price,
                    **metrics
                }
                filtered_options.append(option_result)

            except Exception as e:
                logger.warning(f"Error processing option {idx} for {symbol}: {e}")
                continue

        logger.info(f"Found {len(filtered_options)} qualifying options for {symbol}")
        return filtered_options

    def scan_stock(self, symbol: str) -> List[Dict]:
        """Scan a single stock for put options opportunities."""
        logger.info(f"Scanning {symbol}...")

        stock_data = self.get_stock_data(symbol)
        if not stock_data:
            return []

        options_df = self.get_options_chain(symbol)
        if options_df is None or options_df.empty:
            return []

        qualified_options = self.filter_options(options_df, stock_data)

        # Attach earnings warning to each option
        next_earnings = self._get_next_earnings(symbol)
        today = datetime.utcnow()
        for opt in qualified_options:
            if next_earnings is not None:
                days_to_earn = (next_earnings - today).days
                exp_date = datetime.strptime(opt["expiration"], "%Y-%m-%d")
                earnings_in_window = today <= next_earnings <= exp_date
                opt["earnings_in_window"] = earnings_in_window
                opt["days_to_earnings"] = days_to_earn if days_to_earn >= 0 else None
            else:
                opt["earnings_in_window"] = False
                opt["days_to_earnings"] = None

        # Attach pivot points, Bollinger Bands, and Technical Context Score.
        # get_technicals() is cached per symbol — one API call shared across all contracts.
        if qualified_options:
            current_price = stock_data.get("current_price", 0.0)
            tech = get_technicals(symbol, current_price)
            d_piv = tech.get("pivot_1d") or {}
            w_piv = tech.get("pivot_1w") or {}
            m_piv = tech.get("pivot_1m") or {}
            for opt in qualified_options:
                strike = opt.get("strike", 0.0)
                opt["tech_score"]    = tech_score(tech, strike, current_price)
                opt["pivot_1d_pp"]   = d_piv.get("pp")
                opt["pivot_1d_s1"]   = d_piv.get("s1")
                opt["pivot_1d_r1"]   = d_piv.get("r1")
                opt["pivot_1w_pp"]   = w_piv.get("pp")
                opt["pivot_1w_s1"]   = w_piv.get("s1")
                opt["pivot_1w_s2"]   = w_piv.get("s2")
                opt["pivot_1w_r1"]   = w_piv.get("r1")
                opt["pivot_1m_pp"]   = m_piv.get("pp")
                opt["pivot_1m_s1"]   = m_piv.get("s1")
                opt["pivot_1m_s2"]   = m_piv.get("s2")
                opt["bb_upper"]      = tech.get("bb_upper")
                opt["bb_middle"]     = tech.get("bb_middle")
                opt["bb_lower"]      = tech.get("bb_lower")
                opt["bb_width_pct"]  = tech.get("bb_width_pct")
                opt["bb_pct_b"]      = tech.get("bb_pct_b")

        return qualified_options

    def scan_universe(self, symbols: List[str], max_workers: int = 6) -> List[Dict]:
        """Scan a universe of symbols in parallel for opportunities."""
        all_opportunities = []
        total = len(symbols)
        completed = 0

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(self.scan_stock, sym): sym for sym in symbols}
            for future in as_completed(futures):
                symbol = futures[future]
                completed += 1
                try:
                    results = future.result()
                    all_opportunities.extend(results)
                except Exception as e:
                    logger.error(f"Error scanning {symbol}: {e}")
                if completed % 50 == 0 or completed == total:
                    logger.info(f"Progress: {completed}/{total} stocks done, {len(all_opportunities)} opportunities so far")

        logger.info(f"Scan complete. Found {len(all_opportunities)} total opportunities.")
        return all_opportunities

    def rank_opportunities(self, opportunities: List[Dict]) -> List[Dict]:
        """Rank opportunities by: highest Risk-Adjusted Yield, then highest Open Interest, then lowest Delta magnitude."""
        if not opportunities:
            return []

        # Sort by: Risk-Adjusted Yield (desc), Open Interest (desc), |Delta| (asc)
        ranked = sorted(
            opportunities,
            key=lambda x: (
                -x.get('risk_adjusted_yield', 0),  # Descending
                -x.get('open_interest', 0),        # Descending
                abs(x.get('delta', 0))             # Ascending absolute delta
            )
        )

        return ranked

    def flag_exceptional_opportunities(self, opportunities: List[Dict]) -> List[Dict]:
        """Flag opportunities that meet all exceptional criteria."""
        flagged = []

        for opp in opportunities:
            opp["flagged"] = False
            if (opp.get("risk_adjusted_yield", 0) > self.flag_min_risk_adjusted_yield and
                opp.get("distance_otm", 0) > self.flag_min_distance_otm and
                opp.get("delta", -1) > self.flag_delta_max and
                opp.get("open_interest", 0) > self.flag_min_open_interest):
                opp["flagged"] = True
                flagged.append(opp)

        return flagged

    def generate_summary_sections(self, opportunities: List[Dict]) -> Dict:
        """Generate summary sections: Top 10 safest, highest-yield, and balanced opportunities."""
        if not opportunities:
            return {
                'safest': [],
                'highest_yield': [],
                'balanced': []
            }

        # Safest: Highest Open Interest, then lowest |Delta|, then highest Risk-Adjusted Yield
        safest = sorted(
            opportunities,
            key=lambda x: (
                -x.get('open_interest', 0),
                abs(x.get('delta', 0)),
                -x.get('risk_adjusted_yield', 0)
            )
        )[:10]

        # Highest yield: Highest Risk-Adjusted Yield, then highest Open Interest, then lowest |Delta|
        highest_yield = sorted(
            opportunities,
            key=lambda x: (
                -x.get('risk_adjusted_yield', 0),
                -x.get('open_interest', 0),
                abs(x.get('delta', 0))
            )
        )[:10]

        # Balanced: Weighted score combining yield (40%), safety (30% = OI), and probability (30% = 1-|delta|)
        balanced_scored = []
        for opp in opportunities:
            # Normalize metrics to 0-1 scale for weighting
            max_yield = max((o.get('risk_adjusted_yield', 0) for o in opportunities), default=1)
            max_oi = max((o.get('open_interest', 0) for o in opportunities), default=1)
            max_delta_dist = max((abs(o.get('delta', 0)) for o in opportunities), default=1)

            # Avoid division by zero
            norm_yield = opp.get('risk_adjusted_yield', 0) / max_yield if max_yield > 0 else 0
            norm_oi = opp.get('open_interest', 0) / max_oi if max_oi > 0 else 0
            norm_prob = 1 - (abs(opp.get('delta', 0)) / max_delta_dist) if max_delta_dist > 0 else 1  # Lower |delta| = higher probability

            # Weighted score: 40% yield + 30% safety (OI) + 30% probability
            score = (0.4 * norm_yield) + (0.3 * norm_oi) + (0.3 * norm_prob)

            opp_copy = opp.copy()
            opp_copy['balanced_score'] = score
            balanced_scored.append(opp_copy)

        # Sort by balanced score descending
        balanced = sorted(balanced_scored, key=lambda x: x.get('balanced_score', 0), reverse=True)[:10]

        # Remove the temporary balanced_score field for output
        for opp in balanced:
            if 'balanced_score' in opp:
                del opp['balanced_score']

        return {
            'safest': safest,
            'highest_yield': highest_yield,
            'balanced': balanced
        }

    def print_console_table(self, opportunities: List[Dict], title: str = "Options Opportunities"):
        """Print opportunities as a formatted table in console."""
        if not opportunities:
            print(f"\n{title}: No opportunities found")
            return

        print(f"\n{title}")
        print("=" * 120)

        # Define columns to display
        columns = [
            ('Symbol', 8),
            ('Current Price', 12),
            ('Strike', 8),
            ('Expiration', 12),
            ('Premium', 8),
            ('Delta', 8),
            ('OI', 8),
            ('Distance OTM %', 12),
            ('Annualized Yield %', 16),
            ('Risk-Adj Yield %', 16),
            ('Flagged', 8)
        ]

        # Print header
        header = "".join(f"{name:<{width}}" for name, width in columns)
        print(header)
        print("-" * len(header))

        # Print rows
        for opp in opportunities:
            row_data = [
                f"{opp.get('symbol', 'N/A'):<{columns[0][1]}}",
                f"{opp.get('current_price', 0):<{columns[1][1]}.2f}",
                f"{opp.get('strike', 0):<{columns[2][1]}.2f}",
                f"{opp.get('expiration', 'N/A'):<{columns[3][1]}}",
                f"{opp.get('premium', 0):<{columns[4][1]}.2f}",
                f"{opp.get('delta', 0):<{columns[5][1]}.2f}",
                f"{opp.get('open_interest', 0):<{columns[6][1]}}",
                f"{opp.get('distance_otm', 0):<{columns[7][1]}.2f}",
                f"{opp.get('annualized_yield', 0):<{columns[8][1]}.2f}",
                f"{opp.get('risk_adjusted_yield', 0):<{columns[9][1]}.2f}",
                f"{'YES' if opp.get('flagged', False) else 'NO':<{columns[10][1]}}"
            ]
            print("".join(row_data))

    def save_to_csv(self, opportunities: List[Dict], filename: str):
        """Save opportunities to CSV file."""
        if not opportunities:
            logger.warning(f"No opportunities to save to {filename}")
            return

        try:
            # Define CSV columns
            fieldnames = [
                'symbol', 'current_price', 'strike', 'expiration', 'premium',
                'bid', 'ask', 'delta', 'theta_per_contract', 'implied_volatility',
                'open_interest', 'days_to_expiration', 'years_to_expiration',
                'annualized_yield', 'risk_adjusted_yield', 'realistic_yield',
                'distance_otm', 'bid_ask_spread', 'bid_ask_spread_pct',
                'capital_required', 'earnings_in_window', 'days_to_earnings', 'flagged',
                # Technical context fields
                'tech_score',
                'pivot_1d_pp', 'pivot_1d_s1', 'pivot_1d_r1',
                'pivot_1w_pp', 'pivot_1w_s1', 'pivot_1w_s2', 'pivot_1w_r1',
                'pivot_1m_pp', 'pivot_1m_s1', 'pivot_1m_s2',
                'bb_upper', 'bb_middle', 'bb_lower', 'bb_width_pct', 'bb_pct_b',
            ]

            with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()

                for opp in opportunities:
                    # Create row with only the fields we want
                    row = {key: opp.get(key, '') for key in fieldnames}
                    writer.writerow(row)

            logger.info(f"Saved {len(opportunities)} opportunities to {filename}")
        except Exception as e:
            logger.error(f"Error saving to CSV {filename}: {e}")

    def save_to_json(self, opportunities: List[Dict], filename: str):
        """Save opportunities to JSON file."""
        if not opportunities:
            logger.warning(f"No opportunities to save to {filename}")
            return

        try:
            with open(filename, 'w', encoding='utf-8') as jsonfile:
                json.dump(opportunities, jsonfile, indent=2, default=str)

            logger.info(f"Saved {len(opportunities)} opportunities to {filename}")
        except Exception as e:
            logger.error(f"Error saving to JSON {filename}: {e}")

    def run_scan(self, watchlist_file: str = "watchlist.txt", dte_min: int = 1, dte_max: int = 730):
        """Run the complete options scanning process.

        Parameters
        ----------
        dte_min : int
            Minimum days to expiration to include (default 1).
        dte_max : int
            Maximum days to expiration to include (default 730 / ~2 years).
        """
        self.dte_min = dte_min
        self.dte_max = dte_max
        reset_risk_free_rate_cache()
        reset_tech_cache()
        rfr = fetch_risk_free_rate()
        logger.info(f"Starting scan — DTE window {dte_min}–{dte_max} days, risk-free rate {rfr*100:.2f}%")

        # Get all symbols to scan
        sp500_symbols = self.get_sp500_stocks()
        nasdaq100_symbols = self.get_nasdaq100_stocks()
        watchlist_symbols = self.get_watchlist_stocks(watchlist_file)

        # Combine and deduplicate
        all_symbols = list(set(sp500_symbols + nasdaq100_symbols + watchlist_symbols))
        logger.info(f"Total unique symbols to scan: {len(all_symbols)}")
        logger.info(f"  - S&P 500: {len(sp500_symbols)}")
        logger.info(f"  - Nasdaq 100: {len(nasdaq100_symbols)}")
        logger.info(f"  - Watchlist: {len(watchlist_symbols)}")

        # Scan universe
        all_opportunities = self.scan_universe(all_symbols)

        if not all_opportunities:
            logger.warning("No opportunities found meeting the criteria")
            print("\nNo opportunities found meeting the criteria.")
            print("Consider adjusting filter parameters or checking data availability.")
            return

        # Rank opportunities
        ranked_opportunities = self.rank_opportunities(all_opportunities)

        # Flag exceptional opportunities
        flagged_opportunities = self.flag_exceptional_opportunities(ranked_opportunities)

        # Generate summary sections
        summary_sections = self.generate_summary_sections(ranked_opportunities)

        # Print results to console
        self.print_console_table(ranked_opportunities[:20], "Top 20 Opportunities (Ranked)")

        if flagged_opportunities:
            self.print_console_table(flagged_opportunities, "Flagged Exceptional Opportunities")

        # Print summary sections
        print("\n" + "="*60)
        print("SUMMARY SECTIONS")
        print("="*60)

        self.print_console_table(summary_sections['safest'], "Top 10 Safest Opportunities")
        self.print_console_table(summary_sections['highest_yield'], "Top 10 Highest-Yield Opportunities")
        self.print_console_table(summary_sections['balanced'], "Top 10 Balanced Opportunities")

        # Save to files
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        out = _OUTPUT_DIR

        # Save scan metadata (DTE window used, counts)
        meta = {
            "timestamp": timestamp,
            "dte_min": self.dte_min,
            "dte_max": self.dte_max,
            "total_opportunities": len(ranked_opportunities),
            "flagged_count": len(flagged_opportunities),
        }
        with open(out / f"options_opportunities_meta_{timestamp}.json", "w") as f:
            json.dump(meta, f, indent=2)

        # Save all opportunities
        self.save_to_csv(ranked_opportunities, str(out / f"options_opportunities_all_{timestamp}.csv"))
        self.save_to_json(ranked_opportunities, str(out / f"options_opportunities_all_{timestamp}.json"))

        # Save flagged opportunities
        if flagged_opportunities:
            self.save_to_csv(flagged_opportunities, str(out / f"options_opportunities_flagged_{timestamp}.csv"))
            self.save_to_json(flagged_opportunities, str(out / f"options_opportunities_flagged_{timestamp}.json"))

        # Save summary sections
        for section_name, opportunities in summary_sections.items():
            if opportunities:
                self.save_to_csv(opportunities, str(out / f"options_opportunities_{section_name}_{timestamp}.csv"))
                self.save_to_json(opportunities, str(out / f"options_opportunities_{section_name}_{timestamp}.json"))

        logger.info(f"Scan completed. Results saved with timestamp {timestamp}")
        print(f"\nScan completed. Results saved to files with timestamp {timestamp}")

def main():
    """Main execution function."""
    print("="*60)
    print("Automated Options Opportunity Scanner")
    print("Cash-Secured Put Selling - Research Tool Only")
    print("="*60)
    print("This tool scans for put options opportunities but does NOT place trades.")
    print("For educational and research purposes only.")
    print("="*60)

    # Check for required environment variables (for future Alpaca integration)
    alpaca_key = os.getenv('APCA_API_KEY_ID')
    alpaca_secret = os.getenv('APCA_API_SECRET_KEY')

    if alpaca_key and alpaca_secret:
        print("✓ Alpaca API credentials detected (available for future trade execution)")
    else:
        print("⚠ Alpaca API credentials not set (optional for this research tool)")
        print("  Set APCA_API_KEY_ID and APCA_API_SECRET_KEY for future Alpaca integration")

    print()

    # Initialize and run scanner
    scanner = OptionsScanner()

    try:
        scanner.run_scan()
    except KeyboardInterrupt:
        print("\n\nScan interrupted by user.")
        logger.info("Scan interrupted by user")
    except Exception as e:
        logger.error(f"Unexpected error during scan: {e}", exc_info=True)
        print(f"\nAn error occurred: {e}")
        print("Check options_scanner.log for details.")

if __name__ == "__main__":
    main()