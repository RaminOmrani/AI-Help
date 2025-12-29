import re
import streamlit as st
import requests
import os
from dotenv import load_dotenv

# تنظیمات اولیه صفحه
st.set_page_config(
    page_title="پشتیبان هوشمند میلیونر",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

# استایل‌های CSS سفارشی برای زیبایی بیشتر (راست‌چین، فونت فارسی و تم زرشکی)
st.markdown(
    """
<style>
    @import url('https://fonts.googleapis.com/css2?family=Vazirmatn:wght@400;600;700&display=swap');

    html, body, [class*="css"]  {
        font-family: 'Vazirmatn', sans-serif;
        background: linear-gradient(180deg, #ffffff 0%, #fff5f7 100%);
        color: #2b2b2b;
    }

    .stApp {
        direction: rtl;
    }

    .stChatMessage {
        text-align: right;
        direction: rtl;
    }

    [data-testid="stChatMessageUser"] {
        background: #fff5f5;
        border: 1px solid #b11226;
        border-radius: 16px;
        padding: 12px 14px;
        box-shadow: 0 4px 10px rgba(177, 18, 38, 0.08);
    }

    [data-testid="stChatMessageAssistant"] {
        background: #ffffff;
        border: 1px solid #f3c6ce;
        border-radius: 16px;
        padding: 12px 14px;
        box-shadow: 0 4px 10px rgba(0, 0, 0, 0.04);
    }

    .stTextInput > div > div > input {
        direction: rtl;
        text-align: right;
    }

    div[data-testid="stSidebar"] {
        text-align: right;
        direction: rtl;
        background: #b11226;
        color: #ffffff;
    }

    div[data-testid="stSidebar"] h1, div[data-testid="stSidebar"] h2, div[data-testid="stSidebar"] h3, div[data-testid="stSidebar"] p {
        color: #ffffff;
    }

    div[data-testid="stSidebar"] .stButton button {
        background-color: #ffffff;
        color: #b11226;
        border-radius: 12px;
        border: none;
        font-weight: 700;
        box-shadow: 0 6px 16px rgba(0, 0, 0, 0.08);
    }

    div[data-testid="stSidebar"] .stButton button:hover {
        background-color: #f3c6ce;
    }

    .stMarkdown h1, .stMarkdown h2, .stMarkdown h3, p {
        text-align: right;
        direction: rtl;
    }

    .question-history {
        background: rgba(255, 255, 255, 0.12);
        padding: 10px 12px;
        border-radius: 12px;
        border: 1px solid rgba(255, 255, 255, 0.25);
    }

    .history-item {
        margin-bottom: 8px;
        padding: 8px 10px;
        border-radius: 10px;
        background: rgba(255, 255, 255, 0.9);
        color: #b11226;
        font-weight: 600;
        box-shadow: 0 2px 6px rgba(0, 0, 0, 0.06);
    }
</style>
""",
    unsafe_allow_html=True,
)

load_dotenv()
BACKEND_URL = f"http://{os.getenv('BACKEND_HOST', '127.0.0.1')}:{os.getenv('BACKEND_PORT', '8000')}"


def linkify_text(text: str) -> str:
    """تبدیل URL های معمولی به لینک قابل کلیک برای نمایش در چت."""

    def _replace(match: re.Match) -> str:
        url = match.group(0)
        return f'<a href="{url}" target="_blank" rel="noopener">{url}</a>'

    return re.sub(r"https?://[^\s]+", _replace, text)

# --- توابع کمکی ---
def init_system():
    with st.spinner("در حال ارسال فایل‌ها به مغز هوش مصنوعی... (لطفاً صبر کنید)"):
        try:
            res = requests.post(f"{BACKEND_URL}/initialize_knowledge")
            if res.status_code == 200:
                data = res.json()
                if data["status"] == "success":
                    st.success(data["message"])
                    return True
                else:
                    st.error(f"خطا: {data['message']}")
            else:
                st.error("ارتباط با سرور برقرار نشد.")
        except Exception as e:
            st.error(f"خطای ارتباط: {e}")
    return False

def send_message(msg):
    try:
        res = requests.post(f"{BACKEND_URL}/chat", json={"message": msg})
        if res.status_code == 200:
            return res.json()["response"]
        else:
            return f"خطای سرور: {res.text}"
    except Exception as e:
        return f"خطا: {e}"

# --- رابط کاربری ---

# سایدبار
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/4712/4712109.png", width=80)
    st.title("پنل تنظیمات")
    st.markdown("---")
    
    st.info("💡 فایل‌های PDF خود را در پوشه `docs` کنار برنامه قرار دهید.")
    
    if st.button("🔄 راه‌اندازی / آپدیت پایگاه دانش", type="primary"):
        if init_system():
            st.session_state.system_ready = True
    
    st.markdown("---")
    st.markdown("**وضعیت سیستم:**")
    if st.session_state.get("system_ready"):
        st.markdown("🟢 آماده پاسخگویی")
    else:
        st.markdown("🔴 غیرفعال (نیاز به راه‌اندازی)")

# بخش اصلی چت
st.title("💬 دستیار فنی تیم پشتیبانی")
st.caption("پاسخگویی بر اساس مستندات فنی و اسکرین‌شات‌ها")

if "messages" not in st.session_state:
    st.session_state.messages = []

if "question_history" not in st.session_state:
    st.session_state.question_history = []

if st.session_state.messages:
    st.markdown(
        """
    <div style="background:#b11226;color:#fff;padding:12px 16px;border-radius:14px;margin-bottom:14px;">
        ✨ سوالات و پاسخ‌های قبلی شما در همین صفحه باقی می‌مانند. برای مرور سریع می‌توانید از منوی تاریخچه در سایدبار استفاده کنید.
    </div>
    """,
        unsafe_allow_html=True,
    )

# نمایش پیام‌های قبلی
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(linkify_text(message["content"]), unsafe_allow_html=True)

# ورودی کاربر
if prompt := st.chat_input("سوال خود را بپرسید... (مثلا: خطای SQL 1433 چیست؟)"):
    if not st.session_state.get("system_ready"):
        st.warning("⚠️ لطفاً ابتدا از منوی سمت راست سیستم را راه‌اندازی کنید.")
    else:
        # نمایش پیام کاربر
        st.session_state.messages.append({"role": "user", "content": prompt})
        st.session_state.question_history.append(prompt)
        with st.chat_message("user"):
            st.markdown(prompt)

        # دریافت پاسخ
        with st.chat_message("assistant"):
            message_placeholder = st.empty()
            message_placeholder.markdown("Thinking...")
            response = send_message(prompt)
            message_placeholder.markdown(linkify_text(response), unsafe_allow_html=True)

        st.session_state.messages.append({"role": "assistant", "content": response})

# تاریخچه سوالات در سایدبار
with st.sidebar:
    st.markdown("---")
    st.markdown("### تاریخچه سوالات")
    if st.session_state.question_history:
        st.markdown("<div class='question-history'>", unsafe_allow_html=True)
        for idx, question in enumerate(reversed(st.session_state.question_history), 1):
            st.markdown(f"<div class='history-item'>{idx}. {question}</div>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)
    else:
        st.caption("هنوز سوالی ثبت نشده است.")