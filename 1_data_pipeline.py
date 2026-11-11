import ccxt
import pandas as pd
import sqlite3
import time
from datetime import datetime, timedelta

def fetch_binance_data(symbol='BTC/USDT', timeframe='1h', days=365):
    """Tải dữ liệu lịch sử từ Binance thông qua thư viện CCXT"""
    exchange = ccxt.binance({
        'enableRateLimit': True, # Tự động giới hạn tốc độ gọi API để không bị khóa IP
    })
    
    # Tính mốc thời gian bắt đầu lấy dữ liệu (tính bằng milliseconds)
    since = exchange.parse8601((datetime.utcnow() - timedelta(days=days)).isoformat())
    all_ohlcv = []
    
    print(f"[*] Đang tải dữ liệu {symbol} (Khung {timeframe}) trong {days} ngày qua...")
    
    while since < exchange.milliseconds():
        try:
            ohlcv = exchange.fetch_ohlcv(symbol, timeframe, since=since, limit=1000)
            if not ohlcv:
                break
            since = ohlcv[-1][0] + 1 # Cập nhật mốc thời gian tiếp theo
            all_ohlcv.extend(ohlcv)
            time.sleep(exchange.rateLimit / 1000) # Nghỉ một chút theo quy định của sàn
        except Exception as e:
            print(f"[!] Lỗi khi tải dữ liệu: {e}")
            break
            
    # Chuyển đổi sang bảng Pandas DataFrame
    df = pd.DataFrame(all_ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms')
    
    # Làm sạch dữ liệu cơ bản: Xóa các dòng trùng lặp và sắp xếp theo thời gian
    df = df.drop_duplicates(subset=['timestamp']).sort_values('timestamp').reset_index(drop=True)
    return df

def save_to_sqlite(df, symbol, timeframe, db_name='quant_data.db'):
    """Lưu bảng dữ liệu vào cơ sở dữ liệu SQLite"""
    # Đặt tên bảng theo quy tắc: BTC_USDT_1h
    table_name = f"{symbol.replace('/', '_')}_{timeframe}"
    
    conn = sqlite3.connect(db_name)
    # Lưu đè hoặc cập nhật bảng
    df.to_sql(table_name, conn, if_exists='replace', index=False)
    conn.close()
    print(f"[+] Đã lưu thành công {len(df)} dòng dữ liệu vào bảng '{table_name}' trong file {db_name}\n")

if __name__ == '__main__':
    # 1. Danh sách các cặp tiền
    symbols = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'BNB/USDT']
    
    # 2. KHAI BÁO NHIỀU MỐC THỜI GIAN CÙNG LÚC (Dạng danh sách)
    timeframes = ['15m', '1h', '4h', '1d'] 
    
    days_to_fetch = 180 
    
    # 3. Chạy vòng lặp lồng nhau: Duyệt qua từng đồng coin, mỗi đồng coin lấy đủ 4 khung thời gian
    for sym in symbols:
        for tf in timeframes:
            print(f"--- Bắt đầu xử lý: {sym} (Khung {tf}) ---")
            df_data = fetch_binance_data(symbol=sym, timeframe=tf, days=days_to_fetch)
            save_to_sqlite(df_data, symbol=sym, timeframe=tf)
            
    print("=== HOÀN TẤT THU THẬP TẤT CẢ DỮ LIỆU ===")
