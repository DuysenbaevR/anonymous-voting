from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Depends, Form
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, List, Optional
import asyncio
import secrets
import hashlib
import time
import json
import uuid
from datetime import datetime, timedelta
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Система анонимного голосования")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# В памяти хранилища (для демонстрации, в продакшене используйте Redis/PostgreSQL)
class InMemoryStorage:
    def __init__(self):
        self.sessions: Dict[str, dict] = {}
        self.tokens: Dict[str, dict] = {}
        self.votes: Dict[str, list] = {}  # session_id -> [votes]
        self.members: Dict[str, list] = {}  # session_id -> [members]
        self.active_voting: Dict[str, dict] = {}  # session_id -> voting_info
        
storage = InMemoryStorage()

# WebSocket connections
class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {
            "admin": [],
            "projector": []
        }

    async def connect(self, websocket: WebSocket, connection_type: str):
        await websocket.accept()
        self.active_connections[connection_type].append(websocket)

    def disconnect(self, websocket: WebSocket, connection_type: str):
        if websocket in self.active_connections[connection_type]:
            self.active_connections[connection_type].remove(websocket)

    async def broadcast_to_type(self, message: dict, connection_type: str):
        disconnected = []
        for connection in self.active_connections[connection_type]:
            try:
                await connection.send_text(json.dumps(message))
            except:
                disconnected.append(connection)
        
        # Удаляем отключенные соединения
        for conn in disconnected:
            if conn in self.active_connections[connection_type]:
                self.active_connections[connection_type].remove(conn)

manager = ConnectionManager()

# Pydantic модели
class Member(BaseModel):
    name: str
    contact: str

class Session(BaseModel):
    title: str
    description: str
    members: List[Member]

class VotingSession(BaseModel):
    presenter_name: str
    topic_title: str
    topic_description: str
    duration_minutes: int = 5

class Vote(BaseModel):
    choice: str  # "за", "против", "воздержался"

# Утилиты
def generate_token() -> str:
    return secrets.token_urlsafe(32)

def generate_session_id() -> str:
    return str(uuid.uuid4())

def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()

# API endpoints
@app.post("/api/admin/create-session")
async def create_session(session: Session):
    session_id = generate_session_id()
    
    # Создаем сессию
    storage.sessions[session_id] = {
        "id": session_id,
        "title": session.title,
        "description": session.description,
        "created_at": datetime.now().isoformat(),
        "status": "created"
    }
    
    # Сохраняем участников
    storage.members[session_id] = []
    for member in session.members:
        storage.members[session_id].append({
            "name": member.name,
            "contact": member.contact
        })
    
    # Инициализируем голоса
    storage.votes[session_id] = []
    
    logger.info(f"Создана сессия {session_id} с {len(session.members)} участниками")
    
    return {"session_id": session_id, "status": "success"}

@app.post("/api/admin/start-voting/{session_id}")
async def start_voting(session_id: str, voting: VotingSession):
    if session_id not in storage.sessions:
        raise HTTPException(status_code=404, detail="Сессия не найдена")
    
    # Генерируем токены для участников
    tokens = []
    for member in storage.members[session_id]:
        token = generate_token()
        storage.tokens[token] = {
            "session_id": session_id,
            "member_name": member["name"],
            "used": False,
            "expires_at": time.time() + (voting.duration_minutes * 60) + 300,  # +5 мин буфер
            "created_at": time.time()
        }
        
        tokens.append({
            "member": member["name"],
            "contact": member["contact"],
            "token": token,
            "voting_url": f"/vote?token={token}"
        })
    
    # Устанавливаем активное голосование
    end_time = time.time() + (voting.duration_minutes * 60)
    storage.active_voting[session_id] = {
        "presenter_name": voting.presenter_name,
        "topic_title": voting.topic_title,
        "topic_description": voting.topic_description,
        "start_time": time.time(),
        "end_time": end_time,
        "duration_minutes": voting.duration_minutes,
        "status": "active"
    }
    
    # Обновляем статус сессии
    storage.sessions[session_id]["status"] = "voting"
    
    # Уведомляем проектор
    await manager.broadcast_to_type({
        "type": "voting_started",
        "session_id": session_id,
        "presenter_name": voting.presenter_name,
        "topic_title": voting.topic_title,
        "topic_description": voting.topic_description,
        "end_time": end_time,
        "duration_minutes": voting.duration_minutes
    }, "projector")
    
    # Уведомляем админа
    await manager.broadcast_to_type({
        "type": "voting_started",
        "session_id": session_id,
        "tokens_generated": len(tokens)
    }, "admin")
    
    # Запускаем автоматическое завершение голосования
    asyncio.create_task(auto_end_voting(session_id, voting.duration_minutes * 60))
    
    logger.info(f"Запущено голосование для сессии {session_id}")
    
    return {
        "status": "success",
        "tokens": tokens,
        "voting_ends_at": end_time
    }

async def auto_end_voting(session_id: str, duration_seconds: int):
    await asyncio.sleep(duration_seconds)
    
    if session_id in storage.active_voting and storage.active_voting[session_id]["status"] == "active":
        await end_voting(session_id)

@app.post("/api/admin/end-voting/{session_id}")
async def end_voting(session_id: str):
    if session_id not in storage.active_voting:
        raise HTTPException(status_code=404, detail="Активное голосование не найдено")
    
    # Подсчитываем голоса
    votes_count = {"за": 0, "против": 0, "воздержался": 0}
    
    # Подсчитываем уже поданные голоса
    for vote in storage.votes.get(session_id, []):
        votes_count[vote["choice"]] += 1
    
    # Считаем неиспользованные токены как "воздержался"
    unused_tokens = 0
    for token, token_data in storage.tokens.items():
        if token_data["session_id"] == session_id and not token_data["used"]:
            unused_tokens += 1
    
    votes_count["воздержался"] += unused_tokens
    
    # Обновляем статус голосования
    storage.active_voting[session_id]["status"] = "completed"
    storage.active_voting[session_id]["results"] = votes_count
    storage.sessions[session_id]["status"] = "completed"
    
    # Уведомляем всех подключенных
    result_message = {
        "type": "voting_ended",
        "session_id": session_id,
        "results": votes_count,
        "total_votes": sum(votes_count.values())
    }
    
    await manager.broadcast_to_type(result_message, "projector")
    await manager.broadcast_to_type(result_message, "admin")
    
    logger.info(f"Завершено голосование для сессии {session_id}. Результаты: {votes_count}")
    
    return {"status": "success", "results": votes_count}

@app.post("/api/vote")
async def submit_vote(token: str = Form(...), choice: str = Form(...)):
    # Проверяем токен
    if token not in storage.tokens:
        raise HTTPException(status_code=404, detail="Недействительный токен")
    
    token_data = storage.tokens[token]
    
    # Проверяем, не использован ли токен
    if token_data["used"]:
        raise HTTPException(status_code=400, detail="Токен уже использован")
    
    # Проверяем срок действия
    if time.time() > token_data["expires_at"]:
        raise HTTPException(status_code=400, detail="Токен истек")
    
    # Проверяем, активно ли голосование
    session_id = token_data["session_id"]
    if session_id not in storage.active_voting or storage.active_voting[session_id]["status"] != "active":
        raise HTTPException(status_code=400, detail="Голосование не активно")
    
    # Проверяем выбор
    if choice not in ["за", "против", "воздержался"]:
        raise HTTPException(status_code=400, detail="Недопустимый выбор")
    
    # Записываем голос (анонимно)
    vote_record = {
        "session_id": session_id,
        "choice": choice,
        "timestamp": time.time(),
        "token_hash": hash_token(token)  # Храним только хеш для предотвращения дублирования
    }
    
    if session_id not in storage.votes:
        storage.votes[session_id] = []
    
    storage.votes[session_id].append(vote_record)
    
    # Отмечаем токен как использованный
    storage.tokens[token]["used"] = True
    storage.tokens[token]["voted_at"] = time.time()
    
    # Подсчитываем текущие голоса для обновления
    current_votes = {"за": 0, "против": 0, "воздержался": 0}
    for vote in storage.votes[session_id]:
        current_votes[vote["choice"]] += 1
    
    # Уведомляем админа о новом голосе
    await manager.broadcast_to_type({
        "type": "vote_received",
        "session_id": session_id,
        "current_votes": current_votes,
        "total_members": len(storage.members.get(session_id, []))
    }, "admin")
    
    logger.info(f"Получен голос '{choice}' для сессии {session_id}")
    
    return {"status": "success", "message": "Голос принят"}

@app.get("/api/vote-page")
async def get_vote_page(token: str):
    if token not in storage.tokens:
        raise HTTPException(status_code=404, detail="Недействительный токен")
    
    token_data = storage.tokens[token]
    
    if token_data["used"]:
        return HTMLResponse("""
        <!DOCTYPE html>
        <html lang="ru">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Голосование</title>
            <style>
                body { font-family: Arial, sans-serif; text-align: center; padding: 20px; background: #f0f2f5; }
                .container { max-width: 400px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
                .message { color: #666; font-size: 18px; }
            </style>
        </head>
        <body>
            <div class="container">
                <h2>Голосование завершено</h2>
                <p class="message">Вы уже проголосовали или голосование закончено.</p>
            </div>
        </body>
        </html>
        """)
    
    session_id = token_data["session_id"]
    voting_info = storage.active_voting.get(session_id)
    
    if not voting_info or voting_info["status"] != "active":
        return HTMLResponse("""
        <!DOCTYPE html>
        <html lang="ru">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Голосование</title>
            <style>
                body { font-family: Arial, sans-serif; text-align: center; padding: 20px; background: #f0f2f5; }
                .container { max-width: 400px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
                .message { color: #666; font-size: 18px; }
            </style>
        </head>
        <body>
            <div class="container">
                <h2>Голосование не активно</h2>
                <p class="message">Голосование еще не началось или уже завершено.</p>
            </div>
        </body>
        </html>
        """)
    
    return HTMLResponse(f"""
    <!DOCTYPE html>
    <html lang="ru">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Голосование - {voting_info['topic_title']}</title>
        <style>
            body {{ 
                font-family: Arial, sans-serif; 
                margin: 0; 
                padding: 20px; 
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
            }}
            .container {{ 
                max-width: 400px; 
                margin: 0 auto; 
                background: white; 
                padding: 30px; 
                border-radius: 15px; 
                box-shadow: 0 10px 30px rgba(0,0,0,0.2);
            }}
            .header {{ margin-bottom: 30px; text-align: center; }}
            .topic-title {{ color: #333; margin-bottom: 10px; font-size: 20px; font-weight: bold; }}
            .presenter {{ color: #666; margin-bottom: 15px; }}
            .description {{ color: #555; font-size: 14px; line-height: 1.4; margin-bottom: 20px; }}
            .timer {{ 
                background: #ff4757; 
                color: white; 
                padding: 10px; 
                border-radius: 8px; 
                font-size: 18px; 
                font-weight: bold; 
                margin-bottom: 30px;
            }}
            .vote-buttons {{ display: flex; flex-direction: column; gap: 15px; }}
            .vote-btn {{ 
                padding: 15px; 
                border: none; 
                border-radius: 10px; 
                font-size: 18px; 
                font-weight: bold; 
                cursor: pointer; 
                transition: all 0.3s ease;
                text-transform: uppercase;
            }}
            .vote-for {{ background: #2ed573; color: white; }}
            .vote-for:hover {{ background: #26b96d; transform: translateY(-2px); }}
            .vote-against {{ background: #ff4757; color: white; }}
            .vote-against:hover {{ background: #e73c3c; transform: translateY(-2px); }}
            .vote-abstain {{ background: #ffa502; color: white; }}
            .vote-abstain:hover {{ background: #e89002; transform: translateY(-2px); }}
            .confirmation {{ 
                display: none; 
                text-align: center; 
                padding: 20px; 
                background: #f1f2f6; 
                border-radius: 10px; 
                margin-top: 20px; 
            }}
            .confirm-btn {{ background: #5352ed; color: white; margin-right: 10px; }}
            .cancel-btn {{ background: #6c757d; color: white; }}
            .confirm-btn:hover {{ background: #3b3ad9; }}
            .cancel-btn:hover {{ background: #545b62; }}
            .success {{ 
                display: none; 
                text-align: center; 
                color: #2ed573; 
                font-size: 20px; 
                font-weight: bold; 
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h2 class="topic-title">{voting_info['topic_title']}</h2>
                <div class="presenter">Докладчик: {voting_info['presenter_name']}</div>
                <div class="description">{voting_info['topic_description']}</div>
                <div class="timer" id="timer">Загрузка...</div>
            </div>
            
            <div id="voting-form">
                <div class="vote-buttons">
                    <button class="vote-btn vote-for" onclick="selectVote('за')">За</button>
                    <button class="vote-btn vote-against" onclick="selectVote('против')">Против</button>
                    <button class="vote-btn vote-abstain" onclick="selectVote('воздержался')">Воздержался</button>
                </div>
                
                <div class="confirmation" id="confirmation">
                    <p>Вы выбрали: <strong id="selected-choice"></strong></p>
                    <p>Подтвердить свой голос?</p>
                    <button class="vote-btn confirm-btn" onclick="confirmVote()">Подтвердить</button>
                    <button class="vote-btn cancel-btn" onclick="cancelVote()">Отменить</button>
                </div>
            </div>
            
            <div class="success" id="success">
                <p>✅ Ваш голос принят!</p>
                <p>Спасибо за участие в голосовании.</p>
            </div>
        </div>

        <script>
            let selectedChoice = '';
            const endTime = {voting_info['end_time']} * 1000;
            
            function updateTimer() {{
                const now = Date.now();
                const remaining = Math.max(0, endTime - now);
                const minutes = Math.floor(remaining / 60000);
                const seconds = Math.floor((remaining % 60000) / 1000);
                
                if (remaining > 0) {{
                    document.getElementById('timer').textContent = 
                        `Осталось времени: ${{minutes}}:${{seconds.toString().padStart(2, '0')}}`;
                }} else {{
                    document.getElementById('timer').textContent = 'Время голосования истекло';
                    document.getElementById('timer').style.background = '#6c757d';
                }}
            }}
            
            setInterval(updateTimer, 1000);
            updateTimer();
            
            function selectVote(choice) {{
                selectedChoice = choice;
                document.getElementById('selected-choice').textContent = choice;
                document.getElementById('confirmation').style.display = 'block';
            }}
            
            function cancelVote() {{
                selectedChoice = '';
                document.getElementById('confirmation').style.display = 'none';
            }}
            
            async function confirmVote() {{
                const formData = new FormData();
                formData.append('token', '{token}');
                formData.append('choice', selectedChoice);
                
                try {{
                    const response = await fetch('/api/vote', {{
                        method: 'POST',
                        body: formData
                    }});
                    
                    if (response.ok) {{
                        document.getElementById('voting-form').style.display = 'none';
                        document.getElementById('success').style.display = 'block';
                    }} else {{
                        const error = await response.json();
                        alert('Ошибка: ' + error.detail);
                    }}
                }} catch (error) {{
                    alert('Ошибка соединения: ' + error.message);
                }}
            }}
        </script>
    </body>
    </html>
    """)

@app.get("/api/sessions/{session_id}/status")
async def get_session_status(session_id: str):
    if session_id not in storage.sessions:
        raise HTTPException(status_code=404, detail="Сессия не найдена")
    
    session_data = storage.sessions[session_id]
    voting_data = storage.active_voting.get(session_id, {})
    
    # Подсчитываем текущие голоса
    current_votes = {"за": 0, "против": 0, "воздержался": 0}
    for vote in storage.votes.get(session_id, []):
        current_votes[vote["choice"]] += 1
    
    return {
        "session": session_data,
        "voting": voting_data,
        "current_votes": current_votes,
        "total_members": len(storage.members.get(session_id, []))
    }

# WebSocket endpoints
@app.websocket("/ws/admin")
async def websocket_admin(websocket: WebSocket):
    await manager.connect(websocket, "admin")
    try:
        while True:
            data = await websocket.receive_text()
            # Обработка сообщений от админа при необходимости
    except WebSocketDisconnect:
        manager.disconnect(websocket, "admin")

@app.websocket("/ws/projector")
async def websocket_projector(websocket: WebSocket):
    await manager.connect(websocket, "projector")
    try:
        while True:
            data = await websocket.receive_text()
            # Обработка сообщений от проектора при необходимости
    except WebSocketDisconnect:
        manager.disconnect(websocket, "projector")

# Статические файлы и страницы
@app.get("/vote")
async def vote_page(token: str):
    return await get_vote_page(token)

@app.get("/admin")
async def admin_page():
    return FileResponse("static/admin.html")

@app.get("/projector")
async def projector_page():
    return FileResponse("static/projector.html")

@app.get("/")
async def root():
    return FileResponse("static/index.html")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
