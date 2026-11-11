import sqlite3
import pandas as pd
import numpy as np

def run_mean_reversion_backtest(table_name='BTC_USDT_1h', window=50, z_entry=-2.0, z_exit=0.0, fee=0.001):
    """
    Backtest chiến lược Mean Reversion dựa trên Z-Score:
    - Mua (Long) khi Z-Score < z_entry (ví dụ: -2.0)
    - Đóng lệnh (Flat) khi Z-Score >= z_exit (ví dụ: 0.0)
    - fee: Phí giao dịch của sàn (0.001 tương đương 0.1% trên Binance)
    """
    conn = sqlite3.connect('quant_data.db')
    df = pd.read_sql(f"SELECT * FROM {table_name}", conn)
    conn.close()
    
    # 1. Tính toán các chỉ số thống kê
    df['return'] = df['close'].pct_change()
    df['mean'] = df['close'].rolling(window=window).mean()
    df['std'] = df['close'].rolling(window=window).std()
    df['z_score'] = (df['close'] - df['mean']) / df['std']
    df = df.dropna().reset_index(drop=True)
    
    # 2. Tạo tín hiệu giao dịch (Vectorized / Vòng lặp trạng thái)
    position = 0 # 0 là đứng ngoài, 1 là đang giữ lệnh Mua
    positions = []
    
    for z in df['z_score']:
        if position == 0 and z < z_entry:
            position = 1 # Bắt đầu Mua vào
        elif position == 1 and z >= z_exit:
            position = 0 # Bán ra chốt lời/cắt lỗ
        positions.append(position)
        
    # Dịch chuyển vị thế xuống 1 cây nến (vì tín hiệu đóng nến này thì đầu nến sau mới khớp lệnh thực tế)
    df['position'] = pd.Series(positions).shift(1).fillna(0)
    
    # 3. Tính toán chi phí giao dịch mỗi khi thay đổi vị thế (Mua hoặc Bán)
    df['trades'] = df['position'].diff().abs().fillna(0)
    df['strategy_return'] = (df['position'] * df['return']) - (df['trades'] * fee)
    
    # 4. Tính đường cong vốn (Equity Curve)
    df['cumulative_market'] = (1 + df['return']).cumprod()
    df['cumulative_strategy'] = (1 + df['strategy_return']).cumprod()
    
    # 5. ĐO LƯỜNG HIỆU SUẤT THỐNG KÊ (QUANT METRICS)
    total_return = (df['cumulative_strategy'].iloc[-1] - 1) * 100
    market_return = (df['cumulative_market'].iloc[-1] - 1) * 100
    
    # Tính Sharpe Ratio (Quy đổi theo năm cho khung 1h: 24 giờ * 365 ngày = 8760 nến/năm)
    annual_factor = np.sqrt(365 * 24)
    sharpe_ratio = (df['strategy_return'].mean() / df['strategy_return'].std()) * annual_factor
    
    # Tính Maximum Drawdown (Mức sụt giảm tài khoản sâu nhất từ đỉnh)
    rolling_max = df['cumulative_strategy'].cummax()
    drawdown = (df['cumulative_strategy'] - rolling_max) / rolling_max
    max_drawdown = drawdown.min() * 100
    
    # Đếm số lần giao dịch
    total_trades = int(df['trades'].sum() / 2)
    
    print("="*55)
    print(f" KẾT QUẢ BACKTEST CHIẾN LƯỢC Z-SCORE ({table_name})")
    print("="*55)
    print(f"• Tham số         : Chu kỳ = {window} | Mua khi Z < {z_entry} | Bán khi Z >= {z_exit}")
    print(f"• Tổng số lệnh    : {total_trades} lệnh")
    print(f"• Lợi nhuận Bot   : {total_return:.2f}% (Đã trừ phí sàn 0.1%/lệnh)")
    print(f"• Lợi nhuận Hold  : {market_return:.2f}% (Mua và nắm giữ thụ động)")
    print(f"• Sharpe Ratio    : {sharpe_ratio:.2f} (> 1.0 là ổn, > 2.0 là rất tốt)")
    print(f"• Max Drawdown    : {max_drawdown:.2f}% (Mức sụt giảm vốn tối đa)")
    print("="*55)

if __name__ == '__main__':
    # Chạy kiểm định thử trên các đồng coin trong Database
    for table in ['BTC_USDT_1h', 'ETH_USDT_1h', 'SOL_USDT_1h']:
        run_mean_reversion_backtest(table_name=table, window=50, z_entry=-2.0, z_exit=0.0)