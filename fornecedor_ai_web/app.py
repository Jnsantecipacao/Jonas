import json
import os
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from secrets import token_urlsafe
from typing import Optional

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

try:
    from zoneinfo import ZoneInfo
except Exception:
    ZoneInfo = None

try:
    from openai import OpenAI
except Exception:
    OpenAI = None

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "respostas.db"
TEMPLATES = Jinja2Templates(directory=str(BASE_DIR / "templates"))

STATUS_ACEITO = "ACEITO"
STATUS_NEGOCIAR = "NEGOCIAR"
STATUS_RECUSADO = "RECUSADO"
ALLOWED_STATUS = {STATUS_ACEITO, STATUS_NEGOCIAR, STATUS_RECUSADO}

CLASSIFIER_PROMPT = (
    "Sua tarefa e analisar a resposta de um fornecedor e classificar em uma das opcoes:\n"
    "- ACEITO\n"
    "- NEGOCIAR\n"
    "- RECUSADO\n\n"
    "Regras:\n"
    "- Se houver concordancia clara -> ACEITO\n"
    "- Se houver tentativa de alterar valor/prazo -> NEGOCIAR\n"
    "- Se houver negativa -> RECUSADO\n\n"
    "Responda apenas com uma palavra: ACEITO, NEGOCIAR ou RECUSADO.\n\n"
    "Texto do fornecedor: {resposta}"
)

APP_TIMEZONE = ZoneInfo("America/Sao_Paulo") if ZoneInfo is not None else None


def now_sp_iso() -> str:
    if APP_TIMEZONE is None:
        return datetime.now().isoformat(timespec="seconds")
    return datetime.now(APP_TIMEZONE).isoformat(timespec="seconds")

app = FastAPI(title="Fornecedor IA Respostas", version="1.0.0")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


class RespostaPayload(BaseModel):
    id_proposta: int
    fornecedor: str
    mensagem_texto: str
    token: str


class PropostaPayload(BaseModel):
    numero_proposta: str
    fornecedor: str
    valor: float
    data_proposta: str


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS propostas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                numero_proposta TEXT NOT NULL,
                fornecedor TEXT NOT NULL,
                valor REAL NOT NULL,
                data_proposta TEXT NOT NULL,
                token TEXT NOT NULL UNIQUE,
                responded INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS respostas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                id_proposta INTEGER NOT NULL,
                fornecedor TEXT NOT NULL,
                mensagem_texto TEXT NOT NULL,
                classificacao_ia TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(id_proposta) REFERENCES propostas(id)
            )
            """
        )


def classify_with_openai(texto: str) -> Optional[str]:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key or OpenAI is None:
        return None

    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    client = OpenAI(api_key=api_key)

    prompt = CLASSIFIER_PROMPT.format(resposta=texto)
    response = client.chat.completions.create(
        model=model,
        temperature=0,
        messages=[
            {"role": "system", "content": "Voce e um classificador de intencao."},
            {"role": "user", "content": prompt},
        ],
    )
    content = (response.choices[0].message.content or "").strip().upper()
    content = re.sub(r"[^A-Z]", "", content)

    if "ACEITO" in content:
        return STATUS_ACEITO
    if "NEGOCIAR" in content or "NEGOCIACAO" in content:
        return STATUS_NEGOCIAR
    if "RECUSADO" in content or "RECUSAR" in content:
        return STATUS_RECUSADO
    return None


def classify_local(texto: str) -> str:
    t = texto.lower()

    aceitar = ["aceito", "concordo", "ok", "de acordo", "pode seguir", "aprovado"]
    negociar = ["negoci", "prazo", "desconto", "valor", "taxa", "podemos ajustar", "proponho"]
    recusar = ["nao aceito", "recuso", "nao concordo", "nao temos interesse", "rejeito", "nao vamos seguir"]

    if any(k in t for k in recusar):
        return STATUS_RECUSADO
    if any(k in t for k in negociar):
        return STATUS_NEGOCIAR
    if any(k in t for k in aceitar):
        return STATUS_ACEITO

    return STATUS_NEGOCIAR


def classify_text(texto: str) -> str:
    via_api = classify_with_openai(texto)
    if via_api in ALLOWED_STATUS:
        return via_api
    return classify_local(texto)


def load_proposta(id_proposta: int) -> Optional[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute("SELECT * FROM propostas WHERE id = ?", (id_proposta,)).fetchone()


def validate_proposta_token(id_proposta: int, token: str) -> sqlite3.Row:
    proposta = load_proposta(id_proposta)
    if not proposta:
        raise HTTPException(status_code=404, detail="Proposta nao encontrada")
    if proposta["token"] != token:
        raise HTTPException(status_code=403, detail="Token invalido")
    if proposta["responded"] == 1:
        raise HTTPException(status_code=409, detail="Proposta ja respondida")
    return proposta


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "time": now_sp_iso()}


@app.post("/propostas", response_class=JSONResponse)
def criar_proposta(payload: PropostaPayload) -> dict:
    tk = token_urlsafe(18)
    now = now_sp_iso()
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO propostas (numero_proposta, fornecedor, valor, data_proposta, token, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                payload.numero_proposta,
                payload.fornecedor,
                payload.valor,
                payload.data_proposta,
                tk,
                now,
            ),
        )
        proposta_id = cur.lastrowid

    base_url = os.getenv("PUBLIC_BASE_URL", "http://localhost:8000").rstrip("/")
    link = f"{base_url}/resposta?id={proposta_id}&token={tk}"
    return {"id": proposta_id, "token": tk, "link": link}


@app.get("/resposta", response_class=HTMLResponse)
def tela_resposta(request: Request, id: int, token: str):
    proposta = validate_proposta_token(id, token)
    return TEMPLATES.TemplateResponse(
        request=request,
        name="chat.html",
        context={
            "proposta": proposta,
            "token": token,
        },
    )


@app.post("/resposta", response_class=JSONResponse)
def responder(payload: RespostaPayload) -> dict:
    proposta = validate_proposta_token(payload.id_proposta, payload.token)

    classificacao = classify_text(payload.mensagem_texto)
    now = now_sp_iso()

    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO respostas (id_proposta, fornecedor, mensagem_texto, classificacao_ia, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (payload.id_proposta, payload.fornecedor, payload.mensagem_texto, classificacao, now),
        )
        conn.execute("UPDATE propostas SET responded = 1 WHERE id = ?", (payload.id_proposta,))

    return {
        "ok": True,
        "id_proposta": payload.id_proposta,
        "fornecedor": proposta["fornecedor"],
        "classificacao": classificacao,
        "mensagem": f"Recebemos sua resposta como: {classificacao}",
        "data_hora": now,
    }


@app.get("/admin/respostas", response_class=JSONResponse)
def listar_respostas(limit: int = 100) -> dict:
    limit = max(1, min(limit, 1000))
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT r.id, r.id_proposta, p.numero_proposta, r.fornecedor,
                     p.token,
                   r.mensagem_texto,
                   r.classificacao_ia AS classificacao,
                   r.created_at AS data_resposta,
                   r.classificacao_ia,
                   r.created_at
            FROM respostas r
            JOIN propostas p ON p.id = r.id_proposta
            ORDER BY r.id DESC
            LIMIT ?
            """
            ,
            (limit,),
        ).fetchall()
    return {"items": [dict(r) for r in rows]}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="0.0.0.0", port=int(os.getenv("PORT", "8000")), reload=True)
