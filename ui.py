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

# استایل‌های CSS سفارشی برای زیبایی بیشتر (راست‌چین و فونت)
st.markdown("""
<style>
    .stChatMessage { text-align: right; direction: rtl; }
    .stTextInput > div > div > input { direction: rtl; text-align: right; }
    div[data-testid="stSidebar"] { text-align: right; direction: rtl; }
    h1, h2, h3 { text-align: right; }
    p { text-align: right; direction: rtl; }
</style>
""", unsafe_allow_html=True)

load_dotenv()
BACKEND_URL = f"http://{os.getenv('BACKEND_HOST', '127.0.0.1')}:{os.getenv('BACKEND_PORT', '8000')}"

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

# نمایش پیام‌های قبلی
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# ورودی کاربر
if prompt := st.chat_input("سوال خود را بپرسید... (مثلا: خطای SQL 1433 چیست؟)"):
    if not st.session_state.get("system_ready"):
        st.warning("⚠️ لطفاً ابتدا از منوی سمت راست سیستم را راه‌اندازی کنید.")
    else:
        # نمایش پیام کاربر
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        # دریافت پاسخ
        with st.chat_message("assistant"):
            message_placeholder = st.empty()
            message_placeholder.markdown("Thinking...")
            response = send_message(prompt)
            message_placeholder.markdown(response)
        
        st.session_state.messages.append({"role": "assistant", "content": response})