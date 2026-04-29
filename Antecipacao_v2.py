import pandas as pd # type: ignore
from datetime import datetime, timezone
import tkinter as tk
import tkinter.font as tkfont
from tkinter import filedialog, messagebox, ttk
import os
import sys
import traceback
from fpdf import FPDF # type: ignore
from PIL import Image, ImageTk # type: ignore
import tempfile
import json
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders
import re
import socket
import base64
import mimetypes
import unicodedata
import threading
import uuid
import shutil
import urllib.request
import urllib.error
import urllib.parse

try:
    from zoneinfo import ZoneInfo
except Exception:
    ZoneInfo = None

import matplotlib # type: ignore
matplotlib.use('TkAgg')
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg # type: ignore
from matplotlib.figure import Figure # type: ignore

try:
    from flask import Flask, request as flask_request # type: ignore
    FLASK_AVAILABLE = True
except ImportError:
    FLASK_AVAILABLE = False

try:
    from pyngrok import ngrok # type: ignore
    NGROK_AVAILABLE = True
except ImportError:
    NGROK_AVAILABLE = False

if os.name == 'nt':
    import ctypes
    from ctypes import wintypes

# ==============================================
# Constantes e Caminhos
# ==============================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
EMAIL_CONFIG_FILE = os.path.join(BASE_DIR, 'email_config.json')
FORNECEDOR_EMAILS_FILE = os.path.join(BASE_DIR, 'fornecedor_emails.json')
PROPOSTAS_FILE = os.path.join(BASE_DIR, 'propostas.json')
PROPOSTAS_ACEITAS_DIR = os.path.join(BASE_DIR, 'Propostas_Aceitas')
SERVER_CONFIG_FILE = os.path.join(BASE_DIR, 'server_config.json')

# ==============================================
# Paleta de Cores (baseada na imagem do modelo)
# ==============================================
SIDEBAR_BG    = '#1e3a5f'
SIDEBAR_HOVER = '#2d5282'
ACCENT_ORANGE = '#f6a623'
ACCENT_BLUE   = '#4a90d9'
MAIN_BG       = '#f0f2f5'
CARD_BG       = '#ffffff'
TEXT_WHITE    = '#ffffff'
TEXT_DARK     = '#2d3748'
TEXT_GRAY     = '#718096'
SUCCESS_COLOR = '#48bb78'
DANGER_COLOR  = '#e53e3e'
WARN_COLOR    = '#ed8936'

UI_FONT_STACK = ('Segoe UI', 'Open Sans', 'Roboto', 'Arial')

_TK_SCALING_APPLIED = False
_TK_SCALING_VALUE = None
_PUBLIC_TUNNEL_URL = None
_LAST_PUBLIC_TUNNEL_ERROR = ''
SP_TIMEZONE = ZoneInfo('America/Sao_Paulo') if ZoneInfo is not None else timezone.utc


def _clamp(value, minimum, maximum):
    return max(minimum, min(value, maximum))


def _is_local_base_url(url):
    valor = str(url or '').strip().lower()
    if not valor:
        return True
    return (
        '://localhost' in valor
        or '://127.0.0.1' in valor
        or valor.startswith('localhost:')
        or valor.startswith('127.0.0.1:')
    )


def _ensure_public_base_url(port, ngrok_authtoken=''):
    """Tenta abrir um tunel publico via ngrok para a porta local do Flask."""
    global _PUBLIC_TUNNEL_URL, _LAST_PUBLIC_TUNNEL_ERROR

    if _PUBLIC_TUNNEL_URL:
        return _PUBLIC_TUNNEL_URL
    if not NGROK_AVAILABLE:
        _LAST_PUBLIC_TUNNEL_ERROR = 'pyngrok nao instalado.'
        return None

    try:
        token = str(ngrok_authtoken or '').strip() or os.getenv('NGROK_AUTHTOKEN', '').strip()
        if token:
            ngrok.set_auth_token(token)
        tunel = ngrok.connect(addr=int(port), proto='http')
        _PUBLIC_TUNNEL_URL = str(getattr(tunel, 'public_url', '') or '').strip()
        if _PUBLIC_TUNNEL_URL:
            _LAST_PUBLIC_TUNNEL_ERROR = ''
            print(f"URL publica ngrok ativa: {_PUBLIC_TUNNEL_URL}")
            return _PUBLIC_TUNNEL_URL
    except Exception as e:
        _LAST_PUBLIC_TUNNEL_ERROR = str(e)
        print(f"Nao foi possivel criar tunel ngrok: {e}")

    return None


def _normalizar_base_url(url):
    return str(url or '').strip().rstrip('/')


def _criar_link_resposta_ia(ai_base_url, numero_proposta, fornecedor, valor, data_proposta, taxa_desconto=None, fornecedor_email=''):
    base = _normalizar_base_url(ai_base_url)
    if not base:
        return None

    endpoint = f"{base}/propostas"
    payload = {
        'numero_proposta': str(numero_proposta),
        'fornecedor': str(fornecedor),
        'valor': float(valor or 0),
        'data_proposta': str(data_proposta),
        'taxa_desconto': float(taxa_desconto) if taxa_desconto is not None else None,
        'fornecedor_email': str(fornecedor_email or '').strip() or None,
    }
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(
        endpoint,
        data=data,
        headers={'Content-Type': 'application/json'},
        method='POST',
    )

    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            body = resp.read().decode('utf-8', errors='ignore')
            parsed = json.loads(body)
            link = str(parsed.get('link', '') or '').strip()
            return link or None
    except Exception as e:
        print(f'Nao foi possivel criar link IA em {endpoint}: {e}')
        return None


def enable_high_dpi_support():
    if os.name != 'nt':
        return

    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        return
    except Exception:
        pass

    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
        return
    except Exception:
        pass

    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


def get_display_metrics(root):
    screen_width = max(root.winfo_screenwidth(), 1)
    screen_height = max(root.winfo_screenheight(), 1)

    try:
        dpi = float(root.winfo_fpixels('1i'))
    except Exception:
        dpi = 96.0

    dpi_scale = _clamp(dpi / 96.0, 1.0, 1.75)
    resolution_scale = _clamp(min(screen_width / 1920.0, screen_height / 1080.0), 1.0, 1.35)
    ui_scale = _clamp(max(dpi_scale, resolution_scale), 1.0, 1.5)
    tk_scale = _clamp(dpi / 72.0, 1.0, 2.5)

    return {
        'screen_width': screen_width,
        'screen_height': screen_height,
        'dpi': dpi,
        'dpi_scale': dpi_scale,
        'ui_scale': ui_scale,
        'tk_scale': tk_scale,
    }


def apply_tk_scaling_once(root, tk_scale):
    global _TK_SCALING_APPLIED, _TK_SCALING_VALUE
    if _TK_SCALING_APPLIED:
        return _TK_SCALING_VALUE

    target_scale = _clamp(float(tk_scale or 1.0), 1.0, 2.5)
    try:
        root.tk.call('tk', 'scaling', target_scale)
        _TK_SCALING_VALUE = target_scale
    except Exception:
        _TK_SCALING_VALUE = 1.0

    _TK_SCALING_APPLIED = True
    return _TK_SCALING_VALUE


def _resolve_ui_font_family(root):
    try:
        available = {name.lower(): name for name in tkfont.families(root)}
    except Exception:
        available = {}

    for candidate in UI_FONT_STACK:
        resolved = available.get(candidate.lower())
        if resolved:
            return resolved

    try:
        return tkfont.nametofont('TkDefaultFont', root=root).cget('family')
    except Exception:
        return 'Arial'


def configure_ui_fonts(root, ui_scale=1.0, size_boost=1.0):
    family = _resolve_ui_font_family(root)

    def scaled_font(size, weight='normal'):
        scaled_size = max(8, int(round(size * ui_scale * size_boost)))
        return (family, scaled_size, weight) if weight != 'normal' else (family, scaled_size)

    fonts = {
        'body': scaled_font(10),
        'body_bold': scaled_font(10, 'bold'),
        'body_small': scaled_font(9),
        'body_small_bold': scaled_font(9, 'bold'),
        'body_large': scaled_font(11, 'bold'),
        'heading': scaled_font(12, 'bold'),
        'title': scaled_font(18, 'bold'),
        'metric': scaled_font(22, 'bold'),
        'button': scaled_font(10, 'bold'),
        'nav': scaled_font(10),
        'nav_icon': scaled_font(14),
        'avatar': scaled_font(16, 'bold'),
        'tab': scaled_font(10, 'bold'),
    }

    named_fonts = {
        'TkDefaultFont': fonts['body'],
        'TkTextFont': fonts['body'],
        'TkMenuFont': fonts['body'],
        'TkHeadingFont': fonts['body_bold'],
        'TkCaptionFont': fonts['body_small_bold'],
        'TkSmallCaptionFont': fonts['body_small'],
        'TkIconFont': fonts['body'],
        'TkTooltipFont': fonts['body_small'],
    }
    for named_font, config in named_fonts.items():
        try:
            tkfont.nametofont(named_font, root=root).configure(
                family=config[0], size=config[1], weight=config[2] if len(config) > 2 else 'normal'
            )
        except Exception:
            pass

    return fonts


_MOJIBAKE_MARKERS = ('Ã', 'â', 'ð', 'ï', 'œ', 'š', 'Â')


def corrigir_texto_exibicao(valor):
    if not isinstance(valor, str) or not valor:
        return valor

    texto = valor
    if any(marker in texto for marker in _MOJIBAKE_MARKERS):
        try:
            texto_corrigido = texto.encode('latin1').decode('utf-8')
            if texto_corrigido:
                texto = texto_corrigido
        except Exception:
            pass

    return texto


def aplicar_correcao_global_textos():
    def _patch_widget_init(widget_cls):
        original_init = widget_cls.__init__

        def patched_init(self, master=None, cnf=None, **kw):
            if cnf is None:
                cnf = {}
            if isinstance(cnf, dict) and 'text' in cnf:
                cnf = dict(cnf)
                cnf['text'] = corrigir_texto_exibicao(cnf['text'])
            if 'text' in kw:
                kw['text'] = corrigir_texto_exibicao(kw['text'])
            try:
                return original_init(self, master, cnf, **kw)
            except TypeError:
                merged = dict(cnf) if isinstance(cnf, dict) else {}
                merged.update(kw)
                return original_init(self, master, **merged)

        widget_cls.__init__ = patched_init

    def _patch_messagebox(function_name):
        original_fn = getattr(messagebox, function_name)

        def patched_fn(title=None, message=None, *args, **kwargs):
            title = corrigir_texto_exibicao(title)
            message = corrigir_texto_exibicao(message)
            if 'title' in kwargs:
                kwargs['title'] = corrigir_texto_exibicao(kwargs['title'])
            if 'message' in kwargs:
                kwargs['message'] = corrigir_texto_exibicao(kwargs['message'])
            return original_fn(title, message, *args, **kwargs)

        setattr(messagebox, function_name, patched_fn)

    _patch_widget_init(tk.Label)
    _patch_widget_init(tk.Button)

    original_heading = ttk.Treeview.heading

    def patched_heading(self, column, option=None, **kw):
        if 'text' in kw:
            kw['text'] = corrigir_texto_exibicao(kw['text'])
        return original_heading(self, column, option, **kw)

    ttk.Treeview.heading = patched_heading

    original_notebook_add = ttk.Notebook.add

    def patched_notebook_add(self, child, **kw):
        if 'text' in kw:
            kw['text'] = corrigir_texto_exibicao(kw['text'])
        return original_notebook_add(self, child, **kw)

    ttk.Notebook.add = patched_notebook_add

    for function_name in ('showinfo', 'showwarning', 'showerror', 'askyesno', 'askokcancel'):
        _patch_messagebox(function_name)

# ==============================================
# UtilitÃ¡rios
# ==============================================
def normalizar_cnpj(valor):
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return ""
    try:
        if isinstance(valor, float):
            bruto = str(int(valor)) if valor == int(valor) else str(valor)
        elif isinstance(valor, int):
            bruto = str(valor)
        else:
            bruto = str(valor).strip()
        if re.fullmatch(r'\d+\.0+', bruto):
            bruto = bruto.split('.')[0]
        cnpj = re.sub(r'\D', '', bruto)
        if not cnpj:
            return ""
        if len(cnpj) > 14:
            cnpj = cnpj[-14:]
        return cnpj.zfill(14)
    except Exception:
        return ""

# ==============================================
# DPAPI â€“ criptografia Windows
# ==============================================
if os.name == 'nt':
    class DATA_BLOB(ctypes.Structure):
        _fields_ = [('cbData', wintypes.DWORD), ('pbData', ctypes.POINTER(ctypes.c_char))]

def _encrypt_password_windows(password):
    if not password or os.name != 'nt':
        return None
    try:
        data = password.encode('utf-8')
        buf = ctypes.create_string_buffer(data, len(data))
        blob_in = DATA_BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
        blob_out = DATA_BLOB()
        ok = ctypes.windll.crypt32.CryptProtectData(
            ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out))
        if not ok:
            return None
        enc = ctypes.string_at(blob_out.pbData, blob_out.cbData)
        ctypes.windll.kernel32.LocalFree(blob_out.pbData)
        return base64.b64encode(enc).decode('ascii')
    except Exception:
        return None

def _decrypt_password_windows(enc_pw):
    if not enc_pw or os.name != 'nt':
        return None
    try:
        enc_bytes = base64.b64decode(enc_pw)
        buf = ctypes.create_string_buffer(enc_bytes, len(enc_bytes))
        blob_in = DATA_BLOB(len(enc_bytes), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
        blob_out = DATA_BLOB()
        ok = ctypes.windll.crypt32.CryptUnprotectData(
            ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out))
        if not ok:
            return None
        dec = ctypes.string_at(blob_out.pbData, blob_out.cbData)
        ctypes.windll.kernel32.LocalFree(blob_out.pbData)
        return dec.decode('utf-8')
    except Exception:
        return None

# ==============================================
# ConfiguraÃ§Ãµes SMTP
# ==============================================
def load_email_config():
    if os.path.exists(EMAIL_CONFIG_FILE):
        with open(EMAIL_CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_email_config(config):
    with open(EMAIL_CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=4)

def get_smtp_credentials():
    config = load_email_config()
    senha = os.getenv('ANTECIPACAO_SMTP_PASSWORD', '').strip() or None
    if not senha:
        senha_enc = config.get('smtp_password_encrypted')
        if senha_enc:
            senha = _decrypt_password_windows(senha_enc)
        if not senha and config.get('smtp_password'):
            senha = config.get('smtp_password')
            enc = _encrypt_password_windows(senha)
            if enc:
                config['smtp_password_encrypted'] = enc
                config.pop('smtp_password', None)
                save_email_config(config)
    return (config.get('smtp_server'), config.get('smtp_port'),
            config.get('smtp_user'), senha)

def set_smtp_credentials(server, port, user, password):
    config = {'smtp_server': server, 'smtp_port': port, 'smtp_user': user}
    enc = _encrypt_password_windows(password)
    if enc:
        config['smtp_password_encrypted'] = enc
    elif password:
        config['smtp_password'] = password
    save_email_config(config)

def get_envio_aceitas_pref():
    config = load_email_config()
    return {
        'emails_aceitas_dia': str(config.get('emails_aceitas_dia', '') or ''),
        'salvar_emails_aceitas_automaticamente': bool(config.get('salvar_emails_aceitas_automaticamente', True)),
    }

def save_envio_aceitas_pref(emails_aceitas_dia=None, salvar_emails_aceitas_automaticamente=None):
    config = load_email_config()
    if emails_aceitas_dia is not None:
        config['emails_aceitas_dia'] = str(emails_aceitas_dia)
    if salvar_emails_aceitas_automaticamente is not None:
        config['salvar_emails_aceitas_automaticamente'] = bool(salvar_emails_aceitas_automaticamente)
    save_email_config(config)

def get_fornecedor_email_pref():
    config = load_email_config()
    return {
        'fornecedor_key': str(config.get('fornecedor_key', '') or ''),
        'fornecedor_email': str(config.get('fornecedor_email', '') or ''),
        'salvar_email_fornecedor_automaticamente': bool(config.get('salvar_email_fornecedor_automaticamente', True)),
    }

def save_fornecedor_email_pref(fornecedor_key=None, fornecedor_email=None, salvar_email_fornecedor_automaticamente=None):
    config = load_email_config()
    if fornecedor_key is not None:
        config['fornecedor_key'] = str(fornecedor_key)
    if fornecedor_email is not None:
        config['fornecedor_email'] = str(fornecedor_email)
    if salvar_email_fornecedor_automaticamente is not None:
        config['salvar_email_fornecedor_automaticamente'] = bool(salvar_email_fornecedor_automaticamente)
    save_email_config(config)

# ==============================================
# ConfiguraÃ§Ã£o do Servidor de Respostas
# ==============================================
def load_server_config():
    """Carrega configuraÃ§Ã£o do servidor.
    Se em produÃ§Ã£o (Railway), detecta automaticamente.
    """
    # Detecta se estÃ¡ em Railway
    railway_url = os.getenv('RAILWAY_URL', '')
    if railway_url:
        return {
            'base_url': railway_url,
            'port': int(os.getenv('PORT', 5000)),
            'ngrok_authtoken': str(os.getenv('NGROK_AUTHTOKEN', '') or '')
        }
    
    # Tenta carregar arquivo local
    if os.path.exists(SERVER_CONFIG_FILE):
        with open(SERVER_CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    # PadrÃ£o para desenvolvimento local
    return {'base_url': 'http://localhost:5001', 'port': 5001, 'ngrok_authtoken': ''}

def save_server_config(config):
    """Salva configuraÃ§Ã£o do servidor (ignorado em produÃ§Ã£o)."""
    if os.getenv('RAILWAY_URL'):
        print("âš ï¸ Em produÃ§Ã£o (Railway) - configuraÃ§Ã£o nÃ£o serÃ¡ salva localmente.")
        return
    
    merged = load_server_config()
    merged.update(config or {})
    with open(SERVER_CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(merged, f, indent=4)

# ==============================================
# Emails de Fornecedores
# ==============================================
def load_email_map():
    if os.path.exists(FORNECEDOR_EMAILS_FILE):
        with open(FORNECEDOR_EMAILS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_email_map(email_map):
    with open(FORNECEDOR_EMAILS_FILE, 'w', encoding='utf-8') as f:
        json.dump(email_map, f, indent=4, ensure_ascii=False)

def add_email_fornecedor(cnpj_key, email):
    m = load_email_map()
    m[cnpj_key] = email
    save_email_map(m)

def get_email_fornecedor(chave):
    m = load_email_map()
    if not chave:
        return None
    chave = str(chave).strip()

    # 1) Busca exata
    if chave in m:
        return m[chave]

    # 2) Busca case-insensitive
    chave_lower = chave.lower()
    for k, v in m.items():
        if str(k).strip().lower() == chave_lower:
            return v

    # 3) Busca por CNPJ (apenas dÃ­gitos)
    cnpj = normalizar_cnpj(chave)
    if cnpj:
        for k, v in m.items():
            k_cnpj = normalizar_cnpj(k)
            if k_cnpj and (k_cnpj == cnpj or k_cnpj.endswith(cnpj) or cnpj.endswith(k_cnpj)):
                return v

    # 4) Busca parcial: a chave estÃ¡ contida em alguma entrada ou vice-versa
    for k, v in m.items():
        k_lower = str(k).strip().lower()
        if chave_lower in k_lower or k_lower in chave_lower:
            return v

    return None

def remove_email_fornecedor(chave):
    m = load_email_map()
    if chave in m:
        del m[chave]
        save_email_map(m)

def importar_emails_excel(caminho_excel):
    """
    Importa emails e fornecedores de planilha Excel.
    Colunas esperadas (flexÃ­veis): Nome/Fornecedor, CNPJ, Email
    """
    try:
        df = pd.read_excel(caminho_excel)
        df.columns = [c.strip().lower() for c in df.columns]

        col_nome  = next((c for c in df.columns if 'nome' in c or 'fornecedor' in c or 'razao' in c or 'razÃ£o' in c), None)
        col_cnpj  = next((c for c in df.columns if 'cnpj' in c), None)
        col_email = next((c for c in df.columns if 'email' in c or 'e-mail' in c), None)

        if not col_email:
            return 0, "Coluna 'Email' nÃ£o encontrada na planilha."

        m = load_email_map()
        count = 0
        for _, row in df.iterrows():
            email = str(row.get(col_email, '')).strip()
            if not email or '@' not in email:
                continue
            if col_cnpj:
                cnpj = normalizar_cnpj(row.get(col_cnpj, ''))
                nome = str(row.get(col_nome, '')).strip() if col_nome else ''
                chave = f"{nome} - {cnpj}" if nome else cnpj
            elif col_nome:
                chave = str(row.get(col_nome, '')).strip()
            else:
                continue
            if chave:
                m[chave] = email
                count += 1

        save_email_map(m)
        return count, None
    except Exception as e:
        return 0, str(e)

# ==============================================
# Propostas (rastreamento de respostas)
# ==============================================
def load_propostas():
    if os.path.exists(PROPOSTAS_FILE):
        with open(PROPOSTAS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_propostas(propostas):
    try:
        os.makedirs(os.path.dirname(PROPOSTAS_FILE) or '.', exist_ok=True)
        with open(PROPOSTAS_FILE, 'w', encoding='utf-8') as f:
            json.dump(propostas, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"âŒ Erro ao salvar propostas: {e}")
        raise

def registrar_proposta(token, fornecedor, cnpj, email, valor_total, desconto, valor_pagar, pdf_path, data_pagamento,
                       assunto='', ai_chat_url='', ai_id_proposta=None, ai_token=''):
    propostas = load_propostas()
    propostas[token] = {
        'token': token,
        'fornecedor': fornecedor,
        'cnpj': cnpj,
        'email': email,
        'valor_total': float(valor_total),
        'desconto': float(desconto),
        'valor_pagar': float(valor_pagar),
        'pdf_path': pdf_path,
        'data_pagamento': data_pagamento,
        'data_envio': datetime.now().strftime('%d/%m/%Y %H:%M'),
        'status': 'pendente',  # pendente | aceito | negociando | recusado
        'data_resposta': None,
        'mensagem': '',
        'assunto': assunto,
        'ai_chat_url': ai_chat_url or '',
        'ai_id_proposta': ai_id_proposta,
        'ai_token': ai_token or '',
    }
    save_propostas(propostas)


def _parse_ai_link_data(ai_chat_url):
    try:
        parsed = urllib.parse.urlparse(str(ai_chat_url or '').strip())
        query = urllib.parse.parse_qs(parsed.query)
        proposta_id_raw = str(query.get('id', [''])[0] or '').strip()
        if not proposta_id_raw:
            return None, ''
        proposta_id = int(proposta_id_raw)
        token = str((query.get('token', [''])[0]) or '').strip()
        return proposta_id, token
    except Exception:
        return None, ''


def _normalizar_status_ia(classificacao):
    valor = str(classificacao or '').strip().upper()
    if valor == 'ACEITO':
        return 'aceito'
    if valor == 'NEGOCIAR':
        return 'negociando'
    if valor == 'RECUSADO':
        return 'recusado'
    return ''


def _formatar_data_resposta(valor):
    texto = str(valor or '').strip()
    if not texto:
        return datetime.now().strftime('%d/%m/%Y %H:%M:%S')

    # Dados do backend web chegam em ISO e, historicamente, em UTC.
    # Converte para horario de Sao Paulo para exibicao coerente no desktop.
    texto_iso = texto.replace('Z', '+00:00')
    try:
        dt = datetime.fromisoformat(texto_iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(SP_TIMEZONE).strftime('%d/%m/%Y %H:%M:%S')
    except Exception:
        pass

    for fmt in ('%Y-%m-%dT%H:%M:%S.%f', '%Y-%m-%dT%H:%M:%S', '%d/%m/%Y %H:%M:%S'):
        try:
            dt = datetime.strptime(texto, fmt)
            if 'T' in texto:
                dt = dt.replace(tzinfo=timezone.utc).astimezone(SP_TIMEZONE)
            return dt.strftime('%d/%m/%Y %H:%M:%S')
        except Exception:
            pass
    return texto


def sincronizar_respostas_ia(limit=300):
    try:
        cfg = load_server_config()
        ai_base_url = str(cfg.get('ai_base_url', '') or os.getenv('FORNECEDOR_AI_BASE_URL', '')).strip()
        base = _normalizar_base_url(ai_base_url)
        if not base:
            return 0

        endpoint = f'{base}/admin/respostas?limit={max(1, min(int(limit), 1000))}'
        with urllib.request.urlopen(endpoint, timeout=8) as resp:
            body = resp.read().decode('utf-8', errors='ignore')
            parsed = json.loads(body)

        items = list(parsed.get('items', []) or [])
        if not items:
            return 0

        respostas_por_id = {}
        respostas_por_token = {}
        for item in items:
            try:
                pid = int(item.get('id_proposta'))
            except Exception:
                continue
            if pid not in respostas_por_id:
                respostas_por_id[pid] = item

            token_item = str(item.get('token', '') or '').strip()
            if token_item and token_item not in respostas_por_token:
                respostas_por_token[token_item] = item

        propostas = load_propostas()
        alteradas = 0

        for token_local, proposta in propostas.items():
            ai_id = proposta.get('ai_id_proposta')
            if not ai_id:
                ai_id, ai_token = _parse_ai_link_data(proposta.get('ai_chat_url', ''))
                if ai_id:
                    proposta['ai_id_proposta'] = ai_id
                    if ai_token:
                        proposta['ai_token'] = ai_token
                    alteradas += 1

            resposta = None
            ai_token = str(proposta.get('ai_token', '') or '').strip()
            if ai_token:
                resposta = respostas_por_token.get(ai_token)

            if not resposta and ai_id:
                resposta = respostas_por_id.get(int(ai_id))

            if not resposta:
                continue

            classificacao = resposta.get('classificacao') or resposta.get('classificacao_ia')
            novo_status = _normalizar_status_ia(classificacao)
            if not novo_status:
                continue

            status_atual = str(proposta.get('status', 'pendente'))
            mudou = False

            if status_atual != novo_status:
                proposta['status'] = novo_status
                mudou = True

            data_resp = _formatar_data_resposta(resposta.get('data_resposta') or resposta.get('created_at'))
            if data_resp and proposta.get('data_resposta') != data_resp:
                proposta['data_resposta'] = data_resp
                mudou = True

            msg_resp = str(resposta.get('mensagem_texto', '') or '').strip()
            if msg_resp and proposta.get('mensagem') != msg_resp:
                proposta['mensagem'] = msg_resp
                mudou = True

            if mudou:
                alteradas += 1
                if status_atual != 'aceito' and novo_status == 'aceito':
                    _copiar_para_aceitas(proposta)

        if alteradas:
            save_propostas(propostas)
        return alteradas
    except Exception as e:
        print(f'Erro ao sincronizar respostas IA: {e}')
        return 0

def _enviar_notificacao_resposta(proposta, status):
    """Envia email de notificacao ao remetente SMTP quando o fornecedor responde."""
    try:
        ss, sp, su, spw = get_smtp_credentials()
        if not all([ss, sp, su, spw]):
            return

        icones = {'aceito': 'ACEITO', 'negociando': 'QUER NEGOCIAR', 'recusado': 'RECUSADO'}
        cores  = {'aceito': '#276749', 'negociando': '#856404', 'recusado': '#9b1c1c'}
        bgs    = {'aceito': '#e6ffed',  'negociando': '#fff3cd', 'recusado': '#ffe4e4'}

        def fmt(v):
            return f"R$ {float(v):,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')

        label   = icones.get(status, status.upper())
        cor     = cores.get(status, '#2d3748')
        bg      = bgs.get(status, '#f7fafc')
        forn    = proposta.get('fornecedor', '')
        cnpj    = proposta.get('cnpj', '')
        email_f = proposta.get('email', '')
        vp      = fmt(proposta.get('valor_pagar', 0))
        dp      = proposta.get('data_pagamento', '')
        dr      = proposta.get('data_resposta', datetime.now().strftime('%d/%m/%Y %H:%M'))

        subj = f'[RESPOSTA PROPOSTA] {label} - {forn}'

        html = corrigir_texto_exibicao(f"""<!DOCTYPE html>
<html lang="pt-BR"><head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background:#f0f2f5;font-family:Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="padding:32px 0;">
  <tr><td align="center">
    <table width="560" cellpadding="0" cellspacing="0"
           style="background:#fff;border-radius:12px;box-shadow:0 2px 12px rgba(0,0,0,.08);overflow:hidden;">
      <tr><td style="background:#1e3a5f;padding:24px 32px;text-align:center;">
        <h2 style="color:#fff;margin:0;font-size:20px;">RESPOSTA DE PROPOSTA RECEBIDA</h2>
        <p style="color:#a0c4e4;margin:4px 0 0;font-size:13px;">Mercadao Atacadista - Mesa de Antecipacao</p>
      </td></tr>
      <tr><td style="padding:28px 32px;">
        <div style="background:{bg};border-radius:8px;padding:16px 24px;text-align:center;margin-bottom:24px;">
          <p style="color:{cor};font-size:22px;font-weight:bold;margin:0;">{label}</p>
        </div>
        <table width="100%" cellpadding="0" cellspacing="0"
               style="background:#f7fafc;border-radius:8px;">
          <tr><td style="padding:10px 16px;color:#4a5568;font-size:13px;border-bottom:1px solid #e2e8f0;"><b>Fornecedor</b></td>
              <td style="padding:10px 16px;color:#2d3748;font-size:13px;border-bottom:1px solid #e2e8f0;">{forn}</td></tr>
          <tr><td style="padding:10px 16px;color:#4a5568;font-size:13px;border-bottom:1px solid #e2e8f0;"><b>CNPJ</b></td>
              <td style="padding:10px 16px;color:#2d3748;font-size:13px;border-bottom:1px solid #e2e8f0;">{cnpj}</td></tr>
          <tr><td style="padding:10px 16px;color:#4a5568;font-size:13px;border-bottom:1px solid #e2e8f0;"><b>Email do Fornecedor</b></td>
              <td style="padding:10px 16px;color:#2d3748;font-size:13px;border-bottom:1px solid #e2e8f0;">{email_f}</td></tr>
          <tr><td style="padding:10px 16px;color:#4a5568;font-size:13px;border-bottom:1px solid #e2e8f0;"><b>Valor a Pagar</b></td>
              <td style="padding:10px 16px;color:#2d3748;font-size:13px;font-weight:bold;border-bottom:1px solid #e2e8f0;">{vp}</td></tr>
          <tr><td style="padding:10px 16px;color:#4a5568;font-size:13px;border-bottom:1px solid #e2e8f0;"><b>Data de Pagamento</b></td>
              <td style="padding:10px 16px;color:#2d3748;font-size:13px;border-bottom:1px solid #e2e8f0;">{dp}</td></tr>
          <tr><td style="padding:10px 16px;color:#4a5568;font-size:13px;"><b>Data da Resposta</b></td>
              <td style="padding:10px 16px;color:#2d3748;font-size:13px;">{dr}</td></tr>
        </table>
      </td></tr>
      <tr><td style="background:#f7fafc;padding:16px 32px;text-align:center;
                     border-top:1px solid #e2e8f0;color:#718096;font-size:12px;">
        MERCADAO ATACADISTA - MESA DE ANTECIPACAO
      </td></tr>
    </table>
  </td></tr>
</table>
</body></html>""")

        plain = corrigir_texto_exibicao(f"""RESPOSTA DE PROPOSTA RECEBIDA

Status : {label}
Fornecedor : {forn}
CNPJ : {cnpj}
Email do Fornecedor : {email_f}
Valor a Pagar : {vp}
Data de Pagamento : {dp}
Data da Resposta : {dr}

MERCADAO ATACADISTA - MESA DE ANTECIPACAO""")

        msg = MIMEMultipart('alternative')
        msg['From'] = su
        msg['To'] = su
        msg['Subject'] = subj
        msg.attach(MIMEText(plain, 'plain', 'utf-8'))
        msg.attach(MIMEText(html, 'html', 'utf-8'))

        p = int(re.search(r'(\d+)', str(sp)).group(1))
        with smtplib.SMTP(ss, p) as server:
            server.starttls()
            server.login(su, spw)
            server.send_message(msg)
        print(f'Notificacao de resposta enviada para {su}')
    except Exception as e:
        print(f'Erro ao enviar notificacao de resposta: {e}')


def atualizar_status_proposta(token, status, mensagem=''):
    try:
        propostas = load_propostas()
        if token in propostas:
            propostas[token]['status'] = status
            propostas[token]['data_resposta'] = datetime.now().strftime('%d/%m/%Y %H:%M:%S')
            propostas[token]['mensagem'] = mensagem
            
            # Salva ANTES de tentar outras operaÃ§Ãµes
            save_propostas(propostas)
            print(f"âœ… Proposta {token} atualizada para status '{status}'")

            # O envio de email ao remetente e feito na rota de resposta (/resposta/<token>/<acao>)
            # para manter o assunto com prefixo (Aceito / Quero Negociar / Nao Aceito)
            # e evitar notificacao duplicada.

            # Copia para pasta de aceitas se foi aceita
            if status == 'aceito':
                _copiar_para_aceitas(propostas[token])
        else:
            print(f"âš ï¸ Token {token} nÃ£o encontrado nas propostas")
    except Exception as e:
        print(f"âŒ Erro ao atualizar status da proposta: {e}")
        traceback.print_exc()

def _copiar_para_aceitas(proposta):
    try:
        os.makedirs(PROPOSTAS_ACEITAS_DIR, exist_ok=True)
        pdf_src = proposta.get('pdf_path', '')
        if pdf_src and os.path.exists(pdf_src):
            nome = os.path.basename(pdf_src)
            dst = os.path.join(PROPOSTAS_ACEITAS_DIR, nome)
            shutil.copy2(pdf_src, dst)
            print(f"âœ… PDF copiado para aceitas: {dst}")
            _gerar_relatorio_aceite(proposta, dst)
        else:
            print(f"âš ï¸ PDF nÃ£o encontrado: {pdf_src}")
    except Exception as e:
        print(f"âŒ Erro ao copiar para Propostas Aceitas: {e}")
        traceback.print_exc()

def _gerar_relatorio_aceite(proposta, pdf_original):
    """Gera um relatÃ³rio resumido de aceite para o financeiro."""
    try:
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font('Arial', 'B', 16)
        pdf.set_text_color(0, 60, 100)
        pdf.cell(0, 12, 'PROPOSTA ACEITA - PARA FINANCEIRO', 0, 1, 'C')
        pdf.set_line_width(0.5)
        pdf.set_draw_color(0, 60, 100)
        pdf.line(10, pdf.get_y(), 200, pdf.get_y())
        pdf.ln(8)

        campos = [
            ('Fornecedor:', _safe_pdf_text(proposta.get('fornecedor', ''))),
            ('CNPJ:', proposta.get('cnpj', '')),
            ('Email:', proposta.get('email', '')),
            ('Data de Pagamento:', proposta.get('data_pagamento', '')),
            ('Valor Liquido Total:', f"R$ {proposta.get('valor_total', 0):,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')),
            ('Desconto Antecipacao:', f"R$ {proposta.get('desconto', 0):,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')),
            ('Valor a Pagar:', f"R$ {proposta.get('valor_pagar', 0):,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')),
            ('Data do Aceite:', proposta.get('data_resposta', '')),
            ('Data do Envio:', proposta.get('data_envio', '')),
        ]
        pdf.set_font('Arial', '', 11)
        for label, valor in campos:
            pdf.set_font('Arial', 'B', 11)
            pdf.cell(55, 8, _safe_pdf_text(label), 0, 0)
            pdf.set_font('Arial', '', 11)
            pdf.cell(0, 8, _safe_pdf_text(str(valor)), 0, 1)

        pdf.ln(10)
        pdf.set_font('Arial', 'I', 9)
        pdf.set_text_color(100, 100, 100)
        pdf.cell(0, 6, _safe_pdf_text(f'Relatorio gerado em {datetime.now().strftime("%d/%m/%Y %H:%M:%S")}'), 0, 1, 'C')
        pdf.cell(0, 6, 'MERCADAO ATACADISTA - MESA DE ANTECIPACAO', 0, 1, 'C')

        nome_resumo = os.path.splitext(os.path.basename(pdf_original))[0] + '_ACEITE.pdf'
        caminho_saida = os.path.join(PROPOSTAS_ACEITAS_DIR, nome_resumo)
        pdf.output(caminho_saida)
        print(f"âœ… RelatÃ³rio de aceite gerado: {caminho_saida}")
    except Exception as e:
        print(f"âŒ Erro ao gerar relatÃ³rio de aceite: {e}")
        traceback.print_exc()

# ==============================================
# Servidor Flask de Respostas
# ==============================================
_flask_app = None
_flask_thread = None
_flask_running = False

HTML_RESPOSTA = corrigir_texto_exibicao("""
<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Resposta - Mercadao Atacadista</title>
<style>
  body{{font-family:Arial,sans-serif;background:#f0f2f5;display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0}}
  .card{{background:#fff;border-radius:12px;padding:40px;max-width:480px;width:100%;box-shadow:0 4px 20px rgba(0,0,0,.1);text-align:center}}
  .icon{{font-size:56px;margin-bottom:12px}}
  h2{{color:#1e3a5f;margin:0 0 8px}}
  p{{color:#718096;margin:0 0 24px;line-height:1.5}}
  .status-box{{background:#{status_bg};border-radius:8px;padding:16px;margin:20px 0;border-left:5px solid #{status_color}}}
  .status-box p{{margin:0;font-weight:bold}}
  .badge{{display:inline-block;padding:8px 24px;border-radius:20px;font-weight:bold;font-size:14px}}
  .aceito{{background:#e6ffed;color:#276749}}
  .negociando{{background:#fff3cd;color:#856404}}
  .recusado{{background:#ffe4e4;color:#9b1c1c}}
  .footer{{margin-top:32px;font-size:12px;color:#a0aec0}}
  .check{{color:#48bb78;font-weight:bold}}
</style>
</head>
<body>
<div class="card">
  <div class="icon">{icon}</div>
  <h2>{titulo}</h2>
  <p>{mensagem}</p>
  <div class="badge {classe}">{badge}</div>
  <div class="status-box" style="background:#{status_bg}; border-left-color:#{status_color};">
    <p style="color:#{status_color};">Email enviado com sucesso.</p>
    <p style="font-size:12px;color:#{status_text};">Assunto: {assunto}</p>
  </div>
    <div class="footer">Mercadao Atacadista - Mesa de Antecipacao<br>{data}</div>
</div>
</body>
</html>""")

def _enviar_email_resposta_fornecedor(fornecedor_email, assunto, corpo_msg, prefixo):
    """Envia email de resposta do fornecedor para o remetente SMTP."""
    try:
        ss, sp, su, spw = get_smtp_credentials()
        if not all([ss, sp, su, spw]):
            print("Credenciais SMTP nao configuradas. Email nao enviado.")
            return False

        assunto_completo = f"{prefixo} - {assunto}"

        # Cria mensagem com parte HTML
        msg = MIMEMultipart('alternative')
        msg['From'] = su
        msg['To'] = su
        msg['Subject'] = assunto_completo
        msg['Reply-To'] = fornecedor_email

        # Texto plano
        msg.attach(MIMEText(corpo_msg, 'plain', 'utf-8'))

        # HTML formatado
        html_corpo = corrigir_texto_exibicao(f"""<!DOCTYPE html>
<html lang="pt-BR">
<head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background:#f0f2f5;font-family:Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f0f2f5;padding:32px 0;">
  <tr><td align="center">
    <table width="620" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 4px 16px rgba(0,0,0,0.12);">
      <tr><td style="background:#1e3a5f;padding:24px 32px;text-align:center;">
        <h2 style="color:#ffffff;margin:0;">RESPOSTA DE PROPOSTA RECEBIDA</h2>
        <p style="color:#a0c4e4;margin:4px 0 0;font-size:13px;">Mercadao Atacadista - Mesa de Antecipacao</p>
      </td></tr>
      <tr><td style="padding:32px;">
        <p style="color:#2d3748;margin:0 0 16px;"><strong>Resposta recebida:</strong></p>
        <p style="color:#718096;margin:0 0 24px;">{corpo_msg.replace(chr(10), '<br>')}</p>
        <p style="color:#a0aec0;font-size:12px;margin:0;">Fornecedor: {fornecedor_email}</p>
      </td></tr>
      <tr><td style="background:#f7fafc;padding:16px 32px;text-align:center;border-top:1px solid #e2e8f0;color:#1e3a5f;font-size:12px;font-weight:bold;">
        MERCADAO ATACADISTA - MESA DE ANTECIPACAO
      </td></tr>
    </table>
  </td></tr>
</table>
</body>
</html>""")

        msg.attach(MIMEText(html_corpo, 'html', 'utf-8'))

        # Envia
        p = int(re.search(r'(\d+)', str(sp)).group(1))
        with smtplib.SMTP(ss, p) as server:
            server.starttls()
            server.login(su, spw)
            server.send_message(msg)

        print(f"Email de resposta enviado para {su} (Fornecedor: {fornecedor_email})")
        return True
    except Exception as e:
        print(f"Erro ao enviar email de resposta: {e}")
        traceback.print_exc()
        return False

def criar_flask_app():
    app = Flask(__name__)

    @app.route('/resposta/<token>/<acao>')
    def resposta(token, acao):
        try:
            propostas = load_propostas()
            if token not in propostas:
                return "Token invalido ou expirado.", 404

            p = propostas[token]
            fornecedor = p.get('fornecedor', '')
            fornecedor_email = p.get('email', '')
            assunto_original = p.get('assunto', f"Proposta de Antecipacao de Pagamentos - {fornecedor} ({p.get('cnpj', '')})")

            def fmt_valor(v):
                return f"R$ {v:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')

            corpo_base = (
                f"Fornecedor: {fornecedor}\n"
                f"CNPJ: {p.get('cnpj', '')}\n"
                f"Valor Liquido Total: {fmt_valor(p.get('valor_total', 0))}\n"
                f"Desconto de Antecipacao: {fmt_valor(p.get('desconto', 0))}\n"
                f"Valor a Receber: {fmt_valor(p.get('valor_pagar', 0))}\n"
                f"Data de Pagamento: {p.get('data_pagamento', '')}\n"
            )

            if acao == 'aceito':
                atualizar_status_proposta(token, 'aceito')
                prefixo = 'Aceito'
                corpo_msg = f"Prezados,\n\nInformamos que ACEITAMOS a proposta abaixo:\n\n{corpo_base}\nAtenciosamente,\n{fornecedor}"
                msg_html = f'<strong>{fornecedor}</strong>, sua confirmacao foi registrada com sucesso.<br><br>Status: <strong>ACEITO</strong><br>Data e hora: {datetime.now().strftime("%d/%m/%Y %H:%M:%S")}<br><br>Em breve entraremos em contato para finalizar o processo.'
                classe, badge, icon, titulo = 'aceito', 'ACEITO', 'OK', 'Proposta Aceita'
                status_bg, status_color, status_text = 'e6ffed', '276749', '276749'
            elif acao == 'negociar':
                atualizar_status_proposta(token, 'negociando')
                prefixo = 'Quero Negociar'
                corpo_msg = f"Prezados,\n\nGostariamos de NEGOCIAR as condicoes da proposta abaixo:\n\n{corpo_base}\nAtenciosamente,\n{fornecedor}"
                msg_html = f'<strong>{fornecedor}</strong>, recebemos sua solicitacao.<br><br>Status: <strong>EM NEGOCIACAO</strong><br>Data e hora: {datetime.now().strftime("%d/%m/%Y %H:%M:%S")}<br><br>Nossa equipe entrara em contato em breve para discutir as condicoes.'
                classe, badge, icon, titulo = 'negociando', 'EM NEGOCIACAO', 'INFO', 'Solicitacao de Negociacao'
                status_bg, status_color, status_text = 'fff3cd', '856404', '856404'
            elif acao == 'recusar':
                atualizar_status_proposta(token, 'recusado')
                prefixo = 'Nao Aceito'
                corpo_msg = f"Prezados,\n\nInformamos que NAO ACEITAMOS a proposta abaixo:\n\n{corpo_base}\nAtenciosamente,\n{fornecedor}"
                msg_html = f'<strong>{fornecedor}</strong>, sua resposta foi registrada.<br><br>Status: <strong>RECUSADO</strong><br>Data e hora: {datetime.now().strftime("%d/%m/%Y %H:%M:%S")}<br><br>Agradecemos pelo retorno.'
                classe, badge, icon, titulo = 'recusado', 'RECUSADO', 'X', 'Proposta Recusada'
                status_bg, status_color, status_text = 'ffe4e4', '9b1c1c', '9b1c1c'
            else:
                return "Acao desconhecida.", 400

            assunto_resposta = f"{prefixo} - {assunto_original}"
            
            # Envia email automaticamente
            email_enviado = _enviar_email_resposta_fornecedor(
                fornecedor_email, assunto_original, corpo_msg, prefixo
            )

            html = HTML_RESPOSTA.format(
                icon=icon, titulo=titulo,
                mensagem=msg_html,
                classe=classe, badge=badge,
                assunto=assunto_resposta,
                status_bg=status_bg, status_color=status_color, status_text=status_text,
                data=datetime.now().strftime('%d/%m/%Y %H:%M'))

            return html
        except Exception as e:
            erro_msg = f"Erro ao processar resposta: {str(e)}"
            print(erro_msg)
            traceback.print_exc()
            return f"<h1>Erro</h1><p>{erro_msg}</p><p>Por favor, tente novamente ou entre em contato com o suporte.</p>", 500

    @app.route('/status')
    def status():
        return '{"status":"ok"}', 200, {'Content-Type': 'application/json'}

    return app

def iniciar_servidor(port=None):
    """Inicia servidor Flask para processar respostas de propostas.
    
    Em Railway, detecta porta automaticamente via variÃ¡vel PORT.
    Em desenvolvimento, usa porta padrÃ£o 5001.
    """
    global _flask_app, _flask_thread, _flask_running
    if not FLASK_AVAILABLE:
        print("âš ï¸ Flask nÃ£o instalado. Servidor de respostas desativado.")
        return False
    if _flask_running:
        return True
    
    try:
        # Detecta porta: Railway > argumento > padrÃ£o
        if port is None:
            port = int(os.getenv('PORT', 5001))
        
        is_production = bool(os.getenv('RAILWAY_URL'))
        env_label = "PRODUÃ‡ÃƒO (Railway)" if is_production else "DESENVOLVIMENTO"
        
        _flask_app = criar_flask_app()

        def run():
            import logging
            log = logging.getLogger('werkzeug')
            log.setLevel(logging.ERROR)
            _flask_app.run(host='0.0.0.0', port=port, use_reloader=False, threaded=True)

        _flask_thread = threading.Thread(target=run, daemon=True)
        _flask_thread.start()
        _flask_running = True
        
        cfg = load_server_config()
        base_url = cfg.get('base_url', 'http://localhost:5001')
        
        print(f"âœ… Servidor de respostas iniciado ({env_label})")
        print(f"   Porta: {port}")
        print(f"   URL Base: {base_url}")
        return True
    except Exception as e:
        print(f"âŒ Erro ao iniciar servidor: {e}")
        traceback.print_exc()
        return False

# ==============================================
# Template de Email HTML com BotÃµes
# ==============================================
def get_email_html(fornecedor, cnpj, data_base, data_pagamento, taxa_display,
                   total_valor, total_desconto, total_pagar, base_url, token, ai_chat_url=''):
    def fmt(v):
        return f"R$ {v:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')

    is_ngrok_link = 'ngrok-free.dev' in str(base_url or '').lower() or 'ngrok.io' in str(base_url or '').lower()
    aviso_ngrok = ""
    if is_ngrok_link:
        aviso_ngrok = """
        <div style="background:#fff8e1; border:1px solid #f6a623; border-radius:8px; padding:12px 14px; margin:0 0 18px;">
          <p style="margin:0; color:#7a4b00; font-size:12px; line-height:1.5;">
            <strong>Aviso rapido:</strong> se abrir uma tela de seguranca do ngrok, clique em
            <strong>\"Visite o site\"</strong> para confirmar e continuar.
          </p>
        </div>
        """

    url_aceito   = f"{base_url}/resposta/{token}/aceito"
    url_negociar = f"{base_url}/resposta/{token}/negociar"
    url_recusar  = f"{base_url}/resposta/{token}/recusar"

    action_section = ""
    if ai_chat_url:
        action_section = f"""
                <div style="background:#f7fafc; border:2px solid #e2e8f0; border-radius:12px; padding:28px; text-align:center;">
                    <p style="color:#2d3748; font-size:16px; font-weight:bold; margin:0 0 16px;">
                        Responda em linguagem natural com o Assistente IA
                    </p>
                    <a href="{ai_chat_url}"
                         style="display:inline-block; background:#0f766e; color:#ffffff; padding:16px 24px; border-radius:8px; font-weight:bold; font-size:14px; text-decoration:none;">
                        Abrir Chat da Proposta
                    </a>
                    <p style="color:#6b7280; font-size:12px; margin:14px 0 0;">
                        Exemplo: "aceito", "podemos negociar prazo", "nao aceito".
                    </p>
                </div>
                """
    else:
        action_section = f"""
                <div style="background:#f7fafc; border:2px solid #e2e8f0; border-radius:12px; padding:28px; text-align:center;">
                    <p style="color:#2d3748; font-size:16px; font-weight:bold; margin:0 0 20px;">
                        Como você deseja responder a esta proposta?
                    </p>

                    <table width="100%" cellpadding="0" cellspacing="0">
                        <tr>
                            <td style="padding:0 8px 0 0;">
                                <a href="{url_aceito}"
                                     style="display:inline-block; background:#48bb78; color:#ffffff; padding:16px 24px; border-radius:8px; font-weight:bold; font-size:14px; text-decoration:none; border:none; cursor:pointer; transition:all 0.2s;">
                                    ✅ 1. Aceito
                                </a>
                            </td>
                            <td style="padding:0 8px;">
                                <a href="{url_negociar}"
                                     style="display:inline-block; background:#f6a623; color:#ffffff; padding:16px 24px; border-radius:8px; font-weight:bold; font-size:14px; text-decoration:none; border:none; cursor:pointer; transition:all 0.2s;">
                                    💬 2. Quero Negociar
                                </a>
                            </td>
                            <td style="padding:0 0 0 8px;">
                                <a href="{url_recusar}"
                                     style="display:inline-block; background:#e53e3e; color:#ffffff; padding:16px 24px; border-radius:8px; font-weight:bold; font-size:14px; text-decoration:none; border:none; cursor:pointer; transition:all 0.2s;">
                                    ❌ 3. Não Aceito
                                </a>
                            </td>
                        </tr>
                    </table>

                    <p style="color:#a0aec0; font-size:12px; margin:18px 0 0;">
                        Clique em apenas um dos botões acima para registrar sua resposta.
                    </p>
                </div>
                """

    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Proposta de Antecipação – Mercadão Atacadista</title>
  <style>
    body {{margin:0; padding:0; font-family:'Segoe UI', Arial, sans-serif; background:#f0f2f5;}}
    table {{border-collapse:collapse;}}
    a {{color:inherit; text-decoration:none;}}
  </style>
</head>
<body>
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f0f2f5; padding:32px 0;">
  <tr><td align="center">
    <table width="620" cellpadding="0" cellspacing="0" style="background:#ffffff; border-radius:12px; overflow:hidden; box-shadow:0 4px 16px rgba(0,0,0,0.12);">
      
      <!-- HEADER PRINCIPAL -->
      <tr><td style="background:#1e3a5f; padding:32px; text-align:center;">
        <h1 style="color:#ffffff; margin:0; font-size:24px; font-weight:bold;">MERCADÃO ATACADISTA</h1>
        <p style="color:#a0c4e4; margin:6px 0 0; font-size:14px;">Mesa de Antecipação de Pagamentos</p>
      </td></tr>

      <!-- MAIN CONTENT -->
      <tr><td style="padding:32px 40px;">
        
        <!-- GREETING & CNPJ INFO -->
        <p style="color:#2d3748; font-size:15px; margin:0 0 6px; line-height:1.4;">
          <strong>Prezado(a)</strong> {fornecedor},
        </p>
        <p style="color:#2d3748; font-size:14px; margin:0 0 24px; line-height:1.5;">
          Segue em anexo o relatório de antecipação de pagamentos referente ao CNPJ <strong>{cnpj}</strong>. 
          Aguardamos sua resposta através dos botões ao final deste email.
        </p>

        {aviso_ngrok}

        <!-- INFO CARDS GRID: 2x2 -->
        <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:28px;">
          <tr>
            <td width="50%" style="padding:0 8px 16px 0;">
              <table width="100%" cellpadding="0" cellspacing="0" style="background:#f7fafc; border-radius:8px; overflow:hidden; border-left:5px solid #1e3a5f;">
                <tr><td style="padding:16px 16px;">
                  <p style="margin:0; color:#a0aec0; font-size:11px; text-transform:uppercase; font-weight:600; letter-spacing:0.5px;">Data Base</p>
                  <p style="margin:6px 0 0; color:#2d3748; font-size:16px; font-weight:bold;">{data_base}</p>
                </td></tr>
              </table>
            </td>
            <td width="50%" style="padding:0 0 16px 8px;">
              <table width="100%" cellpadding="0" cellspacing="0" style="background:#f7fafc; border-radius:8px; overflow:hidden; border-left:5px solid #f6a623;">
                <tr><td style="padding:16px 16px;">
                  <p style="margin:0; color:#a0aec0; font-size:11px; text-transform:uppercase; font-weight:600; letter-spacing:0.5px;">Data de Pagamento</p>
                  <p style="margin:6px 0 0; color:#f6a623; font-size:16px; font-weight:bold;">{data_pagamento}</p>
                </td></tr>
              </table>
            </td>
          </tr>
          <tr>
            <td colspan="2" style="padding:0;">
              <table width="100%" cellpadding="0" cellspacing="0" style="background:#f7fafc; border-radius:8px; overflow:hidden; border-left:5px solid #4a90d9;">
                <tr><td style="padding:16px 16px;">
                  <p style="margin:0; color:#a0aec0; font-size:11px; text-transform:uppercase; font-weight:600; letter-spacing:0.5px;">Taxa Aplicada</p>
                  <p style="margin:6px 0 0; color:#2d3748; font-size:16px; font-weight:bold;">{taxa_display}</p>
                </td></tr>
              </table>
            </td>
          </tr>
        </table>

        <!-- VALUES TABLE -->
        <table width="100%" cellpadding="0" cellspacing="0" style="background:#f7fafc; border-radius:8px; overflow:hidden; margin-bottom:32px; border:1px solid #e2e8f0;">
          <tr style="background:#1e3a5f;">
            <th style="color:#ffffff; padding:14px 18px; text-align:left; font-size:13px; font-weight:600;">Valores</th>
            <th style="color:#ffffff; padding:14px 18px; text-align:right; font-size:13px; font-weight:600;">Montante</th>
          </tr>
          <tr>
            <td style="padding:14px 18px; color:#4a5568; font-size:14px; border-bottom:1px solid #e2e8f0;">Valor Líquido Total</td>
            <td style="padding:14px 18px; color:#2d3748; font-size:14px; font-weight:600; text-align:right; border-bottom:1px solid #e2e8f0;">{fmt(total_valor)}</td>
          </tr>
          <tr>
            <td style="padding:14px 18px; color:#4a5568; font-size:14px; border-bottom:1px solid #e2e8f0;">Desconto de Antecipação</td>
            <td style="padding:14px 18px; color:#e53e3e; font-size:14px; font-weight:600; text-align:right; border-bottom:1px solid #e2e8f0;">- {fmt(total_desconto)}</td>
          </tr>
          <tr style="background:#e6ffed;">
            <td style="padding:16px 18px; color:#276749; font-size:15px; font-weight:bold;">🔒 Valor a Receber</td>
            <td style="padding:16px 18px; color:#276749; font-size:18px; font-weight:bold; text-align:right;">{fmt(total_pagar)}</td>
          </tr>
        </table>

        <!-- INFO MESSAGE -->
        <p style="color:#718096; font-size:13px; text-align:center; margin:0 0 28px;">
          O relatório completo está em anexo a este email.
        </p>

                <!-- ACTION SECTION -->
                {action_section}

      </td></tr>

      <!-- FOOTER -->
      <tr><td style="background:#f7fafc; padding:24px 40px; border-top:1px solid #e2e8f0; text-align:center;">
        <p style="margin:0; color:#1e3a5f; font-size:13px; font-weight:bold;">MERCADÃO ATACADISTA – MESA DE ANTECIPAÇÃO</p>
        <p style="margin:6px 0 0; color:#718096; font-size:12px; line-height:1.5;">
          jonas@mercadaoatacadista.com.br &nbsp; | &nbsp; (11) 3791-1130 Ramal 2016
        </p>
      </td></tr>

    </table>
  </td></tr>
</table>
</body>
</html>"""

def get_email_plaintext(fornecedor, cnpj, data_base, data_pagamento, taxa_display,
                        total_valor, total_desconto, total_pagar, base_url, token, ai_chat_url=''):
    def fmt(v):
        return f"R$ {v:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
    is_ngrok_link = 'ngrok-free.dev' in str(base_url or '').lower() or 'ngrok.io' in str(base_url or '').lower()
    aviso_ngrok = ''
    if is_ngrok_link:
        aviso_ngrok = (
            '\nATENCAO: se abrir uma tela de seguranca do ngrok, clique em "Visite o site" para continuar.\n'
        )
    bloco_resposta = ''
    if ai_chat_url:
        bloco_resposta = (
            'RESPONDA NO CHAT COM IA (LINGUAGEM NATURAL):\n\n'
            f'{ai_chat_url}\n'
        )
    else:
        bloco_resposta = (
            'RESPONDA CLICANDO EM UM DOS LINKS ABAIXO:\n\n'
            'ACEITO:\n'
            f'{base_url}/resposta/{token}/aceito\n\n'
            'QUERO NEGOCIAR:\n'
            f'{base_url}/resposta/{token}/negociar\n\n'
            'NAO ACEITO:\n'
            f'{base_url}/resposta/{token}/recusar\n'
        )

    return corrigir_texto_exibicao(f"""
Prezado(a) {fornecedor},

Segue em anexo o relatorio de antecipacao de pagamentos referente ao CNPJ {cnpj}.

{aviso_ngrok}

Data Base: {data_base}
Data de Pagamento: {data_pagamento}
Taxa Aplicada: {taxa_display}

Valor Liquido Total:      {fmt(total_valor)}
Desconto de Antecipacao:  {fmt(total_desconto)}
Valor a Receber:          {fmt(total_pagar)}

------------------------------------------------------------
{bloco_resposta}
------------------------------------------------------------

MERCADAO ATACADISTA - MESA DE ANTECIPACAO
jonas@mercadaoatacadista.com.br | (11) 3791-1130 Ramal 2016
""")

# ==============================================
# Envio de Email (HTML)
# ==============================================
class EmailSender:
    def __init__(self, smtp_server, smtp_port, smtp_user, smtp_password):
        self.smtp_server = smtp_server
        if isinstance(smtp_port, str):
            m = re.search(r'(\d+)', smtp_port)
            smtp_port = int(m.group(1)) if m else 587
        self.smtp_port = smtp_port
        self.smtp_user = smtp_user
        self.smtp_password = smtp_password

    def send_email(self, to_email, subject, html_body, plain_body, attachment_paths=None, bcc_emails=None):
        subject = corrigir_texto_exibicao(subject)
        msg = MIMEMultipart('alternative')
        msg['From'] = self.smtp_user
        msg['To'] = to_email
        msg['Subject'] = subject

        msg.attach(MIMEText(plain_body, 'plain', 'utf-8'))
        msg.attach(MIMEText(html_body, 'html', 'utf-8'))

        if attachment_paths:
            outer = MIMEMultipart('mixed')
            outer['From'] = self.smtp_user
            outer['To'] = to_email
            outer['Subject'] = subject
            outer.attach(msg)

            for path in attachment_paths or []:
                if not os.path.exists(path):
                    continue
                ctype, _ = mimetypes.guess_type(path)
                if ctype is None:
                    ctype = 'application/octet-stream'
                main, sub = ctype.split('/', 1)
                part = MIMEBase(main, sub)
                with open(path, 'rb') as fp:
                    part.set_payload(fp.read())
                encoders.encode_base64(part)
                fname = os.path.basename(path)
                fname_ascii = unicodedata.normalize('NFKD', fname).encode('ascii', 'ignore').decode('ascii').strip() or 'anexo.pdf'
                part.add_header('Content-Disposition', 'attachment', filename=fname_ascii)
                outer.attach(part)
            msg = outer

        # BCC: destinatÃ¡rios ocultos (nÃ£o aparecem no cabeÃ§alho)
        all_recipients = [to_email]
        if bcc_emails:
            for bcc in bcc_emails:
                if bcc and bcc not in all_recipients:
                    all_recipients.append(bcc)

        try:
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_user, self.smtp_password)
                server.sendmail(self.smtp_user, all_recipients, msg.as_string())
            if bcc_emails:
                print(f"  (cÃ³pia BCC enviada para: {', '.join(bcc_emails)})")
            return True
        except smtplib.SMTPAuthenticationError:
            print(f"Erro de autenticaÃ§Ã£o para {to_email}")
            return False
        except Exception as e:
            print(f"Erro ao enviar para {to_email}: {e}")
            traceback.print_exc()
            return False

# ==============================================
# GeraÃ§Ã£o de PDF
# ==============================================
_UNICODE_REPLACE = {
    '\u2013': '-',   # en dash â€“
    '\u2014': '-',   # em dash â€”
    '\u2018': "'",   # ' aspa esquerda
    '\u2019': "'",   # ' aspa direita
    '\u201c': '"',   # " aspas duplas esquerda
    '\u201d': '"',   # " aspas duplas direita
    '\u2026': '...', # â€¦ reticÃªncias
    '\u00b0': 'o',  # Â° grau
    '\u2022': '-',   # â€¢ bullet
    '\u20ac': 'EUR', # â‚¬ euro
    '\u00a0': ' ',   # espaÃ§o nÃ£o quebrÃ¡vel
}

def _safe_pdf_text(text):
    """Remove/substitui caracteres fora do Latin-1 para compatibilidade com FPDF."""
    if not text:
        return ''
    text = str(text)
    for char, repl in _UNICODE_REPLACE.items():
        text = text.replace(char, repl)
    # Codifica para latin-1 substituindo o que nÃ£o couber
    return text.encode('latin-1', errors='replace').decode('latin-1')


class AntecipacaoPDF:
    def __init__(self, logo_path=None):
        self.logo_path = logo_path

    def criar_documento(self):
        pdf = FPDF()
        pdf.add_page()
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.set_font('Arial', '', 10)
        return pdf

    def _processar_logo(self):
        if not self.logo_path or not os.path.exists(self.logo_path):
            return None
        try:
            with Image.open(self.logo_path) as img:
                if img.mode == 'RGBA':
                    bg = Image.new('RGB', img.size, (255, 255, 255))
                    bg.paste(img, mask=img.split()[3])
                    img = bg
                elif img.mode == 'P':
                    img = img.convert('RGB')
                max_w = int(50 * 3.78)
                ratio = max_w / float(img.size[0])
                img = img.resize((max_w, int(img.size[1] * ratio)), Image.LANCZOS)
                tmp = tempfile.NamedTemporaryFile(suffix='.jpg', delete=False)
                img.save(tmp.name, format='JPEG', quality=95)
                return tmp.name
        except Exception:
            return None

    def adicionar_cabecalho(self, pdf, fornecedor, cnpj, data_base, data_pagamento, taxa_display):
        tmp_logo = self._processar_logo()
        logo_h = 0
        if tmp_logo:
            try:
                with Image.open(tmp_logo) as img:
                    logo_h = img.size[1] * 0.264583
                    pdf.image(tmp_logo, x=(210 - 50) / 2, y=10, w=50)
                    logo_h += 8
            finally:
                try:
                    os.unlink(tmp_logo)
                except Exception:
                    pass
        pdf.set_y(15 + logo_h)
        pdf.set_font('Arial', 'B', 16)
        pdf.set_text_color(0, 0, 139)
        pdf.cell(0, 10, 'RELATORIO DE ANTECIPACAO', 0, 1, 'C')
        pdf.ln(5)
        pdf.set_draw_color(0, 0, 139)
        pdf.set_line_width(0.5)
        pdf.line(10, pdf.get_y(), 200, pdf.get_y())
        pdf.ln(8)
        def campo(label, valor):
            pdf.set_font('Arial', 'B', 10)
            pdf.cell(30, 6, label, 0, 0)
            pdf.set_font('Arial', '', 10)
            pdf.cell(0, 6, _safe_pdf_text(str(valor)), 0, 1)
        pdf.set_text_color(0, 0, 0)
        campo('Fornecedor:', _safe_pdf_text(str(fornecedor)[:40]))
        campo('CNPJ:', str(cnpj)[:20])
        campo('Data Base:', data_base.strftime('%d/%m/%Y') if isinstance(data_base, datetime) else str(data_base))
        campo('Data Pagamento:', data_pagamento.strftime('%d/%m/%Y') if isinstance(data_pagamento, datetime) else str(data_pagamento))
        campo('Taxa:', _safe_pdf_text(taxa_display))
        pdf.ln(10)

    def adicionar_secao_loja(self, pdf, dados_loja, loja):
        pdf.set_font('Arial', 'B', 12)
        pdf.cell(0, 8, _safe_pdf_text(f' LOJA: {str(loja)[:25].upper()} '), 0, 1, 'L')
        pdf.ln(3)
        col_w = [12, 12, 18, 26, 28, 28, 28, 28]
        headers = ['Seq', 'Prazo', 'Venc.', 'Loja', 'Nº Doc', 'Valor R$', 'Desc. R$', 'Pagar R$']
        pdf.set_fill_color(200, 220, 255)
        pdf.set_font('Arial', 'B', 8)
        for i, h in enumerate(headers):
            pdf.cell(col_w[i], 6, h, 1, 0, 'C', 1)
        pdf.ln()
        pdf.set_font('Arial', '', 8)
        fill = False

        def fv(v):
            try:
                if pd.isna(v) or v is None:
                    return 'R$ 0,00'
                return f"R$ {float(v):,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
            except Exception:
                return 'R$ 0,00'

        for seq, (_, row) in enumerate(dados_loja.iterrows(), start=1):
            pdf.set_fill_color(240, 240, 240) if fill else pdf.set_fill_color(255, 255, 255)
            prazo = str(int(row['Dias de antecipacao'])) if pd.notna(row['Dias de antecipacao']) else ''
            venc  = row['Data de vencimento'].strftime('%d/%m/%y') if pd.notna(row['Data de vencimento']) else ''
            pdf.cell(col_w[0], 6, str(seq), 1, 0, 'C', fill)
            pdf.cell(col_w[1], 6, prazo, 1, 0, 'C', fill)
            pdf.cell(col_w[2], 6, venc, 1, 0, 'C', fill)
            pdf.cell(col_w[3], 6, _safe_pdf_text(str(row.get('Loja', ''))[:12]), 1, 0, 'L', fill)
            pdf.cell(col_w[4], 6, _safe_pdf_text(str(row.get('Numero doc.', ''))[:6]), 1, 0, 'C', fill)
            pdf.cell(col_w[5], 6, fv(row['Valor liquido']), 1, 0, 'R', fill)
            pdf.cell(col_w[6], 6, fv(row['Desconto de antecipacao']), 1, 0, 'R', fill)
            pdf.cell(col_w[7], 6, fv(row['Valor a pagar']), 1, 1, 'R', fill)
            fill = not fill
        pdf.ln(2)

    def adicionar_subtotal(self, pdf, total):
        col_w = [96, 28, 28, 28]
        pdf.set_font('Arial', 'B', 8)
        pdf.set_fill_color(220, 220, 220)

        def fv(v):
            return f"R$ {float(v):,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')

        pdf.set_x(pdf.l_margin)
        pdf.cell(col_w[0], 6, 'Subtotal', 1, 0, 'R', 1)
        pdf.cell(col_w[1], 6, fv(total['valor']), 1, 0, 'R', 1)
        pdf.cell(col_w[2], 6, fv(total['desconto']), 1, 0, 'R', 1)
        pdf.cell(col_w[3], 6, fv(total['pagar']), 1, 1, 'R', 1)
        pdf.ln(2)

    def adicionar_total_fornecedor(self, pdf, total):
        col_w = [96, 28, 28, 28]
        pdf.set_font('Arial', 'B', 10)
        pdf.set_fill_color(0, 100, 0)
        pdf.set_text_color(255, 255, 255)

        def fv(v):
            return f"R$ {float(v):,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')

        pdf.set_x(pdf.l_margin)
        pdf.cell(col_w[0], 8, 'TOTAL FORNECEDOR', 1, 0, 'R', 1)
        pdf.cell(col_w[1], 8, fv(total['valor']), 1, 0, 'R', 1)
        pdf.cell(col_w[2], 8, fv(total['desconto']), 1, 0, 'R', 1)
        pdf.cell(col_w[3], 8, fv(total['pagar']), 1, 1, 'R', 1)
        pdf.set_text_color(0, 0, 0)
        pdf.ln(5)

    def adicionar_secao_boletos(self, pdf):
        pdf.set_font('Arial', 'B', 10)
        pdf.cell(0, 6, 'Boletos Emitidos', 0, 1)
        pdf.set_font('Arial', '', 8)
        pdf.multi_cell(0, 5, 'Sim, emitimos boletos - para conclusao, sera necessario a baixa dos boletos que serao antecipados.')
        pdf.ln(2)
        pdf.multi_cell(0, 5, 'Nao emitimos boletos - pagamentos sao realizados diretamente em conta bancaria previamente definida.')
        pdf.ln(5)

    def adicionar_rodape(self, pdf):
        pdf.set_font('Arial', 'I', 8)
        pdf.cell(0, 5, datetime.now().strftime('Gerado em %d/%m/%Y as %H:%M:%S'), 0, 1)
        pdf.set_font('Arial', 'B', 10)
        pdf.set_text_color(0, 0, 139)
        pdf.cell(0, 6, 'MERCADAO ATACADISTA - MESA DE ANTECIPACAO', 0, 1, 'C')
        pdf.set_font('Arial', '', 9)
        pdf.set_text_color(0, 0, 0)
        pdf.cell(0, 6, 'jonas@mercadaoatacadista.com.br | (11) 3791-1130 Ramal 2016', 0, 1, 'C')

# ==============================================
# LÃ³gica de AntecipaÃ§Ã£o
# ==============================================
class AntecipacaoPagamentos:
    def __init__(self):
        self.taxas = {
            (0, 5000): 0.10,
            (5000.01, 10000): 0.09,
            (10000.01, 20000): 0.08,
            (20000.01, 50000): 0.07,
            (50000.01, float('inf')): 0.06,
        }
        self.df_processado = pd.DataFrame()
        self.col_numero_doc = 'Numero doc.'
        self.col_valor_liquido = 'Valor liquido'
        self.col_dias_antecipacao = 'Dias de antecipacao'
        self.col_desconto_antecipacao = 'Desconto de antecipacao'
        self.col_taxa_unica = 'Taxa unica aplicada'

    def _sf(self, v, d=0.0):
        try:
            if pd.isna(v) or v is None:
                return d
            return float(v)
        except Exception:
            return d

    def _si(self, v, d=0):
        try:
            if pd.isna(v) or v is None:
                return d
            return int(v)
        except Exception:
            return d

    def get_taxa(self, total):
        total = self._sf(total)
        for (lo, hi), t in self.taxas.items():
            if lo <= total <= hi:
                return t
        return 0.10

    def calcular_desconto(self, valor, dias, taxa=None):
        valor = self._sf(valor)
        dias  = self._si(dias)
        if taxa is None:
            taxa = 0.10
        return valor * taxa * (dias / 30)

    def _parse_taxa_percentual(self, taxa_texto):
        texto = str(taxa_texto or '').strip().replace('%', '').replace(',', '.')
        if not texto:
            return None
        valor_percentual = float(texto)
        if valor_percentual < 0:
            raise ValueError('Taxa fixa nao pode ser negativa.')
        return valor_percentual / 100.0

    def _detectar_coluna(self, df_cols, palavras_chave):
        """Encontra o nome real da coluna pela lista de palavras-chave (case-insensitive)"""
        for col in df_cols:
            col_lower = self._normalizar_nome_coluna(col)
            for p in palavras_chave:
                if self._normalizar_nome_coluna(p) in col_lower:
                    return col
        return None

    def _normalizar_nome_coluna(self, valor):
        texto = corrigir_texto_exibicao(str(valor or '')).strip().lower()
        texto = unicodedata.normalize('NFKD', texto)
        texto = ''.join(ch for ch in texto if not unicodedata.combining(ch))
        texto = re.sub(r'[^a-z0-9]+', ' ', texto)
        return texto.strip()

    def processar_arquivo(self, caminho, data_pagamento_str, taxa_fixa_str=None):
        try:
            df = pd.read_excel(caminho)
            df.columns = [corrigir_texto_exibicao(str(col)).strip() for col in df.columns]
            cols = list(df.columns)

            # Detectar colunas automaticamente pelo conteÃºdo do nome
            map_rename = {}
            def mapear(palavras, destino):
                c = self._detectar_coluna(cols, palavras)
                if c and c != destino:
                    map_rename[c] = destino

            mapear(['cnpj'],                          'CNPJ')
            mapear(['fornecedor', 'nome do forn', 'razao', 'razao social', 'nome forn'], 'Fornecedor')
            mapear(['nº doc', 'num doc', 'numero doc', 'documento', 'nota'], self.col_numero_doc)
            mapear(['vencimento', 'vencto', 'venc.', 'dt venc'],                    'Data de vencimento')
            mapear(['valor liq', 'vlr liq', 'valor liquido', 'valor liquido total'], self.col_valor_liquido)
            mapear(['loja'],                          'Loja')
            mapear(['prazo'],                         'Prazo')

            if map_rename:
                df = df.rename(columns=map_rename)

            # Verificar colunas obrigatÃ³rias
            obrigatorias = ['CNPJ', 'Fornecedor', 'Data de vencimento', self.col_valor_liquido]
            faltando = [c for c in obrigatorias if c not in df.columns]
            if faltando:
                messagebox.showerror('Colunas nÃ£o encontradas',
                    f'As seguintes colunas nÃ£o foram identificadas na planilha:\n\n'
                    f'{chr(10).join(faltando)}\n\n'
                    f'Colunas encontradas no arquivo:\n{chr(10).join(cols[:20])}')
                return pd.DataFrame()

            # Criar coluna Loja se nÃ£o existir
            if 'Loja' not in df.columns:
                df['Loja'] = 'Geral'
            if 'Prazo' not in df.columns:
                df['Prazo'] = 0
            if self.col_numero_doc not in df.columns:
                df[self.col_numero_doc] = ''

            df['Data de vencimento'] = pd.to_datetime(df['Data de vencimento'], errors='coerce')
            df['CNPJ'] = df['CNPJ'].apply(normalizar_cnpj)
            df[self.col_valor_liquido] = df[self.col_valor_liquido].apply(self._sf)
            df['Prazo'] = df['Prazo'].apply(self._si)
            df.dropna(subset=['CNPJ', 'Fornecedor', 'Data de vencimento', self.col_valor_liquido], inplace=True)
            df = df[df['CNPJ'].astype(str).str.len() == 14]

            data_pagamento = datetime.strptime(data_pagamento_str, '%d/%m/%Y')
            data_base = datetime.now()

            df[self.col_dias_antecipacao] = (df['Data de vencimento'] - data_pagamento).dt.days
            df[self.col_dias_antecipacao] = df[self.col_dias_antecipacao].apply(lambda x: max(0, x))

            taxa_unica = None
            if taxa_fixa_str and taxa_fixa_str.strip():
                try:
                    taxa_unica = self._parse_taxa_percentual(taxa_fixa_str)
                except ValueError:
                    pass

            if taxa_unica is None:
                taxa_map = {f: self.get_taxa(df[df['Fornecedor'] == f][self.col_valor_liquido].sum()) for f in df['Fornecedor'].unique()}
                df['Taxa Aplicada (%)'] = df['Fornecedor'].map(taxa_map)
            else:
                df['Taxa Aplicada (%)'] = taxa_unica

            df[self.col_desconto_antecipacao] = df.apply(
                lambda r: self.calcular_desconto(r[self.col_valor_liquido], r[self.col_dias_antecipacao], r['Taxa Aplicada (%)']), axis=1)
            df['Valor a pagar'] = df[self.col_valor_liquido] - df[self.col_desconto_antecipacao]
            df[self.col_taxa_unica] = taxa_unica if taxa_unica is not None else 'Dinamica'

            self.df_processado = df
            return df
        except FileNotFoundError:
            messagebox.showerror('Erro', f'Arquivo nÃ£o encontrado: {caminho}')
            return pd.DataFrame()
        except Exception as e:
            messagebox.showerror('Erro ao processar Excel', str(e))
            traceback.print_exc()
            return pd.DataFrame()

    def gerar_pdfs(self, diretorio_saida, logo_path, data_base, data_pagamento, taxa_unica, enviar_email, base_url=''):
        if self.df_processado.empty:
            messagebox.showwarning('Dados Ausentes', 'Nenhum dado processado.')
            return False

        os.makedirs(diretorio_saida, exist_ok=True)
        pdf_gen = AntecipacaoPDF(logo_path)
        email_sender = None

        if enviar_email:
            ss, sp, su, spw = get_smtp_credentials()
            if not all([ss, sp, su, spw]):
                messagebox.showwarning('SMTP', 'ConfiguraÃ§Ãµes SMTP incompletas. Email desativado.')
                enviar_email = False
            else:
                try:
                    email_sender = EmailSender(ss, sp, su, spw)
                    p = int(re.search(r'(\d+)', str(sp)).group(1))
                    with smtplib.SMTP(ss, p) as srv:
                        srv.starttls(); srv.login(su, spw)
                except Exception as e:
                    messagebox.showerror('SMTP', f'Erro na conexÃ£o SMTP: {e}')
                    enviar_email = False

        cfg = load_server_config()
        ai_base_url = str(cfg.get('ai_base_url', '') or os.getenv('FORNECEDOR_AI_BASE_URL', '')).strip()

        enviados = falhos = sem_email = 0
        fornecedores = self.df_processado['Fornecedor'].unique()

        for fornecedor in fornecedores:
            df_f = self.df_processado[self.df_processado['Fornecedor'] == fornecedor].copy()
            if df_f.empty:
                continue
            cnpj = df_f['CNPJ'].iloc[0]
            cnpj_fmt = normalizar_cnpj(cnpj)

            if taxa_unica is not None:
                taxa_display = f'{float(taxa_unica) * 100:.2f}%'
            else:
                txs = df_f['Taxa Aplicada (%)'] * 100
                mn, mx = txs.min(), txs.max()
                taxa_display = f'{mn:.2f}%' if mn == mx else f'{mn:.2f}% - {mx:.2f}%'

            pdf = pdf_gen.criar_documento()
            pdf_gen.adicionar_cabecalho(pdf, fornecedor, cnpj, data_base, data_pagamento, taxa_display)

            total_f = {'valor': 0.0, 'desconto': 0.0, 'pagar': 0.0}
            try:
                for loja in df_f['Loja'].unique():
                    dl = df_f[df_f['Loja'] == loja].copy()
                    pdf_gen.adicionar_secao_loja(pdf, dl, loja)
                    tl = {'valor': dl[self.col_valor_liquido].sum(), 'desconto': dl[self.col_desconto_antecipacao].sum(), 'pagar': dl['Valor a pagar'].sum()}
                    total_f['valor'] += tl['valor']
                    total_f['desconto'] += tl['desconto']
                    total_f['pagar'] += tl['pagar']
                    pdf_gen.adicionar_subtotal(pdf, tl)

                pdf_gen.adicionar_total_fornecedor(pdf, total_f)
                pdf_gen.adicionar_secao_boletos(pdf)
                pdf_gen.adicionar_rodape(pdf)

                nome_pdf = f'Relatorio_Antecipacao_{cnpj_fmt or "SEM_CNPJ"}.pdf'
                pdf_path = os.path.join(diretorio_saida, nome_pdf)
                pdf.output(pdf_path)

                if enviar_email and email_sender:
                    # Tenta vÃ¡rias combinaÃ§Ãµes para encontrar o email
                    to_email = (
                        get_email_fornecedor(f'{fornecedor} - {cnpj_fmt}') or
                        get_email_fornecedor(cnpj_fmt) or
                        get_email_fornecedor(fornecedor) or
                        get_email_fornecedor(f'{cnpj_fmt} - {fornecedor}')
                    )
                    if to_email:
                        token = str(uuid.uuid4())
                        subj = f'Proposta de Antecipação de Pagamentos - {fornecedor} ({cnpj})'
                        db_str = data_base.strftime('%d/%m/%Y')
                        dp_str = data_pagamento.strftime('%d/%m/%Y')

                        numero_proposta = f"{cnpj_fmt}-{datetime.now().strftime('%Y%m%d%H%M%S')}"
                        ai_chat_url = _criar_link_resposta_ia(
                            ai_base_url,
                            numero_proposta,
                            fornecedor,
                            total_f['pagar'],
                            db_str,
                            (float(taxa_unica) * 100) if taxa_unica is not None else None,
                            to_email,
                        ) or ''
                        ai_id_proposta, ai_token = _parse_ai_link_data(ai_chat_url)

                        registrar_proposta(
                            token,
                            fornecedor,
                            cnpj_fmt,
                            to_email,
                            total_f['valor'],
                            total_f['desconto'],
                            total_f['pagar'],
                            pdf_path,
                            data_pagamento.strftime('%d/%m/%Y'),
                            assunto=subj,
                            ai_chat_url=ai_chat_url,
                            ai_id_proposta=ai_id_proposta,
                            ai_token=ai_token,
                        )

                        html_b  = get_email_html(fornecedor, cnpj, db_str, dp_str, taxa_display,
                                                  total_f['valor'], total_f['desconto'], total_f['pagar'],
                                                  base_url, token, ai_chat_url=ai_chat_url)
                        plain_b = get_email_plaintext(fornecedor, cnpj, db_str, dp_str, taxa_display,
                                                       total_f['valor'], total_f['desconto'], total_f['pagar'],
                                                       base_url, token, ai_chat_url=ai_chat_url)

                        ok = email_sender.send_email(to_email, subj, html_b, plain_b, [pdf_path])
                        if ok:
                            enviados += 1
                        else:
                            falhos += 1
                    else:
                        sem_email += 1
                        print(f'âš  Sem email: {fornecedor} CNPJ:{cnpj_fmt}')
            except Exception as e:
                msg = f'Erro ao processar {fornecedor}: {e}'
                print(msg)
                traceback.print_exc()
                messagebox.showerror('Erro no Fornecedor', msg)

        pdfs_gerados = len(fornecedores)
        if enviar_email:
            messagebox.showinfo('Resumo',
                f'PDFs gerados: {pdfs_gerados}\n'
                f'Emails enviados: {enviados}\n'
                f'Falha no envio: {falhos}\n'
                f'Sem email cadastrado: {sem_email}\n'
                f'Total fornecedores: {len(fornecedores)}')
        else:
            messagebox.showinfo('ConcluÃ­do',
                f'PDFs gerados com sucesso!\nTotal de fornecedores: {pdfs_gerados}\nPasta: {diretorio_saida}')
        return True

# ==============================================
# Dashboard â€“ agregaÃ§Ã£o de dados
# ==============================================
def get_dashboard_data():
    propostas = load_propostas()
    registros = list(propostas.values())

    total_propostas = len(registros)
    aceitas    = sum(1 for r in registros if r['status'] == 'aceito')
    negociando = sum(1 for r in registros if r['status'] == 'negociando')
    recusados  = sum(1 for r in registros if r['status'] == 'recusado')
    pendentes  = sum(1 for r in registros if r['status'] == 'pendente')

    volume_por_empresa = {}
    for r in registros:
        f = r.get('fornecedor', 'Desconhecido')
        volume_por_empresa[f] = volume_por_empresa.get(f, 0) + r.get('valor_pagar', 0)

    volume_por_empresa_sorted = sorted(volume_por_empresa.items(), key=lambda x: x[1], reverse=True)

    return {
        'total_propostas': total_propostas,
        'aceitas': aceitas,
        'negociando': negociando,
        'recusados': recusados,
        'pendentes': pendentes,
        'volume_empresa': volume_por_empresa_sorted,
        'status_counts': {'Aceito': aceitas, 'Negociando': negociando, 'Recusado': recusados, 'Pendente': pendentes},
    }

def _parse_datetime_br(valor):
    if not valor:
        return None
    texto = str(valor).strip()
    for fmt in ('%d/%m/%Y %H:%M', '%d/%m/%Y'):
        try:
            return datetime.strptime(texto, fmt)
        except Exception:
            pass
    return None

def _mes_ref(dt_obj):
    return dt_obj.strftime('%Y-%m') if dt_obj else ''

def _mes_label(mes_ref):
    if not mes_ref or '-' not in mes_ref:
        return ''
    ano, mes = mes_ref.split('-', 1)
    return f'{mes}/{ano}'

def _mes_ref_from_label(label):
    label = str(label or '').strip()
    if not label or label == 'Mes Atual':
        return datetime.now().strftime('%Y-%m')
    try:
        mes, ano = label.split('/', 1)
        return f'{ano}-{mes.zfill(2)}'
    except Exception:
        return datetime.now().strftime('%Y-%m')

def _fmt_moeda_br(valor):
    try:
        return f"R$ {float(valor):,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
    except Exception:
        return 'R$ 0,00'

def get_dashboard_month_refs():
    propostas = load_propostas()
    refs = set()
    for p in propostas.values():
        dt_envio = _parse_datetime_br(p.get('data_envio', ''))
        if dt_envio:
            refs.add(_mes_ref(dt_envio))

    refs.add(datetime.now().strftime('%Y-%m'))
    return sorted(refs, reverse=True)

def _build_dashboard_stats(registros, periodo_label):
    total_propostas = len(registros)
    aceitas    = sum(1 for r in registros if r.get('status') == 'aceito')
    negociando = sum(1 for r in registros if r.get('status') == 'negociando')
    recusados  = sum(1 for r in registros if r.get('status') == 'recusado')
    pendentes  = sum(1 for r in registros if r.get('status') == 'pendente')
    total_valor = sum(float(r.get('valor_pagar', 0) or 0) for r in registros)
    taxa_aprovacao = (aceitas / total_propostas * 100) if total_propostas else 0.0

    volume_por_empresa = {}
    for r in registros:
        forn = r.get('fornecedor', 'Desconhecido')
        volume_por_empresa[forn] = volume_por_empresa.get(forn, 0.0) + float(r.get('valor_pagar', 0) or 0)
    volume_por_empresa_sorted = sorted(volume_por_empresa.items(), key=lambda x: x[1], reverse=True)

    evolucao = {}
    for r in registros:
        dt = r['_dt_envio'].date()
        if dt not in evolucao:
            evolucao[dt] = {'qtd': 0, 'valor': 0.0}
        evolucao[dt]['qtd'] += 1
        evolucao[dt]['valor'] += float(r.get('valor_pagar', 0) or 0)

    dias = sorted(evolucao.keys())
    evolucao_labels = [d.strftime('%d/%m') for d in dias]
    evolucao_qtd = [evolucao[d]['qtd'] for d in dias]
    evolucao_valor = [evolucao[d]['valor'] for d in dias]

    return {
        'periodo_label': periodo_label,
        'total_propostas': total_propostas,
        'total_valor': total_valor,
        'aceitas': aceitas,
        'negociando': negociando,
        'recusados': recusados,
        'pendentes': pendentes,
        'taxa_aprovacao': taxa_aprovacao,
        'volume_empresa': volume_por_empresa_sorted,
        'status_counts': {'Aceito': aceitas, 'Negociando': negociando, 'Recusado': recusados, 'Pendente': pendentes},
        'evolucao_labels': evolucao_labels,
        'evolucao_qtd': evolucao_qtd,
        'evolucao_valor': evolucao_valor,
    }

def get_dashboard_data_mensal(mes_ref=None):
    propostas = load_propostas()
    if not mes_ref:
        mes_ref = datetime.now().strftime('%Y-%m')

    registros = []
    for p in propostas.values():
        dt_envio = _parse_datetime_br(p.get('data_envio', ''))
        if not dt_envio:
            continue
        if _mes_ref(dt_envio) != mes_ref:
            continue
        item = dict(p)
        item['_dt_envio'] = dt_envio
        registros.append(item)

    stats = _build_dashboard_stats(registros, _mes_label(mes_ref))
    stats['mes_ref'] = mes_ref
    stats['mes_label'] = _mes_label(mes_ref)
    return stats

def get_dashboard_data_intervalo(data_inicio, data_fim):
    propostas = load_propostas()

    registros = []
    for p in propostas.values():
        dt_envio = _parse_datetime_br(p.get('data_envio', ''))
        if not dt_envio:
            continue
        dt_dia = dt_envio.date()
        if dt_dia < data_inicio.date() or dt_dia > data_fim.date():
            continue
        item = dict(p)
        item['_dt_envio'] = dt_envio
        registros.append(item)

    periodo_label = f"{data_inicio.strftime('%d/%m/%Y')} a {data_fim.strftime('%d/%m/%Y')}"
    stats = _build_dashboard_stats(registros, periodo_label)
    stats['mes_ref'] = ''
    stats['mes_label'] = periodo_label
    return stats

def get_lojas_data(df_processado):
    if df_processado is None or df_processado.empty:
        return {}
    return df_processado.groupby('Loja')['Valor a pagar'].sum().sort_values(ascending=False).to_dict()

# ==============================================
# GUI â€“ Classe Principal
# ==============================================
class AplicativoGUI:
    def __init__(self, root, ui_fonts, display_metrics):
        self.root = root
        self.ui_fonts = ui_fonts
        self.display_metrics = display_metrics
        self.ui_scale = display_metrics.get('ui_scale', 1.0)
        self._last_normal_geometry = None
        self.root.title(corrigir_texto_exibicao('Antecipacao de Pagamentos - Mercadao Atacadista'))
        self.root.configure(bg=MAIN_BG)
        self.root.protocol('WM_DELETE_WINDOW', self.finalizar)
        self.antecipacao = AntecipacaoPagamentos()
        self.logo_path = None
        self._chart_canvas = None
        self._dash_after_id = None
        self._resize_after_id = None
        self._build_ui()
        self._init_server()

    # -----------------------------------------------
    # InicializaÃ§Ã£o do servidor de respostas
    # -----------------------------------------------
    def _init_server(self):
        cfg = load_server_config()
        port = int(cfg.get('port', 5001))
        if FLASK_AVAILABLE:
            iniciar_servidor(port)
        else:
            print('Flask nao instalado. pip install flask para ativar respostas interativas.')

    # -----------------------------------------------
    # Layout raiz: sidebar + Ã¡rea principal
    # -----------------------------------------------
    def _build_ui(self):
        self._apply_window_geometry()

        # Container principal
        container = tk.Frame(self.root, bg=MAIN_BG)
        container.pack(fill='both', expand=True)

        # Sidebar
        self.sidebar = tk.Frame(container, bg=SIDEBAR_BG, width=self._scale(240))
        self.sidebar.pack(side='left', fill='y')
        self.sidebar.pack_propagate(False)

        # Ãrea de conteÃºdo
        self.content_area = tk.Frame(container, bg=MAIN_BG)
        self.content_area.pack(side='left', fill='both', expand=True)

        self._build_sidebar()
        self._pages = {}
        self._build_all_pages()
        self.root.bind('<Configure>', self._on_root_resize)
        self.root.after_idle(self._apply_responsive_layout)
        self._show_page('dashboard')

    def _scale(self, value, minimum=1):
        return max(minimum, int(round(value * self.ui_scale)))

    def _apply_window_geometry(self):
        screen_width = self.display_metrics['screen_width']
        screen_height = self.display_metrics['screen_height']
        min_w = self._scale(900)
        min_h = self._scale(600)
        width = _clamp(self._scale(1200), min_w, screen_width)
        height = _clamp(self._scale(800), min_h, screen_height)
        self._center_window(width, height)
        self.root.minsize(min_w, min_h)
        self.root.resizable(True, True)
        self._last_normal_geometry = (
            width,
            height,
            max(0, (screen_width - width) // 2),
            max(0, (screen_height - height) // 2),
        )

    def _on_root_resize(self, event):
        if event.widget is self.root:
            if self.root.state() != 'zoomed':
                self.root.update_idletasks()
                self._last_normal_geometry = (
                    self.root.winfo_width(),
                    self.root.winfo_height(),
                    self.root.winfo_x(),
                    self.root.winfo_y(),
                )
            if self._resize_after_id:
                try:
                    self.root.after_cancel(self._resize_after_id)
                except Exception:
                    pass

            width = event.width

            def _apply():
                self._resize_after_id = None
                self._apply_responsive_layout(width)

            self._resize_after_id = self.root.after(60, _apply)

    def _persist_window_geometry(self):
        cfg = load_server_config()
        win_cfg = dict(cfg.get('window_geometry') or {})

        state = str(self.root.state()).lower()
        win_cfg['state'] = 'zoomed' if state == 'zoomed' else 'normal'

        if state == 'zoomed' and self._last_normal_geometry:
            w, h, x, y = self._last_normal_geometry
        else:
            self.root.update_idletasks()
            w, h, x, y = (
                self.root.winfo_width(),
                self.root.winfo_height(),
                self.root.winfo_x(),
                self.root.winfo_y(),
            )

        win_cfg.update({'width': int(w), 'height': int(h), 'x': int(x), 'y': int(y)})
        cfg['window_geometry'] = win_cfg
        save_server_config(cfg)

    def _apply_responsive_layout(self, window_width=None):
        self._update_sidebar_width(window_width)
        if hasattr(self, '_email_tree'):
            self._apply_treeview_columns(self._email_tree, self._email_tree_columns)
        if hasattr(self, '_prop_tree'):
            self._apply_treeview_columns(self._prop_tree, self._prop_tree_columns)

    def _update_sidebar_width(self, window_width=None):
        current_width = window_width or self.root.winfo_width() or self.display_metrics['screen_width']
        sidebar_width = _clamp(int(current_width * 0.18), self._scale(220), self._scale(340))
        if abs(self.sidebar.winfo_width() - sidebar_width) >= 2:
            self.sidebar.config(width=sidebar_width)

    def _bind_treeview_resize(self, container, tree, columns):
        def _resize(_event=None):
            self._apply_treeview_columns(tree, columns)

        container.bind('<Configure>', _resize)
        self.root.after_idle(_resize)

    def _apply_treeview_columns(self, tree, columns):
        total_width = tree.winfo_width()
        if total_width <= 1:
            total_width = tree.master.winfo_width()
        available_width = max(total_width - self._scale(28), self._scale(320))
        total_weight = sum(weight for _, weight, _ in columns)
        used_width = 0

        for index, (column, weight, min_width) in enumerate(columns):
            if index == len(columns) - 1:
                width = max(self._scale(min_width), available_width - used_width)
            else:
                width = max(self._scale(min_width), int(available_width * (weight / total_weight)))
                used_width += width
            tree.column(column, width=width, stretch=True)

    def _center_window(self, w, h):
        self.root.update_idletasks()
        x = (self.root.winfo_screenwidth() - w) // 2
        y = (self.root.winfo_screenheight() - h) // 2
        self.root.geometry(f'{w}x{h}+{x}+{y}')

    # -----------------------------------------------
    # Sidebar
    # -----------------------------------------------
    def _build_sidebar(self):
        # Topo â€“ Logo / Avatar
        top = tk.Frame(self.sidebar, bg=SIDEBAR_BG)
        top.pack(fill='x', pady=(24, 8))

        avatar_frame = tk.Frame(top, width=self._scale(64), height=self._scale(64), bg=ACCENT_BLUE,
                                 relief='flat', bd=0)
        avatar_frame.pack(pady=(0, 8))
        avatar_frame.pack_propagate(False)

        tk.Label(avatar_frame, text='MA', font=self.ui_fonts['avatar'],
                 fg=TEXT_WHITE, bg=ACCENT_BLUE).place(relx=.5, rely=.5, anchor='center')

        tk.Label(top, text='MERCADAO', font=self.ui_fonts['body_large'],
                 fg=TEXT_WHITE, bg=SIDEBAR_BG).pack()
        tk.Label(top, text='Mesa de Antecipacao', font=self.ui_fonts['body_small'],
                 fg='#a0c4e4', bg=SIDEBAR_BG).pack(pady=(0, 12))

        # Separador
        tk.Frame(self.sidebar, bg='#2d5282', height=1).pack(fill='x', padx=16)

        # Itens de navegaÃ§Ã£o
        nav_items = [
            ('dashboard',    'P', 'Painel'),
            ('relatorios',   'R', 'Relatorios'),
            ('fornecedores', 'F', 'Fornecedores'),
            ('propostas',    'E', 'Propostas'),
            ('configuracoes','C', 'Configuracoes'),
        ]

        self._nav_buttons = {}
        for key, icon, label in nav_items:
            btn = self._create_nav_button(key, icon, label)
            self._nav_buttons[key] = btn

        # RodapÃ© sidebar
        tk.Frame(self.sidebar, bg='#2d5282', height=1).pack(fill='x', padx=16, side='bottom', pady=8)
        tk.Label(self.sidebar, text='v2.0 - 2025', font=self.ui_fonts['body_small'],
                 fg='#5a85b5', bg=SIDEBAR_BG).pack(side='bottom', pady=4)

    def _create_nav_button(self, key, icon, label):
        frame = tk.Frame(self.sidebar, bg=SIDEBAR_BG, cursor='hand2')
        frame.pack(fill='x', padx=12, pady=2)

        inner = tk.Frame(frame, bg=SIDEBAR_BG, padx=12, pady=10)
        inner.pack(fill='x')

        lbl_icon = tk.Label(inner, text=icon, font=self.ui_fonts['nav_icon'], fg=TEXT_WHITE, bg=SIDEBAR_BG)
        lbl_icon.pack(side='left')
        lbl_text = tk.Label(inner, text=label, font=self.ui_fonts['nav'], fg=TEXT_WHITE, bg=SIDEBAR_BG)
        lbl_text.pack(side='left', padx=10)

        def on_enter(e):
            if self._current_page != key:
                inner.config(bg=SIDEBAR_HOVER)
                lbl_icon.config(bg=SIDEBAR_HOVER)
                lbl_text.config(bg=SIDEBAR_HOVER)

        def on_leave(e):
            if self._current_page != key:
                inner.config(bg=SIDEBAR_BG)
                lbl_icon.config(bg=SIDEBAR_BG)
                lbl_text.config(bg=SIDEBAR_BG)

        def on_click(e, k=key):
            self._show_page(k)

        for w in [frame, inner, lbl_icon, lbl_text]:
            w.bind('<Enter>', on_enter)
            w.bind('<Leave>', on_leave)
            w.bind('<Button-1>', on_click)

        return (frame, inner, lbl_icon, lbl_text)

    def _current_page(self):
        return getattr(self, '_active_page', None)

    def _show_page(self, key):
        restore_geometry = None
        if self.root.state() != 'zoomed':
            self.root.update_idletasks()
            restore_geometry = (
                self.root.winfo_width(),
                self.root.winfo_height(),
                self.root.winfo_x(),
                self.root.winfo_y(),
            )

        self._active_page = key
        # Atualizar visual da sidebar
        for k, (frame, inner, li, lt) in self._nav_buttons.items():
            if k == key:
                inner.config(bg=SIDEBAR_HOVER)
                li.config(bg=SIDEBAR_HOVER)
                lt.config(bg=SIDEBAR_HOVER)
            else:
                inner.config(bg=SIDEBAR_BG)
                li.config(bg=SIDEBAR_BG)
                lt.config(bg=SIDEBAR_BG)

        # Mostrar a pÃ¡gina
        for k, page in self._pages.items():
            page.pack_forget()
        self._pages[key].pack(fill='both', expand=True)

        # Atualizar dashboard ao ser exibido
        if key == 'dashboard':
            self._start_dashboard_auto_refresh()
            self._refresh_dashboard()
        elif key == 'propostas':
            self._stop_dashboard_auto_refresh()
            self._refresh_propostas()
        else:
            self._stop_dashboard_auto_refresh()

        if restore_geometry:
            w, h, x, y = restore_geometry
            self.root.update_idletasks()
            self.root.geometry(f'{w}x{h}+{x}+{y}')
            self.root.after_idle(lambda: self.root.geometry(f'{w}x{h}+{x}+{y}'))

    def _start_dashboard_auto_refresh(self):
        self._stop_dashboard_auto_refresh()

        def _tick():
            if getattr(self, '_active_page', None) == 'dashboard':
                self._refresh_dashboard()
                self._dash_after_id = self.root.after(60000, _tick)

        self._dash_after_id = self.root.after(60000, _tick)

    def _stop_dashboard_auto_refresh(self):
        if self._dash_after_id:
            try:
                self.root.after_cancel(self._dash_after_id)
            except Exception:
                pass
        self._dash_after_id = None

    # -----------------------------------------------
    # ConstruÃ§Ã£o de todas as pÃ¡ginas
    # -----------------------------------------------
    def _build_all_pages(self):
        for key, fn in [
            ('dashboard',    self._build_page_dashboard),
            ('relatorios',   self._build_page_relatorios),
            ('fornecedores', self._build_page_fornecedores),
            ('propostas',    self._build_page_propostas),
            ('configuracoes',self._build_page_configuracoes),
        ]:
            frame = tk.Frame(self.content_area, bg=MAIN_BG)
            self._pages[key] = frame
            fn(frame)

    # -----------------------------------------------
    # Helpers de constuÃ§Ã£o de UI
    # -----------------------------------------------
    def _page_title(self, parent, title, subtitle=''):
        header = tk.Frame(parent, bg=MAIN_BG)
        header.pack(fill='x', padx=28, pady=(24, 4))
        tk.Label(header, text=title, font=self.ui_fonts['title'],
                 fg=TEXT_DARK, bg=MAIN_BG).pack(side='left')
        if subtitle:
            tk.Label(header, text=subtitle, font=self.ui_fonts['body'],
                     fg=TEXT_GRAY, bg=MAIN_BG).pack(side='left', padx=12, pady=4)
        tk.Frame(parent, bg='#e2e8f0', height=1).pack(fill='x', padx=28, pady=(4, 16))

    def _card(self, parent, title, value, color=CARD_BG, accent=ACCENT_BLUE):
        f = tk.Frame(parent, bg=CARD_BG, relief='flat', bd=0, padx=self._scale(20), pady=self._scale(16))
        f.config(highlightbackground='#e2e8f0', highlightthickness=1)
        tk.Frame(f, bg=accent, width=self._scale(4), height=self._scale(48)).pack(side='left', padx=(0, self._scale(12)))
        info = tk.Frame(f, bg=CARD_BG)
        info.pack(side='left')
        tk.Label(info, text=str(value), font=self.ui_fonts['metric'], fg=TEXT_DARK, bg=CARD_BG).pack(anchor='w')
        tk.Label(info, text=title, font=self.ui_fonts['body_small'], fg=TEXT_GRAY, bg=CARD_BG).pack(anchor='w')
        return f

    def _label_entry(self, parent, row, label, default='', width=40):
        tk.Label(parent, text=label, font=self.ui_fonts['body'], fg=TEXT_DARK, bg=CARD_BG).grid(
            row=row, column=0, sticky='w', padx=(0, 8), pady=6)
        var = tk.StringVar(value=default)
        e = ttk.Entry(parent, textvariable=var, width=width)
        e.grid(row=row, column=1, sticky='ew', pady=6)
        return var, e

    def _btn(self, parent, text, cmd, color=ACCENT_BLUE, fg=TEXT_WHITE, padx=18, pady=8):
        b = tk.Button(parent, text=text, command=cmd, bg=color, fg=fg,
                      font=self.ui_fonts['button'], relief='flat', padx=self._scale(padx), pady=self._scale(pady),
                      cursor='hand2', activebackground=SIDEBAR_HOVER, activeforeground=TEXT_WHITE,
                      bd=0)
        return b

    # -----------------------------------------------
    # PÃ¡gina: Dashboard
    # -----------------------------------------------
    def _build_page_dashboard(self, parent):
        self._dash_parent = parent
        self._page_title(parent, 'Painel Mensal', 'Consolidado diÃ¡rio e mensal de propostas')

        filtro_frame = tk.Frame(parent, bg=MAIN_BG)
        filtro_frame.pack(fill='x', padx=28, pady=(0, 8))
        tk.Label(filtro_frame, text='PerÃ­odo:', font=self.ui_fonts['body_bold'],
                 fg=TEXT_DARK, bg=MAIN_BG).pack(side='left')

        self._v_dash_period = tk.StringVar(value='Mes Atual')
        self._dash_period_combo = ttk.Combobox(
            filtro_frame,
            textvariable=self._v_dash_period,
            state='readonly',
            width=16,
            values=['Mes Atual']
        )
        self._dash_period_combo.pack(side='left', padx=8)
        self._dash_period_combo.bind('<<ComboboxSelected>>', self._on_dash_period_change)

        tk.Label(filtro_frame, text='Data Inicial:', font=self.ui_fonts['body_small'],
             fg=TEXT_DARK, bg=MAIN_BG).pack(side='left', padx=(16, 4))
        self._v_dash_data_ini = tk.StringVar(value=datetime.now().replace(day=1).strftime('%d/%m/%Y'))
        ttk.Entry(filtro_frame, textvariable=self._v_dash_data_ini, width=12).pack(side='left')

        tk.Label(filtro_frame, text='Data Final:', font=self.ui_fonts['body_small'],
             fg=TEXT_DARK, bg=MAIN_BG).pack(side='left', padx=(10, 4))
        self._v_dash_data_fim = tk.StringVar(value=datetime.now().strftime('%d/%m/%Y'))
        ttk.Entry(filtro_frame, textvariable=self._v_dash_data_fim, width=12).pack(side='left')

        self._btn(filtro_frame, 'Aplicar Intervalo', self._aplicar_intervalo_dashboard,
              color=ACCENT_ORANGE, padx=12, pady=4).pack(side='left', padx=8)

        # Cards de stat
        self._dash_cards_frame = tk.Frame(parent, bg=MAIN_BG)
        self._dash_cards_frame.pack(fill='x', padx=28, pady=8)

        # Ãrea de grÃ¡ficos
        self._dash_charts_frame = tk.Frame(parent, bg=MAIN_BG)
        self._dash_charts_frame.pack(fill='both', expand=True, padx=28, pady=8)

    def _on_dash_period_change(self, _event=None):
        self._refresh_dashboard(show_errors=True)

    def _aplicar_intervalo_dashboard(self):
        self._v_dash_period.set('Intervalo Personalizado')
        self._refresh_dashboard(show_errors=True)

    def _atualizar_opcoes_periodo_dashboard(self):
        meses = get_dashboard_month_refs()
        labels = ['Mes Atual', 'Intervalo Personalizado']
        atual_lbl = datetime.now().strftime('%m/%Y')
        for mref in meses:
            lbl = _mes_label(mref)
            if lbl and lbl != atual_lbl:
                labels.append(lbl)

        atual = self._v_dash_period.get().strip()
        self._dash_period_combo['values'] = labels
        if atual not in labels:
            self._v_dash_period.set('Mes Atual')

    def _refresh_dashboard(self, show_errors=False):
        sincronizar_respostas_ia()
        self._atualizar_opcoes_periodo_dashboard()

        periodo = self._v_dash_period.get().strip()
        if periodo == 'Intervalo Personalizado':
            try:
                data_ini = datetime.strptime(self._v_dash_data_ini.get().strip(), '%d/%m/%Y')
                data_fim = datetime.strptime(self._v_dash_data_fim.get().strip(), '%d/%m/%Y')
                if data_ini > data_fim:
                    raise ValueError('Data inicial maior que data final.')
                stats = get_dashboard_data_intervalo(data_ini, data_fim)
            except Exception:
                if show_errors:
                    messagebox.showwarning('PerÃ­odo invÃ¡lido', 'Informe Data Inicial e Data Final no formato DD/MM/AAAA.')
                stats = get_dashboard_data_mensal(datetime.now().strftime('%Y-%m'))
        else:
            mes_ref = _mes_ref_from_label(periodo)
            stats = get_dashboard_data_mensal(mes_ref)

        # Limpar cards
        for w in self._dash_cards_frame.winfo_children():
            w.destroy()

        # Cards de topo
        cards_info = [
            ('Total Propostas', stats['total_propostas'], ACCENT_BLUE),
            ('Valor Total', _fmt_moeda_br(stats['total_valor']), '#2c5282'),
            ('Aceitas', stats['aceitas'], SUCCESS_COLOR),
            ('Pendentes', stats['pendentes'], '#a0aec0'),
            ('Em NegociaÃ§Ã£o', stats['negociando'], ACCENT_ORANGE),
            ('Recusadas', stats['recusados'], DANGER_COLOR),
            ('Taxa AprovaÃ§Ã£o', f"{stats['taxa_aprovacao']:.1f}%", '#2f855a'),
        ]
        for i, (title, value, color) in enumerate(cards_info):
            c = self._card(self._dash_cards_frame, title, value, accent=color)
            c.grid(row=i // 4, column=i % 4, padx=8, pady=4, sticky='ew')
        for i in range(4):
            self._dash_cards_frame.columnconfigure(i, weight=1)

        # Limpar grÃ¡ficos anteriores
        for w in self._dash_charts_frame.winfo_children():
            w.destroy()

        # Criar figura matplotlib
        fig = Figure(figsize=(12, 4.5), dpi=90, facecolor=MAIN_BG)

        # GrÃ¡fico 1: EvoluÃ§Ã£o diÃ¡ria de propostas no mÃªs
        ax1 = fig.add_subplot(1, 3, 1)
        ax1.set_facecolor(CARD_BG)
        fig.patch.set_facecolor(MAIN_BG)
        if stats['evolucao_labels']:
            x = list(range(len(stats['evolucao_labels'])))
            ax1.plot(x, stats['evolucao_qtd'], color=ACCENT_BLUE, linewidth=2.2, marker='o', markersize=4)
            ax1.fill_between(x, stats['evolucao_qtd'], alpha=0.15, color=ACCENT_BLUE)
            ax1.set_xticks(x)
            ax1.set_xticklabels(stats['evolucao_labels'], rotation=45, ha='right', fontsize=7)
            ax1.set_ylabel('Qtd. propostas', fontsize=8, color=TEXT_GRAY)
            ax1.set_title(f"EvoluÃ§Ã£o DiÃ¡ria ({stats['periodo_label']})", fontsize=10, fontweight='bold', color=TEXT_DARK)
            ax1.tick_params(labelsize=7, colors=TEXT_GRAY)
            ax1.spines[['top', 'right']].set_visible(False)
        else:
            ax1.text(0.5, 0.5, 'Sem registros\nno perÃ­odo selecionado',
                     ha='center', va='center', transform=ax1.transAxes,
                     fontsize=9, color=TEXT_GRAY)
            ax1.set_title('EvoluÃ§Ã£o DiÃ¡ria', fontsize=10, fontweight='bold', color=TEXT_DARK)

        # GrÃ¡fico 2: Barras â€“ Top Empresas por volume no mÃªs
        ax2 = fig.add_subplot(1, 3, 2)
        ax2.set_facecolor(CARD_BG)
        vol_empresa = stats['volume_empresa'][:8]
        if vol_empresa:
            empresas = [str(e[0])[:14] for e in vol_empresa]
            volumes  = [e[1] for e in vol_empresa]
            colors_bar = [ACCENT_ORANGE if i == 0 else ACCENT_BLUE for i in range(len(empresas))]
            ax2.barh(empresas[::-1], volumes[::-1], color=colors_bar[::-1], edgecolor='none')
            ax2.set_xlabel('Valor a Pagar (R$)', fontsize=8, color=TEXT_GRAY)
            ax2.set_title(f"Rank de Empresas ({stats['periodo_label']})", fontsize=10, fontweight='bold', color=TEXT_DARK)
            ax2.tick_params(labelsize=7, colors=TEXT_GRAY)
            ax2.spines[['top', 'right']].set_visible(False)
        else:
            ax2.text(0.5, 0.5, 'Nenhuma proposta\nenviada no perÃ­odo',
                     ha='center', va='center', transform=ax2.transAxes,
                     fontsize=9, color=TEXT_GRAY)
            ax2.set_title('Rank de Empresas', fontsize=10, fontweight='bold', color=TEXT_DARK)

        # GrÃ¡fico 3: Pizza â€“ Status das Propostas
        ax3 = fig.add_subplot(1, 3, 3)
        ax3.set_facecolor(CARD_BG)
        status_data = {k: v for k, v in stats['status_counts'].items() if v > 0}
        if status_data:
            colors_pie = {
                'Aceito': SUCCESS_COLOR, 'Negociando': ACCENT_ORANGE,
                'Recusado': DANGER_COLOR, 'Pendente': '#a0aec0'
            }
            labels = list(status_data.keys())
            sizes  = list(status_data.values())
            pie_colors = [colors_pie.get(l, ACCENT_BLUE) for l in labels]
            wedges, texts, autotexts = ax3.pie(
                sizes, labels=labels, autopct='%1.0f%%',
                colors=pie_colors, startangle=90,
                textprops={'fontsize': 8, 'color': TEXT_DARK},
                wedgeprops={'edgecolor': 'white', 'linewidth': 2})
            for at in autotexts:
                at.set_fontsize(8)
                at.set_color(TEXT_WHITE)
            ax3.set_title('Status das Propostas', fontsize=10, fontweight='bold', color=TEXT_DARK)
        else:
            ax3.text(0.5, 0.5, 'Nenhuma proposta\nregistrada',
                     ha='center', va='center', transform=ax3.transAxes,
                     fontsize=9, color=TEXT_GRAY)
            ax3.set_title('Status das Propostas', fontsize=10, fontweight='bold', color=TEXT_DARK)

        fig.tight_layout(pad=2.5)

        canvas = FigureCanvasTkAgg(fig, master=self._dash_charts_frame)
        canvas.draw()
        canvas.get_tk_widget().pack(fill='both', expand=True)

    # -----------------------------------------------
    # PÃ¡gina: RelatÃ³rios
    # -----------------------------------------------
    def _build_page_relatorios(self, parent):
        self._page_title(parent, 'Gerar Relatorios', 'Processe e envie propostas de antecipacao')

        card = tk.Frame(parent, bg=CARD_BG, relief='flat', padx=32, pady=24)
        card.config(highlightbackground='#e2e8f0', highlightthickness=1)
        card.pack(fill='both', expand=True, padx=28, pady=8)
        card.columnconfigure(1, weight=1)

        self._v_logo = tk.StringVar()
        self._v_arquivo = tk.StringVar()
        self._v_data_pgto = tk.StringVar(value=datetime.now().strftime('%d/%m/%Y'))
        self._v_saida = tk.StringVar(value=os.path.join(os.path.expanduser('~'), 'Desktop', 'Relatorios_Antecipacao'))
        self._v_taxa = tk.StringVar()
        self._v_enviar_email = tk.BooleanVar(value=True)

        rows = [
            ('Logo (opcional):', self._v_logo, self.sel_logo, 'Selecionar Logo'),
            ('Arquivo Excel:',   self._v_arquivo, self.sel_arquivo, 'Selecionar Arquivo'),
        ]
        for i, (label, var, cmd, btn_txt) in enumerate(rows):
            tk.Label(card, text=label, font=self.ui_fonts['body'], fg=TEXT_DARK, bg=CARD_BG).grid(
                row=i, column=0, sticky='w', pady=8)
            ttk.Entry(card, textvariable=var, width=50).grid(row=i, column=1, sticky='ew', padx=8, pady=8)
            self._btn(card, btn_txt, cmd).grid(row=i, column=2, padx=4, pady=8)

        r = 2
        for label, var in [('Data de Pagamento (DD/MM/AAAA):', self._v_data_pgto),
                            ('Diretorio de Saida:', self._v_saida),
                            ('Taxa Fixa % (opcional, ex: 2,5):', self._v_taxa)]:
            tk.Label(card, text=label, font=self.ui_fonts['body'], fg=TEXT_DARK, bg=CARD_BG).grid(
                row=r, column=0, sticky='w', pady=8)
            extra_args = {}
            e = ttk.Entry(card, textvariable=var, width=50, **extra_args)
            e.grid(row=r, column=1, sticky='ew', padx=8, pady=8)
            if label.startswith('Diretorio'):
                self._btn(card, 'Selecionar Diretorio', self.sel_diretorio_saida).grid(row=r, column=2, padx=4, pady=8)
            r += 1

        # Checkbox email + botÃ£o processar
        chk_frame = tk.Frame(card, bg=CARD_BG)
        chk_frame.grid(row=r, column=0, columnspan=3, sticky='w', pady=8)
        ttk.Checkbutton(chk_frame, text='Enviar emails automaticamente', variable=self._v_enviar_email).pack(side='left')
        r += 1

        btn_frame = tk.Frame(card, bg=CARD_BG)
        btn_frame.grid(row=r, column=0, columnspan=3, pady=16)
        self._btn(btn_frame, 'Processar e Gerar Relatorios', self.processar,
                  color=ACCENT_BLUE, padx=28, pady=10).pack(side='left', padx=8)
        self._btn(btn_frame, 'Ver Colunas do Excel', self.verificar_colunas_excel,
                  color=ACCENT_ORANGE, padx=16, pady=10).pack(side='left', padx=8)
        self._btn(btn_frame, 'Abrir Pasta de Saida', self.abrir_pasta_saida,
                  color='#4a5568', padx=16, pady=10).pack(side='left', padx=8)
        r += 1

        self._prog = ttk.Progressbar(card, mode='indeterminate')
        self._prog.grid(row=r, column=0, columnspan=3, sticky='ew', pady=8)
        r += 1
        self._status_lbl = tk.Label(card, text='Pronto para processar',
                                     font=self.ui_fonts['body'], fg=SUCCESS_COLOR, bg=CARD_BG)
        self._status_lbl.grid(row=r, column=0, columnspan=3, pady=4)

    # -----------------------------------------------
    # PÃ¡gina: Fornecedores / Emails
    # -----------------------------------------------
    def _build_page_fornecedores(self, parent):
        self._page_title(parent, 'Fornecedores & Emails', 'Gerencie emails e importe da planilha Excel')

        paned = tk.Frame(parent, bg=MAIN_BG)
        paned.pack(fill='both', expand=True, padx=28)
        paned.columnconfigure(0, weight=1)
        paned.columnconfigure(1, weight=1)

        # Card Esquerdo â€“ Cadastro manual
        left = tk.Frame(paned, bg=CARD_BG, relief='flat', padx=24, pady=20)
        left.config(highlightbackground='#e2e8f0', highlightthickness=1)
        left.grid(row=0, column=0, sticky='nsew', padx=(0, 8))
        tk.Label(left, text='Cadastro Manual', font=self.ui_fonts['heading'],
                 fg=TEXT_DARK, bg=CARD_BG).pack(anchor='w', pady=(0, 12))

        form = tk.Frame(left, bg=CARD_BG)
        form.pack(fill='x')
        form.columnconfigure(1, weight=1)

        tk.Label(form, text='Fornecedor (Nome - CNPJ):', font=self.ui_fonts['body'],
                 fg=TEXT_DARK, bg=CARD_BG).grid(row=0, column=0, sticky='w', pady=6)
        pref_forn = get_fornecedor_email_pref()
        self._v_forn_key = tk.StringVar(value=pref_forn.get('fornecedor_key', ''))
        self._e_forn_key = ttk.Entry(form, textvariable=self._v_forn_key, width=30)
        self._e_forn_key.grid(row=0, column=1, sticky='ew', padx=8, pady=6)
        self._e_forn_key.bind('<FocusOut>', lambda _e: self._persistir_email_fornecedor_se_habilitado())

        tk.Label(form, text='Email:', font=self.ui_fonts['body'], fg=TEXT_DARK, bg=CARD_BG).grid(
            row=1, column=0, sticky='w', pady=6)
        self._v_forn_email = tk.StringVar(value=pref_forn.get('fornecedor_email', ''))
        self._e_forn_email = ttk.Entry(form, textvariable=self._v_forn_email, width=30)
        self._e_forn_email.grid(row=1, column=1, sticky='ew', padx=8, pady=6)
        self._e_forn_email.bind('<FocusOut>', lambda _e: self._persistir_email_fornecedor_se_habilitado())

        self._v_salvar_email_forn_auto = tk.BooleanVar(
            value=pref_forn.get('salvar_email_fornecedor_automaticamente', True)
        )
        ttk.Checkbutton(
            form,
            text='Salvar automaticamente',
            variable=self._v_salvar_email_forn_auto,
            command=self._on_toggle_salvar_email_fornecedor
        ).grid(row=2, column=1, sticky='w', padx=8, pady=(2, 6))

        btns = tk.Frame(left, bg=CARD_BG)
        btns.pack(pady=12)
        self._btn(btns, '+ Adicionar / Atualizar', self.add_email_forn, color=ACCENT_BLUE).pack(side='left', padx=4)
        self._btn(btns, 'Remover', self.rem_email_forn, color=DANGER_COLOR).pack(side='left', padx=4)

        # Card Direito â€“ Importar Excel
        right = tk.Frame(paned, bg=CARD_BG, relief='flat', padx=24, pady=20)
        right.config(highlightbackground='#e2e8f0', highlightthickness=1)
        right.grid(row=0, column=1, sticky='nsew', padx=(8, 0))
        tk.Label(right, text='Importar via Planilha Excel', font=self.ui_fonts['heading'],
                 fg=TEXT_DARK, bg=CARD_BG).pack(anchor='w', pady=(0, 8))
        tk.Label(right, text='Colunas esperadas: Nome/Fornecedor, CNPJ, Email\n(os nomes das colunas sao detectados automaticamente)',
             font=self.ui_fonts['body_small'], fg=TEXT_GRAY, bg=CARD_BG, justify='left').pack(anchor='w', pady=(0, 12))

        self._v_excel_import = tk.StringVar()
        impform = tk.Frame(right, bg=CARD_BG)
        impform.pack(fill='x')
        impform.columnconfigure(0, weight=1)
        ttk.Entry(impform, textvariable=self._v_excel_import).grid(row=0, column=0, sticky='ew', padx=(0, 8))
        self._btn(impform, 'Selecionar', self.sel_excel_import).grid(row=0, column=1)
        self._btn(right, 'Importar Planilha', self.importar_excel_emails,
                  color=SUCCESS_COLOR, padx=20, pady=10).pack(pady=12)

        # Lista de emails cadastrados
        tk.Frame(paned, bg='#e2e8f0', height=1).grid(row=1, column=0, columnspan=2, sticky='ew', pady=12)
        list_frame = tk.Frame(paned, bg=CARD_BG, relief='flat', padx=16, pady=12)
        list_frame.config(highlightbackground='#e2e8f0', highlightthickness=1)
        list_frame.grid(row=2, column=0, columnspan=2, sticky='nsew', pady=(0, 8))
        paned.rowconfigure(2, weight=1)

        header_row = tk.Frame(list_frame, bg=CARD_BG)
        header_row.pack(fill='x')
        tk.Label(header_row, text='Emails Cadastrados', font=self.ui_fonts['body_large'],
                 fg=TEXT_DARK, bg=CARD_BG).pack(side='left')
        self._btn(header_row, 'Atualizar Lista', self._refresh_email_list,
                  color='#4a5568', padx=12, pady=5).pack(side='right')

        cols = ('Fornecedor / CNPJ', 'Email')
        self._email_tree = ttk.Treeview(list_frame, columns=cols, show='headings', height=8)
        for col in cols:
            self._email_tree.heading(col, text=col)
        vsb = ttk.Scrollbar(list_frame, orient='vertical', command=self._email_tree.yview)
        self._email_tree.configure(yscrollcommand=vsb.set)
        self._email_tree.pack(side='left', fill='both', expand=True, pady=8)
        vsb.pack(side='right', fill='y', pady=8)
        self._email_tree_columns = [
            ('Fornecedor / CNPJ', 0.56, 250),
            ('Email', 0.44, 220),
        ]
        self._bind_treeview_resize(list_frame, self._email_tree, self._email_tree_columns)
        self._refresh_email_list()

    def _refresh_email_list(self):
        for row in self._email_tree.get_children():
            self._email_tree.delete(row)
        for k, v in load_email_map().items():
            self._email_tree.insert('', 'end', values=(k, v))

    # -----------------------------------------------
    # PÃ¡gina: Propostas
    # -----------------------------------------------
    def _build_page_propostas(self, parent):
        self._page_title(parent, 'Propostas Enviadas', 'Acompanhe respostas dos fornecedores')

        topo = tk.Frame(parent, bg=MAIN_BG)
        topo.pack(fill='x', padx=28, pady=(0, 8))
        self._btn(topo, 'Atualizar', self._refresh_propostas, color=ACCENT_BLUE, padx=14, pady=6).pack(side='left', padx=(0, 8))
        self._btn(topo, 'Enviar Aceitas do Dia', self.enviar_aceitas_do_dia, color=ACCENT_ORANGE, padx=14, pady=6).pack(side='left', padx=(0, 8))
        self._btn(topo, 'Abrir Pasta de Aceitas', self.abrir_propostas_aceitas, color=SUCCESS_COLOR, padx=14, pady=6).pack(side='left')

        destinatarios_frame = tk.Frame(parent, bg=MAIN_BG)
        destinatarios_frame.pack(fill='x', padx=28, pady=(0, 8))
        tk.Label(destinatarios_frame, text='Emails para envio das aceitas (separe por ; ou ,):',
                 font=self.ui_fonts['body_small'], fg=TEXT_DARK, bg=MAIN_BG).pack(side='left', padx=(0, 8))
        pref_envio = get_envio_aceitas_pref()
        self._v_emails_aceitas_dia = tk.StringVar(value=pref_envio.get('emails_aceitas_dia', ''))
        self._e_emails_aceitas_dia = ttk.Entry(destinatarios_frame, textvariable=self._v_emails_aceitas_dia, width=60)
        self._e_emails_aceitas_dia.pack(side='left', fill='x', expand=True)
        self._e_emails_aceitas_dia.bind('<FocusOut>', lambda _e: self._persistir_emails_aceitas_se_habilitado())

        self._v_salvar_emails_aceitas_auto = tk.BooleanVar(
            value=pref_envio.get('salvar_emails_aceitas_automaticamente', True)
        )
        ttk.Checkbutton(
            destinatarios_frame,
            text='Salvar automaticamente',
            variable=self._v_salvar_emails_aceitas_auto,
            command=self._on_toggle_salvar_emails_aceitas
        ).pack(side='left', padx=(8, 0))

        cols = ('Fornecedor', 'CNPJ', 'Email', 'Valor a Pagar', 'Data Envio', 'Status', 'Data Resposta')
        frame = tk.Frame(parent, bg=MAIN_BG)
        frame.pack(fill='both', expand=True, padx=28)

        self._prop_tree = ttk.Treeview(frame, columns=cols, show='headings', height=20)
        widths = {'Fornecedor': 170, 'CNPJ': 110, 'Email': 180, 'Valor a Pagar': 110,
                  'Data Envio': 110, 'Status': 90, 'Data Resposta': 110}
        for col in cols:
            self._prop_tree.heading(col, text=col)
            self._prop_tree.column(col, width=widths.get(col, 100))

        # Tags de cor por status
        self._prop_tree.tag_configure('aceito',    background='#e6ffed', foreground='#276749')
        self._prop_tree.tag_configure('negociando',background='#fff3cd', foreground='#856404')
        self._prop_tree.tag_configure('recusado',  background='#ffe4e4', foreground='#9b1c1c')
        self._prop_tree.tag_configure('pendente',  background='#f7fafc', foreground='#4a5568')

        vsb = ttk.Scrollbar(frame, orient='vertical', command=self._prop_tree.yview)
        self._prop_tree.configure(yscrollcommand=vsb.set)
        self._prop_tree.pack(side='left', fill='both', expand=True)
        vsb.pack(side='right', fill='y')
        self._prop_tree_columns = [
            ('Fornecedor', 0.20, 170),
            ('CNPJ', 0.12, 110),
            ('Email', 0.22, 180),
            ('Valor a Pagar', 0.12, 120),
            ('Data Envio', 0.12, 110),
            ('Status', 0.10, 100),
            ('Data Resposta', 0.12, 120),
        ]
        self._bind_treeview_resize(frame, self._prop_tree, self._prop_tree_columns)

    def _refresh_propostas(self):
        sincronizar_respostas_ia()
        for row in self._prop_tree.get_children():
            self._prop_tree.delete(row)
        propostas = load_propostas()

        def fmt_val(v):
            try:
                return f"R$ {float(v):,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
            except Exception:
                return str(v)

        status_labels = {'aceito': 'Aceito', 'negociando': 'Negociando', 'recusado': 'Recusado', 'pendente': 'Pendente'}
        for token, p in sorted(propostas.items(), key=lambda x: x[1].get('data_envio', ''), reverse=True):
            st = p.get('status', 'pendente')
            self._prop_tree.insert('', 'end', values=(
                p.get('fornecedor', ''),
                p.get('cnpj', ''),
                p.get('email', ''),
                fmt_val(p.get('valor_pagar', 0)),
                p.get('data_envio', ''),
                status_labels.get(st, st),
                p.get('data_resposta', '') or '-',
            ), tags=(st,))

    # -----------------------------------------------
    # PÃ¡gina: ConfiguraÃ§Ãµes
    # -----------------------------------------------
    def _build_page_configuracoes(self, parent):
        self._page_title(parent, 'Configuracoes', 'SMTP e servidor de respostas')

        notebook = ttk.Notebook(parent)
        notebook.pack(fill='both', expand=True, padx=28, pady=0)

        # Aba SMTP
        smtp_frame = tk.Frame(notebook, bg=CARD_BG, padx=24, pady=20)
        notebook.add(smtp_frame, text='  Configuracoes SMTP  ')
        self._build_smtp_tab(smtp_frame)

        # Aba Servidor
        srv_frame = tk.Frame(notebook, bg=CARD_BG, padx=24, pady=20)
        notebook.add(srv_frame, text='  Servidor de Respostas  ')
        self._build_server_tab(srv_frame)

    def _build_smtp_tab(self, frame):
        frame.columnconfigure(1, weight=1)
        ss, sp, su, _ = get_smtp_credentials()

        tk.Label(frame, text='Configuracoes SMTP', font=self.ui_fonts['heading'],
                 fg=TEXT_DARK, bg=CARD_BG).grid(row=0, column=0, columnspan=2, sticky='w', pady=(0, 16))

        labels = ['Servidor SMTP:', 'Porta SMTP:', 'Usuario SMTP:', 'Senha SMTP:']
        defaults = [ss or '', str(sp) if sp else '587', su or '', '']
        self._smtp_vars = []
        for i, (lbl, dflt) in enumerate(zip(labels, defaults)):
            tk.Label(frame, text=lbl, font=self.ui_fonts['body'], fg=TEXT_DARK, bg=CARD_BG).grid(
                row=i + 1, column=0, sticky='w', pady=8)
            show = '*' if 'Senha' in lbl else ''
            var = tk.StringVar(value=dflt)
            e = ttk.Entry(frame, textvariable=var, width=40, show=show)
            e.grid(row=i + 1, column=1, sticky='ew', padx=8, pady=8)
            self._smtp_vars.append(var)
        tk.Label(frame, text='(deixe a senha em branco para manter a salva)', font=self.ui_fonts['body_small'],
                 fg=TEXT_GRAY, bg=CARD_BG).grid(row=5, column=1, sticky='w')

        btns = tk.Frame(frame, bg=CARD_BG)
        btns.grid(row=6, column=0, columnspan=2, pady=16)
        self._btn(btns, 'Salvar SMTP', self.salvar_smtp, color=ACCENT_BLUE).pack(side='left', padx=8)
        self._btn(btns, 'Testar Conexao', self.testar_smtp, color='#4a5568').pack(side='left', padx=8)

    def _build_server_tab(self, frame):
        frame.columnconfigure(1, weight=1)
        cfg = load_server_config()

        tk.Label(
            frame,
            text='Servidor de Respostas (Flask)',
            font=self.ui_fonts['heading'],
            fg=TEXT_DARK,
            bg=CARD_BG,
        ).grid(row=0, column=0, columnspan=2, sticky='w', pady=(0, 16))

        info = (
            'O servidor recebe as respostas dos fornecedores (Aceito / Negociar / Recusar).\n'
            'Para uso externo (fornecedores fora da rede local), configure uma URL publica.\n'
            'Voce pode usar ngrok, Render.com, ou qualquer servidor com IP publico.'
        )
        tk.Label(
            frame,
            text=info,
            font=self.ui_fonts['body_small'],
            fg=TEXT_GRAY,
            bg=CARD_BG,
            justify='left',
        ).grid(row=1, column=0, columnspan=2, sticky='w', pady=(0, 16))

        tk.Label(
            frame,
            text='URL Base (ex: http://meuservidor.com):',
            font=self.ui_fonts['body'],
            fg=TEXT_DARK,
            bg=CARD_BG,
        ).grid(row=2, column=0, sticky='w', pady=8)
        self._v_base_url = tk.StringVar(value=cfg.get('base_url', 'http://localhost:5001'))
        ttk.Entry(frame, textvariable=self._v_base_url, width=45).grid(row=2, column=1, sticky='ew', padx=8, pady=8)

        tk.Label(
            frame,
            text='Porta do Servidor Local:',
            font=self.ui_fonts['body'],
            fg=TEXT_DARK,
            bg=CARD_BG,
        ).grid(row=3, column=0, sticky='w', pady=8)
        self._v_srv_port = tk.StringVar(value=str(cfg.get('port', 5001)))
        ttk.Entry(frame, textvariable=self._v_srv_port, width=10).grid(row=3, column=1, sticky='w', padx=8, pady=8)

        tk.Label(
            frame,
            text='ngrok Authtoken (opcional):',
            font=self.ui_fonts['body'],
            fg=TEXT_DARK,
            bg=CARD_BG,
        ).grid(row=4, column=0, sticky='w', pady=8)
        self._v_ngrok_token = tk.StringVar(value=str(cfg.get('ngrok_authtoken', '') or ''))
        ttk.Entry(frame, textvariable=self._v_ngrok_token, width=45, show='*').grid(row=4, column=1, sticky='ew', padx=8, pady=8)

        flask_status = 'Flask instalado' if FLASK_AVAILABLE else 'Flask NAO instalado - execute: pip install flask'
        tk.Label(
            frame,
            text=flask_status,
            font=self.ui_fonts['body'],
            fg=SUCCESS_COLOR if FLASK_AVAILABLE else DANGER_COLOR,
            bg=CARD_BG,
        ).grid(row=5, column=0, columnspan=2, sticky='w', pady=8)

        ngrok_status = 'pyngrok instalado (URL publica automatica disponivel)' if NGROK_AVAILABLE else 'pyngrok nao instalado - execute: pip install pyngrok'
        tk.Label(
            frame,
            text=ngrok_status,
            font=self.ui_fonts['body_small'],
            fg=SUCCESS_COLOR if NGROK_AVAILABLE else WARN_COLOR,
            bg=CARD_BG,
        ).grid(row=6, column=0, columnspan=2, sticky='w', pady=(0, 8))

        btns = tk.Frame(frame, bg=CARD_BG)
        btns.grid(row=7, column=0, columnspan=2, pady=16)
        self._btn(btns, 'Salvar Configuracao', self.salvar_server_config, color=ACCENT_BLUE).pack(side='left', padx=8)
        if FLASK_AVAILABLE:
            self._btn(btns, 'Testar Servidor', self.testar_servidor, color='#4a5568').pack(side='left', padx=8)

    # -----------------------------------------------
    # AÃ§Ãµes dos botÃµes
    # -----------------------------------------------
    def sel_logo(self):
        p = filedialog.askopenfilename(filetypes=[('Imagens', '*.png *.jpg *.jpeg')])
        if p:
            self._v_logo.set(p)
            self.logo_path = p

    def sel_arquivo(self):
        p = filedialog.askopenfilename(filetypes=[('Excel', '*.xlsx *.xls')])
        if p:
            self._v_arquivo.set(p)

    def sel_diretorio_saida(self):
        d = filedialog.askdirectory()
        if d:
            self._v_saida.set(d)

    def sel_excel_import(self):
        p = filedialog.askopenfilename(filetypes=[('Excel', '*.xlsx *.xls')])
        if p:
            self._v_excel_import.set(p)

    def verificar_colunas_excel(self):
        """Mostra as colunas encontradas no Excel e como foram mapeadas."""
        path = self._v_arquivo.get().strip()
        if not path:
            messagebox.showwarning('Arquivo', 'Selecione um Arquivo Excel primeiro na aba RelatÃ³rios.')
            return
        try:
            df = pd.read_excel(path, nrows=0)
            cols = list(df.columns.str.strip())

            mapeamentos = {
                'CNPJ': ['cnpj'],
                'Fornecedor': ['fornecedor', 'nome do forn', 'razao', 'razao social', 'nome forn'],
                'Numero doc.': ['nº doc', 'num doc', 'numero doc', 'documento', 'nota'],
                'Data de vencimento': ['vencimento', 'vencto', 'venc.', 'dt venc'],
                'Valor liquido': ['valor liq', 'vlr liq', 'valor liquido', 'valor liquido total'],
                'Loja': ['loja'],
                'Prazo': ['prazo'],
            }

            linhas = ['Colunas encontradas no arquivo:\n']
            for c in cols:
                linhas.append(f'  â€¢ {c}')

            linhas.append('\n\nMapeamento detectado (Campo â†’ Coluna no Excel):')
            for destino, palavras in mapeamentos.items():
                encontrada = next(
                    (c for c in cols if any(p in c.lower() for p in palavras)), None)
                status = f'âœ… "{encontrada}"' if encontrada else 'âŒ NÃƒO ENCONTRADA (serÃ¡ ignorada)'
                obrig = ' *obrigatoria*' if destino in ['CNPJ', 'Fornecedor', 'Data de vencimento', 'Valor liquido'] else ''
                linhas.append(f'  {destino}{obrig}: {status}')

            messagebox.showinfo('DiagnÃ³stico do Excel', '\n'.join(linhas))
        except Exception as e:
            messagebox.showerror('Erro', f'NÃ£o foi possÃ­vel ler o arquivo:\n{e}')

    def abrir_pasta_saida(self):
        d = self._v_saida.get().strip() or os.path.join(os.path.expanduser('~'), 'Desktop', 'Relatorios_Antecipacao')
        os.makedirs(d, exist_ok=True)
        os.startfile(d)

    def abrir_propostas_aceitas(self):
        os.makedirs(PROPOSTAS_ACEITAS_DIR, exist_ok=True)
        os.startfile(PROPOSTAS_ACEITAS_DIR)

    def importar_excel_emails(self):
        path = self._v_excel_import.get().strip()
        if not path:
            messagebox.showwarning('Arquivo', 'Selecione um arquivo Excel primeiro.')
            return
        count, err = importar_emails_excel(path)
        if err:
            messagebox.showerror('Erro', f'Erro ao importar:\n{err}')
        else:
            messagebox.showinfo('ImportaÃ§Ã£o', f'{count} email(s) importado(s) com sucesso!')
            self._refresh_email_list()

    def add_email_forn(self):
        key   = self._v_forn_key.get().strip()
        email = self._v_forn_email.get().strip()
        if not key or not email:
            messagebox.showwarning('Campos', 'Preencha o Fornecedor e o Email.')
            return
        if '@' not in email:
            messagebox.showwarning('Email', 'Email invÃ¡lido.')
            return
        add_email_fornecedor(key, email)
        save_fornecedor_email_pref(
            fornecedor_key=key,
            fornecedor_email=email,
            salvar_email_fornecedor_automaticamente=bool(getattr(self, '_v_salvar_email_forn_auto', tk.BooleanVar(value=True)).get())
        )
        messagebox.showinfo('Sucesso', f'Email {email} salvo para {key}.')
        self._v_forn_key.set('')
        self._v_forn_email.set('')
        self._refresh_email_list()

    def rem_email_forn(self):
        key = self._v_forn_key.get().strip()
        if not key:
            messagebox.showwarning('Campo', 'Informe o Fornecedor para remover.')
            return
        remove_email_fornecedor(key)
        save_fornecedor_email_pref(fornecedor_key=key,
                                   fornecedor_email=self._v_forn_email.get().strip(),
                                   salvar_email_fornecedor_automaticamente=bool(getattr(self, '_v_salvar_email_forn_auto', tk.BooleanVar(value=True)).get()))
        messagebox.showinfo('Removido', f'Email de {key} removido.')
        self._v_forn_key.set('')
        self._refresh_email_list()

    def _on_toggle_salvar_email_fornecedor(self):
        save_fornecedor_email_pref(
            fornecedor_key=self._v_forn_key.get().strip(),
            fornecedor_email=self._v_forn_email.get().strip(),
            salvar_email_fornecedor_automaticamente=bool(self._v_salvar_email_forn_auto.get())
        )

    def _persistir_email_fornecedor_se_habilitado(self):
        if not getattr(self, '_v_salvar_email_forn_auto', None):
            return

        key = self._v_forn_key.get().strip()
        email = self._v_forn_email.get().strip()
        habilitado = bool(self._v_salvar_email_forn_auto.get())

        save_fornecedor_email_pref(
            fornecedor_key=key,
            fornecedor_email=email,
            salvar_email_fornecedor_automaticamente=habilitado
        )

        if not habilitado:
            return
        if not key or not email:
            return
        if not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', email):
            return

        add_email_fornecedor(key, email)
        if hasattr(self, '_email_tree'):
            self._refresh_email_list()

    def salvar_smtp(self):
        ss, sp, su, spw = [v.get().strip() for v in self._smtp_vars]
        if not all([ss, sp, su]):
            messagebox.showwarning('Campos', 'Preencha servidor, porta e usuÃ¡rio.')
            return
        if not spw:
            _, _, _, spw = get_smtp_credentials()
            spw = spw or ''
        try:
            set_smtp_credentials(ss, sp, su, spw)
            messagebox.showinfo('Salvo', 'ConfiguraÃ§Ãµes SMTP salvas!')
        except Exception as e:
            messagebox.showerror('Erro', str(e))

    def testar_smtp(self):
        ss, sp, su, spw = [v.get().strip() for v in self._smtp_vars]
        if not spw:
            _, _, _, spw = get_smtp_credentials()
            spw = spw or ''
        if not all([ss, sp, su, spw]):
            messagebox.showwarning('Campos', 'Preencha todos os campos SMTP.')
            return
        try:
            p = int(re.search(r'(\d+)', sp).group(1))
            with smtplib.SMTP(ss, p) as srv:
                srv.starttls()
                srv.login(su, spw)
            messagebox.showinfo('Sucesso', 'ConexÃ£o SMTP OK!')
        except Exception as e:
            messagebox.showerror('Erro', str(e))

    def salvar_server_config(self):
        cfg = {
            'base_url': self._v_base_url.get().strip(),
            'port': int(self._v_srv_port.get().strip() or 5001),
            'ngrok_authtoken': self._v_ngrok_token.get().strip(),
        }
        save_server_config(cfg)
        messagebox.showinfo('Salvo', 'ConfiguraÃ§Ã£o do servidor salva!')

    def testar_servidor(self):
        import urllib.request
        try:
            port = self._v_srv_port.get().strip() or '5001'
            urllib.request.urlopen(f'http://localhost:{port}/status', timeout=3)
            messagebox.showinfo('Servidor', f'Servidor respondendo na porta {port}!')
        except Exception:
            messagebox.showwarning('Servidor', 'Servidor nÃ£o respondeu. Verifique se estÃ¡ rodando.')

    def _selecionar_destinatarios(self, sugestoes=None):
        sugestoes = sorted(set(s for s in (sugestoes or []) if s and '@' in s), key=lambda x: x.lower())
        resultado = {'emails': None}

        win = tk.Toplevel(self.root)
        win.title(corrigir_texto_exibicao('Selecionar DestinatÃ¡rios'))
        win.configure(bg=CARD_BG)
        dialog_width = _clamp(int(self.display_metrics['screen_width'] * 0.32), self._scale(520), self._scale(760))
        dialog_height = _clamp(int(self.display_metrics['screen_height'] * 0.42), self._scale(430), self._scale(620))
        win.geometry(f'{dialog_width}x{dialog_height}')
        win.transient(self.root)
        win.grab_set()

        tk.Label(win, text='Selecione um ou mais destinatÃ¡rios:',
             font=self.ui_fonts['body_bold'], fg=TEXT_DARK, bg=CARD_BG).pack(anchor='w', padx=16, pady=(16, 8))

        lista = tk.Listbox(win, selectmode='multiple', height=10)
        for e in sugestoes:
            lista.insert(tk.END, e)
        lista.pack(fill='both', expand=True, padx=16)

        tk.Label(win, text='Emails adicionais (separe por ; ou ,):',
             font=self.ui_fonts['body_small'], fg=TEXT_GRAY, bg=CARD_BG).pack(anchor='w', padx=16, pady=(10, 4))
        extra_var = tk.StringVar()
        ttk.Entry(win, textvariable=extra_var).pack(fill='x', padx=16)

        def confirmar():
            emails = []
            for idx in lista.curselection():
                email = str(lista.get(idx)).strip()
                if email and email not in emails:
                    emails.append(email)

            extras = [x.strip() for x in re.split(r'[;,]', extra_var.get() or '') if x.strip()]
            for email in extras:
                if '@' in email and email not in emails:
                    emails.append(email)

            if not emails:
                messagebox.showwarning('DestinatÃ¡rios', 'Selecione ou informe ao menos um email.', parent=win)
                return

            invalidos = [e for e in emails if not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', e)]
            if invalidos:
                messagebox.showwarning('Email invÃ¡lido', f'Email(s) invÃ¡lido(s):\n' + '\n'.join(invalidos), parent=win)
                return

            resultado['emails'] = emails
            win.destroy()

        def cancelar():
            resultado['emails'] = None
            win.destroy()

        botoes = tk.Frame(win, bg=CARD_BG)
        botoes.pack(fill='x', padx=16, pady=16)
        self._btn(botoes, 'Confirmar', confirmar, color=ACCENT_BLUE, padx=14, pady=6).pack(side='left')
        self._btn(botoes, 'Cancelar', cancelar, color='#4a5568', padx=14, pady=6).pack(side='left', padx=8)

        win.wait_window()
        return resultado['emails']

    def _parse_emails_texto(self, texto):
        emails = [x.strip() for x in re.split(r'[;,]', str(texto or '')) if x.strip()]
        invalidos = [e for e in emails if not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', e)]
        if invalidos:
            raise ValueError('Email(s) invÃ¡lido(s):\n' + '\n'.join(invalidos))
        # Remove duplicados preservando ordem
        unicos = []
        for e in emails:
            if e not in unicos:
                unicos.append(e)
        return unicos

    def _on_toggle_salvar_emails_aceitas(self):
        habilitado = bool(self._v_salvar_emails_aceitas_auto.get())
        save_envio_aceitas_pref(
            emails_aceitas_dia=self._v_emails_aceitas_dia.get().strip(),
            salvar_emails_aceitas_automaticamente=habilitado
        )

    def _persistir_emails_aceitas_se_habilitado(self, texto_forcado=None):
        if not getattr(self, '_v_salvar_emails_aceitas_auto', None):
            return
        if not self._v_salvar_emails_aceitas_auto.get():
            return
        texto = self._v_emails_aceitas_dia.get().strip() if texto_forcado is None else str(texto_forcado).strip()
        save_envio_aceitas_pref(
            emails_aceitas_dia=texto,
            salvar_emails_aceitas_automaticamente=True
        )

    def _enviar_aceitas_em_thread(self, ss, sp, su, spw, aceitas_hoje, destinatarios):
        """Executa o envio de emails em uma thread separada para nÃ£o bloquear a UI."""
        try:
            sender = EmailSender(ss, sp, su, spw)
            enviados = 0
            falhas = 0
            sem_anexo = 0

            for p in aceitas_hoje:
                fornecedor = p.get('fornecedor', 'Fornecedor')
                cnpj = p.get('cnpj', '')
                valor = _fmt_moeda_br(p.get('valor_pagar', 0))
                data_pgto = p.get('data_pagamento', '')
                data_resp = p.get('data_resposta', '')
                anexo = p.get('pdf_path', '')

                anexos = []
                if anexo and os.path.exists(anexo):
                    anexos = [anexo]
                else:
                    sem_anexo += 1

                assunto = f"[Proposta Aprovada] {fornecedor} ({cnpj})"
                html = f"""<!DOCTYPE html>
<html lang='pt-BR'><head><meta charset='UTF-8'></head>
<body style='font-family:Arial,sans-serif;background:#f7fafc;padding:16px;'>
  <div style='max-width:580px;background:#fff;border:1px solid #e2e8f0;border-radius:10px;padding:18px;'>
    <h3 style='margin:0 0 10px;color:#1e3a5f;'>Proposta aprovada no dia</h3>
    <p style='margin:0 0 10px;color:#4a5568;'>Resumo da proposta aprovada:</p>
    <table style='width:100%;border-collapse:collapse;font-size:13px;'>
      <tr><td style='padding:6px 0;color:#718096;'>Fornecedor</td><td style='padding:6px 0;color:#2d3748;font-weight:bold;'>{fornecedor}</td></tr>
      <tr><td style='padding:6px 0;color:#718096;'>CNPJ</td><td style='padding:6px 0;color:#2d3748;'>{cnpj}</td></tr>
      <tr><td style='padding:6px 0;color:#718096;'>Valor a Pagar</td><td style='padding:6px 0;color:#2d3748;font-weight:bold;'>{valor}</td></tr>
      <tr><td style='padding:6px 0;color:#718096;'>Data Pagamento</td><td style='padding:6px 0;color:#2d3748;'>{data_pgto}</td></tr>
      <tr><td style='padding:6px 0;color:#718096;'>Data AprovaÃ§Ã£o</td><td style='padding:6px 0;color:#2d3748;'>{data_resp}</td></tr>
    </table>
    <p style='margin:12px 0 0;color:#718096;font-size:12px;'>Anexo: relatÃ³rio PDF da proposta aprovada.</p>
  </div>
</body></html>"""
                plain = (
                    'Proposta aprovada no dia\n\n'
                    f'Fornecedor: {fornecedor}\n'
                    f'CNPJ: {cnpj}\n'
                    f'Valor a Pagar: {valor}\n'
                    f'Data Pagamento: {data_pgto}\n'
                    f'Data AprovaÃ§Ã£o: {data_resp}\n'
                )

                for dest in destinatarios:
                    ok = sender.send_email(dest, assunto, html, plain, attachment_paths=anexos)
                    if ok:
                        enviados += 1
                    else:
                        falhas += 1

            total_emails = len(aceitas_hoje) * len(destinatarios)
            msg = (
                f'Propostas aceitas hoje: {len(aceitas_hoje)}\n'
                f'DestinatÃ¡rios: {len(destinatarios)}\n'
                f'Lista: {", ".join(destinatarios)}\n'
                f'Emails previstos: {total_emails}\n'
                f'Emails enviados com sucesso: {enviados}\n'
                f'Falhas de envio: {falhas}\n'
                f'Propostas sem anexo encontrado: {sem_anexo}'
            )
            self.root.after(0, lambda: messagebox.showinfo('Resumo do Envio em Lote', msg))
        except Exception as e:
            self.root.after(0, lambda e=e: messagebox.showerror('Erro ao enviar', str(e)))
            traceback.print_exc()

    def enviar_aceitas_do_dia(self):
        ss, sp, su, spw = get_smtp_credentials()
        if not all([ss, sp, su, spw]):
            messagebox.showwarning('SMTP', 'Configure SMTP antes de enviar os emails.')
            return

        hoje = datetime.now().strftime('%d/%m/%Y')
        propostas = load_propostas()
        aceitas_hoje = [
            p for p in propostas.values()
            if p.get('status') == 'aceito' and str(p.get('data_resposta', '')).startswith(hoje)
        ]

        if not aceitas_hoje:
            messagebox.showinfo('Envio em lote', 'Nenhuma proposta aceita hoje foi encontrada.')
            return

        sugestoes = set()
        sugestoes.add(su)
        for p in aceitas_hoje:
            if p.get('email'):
                sugestoes.add(p.get('email'))
        for em in load_email_map().values():
            if em:
                sugestoes.add(em)

        # Se houver emails preenchidos no campo da tela de Propostas, usa esses destinatÃ¡rios direto.
        destinatarios_campo = []
        try:
            destinatarios_campo = self._parse_emails_texto(self._v_emails_aceitas_dia.get())
        except ValueError as e:
            messagebox.showwarning('Emails invÃ¡lidos', str(e))
            return

        if destinatarios_campo:
            destinatarios = destinatarios_campo
        else:
            destinatarios = self._selecionar_destinatarios(list(sugestoes))
            if not destinatarios:
                return

        self._persistir_emails_aceitas_se_habilitado('; '.join(destinatarios))

        # Inicia o envio em uma thread separada
        thread = threading.Thread(target=self._enviar_aceitas_em_thread,
                                 args=(ss, sp, su, spw, aceitas_hoje, destinatarios),
                                 daemon=True)
        thread.start()

    def _processar_em_thread(self, arquivo, data_pgto, diretorio, taxa_fixa, enviar_email):
        """Executa o processamento em uma thread separada para nÃ£o bloquear a UI."""
        try:
            df = self.antecipacao.processar_arquivo(arquivo, data_pgto, taxa_fixa)
            if not df.empty:
                taxa_unica = self.antecipacao._parse_taxa_percentual(taxa_fixa) if taxa_fixa else None
                data_pagamento = datetime.strptime(data_pgto, '%d/%m/%Y')
                data_base = datetime.now()
                cfg = load_server_config()
                base_url = cfg.get('base_url', 'http://localhost:5001')

                ok = self.antecipacao.gerar_pdfs(diretorio, self.logo_path,
                                                  data_base, data_pagamento,
                                                  taxa_unica, enviar_email, base_url)
                if ok:
                    # Usa after() para atualizar a UI de forma segura
                    self.root.after(0, lambda: self._status_lbl.config(
                        text='âœ… Processamento concluÃ­do com sucesso!', fg=SUCCESS_COLOR))
                    self.root.after(0, lambda: messagebox.showinfo(
                        'Sucesso', f'RelatÃ³rios gerados em:\n{diretorio}'))
                else:
                    self.root.after(0, lambda: self._status_lbl.config(
                        text='Erro ao gerar relatÃ³rios.', fg=DANGER_COLOR))
            else:
                self.root.after(0, lambda: self._status_lbl.config(
                    text='Nenhum dado processado.', fg=WARN_COLOR))
        except Exception as e:
            self.root.after(0, lambda e=e: messagebox.showerror('Erro', str(e)))
            self.root.after(0, lambda: self._status_lbl.config(
                text='Erro durante o processamento.', fg=DANGER_COLOR))
            traceback.print_exc()
        finally:
            self.root.after(0, self._prog.stop)

    def processar(self):
        arquivo      = self._v_arquivo.get().strip()
        data_pgto    = self._v_data_pgto.get().strip()
        diretorio    = self._v_saida.get().strip()
        taxa_fixa    = self._v_taxa.get().strip()
        enviar_email = self._v_enviar_email.get()

        if not arquivo or not data_pgto or not diretorio:
            messagebox.showwarning('Campos', 'Preencha Arquivo, Data de Pagamento e DiretÃ³rio.')
            return
        try:
            datetime.strptime(data_pgto, '%d/%m/%Y')
        except ValueError:
            messagebox.showwarning('Data', 'Data invÃ¡lida. Use DD/MM/AAAA.')
            return

        if enviar_email:
            cfg = load_server_config()
            base_url = cfg.get('base_url', 'http://localhost:5001')
            if _is_local_base_url(base_url):
                porta_local = int(cfg.get('port', 5001) or 5001)
                url_publica = _ensure_public_base_url(porta_local, cfg.get('ngrok_authtoken', ''))
                if url_publica:
                    cfg['base_url'] = url_publica
                    save_server_config(cfg)
                    if hasattr(self, '_v_base_url'):
                        self._v_base_url.set(url_publica)
                    messagebox.showinfo(
                        'URL Publica Ativada',
                        'Criamos automaticamente uma URL publica para este envio:\n\n'
                        + str(url_publica)
                        + '\n\nMantenha o aplicativo aberto durante as respostas.'
                    )
                else:
                    msg_tunel = (
                        '\nTentativa automatica de URL publica: '
                        + (str(_LAST_PUBLIC_TUNNEL_ERROR or '').strip() if NGROK_AVAILABLE else 'pyngrok nao instalado.')
                    )
                    continuar = messagebox.askyesno(
                        'URL Base Local Detectada',
                        'A URL Base atual estÃ¡ em localhost/127.0.0.1.\n\n'
                        'Fornecedores fora da sua mÃ¡quina NÃƒO conseguirÃ£o responder os botÃµes.\n\n'
                        'Dica: em Configuracoes > Servidor de Respostas, preencha o campo "ngrok Authtoken".\n\n'
                        'URL atual: ' + str(base_url) + msg_tunel + '\n\n'
                        'Deseja continuar mesmo assim?'
                    )
                    if not continuar:
                        return

        self._prog.start()
        self._status_lbl.config(text='Processando...', fg=ACCENT_BLUE)
        self.root.update()

        # Inicia o processamento em uma thread separada
        thread = threading.Thread(target=self._processar_em_thread,
                                 args=(arquivo, data_pgto, diretorio, taxa_fixa, enviar_email),
                                 daemon=True)
        thread.start()

    def finalizar(self):
        self._stop_dashboard_auto_refresh()
        if messagebox.askokcancel('Sair', 'Deseja realmente sair do sistema?'):
            try:
                self._persist_window_geometry()
            except Exception:
                pass
            self.root.quit()
            self.root.destroy()

# ==============================================
# Main
# ==============================================
def main():
    try:
        enable_high_dpi_support()
        aplicar_correcao_global_textos()
        root = tk.Tk()
        root.title(corrigir_texto_exibicao('Antecipacao de Pagamentos v2 - Mercadao Atacadista'))

        # DPI fixo e fonte global (aplicados uma Ãºnica vez no startup)
        root.tk.call('tk', 'scaling', 1.2)
        default_font = tkfont.nametofont('TkDefaultFont', root=root)
        default_font.configure(family='Segoe UI', size=12)
        root.option_add('*Font', default_font)

        display_metrics = get_display_metrics(root)
        ui_fonts = configure_ui_fonts(root, display_metrics['ui_scale'])

        # Estilo ttk
        style = ttk.Style(root)
        try:
            style.theme_use('clam')
        except Exception:
            pass
        style.configure('.', font=ui_fonts['body'])
        style.configure('TLabel', font=ui_fonts['body'])
        style.configure('TButton', font=ui_fonts['button'])
        style.configure('TCheckbutton', font=ui_fonts['body'])
        style.configure('TRadiobutton', font=ui_fonts['body'])
        style.configure('TNotebook', background=MAIN_BG, borderwidth=0)
        style.configure('TNotebook.Tab', padding=[max(10, int(round(12 * display_metrics['ui_scale']))), max(6, int(round(6 * display_metrics['ui_scale'])))], font=ui_fonts['tab'])
        style.configure('TEntry', padding=6, font=ui_fonts['body'])
        style.configure('TCombobox', font=ui_fonts['body'])
        style.configure('Treeview', rowheight=max(26, int(round(26 * display_metrics['ui_scale']))), font=ui_fonts['body'])
        style.configure('Treeview.Heading', font=ui_fonts['body_bold'])

        app = AplicativoGUI(root, ui_fonts, display_metrics)

        # Avisar se Flask nÃ£o instalado
        if not FLASK_AVAILABLE:
            messagebox.showwarning(
                'Flask nÃ£o instalado',
                'Para ativar os botÃµes de resposta no email, instale o Flask:\n\n'
                'pip install flask\n\n'
                'Sem o Flask, os emails ainda serÃ£o enviados com links de texto.'
            )

        # Avisar configuraÃ§Ã£o SMTP
        ss, sp, su, spw = get_smtp_credentials()
        if not all([ss, sp, su, spw]):
            messagebox.showinfo(
                'ConfiguraÃ§Ã£o SMTP',
                'Acesse "ConfiguraÃ§Ãµes > SMTP" para configurar o envio de emails.'
            )

        root.mainloop()
    except Exception as e:
        print(f'Erro: {e}')
        traceback.print_exc()
        input('Pressione Enter para sair...')

if __name__ == '__main__':
    main()


