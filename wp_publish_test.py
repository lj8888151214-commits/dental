import base64
from datetime import datetime
import sqlite3
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, EmailStr
import requests
import uvicorn

app = FastAPI(title="고객관리 CRM 및 워드프레스 자동화 시스템")

# React 및 외부 통신 허용 (CORS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- 1. 워드프레스 연동 설정 (LocalWP 정보) ---
WP_URL = "http://tle.local/wp-json/wp/v2/posts"
WP_USER = "root"  # 본인의 워드프레스 ID
WP_APP_PASSWORD = "tQlN bDpQ GQB9 QjtK NUjw y20R"  # 발급받은 24자리 애플리케이션 비밀번호


def get_wp_headers():
    credentials = f"{WP_USER}:{WP_APP_PASSWORD}"
    token = base64.b64encode(credentials.encode("utf-8")).decode("utf-8")
    return {
        "Authorization": f"Basic {token}",
        "Content-Type": "application/json; charset=utf-8"
    }


# --- 2. 초간편 로컬 DB (SQLite) 초기화 ---
def init_db():
    conn = sqlite3.connect("crm_leads.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            company TEXT,
            message TEXT,
            created_at TEXT
        )
    """)
    conn.commit()
    conn.close()


init_db()


# --- 3. 데이터 모델 ---
class LeadRequest(BaseModel):
    name: str
    email: EmailStr
    company: Optional[str] = "-"
    message: Optional[str] = "-"


# --- 4. 워드프레스 자동 알림 포스팅 함수 ---
def post_lead_notification_to_wp(name: str, company: str, email: str, message: str, created_at: str):
    html_content = f"""
    <h2>🔔 [신규 고객 상담 접수 알림]</h2>
    <p>고객 문의 폼을 통해 새로운 리드가 등록되었습니다.</p>
    <table style="width: 100%; border-collapse: collapse; margin-top: 15px;">
        <tr style="background-color: #f1f5f9;">
            <th style="padding: 10px; border: 1px solid #cbd5e1; text-align: left;">고객명</th>
            <td style="padding: 10px; border: 1px solid #cbd5e1;"><strong>{name}</strong></td>
        </tr>
        <tr>
            <th style="padding: 10px; border: 1px solid #cbd5e1; text-align: left;">회사명</th>
            <td style="padding: 10px; border: 1px solid #cbd5e1;">{company}</td>
        </tr>
        <tr style="background-color: #f1f5f9;">
            <th style="padding: 10px; border: 1px solid #cbd5e1; text-align: left;">이메일</th>
            <td style="padding: 10px; border: 1px solid #cbd5e1;">{email}</td>
        </tr>
        <tr>
            <th style="padding: 10px; border: 1px solid #cbd5e1; text-align: left;">접수 시각</th>
            <td style="padding: 10px; border: 1px solid #cbd5e1;">{created_at}</td>
        </tr>
        <tr style="background-color: #f1f5f9;">
            <th style="padding: 10px; border: 1px solid #cbd5e1; text-align: left;">문의 내용</th>
            <td style="padding: 10px; border: 1px solid #cbd5e1;">{message}</td>
        </tr>
    </table>
    <br>
    <p><em>* 본 포스트는 FastAPI 고객관리 CRM 시스템 연동 파이프라인에 의해 자동 작성되었습니다.</em></p>
    """

    # ✅ 정상 코드
    payload = {
        "title": f"[CRM 접수] {company} - {name} 님의 신규 문의",
        "content": html_content,
        "status": "publish"
    }

    try:
        res = requests.post(WP_URL, headers=get_wp_headers(), json=payload, timeout=5)
        if res.status_code == 201:
            print(f"👉 워드프레스 알림 포스팅 등록 성공: ID {res.json().get('id')}")
        else:
            print(f"⚠️ 워드프레스 등록 실패 ({res.status_code}): {res.text}")
    except Exception as e:
        print(f"⚠️ 워드프레스 통신 예외 발생: {e}")


# --- 5. 백엔드 API 엔드포인트 ---
@app.post("/api/leads")
def create_lead(lead: LeadRequest):
    """고객 폼 제출 처리 -> SQLite 저장 -> 워드프레스 자동 포스팅 트리거"""
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    conn = sqlite3.connect("crm_leads.db")
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO leads (name, email, company, message, created_at) VALUES (?, ?, ?, ?, ?)",
        (lead.name, lead.email, lead.company, lead.message, now_str)
    )
    conn.commit()
    conn.close()

    # 워드프레스에 자동 포스팅 알림 전송
    post_lead_notification_to_wp(lead.name, lead.company, lead.email, lead.message, now_str)

    return {"status": "success", "message": "성공적으로 접수되었습니다."}


@app.get("/api/leads")
def get_leads():
    """관리자용 접수 목록 조회"""
    conn = sqlite3.connect("crm_leads.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM leads ORDER BY id DESC")
    rows = cursor.fetchall()
    leads = [dict(row) for row in rows]
    conn.close()
    return leads


# --- 6. 브라우저 즉시 테스트용 내장 UI (React 연동 전 즉시 시연 가능) ---
@app.get("/", response_class=HTMLResponse)
def index_page():
    return """
    <!DOCTYPE html>
    <html lang="ko">
    <head>
        <meta charset="UTF-8">
        <title>고객 상담 접수 폼 (CRM 연동)</title>
        <style>
            body { font-family: sans-serif; background: #f8fafc; padding: 40px; display: flex; justify-content: center; }
            .card { background: white; padding: 30px; border-radius: 10px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1); width: 100%; max-width: 480px; }
            h2 { margin-top: 0; color: #1e293b; }
            label { display: block; margin-top: 15px; font-weight: bold; font-size: 14px; color: #475569; }
            input, textarea { width: 100%; padding: 10px; margin-top: 5px; border: 1px solid #cbd5e1; border-radius: 6px; box-sizing: border-box; }
            button { width: 100%; padding: 12px; margin-top: 20px; background: #2563eb; color: white; border: none; border-radius: 6px; font-size: 16px; font-weight: bold; cursor: pointer; }
            button:hover { background: #1d4ed8; }
            #result { margin-top: 15px; padding: 10px; border-radius: 6px; display: none; }
        </style>
    </head>
    <body>
        <div class="card">
            <h2>💼 B2B 고객 상담 신청</h2>
            <form id="leadForm">
                <label>성함 *</label>
                <input type="text" id="name" required placeholder="홍길동">
                <label>이메일 *</label>
                <input type="email" id="email" required placeholder="name@company.com">
                <label>회사명</label>
                <input type="text" id="company" placeholder="(주)테크솔루션">
                <label>문의 내용</label>
                <textarea id="message" rows="3" placeholder="도입 상담 요청 내용"></textarea>
                <button type="submit">신청하기</button>
            </form>
            <div id="result"></div>
        </div>

        <script>
            document.getElementById('leadForm').addEventListener('submit', async (e) => {
                e.preventDefault();
                const resDiv = document.getElementById('result');
                resDiv.style.display = 'block';
                resDiv.style.background = '#e2e8f0';
                resDiv.style.color = '#334155';
                resDiv.innerText = '접수 처리 및 워드프레스 동기화 중...';

                const payload = {
                    name: document.getElementById('name').value,
                    email: document.getElementById('email').value,
                    company: document.getElementById('company').value,
                    message: document.getElementById('message').value
                };

                try {
                    const res = await fetch('/api/leads', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(payload)
                    });
                    const data = await res.json();
                    if(res.ok) {
                        resDiv.style.background = '#dcfce7';
                        resDiv.style.color = '#15803d';
                        resDiv.innerText = '✅ 성공적으로 접수되었습니다! 워드프레스에 알림 글이 등록되었습니다.';
                        document.getElementById('leadForm').reset();
                    } else {
                        throw new Error(data.detail || '접수 실패');
                    }
                } catch(err) {
                    resDiv.style.background = '#fee2e2';
                    resDiv.style.color = '#b91c1c';
                    resDiv.innerText = '❌ 에러: ' + err.message;
                }
            });
        </script>
    </body>
    </html>
    """


# --- 7. 파이참에서 바로 Run으로 실행 ---
#if __name__ == "__main__":
#    uvicorn.run(app, host="127.0.0.1", port=8000)

# --- 7. 실행 블록 ---
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=5137)