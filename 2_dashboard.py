import streamlit as st
import pandas as pd
import numpy as np
import sqlite3
import ccxt
import feedparser
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
from statsmodels.tsa.stattools import adfuller
from datetime import datetime, timedelta
import time

# ==========================================
# 1. CẤU HÌNH GIAO DIỆN TRANG WEB
# ==========================================
st.set_page_config(page_title="Hệ Thống Giao Dịch Định Lượng", page_icon="📈", layout="wide")

st.markdown("""
    <style>
    .metric-box {
        background-color: #1E2129; padding: 15px; border-radius: 10px;
        border-left: 5px solid #00F0FF; box-shadow: 0 4px 6px rgba(0,0,0,0.3);
    }
    .risk-box {
        background-color: #1E2129; padding: 15px; border-radius: 10px;
        border-left: 5px solid #FF4B4B; box-shadow: 0 4px 6px rgba(0,0,0,0.3);
    }
    .news-card {
        background-color: #1A1C23; padding: 15px; border-radius: 8px;
        margin-bottom: 12px; border-left: 4px solid #F0B90B;
    }
    </style>
""", unsafe_allow_html=True)

st.title("Lil_Duck PHÂN TÍCH CHO NHA")
DB_NAME = 'quant_data.db'

# ==========================================
# 2. CÁC HÀM XỬ LÝ DỮ LIỆU & TIN TỨC
# ==========================================
def fetch_and_save_data(symbol, timeframe, days=180):
    exchange = ccxt.binance({'enableRateLimit': True})
    since = exchange.parse8601((datetime.utcnow() - timedelta(days=days)).isoformat())
    all_ohlcv = []
    
    my_bar = st.progress(0, text=f"Đang tải dữ liệu {symbol} ({timeframe})...")
    while since < exchange.milliseconds():
        try:
            ohlcv = exchange.fetch_ohlcv(symbol, timeframe, since=since, limit=1000)
            if not ohlcv: break
            since = ohlcv[-1][0] + 1
            all_ohlcv.extend(ohlcv)
            time.sleep(0.1)
        except Exception as e:
            st.error(f"Lỗi mạng: {e}")
            break
            
    my_bar.empty()
    df = pd.DataFrame(all_ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms')
    df = df.drop_duplicates(subset=['timestamp']).sort_values('timestamp').reset_index(drop=True)
    
    table_name = f"{symbol.replace('/', '_')}_{timeframe}"
    conn = sqlite3.connect(DB_NAME)
    df.to_sql(table_name, conn, if_exists='replace', index=False)
    conn.close()
    return table_name, len(df)

def get_available_tables():
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        
        # Chỉ lấy các bảng dữ liệu coin, loại trừ bảng 'user_settings'
        tables = [row[0] for row in cursor.fetchall() if row[0] != 'user_settings']
        
        conn.close()
        return tables
    except: 
        return []

def load_table_data(table_name, window=50):
    conn = sqlite3.connect(DB_NAME)
    df = pd.read_sql(f"SELECT * FROM {table_name}", conn)
    conn.close()
    df['datetime'] = pd.to_datetime(df['datetime'])
    df['return'] = df['close'].pct_change()
    df['log_return'] = np.log(df['close'] / df['close'].shift(1))
    df['rolling_mean'] = df['close'].rolling(window=window).mean()
    df['rolling_std'] = df['close'].rolling(window=window).std()
    df['z_score'] = (df['close'] - df['rolling_mean']) / df['rolling_std']
    return df.dropna().reset_index(drop=True)

@st.cache_data(ttl=300)
def fetch_crypto_news():
    """Hàm kéo tin tức RSS và chấm điểm Tâm lý thị trường (Sentiment)"""
    feeds = {
        "CoinDesk": "https://www.coindesk.com/arc/outboundfeeds/rss/",
        "CoinTelegraph": "https://cointelegraph.com/rss"
    }
    bullish_words = ['surge', 'jump', 'bull', 'high', 'gain', 'approve', 'etf', 'buy', 'rally', 'soar', 'upgrade', 'adoption', 'record']
    bearish_words = ['drop', 'crash', 'bear', 'low', 'hack', 'ban', 'sec', 'lawsuit', 'fall', 'plunge', 'dump', 'fear', 'inflation', 'cpi']
    
    news_items = []
    for source, url in feeds.items():
        try:
            parsed = feedparser.parse(url)
            for entry in parsed.entries[:8]:
                title = entry.title
                summary = entry.get('summary', '')[:200] + "..."
                text_lower = (title + " " + summary).lower()
                
                bull_score = sum(1 for w in bullish_words if w in text_lower)
                bear_score = sum(1 for w in bearish_words if w in text_lower)
                
                if bull_score > bear_score:
                    sentiment = "🟢 Tích cực (Bullish)"
                elif bear_score > bull_score:
                    sentiment = "🔴 Tiêu cực (Bearish)"
                else:
                    sentiment = "⚪ Trung lập (Neutral)"
                    
                news_items.append({
                    'source': source,
                    'title': title,
                    'link': entry.link,
                    'published': entry.get('published', 'Mới cập nhật'),
                    'sentiment': sentiment
                })
        except: continue
    return news_items

# ==========================================
# 3. THANH CÔNG CỤ BÊN TRÁI (SIDEBAR)
# ==========================================
st.sidebar.header("📥 1. Tải Dữ Liệu (Download Data)")
with st.sidebar.form("download_form"):
    sym = st.selectbox("Chọn Mã Coin:", ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'BNB/USDT', 'XRP/USDT', 'ADA/USDT'])
    tf = st.selectbox("Khung Thời Gian:", ['15m', '1h', '4h', '1d'])
    if st.form_submit_button("Tải Dữ Liệu Từ Binance"):
        table_saved, row_count = fetch_and_save_data(sym, tf, days=180)
        st.sidebar.success(f"✅ Đã lưu {row_count} dòng vào {table_saved}")
        time.sleep(1)
        st.rerun()

st.sidebar.markdown("---")
st.sidebar.header("⚙️ 2. Thiết Lập Phân Tích")
tables = get_available_tables()
if not tables:
    st.warning("👈 Hãy bấm nút 'Tải Dữ Liệu Từ Binance' ở thanh bên trái trước!")
    st.stop()

selected_table = st.sidebar.selectbox("Chọn Tài Sản Phân Tích:", tables)
window = st.sidebar.slider("Chu kỳ Z-Score (Rolling Window):", 10, 200, 50)

df = load_table_data(selected_table, window)

# ==========================================
# 4. CHIA 4 TAB CHỨC NĂNG CHÍNH TRÊN SAFARI
# ==========================================
tab1, tab2, tab3, tab4 = st.tabs([
    "📈 1. Phân Tích Kỹ Thuật & Thống Kê", 
    "🎯 2. Tư Vấn Đầu Tư (Screener)", 
    "🛡️ 3. Quản Lý Vốn & Rủi Ro", 
    "📰 4. Tin Tức Vĩ Mô & Crypto"
])

# ------------------------------------------
# TAB 1: BIỂU ĐỒ GIÁ & CHỈ SỐ THỐNG KÊ
# ------------------------------------------
with tab1:
    st.subheader(f"Góc nhìn Thống Kê: `{selected_table}`")
    current_price = df['close'].iloc[-1]
    current_z = df['z_score'].iloc[-1]
    kurt = df['log_return'].kurtosis()
    p_value = adfuller(df['close'].dropna())[1]

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Giá Hiện Tại (Price)", f"${current_price:,.4f}")
    
    z_status = "🔴 Quá Mua (Canh Short)" if current_z > 2 else "🟢 Quá Bán (Canh Long)" if current_z < -2 else "⚪ Trung Tính"
    col2.metric("Z-Score (Độ lệch chuẩn)", f"{current_z:.2f} σ", delta=z_status, delta_color="off")
    
    k_status = "⚠️ Đuôi Béo (Biến động gắt)" if kurt > 3 else "✅ Phân phối ổn định"
    col3.metric("Kurtosis (Độ Nhọn)", f"{kurt:.2f}", delta=k_status, delta_color="off")
    
    adf_status = "📉 Chuỗi Dừng (Đánh Hồi Quy)" if p_value < 0.05 else "📈 Có Xu Hướng (Đánh Theo Trend)"
    col4.metric("Kiểm định ADF (p-value)", f"{p_value:.4f}", delta=adf_status, delta_color="off")

    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.05, row_heights=[0.7, 0.3])
    fig.add_trace(go.Scatter(x=df['datetime'], y=df['close'], name='Giá Close', line=dict(color='#00F0FF', width=2)), row=1, col=1)
    fig.add_trace(go.Scatter(x=df['datetime'], y=df['rolling_mean'], name='Trung bình', line=dict(color='orange', dash='dash')), row=1, col=1)
    
    upper_band = df['rolling_mean'] + (2 * df['rolling_std'])
    lower_band = df['rolling_mean'] - (2 * df['rolling_std'])
    fig.add_trace(go.Scatter(x=df['datetime'], y=upper_band, name='Trần (+2σ)', line=dict(color='rgba(255,0,0,0.3)')), row=1, col=1)
    fig.add_trace(go.Scatter(x=df['datetime'], y=lower_band, name='Sàn (-2σ)', fill='tonexty', fillcolor='rgba(128,128,128,0.1)', line=dict(color='rgba(0,255,0,0.3)')), row=1, col=1)

    fig.add_trace(go.Scatter(x=df['datetime'], y=df['z_score'], name='Z-Score', line=dict(color='#B266FF')), row=2, col=1)
    fig.add_hline(y=2.0, line_dash="dot", line_color="red", row=2, col=1)
    fig.add_hline(y=-2.0, line_dash="dot", line_color="green", row=2, col=1)
    fig.add_hline(y=0.0, line_dash="solid", line_color="gray", row=2, col=1)
    fig.update_layout(height=600, template="plotly_dark", hovermode="x unified")
    st.plotly_chart(fig, use_container_width=True)

# ------------------------------------------
# TAB 2: TƯ VẤN ĐẦU TƯ & LỌC MÃ (SCREENER)
# ------------------------------------------
with tab2:
    st.subheader("🎯 Bảng Xếp Hạng & Khuyến Nghị Đầu Tư Tự Động")
    st.info("💡 Hệ thống tự động quét tất cả các đồng coin bạn đã tải về, kết hợp giữa điểm Z-Score và Kiểm định tính dừng (ADF) để tìm ra cơ hội có xác suất thắng cao nhất ngay lúc này.")
    
    screener_data = []
    for t in tables:
        temp_df = load_table_data(t, window)
        last_close = temp_df['close'].iloc[-1]
        last_z = temp_df['z_score'].iloc[-1]
        mean_val = temp_df['rolling_mean'].iloc[-1]
        std_val = temp_df['rolling_std'].iloc[-1]
        adf_p = adfuller(temp_df['close'].dropna())[1]
        
        # Logic chấm điểm khuyến nghị
        if last_z <= -2.0 and adf_p < 0.05:
            rec = "🔥 MUA MẠNH (Strong Long - Chuỗi dừng + Quá bán)"
        elif last_z <= -1.8:
            rec = "🟢 CANH MUA (Long - Vùng giá rẻ thống kê)"
        elif last_z >= 2.0 and adf_p < 0.05:
            rec = "🔥 BÁN KHỐNG MẠNH (Strong Short - Chuỗi dừng + Quá mua)"
        elif last_z >= 1.8:
            rec = "🔴 CANH BÁN (Short - Vùng giá đắt thống kê)"
        else:
            rec = "⚪ ĐỨNG NGOÀI (Chờ tín hiệu rõ hơn)"
            
        screener_data.append({
            "Tài sản (Khung giờ)": t,
            "Giá Hiện Tại ($)": round(last_close, 4),
            "Z-Score (σ)": round(last_z, 2),
            "ADF p-value": round(adf_p, 4),
            "Mục tiêu Chốt lời ($)": round(mean_val, 4),
            "Khuyến Nghị Từ Bot": rec
        })
        
    df_screener = pd.DataFrame(screener_data).sort_values(by="Z-Score (σ)")
    st.dataframe(df_screener, use_container_width=True, hide_index=True)

    st.subheader("🔗 Ma trận Tương Quan Đa Tài Sản (Tránh bỏ trứng vào 1 giỏ)")
    st.markdown("Nếu 2 đồng coin có hệ số tương quan **> 0.80**, bạn **chỉ nên đầu tư vào 1 trong 2 đồng** (chọn đồng có Z-Score tốt hơn ở bảng trên) để tránh việc rủi ro bị nhân đôi khi thị trường sập.")
    close_prices = pd.DataFrame()
    for t in tables:
        temp_df = load_table_data(t, window)
        close_prices[t] = temp_df.set_index('datetime')['log_return']
    fig_corr = px.imshow(close_prices.corr(), text_auto=".2f", aspect="auto", color_continuous_scale='RdBu_r', template="plotly_dark")
    st.plotly_chart(fig_corr, use_container_width=True)

# ------------------------------------------
# TAB 3: QUẢN LÝ VỐN & QUẢN TRỊ RỦI RO
# ------------------------------------------
with tab3:
    st.subheader(f"🛡️ Máy Tính Đi Vốn & Đo Lường Rủi Ro: `{selected_table}`")
    
    col_input, col_result = st.columns([1, 1.5])
    
    with col_input:
        st.markdown("#### 1. Nhập Tham Số Tài Khoản Của Bạn")
        capital = st.number_input("Tổng Vốn Hiện Có (USDT):", min_value=10.0, value=1000.0, step=100.0)
        risk_pct = st.slider("Mức Chấp Nhận Mất Tối Đa Cho 1 Lệnh (%):", min_value=0.5, max_value=5.0, value=1.5, step=0.5,
                             help="Quy tắc vàng của các quỹ định lượng: Chỉ chấp nhận mất từ 1% - 2% tổng tài khoản nếu lệnh đó chạm Cắt lỗ (Stoploss).")
        settings_df = pd.DataFrame({'capital': [capital], 'risk_pct': [risk_pct]})
        conn = sqlite3.connect(DB_NAME)
        settings_df.to_sql('user_settings', conn, if_exists='replace', index=False)
        conn.close()
        trade_dir = st.radio("Hướng Giao Dịch Dự Kiến:", ["🟢 MUA LÊN (Long)", "🔴 BÁN KHỐNG (Short)"])
        std_mult = st.slider("Khoảng cách đặt Cắt lỗ (Theo số lần Độ lệch chuẩn σ):", 0.5, 3.0, 1.0, 0.5,
                             help="Mặc định 1.0σ là khoảng cách an toàn thống kê để không bị quét râu nến oan.")

    with col_result:
        st.markdown("#### 2. Kế Hoạch Đi Tiền Tự Động (Position Sizing)")
        entry_price = df['close'].iloc[-1]
        std_val = df['rolling_std'].iloc[-1]
        mean_val = df['rolling_mean'].iloc[-1]
        
        # Tính điểm Stoploss và Take Profit
        if "Long" in trade_dir:
            sl_price = entry_price - (std_mult * std_val)
            tp_price = max(mean_val, entry_price + (1.5 * std_val))
        else:
            sl_price = entry_price + (std_mult * std_val)
            tp_price = min(mean_val, entry_price - (1.5 * std_val))
            
        # Số tiền chấp nhận mất (USD)
        risk_amount_usd = capital * (risk_pct / 100)
        # Khoảng cách giá từ Entry đến Stoploss (%)
        stop_distance_pct = abs(entry_price - sl_price) / entry_price
        
        # Khối lượng vào lệnh tối ưu (Position Size)
        position_size_usd = risk_amount_usd / stop_distance_pct if stop_distance_pct > 0 else 0
        coin_amount = position_size_usd / entry_price
        recommended_leverage = max(1.0, round(position_size_usd / capital, 1))
        
        # Tỷ lệ Lợi nhuận / Rủi ro (Risk:Reward Ratio)
        rr_ratio = abs(tp_price - entry_price) / abs(entry_price - sl_price) if abs(entry_price - sl_price) > 0 else 0

        c1, c2 = st.columns(2)
        c1.metric("Số Tiền Rủi Ro Tối Đa (Nếu chạm SL)", f"-${risk_amount_usd:,.2f}", f"Tương đương {risk_pct}% tổng vốn", delta_color="inverse")
        c2.metric("Tổng Quy Mô Lệnh Nên Vào (Position Size)", f"${position_size_usd:,.2f}", f"Mua/Bán: {coin_amount:.4f} coin", delta_color="off")
        
        c3, c4, c5 = st.columns(3)
        c3.metric("Giá Cắt Lỗ (Stop Loss)", f"${sl_price:,.4f}", f"Cách {stop_distance_pct*100:.2f}%", delta_color="off")
        c4.metric("Giá Chốt Lời (Take Profit)", f"${tp_price:,.4f}", f"Tỷ lệ R:R = 1 : {rr_ratio:.1f}", delta_color="off")
        c5.metric("Đòn Bẩy Khuyên Dùng", f"{recommended_leverage}x", "Cần cảnh giác nếu > 5x", delta_color="off")

    st.markdown("---")
    st.markdown("#### 3. Chỉ Số Rủi Ro Thống Kê Chuyên Sâu (VaR & Kelly Criterion)")
    
    # Tính Value at Risk (VaR 95%) và Expected Shortfall (CVaR)
    var_95_pct = np.percentile(df['return'], 5) # Ngưỡng 5% tệ nhất lịch sử
    cvar_95_pct = df['return'][df['return'] <= var_95_pct].mean()
    
    # Tính Kelly Criterion thực nghiệm dựa trên lịch sử Z-Score của mã này
    wins = df[df['return'] > 0]['return']
    losses = df[df['return'] < 0]['return']
    win_rate = len(wins) / len(df)
    avg_win_loss_ratio = wins.mean() / abs(losses.mean()) if len(losses) > 0 else 1
    kelly_f = win_rate - ((1 - win_rate) / avg_win_loss_ratio)
    half_kelly = max(0.0, (kelly_f / 2) * 100) # Dùng Half-Kelly để an toàn trong Crypto

    k1, k2, k3 = st.columns(3)
    k1.metric("Value at Risk (VaR 95% - 1 cây nến)", f"{var_95_pct*100:.2f}%", 
              help="Với độ tin cậy 95%, trong 1 cây nến tiếp theo bạn sẽ không lỗ vượt quá tỷ lệ phần trăm này.")
    k2.metric("Expected Shortfall (CVaR 95%)", f"{cvar_95_pct*100:.2f}%", 
              help="Nếu xui xẻo rơi vào 5% ngày thị trường sập mạnh nhất (Black Swan), mức lỗ trung bình của 1 cây nến sẽ là con số này.")
    k3.metric("Tỷ Trọng Vốn Tối Ưu (Half-Kelly)", f"{half_kelly:.1f}% vốn", 
              help="Công thức toán học của John Kelly tính toán tỷ lệ phần trăm vốn tối đa nên phân bổ dựa trên xác suất thắng lịch sử.")

# ------------------------------------------
# TAB 4: TỔNG HỢP TIN TỨC & SENTIMENT
# ------------------------------------------
with tab4:
    st.subheader("📰 Điểm Tin Tài Chính & Tâm Lý Thị Trường (Real-time RSS Feed)")
    st.info("💡 Tin tức được kéo trực tiếp từ CoinDesk và CoinTelegraph. Hệ thống tự động quét các từ khóa kinh tế (ETF, SEC, CPI, Inflation, Hack, Surge...) để đánh giá sơ bộ tác động lên giá Crypto.")
    
    news_list = fetch_crypto_news()
    if not news_list:
        st.warning("Đang không kết nối được máy chủ RSS hoặc mạng bị chặn. Hãy thử lại sau vài giây.")
    else:
        # Thống kê tổng quan tâm lý thị trường
        bull_count = sum(1 for n in news_list if "Tích cực" in n['sentiment'])
        bear_count = sum(1 for n in news_list if "Tiêu cực" in n['sentiment'])
        
        m1, m2, m3 = st.columns(3)
        m1.metric("Số Tin Tích Cực (Bullish)", f"{bull_count} bài báo")
        m2.metric("Số Tin Tiêu Cực (Bearish)", f"{bear_count} bài báo")
        overall = "🟢 NGHIÊNG VỀ TĂNG GIÁ" if bull_count > bear_count else "🔴 NGHIÊNG VỀ GIẢM GIÁ" if bear_count > bull_count else "⚪ TRUNG LẬP / GIẰNG CO"
        m3.metric("Bức Tranh Tin Tức Chung", overall)
        
        st.markdown("---")
        for item in news_list:
            st.markdown(f"""
            <div class="news-card">
                <span style="color: #00F0FF; font-weight: bold;">[{item['source']}]</span> 
                <span style="float: right; font-weight: bold;">{item['sentiment']}</span><br>
                <a href="{item['link']}" target="_blank" style="color: white; font-size: 1.15rem; text-decoration: none; font-weight: 600;">
                    {item['title']}
                </a><br>
                <small style="color: #888;">🕒 {item['published']}</small>
            </div>
            """, unsafe_allow_html=True)