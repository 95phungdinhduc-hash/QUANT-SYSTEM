import ccxt
import pandas as pd
import numpy as np
import requests
import time
import sqlite3
import math
from datetime import datetime
import pytz
import feedparser

TELEGRAM_BOT_TOKEN = "9296707854:AAFdAKMreBsDx6oPJejQbiv6MFeGn75gWv4"
TELEGRAM_CHAT_ID = "6256284096"

def get_user_settings():
    """Tự động đọc cấu hình Vốn và Rủi ro từ trang Web Safari (Database)"""
    try:
        conn = sqlite3.connect('quant_data.db')
        df = pd.read_sql("SELECT * FROM user_settings", conn)
        conn.close()
        return df['capital'].iloc[0], df['risk_pct'].iloc[0]
    except Exception:
        # Nếu Web chưa tạo bảng, dùng mức mặc định an toàn
        return 100.0, 2.0 

def send_telegram_alert(message):
    print(f"\n[🔔 BÁO ĐỘNG]\n{message}\n")
    if "ĐIỀN_TOKEN" not in TELEGRAM_BOT_TOKEN:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}, timeout=10)

def get_trading_session():
    hour = datetime.now(pytz.timezone('Asia/Ho_Chi_Minh')).hour
    if 6 <= hour < 14: return "🇯🇵 Phiên Á (Sideway, biên độ hẹp)"
    elif 14 <= hour < 19: return "🇬🇧 Phiên Âu (Biến động trung bình)"
    elif 19 <= hour < 23: return "🇺🇸 Phiên Mỹ + Âu (Thanh khoản cực lớn, sóng mạnh)"
    else: return "🇺🇸 Phiên Mỹ (Chạy theo xu hướng)"

def get_news_sentiment():
    try:
        parsed = feedparser.parse("https://www.coindesk.com/arc/outboundfeeds/rss/")
        text = " ".join([entry.title for entry in parsed.entries[:5]]).lower()
        bull_score = sum(1 for w in ['surge', 'jump', 'bull', 'high', 'gain', 'approve', 'etf', 'buy', 'rally'] if w in text)
        bear_score = sum(1 for w in ['drop', 'crash', 'bear', 'low', 'hack', 'ban', 'sec', 'lawsuit', 'fall', 'dump'] if w in text)
        if bull_score > bear_score: return "🟢 TÍCH CỰC (Nhiều tin tốt)"
        elif bear_score > bull_score: return "🔴 TIÊU CỰC (Nhiều tin xấu)"
        else: return "⚪ TRUNG LẬP (Không có tin sốc)"
    except:
        return "⚪ Không thể kết nối tin tức"

def scan_market(symbols, timeframe='1h', window=50):
    exchange = ccxt.binance({'enableRateLimit': True})
    
    # 1. ĐỌC CÀI ĐẶT TỪ WEB TRƯỚC MỖI LẦN QUÉT
    capital, risk_pct = get_user_settings()
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Đang quét thị trường | Vốn cài đặt: ${capital:,.2f} | Rủi ro: {risk_pct}%...")
    
    for sym in symbols:
        try:
            ohlcv = exchange.fetch_ohlcv(sym, timeframe, limit=window + 10)
            df = pd.DataFrame(ohlcv, columns=['ts', 'open', 'high', 'low', 'close', 'volume'])
            
            current_price = df['close'].iloc[-1]
            mean_price = df['close'].rolling(window).mean().iloc[-1]
            std_price = df['close'].rolling(window).std().iloc[-1]
            z_score = (current_price - mean_price) / std_price
            
            if abs(z_score) >= 2.0:
                session = get_trading_session()
                sentiment = get_news_sentiment()
                
                if z_score > 0:
                    trade_type = "🔴 BÁN KHỐNG (Short)"
                    sl_price = current_price + (1.2 * std_price) 
                    tp_price = mean_price
                    warning = "⚠️ LƯU Ý: Tin tức đang tốt, cản tàu rủi ro cao!" if "TÍCH CỰC" in sentiment else "✅ Tin xấu ủng hộ lệnh Short."
                else:
                    trade_type = "🟢 MUA VÀO (Long)"
                    sl_price = current_price - (1.2 * std_price)
                    tp_price = mean_price
                    warning = "⚠️ LƯU Ý: Tin đang rất xấu, bắt dao rơi rủi ro!" if "TIÊU CỰC" in sentiment else "✅ Tin tốt ủng hộ lệnh Long."

                # 2. TÍNH TOÁN THEO ĐÚNG SỐ VỐN TRÊN WEB
                risk_amount_usd = capital * (risk_pct / 100)
                stop_distance_pct = abs(current_price - sl_price) / current_price
                position_size_usd = risk_amount_usd / stop_distance_pct if stop_distance_pct > 0 else 0
                
                if position_size_usd < 5.0:
                    lev_needed = 5.0 / position_size_usd
                    pos_note = f"Cần đòn bẩy tối thiểu {math.ceil(lev_needed)}x để đạt lệnh tối thiểu 5$ của Binance."
                    actual_size = 5.0
                else:
                    pos_note = "Không cần đòn bẩy, đánh Spot bình thường."
                    actual_size = position_size_usd

                msg = (f"🤖 *TRỢ LÝ ĐỊNH LƯỢNG BÁO CÁO*\n\n"
                       f"Tài sản: `{sym}` (Khung {timeframe})\n"
                       f"Hành động: *{trade_type}*\n"
                       f"Giá hiện tại: `${current_price:,.4f}`\n"
                       f"Z-Score: `{z_score:.2f} σ`\n\n"
                       
                       f"📰 *VĨ MÔ:*\n"
                       f"• Tin tức: {sentiment}\n"
                       f"• _{warning}_\n\n"
                       
                       f"🛡️ *ĐI VỐN (Theo vốn set trên Web: ${capital}):*\n"
                       f"• Lệnh cần vào: `${actual_size:,.2f}`\n"
                       f"• Chấp nhận lỗ: `${risk_amount_usd:,.2f}`\n"
                       f"• Ghi chú: _{pos_note}_\n\n"
                       
                       f"🎯 *ĐIỂM ĐẶT LỆNH:*\n"
                       f"• SL (Cắt lỗ): `${sl_price:,.4f}`\n"
                       f"• TP (Chốt lời): `${tp_price:,.4f}`")
                
                send_telegram_alert(msg)
                
        except Exception as e:
            pass

if __name__ == '__main__':
    watchlist = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'BNB/USDT']
    print("=== BOT ĐÃ KẾT NỐI ĐỒNG BỘ VỚI WEB SAFARI ===")
    while True:
        scan_market(symbols=watchlist, timeframe='1h', window=50)
        time.sleep(300)