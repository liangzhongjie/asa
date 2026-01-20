import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import re

# 1. 页面基础设置
st.set_page_config(page_title="ASA 数据监控看板", layout="wide")
st.title("ASA 每日波动分析 By Alex")

# 2. 上传文件模块
st.sidebar.header("数据上传")
uploaded_file = st.sidebar.file_uploader("请上传 Apple Search Ads 导出的 Excel 或 CSV 文件", type=['xlsx', 'xls', 'csv'])

# 辅助函数：加载数据
@st.cache_data
def load_data(file):
    try:
        # 读取文件
        if file.name.endswith('.csv'):
            df = pd.read_csv(file)
        else:
            df = pd.read_excel(file)
        
        # --- 数据清洗 ---
        # 1. 去除列名前后空格
        df.columns = df.columns.str.strip()
        
        # 2. 智能找日期列
        date_col_name = None
        for col in df.columns:
            if '日期' in col or 'Date' in col or 'Day' in col:
                date_col_name = col
                break
        
        if date_col_name is None:
            st.error(f"❌ 找不到日期列！你的表头是：{list(df.columns)}")
            return None

        # 3. 转换日期
        df['Date_Cleaned'] = pd.to_datetime(df[date_col_name], errors='coerce')
        df = df.dropna(subset=['Date_Cleaned']) 
        df['Date'] = df['Date_Cleaned']

        # 4. 暴力重命名 (直接针对你截图里的列名)
        # 先定义标准映射
        rename_dict = {}
        for col in df.columns:
            # 识别 Campaign
            if col in ['广告名称', '广告系列', '广告计划', 'Campaign Name', 'Campaign']:
                rename_dict[col] = 'Campaign Name'
            
            # 识别 Installs (只要列名包含 '下载' 且不包含 '率')
            elif ('下载' in col and '率' not in col) or col in ['安装', 'Installs', 'Conversions']:
                rename_dict[col] = 'Installs'
            
            # 识别 CPI (只要列名包含 CPI 或 CPA)
            elif ('CPI' in col or 'CPA' in col) and '平均' in col: 
                rename_dict[col] = 'CPI'
            elif col in ['CPI', 'CPA', 'Avg CPA']:
                rename_dict[col] = 'CPI'
        
        # 应用重命名
        df.rename(columns=rename_dict, inplace=True)

        # 5. 检查关键列
        required_cols = ['Campaign Name', 'Installs', 'CPI']
        missing_cols = [c for c in required_cols if c not in df.columns]
        
        # 如果还是找不到，尝试更宽松的匹配（针对你截图的具体情况）
        # 如果上方逻辑没匹配到，这里手动强制指定（保底方案）
        if 'Installs' not in df.columns and '下载量 (经点击)' in df.columns:
             df.rename(columns={'下载量 (经点击)': 'Installs'}, inplace=True)
        if 'CPI' not in df.columns and '平均CPI (经点击)' in df.columns:
             df.rename(columns={'平均CPI (经点击)': 'CPI'}, inplace=True)
             
        # 再次检查
        missing_cols = [c for c in required_cols if c not in df.columns]
        if missing_cols:
            st.error(f"❌ 依然无法识别下列数据列: {missing_cols}")
            st.info(f"请检查你的表头是否包含: {required_cols}")
            st.write("当前识别到的列名:", df.columns.tolist())
            return None
            
        # 6. 数据类型转换
        for col in ['Installs', 'CPI']:
            if df[col].dtype == 'object':
                df[col] = df[col].astype(str).str.replace('$', '').str.replace(',', '')
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
            
        return df

    except Exception as e:
        st.error(f"⚠️ 数据读取失败: {e}")
        return None

if uploaded_file is not None:
    # 调试选项
    with st.expander("🔍 调试：查看原始数据 (前5行)"):
        uploaded_file.seek(0)
        if uploaded_file.name.endswith('.csv'):
            st.write(pd.read_csv(uploaded_file).head())
        else:
            st.write(pd.read_excel(uploaded_file).head())

    # 重置指针并加载
    uploaded_file.seek(0)
    df = load_data(uploaded_file)
    
    if df is not None:
        # 获取日期
        all_dates = df['Date'].sort_values().unique()
        
        if len(all_dates) < 1:
            st.warning("数据为空。")
        else:
            # 默认取最近两天
            latest_date = all_dates[-1] if len(all_dates) > 0 else None
            prev_date = all_dates[-2] if len(all_dates) > 1 else latest_date

            st.sidebar.subheader("📅 日期对比")
            date1 = st.sidebar.date_input("主要日期 (Current)", latest_date)
            date2 = st.sidebar.date_input("对比日期 (Previous)", prev_date)
            
            date1 = pd.to_datetime(date1)
            date2 = pd.to_datetime(date2)

            # --- 核心逻辑 ---
            # 聚合数据
            daily_summary = df.groupby('Date').agg({
                'Installs': 'sum',
                'CPI': 'mean' 
            }).reset_index()
            
            metrics_today = daily_summary[daily_summary['Date'] == date1]
            metrics_yesterday = daily_summary[daily_summary['Date'] == date2]
            
            installs_now, installs_diff = 0, 0
            cpi_now, cpi_diff = 0, 0

            if not metrics_today.empty:
                installs_now = int(metrics_today['Installs'].values[0])
                cpi_now = round(metrics_today['CPI'].values[0], 2)
            
            if not metrics_yesterday.empty:
                installs_prev = int(metrics_yesterday['Installs'].values[0])
                cpi_prev = round(metrics_yesterday['CPI'].values[0], 2)
                installs_diff = installs_now - installs_prev
                cpi_diff = round(cpi_now - cpi_prev, 2)

            # 顶部卡片
            st.subheader(f"📊 核心指标 ({date1.date()} vs {date2.date()})")
            col1, col2 = st.columns(2)
            with col1:
                st.metric("总下载量", f"{installs_now}", f"{installs_diff}", delta_color="normal")
            with col2:
                st.metric("平均 CPI", f"${cpi_now}", f"${cpi_diff}", delta_color="inverse")
            
            st.markdown("---")

            # 波动归因
            st.subheader("🕵️‍♀️ 波动归因：哪个计划下载量变了？")
            
            detail_today = df[df['Date'] == date1][['Campaign Name', 'Installs', 'CPI']]
            detail_prev = df[df['Date'] == date2][['Campaign Name', 'Installs', 'CPI']]
            
            merged_df = pd.merge(detail_today, detail_prev, on='Campaign Name', suffixes=('_Now', '_Prev'), how='outer').fillna(0)
            
            merged_df['Install_Diff'] = merged_df['Installs_Now'] - merged_df['Installs_Prev']
            merged_df['CPI_Diff'] = merged_df['CPI_Now'] - merged_df['CPI_Prev']
            
            # 按下载量波动绝对值排序
            top_contributors = merged_df.reindex(merged_df['Install_Diff'].abs().sort_values(ascending=False).index).head(10)
            
            def color_diff(val):
                color = 'red' if val < 0 else 'green'
                return f'color: {color}'

            st.dataframe(
                top_contributors[['Campaign Name', 'Installs_Now', 'Installs_Prev', 'Install_Diff', 'CPI_Now', 'CPI_Diff']].style.applymap(color_diff, subset=['Install_Diff', 'CPI_Diff']),
                use_container_width=True,
                column_config={
                    "Campaign Name": "广告计划",
                    "Installs_Now": "当前下载",
                    "Installs_Prev": "对比下载",
                    "Install_Diff": "📉 下载波动",
                    "CPI_Now": "当前CPI",
                    "CPI_Diff": "CPI波动"
                }
            )
            
            # 趋势图
            st.subheader("📈 趋势回顾")
            fig = go.Figure()
            trend_data = daily_summary.sort_values('Date')
            
            fig.add_trace(go.Bar(x=trend_data['Date'], y=trend_data['Installs'], name='Downloads', marker_color='#5c6bc0'))
            fig.add_trace(go.Scatter(x=trend_data['Date'], y=trend_data['CPI'], name='CPI', yaxis='y2', line=dict(color='#ef5350')))
            
            fig.update_layout(
                yaxis=dict(title="Downloads"),
                yaxis2=dict(title="CPI", overlaying='y', side='right'),
                hovermode="x unified",
                legend=dict(orientation="h", y=1.1)
            )
            st.plotly_chart(fig, use_container_width=True)

else:
    st.info("👋 请上传数据文件 (Excel 或 CSV)。")
