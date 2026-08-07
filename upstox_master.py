import urllib.request
import json

def get_nse_direct_live_data(yahoo_symbol):
    """Fetches live market data directly using NSE Yahoo Live Scraping engine"""
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
            
            log_activity(f"🟢 Direct NSE Feed Fetched: {spot_price}")
            return spot_price, open_price, high_price, low_price, "NSE DIRECT LIVE FEED"
    except Exception as e:
        log_activity(f"❌ NSE Direct Feed Error: {e}")
        return None












