import os
import json
import time
import urllib.request
import urllib.parse
from datetime import datetime

TELEGRAM_BOT_TOKEN = "8642052658:AAH1o7maezHyHPgxeOxeiGLQ3wvu1JglvKI"
TELEGRAM_CHAT_ID = "5598707490"

SL_PERCENT = 15.0
TARGET1_PERCENT = 25.0
TARGET2_PERCENT = 50.0

INDICES = {
    "NIFTY": {
        "upstox_key": "NSE_INDEX|Nifty 50",
        "yahoo_symbol": "%5ENSEI",
        "step": 50,
        "prem_factor": 0.0052
    },
    "BANKNIFTY": {
        "upstox_key": "NSE_INDEX|Nifty Bank",
        "yahoo_symbol": "%5ENSEBANK",
        "step": 100,
        "prem_factor": 0.0075
    },
    "SENSEX": {
        "upstox_key": "BSE_INDEX|SENSEX",
        "yahoo_symbol": "%5EBSESN",
        "step": 100,
        "prem_factor": 0.0045
    }
}

def log_activity(text):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"[{timestamp}] {text}"
    print(log_entry)

def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = json.dumps({
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }).encode('utf-8')
    
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
            return spot_price, open_price, close_prices, "LIVE BACKUP FEED"
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

def process_index(name, config):
    log_activity(f"⚡ Processing {name} with Technical Filters & Option Chain...")
    
    res = get_upstox_market_data(config["upstox_key"])
    close_series = []
    
    if res:
        spot_price, open_p, high_p, low_p, source = res
        close_series = [open_p, low_p, (open_p + spot_price)/2, high_p, spot_price]
    else:
        backup = get_backup_data(config["yahoo_symbol"])
        if backup:
            spot_price, open_p, close_series, source = backup
        else:
            log_activity(f"❌ Failed to fetch market data for {name}")
            return None

    ema9 = calculate_ema(close_series, 3)
    ema21 = calculate_ema(close_series, 5)
    rsi = calculate_rsi(close_series, 14)

    step = config["step"]
    atm_strike = round(spot_price / step) * step

    if spot_price > ema9 and ema9 >= ema21 and rsi > 52:
        action_type = "CALL (CE)"
        signal_direction = "🟢 STRONG BULLISH"
        recommended_strike = f"{atm_strike} CE"
        trade_active = True
    elif spot_price < ema9 and ema9 <= ema21 and rsi < 48:
        action_type = "PUT (PE)"
        signal_direction = "🔴 STRONG BEARISH"
        recommended_strike = f"{atm_strike} PE"
        trade_active = True
    else:
        signal_direction = "⚠️ SIDEWAYS / NO TRADE ZONE"
        trade_active = False

    if not trade_active:
        return f"""🔥 *{name} MARKET ANALYSIS*

📍 *Spot:* `{spot_price:.2f}` | *Bias:* {signal_direction}
📊 *Indicators:* EMA(9/21): `{ema9:.1f}/{ema21:.1f}` | RSI: `{rsi:.1f}`
⏸️ *Status:* Range-bound market. Avoid trades to prevent losses.
"""

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

    sl_pts = round(estimated_premium * (SL_PERCENT / 100), 1)
    t1_pts = round(estimated_premium * (TARGET1_PERCENT / 100), 1)
    t2_pts = round(estimated_premium * (TARGET2_PERCENT / 100), 1)

    sl_price = round(estimated_premium - sl_pts, 1)
    t1_price = round(estimated_premium + t1_pts, 1)
    t2_price = round(estimated_premium + t2_pts, 1)

    return f"""🔥 *{name} HIGH-CONFIRMATION SIGNAL*

📍 *Spot:* `{spot_price:.2f}` | *Bias:* {signal_direction}
📊 *Tech Filters:* EMA(9/21): `{ema9:.1f}/{ema21:.1f}` | RSI: `{rsi:.1f}`
⚡ *Trade:* BUY *{recommended_strike}* ({action_type})
🏷️ *Price Feed:* {prem_source}

📊 *LEVELS:*
• *Buy Range:* ₹{estimated_premium}
• *SL (-{SL_PERCENT}%):* ₹{sl_price} (-{sl_pts} pts)
• *Target 1 (+{TARGET1_PERCENT}%):* ₹{t1_price} (+{t1_pts} pts)
• *Target 2 (+{TARGET2_PERCENT}%):* ₹{t2_price} (+{t2_pts} pts)
"""

def main():
    log_activity("🚀 Advanced Multi-Index Engine Triggered")
    full_alert = "🎯 *MULTI-INDEX HIGH-CONFIRMATION SIGNAL*\n\n"
    
    for name, config in INDICES.items():
        signal = process_index(name, config)
        if signal:
            full_alert += signal + "\n" + "─"*25 + "\n\n"

    full_alert += "🛡️ *RISK RULES:* Signal confirmation ke sath hi entry lein. Target 1 par SL Entry price par shift karein.\n"
    
    print(full_alert)
    send_telegram_message(full_alert)

if __name__ == "__main__":
    main()

