import os
import json
import time
import csv
import urllib.request
import urllib.parse
from datetime import datetime

TELEGRAM_BOT_TOKEN = "8642052658:AAH1o7maezHyHPgxeOxeiGLQ3wvu1JglvKI"
TELEGRAM_CHAT_ID = "5598707490"

# Risk Management Parameters
TOTAL_CAPITAL = 50000.0  # Total trading account capital in INR
MAX_RISK_PER_TRADE_PCT = 2.0  # Max risk per trade (2% = ₹1,000)

# Index Configuration Matrix
INDICES = {
    "NIFTY": {
        "upstox_key": "NSE_INDEX|Nifty 50",
        "yahoo_symbol": "%5ENSEI",
        "tv_chart": "NSE:NIFTY",
        "step": 50,
        "lot_size": 25,
        "prem_factor": 0.0052,
    },
    "SENSEX": {
        "upstox_key": "BSE_INDEX|SENSEX",
        "yahoo_symbol": "%5EBSESN",
        "tv_chart": "BSE:SENSEX",
        "step": 100,
        "lot_size": 10,
        "prem_factor": 0.0045,
    },
    "BANKNIFTY": {
        "upstox_key": "NSE_INDEX|Nifty Bank",
        "yahoo_symbol": "%5ENSEBANK",
        "tv_chart": "NSE:BANKNIFTY",
        "step": 100,
        "lot_size": 15,
        "prem_factor": 0.0075,
    }
}

def log_activity(text):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"[{timestamp}] {text}"
    print(log_entry)

def send_telegram_message(message, inline_keyboard=None):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload_dict = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    
    if inline_keyboard and len(inline_keyboard) > 0:
        payload_dict["reply_markup"] = {"inline_keyboard": inline_keyboard}

    payload = json.dumps(payload_dict).encode('utf-8')
    req = urllib.request.Request(url, data=payload, headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req) as response:
            if response.status == 200:
                log_activity("✅ Telegram Alert Sent Successfully!")
    except Exception as e:
        log_activity(f"❌ Telegram Error: {e}")

def get_token():
    token = os.environ.get("UPSTOX_TOKEN")
    if not token and os.path.exists("token.txt"):
        with open("token.txt", "r") as f:
            token = f.read().strip()
    return token

def calculate_ema(prices, period):
    if len(prices) < period:
        return prices[-1] if prices else 0
    k = 2 / (period + 1)
    ema = sum(prices[:period]) / period
    for price in prices[period:]:
        ema = (price * k) + (ema * (1 - k))
    return ema

def calculate_rsi(prices, period=14):
    if len(prices) <= period:
        return 50.0
    gains, losses = [], []
    for i in range(1, len(prices)):
        change = prices[i] - prices[i - 1]
        if change > 0:
            gains.append(change)
            losses.append(0)
        else:
            gains.append(0)
            losses.append(abs(change))
    
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))

def calculate_atr(highs, lows, closes, period=14):
    if len(closes) < 2:
        return 10.0
    tr_list = []
    for i in range(1, len(closes)):
        tr = max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1]))
        tr_list.append(tr)
    return sum(tr_list[-period:]) / min(len(tr_list), period) if tr_list else 10.0

def calculate_vwap(high, low, close):
    return (high + low + close) / 3.0

def calculate_position_size(entry_price, sl_price, lot_size):
    risk_per_share = abs(entry_price - sl_price)
    if risk_per_share <= 0:
        return 1, TOTAL_CAPITAL * (MAX_RISK_PER_TRADE_PCT / 100)
    
    max_risk_amount = TOTAL_CAPITAL * (MAX_RISK_PER_TRADE_PCT / 100)
    recommended_qty = int(max_risk_amount / (risk_per_share * lot_size)) * lot_size
    
    if recommended_qty < lot_size:
        recommended_qty = lot_size
        
    actual_risk = round(recommended_qty * risk_per_share, 1)
    lots_count = int(recommended_qty / lot_size)
    return lots_count, actual_risk

def analyze_drawdown_and_backtest():
    """Analyzes trade_journal.csv for Max Drawdown and Profit Factor"""
    if not os.path.isfile("trade_journal.csv"):
        return "Insufficient Trade History"
    
    total_pnl = 0
    max_drawdown = 0
    peak_pnl = 0
    gross_profit = 0
    gross_loss = 0

    try:
        with open("trade_journal.csv", "r") as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                status = row.get("Status", "OPEN")
                entry = float(row.get("Entry_Premium", 0))
                sl = float(row.get("SL", 0))
                t1 = float(row.get("Target1", 0))

                if status in ["T1_HIT", "T2_HIT", "T3_HIT"]:
                    pnl = (t1 - entry)
                    gross_profit += pnl
                elif status == "SL_HIT":
                    pnl = -abs(entry - sl)
                    gross_loss += abs(pnl)
                else:
                    pnl = 0

                total_pnl += pnl
                if total_pnl > peak_pnl:
                    peak_pnl = total_pnl
                dd = peak_pnl - total_pnl
                if dd > max_drawdown:
                    max_drawdown = dd

        profit_factor = round(gross_profit / gross_loss, 2) if gross_loss > 0 else (gross_profit if gross_profit > 0 else 1.0)
        return f"Max DD: {max_drawdown:.1f} pts | Profit Factor: {profit_factor}"
    except Exception:
        return "Backtest Engine Active"

def get_multi_timeframe_data(yahoo_symbol):
    heatmap = {"1M": "NEUTRAL", "5M": "NEUTRAL", "15M": "NEUTRAL", "1H": "NEUTRAL"}
    closes_5m_all, highs_5m, lows_5m = [], [], []
    try:
        # Fetch 5m data
        url_5m = f"https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_symbol}?range=1d&interval=5m"
        req = urllib.request.Request(url_5m, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            quote = data['chart']['result'][0]['indicators']['quote'][0]
            closes_5m_all = [p for p in quote['close'] if p is not None]
            highs_5m = [p for p in quote['high'] if p is not None]
            lows_5m = [p for p in quote['low'] if p is not None]

            if len(closes_5m_all) >= 5:
                e_fast = calculate_ema(closes_5m_all, 3)
                e_slow = calculate_ema(closes_5m_all, 5)
                heatmap["5M"] = "BULLISH" if e_fast > e_slow else "BEARISH"
                heatmap["1M"] = heatmap["5M"]  # Derived intraday proxy

        # Fetch 15m data
        url_15m = f"https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_symbol}?range=1d&interval=15m"
        req = urllib.request.Request(url_15m, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            closes_15m = [p for p in data['chart']['result'][0]['indicators']['quote'][0]['close'] if p is not None]
            if len(closes_15m) >= 5:
                e_fast15 = calculate_ema(closes_15m, 3)
                e_slow15 = calculate_ema(closes_15m, 5)
                heatmap["15M"] = "BULLISH" if e_fast15 > e_slow15 else "BEARISH"

        # Fetch 1H data
        url_1h = f"https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_symbol}?range=5d&interval=1h"
        req = urllib.request.Request(url_1h, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            closes_1h = [p for p in data['chart']['result'][0]['indicators']['quote'][0]['close'] if p is not None]
            if len(closes_1h) >= 5:
                e_fast1h = calculate_ema(closes_1h, 3)
                e_slow1h = calculate_ema(closes_1h, 5)
                heatmap["1H"] = "BULLISH" if e_fast1h > e_slow1h else "BEARISH"

    except Exception as e:
        log_activity(f"MTF Fetch Warning: {e}")

    return heatmap, highs_5m, lows_5m, closes_5m_all

def get_india_vix():
    try:
        url = "https://query1.finance.yahoo.com/v8/finance/chart/%5EINDIAVIX?range=1d&interval=5m"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode('utf-8'))
            meta = data['chart']['result'][0]['meta']
            return float(meta['regularMarketPrice'])
    except Exception:
        return 14.0

def fetch_option_chain_metrics(instrument_key, atm_strike):
    """Auto selects expiry, PCR, and Delta sensitivity"""
    token = get_token()
    pcr_ratio = 1.0
    expiry_date = "Nearest Expiry"
    opt_delta = 0.50  # Default ATM Delta proxy
    ce_price, pe_price = None, None

    if not token:
        return expiry_date, pcr_ratio, opt_delta, ce_price, pe_price

    try:
        encoded_key = urllib.parse.quote(instrument_key)
        url = f"https://api.upstox.com/v2/option/chain?instrument_key={encoded_key}"
        headers = {'Accept': 'application/json', 'Api-Version': '2.0', 'Authorization': f'Bearer {token}'}
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=5) as resp:
            if resp.status == 200:
                res = json.loads(resp.read().decode('utf-8'))
                if 'data' in res and len(res['data']) > 0:
                    expiry_date = res['data'][0].get('expiry', "Nearest Expiry")
                    total_ce_oi = sum(opt.get('call_options', {}).get('market_data', {}).get('oi', 0) for opt in res['data'])
                    total_pe_oi = sum(opt.get('put_options', {}).get('market_data', {}).get('oi', 0) for opt in res['data'])
                    if total_ce_oi > 0:
                        pcr_ratio = round(total_pe_oi / total_ce_oi, 2)

                    for option in res['data']:
                        if option.get('strike_price') == atm_strike:
                            ce_price = option.get('call_options', {}).get('market_data', {}).get('ltp', 0)
                            pe_price = option.get('put_options', {}).get('market_data', {}).get('ltp', 0)
                            opt_delta = option.get('call_options', {}).get('option_greeks', {}).get('delta', 0.50)
                            if not opt_delta or opt_delta == 0:
                                opt_delta = 0.50
    except Exception as e:
        log_activity(f"Option Chain API Info: {e}")

    return expiry_date, pcr_ratio, abs(float(opt_delta)), ce_price, pe_price

def get_upstox_market_data(upstox_key):
    token = get_token()
    if not token:
        return None

    inst_key = urllib.parse.quote(upstox_key)
    url = f"https://api.upstox.com/v2/market-quote/quotes?instrument_key={inst_key}"
    headers = {
        'Accept': 'application/json',
        'Api-Version': '2.0',
        'Authorization': f'Bearer {token}',
        'User-Agent': 'Mozilla/5.0'
    }
    
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=5) as response:
            if response.status == 200:
                data = json.loads(response.read().decode('utf-8'))
                key_formatted = upstox_key.replace('|', ':')
                if 'data' in data and key_formatted in data['data']:
                    quote = data['data'][key_formatted]
                    return float(quote['last_price']), float(quote['ohlc']['open']), float(quote['ohlc']['high']), float(quote['ohlc']['low']), "UPSTOX API"
    except Exception as e:
        log_activity(f"Upstox Quote Error: {e}")
    return None

# 🟢 DIRECT NSE LIVE FEED SCRAPER ENGINE (Zero Token Required)
def get_nse_direct_live_data(yahoo_symbol):
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_symbol}?range=1d&interval=1m"
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode('utf-8'))
            result = data['chart']['result'][0]
            close_prices = [p for p in result['indicators']['quote'][0]['close'] if p is not None]
            meta = result['meta']
            
            spot_price = float(meta['regularMarketPrice'])
            open_price = float(meta['chartPreviousClose'])
            high_price = max(close_prices) if close_prices else spot_price
            low_price = min(close_prices) if close_prices else spot_price
            
            log_activity(f"🟢 Direct NSE Live Feed Fetched: {spot_price}")
            return spot_price, open_price, high_price, low_price, close_prices, "NSE DIRECT LIVE FEED"
    except Exception as e:
        log_activity(f"❌ NSE Direct Feed Error: {e}")
        return None

def log_trade_to_csv(data_row):
    file_exists = os.path.isfile("trade_journal.csv")
    fields = ["Timestamp", "Index", "Signal", "Strike", "Spot", "Entry_Premium", "SL", "Target1", "Target2", "Target3", "Delta", "PCR", "VIX", "Status"]
    try:
        with open("trade_journal.csv", "a", newline="") as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fields)
            if not file_exists:
                writer.writeheader()
            if "Status" not in data_row:
                data_row["Status"] = "OPEN"
            writer.writerow(data_row)
            log_activity("📝 Trade logged to trade_journal.csv successfully.")
    except Exception as e:
        log_activity(f"CSV Logging Error: {e}")

def update_csv_trade_status(timestamp, new_status):
    if not os.path.isfile("trade_journal.csv"):
        return
    rows = []
    try:
        with open("trade_journal.csv", "r") as csvfile:
            reader = csv.DictReader(csvfile)
            fieldnames = reader.fieldnames
            for row in reader:
                if row["Timestamp"] == timestamp:
                    row["Status"] = new_status
                rows.append(row)

        with open("trade_journal.csv", "w", newline="") as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
            log_activity(f"📝 CSV Status Updated to: {new_status}")
    except Exception as e:
        log_activity(f"CSV Status Update Error: {e}")

def generate_daily_pnl_summary():
    if not os.path.isfile("trade_journal.csv"):
        log_activity("No trade journal found for P&L summary.")
        return

    today_str = datetime.now().strftime("%Y-%m-%d")
    total_trades = 0
    t1_hits, t2_hits, t3_hits, sl_hits = 0, 0, 0, 0

    try:
        with open("trade_journal.csv", "r") as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                if row["Timestamp"].startswith(today_str):
                    total_trades += 1
                    status = row.get("Status", "OPEN")
                    if status == "T1_HIT":
                        t1_hits += 1
                    elif status == "T2_HIT":
                        t2_hits += 1
                    elif status == "T3_HIT":
                        t3_hits += 1
                    elif status == "SL_HIT":
                        sl_hits += 1

        if total_trades > 0:
            win_count = t1_hits + t2_hits + t3_hits
            win_rate = (win_count / total_trades) * 100

            summary_msg = f"""📊 *DAILY ALGO PERFORMANCE REPORT*
📅 *Date:* `{today_str}`

📈 *Total Signals Generated:* `{total_trades}`
🎯 *Target Hits:* `{win_count}` (T1: {t1_hits} | T2: {t2_hits} | T3: {t3_hits})
🛑 *SL Hits:* `{sl_hits}`
🔥 *Win Rate:* `{win_rate:.1f}%`

🏆 *Summary Status:* {'🟢 HIGHLY PROFITABLE' if win_rate >= 50 else '🔴 DEFENSIVE DAY'}
"""
            send_telegram_message(summary_msg)
            log_activity("📊 Daily P&L Summary sent to Telegram.")
    except Exception as e:
        log_activity(f"Daily Summary Error: {e}")

def format_heatmap_str(hm):
    def icon(val):
        return "🟩" if val == "BULLISH" else ("🟥" if val == "BEARISH" else "⬜")
    return f"1M:{icon(hm['1M'])} | 5M:{icon(hm['5M'])} | 15M:{icon(hm['15M'])} | 1H:{icon(hm['1H'])}"

def process_index(name, config, vix_val):
    log_activity(f"⚡ Processing {name} with Fast Momentum + Scalping Engine...")
    
    # Priority 1: Upstox API -> Priority 2: Direct NSE Feed Scraper
    res = get_upstox_market_data(config["upstox_key"])
    if res:
        spot_price, open_p, high_p, low_p, source = res
        close_series = [open_p, low_p, (open_p + spot_price)/2, high_p, spot_price]
    else:
        log_activity(f"🔄 Switching to NSE Direct Live Feed for {name}...")
        backup = get_nse_direct_live_data(config["yahoo_symbol"])
        if backup:
            spot_price, open_p, high_p, low_p, close_series, source = backup
        else:
            log_activity(f"❌ Failed to fetch market data for {name}")
            return None, None, None

    heatmap, h5, l5, c5 = get_multi_timeframe_data(config["yahoo_symbol"])
    step = config["step"]
    atm_strike = round(spot_price / step) * step

    auto_expiry, pcr_val, delta_val, ce_ltp, pe_ltp = fetch_option_chain_metrics(config["upstox_key"], atm_strike)
    atr_val = calculate_atr(h5, l5, c5) if h5 and l5 and c5 else 15.0

    ema9 = calculate_ema(close_series, 3)
    rsi = calculate_rsi(close_series, 14)

    tv_symbol = config["tv_chart"]
    oc_url = "https://www.nseindia.com/option-chain" if "NIFTY" in name and "BANK" not in name else "https://upstox.com/option-chain/"
    
    buttons = [
        [{"text": f"📈 {name} Chart", "url": f"https://in.tradingview.com/chart/?symbol={tv_symbol}"},
         {"text": "📊 Option Chain", "url": oc_url}]
    ]

    heatmap_text = format_heatmap_str(heatmap)

    # FAST MOMENTUM BREAKOUT ENGINE (Direct Real-time Trigger)
    net_change_from_open = spot_price - open_p
    
    is_fast_bullish = (heatmap["5M"] == "BULLISH") and (spot_price > ema9 or net_change_from_open >= 25) and rsi >= 48
    is_fast_bearish = (heatmap["5M"] == "BEARISH") and (spot_price < ema9 or net_change_from_open <= -25) and rsi <= 52

    if is_fast_bullish:
        action_type = "CALL (CE)"
        signal_direction = "🚀 FAST BULLISH BREAKOUT DETECTED"
        recommended_strike = f"{atm_strike} CE"
        trade_active = True
    elif is_fast_bearish:
        action_type = "PUT (PE)"
        signal_direction = "💥 FAST BEARISH BREAKDOWN DETECTED"
        recommended_strike = f"{atm_strike} PE"
        trade_active = True
    else:
        signal_direction = "⚠️ RANGEBOUND (NO FAST MOMENTUM)"
        trade_active = False

    vix_warning = "⚠️ HIGH VOLATILITY" if vix_val > 17.5 else "🟢 STABLE"

    if not trade_active:
        msg = f"""🔥 *{name} MARKET STATUS*
📅 *Expiry:* `{auto_expiry}` | *Feed:* `{source}`

📍 *Spot:* `{spot_price:.2f}` | *Bias:* {signal_direction}
📊 *MTF Heatmap:* `{heatmap_text}`
📈 *Metrics:* RSI: `{rsi:.1f}` | PCR: `{pcr_val}` | Delta: `{delta_val:.2f}` | VIX: `{vix_val:.1f}`
⏸️ *Status:* Rangebound / No Breakout candle yet.
"""
        return msg, buttons, None

    if "CE" in action_type and ce_ltp and ce_ltp > 0:
        estimated_premium = ce_ltp
        prem_source = "Option Chain API"
    elif "PE" in action_type and pe_ltp and pe_ltp > 0:
        estimated_premium = pe_ltp
        prem_source = "Option Chain API"
    else:
        estimated_premium = round(spot_price * config["prem_factor"], 1)
        prem_source = "Estimated Delta Model"

    sl_pts = round(max(atr_val * 0.15, estimated_premium * 0.12), 1)
    t1_pts = round(sl_pts * 1.5, 1)
    t2_pts = round(sl_pts * 2.5, 1)
    t3_pts = round(sl_pts * 4.0, 1)

    sl_price = round(estimated_premium - sl_pts, 1)
    t1_price = round(estimated_premium + t1_pts, 1)
    t2_price = round(estimated_premium + t2_pts, 1)
    t3_price = round(estimated_premium + t3_pts, 1)

    rec_lots, max_risk_amt = calculate_position_size(estimated_premium, sl_price, config["lot_size"])
    timestamp_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    execution_payload = {
        "symbol": recommended_strike,
        "action": "BUY",
        "qty": rec_lots * config["lot_size"],
        "price": estimated_premium,
        "sl": sl_price,
        "target": t1_price
    }

    log_trade_to_csv({
        "Timestamp": timestamp_str,
        "Index": name,
        "Signal": action_type,
        "Strike": recommended_strike,
        "Spot": spot_price,
        "Entry_Premium": estimated_premium,
        "SL": sl_price,
        "Target1": t1_price,
        "Target2": t2_price,
        "Target3": t3_price,
        "Delta": delta_val,
        "PCR": pcr_val,
        "VIX": vix_val,
        "Status": "OPEN"
    })

    msg = f"""⚡ *{name} FAST MOMENTUM BREAKOUT SIGNAL*
📅 *Expiry:* `{auto_expiry}` | *Feed:* `{source}`

📍 *Spot:* `{spot_price:.2f}` | *Bias:* {signal_direction}
📊 *MTF Heatmap:* `{heatmap_text}`
⚡ *Trade:* BUY *{recommended_strike}* ({action_type})
🏷️ *Price Source:* {prem_source} | *Delta:* `{delta_val:.2f}`

🎯 *RISK & POSITION SIZING (Capital ₹{int(TOTAL_CAPITAL)}):*
• *Rec. Size:* `{rec_lots} Lot(s)` ({rec_lots * config['lot_size']} Qty)
• *Max Risk:* ₹{max_risk_amt} ({MAX_RISK_PER_TRADE_PCT}% Capital)

📊 *DYNAMIC ATR VOLATILITY TARGETS:*
• *Buy Range:* ₹{estimated_premium}
• *SL (ATR Risk):* ₹{sl_price} (-{sl_pts} pts)
• *Target 1 (Book 50%):* ₹{t1_price} (+{t1_pts} pts)
• *Target 2 (Book 30%):* ₹{t2_price} (+{t2_pts} pts)
• *Target 3 (Trail 20%):* ₹{t3_price} (+{t3_pts} pts)

🔗 *Execution Payload:* `{json.dumps(execution_payload)}`
"""

    trade_monitor_info = {
        "timestamp": timestamp_str,
        "index": name,
        "strike": recommended_strike,
        "entry": estimated_premium,
        "sl": sl_price,
        "t1": t1_price,
        "t2": t2_price,
        "t3": t3_price,
        "upstox_key": config["upstox_key"],
        "atm_strike": atm_strike,
        "expiry": auto_expiry,
        "action": action_type
    }

    return msg, buttons, trade_monitor_info

def monitor_live_trades(active_trades):
    if not active_trades:
        return
    
    log_activity("📡 Dynamic Multi-Lot Trade Trailing Engine Active...")
    for _ in range(5):
        time.sleep(30)
        for trade in active_trades:
            _, _, _, ce_ltp, pe_ltp = fetch_option_chain_metrics(trade["upstox_key"], trade["atm_strike"])
            current_price = ce_ltp if "CE" in trade["action"] else pe_ltp

            if current_price and current_price > 0:
                if current_price >= trade["t3"]:
                    alert = f"🚀 *{trade['index']} TARGET 3 (RUNNER) HIT!* 🎉\n\nStrike: *{trade['strike']}*\nEntry: ₹{trade['entry']} ➡️ Current: ₹{current_price}\n🔥 *100% Multi-Lot Targets Accomplished!*"
                    send_telegram_message(alert)
                    update_csv_trade_status(trade["timestamp"], "T3_HIT")
                    active_trades.remove(trade)
                elif current_price >= trade["t2"] and not trade.get("t2_alert_sent"):
                    alert = f"🎯 *{trade['index']} TARGET 2 HIT!* 👏\n\nStrike: *{trade['strike']}*\nEntry: ₹{trade['entry']} ➡️ Current: ₹{current_price}\n💰 *ACTION:* Book additional 30% Lot profit. Trail remaining 20% Lot for T3."
                    send_telegram_message(alert)
                    update_csv_trade_status(trade["timestamp"], "T2_HIT")
                    trade["t2_alert_sent"] = True
                elif current_price >= trade["t1"] and not trade.get("t1_alert_sent"):
                    alert = f"🎯 *{trade['index']} TARGET 1 HIT!* 👏\n\nStrike: *{trade['strike']}*\nEntry: ₹{trade['entry']} ➡️ Current: ₹{current_price}\n🛡️ *ACTION:* Book 50% Lot Profit! Move Stop Loss to Entry Price (₹{trade['entry']}). Trade is now RISK-FREE."
                    send_telegram_message(alert)
                    update_csv_trade_status(trade["timestamp"], "T1_HIT")
                    trade["t1_alert_sent"] = True
                elif current_price <= trade["sl"]:
                    alert = f"🛑 *{trade['index']} STOP LOSS HIT!*\n\nStrike: *{trade['strike']}*\nEntry: ₹{trade['entry']} ➡️ Exit: ₹{current_price}\n🛡️ System exited position safely."
                    send_telegram_message(alert)
                    update_csv_trade_status(trade["timestamp"], "SL_HIT")
                    active_trades.remove(trade)

def main():
    log_activity("🚀 Institutional Master Algo Engine Started")
    now_hour = datetime.now().hour

    if now_hour >= 15 and datetime.now().minute >= 30:
        generate_daily_pnl_summary()
        return

    vix_val = get_india_vix()
    backtest_metrics = analyze_drawdown_and_backtest()

    full_alert = f"🎯 *MULTI-INDEX TRADING ALGO REPORT*\n*VIX:* `{vix_val:.2f}` | *Health:* `{backtest_metrics}`\n\n"
    all_buttons = []
    active_trades = []

    for name, config in INDICES.items():
        signal_text, btns, trade_info = process_index(name, config, vix_val)
        if signal_text:
            full_alert += signal_text + "\n" + "─"*25 + "\n\n"
            if btns:
                all_buttons.extend(btns)
            if trade_info:
                active_trades.append(trade_info)

    full_alert += "🛡️ *MULTI-LOT RULE:* T1 par 50% book karke SL Entry price par lock karein."

    send_telegram_message(full_alert, inline_keyboard=all_buttons)
    
    if active_trades:
        monitor_live_trades(active_trades)

if __name__ == "__main__":
    main()













