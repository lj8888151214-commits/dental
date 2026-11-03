import base64
from datetime import datetime
import os
import sqlite3
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
import google.generativeai as genai
from PIL import Image
from pydantic import BaseModel
import requests
import uvicorn

app = FastAPI(title="AI 스마트 레시피 & 워드프레스 자동화 시스템")

# CORS 허용
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- 1. 워드프레스 및 AI API 설정 ---
WP_URL = "http://tle.local/wp-json/wp/v2/posts"
WP_USER = "root"  # 본인의 워드프레스 ID
WP_APP_PASSWORD = "tQlN bDpQ GQB9 QjtK NUjw y20R"  # 24자리 애플리케이션 비밀번호

# Gemini API 키 (환경 변수 또는 직접 입력)
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "YOUR_GEMINI_API_KEY_HERE")
if GEMINI_API_KEY != "YOUR_GEMINI_API_KEY_HERE":
    genai.configure(api_key=GEMINI_API_KEY)


def get_wp_headers():
    credentials = f"{WP_USER}:{WP_APP_PASSWORD}"
    token = base64.b64encode(credentials.encode("utf-8")).decode("utf-8")
    return {
        "Authorization": f"Basic {token}",
        "Content-Type": "application/json; charset=utf-8",
    }


# --- 2. 로컬 SQLite DB 초기화 ---
def init_db():
    conn = sqlite3.connect("smart_recipe.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS recipes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            ingredients TEXT NOT NULL,
            content TEXT NOT NULL,
            wp_post_id INTEGER,
            created_at TEXT
        )
    """)
    conn.commit()
    conn.close()


init_db()


# --- 3. 워드프레스 포스팅 유틸리티 ---
def publish_recipe_to_wordpress(
        title: str, ingredients: str, recipe_html: str
) -> Optional[int]:
    """생성된 레시피를 워드프레스에 SEO 구조화 태그로 즉시 발행"""
    full_content = f"""
    <div style="background-color: #f0fdf4; border: 1px solid #86efac; border-radius: 8px; padding: 20px; margin-bottom: 25px;">
        <h3 style="margin-top: 0; color: #166534;">🥗 인식된 냉장고 식재료</h3>
        <p style="font-size: 15px; color: #1e293b;">{ingredients}</p>
    </div>
    <div style="line-height: 1.8; font-size: 15px;">
        {recipe_html}
    </div>
    <hr style="margin-top: 30px;" />
    <p style="font-size: 12px; color: #64748b;">
        * 본 레시피는 AI 비전/자연어 모델이 식재료를 분석하여 자동 발행한 맞춤형 요리 가이드입니다.
    </p>
    """

    payload = {
        "title": f"[스마트 냉장고 레시피] {title}",
        "content": full_content,
        "status": "publish",
    }

    try:
        res = requests.post(
            WP_URL, headers=get_wp_headers(), json=payload, timeout=10
        )
        if res.status_code == 201:
            post_id = res.json().get("id")
            print(f"👉 워드프레스 레시피 발행 성공! (ID: {post_id})")
            return post_id
        else:
            print(f"⚠️ 워드프레스 발행 실패: {res.text}")
    except Exception as e:
        print(f"⚠️ 워드프레스 통신 오류: {e}")
    return None


# --- 4. 레시피 생성 API 엔드포인트 ---
@app.post("/api/recipe/generate")
async def generate_recipe(
        ingredients_text: str = Form(...), image: Optional[UploadFile] = File(None)
):
    """
    텍스트 식재료 또는 냉장고 사진을 전달받아 AI 레시피를 생성하고 워드프레스에 자동 등록
    """
    detected_items = ingredients_text

    # 이미지가 업로드된 경우 Gemini Vision 분석
    if image and GEMINI_API_KEY != "YOUR_GEMINI_API_KEY_HERE":
        try:
            img = Image.open(image.file)
            vision_model = genai.GenerativeModel("gemini-1.5-flash")
            vision_prompt = "이 냉장고 또는 식재료 사진에서 식별되는 주요 식재료 목록을 쉼표로 구분하여 한국어로 단어만 나열해줘."
            vision_res = vision_model.generate_content([vision_prompt, img])
            if vision_res.text:
                detected_items += f", {vision_res.text.strip()}"
        except Exception as e:
            print(f"이미지 인식 오류: {e}")

    # 레시피 상세 생성 (구조화된 HTML 형태 요청)
    recipe_prompt = f"""
    식재료: [{detected_items}]
    위 재료들을 최대한 활용하여 만들 수 있는 훌륭한 요리 1가지를 추천해줘.

    출력 형식:
    1. 맨 첫 줄은 요리 이름만 작성할 것. (예: 토마토 달걀 볶음)
    2. 그 다음 줄부터는 웹 브라우저에 바로 표시할 수 있도록 <h3>, <ul>, <ol>, <li>, <p> 태그만 사용한 HTML 본문으로 조리법을 작성할 것.
       - 소요 시간 및 난이도
       - 필요 재료 (기본 양념 포함)
       - 단계별 상세 조리 순서
    """

    recipe_title = "간편 맞춤형 요리"
    recipe_body = f"<p>인식된 식재료: {detected_items}</p><ol><li>재료를 손질합니다.</li><li>팬에 볶아 조리합니다.</li></ol>"

    if GEMINI_API_KEY != "YOUR_GEMINI_API_KEY_HERE":
        try:
            model = genai.GenerativeModel("gemini-1.5-flash")
            ai_res = model.generate_content(recipe_prompt)
            lines = ai_res.text.strip().split("\n")
            recipe_title = (
                lines[0].replace("#", "").replace("**", "").strip()
            )  # 첫 줄을 요리명으로 파싱
            recipe_body = "\n".join(lines[1:]).strip()
        except Exception as e:
            print(f"AI 생성 실패, 기본 템플릿 사용: {e}")

    # 워드프레스에 자동 발행
    wp_id = publish_recipe_to_wordpress(
        recipe_title, detected_items, recipe_body
    )

    # SQLite 로컬 DB 저장
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = sqlite3.connect("smart_recipe.db")
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO recipes (title, ingredients, content, wp_post_id, created_at) VALUES (?, ?, ?, ?, ?)",
        (recipe_title, detected_items, recipe_body, wp_id, now_str),
    )
    conn.commit()
    conn.close()

    return {
        "status": "success",
        "title": recipe_title,
        "ingredients": detected_items,
        "wp_post_id": wp_id,
        "view_url": f"http://tle.local/?p={wp_id}"
        if wp_id
        else "http://tle.local",
    }


# --- 5. 스마트 냉장고 웹 테스트 화면 (UI) ---
@app.get("/", response_class=HTMLResponse)
def recipe_ui():
    return """
    <!DOCTYPE html>
    <html lang="ko">
    <head>
        <meta charset="UTF-8">
        <title>스마트 냉장고 AI 레시피 생성기</title>
        <style>
            body { font-family: -apple-system, BlinkMacSystemFont, sans-serif; background: #f1f5f9; padding: 40px; display: flex; justify-content: center; }
            .container { background: white; padding: 30px; border-radius: 12px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1); width: 100%; max-width: 500px; }
            h2 { color: #0f172a; margin-top: 0; }
            label { display: block; margin-top: 15px; font-weight: 600; font-size: 14px; color: #334155; }
            input[type="text"], input[type="file"] { width: 100%; padding: 10px; margin-top: 6px; border: 1px solid #cbd5e1; border-radius: 6px; box-sizing: border-box; }
            button { width: 100%; padding: 12px; margin-top: 20px; background: #059669; color: white; border: none; border-radius: 6px; font-size: 16px; font-weight: bold; cursor: pointer; }
            button:hover { background: #047857; }
            #statusBox { margin-top: 20px; padding: 15px; border-radius: 6px; display: none; line-height: 1.5; }
        </style>
    </head>
    <body>
        <div class="container">
            <h2>🍳 스마트 냉장고 AI 레시피</h2>
            <p style="font-size: 13px; color: #64748b;">식재료를 입력하거나 냉장고 사진을 올리면 AI가 레시피를 만들어 워드프레스에 자동 게시합니다.</p>

            <form id="recipeForm">
                <label>냉장고 속 재료 입력 (쉼표 구분)</label>
                <input type="text" id="ingredients" placeholder="예: 두부, 대파, 계란, 스팸" required>

                <label>냉장고 사진 업로드 (선택)</label>
                <input type="file" id="imageInput" accept="image/*">

                <button type="submit">AI 레시피 생성 및 자동 발행</button>
            </form>

            <div id="statusBox"></div>
        </div>

        <script>
            document.getElementById('recipeForm').addEventListener('submit', async (e) => {
                e.preventDefault();
                const statusBox = document.getElementById('statusBox');
                statusBox.style.display = 'block';
                statusBox.style.background = '#e2e8f0';
                statusBox.style.color = '#1e293b';
                statusBox.innerHTML = '⏳ AI가 재료를 분석하고 워드프레스에 포스팅 중입니다...';

                const formData = new FormData();
                formData.append('ingredients_text', document.getElementById('ingredients').value);

                const fileInput = document.getElementById('imageInput');
                if (fileInput.files[0]) {
                    formData.append('image', fileInput.files[0]);
                }

                try {
                    const res = await fetch('/api/recipe/generate', {
                        method: 'POST',
                        body: formData
                    });
                    const data = await res.json();

                    if(res.ok) {
                        statusBox.style.background = '#dcfce7';
                        statusBox.style.color = '#14532d';
                        statusBox.innerHTML = `
                            ✅ <strong>${data.title}</strong> 생성 완료!<br>
                            👉 <a href="${data.view_url}" target="_blank" style="color: #059669; font-weight: bold; text-decoration: underline;">워드프레스에서 글 확인하기</a>
                        `;
                    } else {
                        throw new Error('생성 실패');
                    }
                } catch(err) {
                    statusBox.style.background = '#fee2e2';
                    statusBox.style.color = '#991b1b';
                    statusBox.innerHTML = '❌ 처리 중 오류가 발생했습니다.';
                }
            });
        </script>
    </body>
    </html>
    """


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)