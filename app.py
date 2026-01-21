import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import re

# 1. 页面配置
st.set_page_config(page_title="ASA 原始数据看板", layout="wide")
st.title("📱 ASA 原始数据分析 (高亮表格版)")

# 注入 CSS
st.markdown("""
<style>
    .table-container {
        width: 100%;
        display: flex;
        justify-content: center;
        padding: 10px;
    }
    .styled-table {
        border-collapse: collapse;
        margin: 25px 0;
        font-size: 0.9em;
        font-family: sans-serif;
        width: 100%;
        box-shadow: 0 0 20px rgba(0, 0, 0, 0.15);
        border-radius: 10px;
        overflow: hidden;
        /* ★★★ 关键修改：强制白色背景，与深色界面形成反差 ★★★ */
        background-color: #ffffff; 
    }
    .styled-table thead tr {
        background-color: #009879; /*以此改为显眼的绿色表头，或保持浅灰 #f0f2f6 */
        background-color: #f0f2f6; 
        color: #333333;
        text-align: center;
        font-weight: bold;
        border-bottom: 2px solid #dddddd;
    }
    .styled-table th, .styled-table td {
        padding: 12px 15px;
        text-align: center;
        border-bottom: 1px solid #eeeeee;
        /* ★★★ 强制深色文字，防止在深色模式下变白看不清 ★★★ */
        color: #333333; 
    }
    /* 偶数行颜色 */
    .styled-table tbody tr:nth-of-type(even) {
        background-color: #f3f3f3;
    }
    /* 奇数行颜色 (显式设置，防止透明) */
    .styled-table tbody tr:nth-of-type(odd) {
        background-color: #ffffff;
    }
    
    .styled-table tbody tr:last-of-type {
        border-bottom: 2px solid #009879;
    }
    
    /* 涨跌颜色 */
    .trend-up {
        color: #d62728;
        font-weight: bold;
        background-color: rgba(214, 39, 40, 0.1);
        border-radius: 4px;
        padding: 2px 6px;
    }
    .trend-down {
        color: #2ca02c;
        font-weight: bold;
        background-color: rgba(44, 160, 44, 0.1);
        border-radius: 4px;
        padding: 2px 6px;
    }
    .trend-flat {
        color: #999;
    }
</style>
""", unsafe_allow_html=True)

# 2. 侧边栏
st.sidebar.header("数据源")
uploaded_file = st.sidebar.file_uploader("请上传 ASA 导出的原始 CSV 或 Excel 文件", type=['csv', 'xlsx', 'xls'])

# --- 核心处理 ---
@st.cache_data
def load_and_clean_data(file):
    try:
        df = None
        if file.name.endswith('.csv'):
            try:
                df = pd.read_csv(file, encoding='utf-8', on_bad_lines='skip')
            except:
                file.seek(0)
                try:
                    df = pd.read_csv(file, encoding='gbk', on_bad_lines='skip')
                except Exception:
                    return None
        else:
            df = pd.read_excel(file)

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

        df.columns = df.columns.str.strip()
        
        def find_best_column(columns, keywords, blacklist=[]):
            candidates = []
            for col in columns:
                if any(k in col for k in keywords):
                    if not any(b in col for b in blacklist):
                        candidates.append(col)
            if not candidates: return None
            for col in candidates:
                if col in keywords: return col
            candidates.sort(key=len)
            return candidates[0]

        date_col = find_best_column(df.columns, ['日期', 'Date', 'Day'])
        camp_col = find_best_column(df.columns, ['广告名称', 'Campaign Name', 'Campaign', '广告计划'])
        install_col = find_best_column(df.columns, ['下载量 (经点击)', 'Installs', 'Downloads', '安装', '下载'], blacklist=['率', 'Rate', '转化', 'Cost', 'CPI'])
        spend_col = find_best_column(df.columns, ['花费', 'Spend', 'Cost'], blacklist=['每日', 'Budget', 'avg', 'Local', 'Avg', 'CPM', 'CPT', 'CPA'])

        col_map = {}
        if date_col: col_map[date_col] = 'Date'
        if camp_col: col_map[camp_col] = 'Campaign Name'
        if install_col: col_map[install_col] = 'Installs'
        if spend_col: col_map[spend_col] = 'Spend'
        
        df.rename(columns=col_map, inplace=True)
        df = df.loc[:, ~df.columns.duplicated()]
        
        required = ['Date', 'Campaign Name', 'Installs', 'Spend']
        if any(c not in df.columns for c in required): return None

        df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
        df = df.dropna(subset=['Date'])
        
        def clean_num(x):
            if isinstance(x, str):
                return x.replace('$', '').replace('¥', '').replace(',', '').replace(' ', '')
            return x

        for col in ['Installs', 'Spend']:
            df[col] = df[col].apply(clean_num).apply(pd.to_numeric, errors='coerce').fillna(0)

        def extract_country(name):
            if not isinstance(name, str): return "Unknown"
            parts = re.split(r'[_ -]', name)
            if parts and len(parts[0]) == 2:
                return parts[0].upper()
            return name[:2].upper()
            
        df['Country'] = df['Campaign Name'].apply(extract_country)
        return df
    except Exception:
        return None

if uploaded_file:
    df = load_and_clean_data(uploaded_file)
    
    if df is not None:
        all_dates = df['Date'].sort_values().unique()
        
        if len(all_dates) == 0:
            st.error("数据为空")
        else:
            st.sidebar.markdown("---")
            st.sidebar.subheader("📅 日期对比")
            latest = all_dates[-1]
            prev = all_dates[-2] if len(all_dates) > 1 else latest
            
            date1 = st.sidebar.date_input("主要日期", latest, min_value=all_dates[0], max_value=all_dates[-1])
            date2 = st.sidebar.date_input("对比日期", prev, min_value=all_dates[0], max_value=all_dates[-1])
            date1 = pd.to_datetime(date1)
            date2 = pd.to_datetime(date2)

            def get_daily_stats(data, target_date):
                day_data = data[data['Date'] == target_date]
                total_installs = float(day_data['Installs'].sum())
                total_spend = float(day_data['Spend'].sum())
                cpi = total_spend / total_installs if total_installs > 0 else 0.0
                return int(total_installs), total_spend, cpi

            i1, s1, cpi1 = get_daily_stats(df, date1)
            i2, s2, cpi2 = get_daily_stats(df, date2)

            # --- 顶部卡片 ---
            st.subheader(f"📊 核心数据 ({date1.date()} vs {date2.date()})")
            c1, c2, c3 = st.columns(3)
            
            def show_metric(label, current, diff, is_currency=False):
                prefix = "$" if is_currency else ""
                diff_val = float(diff)
                st.metric(label, f"{prefix}{current:,.2f}" if is_currency else f"{current:,}", f"{prefix}{diff_val:+,.2f}" if is_currency else f"{diff_val:+,.0f}", delta_color="inverse")

            with c1: show_metric("总下载量", i1, i1-i2, False)
            with c2: show_metric("综合 CPI", cpi1, cpi1-cpi2, True)
            with c3: show_metric("总花费", s1, s1-s2, True)
            
            st.markdown("---")

            # --- 波动归因 ---
            st.subheader("🕵️‍♀️ 波动归因 (Top 10)")
            
            d1 = df[df['Date'] == date1].groupby('Campaign Name')[['Installs', 'Spend']].sum().reset_index()
            d2 = df[df['Date'] == date2].groupby('Campaign Name')[['Installs', 'Spend']].sum().reset_index()
            
            m = pd.merge(d1, d2, on='Campaign Name', suffixes=('_Now', '_Prev'), how='outer').fillna(0)
            m['Diff'] = m['Installs_Now'] - m['Installs_Prev']
            m['CPI_Now'] = m.apply(lambda x: x['Spend_Now']/x['Installs_Now'] if x['Installs_Now']>0 else 0, axis=1)
            
            top = m.reindex(m['Diff'].abs().sort_values(ascending=False).index).head(10)
            
            # 严格无缩进 HTML 生成
            table_rows = ""
            for _, row in top.iterrows():
                diff = row['Diff']
                if diff > 0:
                    span_class = "trend-up"
                    diff_text = f"▲ +{diff:,.0f}"
                elif diff < 0:
                    span_class = "trend-down"
                    diff_text = f"▼ {diff:,.0f}"
                else:
                    span_class = "trend-flat"
                    diff_text = "-"
                
                # 无缩进拼接
                row_html = f"<tr><td style='text-align:left!important;padding-left:20px;font-weight:500;'>{row['Campaign Name']}</td><td>{row['Installs_Now']:,.0f}</td><td>{row['Installs_Prev']:,.0f}</td><td><span class='{span_class}'>{diff_text}</span></td><td>${row['CPI_Now']:.2f}</td></tr>"
                table_rows += row_html

            html_content = f"""
<div class="table-container">
<table class="styled-table">
<thead>
<tr>
<th style="width:30%;">广告计划</th>
<th style="width:15%;">当前下载</th>
<th style="width:15%;">对比下载</th>
<th style="width:20%;">📉 波动值</th>
<th style="width:20%;">当前 CPI</th>
</tr>
</thead>
<tbody>
{table_rows}
</tbody>
</table>
</div>
"""
            st.markdown(html_content, unsafe_allow_html=True)

            # --- 趋势图 ---
            st.markdown("---")
            st.subheader("📈 趋势分析")
            tab1, tab2 = st.tabs(["🌍 分国家下载趋势", "💰 每日综合 CPI"])
            
            with tab1:
                country_trend = df.groupby(['Date', 'Country'])['Installs'].sum().reset_index()
                fig1 = px.bar(country_trend, x='Date', y='Installs', color='Country', title="每日下载量 (分国家)", text_auto=True)
                fig1.update_traces(textfont_size=12, textangle=0, textposition="inside", cliponaxis=False)
                fig1.update_layout(uniformtext_minsize=8, uniformtext_mode='hide')
                st.plotly_chart(fig1, use_container_width=True)
                
            with tab2:
                daily = df.groupby('Date').apply(lambda x: pd.Series({'Installs': x['Installs'].sum(), 'Spend': x['Spend'].sum()})).reset_index()
                daily['CPI'] = daily.apply(lambda x: x['Spend']/x['Installs'] if x['Installs']>0 else 0, axis=1)
                
                fig2 = go.Figure()
                fig2.add_trace(go.Scatter(
                    x=daily['Date'], y=daily['CPI'], 
                    mode='lines+markers+text',
                    text=[f"${x:.2f}" for x in daily['CPI']], 
                    textposition="top center",
                    textfont=dict(size=12, color="black"),
                    line=dict(color='#ffa726', width=3),
                    name='CPI'
                ))
                fig2.update_layout(title="每日综合 CPI 趋势", yaxis_title="CPI ($)", yaxis=dict(tickformat=".2f"), margin=dict(t=50))
                st.plotly_chart(fig2, use_container_width=True)
else:
    st.info("👋 请上传数据文件")
