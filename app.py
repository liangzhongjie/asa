import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import re

# 1. 页面配置
st.set_page_config(page_title="ASA 原始数据高级看板", layout="wide")
st.title("📱 ASA 原始数据分析 (自动清洗版)")

# 2. 侧边栏上传
st.sidebar.header("数据源")
uploaded_file = st.sidebar.file_uploader("请上传 ASA 导出的原始 CSV 或 Excel 文件", type=['csv', 'xlsx', 'xls'])

# --- 核心数据处理函数 ---
@st.cache_data
def load_and_clean_data(file):
    try:
        # A. 读取文件 (兼容 CSV 和 Excel)
        if file.name.endswith('.csv'):
            # 原始文件通常很大，且可能有元数据，先尝试直接读
            df = pd.read_csv(file)
        else:
            df = pd.read_excel(file)
        
        # B. 智能定位表头
        # 很多原始报表第一行不是表头，我们要找到包含 "广告名称" 的那一行
        header_row_index = None
        for i, row in df.head(10).iterrows():
            # 转换为字符串查找
            row_str = " ".join(row.astype(str).values)
            if "广告名称" in row_str or "Campaign Name" in row_str:
                header_row_index = i
                break
        
        # 如果找到了非第一行的表头，重新读取
        if header_row_index is not None and header_row_index > 0:
            if file.name.endswith('.csv'):
                file.seek(0)
                df = pd.read_csv(file, header=header_row_index)
            else:
                file.seek(0)
                df = pd.read_excel(file, header=header_row_index)
        
        # C. 列名清洗 (去空格)
        df.columns = df.columns.str.strip()
        
        # D. 关键列名标准化 (建立映射关系)
        # 我们需要：日期, 广告名称, 下载量, 花费
        col_map = {}
        for col in df.columns:
            if col in ['日期', 'Date', 'Day']:
                col_map[col] = 'Date'
            elif col in ['广告名称', 'Campaign Name', 'Campaign']:
                col_map[col] = 'Campaign Name'
            elif '下载量 (经点击)' in col or 'Installs' in col: # 优先匹配用户指定的列名
                col_map[col] = 'Installs'
            elif col in ['花费', 'Spend', 'Cost']:
                col_map[col] = 'Spend'
        
        df.rename(columns=col_map, inplace=True)
        
        # 检查关键列是否存在
        required_cols = ['Date', 'Campaign Name', 'Installs', 'Spend']
        missing = [c for c in required_cols if c not in df.columns]
        if missing:
            st.error(f"❌ 缺少关键列: {missing}。请检查源文件表头。")
            st.write("当前识别到的列:", df.columns.tolist())
            return None

        # E. 数据类型转换
        # 1. 日期转换
        df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
        df = df.dropna(subset=['Date']) # 删除汇总行

        # 2. 数值转换 (处理 '1,000', '$50.00' 这种格式)
        def clean_currency(x):
            if isinstance(x, str):
                return x.replace('$', '').replace(',', '').replace('¥', '').replace(' ', '')
            return x

        df['Installs'] = df['Installs'].apply(clean_currency).apply(pd.to_numeric, errors='coerce').fillna(0)
        df['Spend'] = df['Spend'].apply(clean_currency).apply(pd.to_numeric, errors='coerce').fillna(0)

        # F. 高级功能：提取国家 (从广告名称)
        # 假设命名规范为：US_Search, UK-Brand 等，提取前两个字母作为国家
        # 如果没有分隔符，默认取前2位
        def extract_country(campaign_name):
            if not isinstance(campaign_name, str):
                return "Unknown"
            # 常见分隔符处理
            parts = re.split(r'[_ -]', campaign_name)
            if parts and len(parts[0]) == 2: # 如果第一部分是2个字母 (US, UK, DE)
                return parts[0].upper()
            return campaign_name[:2].upper() # 兜底逻辑

        df['Country'] = df['Campaign Name'].apply(extract_country)

        return df

    except Exception as e:
        st.error(f"⚠️ 数据处理出错: {e}")
        return None

if uploaded_file:
    df = load_and_clean_data(uploaded_file)
    
    if df is not None:
        # 获取所有日期
        all_dates = df['Date'].sort_values().unique()
        min_date = all_dates[0]
        max_date = all_dates[-1]

        # ==========================================
        # 模块 1: 任意两天对比 (核心需求 1 & 2)
        # ==========================================
        st.sidebar.markdown("---")
        st.sidebar.subheader("📅 日期对比设置")
        
        # 默认对比最近两天
        default_date_now = max_date
        default_date_prev = all_dates[-2] if len(all_dates) > 1 else min_date

        date_now = st.sidebar.date_input("选择主要日期", default_date_now, min_value=min_date, max_value=max_date)
        date_prev = st.sidebar.date_input("选择对比日期", default_date_prev, min_value=min_date, max_value=max_date)
        
        date_now = pd.to_datetime(date_now)
        date_prev = pd.to_datetime(date_prev)

        # 计算两天的大盘数据
        # 逻辑：先筛选日期，再求和，最后算 CPI = 总花费 / 总下载
        def get_daily_stats(data, target_date):
            day_data = data[data['Date'] == target_date]
            total_installs = day_data['Installs'].sum()
            total_spend = day_data['Spend'].sum()
            # 避免除以 0
            cpi = total_spend / total_installs if total_installs > 0 else 0
            return int(total_installs), total_spend, cpi

        installs_now, spend_now, cpi_now = get_daily_stats(df, date_now)
        installs_prev, spend_prev, cpi_prev = get_daily_stats(df, date_prev)

        # 计算差值
        diff_installs = installs_now - installs_prev
        diff_cpi = cpi_now - cpi_prev

        # 展示指标卡片
        st.subheader(f"📊 大盘对比: {date_now.date()} vs {date_prev.date()}")
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("总下载量 (经点击)", f"{installs_now:,}", f"{diff_installs:+}", delta_color="normal")
        with col2:
            st.metric("综合 CPI (总花费/总下载)", f"${cpi_now:.2f}", f"${diff_cpi:+.2f}", delta_color="inverse")
        with col3:
            st.metric("总花费", f"${spend_now:,.2f}", f"${spend_now - spend_prev:+,.2f}", delta_color="inverse")

        st.markdown("---")

        # ==========================================
        # 模块 2: 波动归因 (Top Campaign 变化)
        # ==========================================
        st.subheader("🕵️‍♀️ 波动归因：哪些广告计划变动最大？")
        
        # 准备两天的详细数据
        df_now_detail = df[df['Date'] == date_now].groupby('Campaign Name')[['Installs', 'Spend']].sum().reset_index()
        df_prev_detail = df[df['Date'] == date_prev].groupby('Campaign Name')[['Installs', 'Spend']].sum().reset_index()
        
        # 合并
        merged = pd.merge(df_now_detail, df_prev_detail, on='Campaign Name', suffixes=('_Now', '_Prev'), how='outer').fillna(0)
        
        # 计算每个计划的波动
        merged['Install_Diff'] = merged['Installs_Now'] - merged['Installs_Prev']
        
        # 筛选：按下载量变化绝对值排序，取前 10
        top_changes = merged.reindex(merged['Install_Diff'].abs().sort_values(ascending=False).index).head(10)
        
        # 计算单计划 CPI 用于展示 (可选)
        top_changes['CPI_Now'] = top_changes.apply(lambda x: x['Spend_Now'] / x['Installs_Now'] if x['Installs_Now'] > 0 else 0, axis=1)

        # 样式函数
        def color_diff(val):
            return f'color: {"red" if val < 0 else "green"}'

        st.dataframe(
            top_changes[['Campaign Name', 'Installs_Now', 'Installs_Prev', 'Install_Diff', 'CPI_Now']].style.format({'CPI_Now': "{:.2f}"}).applymap(color_diff, subset=['Install_Diff']),
            use_container_width=True,
            column_config={
                "Campaign Name": "广告计划",
                "Installs_Now": "当前下载",
                "Installs_Prev": "对比下载",
                "Install_Diff": "📉 波动值",
                "CPI_Now": "当前CPI ($)"
            }
        )

        st.markdown("---")

        # ==========================================
        # 模块 3: 趋势图 (核心需求 3 - 按国家)
        # ==========================================
        st.subheader("📈 趋势分析")

        tab1, tab2 = st.tabs(["🌍 按国家下载趋势", "💰 每日综合 CPI 趋势"])

        with tab1:
            # 数据准备：按 日期 + 国家 汇总下载量
            country_trend = df.groupby(['Date', 'Country'])['Installs'].sum().reset_index()
            
            # 绘制堆叠柱状图 (或者多折线图)
            fig_country = px.bar(
                country_trend, 
                x="Date", 
                y="Installs", 
                color="Country", 
                title="每日下载量分布 (按国家)",
                text_auto=True
            )
            fig_country.update_layout(hovermode="x unified")
            st.plotly_chart(fig_country, use_container_width=True)
            
            st.info("💡 国家代码是根据‘广告名称’的前两个字符自动提取的 (例如 'US_Search' -> 'US')。如果你的命名规则不同，请统一广告命名。")

        with tab2:
            # 数据准备：每日大盘 CPI
            daily_stats = df.groupby('Date').apply(
                lambda x: pd.Series({
                    'Total_Spend': x['Spend'].sum(),
                    'Total_Installs': x['Installs'].sum()
                })
            ).reset_index()
            
            # 计算每日 CPI
            daily_stats['Daily_CPI'] = daily_stats['Total_Spend'] / daily_stats['Total_Installs']
            
            fig_cpi = go.Figure()
            fig_cpi.add_trace(go.Scatter(
                x=daily_stats['Date'], 
                y=daily_stats['Daily_CPI'],
                mode='lines+markers',
                name='CPI',
                line=dict(color='#ff5722', width=3)
            ))
            fig_cpi.update_layout(title="每日综合 CPI 走势 (总花费/总下载)", yaxis_title="CPI ($)", hovermode="x unified")
            st.plotly_chart(fig_cpi, use_container_width=True)

else:
    st.info("👋 请上传源文件 (CSV/Excel)。")
