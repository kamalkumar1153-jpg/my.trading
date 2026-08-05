import os
import json
import time
import csv
import urllib.request
import urllib.parse
from datetime import datetime

TELEGRAM_BOT_TOKEN = "8642052658:AAH1o7maezHyHPgxeOxeiGLQ3wvu1JglvKI"
TELEGRAM_CHAT_ID = "5598707490"

# Default Level Percentages
BASE_SL_PERCENT = 15.0
BASE_TARGET1_PERCENT = 25.0
BASE_TARGET2_PERCENT = 50.0

# Index Configuration Matrix
# Weekdays: 0=Mon, 1=Tue, 2=Wed, 3=Thu, 4=Fri, 5=Sat, 6=Sun
INDICES = {
    "NIFTY": {
        "upstox_key": "NSE_INDEX|Nifty 50",
        "yahoo_symbol": "%5ENSEI",
        "tv_chart": "NSE:NIFTY",
        "step": 50,
        "prem_factor": 0.0052,
        "expiry_type": "weekday",
        "expiry_value": 1  # Tuesday
    },
    "SENSEX": {
        "upstox_key": "BSE_INDEX|SENSEX",
        "yahoo_symbol": "%5EBSESN",
        "tv_chart": "BSE:SENSEX",
        "step": 100,
        "prem_factor": 0.0045,
        "expiry_type": "weekday",
        "expiry_value": 3  # Thursday
    },
    "BANKNIFTY": {
        "upstox_key": "NSE_INDEX|Nifty Bank",
        "yahoo_symbol": "%5ENSEBANK",
        "tv_chart": "NSE:BANKNIFTY",
        "step": 100,
        "prem_factor": 0.0075,
        "expiry_type": "monthly_date",
        "expiry_value": 1  # 1st of Every Month
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
    if inline_keyboard:
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

def calculate_vwap(high, low, close):
    # Approximation for intraday VWAP proxy using Typical Price
    return (high + low + close) / 3.0

def get_india_vix():
    # Dynamic VIX Fetching with Fallback
    try:
        url = "https://query1.finance.yahoo.com/v8/finance/chart/%5EINDIAVIX?range=1d&interval=5m"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode('utf-8'))
            meta = data['chart']['result'][0]['meta']
            return float(meta['regularMarketPrice'])
    except Exception:
        return 14.0  # Normal Default VIX

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

def get_option_chain_data(instrument_key, atm_strike):
    token = get_token()
    if not token:
        return None, None
    try:
        encoded_key = urllib.parse.quote(instrument_key)
        url = f"https://api.upstox.com/v2/option/chain?instrument_key={encoded_key}&expiry_date="
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

def check_is_expiry(config):
    now = datetime.now()
    if config["expiry_type"] == "weekday":
        return now.weekday() == config["expiry_value"]
    elif config["expiry_type"] == "monthly_date":
        return now.day == config["expiry_value"]
    return False

def log_trade_to_csv(data_row):
    file_exists = os.path.isfile("trade_journal.csv")
    fields = ["Timestamp", "Index", "Signal", "Strike", "Spot", "Entry_Premium", "SL", "Target1", "Target2", "VIX"]
    try:
        with open("trade_journal.csv", "a", newline="") as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fields)
            if not file_exists:
                writer.writeheader()
            writer.writerow(data_row)
            log_activity("📝 Trade logged to trade_journal.csv successfully.")
    except Exception as e:
        log_activity(f"CSV Logging Error: {e}")

def process_index(name, config, vix_val):
    log_activity(f"⚡ Processing {name} with Advanced Filters...")
    
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

    # Dynamic Risk Adjustment Based on VIX
    vix_modifier = 1.0
    if vix_val > 16.0:
        vix_modifier = 1.25  # Dynamic Wider SL/Target in High Volatility
    elif vix_val < 11.0:
        vix_modifier = 0.85  # Tighter SL/Target in Low Volatility

    is_expiry_day = check_is_expiry(config)

    if is_expiry_day:
        sl_pct = 10.0 * vix_modifier
        t1_pct = 40.0 * vix_modifier
        t2_pct = 100.0 * vix_modifier
        expiry_tag = "🔥 *EXPIRY DAY (HERO-ZERO MODE)*"
    else:
        sl_pct = BASE_SL_PERCENT * vix_modifier
        t1_pct = BASE_TARGET1_PERCENT * vix_modifier
        t2_pct = BASE_TARGET2_PERCENT * vix_modifier
        expiry_tag = "📅 Regular Session"

    # Indicators: EMA, RSI, VWAP
    ema9 = calculate_ema(close_series, 3)
    ema21 = calculate_ema(close_series, 5)
    rsi = calculate_rsi(close_series, 14)
    vwap_val = calculate_vwap(high_p, low_p, spot_price)

    step = config["step"]
    atm_strike = round(spot_price / step) * step

    # Advanced Entry Rules (Technical + VWAP Validation)
    if spot_price > ema9 and ema9 >= ema21 and rsi > 52 and spot_price >= vwap_val:
        action_type = "CALL (CE)"
        signal_direction = "🟢 STRONG BULLISH (VWAP CONFIRMED)"
        recommended_strike = f"{atm_strike} CE"
        trade_active = True
    elif spot_price < ema9 and ema9 <= ema21 and rsi < 48 and spot_price <= vwap_val:
        action_type = "PUT (PE)"
        signal_direction = "🔴 STRONG BEARISH (VWAP CONFIRMED)"
        recommended_strike = f"{atm_strike} PE"
        trade_active = True
    else:
        signal_direction = "⚠️ SIDEWAYS / NO TRADE ZONE"
        trade_active = False

    if not trade_active:
        msg = f"""🔥 *{name} MARKET ANALYSIS*
{expiry_tag}

📍 *Spot:* `{spot_price:.2f}` | *Bias:* {signal_direction}
📊 *Filters:* EMA(9/21): `{ema9:.1f}/{ema21:.1f}` | RSI: `{rsi:.1f}` | VWAP: `{vwap_val:.1f}` | VIX: `{vix_val:.1f}`
⏸️ *Status:* Range-bound or VWAP mismatch. Avoid trades.
"""
        return msg, None, None

    # Fetch Premium Data
    ce_ltp, pe_ltp = get_option_chain_data(config["upstox_key"], atm_strike)
    
    if "CE" in action_type and ce_ltp and ce_ltp > 0:
        estimated_premium = ce_ltp
        prem_source = "Option Chain API"
    elif "PE" in action_type and pe_ltp and pe_ltp > 0:
        estimated_premium = pe_ltp
        prem_source = "Option Chain API"
    else:
        estimated_premium = round(spot_price * config["prem_factor"], 1)
        prem_source = "Estimated Delta Model"

    sl_pts = round(estimated_premium * (sl_pct / 100), 1)
    t1_pts = round(estimated_premium * (t1_pct / 100), 1)
    t2_pts = round(estimated_premium * (t2_pct / 100), 1)

    sl_price = round(estimated_premium - sl_pts, 1)
    t1_price = round(estimated_premium + t1_pts, 1)
    t2_price = round(estimated_premium + t2_pts, 1)

    # Log Active Trade to CSV
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
        "VIX": vix_val
    })

    msg = f"""🔥 *{name} HIGH-CONFIRMATION SIGNAL*
{expiry_tag}

📍 *Spot:* `{spot_price:.2f}` | *Bias:* {signal_direction}
📊 *Tech Filters:* VWAP: `{vwap_val:.1f}` | RSI: `{rsi:.1f}` | India VIX: `{vix_val:.1f}`
⚡ *Trade:* BUY *{recommended_strike}* ({action_type})
🏷️ *Price Feed:* {prem_source}

📊 *LEVELS:*
• *Buy Range:* ₹{estimated_premium}
• *SL (-{sl_pct:.1f}%):* ₹{sl_price} (-{sl_pts} pts)
• *Target 1 (+{t1_pct:.1f}%):* ₹{t1_price} (+{t1_pts} pts)
• *Target 2 (+{t2_pct:.1f}%):* ₹{t2_price} (+{t2_pts} pts)
"""

    tv_symbol = config["tv_chart"]
    if "NIFTY" in name and "BANK" not in name:
        oc_url = "https://www.nseindia.com/option-chain"
    else:
        oc_url = "https://upstox.com/option-chain/"

    buttons = [
        {"text": f"📈 {name} Chart", "url": f"https://in.tradingview.com/chart/?symbol={tv_symbol}"},
        {"text": "📊 Live Option Chain", "url": oc_url}
    ]

    trade_monitor_info = {
        "index": name,
        "strike": recommended_strike,
        "entry": estimated_premium,
        "sl": sl_price,
        "t1": t1_price,
        "t2": t2_price,
        "upstox_key": config["upstox_key"],
        "yahoo_symbol": config["yahoo_symbol"],
        "atm_strike": atm_strike,
        "action": action_type
    }

    return msg, buttons, trade_monitor_info

def monitor_live_trades(active_trades):
    if not active_trades:
        return
    
    log_activity("📡 Starting Live Auto Trailing SL & Target Hit Monitoring...")
    # Monitor active positions for up to 10 cycles (approx 5 minutes per run)
    for _ in range(5):
        time.sleep(30)
        for trade in active_trades:
            ce_ltp, pe_ltp = get_option_chain_data(trade["upstox_key"], trade["atm_strike"])
            current_price = None
            if "CE" in trade["action"] and ce_ltp:
                current_price = ce_ltp
            elif "PE" in trade["action"] and pe_ltp:
                current_price = pe_ltp

            if current_price:
                if current_price >= trade["t2"]:
                    alert = f"🚀 *{trade['index']} TARGET 2 HIT!* 🎉\n\nStrike: *{trade['strike']}*\nEntry: ₹{trade['entry']} ➡️ Current: ₹{current_price}\n🔥 *Full Profit Booked!*"
                    send_telegram_message(alert)
                    active_trades.remove(trade)
                elif current_price >= trade["t1"] and not trade.get("t1_alert_sent"):
                    alert = f"🎯 *{trade['index']} TARGET 1 HIT!* 👏\n\nStrike: *{trade['strike']}*\nEntry: ₹{trade['entry']} ➡️ Current: ₹{current_price}\n🛡️ *ACTION:* Stop Loss ko Entry Price (₹{trade['entry']}) par Shift (Trail) kar dein!"
                    send_telegram_message(alert)
                    trade["t1_alert_sent"] = True
                elif current_price <= trade["sl"]:
                    alert = f"🛑 *{trade['index']} STOP LOSS HIT!*\n\nStrike: *{trade['strike']}*\nEntry: ₹{trade['entry']} ➡️ Exit: ₹{current_price}\n🛡️ System exited position safely."
                    send_telegram_message(alert)
                    active_trades.remove(trade)

def main():
    log_activity("🚀 Institutional Multi-Index Algo Engine Started")
    vix_val = get_india_vix()
    full_alert = f"🎯 *MULTI-INDEX HIGH-CONFIRMATION SIGNAL*\n*India VIX:* `{vix_val:.2f}`\n\n"
    all_buttons = []
    active_trades = []

    for name, config in INDICES.items():
        signal_text, btns, trade_info = process_index(name, config, vix_val)
        if signal_text:
            full_alert += signal_text + "\n" + "─"*25 + "\n\n"
            if btns:
                all_buttons.append(btns)
            if trade_info:
                active_trades.append(trade_info)

    full_alert += "🛡️ *RISK RULES:* Target 1 hit hone par Stop Loss ko Entry price par shift karein."

    send_telegram_message(full_alert, inline_keyboard=all_buttons)
    
    if active_trades:
        monitor_live_trades(active_trades)

if __name__ == "__main__":
    main()




