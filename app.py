import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px

# 1. 页面基础设置
st.set_page_config(page_title="ASA 数据监控看板", layout="wide")
st.title("📱 ASA 每日波动分析与归因")

# 2. 上传文件模块
st.sidebar.header("数据上传")
uploaded_file = st.sidebar.file_uploader("请上传 Apple Search Ads 导出的 CSV 文件", type=['csv'])

# 辅助函数：加载数据
@st.cache_data
def load_data(file):
    try:
        # 尝试读取 CSV
        df = pd.read_csv(file)
        
        # ⚠️ 关键：统一列名处理 (如果你的CSV列名不一样，请在这里修改)
        # 假设标准列名是英文，如果是中文可以在这里重命名
        # df.rename(columns={'日期': 'Date', '广告名称': 'Campaign Name', '下载量 (经点击)': 'Installs'}, inplace=True)
        
        # 确保日期格式正确
        df['Date'] = pd.to_datetime(df['Date'])
        
        # 如果没有 CPI 列，手动计算 (Spend / Installs)
        if 'CPI' not in df.columns and 'Spend' in df.columns and 'Installs' in df.columns:
            df['CPI'] = df['Spend'] / df['Installs']
            df['CPI'] = df['CPI'].fillna(0) # 处理除以0的情况
            
        return df
    except Exception as e:
        st.error(f"数据读取失败: {e}")
        return None

if uploaded_file is not None:
    df = load_data(uploaded_file)
    
    if df is not None:
        # --- 数据预处理完成 ---

        # 3. 获取日期范围
        all_dates = df['Date'].sort_values().unique()
        if len(all_dates) < 2:
            st.warning("数据不足两天，无法进行对比分析。")
        else:
            # 默认取最近两天
            latest_date = all_dates[-1]
            prev_date = all_dates[-2]
            
            # 也可以在侧边栏让用户手动选择日期
            st.sidebar.subheader("日期对比选择")
            date1 = st.sidebar.date_input("选择主要日期 (今天/昨天)", latest_date)
            date2 = st.sidebar.date_input("选择对比日期 (昨天/前天)", prev_date)
            
            # 将用户选择转为 datetime 类型以匹配 dataframe
            date1 = pd.to_datetime(date1)
            date2 = pd.to_datetime(date2)

            # --- 核心逻辑：大盘数据对比 ---
            # 按日期汇总所有 Campaign 的数据
            daily_summary = df.groupby('Date')[['Installs', 'Spend']].sum().reset_index()
            daily_summary['CPI'] = daily_summary['Spend'] / daily_summary['Installs']
            
            # 获取两天的大盘数据
            metrics_today = daily_summary[daily_summary['Date'] == date1]
            metrics_yesterday = daily_summary[daily_summary['Date'] == date2]
            
            if not metrics_today.empty and not metrics_yesterday.empty:
                # 计算数值
                installs_now = int(metrics_today['Installs'].values[0])
                installs_prev = int(metrics_yesterday['Installs'].values[0])
                installs_diff = installs_now - installs_prev
                
                cpi_now = round(metrics_today['CPI'].values[0], 2)
                cpi_prev = round(metrics_yesterday['CPI'].values[0], 2)
                cpi_diff = round(cpi_now - cpi_prev, 2)

                # 4. 展示顶部指标卡片
                st.subheader(f"📊 大盘概览 ({date1.date()} vs {date2.date()})")
                col1, col2 = st.columns(2)
                with col1:
                    st.metric("总下载量 (Installs)", f"{installs_now}", f"{installs_diff} (波动)", delta_color="normal")
                with col2:
                    st.metric("平均 CPI", f"${cpi_now}", f"${cpi_diff}", delta_color="inverse") # CPI越低越好，所以inverse
            
            st.markdown("---")

            # 5. 核心逻辑：波动归因 (谁导致了变化？)
            st.subheader("🕵️‍♀️ 波动归因：是谁导致了下载量变化？")
            
            # 提取两天的详细数据
            detail_today = df[df['Date'] == date1].groupby('Campaign Name')[['Installs', 'Spend']].sum().reset_index()
            detail_prev = df[df['Date'] == date2].groupby('Campaign Name')[['Installs', 'Spend']].sum().reset_index()
            
            # 合并数据进行对比
            merged_df = pd.merge(detail_today, detail_prev, on='Campaign Name', suffixes=('_Now', '_Prev'), how='outer').fillna(0)
            
            # 计算差值
            merged_df['Install_Diff'] = merged_df['Installs_Now'] - merged_df['Installs_Prev']
            merged_df['Spend_Diff'] = merged_df['Spend_Now'] - merged_df['Spend_Prev']
            
            # 排序：按“下载量变化绝对值”排序，找出变化最大的前 5 名
            # 也可以改为按 Install_Diff 升序排，只看跌得最多的
            top_contributors = merged_df.reindex(merged_df['Install_Diff'].abs().sort_values(ascending=False).index).head(10)
            
            # 格式化一下表格显示
            display_cols = ['Campaign Name', 'Installs_Now', 'Installs_Prev', 'Install_Diff', 'Spend_Diff']
            
            # 使用颜色高亮：下载量跌了显示红色背景 (Styler)
            def color_negative_red(val):
                color = 'red' if val < 0 else 'green'
                return f'color: {color}'

            st.dataframe(
                top_contributors[display_cols].style.applymap(color_negative_red, subset=['Install_Diff']),
                use_container_width=True,
                column_config={
                    "Campaign Name": "广告计划名称",
                    "Installs_Now": "当前下载",
                    "Installs_Prev": "对比下载",
                    "Install_Diff": "📉 下载量波动",
                    "Spend_Diff": "花费波动"
                }
            )
            
            st.markdown("---")

            # 6. 趋势图表
            st.subheader("📈 30天趋势回顾")
            
            # 过滤最近30天
            trend_data = daily_summary[daily_summary['Date'] >= (latest_date - pd.Timedelta(days=30))]
            
            # 创建双轴图
            fig = go.Figure()

            # 左轴：下载量 (柱状图)
            fig.add_trace(go.Bar(
                x=trend_data['Date'],
                y=trend_data['Installs'],
                name='Downloads',
                marker_color='#5c6bc0',
                opacity=0.6
            ))

            # 右轴：CPI (折线图)
            fig.add_trace(go.Scatter(
                x=trend_data['Date'],
                y=trend_data['CPI'],
                name='CPI',
                yaxis='y2',
                line=dict(color='#ef5350', width=3)
            ))

            # 设置布局
            fig.update_layout(
                title="每日下载量 vs CPI 趋势",
                xaxis_title="日期",
                yaxis=dict(title="下载量 (Installs)"),
                yaxis2=dict(
                    title="CPI ($)",
                    overlaying='y',
                    side='right'
                ),
                legend=dict(x=0, y=1.1, orientation='h'),
                hovermode="x unified"
            )

            st.plotly_chart(fig, use_container_width=True)

else:
    st.info("👋 欢迎！请在左侧上传你的 ASA 数据 (CSV格式) 以开始分析。")
    st.markdown("""
    **CSV 文件建议包含以下列：**
    - `Date` (日期)
    - `Campaign Name` (广告计划名称)
    - `Installs` (下载量)
    - `Spend` (花费)
    """)