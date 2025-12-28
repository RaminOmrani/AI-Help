from fastapi import FastAPI, UploadFile, HTTPException
from pydantic import BaseModel
import google.generativeai as genai
import os
from dotenv import load_dotenv
import time

# بارگذاری تنظیمات
load_dotenv()

app = FastAPI(title="Millionaire Support AI Backend")

# تنظیمات Gemini
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
MODEL_ID = "gemini-2.5-flash"

# حافظه موقت برای نگهداری وضعیت چت (در پروداکشن واقعی باید دیتابیس باشد)
class GlobalState:
    chat_session = None
    uploaded_files = []

state = GlobalState()

class ChatRequest(BaseModel):
    message: str

@app.get("/")
def health_check():
    return {"status": "running", "model": MODEL_ID}

@app.post("/initialize_knowledge")
async def initialize_knowledge():
    """
    این تابع فایل‌های PDF موجود در پوشه docs را می‌خواند و به هوش مصنوعی می‌دهد.
    """
    folder_path = "docs"
    if not os.path.exists(folder_path):
        os.makedirs(folder_path)
        return {"status": "error", "message": "پوشه docs یافت نشد. پوشه ساخته شد، فایل‌ها را داخل آن بریزید."}

    pdf_files = [f for f in os.listdir(folder_path) if f.endswith('.pdf')]
    if not pdf_files:
        return {"status": "error", "message": "هیچ فایل PDF در پوشه docs پیدا نشد."}

    state.uploaded_files = []
    
    try:
        # آپلود فایل‌ها به گوگل
        for pdf in pdf_files:
            file_path = os.path.join(folder_path, pdf)
            print(f"Uploading {pdf}...")
            uploaded_file = genai.upload_file(path=file_path, mime_type="application/pdf")
            
            # انتظار برای پردازش
            while uploaded_file.state.name == "PROCESSING":
                time.sleep(2)
                uploaded_file = genai.get_file(uploaded_file.name)
            
            if uploaded_file.state.name != "ACTIVE":
                raise Exception(f"File {pdf} failed to process.")
                
            state.uploaded_files.append(uploaded_file)

        # ساخت مدل و شروع چت
        model = genai.GenerativeModel(
            model_name=MODEL_ID,
            system_instruction="""
            تو دستیار هوشمند پشتیبانی نرم‌افزار هستی.
            وظیفه: پاسخ به سوالات فنی بر اساس فایل‌های PDF آپلود شده (شامل متن و اسکرین‌شات).
            قوانین:
            1. پاسخ‌ها باید کوتاه، گام‌به‌گام و کاملاً اجرایی باشند.
            2. حتماً به نام فایل و شماره صفحه رفرنس بده. (مثال: طبق راهنمای سریع - صفحه 5).
            3. اگر راه حل در یک تصویر (اسکرین‌شات) بود، توضیح بده در تصویر چه می‌بینی.
            4. اگر اطلاعاتی موجود نبود، صادقانه بگو "در مستندات یافت نشد".
            """
        )
        
        # تاریخچه اولیه شامل فایل‌ها
        history = [{"role": "user", "parts": [f]} for f in state.uploaded_files]
        state.chat_session = model.start_chat(history=history)
        
        return {"status": "success", "message": f"{len(pdf_files)} فایل با موفقیت بارگذاری شد.", "files": pdf_files}

    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/chat")
async def chat_endpoint(request: ChatRequest):
    if not state.chat_session:
        raise HTTPException(status_code=400, detail="ابتدا باید سیستم را راه‌اندازی (Initialize) کنید.")
    
    try:
        response = state.chat_session.send_message(request.message)
        return {"response": response.text}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))