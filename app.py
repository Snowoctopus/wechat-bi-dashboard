import streamlit as st
import requests
import pandas as pd
from openai import OpenAI

# 1. 页面基本设置
st.set_page_config(page_title="WeChat Intelligence", page_icon="📡", layout="wide")

# --- 核心配置区（请将这三行替换为你自己的真实数据！） ---
NOTION_TOKEN = st.secrets["NOTION_TOKEN"]
DATABASE_ID = st.secrets["DATABASE_ID"]
OPENAI_API_KEY = st.secrets["OPENAI_API_KEY"]

# 2. 从 Notion 获取数据的魔法函数
@st.cache_data(ttl=600) 
def get_notion_data():
    url = f"https://api.notion.com/v1/databases/{DATABASE_ID}/query"
    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json"
    }
    response = requests.post(url, headers=headers)
    
    if response.status_code != 200:
        st.error("连接 Notion 失败！请检查 Token 和 数据库 ID。")
        return pd.DataFrame()
        
    data = response.json()
    results = []
    for item in data.get("results", []):
        props = item["properties"]
        try:
            title = props["标题"]["title"][0]["plain_text"] if props["标题"]["title"] else "无标题"
            url = props["url"]["rich_text"][0]["plain_text"] if props["url"]["rich_text"] else ""
            time = props["时间"]["date"]["start"] if props["时间"]["date"] else ""
            source = props["来源"]["rich_text"][0]["plain_text"] if props["来源"]["rich_text"] else "未知来源"
            source = source.replace("=", "") # 去掉难看的等号
            st.write(f"正在读取来源: '{source}'")
            
            results.append({
                "发布时间": time,
                "竞品来源": source,
                "文章标题": title,
                "直达链接": url
            })
        except Exception as e:
            continue
            
    df = pd.DataFrame(results)
    if not df.empty:
        # 将时间字符串转换为真正的时间对象，并去除时区以便于计算
        df["发布时间"] = pd.to_datetime(df["发布时间"]).dt.tz_localize(None)
        df = df.sort_values(by="发布时间", ascending=False)
    return df

df = get_notion_data()

# 3. 左侧边栏 (完美复刻原型设计)
with st.sidebar:
    st.title("📡 WeChat BI")
    st.markdown("### COMPANIES")
    
    if not df.empty:
        companies = df["竞品来源"].unique().tolist()
        companies.insert(0, "全部")
        selected_company = st.radio("选择竞品", companies)
    else:
        selected_company = st.radio("选择竞品", ["暂无数据"])
    
    st.divider()
    
    st.markdown("### TIME RANGE")
    time_range = st.radio("时间范围", ["Last 7 days", "Last 14 days", "Last 30 days"])

# 4. 动态数据过滤逻辑
filtered_df = df.copy()

if not filtered_df.empty:
    # A. 按照公司过滤
    if selected_company != "全部":
        filtered_df = filtered_df[filtered_df["竞品来源"] == selected_company]
    
    # B. 按照时间过滤
    now = pd.Timestamp.now()
    if time_range == "Last 7 days":
        cutoff = now - pd.Timedelta(days=7)
    elif time_range == "Last 14 days":
        cutoff = now - pd.Timedelta(days=14)
    else:
        cutoff = now - pd.Timedelta(days=30)
        
    filtered_df = filtered_df[filtered_df["发布时间"] >= cutoff]

# 5. 右侧主页面区
st.title(f"{selected_company} 动态追踪面板" if selected_company != "全部" else "全行业动态追踪面板")

# 6. 数据卡片区
col1, col2, col3 = st.columns(3)

# 动态计算经过的天数
if time_range == "Last 7 days":
    days = 7
elif time_range == "Last 14 days":
    days = 14
else:
    days = 30

# 计算每周平均发文量 (保留1位小数)
avg_per_week = len(filtered_df) / (days / 7) if days > 0 else 0

col1.metric(label="Posts in period", value=f"{len(filtered_df)} 篇")
col2.metric(label="Avg / week", value=f"{avg_per_week:.1f} 篇") 
col3.metric(label="Total likes", value="--") # 这个依然需要等后端数据

st.divider()

# 7. ✨ 核心功能：动态 AI 总结区 ✨
st.subheader("🔴 AI-GENERATED SUMMARY")

# 为什么用按钮？为了省钱！避免用户每次点左边栏都自动调用消耗 Token
if st.button(f"生成 {selected_company} ({time_range}) 动态总结"):
    if filtered_df.empty:
        st.warning(f"在 {time_range} 内没有找到 {selected_company} 的文章数据哦。")
    else:
        with st.spinner("AI 正在深度阅读并思考中，请稍候..."):
            try:
                # 组装发给 AI 的语料
                articles_text = "\n".join(filtered_df["文章标题"].tolist())
                prompt = f"""
                你是一个资深的商业情报分析师。请根据以下 {selected_company} 在 {time_range} 内发布的微信公众号文章标题，
                提炼出其近期的核心营销动作、产品发布动态以及对外传达的战略意图。
                要求：语言极其精炼，逻辑清晰，使用 Markdown 格式分点阐述。
                
                近期文章列表：
                {articles_text}
                """
                
                client = OpenAI(api_key=OPENAI_API_KEY)
                response = client.chat.completions.create(
                    model="gpt-3.5-turbo", # 如果你想用更强的模型，可以改成 gpt-4o
                    messages=[{"role": "user", "content": prompt}]
                )
                
                st.success("分析完成！")
                st.markdown(response.choices[0].message.content)
            except Exception as e:
                st.error(f"调用 AI 失败，请检查 API 密钥或网络环境。错误详情：{e}")

st.divider()

# 8. 真实数据展示区
st.subheader("📝 近期文章列表")
if not filtered_df.empty:
    # 遍历数据框中的每一行，为每一篇文章生成一个独立卡片
    for index, row in filtered_df.iterrows():
        # st.container(border=True) 会自动生成一个带圆角边框的漂亮卡片
        with st.container(border=True):
            # 将卡片分为左右两列，比例大概是 5:1
            col1, col2 = st.columns([5, 1])
            
            with col1:
                # 顶部小字：标签和时间
                st.caption(f"🏷️ **{row['竞品来源']}** &nbsp; | &nbsp; 🕒 {row['发布时间'].strftime('%Y-%m-%d %H:%M')}")
                # 文章大标题（做成 Markdown 超链接，点击文字也能跳转）
                st.markdown(f"#### [{row['文章标题']}]({row['直达链接']})")
                
            with col2:
                # 敲几个换行，让右侧的按钮在垂直方向上居中对齐
                st.write("") 
                # 添加一个原生直达按钮
                st.link_button("阅读原文 ↗", row['直达链接'], use_container_width=True)
else:
    st.warning("当前筛选条件下没有数据。")
