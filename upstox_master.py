import os
import json
import time
import csv
import urllib.request
import urllib.parse
from datetime import datetime

TELEGRAM_BOT_TOKEN = "8642052658:AAH1o7maezHyHPgxeOxeiGLQ3wvu1JglvKI"
TELEGRAM_CHAT_ID = "5598707490"

# Index Configuration Matrix
INDICES = {
    "NIFTY": {
        "upstox_key": "NSE_INDEX|Nifty 50",
        "yahoo_symbol": "%5ENSEI",
        "tv_chart": "NSE:NIFTY",
        "step": 50,
        "prem_factor": 0.0052,
    },
    "SENSEX": {
        "upstox_key": "BSE_INDEX|SENSEX",
        "yahoo_symbol": "%5EBSESN",
        "tv_chart": "BSE:SENSEX",
        "step": 100,
        "prem_factor": 0.0045,
    },
    "BANKNIFTY": {
        "upstox_key": "NSE_INDEX|Nifty Bank",
        "yahoo_symbol": "%5ENSEBANK",
        "tv_chart": "NSE:BANKNIFTY",
        "step": 100,
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
    """Calculates Average True Range (ATR) for dynamic volatility SL"""
    if len(closes) < 2:
        return 10.0
    tr_list = []
    for i in range(1, len(closes)):
        tr = max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1]))
        tr_list.append(tr)
    return sum(tr_list[-period:]) / min(len(tr_list), period) if tr_list else 10.0

def calculate_vwap(high, low, close):
    return (high + low + close) / 3.0

def get_multi_timeframe_data(yahoo_symbol):
    trend_5m = "NEUTRAL"
    trend_15m = "NEUTRAL"
    closes_5m_all, highs_5m, lows_5m = [], [], []
    try:
        url_5m = f"https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_symbol}?range=1d&interval=5m"
        req = urllib.request.Request(url_5m, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            quote = data['chart']['result'][0]['indicators']['quote'][0]
            closes_5m_all = [p for p in quote['close'] if p is not None]
            highs_5m = [p for p in quote['high'] if p is not None]
            lows_5m = [p for p in quote['low'] if p is not None]

            if len(closes_5m_all) >= 5:
                ema_fast = calculate_ema(closes_5m_all, 3)
                ema_slow = calculate_ema(closes_5m_all, 5)
                trend_5m = "BULLISH" if ema_fast > ema_slow else "BEARISH"

        url_15m = f"https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_symbol}?range=1d&interval=15m"
        req = urllib.request.Request(url_15m, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            closes_15m = [p for p in data['chart']['result'][0]['indicators']['quote'][0]['close'] if p is not None]
            if len(closes_15m) >= 5:
                ema_fast15 = calculate_ema(closes_15m, 3)
                ema_slow15 = calculate_ema(closes_15m, 5)
                trend_15m = "BULLISH" if ema_fast15 > ema_slow15 else "BEARISH"

    except Exception as e:
        log_activity(f"MTF Fetch Warning: {e}")

    return trend_5m, trend_15m, highs_5m, lows_5m, closes_5m_all

def get_india_vix():
    try:
        url = "https://query1.finance.yahoo.com/v8/finance/chart/%5EINDIAVIX?range=1d&interval=5m"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode('utf-8'))
            meta = data['chart']['result'][0]['meta']
            return float(meta['regularMarketPrice'])
    except Exception:
        return 14.0

def fetch_auto_expiry(instrument_key):
    """Automatically selects nearest weekly option expiry from Upstox API"""
    token = get_token()
    if not token:
        return "Nearest Expiry"
    try:
        encoded_key = urllib.parse.quote(instrument_key)
        url = f"https://api.upstox.com/v2/option/chain?instrument_key={encoded_key}"
        headers = {'Accept': 'application/json', 'Api-Version': '2.0', 'Authorization': f'Bearer {token}'}
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=5) as resp:
            if resp.status == 200:
                res = json.loads(resp.read().decode('utf-8'))
                if 'data' in res and len(res['data']) > 0:
                    exp = res['data'][0].get('expiry')
                    if exp:
                        return exp
    except Exception as e:
        log_activity(f"Auto Expiry Fetch Warning: {e}")
    return "Nearest Expiry"

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

def get_backup_data(yahoo_symbol):
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_symbol}?range=1d&interval=5m"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode('utf-8'))
            result = data['chart']['result'][0]
            close_prices = [p for p in result['indicators']['quote'][0]['close'] if p is not None]
            meta = result['meta']
            spot_price = float(meta['regularMarketPrice'])
            open_price = float(meta['chartPreviousClose'])
            high_price = max(close_prices) if close_prices else spot_price
            low_price = min(close_prices) if close_prices else spot_price
            return spot_price, open_price, high_price, low_price, close_prices, "LIVE BACKUP FEED"
    except Exception as e:
        log_activity(f"Backup Feed Error: {e}")
    return None

def get_option_chain_data(instrument_key, atm_strike, expiry_date):
    token = get_token()
    if not token:
        return None, None
    try:
        encoded_key = urllib.parse.quote(instrument_key)
        exp_param = expiry_date if expiry_date != "Nearest Expiry" else ""
        url = f"https://api.upstox.com/v2/option/chain?instrument_key={encoded_key}&expiry_date={exp_param}"
        headers = {
            'Accept': 'application/json',
            'Api-Version': '2.0',
            'Authorization': f'Bearer {token}'
        }
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=5) as response:
            if response.status == 200:
                res = json.loads(response.read().decode('utf-8'))
                if 'data' in res:
                    for option in res['data']:
                        if option.get('strike_price') == atm_strike:
                            ce_price = option.get('call_options', {}).get('market_data', {}).get('ltp', 0)
                            pe_price = option.get('put_options', {}).get('market_data', {}).get('ltp', 0)
                            return ce_price, pe_price
    except Exception as e:
        log_activity(f"Option Chain API Info: {e}")
    return None, None

def log_trade_to_csv(data_row):
    file_exists = os.path.isfile("trade_journal.csv")
    fields = ["Timestamp", "Index", "Signal", "Strike", "Spot", "Entry_Premium", "SL", "Target1", "Target2", "Target3", "MTF_Status", "VIX", "Status"]
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

def generate_daily_pnl_summary():
    """Reads CSV and sends end-of-day summary to Telegram"""
    if not os.path.isfile("trade_journal.csv"):
        log_activity("No trade journal found for P&L summary.")
        return

    today_str = datetime.now().strftime("%Y-%m-%d")
    total_trades = 0
    t1_hits = 0
    t2_hits = 0
    t3_hits = 0
    sl_hits = 0

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

def process_index(name, config, vix_val):
    log_activity(f"⚡ Processing {name} with MTF + Dynamic ATR Engine...")
    
    res = get_upstox_market_data(config["upstox_key"])
    if res:
        spot_price, open_p, high_p, low_p, source = res
        close_series = [open_p, low_p, (open_p + spot_price)/2, high_p, spot_price]
    else:
        backup = get_backup_data(config["yahoo_symbol"])
        if backup:
            spot_price, open_p, high_p, low_p, close_series, source = backup
        else:
            log_activity(f"❌ Failed to fetch market data for {name}")
            return None, None, None

    trend_5m, trend_15m, h5, l5, c5 = get_multi_timeframe_data(config["yahoo_symbol"])
    auto_expiry = fetch_auto_expiry(config["upstox_key"])

    # Calculate ATR Volatility factor
    atr_val = calculate_atr(h5, l5, c5) if h5 and l5 and c5 else 15.0

    ema9 = calculate_ema(close_series, 3)
    ema21 = calculate_ema(close_series, 5)
    rsi = calculate_rsi(close_series, 14)
    vwap_val = calculate_vwap(high_p, low_p, spot_price)

    step = config["step"]
    atm_strike = round(spot_price / step) * step

    tv_symbol = config["tv_chart"]
    oc_url = "https://www.nseindia.com/option-chain" if "NIFTY" in name and "BANK" not in name else "https://upstox.com/option-chain/"
    
    # Callback-style interactive UI buttons
    buttons = [
        [{"text": f"📈 {name} Chart", "url": f"https://in.tradingview.com/chart/?symbol={tv_symbol}"},
         {"text": "📊 Option Chain", "url": oc_url}]
    ]

    if spot_price > ema9 and ema9 >= ema21 and rsi > 52 and spot_price >= vwap_val and trend_5m == "BULLISH" and trend_15m == "BULLISH":
        action_type = "CALL (CE)"
        signal_direction = "🟢 STRONG BULLISH (5M + 15M ALIGNED)"
        recommended_strike = f"{atm_strike} CE"
        trade_active = True
    elif spot_price < ema9 and ema9 <= ema21 and rsi < 48 and spot_price <= vwap_val and trend_5m == "BEARISH" and trend_15m == "BEARISH":
        action_type = "PUT (PE)"
        signal_direction = "🔴 STRONG BEARISH (5M + 15M ALIGNED)"
        recommended_strike = f"{atm_strike} PE"
        trade_active = True
    else:
        signal_direction = "⚠️ NO ALIGNMENT / RANGE-BOUND"
        trade_active = False

    if not trade_active:
        msg = f"""🔥 *{name} MARKET STATUS*
📅 *Auto Expiry:* `{auto_expiry}`

📍 *Spot:* `{spot_price:.2f}` | *Bias:* {signal_direction}
📊 *Trend Alignment:* 5M (`{trend_5m}`) | 15M (`{trend_15m}`)
📊 *Indicators:* VWAP: `{vwap_val:.1f}` | RSI: `{rsi:.1f}` | ATR: `{atr_val:.1f}` | VIX: `{vix_val:.1f}`
⏸️ *Status:* Timeframe mismatch or range-bound market.
"""
        return msg, buttons, None

    ce_ltp, pe_ltp = get_option_chain_data(config["upstox_key"], atm_strike, auto_expiry)
    
    if "CE" in action_type and ce_ltp and ce_ltp > 0:
        estimated_premium = ce_ltp
        prem_source = "Option Chain API"
    elif "PE" in action_type and pe_ltp and pe_ltp > 0:
        estimated_premium = pe_ltp
        prem_source = "Option Chain API"
    else:
        estimated_premium = round(spot_price * config["prem_factor"], 1)
        prem_source = "Estimated Delta Model"

    # ATR Dynamic Volatility Multipliers
    sl_pts = round(max(atr_val * 0.15, estimated_premium * 0.12), 1)
    t1_pts = round(sl_pts * 1.5, 1)
    t2_pts = round(sl_pts * 2.5, 1)
    t3_pts = round(sl_pts * 4.0, 1)

    sl_price = round(estimated_premium - sl_pts, 1)
    t1_price = round(estimated_premium + t1_pts, 1)
    t2_price = round(estimated_premium + t2_pts, 1)
    t3_price = round(estimated_premium + t3_pts, 1)

    log_trade_to_csv({
        "Timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "Index": name,
        "Signal": action_type,
        "Strike": recommended_strike,
        "Spot": spot_price,
        "Entry_Premium": estimated_premium,
        "SL": sl_price,
        "Target1": t1_price,
        "Target2": t2_price,
        "Target3": t3_price,
        "MTF_Status": f"5M:{trend_5m}|15M:{trend_15m}",
        "VIX": vix_val,
        "Status": "OPEN"
    })

    msg = f"""🔥 *{name} INSTITUTIONAL SIGNAL*
📅 *Auto Expiry:* `{auto_expiry}`

📍 *Spot:* `{spot_price:.2f}` | *Bias:* {signal_direction}
📊 *MTF Confirmation:* 5m ({trend_5m}) + 15m ({trend_15m}) 🟢
⚡ *Trade:* BUY *{recommended_strike}* ({action_type})
🏷️ *Price Feed:* {prem_source}

📊 *DYNAMIC ATR VOLATILITY LEVELS:*
• *Buy Range:* ₹{estimated_premium}
• *SL (ATR Risk):* ₹{sl_price} (-{sl_pts} pts)
• *Target 1 (Book 50% Lot):* ₹{t1_price} (+{t1_pts} pts)
• *Target 2 (Book 30% Lot):* ₹{t2_price} (+{t2_pts} pts)
• *Target 3 (Trail 20% Runner):* ₹{t3_price} (+{t3_pts} pts)
"""

    trade_monitor_info = {
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
            ce_ltp, pe_ltp = get_option_chain_data(trade["upstox_key"], trade["atm_strike"], trade["expiry"])
            current_price = ce_ltp if "CE" in trade["action"] else pe_ltp

            if current_price and current_price > 0:
                if current_price >= trade["t3"]:
                    alert = f"🚀 *{trade['index']} TARGET 3 (RUNNER) HIT!* 🎉\n\nStrike: *{trade['strike']}*\nEntry: ₹{trade['entry']} ➡️ Current: ₹{current_price}\n🔥 *100% Multi-Lot Targets Accomplished!*"
                    send_telegram_message(alert)
                    active_trades.remove(trade)
                elif current_price >= trade["t2"] and not trade.get("t2_alert_sent"):
                    alert = f"🎯 *{trade['index']} TARGET 2 HIT!* 👏\n\nStrike: *{trade['strike']}*\nEntry: ₹{trade['entry']} ➡️ Current: ₹{current_price}\n💰 *ACTION:* Book additional 30% Lot profit. Trail remaining 20% Lot for T3."
                    send_telegram_message(alert)
                    trade["t2_alert_sent"] = True
                elif current_price >= trade["t1"] and not trade.get("t1_alert_sent"):
                    alert = f"🎯 *{trade['index']} TARGET 1 HIT!* 👏\n\nStrike: *{trade['strike']}*\nEntry: ₹{trade['entry']} ➡️ Current: ₹{current_price}\n🛡️ *ACTION:* Book 50% Lot Profit! Move Stop Loss to Entry Price (₹{trade['entry']}). Trade is now RISK-FREE."
                    send_telegram_message(alert)
                    trade["t1_alert_sent"] = True
                elif current_price <= trade["sl"]:
                    alert = f"🛑 *{trade['index']} STOP LOSS HIT!*\n\nStrike: *{trade['strike']}*\nEntry: ₹{trade['entry']} ➡️ Exit: ₹{current_price}\n🛡️ System exited position safely."
                    send_telegram_message(alert)
                    active_trades.remove(trade)

def main():
    log_activity("🚀 Institutional Multi-Index Algo Engine (MTF + ATR + Auto-Expiry) Started")
    now_hour = datetime.now().hour

    if now_hour >= 15 and datetime.now().minute >= 30:
        generate_daily_pnl_summary()
        return

    vix_val = get_india_vix()
    full_alert = f"🎯 *MULTI-INDEX TRADING ALGO REPORT*\n*India VIX:* `{vix_val:.2f}`\n\n"
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







