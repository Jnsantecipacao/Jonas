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
    acao: Optional[str] = None  # "aceitar", "negociar", "recusar"


class PropostaPayload(BaseModel):
    numero_proposta: str
    fornecedor: str
    valor: float
    data_proposta: str
    taxa_desconto: Optional[float] = None


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
                taxa_desconto REAL,
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


def calcular_contraproposta(taxa_atual: float) -> Optional[float]:
    """Calcula a contraproposta aplicando redução de 2 pontos percentuais."""
    if taxa_atual is None:
        return None
    # Não negociar abaixo de 4%
    nova_taxa = taxa_atual - 2
    return max(nova_taxa, 4) if nova_taxa >= 4 else None


def gerar_saudacao_inicial(taxa_desconto: Optional[float]) -> str:
    """Gera saudação inicial variável baseada na taxa de desconto."""
    if taxa_desconto is None:
        return "Olá! Bem-vindo ao sistema de negociação de propostas. Clique em Quero Negociar para sugerir ajustes na taxa."
    elif taxa_desconto > 10:
        return "Taxa elevada detectada. Vamos negociar para encontrar a melhor condição? Clique em Quero Negociar."
    elif taxa_desconto >= 6:
        return "Proposta recebida. Podemos ajustar a taxa se necessário. Use Quero Negociar para sugerir alterações."
    else:
        return "Taxa competitiva! Podemos confirmar esta proposta ou negociar se preferir. Escolha sua opção abaixo."


def gerar_resposta_negociacao(taxa_atual: float) -> str:
    """Gera resposta automática de negociação baseada na taxa."""
    if taxa_atual is None:
        return "Recebi sua proposta e estou à disposição para tratar exclusivamente da taxa de desconto. Se preferir, também podemos seguir pelo WhatsApp: (11) 93239-3849."
    
    # Se já está no mínimo aceitável
    if taxa_atual <= 4:
        return f"Recebi sua proposta com taxa de {taxa_atual}%. Essa condição já está dentro do nosso mínimo aceitável e podemos seguir com a aprovação. Se quiser confirmar por atendimento direto, fale no WhatsApp: (11) 93239-3849."
    
    # Calcular contraproposta (máximo até 4%)
    nova_taxa = max(taxa_atual - 2, 4)
    
    return f"Recebi sua proposta com taxa de {taxa_atual}%. Como contraproposta, podemos seguir com taxa de {nova_taxa}%. Se essa condição não for viável, peço por gentileza que continue o alinhamento pelo WhatsApp: (11) 93239-3849."


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
            INSERT INTO propostas (numero_proposta, fornecedor, valor, data_proposta, taxa_desconto, token, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload.numero_proposta,
                payload.fornecedor,
                payload.valor,
                payload.data_proposta,
                payload.taxa_desconto,
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
    proposta_dict = dict(proposta)
    resposta_negociacao = gerar_resposta_negociacao(proposta_dict.get("taxa_desconto"))
    resposta_inicial = gerar_saudacao_inicial(proposta_dict.get("taxa_desconto"))
    return TEMPLATES.TemplateResponse(
        request=request,
        name="chat.html",
        context={
            "proposta": proposta_dict,
            "token": token,
            "resposta_negociacao": resposta_negociacao,
            "resposta_inicial": resposta_inicial,
        },
    )


@app.post("/resposta", response_class=JSONResponse)
def responder(payload: RespostaPayload) -> dict:
    try:
        proposta = validate_proposta_token(payload.id_proposta, payload.token)
        
        # Converter proposta para dict para facilitar acesso
        proposta_dict = dict(proposta)

        # Se ação de botão, traduzir para classificação apropriada
        if payload.acao == "aceitar":
            classificacao = STATUS_ACEITO
            mensagem_final = "Recebi sua confirmação de aceite. A proposta foi aprovada com sucesso e seguiremos com a formalização dos próximos passos do processo. Caso precise de qualquer alinhamento adicional, nosso atendimento também está disponível pelo WhatsApp: (11) 93239-3849."
        elif payload.acao == "negociar":
            classificacao = STATUS_NEGOCIAR
            mensagem_final = gerar_resposta_negociacao(proposta_dict.get("taxa_desconto"))
        elif payload.acao == "recusar":
            classificacao = STATUS_RECUSADO
            mensagem_final = "Recebi sua sinalização de não aceite. Para tratarmos qualquer nova condição comercial, peço por gentileza que siga o atendimento pelo WhatsApp: (11) 93239-3849."
        else:
            # Texto livre - classificar automaticamente
            classificacao = classify_text(payload.mensagem_texto)
            mensagem_final = payload.mensagem_texto

        now = now_sp_iso()

        with get_conn() as conn:
            conn.execute(
                """
                INSERT INTO respostas (id_proposta, fornecedor, mensagem_texto, classificacao_ia, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (payload.id_proposta, payload.fornecedor, mensagem_final, classificacao, now),
            )
            conn.execute("UPDATE propostas SET responded = 1 WHERE id = ?", (payload.id_proposta,))

        return {
            "ok": True,
            "id_proposta": payload.id_proposta,
            "fornecedor": proposta_dict["fornecedor"],
            "classificacao": classificacao,
            "mensagem": mensagem_final,
            "data_hora": now,
        }
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}\n{tb}")


@app.get("/resposta/{token}/{acao}", response_class=HTMLResponse)
def responder_via_link(token: str, acao: str):
    """Rota acionada pelo clique direto nos botões do email."""
    acao = acao.lower().strip()
    mapa_acao = {"aceito": "aceitar", "aceitar": "aceitar", "negociar": "negociar", "recusar": "recusar", "nao-aceito": "recusar"}
    acao_norm = mapa_acao.get(acao)

    if not acao_norm:
        raise HTTPException(status_code=400, detail="Acao invalida")

    # Buscar proposta pelo token
    with get_conn() as conn:
        proposta = conn.execute("SELECT * FROM propostas WHERE token = ?", (token,)).fetchone()

    if not proposta:
        raise HTTPException(status_code=404, detail="Proposta nao encontrada")

    proposta_dict = dict(proposta)

    if proposta_dict["responded"] == 1:
        return HTMLResponse(content=_html_confirmacao(
            proposta_dict["fornecedor"],
            "Proposta já respondida",
            "Esta proposta já foi respondida anteriormente. Entre em contato pelo WhatsApp: (11) 93239-3849.",
            "#718096", "aviso"
        ))

    if acao_norm == "aceitar":
        classificacao = STATUS_ACEITO
        mensagem_final = "Confirmação de aceite registrada. A proposta foi aprovada e seguiremos com a formalização dos próximos passos. Aguarde o contato do Financeiro."
        titulo = "Aceite Confirmado!"
        cor = "#276749"
        icone = "✅"
    elif acao_norm == "negociar":
        classificacao = STATUS_NEGOCIAR
        mensagem_final = gerar_resposta_negociacao(proposta_dict.get("taxa_desconto"))
        titulo = "Negociação Registrada!"
        cor = "#856404"
        icone = "💬"
    else:
        classificacao = STATUS_RECUSADO
        mensagem_final = "Não aceite registrado. Para tratarmos novas condições comerciais, entre em contato pelo WhatsApp: (11) 93239-3849."
        titulo = "Não Aceite Registrado"
        cor = "#9b1c1c"
        icone = "❌"

    now = now_sp_iso()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO respostas (id_proposta, fornecedor, mensagem_texto, classificacao_ia, created_at) VALUES (?, ?, ?, ?, ?)",
            (proposta_dict["id"], proposta_dict["fornecedor"], mensagem_final, classificacao, now),
        )
        conn.execute("UPDATE propostas SET responded = 1 WHERE id = ?", (proposta_dict["id"],))

    return HTMLResponse(content=_html_confirmacao(proposta_dict["fornecedor"], titulo, mensagem_final, cor, icone))


def _html_confirmacao(fornecedor: str, titulo: str, mensagem: str, cor: str, icone: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Resposta Registrada</title>
  <style>
    *{{box-sizing:border-box;margin:0;padding:0}}
    body{{font-family:'Segoe UI',Arial,sans-serif;background:#f0f2f5;display:flex;align-items:center;justify-content:center;min-height:100vh;padding:24px}}
    .card{{background:#fff;border-radius:16px;padding:48px 40px;max-width:520px;width:100%;box-shadow:0 8px 32px rgba(0,0,0,.12);text-align:center}}
    .icone{{font-size:64px;margin-bottom:16px}}
    h1{{color:#1e3a5f;font-size:24px;margin-bottom:12px}}
    .mensagem{{color:#4a5568;font-size:15px;line-height:1.6;margin-bottom:28px;padding:0 8px}}
    .aviso-box{{background:#f0fdf4;border:1px solid #86efac;border-radius:10px;padding:18px 20px;margin-bottom:24px;color:#166534;font-size:14px;line-height:1.5}}
    .aviso-box strong{{display:block;margin-bottom:6px;font-size:15px}}
    .fornecedor{{color:#718096;font-size:13px;margin-bottom:32px}}
    .footer{{border-top:1px solid #e2e8f0;padding-top:20px;color:#a0aec0;font-size:12px;line-height:1.6}}
    .footer strong{{color:#1e3a5f;display:block;margin-bottom:4px}}
  </style>
</head>
<body>
  <div class="card">
    <div class="icone">{icone}</div>
    <h1>{titulo}</h1>
    <p class="fornecedor">{fornecedor}</p>
    <p class="mensagem">{mensagem}</p>
    <div class="aviso-box">
      <strong>📧 Email enviado com sucesso!</strong>
      Sua resposta foi registrada e o Financeiro será notificado. Aguarde o retorno em breve.
    </div>
    <div class="footer">
      <strong>MERCADÃO ATACADISTA – MESA DE ANTECIPAÇÃO</strong>
      jonas@mercadaoatacadista.com.br &nbsp;|&nbsp; (11) 3791-1130 Ramal 2016
    </div>
  </div>
</body>
</html>"""


@app.get("/admin/respostas", response_class=JSONResponse)
def listar_respostas(limit: int = 100) -> dict:
    limit = max(1, min(limit, 1000))
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT r.id, r.id_proposta, p.numero_proposta, r.fornecedor,
                     p.token, p.taxa_desconto,
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
