import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import re

# 1. 页面配置
st.set_page_config(page_title="ASA 原始数据看板", layout="wide")
st.title("📱 ASA 原始数据分析 (精准花费版)")

# 2. 侧边栏上传
st.sidebar.header("数据源")
uploaded_file = st.sidebar.file_uploader("请上传 ASA 导出的原始 CSV 或 Excel 文件", type=['csv', 'xlsx', 'xls'])

# --- 核心数据处理函数 ---
@st.cache_data
def load_and_clean_data(file):
    try:
        df = None
        
        # === 阶段 1: 暴力读取 ===
        if file.name.endswith('.csv'):
            try:
                df = pd.read_csv(file, encoding='utf-8', on_bad_lines='skip')
            except:
                file.seek(0)
                try:
                    df = pd.read_csv(file, encoding='gbk', on_bad_lines='skip')
                except Exception as e:
                    st.error(f"❌ CSV 读取失败: {e}")
                    return None
        else:
            df = pd.read_excel(file)

        # === 阶段 2: 智能寻找表头 ===
        header_idx = -1
        for i, row in df.head(20).iterrows():
            row_str = " ".join(row.astype(str).values)
            if "广告" in row_str or "Campaign" in row_str or "日期" in row_str or "Date" in row_str:
                header_idx = i
                break
        
        if header_idx != -1 and header_idx > 0:
            file.seek(0)
            if file.name.endswith('.csv'):
                try:
                    df = pd.read_csv(file, header=header_idx+1, encoding='utf-8', on_bad_lines='skip')
                except:
                    file.seek(0)
                    df = pd.read_csv(file, header=header_idx+1, encoding='gbk', on_bad_lines='skip')
            else:
                df = pd.read_excel(file, header=header_idx+1)

        # === 阶段 3: 列名清洗与精准映射 ===
        df.columns = df.columns.str.strip()
        
        col_map = {}
        for col in df.columns:
            # 1. 日期
            if any(x in col for x in ['日期', 'Date', 'Day']):
                col_map[col] = 'Date'
            
            # 2. 广告名称
            elif any(x in col for x in ['广告名称', 'Campaign', '广告计划']):
                col_map[col] = 'Campaign Name'
            
            # 3. 下载量 (排除转化率等)
            elif ('下载' in col and '率' not in col) or 'Installs' in col or 'Conversions' in col:
                col_map[col] = 'Installs'
            
            # 4. 花费 (★★★ 关键修复 ★★★)
            # 逻辑：必须包含“花费”或“Spend”
            # 且：不能包含“每日”、“Budget” (排除预算列)
            elif any(x in col for x in ['花费', 'Spend', 'Cost']):
                if '每日' in col or 'Budget' in col:
                    continue # 跳过“每日花费”这一列
                col_map[col] = 'Spend'

        df.rename(columns=col_map, inplace=True)

        # 去除重复列 (防止有多个列被识别为 Installs 或 Spend)
        df = df.loc[:, ~df.columns.duplicated()]

        # 检查
        required = ['Date', 'Campaign Name', 'Installs', 'Spend']
        missing = [c for c in required if c not in df.columns]
        if missing:
            st.error(f"❌ 缺少关键列: {missing}。请检查表头是否包含‘花费’且不含‘每日’。")
            st.write("识别到的列名:", df.columns.tolist())
            return None

        # === 阶段 4: 数据类型清洗 ===
        df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
        df = df.dropna(subset=['Date'])
        
        def clean_num(x):
            if isinstance(x, str):
                return x.replace('$', '').replace('¥', '').replace(',', '').replace(' ', '')
            return x

        for col in ['Installs', 'Spend']:
            df[col] = df[col].apply(clean_num).apply(pd.to_numeric, errors='coerce').fillna(0)

        # === 阶段 5: 提取国家 ===
        def extract_country(name):
            if not isinstance(name, str): return "Unknown"
            parts = re.split(r'[_ -]', name)
            if parts and len(parts[0]) == 2:
                return parts[0].upper()
            return name[:2].upper()
            
        df['Country'] = df['Campaign Name'].apply(extract_country)

        return df

    except Exception as e:
        st.error(f"⚠️ 严重错误: {e}")
        return None

if uploaded_file:
    df = load_and_clean_data(uploaded_file)
    
    if df is not None:
        all_dates = df['Date'].sort_values().unique()
        
        if len(all_dates) == 0:
            st.error("数据为空")
        else:
            # 侧边栏
            st.sidebar.markdown("---")
            st.sidebar.subheader("📅 日期对比")
            latest = all_dates[-1]
            prev = all_dates[-2] if len(all_dates) > 1 else latest
            
            date1 = st.sidebar.date_input("主要日期", latest, min_value=all_dates[0], max_value=all_dates[-1])
            date2 = st.sidebar.date_input("对比日期", prev, min_value=all_dates[0], max_value=all_dates[-1])
            date1 = pd.to_datetime(date1)
            date2 = pd.to_datetime(date2)

            # --- 计算函数 ---
            def get_daily_stats(data, target_date):
                day_data = data[data['Date'] == target_date]
                total_installs = float(day_data['Installs'].sum())
                total_spend = float(day_data['Spend'].sum()) # 现在这里的 Spend 是真实的“花费”列
                cpi = total_spend / total_installs if total_installs > 0 else 0.0
                return int(total_installs), total_spend, cpi

            i1, s1, cpi1 = get_daily_stats(df, date1)
            i2, s2, cpi2 = get_daily_stats(df, date2)

            # --- 页面展示 ---
            st.subheader(f"📊 核心数据 ({date1.date()} vs {date2.date()})")
            c1, c2, c3 = st.columns(3)
            c1.metric("总下载量 (经点击)", f"{i1:,}", f"{i1-i2:+}", delta_color="normal")
            c2.metric("综合 CPI (总花费/总下载)", f"${cpi1:.2f}", f"${cpi1-cpi2:+.2f}", delta_color="inverse")
            c3.metric("总花费 (实际消耗)", f"${s1:,.2f}", f"${s1-s2:+,.2f}", delta_color="inverse")
            
            st.markdown("---")

            # --- 波动归因 ---
            st.subheader("🕵️‍♀️ 波动归因 (Top 10)")
            d1 = df[df['Date'] == date1].groupby('Campaign Name')[['Installs', 'Spend']].sum().reset_index()
            d2 = df[df['Date'] == date2].groupby('Campaign Name')[['Installs', 'Spend']].sum().reset_index()
            
            m = pd.merge(d1, d2, on='Campaign Name', suffixes=('_Now', '_Prev'), how='outer').fillna(0)
            m['Diff'] = m['Installs_Now'] - m['Installs_Prev']
            
            # 这里的 CPI 也是基于正确花费计算的
            m['CPI_Now'] = m.apply(lambda x: x['Spend_Now']/x['Installs_Now'] if x['Installs_Now']>0 else 0, axis=1)
            
            top = m.reindex(m['Diff'].abs().sort_values(ascending=False).index).head(10)
            
            st.dataframe(
                top[['Campaign Name', 'Installs_Now', 'Installs_Prev', 'Diff', 'CPI_Now']].style.format({'CPI_Now':"{:.2f}"}).applymap(lambda v: f'color: {"red" if v<0 else "green"}', subset=['Diff']),
                use_container_width=True,
                column_config={"Diff": "📉 波动值"}
            )

            # --- 趋势图 ---
            st.markdown("---")
            st.subheader("📈 趋势分析")
            tab1, tab2 = st.tabs(["🌍 分国家下载趋势", "💰 每日综合 CPI"])
            
            with tab1:
                country_trend = df.groupby(['Date', 'Country'])['Installs'].sum().reset_index()
                fig1 = px.bar(country_trend, x='Date', y='Installs', color='Country', title="每日下载量 (分国家堆叠)")
                st.plotly_chart(fig1, use_container_width=True)
                
            with tab2:
                daily = df.groupby('Date').apply(lambda x: pd.Series({
                    'Installs': x['Installs'].sum(), 
                    'Spend': x['Spend'].sum()
                })).reset_index()
                daily['CPI'] = daily.apply(lambda x: x['Spend']/x['Installs'] if x['Installs']>0 else 0, axis=1)
                
                fig2 = go.Figure()
                fig2.add_trace(go.Scatter(x=daily['Date'], y=daily['CPI'], mode='lines+markers', line=dict(color='orange', width=3)))
                fig2.update_layout(title="每日综合 CPI 趋势", yaxis_title="CPI ($)")
                st.plotly_chart(fig2, use_container_width=True)
else:
    st.info("👋 请上传数据文件")
