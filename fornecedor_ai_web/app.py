import base64
import json
import os
import re
import socket
import smtplib
import sqlite3
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path
from secrets import token_urlsafe
from typing import Optional

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

try:
    from fpdf import FPDF
except Exception:
    FPDF = None

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
DEFAULT_WHATSAPP = str(os.getenv("WHATSAPP_CONTATO", "") or "").strip() or "11 99462-6366"
DEFAULT_WHATSAPP_URL = "https://wa.me/5511994626366"


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
    taxa_original_pct: Optional[float] = None
    taxa_primeira_contraproposta_pct: Optional[float] = None
    taxa_segunda_contraproposta_pct: Optional[float] = None
    negociacao_max_tentativas: Optional[int] = None
    whatsapp_contato: Optional[str] = None
    instrucao_limite: Optional[str] = None


class PropostaPayload(BaseModel):
    numero_proposta: str
    fornecedor: str
    valor: float
    data_proposta: str
    taxa_desconto: Optional[float] = None
    fornecedor_email: Optional[str] = None
    pdf_filename: Optional[str] = None
    pdf_b64: Optional[str] = None
    cnpj: Optional[str] = None
    data_pagamento: Optional[str] = None
    valor_total: Optional[float] = None
    desconto_total: Optional[float] = None
    valor_pagar: Optional[float] = None
    itens_detalhados: Optional[list[dict]] = None


class SmtpTestPayload(BaseModel):
    to_email: Optional[str] = None


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
                fornecedor_email TEXT,
                valor REAL NOT NULL,
                data_proposta TEXT NOT NULL,
                taxa_desconto REAL,
                token TEXT NOT NULL UNIQUE,
                responded INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            )
            """
        )
        cols = [r[1] for r in conn.execute("PRAGMA table_info(propostas)").fetchall()]
        if "fornecedor_email" not in cols:
            conn.execute("ALTER TABLE propostas ADD COLUMN fornecedor_email TEXT")
        if "pdf_filename" not in cols:
            conn.execute("ALTER TABLE propostas ADD COLUMN pdf_filename TEXT")
        if "pdf_b64" not in cols:
            conn.execute("ALTER TABLE propostas ADD COLUMN pdf_b64 TEXT")
        if "cnpj" not in cols:
            conn.execute("ALTER TABLE propostas ADD COLUMN cnpj TEXT")
        if "data_pagamento" not in cols:
            conn.execute("ALTER TABLE propostas ADD COLUMN data_pagamento TEXT")
        if "valor_total" not in cols:
            conn.execute("ALTER TABLE propostas ADD COLUMN valor_total REAL")
        if "desconto_total" not in cols:
            conn.execute("ALTER TABLE propostas ADD COLUMN desconto_total REAL")
        if "valor_pagar" not in cols:
            conn.execute("ALTER TABLE propostas ADD COLUMN valor_pagar REAL")
        if "itens_detalhados_json" not in cols:
            conn.execute("ALTER TABLE propostas ADD COLUMN itens_detalhados_json TEXT")
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


def _to_float(value: object) -> Optional[float]:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except Exception:
        return None


def _to_int(value: object, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _formatar_taxa(value: Optional[float]) -> str:
    if value is None:
        return "não informada"
    value_float = float(value)
    if abs(value_float - round(value_float)) < 1e-9:
        return f"{int(round(value_float))}%"
    return f"{value_float:.2f}%".replace(".00", "")


def _formatar_moeda(valor: Optional[float]) -> str:
    try:
        v = float(valor or 0.0)
    except Exception:
        v = 0.0
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _build_simple_pdf(lines: list[str]) -> bytes:
    def _esc(text: str) -> str:
        return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    pdf_lines = [
        "BT",
        "/F1 12 Tf",
        "40 800 Td",
    ]
    for idx, line in enumerate(lines):
        if idx > 0:
            pdf_lines.append("0 -18 Td")
        safe = _esc(str(line)).encode("latin-1", "replace").decode("latin-1")
        pdf_lines.append(f"({safe}) Tj")
    pdf_lines.append("ET")
    stream = "\n".join(pdf_lines).encode("latin-1", "replace")

    objs = []
    objs.append(b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n")
    objs.append(b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n")
    objs.append(
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>\nendobj\n"
    )
    objs.append(
        b"4 0 obj\n<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"\nendstream\nendobj\n"
    )
    objs.append(b"5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n")

    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for obj in objs:
        offsets.append(len(out))
        out.extend(obj)

    xref_pos = len(out)
    out.extend(f"xref\n0 {len(offsets)}\n".encode("ascii"))
    out.extend(b"0000000000 65535 f \n")
    for off in offsets[1:]:
        out.extend(f"{off:010d} 00000 n \n".encode("ascii"))

    out.extend(
        (
            "trailer\n"
            f"<< /Size {len(offsets)} /Root 1 0 R >>\n"
            "startxref\n"
            f"{xref_pos}\n"
            "%%EOF\n"
        ).encode("ascii")
    )
    return bytes(out)


def _safe_pdf_text(text: str) -> str:
    if text is None:
        return ""
    s = str(text)
    try:
        s.encode("latin-1")
        return s
    except Exception:
        return s.encode("latin-1", "replace").decode("latin-1")


def _build_layout_pdf_proposta_atualizada(
    proposta: dict,
    valor_base: float,
    taxa_original: Optional[float],
    taxa_final: Optional[float],
    desconto_final: Optional[float],
    valor_liquido_final: Optional[float],
    data_hora: str,
) -> Optional[bytes]:
    if FPDF is None:
        return None

    try:
        pdf = FPDF()
        pdf.add_page()
        pdf.set_auto_page_break(auto=True, margin=15)

        numero = str(proposta.get("numero_proposta", "") or "")
        fornecedor = str(proposta.get("fornecedor", "") or "")
        cnpj = str(proposta.get("cnpj", "") or "").strip()
        if not cnpj:
            m_cnpj = re.match(r"^(\d{14})", numero)
            if m_cnpj:
                cnpj = m_cnpj.group(1)

        data_base_txt = str(proposta.get("data_proposta", "") or "")
        data_pagamento_txt = str(proposta.get("data_pagamento", "") or "")
        data_base_dt = None
        data_pagamento_dt = None
        try:
            data_base_dt = datetime.fromisoformat(data_base_txt[:10])
            data_base_txt = data_base_dt.strftime("%d/%m/%Y")
        except Exception:
            pass
        try:
            if data_pagamento_txt:
                data_pagamento_dt = datetime.fromisoformat(data_pagamento_txt[:10])
                data_pagamento_txt = data_pagamento_dt.strftime("%d/%m/%Y")
        except Exception:
            pass
        if not data_pagamento_txt:
            data_pagamento_txt = data_base_txt or "nao informado"

        prazo_txt = ""
        if data_base_dt is not None and data_pagamento_dt is not None:
            try:
                prazo_txt = str((data_pagamento_dt - data_base_dt).days)
            except Exception:
                prazo_txt = ""

        taxa_txt = _formatar_taxa(taxa_final)
        if taxa_final is not None:
            taxa_txt = f"{float(taxa_final):.2f}%"
        data_aprovacao_txt = data_hora
        try:
            data_aprovacao_txt = datetime.fromisoformat(str(data_hora)).strftime("%d/%m/%Y %H:%M")
        except Exception:
            pass

        itens_detalhados = proposta.get("itens_detalhados") or proposta.get("itens_detalhados_json") or []
        if isinstance(itens_detalhados, str):
            try:
                itens_detalhados = json.loads(itens_detalhados)
            except Exception:
                itens_detalhados = []
        itens_render = []
        total_valor = 0.0
        total_desconto = 0.0
        total_pagar = 0.0
        taxa_calc = float(taxa_final or 0.0)

        for item in itens_detalhados:
            try:
                valor_liquido_item = float(item.get("valor_liquido", 0) or 0)
            except Exception:
                valor_liquido_item = 0.0
            desconto_item = valor_liquido_item * (taxa_calc / 100.0)
            pagar_item = valor_liquido_item - desconto_item
            total_valor += valor_liquido_item
            total_desconto += desconto_item
            total_pagar += pagar_item
            itens_render.append({
                "loja": str(item.get("loja", "") or ""),
                "numero_doc": str(item.get("numero_doc", "") or ""),
                "data_vencimento": str(item.get("data_vencimento", "") or ""),
                "prazo_dias": str(item.get("prazo_dias", "") or ""),
                "valor_liquido": valor_liquido_item,
                "desconto": desconto_item,
                "valor_pagar": pagar_item,
            })

        if itens_render:
            valor_base = total_valor
            desconto_final = total_desconto
            valor_liquido_final = total_pagar

        pdf.set_y(18)
        pdf.set_font("Arial", "B", 16)
        pdf.set_text_color(0, 0, 139)
        pdf.cell(0, 10, "RELATORIO DE ANTECIPACAO", 0, 1, "C")
        pdf.ln(4)
        pdf.set_draw_color(0, 0, 139)
        pdf.set_line_width(0.5)
        pdf.line(10, pdf.get_y(), 200, pdf.get_y())
        pdf.ln(8)

        def campo(label: str, valor: str) -> None:
            pdf.set_font("Arial", "B", 10)
            pdf.cell(32, 6, _safe_pdf_text(label), 0, 0)
            pdf.set_font("Arial", "", 10)
            pdf.cell(0, 6, _safe_pdf_text(valor), 0, 1)

        pdf.set_text_color(0, 0, 0)
        campo("Fornecedor:", fornecedor[:60])
        campo("CNPJ:", cnpj or "nao informado")
        campo("Data Base:", data_base_txt or "nao informado")
        campo("Data Pagamento:", data_pagamento_txt)
        campo("Taxa:", taxa_txt)

        pdf.ln(6)
        col_w = [12, 12, 18, 26, 28, 28, 28, 28]
        headers = ["Seq", "Prazo", "Venc.", "Loja", "N Doc", "Valor R$", "Desc. R$", "Pagar R$"]
        pdf.set_fill_color(200, 220, 255)
        pdf.set_font("Arial", "B", 8)
        for i, h in enumerate(headers):
            pdf.cell(col_w[i], 6, h, 1, 0, "C", 1)
        pdf.ln()

        linhas = itens_render or [{
            "loja": fornecedor[:12].upper() if fornecedor else "-",
            "numero_doc": numero[-6:] if numero else "",
            "data_vencimento": data_pagamento_txt[-8:] if data_pagamento_txt and len(data_pagamento_txt) >= 8 else "",
            "prazo_dias": prazo_txt,
            "valor_liquido": valor_base,
            "desconto": desconto_final,
            "valor_pagar": valor_liquido_final,
        }]

        pdf.set_font("Arial", "", 8)
        for idx, linha in enumerate(linhas, start=1):
            pdf.cell(col_w[0], 6, str(idx), 1, 0, "C")
            pdf.cell(col_w[1], 6, _safe_pdf_text(str(linha.get("prazo_dias", ""))), 1, 0, "C")
            pdf.cell(col_w[2], 6, _safe_pdf_text(str(linha.get("data_vencimento", ""))[:8]), 1, 0, "C")
            pdf.cell(col_w[3], 6, _safe_pdf_text(str(linha.get("loja", ""))[:12].upper()), 1, 0, "L")
            pdf.cell(col_w[4], 6, _safe_pdf_text(str(linha.get("numero_doc", ""))[:10]), 1, 0, "C")
            pdf.cell(col_w[5], 6, _safe_pdf_text(_formatar_moeda(linha.get("valor_liquido", 0))), 1, 0, "R")
            pdf.cell(col_w[6], 6, _safe_pdf_text(_formatar_moeda(linha.get("desconto", 0))), 1, 0, "R")
            pdf.cell(col_w[7], 6, _safe_pdf_text(_formatar_moeda(linha.get("valor_pagar", 0))), 1, 1, "R")

        pdf.ln(2)
        total_col_w = [96, 28, 28, 28]
        pdf.set_font("Arial", "B", 8)
        pdf.set_fill_color(220, 220, 220)
        pdf.cell(total_col_w[0], 6, "Subtotal", 1, 0, "R", 1)
        pdf.cell(total_col_w[1], 6, _safe_pdf_text(_formatar_moeda(valor_base)), 1, 0, "R", 1)
        pdf.cell(total_col_w[2], 6, _safe_pdf_text(_formatar_moeda(desconto_final)), 1, 0, "R", 1)
        pdf.cell(total_col_w[3], 6, _safe_pdf_text(_formatar_moeda(valor_liquido_final)), 1, 1, "R", 1)

        pdf.ln(2)
        pdf.set_font("Arial", "B", 10)
        pdf.set_fill_color(0, 100, 0)
        pdf.set_text_color(255, 255, 255)
        pdf.cell(total_col_w[0], 8, "TOTAL FORNECEDOR", 1, 0, "R", 1)
        pdf.cell(total_col_w[1], 8, _safe_pdf_text(_formatar_moeda(valor_base)), 1, 0, "R", 1)
        pdf.cell(total_col_w[2], 8, _safe_pdf_text(_formatar_moeda(desconto_final)), 1, 0, "R", 1)
        pdf.cell(total_col_w[3], 8, _safe_pdf_text(_formatar_moeda(valor_liquido_final)), 1, 1, "R", 1)
        pdf.set_text_color(0, 0, 0)

        pdf.ln(5)
        pdf.set_font("Arial", "I", 8)
        pdf.set_text_color(70, 70, 70)
        pdf.multi_cell(0, 5, _safe_pdf_text(f"Atualizado apos aceite da contraproposta no chat em {data_aprovacao_txt}."))

        raw = pdf.output(dest="S")
        if isinstance(raw, (bytes, bytearray)):
            return bytes(raw)
        return str(raw).encode("latin-1", "replace")
    except Exception:
        return None


def _gerar_pdf_proposta_atualizada(proposta: dict, regras_negociacao: dict, taxa_aceita: Optional[float], data_hora: str) -> Optional[tuple[str, bytes, str]]:
    try:
        numero = str(proposta.get("numero_proposta", "") or "").strip() or "SEM_NUMERO"
        fornecedor = str(proposta.get("fornecedor", "") or "")
        valor_base = float(proposta.get("valor_total", proposta.get("valor", 0)) or 0)
        taxa_original = _to_float(regras_negociacao.get("taxa_original_pct"))
        taxa_final = _to_float(taxa_aceita)
        if taxa_final is None:
            taxa_final = taxa_original

        desconto_final = None
        valor_liquido_final = None
        if taxa_final is not None:
            desconto_final = valor_base * (taxa_final / 100.0)
            valor_liquido_final = valor_base - desconto_final

        pdf_bytes = _build_layout_pdf_proposta_atualizada(
            proposta,
            valor_base,
            taxa_original,
            taxa_final,
            desconto_final,
            valor_liquido_final,
            data_hora,
        )
        if pdf_bytes is None:
            lines = [
                "PROPOSTA ATUALIZADA - ANTECIPACAO",
                "",
                f"Fornecedor: {fornecedor}",
                f"Numero da proposta: {numero}",
                f"Data/Hora da aprovacao: {data_hora}",
                "",
                f"Valor base da proposta: {_formatar_moeda(valor_base)}",
                f"Taxa original: {_formatar_taxa(taxa_original)}",
                f"Taxa final aprovada: {_formatar_taxa(taxa_final)}",
                f"Desconto final: {_formatar_moeda(desconto_final) if desconto_final is not None else 'nao informado'}",
                f"Valor final a receber: {_formatar_moeda(valor_liquido_final) if valor_liquido_final is not None else 'nao informado'}",
                "",
                "Documento gerado automaticamente a partir da negociacao via chat.",
                "MERCADAO ATACADISTA - MESA DE ANTECIPACAO",
            ]
            pdf_bytes = _build_simple_pdf(lines)

        safe_numero = re.sub(r"[^A-Za-z0-9_.-]", "_", numero)
        filename = f"Proposta_Atualizada_{safe_numero}.pdf"
        return (filename, pdf_bytes, "application/pdf")
    except Exception:
        return None


def _resolver_regras_negociacao(proposta: dict, payload: Optional[RespostaPayload] = None, request: Optional[Request] = None) -> dict:
    taxa_original = None
    taxa_primeira = None
    taxa_segunda = None
    max_tentativas = 2
    whatsapp_contato = DEFAULT_WHATSAPP
    instrucao_limite = "encaminhar_whatsapp"

    if payload is not None:
        taxa_original = _to_float(payload.taxa_original_pct)
        taxa_primeira = _to_float(payload.taxa_primeira_contraproposta_pct)
        taxa_segunda = _to_float(payload.taxa_segunda_contraproposta_pct)
        max_tentativas = max(1, min(2, _to_int(payload.negociacao_max_tentativas, 2)))
        whatsapp_contato = str(payload.whatsapp_contato or "").strip() or whatsapp_contato
        instrucao_limite = str(payload.instrucao_limite or "").strip() or instrucao_limite

    if request is not None:
        qp = request.query_params
        taxa_original = _to_float(qp.get("taxa_original_pct")) if taxa_original is None else taxa_original
        taxa_primeira = _to_float(qp.get("taxa_primeira_contraproposta_pct")) if taxa_primeira is None else taxa_primeira
        taxa_segunda = _to_float(qp.get("taxa_segunda_contraproposta_pct")) if taxa_segunda is None else taxa_segunda
        max_tentativas = max(1, min(2, _to_int(qp.get("negociacao_max_tentativas"), max_tentativas)))
        whatsapp_contato = str(qp.get("whatsapp_contato") or "").strip() or whatsapp_contato
        instrucao_limite = str(qp.get("instrucao_limite") or "").strip() or instrucao_limite

    if taxa_original is None:
        taxa_original = _to_float(proposta.get("taxa_desconto"))
    if taxa_primeira is None and taxa_original is not None:
        taxa_primeira = max(0.0, taxa_original - 1)
    if taxa_segunda is None and taxa_original is not None:
        taxa_segunda = max(0.0, taxa_original - 2)

    return {
        "taxa_original_pct": taxa_original,
        "taxa_primeira_contraproposta_pct": taxa_primeira,
        "taxa_segunda_contraproposta_pct": taxa_segunda,
        "negociacao_max_tentativas": max_tentativas,
        "whatsapp_contato": whatsapp_contato,
        "instrucao_limite": instrucao_limite,
    }


def gerar_saudacao_inicial(regras_negociacao: dict) -> str:
    taxa_original = regras_negociacao.get("taxa_original_pct")
    taxa_primeira = regras_negociacao.get("taxa_primeira_contraproposta_pct")
    whatsapp_contato = regras_negociacao.get("whatsapp_contato") or DEFAULT_WHATSAPP

    if taxa_original is None:
        return "Olá. Você deseja aceitar a proposta atual ou negociar a taxa?"

    return (
        f"Ola! A taxa atual da proposta e {_formatar_taxa(taxa_original)}. "
        f"Se clicar em Quero Negociar, posso oferecer primeiro {_formatar_taxa(taxa_primeira)}. "
        f"Depois disso, seguimos pelo WhatsApp {whatsapp_contato}."
    )


def gerar_resposta_negociacao(regras_negociacao: dict, tentativa: int) -> str:
    taxa_original = regras_negociacao.get("taxa_original_pct")
    taxa_primeira = regras_negociacao.get("taxa_primeira_contraproposta_pct")
    taxa_segunda = regras_negociacao.get("taxa_segunda_contraproposta_pct")
    whatsapp_contato = regras_negociacao.get("whatsapp_contato") or DEFAULT_WHATSAPP
    whatsapp_url = _whatsapp_url(whatsapp_contato)

    if tentativa <= 1 and taxa_primeira is not None:
        return (
            f"Primeira contraproposta: {_formatar_taxa(taxa_primeira)} (taxa original {_formatar_taxa(taxa_original)}). "
            "Você aceita esta condição?"
        )

    if tentativa == 2 and taxa_segunda is not None:
        return (
            f"Consegui avancar um pouco mais. Saindo da taxa original de {_formatar_taxa(taxa_original)}, "
            f"a nossa segunda e ultima contraproposta e {_formatar_taxa(taxa_segunda)}. "
            "Se concordar, clique em Aceito ou responda confirmando o aceite."
        )

    return (
        "Limite automático de negociação atingido. "
        f"Para continuar, fale com nosso time no WhatsApp: {whatsapp_contato}. "
        f"Link: {whatsapp_url}"
    )


def _whatsapp_url(contato: Optional[str] = None) -> str:
    texto = str(contato or "").strip()
    digitos = re.sub(r"\D", "", texto)
    if not digitos:
        return DEFAULT_WHATSAPP_URL
    if digitos.startswith("55"):
        return f"https://wa.me/{digitos}"
    return f"https://wa.me/55{digitos}"


def _contar_tentativas_negociacao(id_proposta: int) -> int:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS total FROM respostas WHERE id_proposta = ? AND classificacao_ia = ?",
            (id_proposta, STATUS_NEGOCIAR),
        ).fetchone()
    return int((row["total"] if row else 0) or 0)


def _taxa_em_oferta(regras_negociacao: dict, tentativas_existentes: int) -> Optional[float]:
    if tentativas_existentes >= 2:
        return regras_negociacao.get("taxa_segunda_contraproposta_pct")
    if tentativas_existentes >= 1:
        return regras_negociacao.get("taxa_primeira_contraproposta_pct")
    return None


def fornecedor_aceitou_sugestao(texto: str) -> bool:
    t = (texto or "").strip().lower()
    if not t:
        return False

    termos_aceite = [
        "aceito",
        "de acordo",
        "concordo",
        "aprovado",
        "pode seguir",
        "fechado",
        "ok",
    ]
    termos_negacao = [
        "não aceito",
        "nao aceito",
        "não concordo",
        "nao concordo",
        "recuso",
        "não",
        "nao",
    ]

    if any(k in t for k in termos_negacao):
        return False
    return any(k in t for k in termos_aceite)


def _enviar_email_refazer_proposta(proposta: dict, regras_negociacao: dict, taxa_aceita: Optional[float], data_hora: str) -> None:
    cfg = _get_smtp_config()
    notify_email = cfg["notify_email"]
    fornecedor_email = str(proposta.get("fornecedor_email", "") or "").strip()

    # 1) Email interno para o financeiro operacionalizar eventual ajuste de documento/PDF.
    assunto_interno = f"[Refazer Proposta] {proposta.get('fornecedor', '')} ({proposta.get('numero_proposta', '')})"
    body_interno = (
        "Negociação concluída no chat com aceite de contraproposta.\n\n"
        "Refazer a proposta e encaminhar ao fornecedor.\n\n"
        f"Numero da proposta: {proposta.get('numero_proposta', '')}\n"
        f"Fornecedor: {proposta.get('fornecedor', '')}\n"
        f"Email fornecedor: {fornecedor_email or 'nao informado'}\n"
        f"Taxa original: {_formatar_taxa(regras_negociacao.get('taxa_original_pct'))}\n"
        f"Taxa aprovada: {_formatar_taxa(taxa_aceita)}\n"
        f"Data e hora: {data_hora}\n"
    )
    if notify_email:
        _send_smtp_email([notify_email], assunto_interno, body_interno)
    else:
        print("Email de notificacao nao configurado no backend web; aviso interno nao enviado.")

    # 2) Email automatico ao fornecedor com a proposta atualizada aprovada no chat.
    if not fornecedor_email:
        print("Fornecedor sem email cadastrado no backend web; reenvio automatico da proposta atualizado nao enviado ao fornecedor.")
        return

    assunto_fornecedor = f"[Proposta Atualizada] {proposta.get('numero_proposta', '')}"
    body_fornecedor = (
        f"Prezado(a) {proposta.get('fornecedor', '')},\n\n"
        "Conforme negociação no chat, sua contraproposta foi aprovada.\n\n"
        f"Numero da proposta: {proposta.get('numero_proposta', '')}\n"
        f"Valor da proposta: R$ {float(proposta.get('valor', 0) or 0):,.2f}\n"
        f"Taxa original: {_formatar_taxa(regras_negociacao.get('taxa_original_pct'))}\n"
        f"Taxa final aprovada: {_formatar_taxa(taxa_aceita)}\n"
        f"Data/hora da aprovacao: {data_hora}\n\n"
        "Esta e a confirmacao automatica por email da proposta atualizada.\n"
        "Nosso time financeiro seguira com a formalizacao e, se aplicavel, envio de documento atualizado.\n\n"
        "MERCADAO ATACADISTA - MESA DE ANTECIPACAO\n"
        "jonas@mercadaoatacadista.com.br | (11) 3791-1130 Ramal 2016\n"
    )

    anexos = []

    # Prioriza anexo realmente atualizado com a taxa aprovada no chat.
    anexo_atualizado = _gerar_pdf_proposta_atualizada(proposta, regras_negociacao, taxa_aceita, data_hora)
    if anexo_atualizado is not None:
        anexos.append(anexo_atualizado)
    else:
        # Fallback: se nao conseguir gerar PDF atualizado, usa o PDF original salvo.
        pdf_b64 = str(proposta.get("pdf_b64", "") or "").strip()
        pdf_filename = str(proposta.get("pdf_filename", "") or "").strip() or "Proposta_Atualizada.pdf"
        if pdf_b64:
            try:
                anexos.append((pdf_filename, base64.b64decode(pdf_b64), "application/pdf"))
            except Exception:
                pass

    _send_smtp_email([fornecedor_email], assunto_fornecedor, body_fornecedor, attachments=anexos)


def load_proposta(id_proposta: int) -> Optional[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute("SELECT * FROM propostas WHERE id = ?", (id_proposta,)).fetchone()


def _env_first(*keys: str) -> str:
    for key in keys:
        val = str(os.getenv(key, "") or "").strip()
        if val:
            return val
    return ""


def _get_smtp_config() -> dict:
    smtp_host = _env_first("SMTP_HOST", "smtp_host")
    smtp_port_raw = _env_first("SMTP_PORT", "smtp_port") or "587"
    smtp_user = _env_first("SMTP_USER", "smtp_user")
    smtp_password = _env_first("SMTP_PASSWORD", "smtp_password")
    notify_email = _env_first(
        "NOTIFY_EMAIL",
        "notify_email",
        "NOTIFYEMAIL",
        "notifyemail",
        "FINANCE_EMAIL",
        "finance_email",
    ) or smtp_user
    smtp_timeout_raw = _env_first("SMTP_TIMEOUT", "smtp_timeout") or "20"

    m = re.search(r"(\d+)", smtp_port_raw)
    smtp_port = int(m.group(1)) if m else 587
    t = re.search(r"(\d+)", smtp_timeout_raw)
    smtp_timeout = int(t.group(1)) if t else 20

    return {
        "smtp_host": smtp_host,
        "smtp_port": smtp_port,
        "smtp_user": smtp_user,
        "smtp_password": smtp_password,
        "notify_email": notify_email,
        "smtp_timeout": max(5, smtp_timeout),
    }


def _send_smtp_email(to_addrs: list[str], subject: str, body: str, attachments: Optional[list[tuple[str, bytes, str]]] = None) -> None:
    cfg = _get_smtp_config()
    if not all([cfg["smtp_host"], cfg["smtp_user"], cfg["smtp_password"], to_addrs]):
        raise RuntimeError("Configuracao SMTP incompleta")

    msg = EmailMessage()
    msg["From"] = cfg["smtp_user"]
    msg["To"] = ", ".join(to_addrs)
    msg["Subject"] = subject
    msg.set_content(body, subtype="plain", charset="utf-8")

    for item in attachments or []:
        try:
            filename, content_bytes, mime = item
            mime_main, mime_sub = str(mime or "application/pdf").split("/", 1)
            msg.add_attachment(content_bytes, maintype=mime_main, subtype=mime_sub, filename=str(filename or "proposta.pdf"))
        except Exception:
            continue

    etapa = "conexao"
    try:
        with smtplib.SMTP(cfg["smtp_host"], cfg["smtp_port"], timeout=cfg["smtp_timeout"]) as server:
            server.ehlo()
            etapa = "starttls"
            server.starttls()
            server.ehlo()
            etapa = "autenticacao"
            server.login(cfg["smtp_user"], cfg["smtp_password"])
            etapa = "envio"
            server.send_message(msg, to_addrs=to_addrs)
    except smtplib.SMTPAuthenticationError as e:
        raise RuntimeError(f"Falha de autenticacao SMTP na etapa {etapa}: verifique usuario e senha") from e
    except smtplib.SMTPConnectError as e:
        raise RuntimeError(f"Falha de conexao SMTP na etapa {etapa}: servidor recusou conexao") from e
    except (socket.timeout, TimeoutError) as e:
        raise RuntimeError(f"Timeout SMTP na etapa {etapa}: servidor demorou para responder") from e
    except OSError as e:
        raise RuntimeError(f"Erro de rede SMTP na etapa {etapa}: {e}") from e
    except smtplib.SMTPException as e:
        raise RuntimeError(f"Erro SMTP na etapa {etapa}: {e}") from e


def _enviar_notificacao_resposta(proposta: dict, classificacao: str, mensagem_final: str, mensagem_fornecedor: str = "") -> None:
    cfg = _get_smtp_config()

    smtp_user = cfg["smtp_user"]
    notify_email = cfg["notify_email"]
    fornecedor_email = str(proposta.get("fornecedor_email", "") or "").strip()

    if not all([cfg["smtp_host"], smtp_user, cfg["smtp_password"], notify_email]):
        print("SMTP incompleto no backend web; notificacao de resposta nao enviada.")
        return

    assunto = f"[RESPOSTA PROPOSTA] {classificacao} - {proposta.get('fornecedor', '')}"
    numero = proposta.get("numero_proposta", "")
    taxa = proposta.get("taxa_desconto", "")
    taxa_confirmada = "nao informada"
    if taxa not in (None, ""):
        try:
            taxa_num = float(str(taxa).replace('%', '').replace(',', '.').strip())
            if taxa_num <= 1:
                taxa_num *= 100
            taxa_str = f"{taxa_num:.2f}".rstrip('0').rstrip('.').replace('.', ',')
            taxa_confirmada = f"{taxa_str}%"
        except Exception:
            taxa_str = str(taxa).strip()
            if taxa_str and '%' not in taxa_str:
                taxa_str = f"{taxa_str}%"
            taxa_confirmada = taxa_str or "nao informada"

    body_lines = [
        "Resposta registrada no portal de propostas.",
        "",
        f"Fornecedor: {proposta.get('fornecedor', '')}",
        f"Email fornecedor: {fornecedor_email or 'nao informado'}",
        f"Proposta: {numero}",
        f"Classificacao: {classificacao}",
        f"Taxa confirmada: {taxa_confirmada}",
        "",
        f"Mensagem final do sistema: {mensagem_final}",
    ]
    if mensagem_fornecedor:
        body_lines.extend(["", f"Mensagem enviada pelo fornecedor: {mensagem_fornecedor}"])

    destinatarios = [notify_email] + ([fornecedor_email] if fornecedor_email else [])

    _send_smtp_email(destinatarios, assunto, "\n".join(body_lines))


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


@app.get("/status")
def status() -> dict:
    return {"status": "ok"}


@app.post("/propostas", response_class=JSONResponse)
def criar_proposta(payload: PropostaPayload) -> dict:
    tk = token_urlsafe(18)
    now = now_sp_iso()
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO propostas (
                numero_proposta,
                fornecedor,
                fornecedor_email,
                cnpj,
                valor,
                valor_total,
                desconto_total,
                valor_pagar,
                data_proposta,
                data_pagamento,
                taxa_desconto,
                pdf_filename,
                pdf_b64,
                itens_detalhados_json,
                token,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload.numero_proposta,
                payload.fornecedor,
                payload.fornecedor_email,
                payload.cnpj,
                payload.valor,
                payload.valor_total,
                payload.desconto_total,
                payload.valor_pagar,
                payload.data_proposta,
                payload.data_pagamento,
                payload.taxa_desconto,
                str(payload.pdf_filename or "").strip() or None,
                str(payload.pdf_b64 or "").strip() or None,
                json.dumps(payload.itens_detalhados or [], ensure_ascii=False),
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
    regras_negociacao = _resolver_regras_negociacao(proposta_dict, request=request)
    resposta_inicial = gerar_saudacao_inicial(regras_negociacao)
    return TEMPLATES.TemplateResponse(
        request=request,
        name="chat.html",
        context={
            "proposta": proposta_dict,
            "token": token,
            "resposta_inicial": resposta_inicial,
            "regras_negociacao": regras_negociacao,
        },
    )


@app.post("/resposta", response_class=JSONResponse)
def responder(payload: RespostaPayload) -> dict:
    try:
        proposta = validate_proposta_token(payload.id_proposta, payload.token)
        
        # Converter proposta para dict para facilitar acesso
        proposta_dict = dict(proposta)
        regras_negociacao = _resolver_regras_negociacao(proposta_dict, payload=payload)
        tentativas_existentes = _contar_tentativas_negociacao(payload.id_proposta)
        finalizada = False
        disparar_email_refazer = False
        taxa_aceita = None
        whatsapp_url = _whatsapp_url(regras_negociacao.get("whatsapp_contato") or DEFAULT_WHATSAPP)

        # Se ação de botão, traduzir para classificação apropriada
        if payload.acao == "aceitar":
            classificacao = STATUS_ACEITO
            finalizada = True
            taxa_aceita = _taxa_em_oferta(regras_negociacao, tentativas_existentes) or regras_negociacao.get("taxa_original_pct")
            disparar_email_refazer = tentativas_existentes > 0
            mensagem_final = (
                "Proposta aprovada. "
                f"Taxa confirmada: {_formatar_taxa(taxa_aceita)}."
            )
        elif payload.acao == "negociar":
            texto_fornecedor = (payload.mensagem_texto or "").strip()

            if texto_fornecedor:
                if fornecedor_aceitou_sugestao(texto_fornecedor):
                    classificacao = STATUS_ACEITO
                    finalizada = True
                    taxa_aceita = _taxa_em_oferta(regras_negociacao, tentativas_existentes)
                    disparar_email_refazer = taxa_aceita is not None
                    mensagem_final = (
                        "Contraproposta aprovada. "
                        f"Taxa final aprovada: {_formatar_taxa(taxa_aceita)}. "
                        "Atendimento finalizado."
                    )
                else:
                    proxima_tentativa = tentativas_existentes + 1
                    if proxima_tentativa <= int(regras_negociacao.get("negociacao_max_tentativas") or 2):
                        classificacao = STATUS_NEGOCIAR
                        mensagem_final = gerar_resposta_negociacao(regras_negociacao, proxima_tentativa)
                    else:
                        classificacao = STATUS_NEGOCIAR
                        finalizada = True
                        mensagem_final = (
                            f"{gerar_resposta_negociacao(regras_negociacao, proxima_tentativa)} "
                            "Use o botão de WhatsApp para continuar."
                        )
            else:
                proxima_tentativa = tentativas_existentes + 1
                classificacao = STATUS_NEGOCIAR
                mensagem_final = gerar_resposta_negociacao(regras_negociacao, proxima_tentativa)
                if proxima_tentativa > int(regras_negociacao.get("negociacao_max_tentativas") or 2):
                    finalizada = True
        elif payload.acao == "recusar":
            classificacao = STATUS_RECUSADO
            finalizada = True
            mensagem_final = (
                "Negociação automática encerrada. "
                f"Para continuar, use o WhatsApp: {regras_negociacao.get('whatsapp_contato') or DEFAULT_WHATSAPP}. "
                f"Link: {whatsapp_url}"
            )
        else:
            # Texto livre - classificar automaticamente
            classificacao = classify_text(payload.mensagem_texto)
            mensagem_final = payload.mensagem_texto
            finalizada = classificacao in {STATUS_ACEITO, STATUS_RECUSADO}

        now = now_sp_iso()

        with get_conn() as conn:
            conn.execute(
                """
                INSERT INTO respostas (id_proposta, fornecedor, mensagem_texto, classificacao_ia, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (payload.id_proposta, payload.fornecedor, mensagem_final, classificacao, now),
            )
            if finalizada:
                conn.execute("UPDATE propostas SET responded = 1 WHERE id = ?", (payload.id_proposta,))

        try:
            if finalizada:
                _enviar_notificacao_resposta(
                    proposta_dict,
                    classificacao,
                    mensagem_final,
                    (payload.mensagem_texto or "").strip(),
                )
            if disparar_email_refazer:
                _enviar_email_refazer_proposta(proposta_dict, regras_negociacao, taxa_aceita, now)
        except Exception as notify_err:
            print(f"Falha ao enviar notificacao por email: {notify_err}")

        return {
            "ok": True,
            "id_proposta": payload.id_proposta,
            "fornecedor": proposta_dict["fornecedor"],
            "classificacao": classificacao,
            "mensagem": mensagem_final,
            "data_hora": now,
            "finalizada": finalizada,
            "etapa_negociacao": tentativas_existentes + (1 if classificacao == STATUS_NEGOCIAR else 0),
            "permite_continuar": not finalizada,
            "whatsapp_url": whatsapp_url if finalizada and classificacao in {STATUS_NEGOCIAR, STATUS_RECUSADO} else None,
        }
    except HTTPException as e:
        # Mantem codigos esperados (ex.: 403/404/409), mas sanitiza detalhe
        # para nao vazar traceback para o frontend.
        if int(getattr(e, "status_code", 500) or 500) == 409:
            raise HTTPException(status_code=409, detail="Proposta ja respondida")

        detalhe = str(getattr(e, "detail", "") or "").strip()
        if "Traceback" in detalhe:
            detalhe = detalhe.split("Traceback", 1)[0].strip()
        if not detalhe:
            detalhe = "Erro ao registrar resposta"

        raise HTTPException(status_code=int(getattr(e, "status_code", 500) or 500), detail=detalhe)
    except Exception as e:
        print(f"Erro inesperado no endpoint /resposta: {e}")
        raise HTTPException(status_code=500, detail="Erro interno ao registrar resposta")


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

    try:
        _enviar_notificacao_resposta(proposta_dict, classificacao, mensagem_final)
    except Exception as notify_err:
        print(f"Falha ao enviar notificacao por email: {notify_err}")

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
    .aviso-box{{background:#f0fdf4;border:1px solid #86efac;border-radius:10px;padding:18px 20px;margin-bottom:24px;color:#166534;font-size:15px;line-height:1.5;font-weight:600}}
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
        <div class="aviso-box">Email enviado. Aguarde retorno do Financeiro.</div>
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


@app.get("/admin/smtp-status", response_class=JSONResponse)
def smtp_status() -> dict:
    cfg = _get_smtp_config()
    return {
        "ok": all([cfg["smtp_host"], cfg["smtp_user"], cfg["smtp_password"], cfg["notify_email"]]),
        "has_smtp_host": bool(cfg["smtp_host"]),
        "has_smtp_port": bool(cfg["smtp_port"]),
        "has_smtp_user": bool(cfg["smtp_user"]),
        "has_smtp_password": bool(cfg["smtp_password"]),
        "has_notify_email": bool(cfg["notify_email"]),
        "notify_email": cfg["notify_email"] or "",
    }


@app.post("/admin/smtp-test", response_class=JSONResponse)
def smtp_test(payload: SmtpTestPayload) -> dict:
    cfg = _get_smtp_config()
    destino = (payload.to_email or cfg["notify_email"] or "").strip()
    if not destino:
        raise HTTPException(status_code=400, detail="Destino de teste nao informado")

    assunto = "[SMTP TESTE] Fornecedor IA Web"
    corpo = (
        "Teste de envio SMTP realizado com sucesso pelo backend web.\n\n"
        f"Horario: {now_sp_iso()}\n"
        "Sistema: Fornecedor IA Respostas"
    )
    try:
        _send_smtp_email([destino], assunto, corpo)
        return {"ok": True, "sent_to": destino}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Falha no envio SMTP: {e}")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="0.0.0.0", port=int(os.getenv("PORT", "8000")), reload=True)
