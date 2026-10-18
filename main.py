"""Minha Companheira Virtual IA - versao unica (um arquivo) para deploy facil.

Frontend + backend juntos. Ideal para publicar pelo celular: sao poucos
arquivos para enviar ao GitHub. As chaves de API ficam APENAS no servidor
(variaveis de ambiente). Se um provedor nao estiver configurado, a funcao
aparece como 'Precisa conectar' em vez de simular um resultado.
"""
import datetime as dt
import json
import os
import uuid

import bcrypt
import httpx
from fastapi import (APIRouter, BackgroundTasks, Depends, FastAPI, File, Form,
                     Header, HTTPException, UploadFile)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from jose import JWTError, jwt
from pydantic import BaseModel
from sqlalchemy import (Column, DateTime, ForeignKey, Integer, String, Text,
                        create_engine)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


# =========================== Configuracao ===========================
class S:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-me")
    AUTH_ENABLED = os.getenv("AUTH_ENABLED", "false").lower() == "true"
    TOKEN_MIN = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "10080"))
    DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR}/storage/app.db")
    STORAGE_DIR = os.getenv("STORAGE_DIR", f"{BASE_DIR}/storage/media")
    MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "15"))
    PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "")
    MAX_VIDEOS_PER_DAY = int(os.getenv("MAX_VIDEOS_PER_DAY", "30"))
    MAX_CHARS = int(os.getenv("MAX_CHARS_PER_MESSAGE", "2000"))
    LLM_PROVIDER = os.getenv("LLM_PROVIDER", "")
    LLM_API_KEY = os.getenv("LLM_API_KEY", "")
    LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
    LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")
    TTS_PROVIDER = os.getenv("TTS_PROVIDER", "")
    TTS_API_KEY = os.getenv("TTS_API_KEY", "")
    TTS_BASE_URL = os.getenv("TTS_BASE_URL", "https://api.openai.com/v1")
    TTS_MODEL = os.getenv("TTS_MODEL", "gpt-4o-mini-tts")
    TTS_VOICE = os.getenv("TTS_VOICE", "shimmer")
    IMAGE_PROVIDER = os.getenv("IMAGE_PROVIDER", "")
    IMAGE_API_KEY = os.getenv("IMAGE_API_KEY", "")
    IMAGE_BASE_URL = os.getenv("IMAGE_BASE_URL", "")
    IMAGE_MODEL = os.getenv("IMAGE_MODEL", "")
    VIDEO_PROVIDER = os.getenv("VIDEO_PROVIDER", "")
    VIDEO_API_KEY = os.getenv("VIDEO_API_KEY", "")
    VIDEO_BASE_URL = os.getenv("VIDEO_BASE_URL", "")
    VIDEO_MODEL = os.getenv("VIDEO_MODEL", "")
    LIPSYNC_PROVIDER = os.getenv("LIPSYNC_PROVIDER", "")
    LIPSYNC_API_KEY = os.getenv("LIPSYNC_API_KEY", "")
    LIPSYNC_BASE_URL = os.getenv("LIPSYNC_BASE_URL", "")
    LIPSYNC_MODEL = os.getenv("LIPSYNC_MODEL", "")


# =========================== Banco de dados ===========================
connect_args = {"check_same_thread": False} if S.DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(S.DATABASE_URL, connect_args=connect_args)
Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def now():
    return dt.datetime.utcnow()


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True, index=True)
    password_hash = Column(String(255))
    created_at = Column(DateTime, default=now)


class Character(Base):
    __tablename__ = "characters"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, index=True, default=0)
    name = Column(String(120), default="Minha Companheira")
    personality = Column(Text, default="Carinhosa, simpatica, natural e interativa.")
    voice = Column(String(60), default="shimmer")
    speaking_style = Column(Text, default="Fala de forma proxima e afetuosa, em portugues brasileiro.")
    reference_image = Column(String(500), default="")
    consent_confirmed = Column(Integer, default=0)
    created_at = Column(DateTime, default=now)
    updated_at = Column(DateTime, default=now, onupdate=now)
    messages = relationship("Message", back_populates="character", cascade="all, delete-orphan")


class Message(Base):
    __tablename__ = "messages"
    id = Column(Integer, primary_key=True)
    character_id = Column(Integer, ForeignKey("characters.id"), index=True)
    role = Column(String(20))
    text = Column(Text, default="")
    audio_path = Column(String(500), default="")
    video_id = Column(Integer, default=0)
    created_at = Column(DateTime, default=now)
    character = relationship("Character", back_populates="messages")


class VideoJob(Base):
    __tablename__ = "video_jobs"
    id = Column(Integer, primary_key=True)
    character_id = Column(Integer, index=True)
    kind = Column(String(30), default="scene")
    status = Column(String(20), default="queued")
    prompt = Column(Text, default="")
    scene_spec = Column(Text, default="")
    spoken_text = Column(Text, default="")
    output_path = Column(String(500), default="")
    audio_path = Column(String(500), default="")
    error = Column(Text, default="")
    duration = Column(Integer, default=8)
    created_at = Column(DateTime, default=now)
    updated_at = Column(DateTime, default=now, onupdate=now)


def get_db():
    db = Session()
    try:
        yield db
    finally:
        db.close()

# =========================== Provedores de IA ===========================
SYSTEM_TMPL = (
    "Voce e {name}, uma companheira virtual. Personalidade: {p}. Estilo: {s}. "
    "Responda SEMPRE em portugues brasileiro, de forma natural, carinhosa e "
    "interativa; use o contexto anterior; faca perguntas de volta; seja concisa "
    "(1 a 4 frases). Voce e uma IA e nao produz conteudo explicito."
)


def llm_on():
    return bool(S.LLM_PROVIDER and S.LLM_API_KEY)


def tts_on():
    return bool(S.TTS_PROVIDER and S.TTS_API_KEY)


def image_on():
    return bool(S.IMAGE_PROVIDER and S.IMAGE_API_KEY)


def video_on():
    return bool(S.VIDEO_PROVIDER and S.VIDEO_API_KEY)


def lipsync_on():
    return bool(S.LIPSYNC_PROVIDER and S.LIPSYNC_API_KEY)


async def llm_chat(char, history):
    msgs = [{"role": "system", "content": SYSTEM_TMPL.format(
        name=char.name, p=char.personality, s=char.speaking_style)}]
    for m in history:
        if m.get("text"):
            msgs.append({"role": "assistant" if m["role"] == "assistant" else "user",
                         "content": m["text"]})
    payload = {"model": S.LLM_MODEL, "messages": msgs, "temperature": 0.8}
    async with httpx.AsyncClient(timeout=60) as cli:
        r = await cli.post(f"{S.LLM_BASE_URL.rstrip('/')}/chat/completions",
                           json=payload, headers={"Authorization": f"Bearer {S.LLM_API_KEY}"})
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()


async def llm_scene(free_prompt):
    sys = ("Converta o pedido em um JSON de cena para gerar video de uma personagem "
           "feminina. Campos: action, scenario, outfit, expression, body, camera, "
           "duration_seconds, spoken_text. Responda SOMENTE o JSON.")
    payload = {"model": S.LLM_MODEL, "temperature": 0.5,
               "response_format": {"type": "json_object"},
               "messages": [{"role": "system", "content": sys},
                            {"role": "user", "content": free_prompt}]}
    async with httpx.AsyncClient(timeout=60) as cli:
        r = await cli.post(f"{S.LLM_BASE_URL.rstrip('/')}/chat/completions",
                           json=payload, headers={"Authorization": f"Bearer {S.LLM_API_KEY}"})
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()


async def tts_say(text, voice=None):
    payload = {"model": S.TTS_MODEL, "voice": voice or S.TTS_VOICE,
               "input": text, "response_format": "mp3"}
    async with httpx.AsyncClient(timeout=120) as cli:
        r = await cli.post(f"{S.TTS_BASE_URL.rstrip('/')}/audio/speech",
                           json=payload, headers={"Authorization": f"Bearer {S.TTS_API_KEY}"})
        r.raise_for_status()
        return r.content


async def _poll(cli, url, headers, timeout=600):
    waited = 0
    while waited < timeout:
        r = await cli.get(url, headers=headers)
        r.raise_for_status()
        d = r.json()
        st = (d.get("status") or "").lower()
        if st in ("succeeded", "done", "completed", "success"):
            out = d.get("output") or d.get("video_url") or d.get("url")
            return out[0] if isinstance(out, list) else out
        if st in ("failed", "error", "canceled"):
            raise RuntimeError(d.get("error", st))
        import asyncio
        await asyncio.sleep(3)
        waited += 3
    raise RuntimeError("tempo limite excedido")


async def gen_video(image_url, prompt, duration=8):
    headers = {"Authorization": f"Bearer {S.VIDEO_API_KEY}"}
    base = S.VIDEO_BASE_URL.rstrip("/")
    payload = {"model": S.VIDEO_MODEL, "image": image_url, "prompt": prompt, "duration": duration}
    async with httpx.AsyncClient(timeout=120) as cli:
        r = await cli.post(f"{base}/video/generations", json=payload, headers=headers)
        r.raise_for_status()
        d = r.json()
        direct = d.get("output") or d.get("video_url") or d.get("url")
        if direct:
            return direct[0] if isinstance(direct, list) else direct
        tid = d.get("id") or d.get("task_id")
        return await _poll(cli, f"{base}/video/generations/{tid}", headers)


async def gen_lipsync(src_url, audio_url, prompt=""):
    headers = {"Authorization": f"Bearer {S.LIPSYNC_API_KEY}"}
    base = S.LIPSYNC_BASE_URL.rstrip("/")
    payload = {"model": S.LIPSYNC_MODEL, "source": src_url, "audio": audio_url, "prompt": prompt}
    async with httpx.AsyncClient(timeout=120) as cli:
        r = await cli.post(f"{base}/lipsync", json=payload, headers=headers)
        r.raise_for_status()
        d = r.json()
        direct = d.get("output") or d.get("video_url") or d.get("url")
        if direct:
            return direct[0] if isinstance(direct, list) else direct
        tid = d.get("id") or d.get("task_id")
        return await _poll(cli, f"{base}/lipsync/{tid}", headers)


# =========================== Armazenamento ===========================
def _root():
    os.makedirs(S.STORAGE_DIR, exist_ok=True)
    return S.STORAGE_DIR


def save_bytes(data, ext):
    name = f"{uuid.uuid4().hex}.{ext.lstrip('.')}"
    with open(os.path.join(_root(), name), "wb") as f:
        f.write(data)
    return name


async def save_url(url, ext):
    async with httpx.AsyncClient(timeout=300) as cli:
        r = await cli.get(url)
        r.raise_for_status()
        return save_bytes(r.content, ext)


def del_file(name):
    if name:
        p = os.path.join(_root(), name)
        if os.path.exists(p):
            os.remove(p)


def media_url(name):
    base = S.PUBLIC_BASE_URL.rstrip("/") if S.PUBLIC_BASE_URL else ""
    return f"{base}/media/{name}"

# =========================== Tarefa de video (assincrona) ===========================
def scene_to_prompt(spec, char):
    parts = [f"Mulher identica a foto de referencia ({char.name}), preservando rosto, "
             "cabelo, cor dos olhos, tom de pele e tracos."]
    labels = {"action": "Acao", "scenario": "Cenario", "outfit": "Roupa",
              "expression": "Expressao", "body": "Movimento do corpo", "camera": "Camera"}
    for k, lb in labels.items():
        if spec.get(k):
            parts.append(f"{lb}: {spec[k]}.")
    if spec.get("free_prompt"):
        parts.append(spec["free_prompt"])
    parts.append("Movimentos naturais, sem deformacoes no rosto e maos, boa iluminacao.")
    return " ".join(parts)


def _set(db, job, **kw):
    for k, v in kw.items():
        setattr(job, k, v)
    db.add(job)
    db.commit()
    db.refresh(job)


async def run_video_job(job_id):
    db = Session()
    try:
        job = db.get(VideoJob, job_id)
        if not job:
            return
        char = db.get(Character, job.character_id)
        if not char or not char.reference_image:
            _set(db, job, status="error", error="Personagem sem foto de referencia.")
            return
        _set(db, job, status="running")
        image_ref = media_url(char.reference_image)
        audio_name = ""
        if job.spoken_text:
            if tts_on():
                try:
                    audio_name = save_bytes(await tts_say(job.spoken_text, char.voice), "mp3")
                    _set(db, job, audio_path=audio_name)
                except Exception as e:
                    _set(db, job, status="error", error=f"TTS: {e}")
                    return
            elif job.kind == "video_reply":
                _set(db, job, status="not_configured",
                     error="Conecte o TTS para gerar a voz da resposta em video.")
                return
        out_url = None
        try:
            if job.spoken_text and audio_name and lipsync_on() and S.PUBLIC_BASE_URL:
                out_url = await gen_lipsync(image_ref, media_url(audio_name), job.prompt)
            elif video_on() and S.PUBLIC_BASE_URL:
                out_url = await gen_video(image_ref, job.prompt, job.duration)
            else:
                msg = ("Geracao de video nao conectada. Configure VIDEO_PROVIDER "
                       "(e LIPSYNC_PROVIDER para respostas faladas) e PUBLIC_BASE_URL.")
                _set(db, job, status="not_configured", error=msg)
                return
        except Exception as e:
            _set(db, job, status="error", error=f"Video: {e}")
            return
        try:
            vid = await save_url(out_url, "mp4")
        except Exception as e:
            _set(db, job, status="error", error=f"Download: {e}")
            return
        _set(db, job, status="done", output_path=vid)
    finally:
        db.close()


# =========================== Schemas / auth helpers ===========================
class CharacterIn(BaseModel):
    name: str | None = None
    personality: str | None = None
    voice: str | None = None
    speaking_style: str | None = None
    consent_confirmed: bool | None = None


class ChatIn(BaseModel):
    text: str
    mode: str = "text"


class SceneIn(BaseModel):
    action: str = ""
    scenario: str = ""
    outfit: str = ""
    expression: str = ""
    body: str = ""
    spoken_text: str = ""
    duration: int = 8
    camera: str = "selfie"
    free_prompt: str = ""


class AuthIn(BaseModel):
    email: str
    password: str


def hash_pw(pw):
    return bcrypt.hashpw(pw.encode()[:72], bcrypt.gensalt()).decode()


def verify_pw(pw, h):
    try:
        return bcrypt.checkpw(pw.encode()[:72], h.encode())
    except ValueError:
        return False


def make_token(uid):
    exp = now() + dt.timedelta(minutes=S.TOKEN_MIN)
    return jwt.encode({"sub": str(uid), "exp": exp}, S.SECRET_KEY, algorithm="HS256")


def current_user_id(authorization: str = Header(default="")):
    if not S.AUTH_ENABLED:
        return 0
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "Nao autenticado")
    try:
        return int(jwt.decode(authorization.split(" ", 1)[1], S.SECRET_KEY,
                              algorithms=["HS256"])["sub"])
    except (JWTError, KeyError, ValueError):
        raise HTTPException(401, "Token invalido")


def get_char(db=Depends(get_db), uid=Depends(current_user_id)):
    char = db.query(Character).filter(Character.user_id == uid).first()
    if not char:
        char = Character(user_id=uid)
        db.add(char)
        db.commit()
        db.refresh(char)
    return char

# =========================== Rotas ===========================
api = APIRouter(prefix="/api")


def char_out(c):
    return {"id": c.id, "name": c.name, "personality": c.personality, "voice": c.voice,
            "speaking_style": c.speaking_style, "reference_image": c.reference_image,
            "consent_confirmed": c.consent_confirmed}


def msg_out(m):
    return {"id": m.id, "role": m.role, "text": m.text, "audio_path": m.audio_path,
            "video_id": m.video_id, "created_at": m.created_at.isoformat()}


def job_out(j):
    return {"id": j.id, "kind": j.kind, "status": j.status, "prompt": j.prompt,
            "spoken_text": j.spoken_text, "output_path": j.output_path,
            "audio_path": j.audio_path, "error": j.error, "duration": j.duration,
            "created_at": j.created_at.isoformat()}


@api.get("/system/health")
def health():
    return {"status": "ok"}


@api.get("/system/capabilities")
def capabilities():
    return {
        "chat": {"configured": llm_on(), "provider": S.LLM_PROVIDER, "label": "Conversa com IA"},
        "tts": {"configured": tts_on(), "provider": S.TTS_PROVIDER, "label": "Voz feminina (texto em fala)"},
        "image": {"configured": image_on(), "provider": S.IMAGE_PROVIDER, "label": "Gerar roupas/cenarios"},
        "video": {"configured": video_on() and bool(S.PUBLIC_BASE_URL), "provider": S.VIDEO_PROVIDER, "label": "Gerar mini videos"},
        "lipsync": {"configured": lipsync_on() and bool(S.PUBLIC_BASE_URL), "provider": S.LIPSYNC_PROVIDER, "label": "Resposta em video com sincronia labial"},
        "auth_enabled": S.AUTH_ENABLED,
    }


@api.post("/auth/register")
def register(data: AuthIn, db=Depends(get_db)):
    if db.query(User).filter(User.email == data.email).first():
        raise HTTPException(400, "E-mail ja cadastrado.")
    u = User(email=data.email, password_hash=hash_pw(data.password))
    db.add(u); db.commit(); db.refresh(u)
    return {"access_token": make_token(u.id), "token_type": "bearer"}


@api.post("/auth/login")
def login(data: AuthIn, db=Depends(get_db)):
    u = db.query(User).filter(User.email == data.email).first()
    if not u or not verify_pw(data.password, u.password_hash):
        raise HTTPException(401, "Credenciais invalidas.")
    return {"access_token": make_token(u.id), "token_type": "bearer"}


@api.get("/character")
def get_character(char=Depends(get_char)):
    return char_out(char)


@api.put("/character")
def update_character(data: CharacterIn, char=Depends(get_char), db=Depends(get_db)):
    for f in ("name", "personality", "voice", "speaking_style"):
        v = getattr(data, f)
        if v is not None:
            setattr(char, f, v)
    if data.consent_confirmed is not None:
        char.consent_confirmed = 1 if data.consent_confirmed else 0
    db.add(char); db.commit(); db.refresh(char)
    return char_out(char)


@api.post("/character/photo")
async def upload_photo(file: UploadFile = File(...), consent: bool = Form(False),
                       char=Depends(get_char), db=Depends(get_db)):
    if file.content_type not in {"image/png", "image/jpeg", "image/webp"}:
        raise HTTPException(400, "Envie uma imagem PNG, JPEG ou WEBP.")
    data = await file.read()
    if len(data) > S.MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(400, f"Imagem acima de {S.MAX_UPLOAD_MB} MB.")
    if not consent:
        raise HTTPException(400, "Confirme que a personagem e ficticia ou que voce tem "
                                 "autorizacao da pessoa retratada.")
    if char.reference_image:
        del_file(char.reference_image)
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in (file.filename or "") else "png"
    char.reference_image = save_bytes(data, ext)
    char.consent_confirmed = 1
    db.add(char); db.commit(); db.refresh(char)
    return char_out(char)


@api.get("/chat/history")
def chat_history(char=Depends(get_char), db=Depends(get_db)):
    ms = db.query(Message).filter(Message.character_id == char.id).order_by(Message.id.asc()).all()
    return [msg_out(m) for m in ms]


@api.delete("/chat/history")
def chat_clear(char=Depends(get_char), db=Depends(get_db)):
    db.query(Message).filter(Message.character_id == char.id).delete()
    db.commit()
    return {"ok": True}


@api.post("/chat/send")
async def chat_send(data: ChatIn, background: BackgroundTasks, char=Depends(get_char), db=Depends(get_db)):
    text = (data.text or "").strip()
    if not text:
        raise HTTPException(400, "Mensagem vazia.")
    if len(text) > S.MAX_CHARS:
        raise HTTPException(400, "Mensagem muito longa.")
    if not llm_on():
        raise HTTPException(503, "Conversa com IA nao conectada. Configure LLM_PROVIDER/LLM_API_KEY.")
    db.add(Message(character_id=char.id, role="user", text=text)); db.commit()
    hist = db.query(Message).filter(Message.character_id == char.id).order_by(Message.id.asc()).all()
    try:
        reply = await llm_chat(char, [{"role": m.role, "text": m.text} for m in hist])
    except Exception as e:
        raise HTTPException(502, f"Falha no LLM: {e}")
    a = Message(character_id=char.id, role="assistant", text=reply)
    db.add(a); db.commit(); db.refresh(a)
    res = {"reply": msg_out(a)}
    if data.mode == "audio" and tts_on():
        try:
            a.audio_path = save_bytes(await tts_say(reply, char.voice), "mp3")
            db.add(a); db.commit()
            res["reply"]["audio_path"] = a.audio_path
        except Exception:
            res["audio_warning"] = "TTS indisponivel."
    if data.mode == "video":
        job = VideoJob(character_id=char.id, kind="video_reply", status="queued",
                       prompt=f"{char.name} falando de forma natural, olhando para a camera.",
                       spoken_text=reply, duration=min(max(len(reply) // 15, 5), 15))
        db.add(job); db.commit(); db.refresh(job)
        a.video_id = job.id; db.add(a); db.commit()
        res["reply"]["video_id"] = job.id
        background.add_task(run_video_job, job.id)
    return res


@api.post("/chat/audio")
async def chat_audio(file: UploadFile = File(...), char=Depends(get_char), db=Depends(get_db)):
    name = save_bytes(await file.read(), "webm")
    m = Message(character_id=char.id, role="user", text="[audio enviado]", audio_path=name)
    db.add(m); db.commit(); db.refresh(m)
    return {"ok": True, "message": msg_out(m),
            "note": "Conecte um provedor de transcricao para converter o audio em texto."}


def _check_limit(db, char):
    today = dt.datetime.combine(now().date(), dt.time.min)
    n = db.query(VideoJob).filter(VideoJob.character_id == char.id,
                                  VideoJob.created_at >= today).count()
    if n >= S.MAX_VIDEOS_PER_DAY:
        raise HTTPException(429, "Limite diario de videos atingido.")


@api.post("/scene/create")
async def scene_create(data: SceneIn, background: BackgroundTasks, char=Depends(get_char), db=Depends(get_db)):
    if not char.reference_image:
        raise HTTPException(400, "Envie primeiro a foto da personagem.")
    _check_limit(db, char)
    spec = data.model_dump()
    job = VideoJob(character_id=char.id, kind="scene", status="queued",
                   prompt=scene_to_prompt(spec, char),
                   scene_spec=json.dumps(spec, ensure_ascii=False),
                   spoken_text=(data.spoken_text or "").strip(),
                   duration=min(max(int(data.duration or 8), 3), 60))
    db.add(job); db.commit(); db.refresh(job)
    background.add_task(run_video_job, job.id)
    return job_out(job)


@api.post("/scene/command")
async def scene_command(payload: dict, background: BackgroundTasks, char=Depends(get_char), db=Depends(get_db)):
    command = (payload.get("command") or "").strip()
    if not command:
        raise HTTPException(400, "Descreva o que a personagem deve fazer.")
    if not char.reference_image:
        raise HTTPException(400, "Envie primeiro a foto da personagem.")
    _check_limit(db, char)
    spec = {"free_prompt": command}
    spoken = ""
    if llm_on():
        try:
            parsed = json.loads(await llm_scene(command))
            spec.update({k: v for k, v in parsed.items() if isinstance(v, str)})
            spoken = parsed.get("spoken_text", "") or ""
        except Exception:
            pass
    job = VideoJob(character_id=char.id, kind="scene", status="queued",
                   prompt=scene_to_prompt(spec, char),
                   scene_spec=json.dumps(spec, ensure_ascii=False), spoken_text=spoken,
                   duration=min(max(int(spec.get("duration_seconds", 8) or 8), 3), 60))
    db.add(job); db.commit(); db.refresh(job)
    background.add_task(run_video_job, job.id)
    return job_out(job)


@api.get("/scene/job/{job_id}")
def scene_job(job_id: int, char=Depends(get_char), db=Depends(get_db)):
    j = db.get(VideoJob, job_id)
    if not j or j.character_id != char.id:
        raise HTTPException(404, "Job nao encontrado.")
    return job_out(j)


@api.get("/gallery")
def gallery(char=Depends(get_char), db=Depends(get_db)):
    js = db.query(VideoJob).filter(VideoJob.character_id == char.id).order_by(VideoJob.id.desc()).all()
    return [job_out(j) for j in js]


@api.delete("/gallery/{job_id}")
def gallery_del(job_id: int, char=Depends(get_char), db=Depends(get_db)):
    j = db.get(VideoJob, job_id)
    if not j or j.character_id != char.id:
        raise HTTPException(404, "Video nao encontrado.")
    del_file(j.output_path); del_file(j.audio_path)
    db.delete(j); db.commit()
    return {"ok": True}


# =========================== App ===========================
app = FastAPI(title="Minha Companheira Virtual IA", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])
app.include_router(api)


@app.on_event("startup")
def _startup():
    Base.metadata.create_all(bind=engine)
    os.makedirs(S.STORAGE_DIR, exist_ok=True)


os.makedirs(S.STORAGE_DIR, exist_ok=True)
app.mount("/media", StaticFiles(directory=S.STORAGE_DIR), name="media")


@app.get("/")
def index():
    return FileResponse(os.path.join(BASE_DIR, "index.html"))
