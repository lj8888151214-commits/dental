import base64
from datetime import datetime
import os
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import requests
from sqlalchemy import Column, Integer, String, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import uvicorn

# 1. DATABASE_URL 환경변수가 없으면 자동으로 로컬 SQLite 파일(local_dental.db) 사용
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./local_dental.db")

# 2. SQLite / PostgreSQL 분기 처리
if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(
        DATABASE_URL, connect_args={"check_same_thread": False}
    )
else:
    engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


# 3. 테이블 모델 정의
class DentalGuideLog(Base):
    __tablename__ = "dental_guide_logs"

    id = Column(Integer, primary_key=True, index=True)
    mode = Column(String(100), nullable=False)
    target_area = Column(String(100), nullable=False)
    wp_post_id = Column(Integer, nullable=True)
    created_at = Column(String(50), nullable=False)


# 테이블 자동 생성 (SQLite 파일이 없으면 자동 생성됨)
Base.metadata.create_all(bind=engine)


app = FastAPI(title="스마트 덴탈 3D 뷰어 & 워드프레스 자동화 시스템")

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 1. static 폴더 생성 확인 및 마운트 (3D 모델 서빙용)
os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

# 2. 워드프레스 연동 설정
WP_URL = os.getenv("WP_URL", "http://tle.local/wp-json/wp/v2/posts")
WP_USER = os.getenv("WP_USER", "root")
WP_APP_PASSWORD = os.getenv(
    "WP_APP_PASSWORD", "tQlN bDpQ GQB9 QjtK NUjw y20R"
)


def get_wp_headers():
    credentials = f"{WP_USER}:{WP_APP_PASSWORD}"
    token = base64.b64encode(credentials.encode("utf-8")).decode("utf-8")
    return {
        "Authorization": f"Basic {token}",
        "Content-Type": "application/json; charset=utf-8",
    }


class DentalGuideRequest(BaseModel):
    mode: str
    target_area: str


# 3. 워드프레스 자동 포스팅 API 엔드포인트
@app.post("/api/dental/post-guide")
def post_dental_guide(req: DentalGuideRequest):
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    guide_html = f"""
    <div style="background-color: #eff6ff; border: 1px solid #bfdbfe; border-radius: 8px; padding: 20px; margin-bottom: 20px;">
        <h3 style="margin-top: 0; color: #1e40af;">🪥 [모바일 구강 케어] {req.mode} 맞춤 가이드</h3>
        <p style="font-size: 14px; color: #334155;"><strong>케어 부위:</strong> {req.target_area} | <strong>발행 시각:</strong> {now_str}</p>
    </div>

    <h3>1. 추천 칫솔질 각도 및 테크닉</h3>
    <ul>
        <li>칫솔모를 잇몸선과 치아 경계면에 <strong>45도 각도</strong>로 밀착시킵니다 (변형 바스법).</li>
        <li>손목 스냅을 가볍게 회전시키며 치아 방향으로 쓸어 넘깁니다.</li>
    </ul>

    <h3>2. 주의 사항 및 권장 시간</h3>
    <ol>
        <li>스마트폰 거치대나 거울을 보며 균등한 힘으로 닦아주세요.</li>
        <li>{req.target_area} 부위는 1회 양치 시 최소 15초 이상 집중 관리합니다.</li>
    </ol>
    <br>
    <p><em>* 본 포스트는 모바일 3D 인터랙티브 뷰어 연동 파이프라인을 통해 자동 발행되었습니다.</em></p>
    """

    payload = {
        "title": f"[모바일 덴탈 케어] {req.mode} - {req.target_area} 가이드",
        "content": guide_html,
        "status": "publish",
    }

    wp_id = None
    try:
        res = requests.post(
            WP_URL, headers=get_wp_headers(), json=payload, timeout=8
        )
        if res.status_code == 201:
            wp_id = res.json().get("id")
    except Exception as e:
        print(f"워드프레스 통신 예외 발생: {e}")

    # 데이터베이스에 로그 기록 (SQLite / PostgreSQL 공용)
    db = SessionLocal()
    try:
        log_entry = DentalGuideLog(
            mode=req.mode,
            target_area=req.target_area,
            wp_post_id=wp_id,
            created_at=now_str,
        )
        db.add(log_entry)
        db.commit()
    except Exception as e:
        print(f"DB 저장 실패: {e}")
    finally:
        db.close()

    if wp_id:
        return {
            "status": "success",
            "post_id": wp_id,
            "url": f"http://tle.local/?p={wp_id}",
        }
    else:
        return {
            "status": "fail",
            "detail": "워드프레스 등록 실패 (DB에는 기록됨)",
        }


# 4. 모바일 반응형 3D 칫솔 뷰어 웹 화면
@app.get("/", response_class=HTMLResponse)
def dental_3d_page():
    return """
    <!DOCTYPE html>
    <html lang="ko">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
        <title>스마트 덴탈 3D 모바일 뷰어</title>
        <style>
            * { box-sizing: border-box; -webkit-tap-highlight-color: transparent; }

            html, body {
                margin: 0; padding: 0; width: 100%; height: 100%;
                overflow: hidden; background: #0f172a;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            }

            #canvas-container {
                width: 100vw; height: 100vh;
                position: absolute; top: 0; left: 0; z-index: 1;
            }

            /* 기본 데스크톱 패널 */
            .ui-panel {
                position: absolute; top: 20px; left: 20px; z-index: 10;
                background: rgba(15, 23, 42, 0.88); backdrop-filter: blur(12px);
                border: 1px solid rgba(255, 255, 255, 0.15); border-radius: 14px;
                padding: 20px; color: white; width: 320px;
                box-shadow: 0 12px 30px rgba(0,0,0,0.4);
            }
            h2 { margin: 0 0 6px 0; font-size: 18px; color: #38bdf8; }
            p.desc { margin: 0 0 12px 0; font-size: 13px; color: #94a3b8; line-height: 1.4; }
            label { display: block; font-size: 12px; font-weight: 600; margin-top: 10px; color: #cbd5e1; }
            select {
                width: 100%; height: 42px; padding: 0 10px; margin-top: 5px;
                border-radius: 8px; background: #1e293b; color: white;
                border: 1px solid #475569; font-size: 14px; outline: none;
            }
            button {
                width: 100%; height: 44px; margin-top: 15px;
                background: #0284c7; color: white; border: none; border-radius: 8px;
                font-size: 15px; font-weight: bold; cursor: pointer;
                transition: background 0.2s, transform 0.1s;
            }
            button:active { transform: scale(0.98); background: #0369a1; }
            #result { margin-top: 10px; font-size: 13px; line-height: 1.4; display: none; }

            .guide-hint {
                position: absolute; top: 15px; right: 15px; z-index: 10;
                background: rgba(0, 0, 0, 0.65); color: #cbd5e1;
                padding: 6px 12px; border-radius: 20px; font-size: 12px;
                pointer-events: none; border: 1px solid rgba(255,255,255,0.1);
            }

            /* 📱 스마트폰 모바일 해상도 (600px 이하) 최적화 */
            @media (max-width: 600px) {
                .ui-panel {
                    top: auto; bottom: 0; left: 0; right: 0;
                    width: 100%; border-radius: 20px 20px 0 0;
                    padding: 18px 20px 25px 20px;
                    border-bottom: none;
                    box-shadow: 0 -10px 25px rgba(0,0,0,0.5);
                }
                h2 { font-size: 17px; }
                p.desc { display: none; }
                .guide-hint {
                    top: auto; bottom: 250px; left: 50%; right: auto;
                    transform: translateX(-50%); font-size: 11px;
                }
            }
        </style>
        <script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>
        <script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/controls/OrbitControls.js"></script>
        <script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/loaders/GLTFLoader.js"></script>
    </head>
    <body>
        <div id="canvas-container"></div>

        <div class="guide-hint">👆 터치 드래그: 360도 회전 | 두 손가락: 줌</div>

        <div class="ui-panel">
            <h2>🪥 3D 스마트 칫솔 코칭</h2>
            <p class="desc">화면의 칫솔을 직접 돌려보며 올바른 각도를 확인하세요.</p>

            <label>양치 모드 선택</label>
            <select id="mode">
                <option value="잇몸선 케어 (바스법)">잇몸선 집중 케어 (바스법)</option>
                <option value="플라그 회전 제거">표면 플라그 제거 (회전법)</option>
                <option value="교정 장치 틈새 관리">교정 치아 틈새 케어</option>
            </select>

            <label>집중 케어 구역</label>
            <select id="targetArea">
                <option value="어금니 안쪽 깊은 면">어금니 안쪽 깊은 면</option>
                <option value="앞니 잇몸 경계면">앞니 잇몸 경계면</option>
                <option value="어금니 씹는 면">어금니 씹는 면 (교합면)</option>
            </select>

            <button onclick="publishGuide()">가이드 워드프레스 자동 발행</button>
            <div id="result"></div>
        </div>

        <script>
            const container = document.getElementById('canvas-container');
            const scene = new THREE.Scene();

            const isMobile = window.innerWidth <= 600;
            const camera = new THREE.PerspectiveCamera(45, window.innerWidth / window.innerHeight, 0.1, 1000);

            if (isMobile) {
                camera.position.set(0, 3, 11);
            } else {
                camera.position.set(0, 2, 8);
            }

            const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
            renderer.setSize(window.innerWidth, window.innerHeight);
            renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
            container.appendChild(renderer.domElement);

            const hemiLight = new THREE.HemisphereLight(0xffffff, 0x334155, 1.3);
            scene.add(hemiLight);

            const dirLight = new THREE.DirectionalLight(0xffffff, 1.6);
            dirLight.position.set(5, 10, 7);
            scene.add(dirLight);

            const controls = new THREE.OrbitControls(camera, renderer.domElement);
            controls.enableDamping = true;
            controls.dampingFactor = 0.05;

            if (isMobile) {
                controls.target.set(0, 1.0, 0);
            }

            const loader = new THREE.GLTFLoader();
            loader.load('/static/toothbrush.glb', (gltf) => {
                const model = gltf.scene;

                const box = new THREE.Box3().setFromObject(model);
                const size = box.getSize(new THREE.Vector3());
                const center = box.getCenter(new THREE.Vector3());

                model.position.x += (model.position.x - center.x);
                model.position.y += (model.position.y - center.y);
                model.position.z += (model.position.z - center.z);

                const maxDim = Math.max(size.x, size.y, size.z);
                if (maxDim > 0) {
                    const scaleFactor = (isMobile ? 3.6 : 4.2) / maxDim;
                    model.scale.set(scaleFactor, scaleFactor, scaleFactor);
                }

                scene.add(model);
                console.log("3D 모델 로드 성공!");
            }, undefined, (err) => {
                console.error("3D 로드 실패: static/toothbrush.glb 확인 필요", err);
            });

            function animate() {
                requestAnimationFrame(animate);
                controls.update();
                renderer.render(scene, camera);
            }
            animate();

            window.addEventListener('resize', () => {
                camera.aspect = window.innerWidth / window.innerHeight;
                camera.updateProjectionMatrix();
                renderer.setSize(window.innerWidth, window.innerHeight);
            });

            async function publishGuide() {
                const resDiv = document.getElementById('result');
                resDiv.style.display = 'block';
                resDiv.style.color = '#38bdf8';
                resDiv.innerText = '워드프레스 발행 및 DB 저장 중...';

                const payload = {
                    mode: document.getElementById('mode').value,
                    target_area: document.getElementById('targetArea').value
                };

                try {
                    const res = await fetch('/api/dental/post-guide', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(payload)
                    });
                    const data = await res.json();

                    if(data.status === 'success') {
                        resDiv.style.color = '#4ade80';
                        resDiv.innerHTML = `✅ 포스팅 완료!<br><a href="${data.url}" target="_blank" style="color: #38bdf8; text-decoration: underline;">👉 워드프레스 글 확인</a>`;
                    } else {
                        resDiv.style.color = '#f87171';
                        resDiv.innerText = '❌ 발행 실패: ' + (data.detail || '오류 발생');
                    }
                } catch(e) {
                    resDiv.style.color = '#f87171';
                    resDiv.innerText = '❌ 서버 통신 오류';
                }
            }
        </script>
    </body>
    </html>
    """


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)