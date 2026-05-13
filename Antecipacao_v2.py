import pandas as pd # type: ignore
from datetime import datetime, timezone, timedelta
import tkinter as tk
import tkinter.font as tkfont
from tkinter import filedialog, messagebox, ttk, simpledialog
import os
import sys
import traceback
FPDF = None
_FPDF_IMPORT_ERROR = ''
try:
    from fpdf import FPDF # type: ignore
except Exception as _e:
    _FPDF_IMPORT_ERROR = str(_e)
from PIL import Image, ImageTk # type: ignore
import tempfile
import json
import html
import csv
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
BACKUPS_MENSAIS_DIR = os.path.join(BASE_DIR, 'Backups_Mensais')
PROPOSTAS_GERADAS_DIR = os.path.join(BASE_DIR, 'Propostas_Geradas')
SERVER_CONFIG_FILE = os.path.join(BASE_DIR, 'server_config.json')
MOVIMENTOS_RELATORIOS_FILE = os.path.join(BASE_DIR, 'movimentos_relatorios.json')
RELATORIOS_MENSAIS_DIR = os.path.join(BASE_DIR, 'Relatorios_Mensais')

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
        tunel = ngrok.connect(addr=str(port), proto='http')
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
    base = str(url or '').strip().rstrip('/')
    if not base:
        return ''

    # Se o usuario informar sem esquema, assume HTTPS para hosts publicos.
    if '://' not in base:
        base = f'https://{base}'

    # Evita 307/308 em provedores que forcam HTTPS para dominios publicos.
    if base.lower().startswith('http://') and not _is_local_base_url(base):
        base = 'https://' + base[len('http://'):]

    return base


def _url_respostas_ativa(base_url, timeout=6):
    """Valida se a URL base responde ao endpoint /status do servidor de respostas."""
    base = _normalizar_base_url(base_url)
    if not base:
        return False
    endpoint = f"{base}/status"
    try:
        with urllib.request.urlopen(endpoint, timeout=max(1, int(timeout))) as resp:
            body = resp.read().decode('utf-8', errors='ignore').lower()
        return ('"status"' in body and 'ok' in body) or body.strip() == '{"status":"ok"}'
    except Exception:
        return False


def _registrar_proposta_resposta_remota(base_url, payload, timeout=8):
    """Registra token/proposta no servidor remoto para garantir que o link funcione."""
    base = _normalizar_base_url(base_url)
    if not base:
        return False

    # Para URL publica, prioriza HTTPS para evitar 307/308 de redirecionamento.
    base_lower = base.lower()
    tentativas_base = []
    if base_lower.startswith('http://') and not _is_local_base_url(base):
        tentativas_base.append('https://' + base[len('http://'):])
        tentativas_base.append(base)
    elif base_lower.startswith('https://') and not _is_local_base_url(base):
        tentativas_base.append(base)
        tentativas_base.append('http://' + base[len('https://'):])
    else:
        tentativas_base.append(base)

    # Remove duplicatas preservando ordem.
    tentativas_base = list(dict.fromkeys(tentativas_base))

    data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
    ultimo_erro = ''

    # Compatibilidade entre versões do backend.
    caminhos_registro = ['/api/propostas/register', '/propostas']

    for base_try in tentativas_base:
        for caminho in caminhos_registro:
            endpoint = f"{base_try}{caminho}"
            req = urllib.request.Request(
                endpoint,
                data=data,
                headers={'Content-Type': 'application/json'},
                method='POST',
            )
            try:
                with urllib.request.urlopen(req, timeout=max(1, int(timeout))) as resp:
                    status = int(getattr(resp, 'status', 0) or 0)
                    if status in (200, 201):
                        return True
                    ultimo_erro = f'status={status} endpoint={endpoint}'
            except urllib.error.HTTPError as e:
                ultimo_erro = f'HTTP {e.code} endpoint={endpoint}'
                # Alguns provedores redirecionam POST com 307/308 (ou 301/302/303)
                # de http para https. Nesses casos, tenta a proxima URL automaticamente.
                if e.code in (301, 302, 303, 307, 308, 405, 404):
                    continue
            except Exception as e:
                ultimo_erro = f'{e} endpoint={endpoint}'

    print(f'Falha ao registrar proposta no servidor remoto: {ultimo_erro}')
    return False


def _criar_link_resposta_ia(ai_base_url, numero_proposta, fornecedor, valor, data_proposta, taxa_desconto=None, fornecedor_email='', pdf_path='', cnpj='', data_pagamento='', valor_total=None, desconto_total=None, valor_pagar=None, itens_detalhados=None):
    base = _normalizar_base_url(ai_base_url)
    if not base:
        return None

    pdf_filename = ''
    pdf_b64 = ''
    try:
        caminho_pdf = str(pdf_path or '').strip()
        if caminho_pdf and os.path.exists(caminho_pdf):
            pdf_filename = os.path.basename(caminho_pdf)
            with open(caminho_pdf, 'rb') as f_pdf:
                pdf_b64 = base64.b64encode(f_pdf.read()).decode('ascii')
    except Exception:
        pdf_filename = ''
        pdf_b64 = ''

    endpoint = f"{base}/propostas"
    payload = {
        'numero_proposta': str(numero_proposta),
        'fornecedor': str(fornecedor),
        'valor': float(valor or 0),
        'data_proposta': str(data_proposta),
        'taxa_desconto': float(taxa_desconto) if taxa_desconto is not None else None,
        'fornecedor_email': str(fornecedor_email or '').strip() or None,
        'pdf_filename': pdf_filename or None,
        'pdf_b64': pdf_b64 or None,
        'cnpj': str(cnpj or '').strip() or None,
        'data_pagamento': str(data_pagamento or '').strip() or None,
        'valor_total': float(valor_total or 0) if valor_total is not None else None,
        'desconto_total': float(desconto_total or 0) if desconto_total is not None else None,
        'valor_pagar': float(valor_pagar or 0) if valor_pagar is not None else None,
        'itens_detalhados': itens_detalhados or None,
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


def _resolver_taxa_base_percentual(proposta):
    """Resolve taxa base (%) da proposta para regras de negociacao automatica."""
    taxa_raw = proposta.get('taxa_percentual', None)
    if taxa_raw is not None:
        try:
            valor = float(taxa_raw)
            if valor <= 1.0:
                return int(round(valor * 100.0))
            return int(round(valor))
        except Exception:
            pass

    taxa_display = str(proposta.get('taxa_display', '') or '').strip().replace('%', '').replace(',', '.')
    if taxa_display:
        try:
            return int(round(float(taxa_display)))
        except Exception:
            pass

    return 10


def _get_regras_negociacao(proposta):
    """Calcula ate duas contrapropostas reduzindo 1 p.p. por tentativa."""
    taxa_base_pct = max(1, min(_resolver_taxa_base_percentual(proposta), 100))
    taxa_primeira_pct = max(0, taxa_base_pct - 1)
    taxa_segunda_pct = max(0, taxa_base_pct - 2)
    return {
        'taxa_base_pct': taxa_base_pct,
        'taxa_primeira_pct': taxa_primeira_pct,
        'taxa_segunda_pct': taxa_segunda_pct,
    }


def _resolver_taxa_final_aceita_percentual(proposta):
    mensagem = str(proposta.get('mensagem', '') or '')
    match = re.search(r'(\d+(?:[\.,]\d+)?)\s*%', mensagem)
    if match:
        try:
            return float(match.group(1).replace(',', '.'))
        except Exception:
            pass

    taxa_percentual = proposta.get('taxa_percentual')
    if taxa_percentual is not None:
        try:
            valor = float(taxa_percentual)
            return valor * 100.0 if valor <= 1.0 else valor
        except Exception:
            pass

    taxa_display = str(proposta.get('taxa_display', '') or '').strip()
    match = re.search(r'(\d+(?:[\.,]\d+)?)\s*%', taxa_display)
    if match:
        try:
            return float(match.group(1).replace(',', '.'))
        except Exception:
            pass
    return None


def _montar_link_chat_negociacao(ai_chat_url, proposta, whatsapp_contato=''):
    link = str(ai_chat_url or '').strip()
    if not link:
        return ''

    regras = _get_regras_negociacao(proposta)
    parsed = urllib.parse.urlparse(link)
    query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)

    query.extend([
        ('origem', 'botao_negociar'),
        ('negociacao_ativa', '1'),
        ('negociacao_max_tentativas', '2'),
        ('taxa_original_pct', str(regras['taxa_base_pct'])),
        ('taxa_primeira_contraproposta_pct', str(regras['taxa_primeira_pct'])),
        ('taxa_segunda_contraproposta_pct', str(regras['taxa_segunda_pct'])),
        ('instrucao_limite', 'encaminhar_whatsapp'),
    ])
    if whatsapp_contato:
        query.append(('whatsapp_contato', whatsapp_contato))

    new_query = urllib.parse.urlencode(query)
    return urllib.parse.urlunparse((
        parsed.scheme,
        parsed.netloc,
        parsed.path,
        parsed.params,
        new_query,
        parsed.fragment,
    ))


def _validar_link_chat_ia(url):
    """Valida se o link de chat parece utilizavel (evita redirecionar para proposta inexistente)."""
    link = str(url or '').strip()
    if not link:
        return False

    def _normalizar_texto_erro(texto):
        bruto = str(texto or '')
        sem_acentos = unicodedata.normalize('NFKD', bruto)
        sem_acentos = ''.join(ch for ch in sem_acentos if not unicodedata.combining(ch))
        return sem_acentos.lower()

    def _indica_proposta_nao_encontrada(texto):
        t = _normalizar_texto_erro(texto)
        if 'proposta nao encontrada' in t:
            return True
        if '"detail"' in t and 'nao encontrada' in t:
            return True
        if 'nao encontrada' in t and 'proposta' in t:
            return True
        return False

    def _http_get(url_alvo):
        req = urllib.request.Request(
            url_alvo,
            headers={'User-Agent': 'Mozilla/5.0'},
            method='GET',
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            body = resp.read().decode('utf-8', errors='ignore')
            return resp.status, body

    parsed = urllib.parse.urlparse(link)
    q = urllib.parse.parse_qs(parsed.query)
    proposta_id = str((q.get('id', [''])[0]) or '').strip()
    token = str((q.get('token', [''])[0]) or '').strip()

    # Se o link possui id/token, valida direto no endpoint da proposta para evitar falso-positivo do frontend.
    if proposta_id:
        base = urllib.parse.urlunparse((parsed.scheme, parsed.netloc, '', '', '', '')).rstrip('/')
        endpoint = f"{base}/propostas/{proposta_id}"
        if token:
            endpoint = f"{endpoint}?{urllib.parse.urlencode({'token': token})}"
        try:
            status, body = _http_get(endpoint)
            if status >= 400:
                return False
            if _indica_proposta_nao_encontrada(body):
                return False
            return True
        except urllib.error.HTTPError as e:
            try:
                body = e.read().decode('utf-8', errors='ignore')
            except Exception:
                body = ''
            if _indica_proposta_nao_encontrada(body):
                return False
            return False
        except Exception:
            return False

    try:
        _, body = _http_get(link)
        if _indica_proposta_nao_encontrada(body):
            return False
        return True
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode('utf-8', errors='ignore')
        except Exception:
            body = ''
        if _indica_proposta_nao_encontrada(body):
            return False
        return False
    except Exception:
        return False


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
                family=config[0], size=config[1], weight=('bold' if config[2] == 'bold' else 'normal') if len(config) > 2 else 'normal'
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
# Utilitários
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
# DPAPI – criptografia Windows
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
# Configurações SMTP
# ==============================================
def load_email_config():
    if os.path.exists(EMAIL_CONFIG_FILE):
        try:
            with open(EMAIL_CONFIG_FILE, 'r', encoding='utf-8') as f:
                loaded = json.load(f)
                if isinstance(loaded, dict):
                    return loaded
        except Exception as e:
            print(f'Arquivo de configuracao SMTP invalido ({EMAIL_CONFIG_FILE}): {e}')
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
        'envio_aceitas_automatico_ativo': bool(config.get('envio_aceitas_automatico_ativo', True)),
        'envio_aceitas_automatico_hora': str(config.get('envio_aceitas_automatico_hora', '18:00') or '18:00').strip(),
        'ultima_data_envio_auto_aceitas': str(config.get('ultima_data_envio_auto_aceitas', '') or '').strip(),
    }

def save_envio_aceitas_pref(
    emails_aceitas_dia=None,
    salvar_emails_aceitas_automaticamente=None,
    envio_aceitas_automatico_ativo=None,
    envio_aceitas_automatico_hora=None,
    ultima_data_envio_auto_aceitas=None,
):
    config = load_email_config()
    if emails_aceitas_dia is not None:
        config['emails_aceitas_dia'] = str(emails_aceitas_dia)
    if salvar_emails_aceitas_automaticamente is not None:
        config['salvar_emails_aceitas_automaticamente'] = bool(salvar_emails_aceitas_automaticamente)
    if envio_aceitas_automatico_ativo is not None:
        config['envio_aceitas_automatico_ativo'] = bool(envio_aceitas_automatico_ativo)
    if envio_aceitas_automatico_hora is not None:
        config['envio_aceitas_automatico_hora'] = str(envio_aceitas_automatico_hora).strip() or '18:00'
    if ultima_data_envio_auto_aceitas is not None:
        config['ultima_data_envio_auto_aceitas'] = str(ultima_data_envio_auto_aceitas).strip()
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
# Configuração do Servidor de Respostas
# ==============================================
def load_server_config():
    """Carrega configuração do servidor.
    Se em produção (Railway), detecta automaticamente.
    """
    default_cfg = {
        'base_url': 'http://localhost:5001',
        'port': 5001,
        'ngrok_authtoken': '',
        'whatsapp_contato': str(os.getenv('ANTECIPACAO_WHATSAPP', '') or '').strip(),
    }

    # Detecta se está em Railway
    railway_url = os.getenv('RAILWAY_URL', '')
    if railway_url:
        cfg = {
            'base_url': railway_url,
            'port': int(os.getenv('PORT', 5000)),
            'ngrok_authtoken': str(os.getenv('NGROK_AUTHTOKEN', '') or ''),
            'whatsapp_contato': default_cfg['whatsapp_contato'],
        }
        return cfg
    
    # Tenta carregar arquivo local
    if os.path.exists(SERVER_CONFIG_FILE):
        try:
            with open(SERVER_CONFIG_FILE, 'r', encoding='utf-8') as f:
                loaded = json.load(f)
                if isinstance(loaded, dict):
                    merged = dict(default_cfg)
                    merged.update(loaded)

                    try:
                        merged['port'] = int(str(merged.get('port', default_cfg['port']) or default_cfg['port']).strip())
                    except Exception:
                        merged['port'] = default_cfg['port']

                    merged['base_url'] = _normalizar_base_url(
                        merged.get('base_url', default_cfg['base_url']) or default_cfg['base_url']
                    ) or default_cfg['base_url']
                    if 'ai_base_url' in merged:
                        merged['ai_base_url'] = _normalizar_base_url(merged.get('ai_base_url', ''))
                    merged['ngrok_authtoken'] = str(merged.get('ngrok_authtoken', '') or '').strip()
                    merged['whatsapp_contato'] = str(merged.get('whatsapp_contato', '') or '').strip()
                    return merged
        except Exception as e:
            print(f'Arquivo de configuracao do servidor invalido ({SERVER_CONFIG_FILE}): {e}')
    
    # Padrão para desenvolvimento local
    return default_cfg


def get_whatsapp_contato_negociacao(config=None):
    cfg = config if isinstance(config, dict) else load_server_config()
    contato_cfg = str(cfg.get('whatsapp_contato', '') or '').strip()
    contato_env = str(os.getenv('ANTECIPACAO_WHATSAPP', '') or '').strip()
    return contato_cfg or contato_env

def save_server_config(config):
    """Salva configuração do servidor (ignorado em produção)."""
    if os.getenv('RAILWAY_URL'):
        print("⚠️ Em produção (Railway) - configuração não será salva localmente.")
        return
    
    merged = load_server_config()
    merged.update(config or {})
    merged['base_url'] = _normalizar_base_url(merged.get('base_url', '')) or 'http://localhost:5001'
    if 'ai_base_url' in merged:
        merged['ai_base_url'] = _normalizar_base_url(merged.get('ai_base_url', ''))
    with open(SERVER_CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(merged, f, indent=4)

# ==============================================
# Emails de Fornecedores
# ==============================================
def load_email_map():
    if os.path.exists(FORNECEDOR_EMAILS_FILE):
        try:
            with open(FORNECEDOR_EMAILS_FILE, 'r', encoding='utf-8') as f:
                loaded = json.load(f)
                if isinstance(loaded, dict):
                    return loaded
        except Exception as e:
            print(f'Arquivo de emails de fornecedores invalido ({FORNECEDOR_EMAILS_FILE}): {e}')
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

    # 3) Busca por CNPJ (apenas dígitos)
    cnpj = normalizar_cnpj(chave)
    if cnpj:
        for k, v in m.items():
            k_cnpj = normalizar_cnpj(k)
            if k_cnpj and (k_cnpj == cnpj or k_cnpj.endswith(cnpj) or cnpj.endswith(k_cnpj)):
                return v

    # 4) Busca parcial: a chave está contida em alguma entrada ou vice-versa
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
    Colunas esperadas (flexíveis): Nome/Fornecedor, CNPJ, Email
    """
    try:
        df = pd.read_excel(caminho_excel)
        df.columns = [c.strip().lower() for c in df.columns]

        col_nome  = next((c for c in df.columns if 'nome' in c or 'fornecedor' in c or 'razao' in c or 'razão' in c), None)
        col_cnpj  = next((c for c in df.columns if 'cnpj' in c), None)
        col_email = next((c for c in df.columns if 'email' in c or 'e-mail' in c), None)

        if not col_email:
            return 0, "Coluna 'Email' não encontrada na planilha."

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
        try:
            with open(PROPOSTAS_FILE, 'r', encoding='utf-8') as f:
                loaded = json.load(f)
                if isinstance(loaded, dict):
                    return loaded
        except Exception as e:
            print(f'Arquivo de propostas invalido ({PROPOSTAS_FILE}): {e}')
    return {}

def save_propostas(propostas):
    try:
        os.makedirs(os.path.dirname(PROPOSTAS_FILE) or '.', exist_ok=True)
        with open(PROPOSTAS_FILE, 'w', encoding='utf-8') as f:
            json.dump(propostas, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"❌ Erro ao salvar propostas: {e}")
        raise


def load_movimentos_relatorios():
    if os.path.exists(MOVIMENTOS_RELATORIOS_FILE):
        try:
            with open(MOVIMENTOS_RELATORIOS_FILE, 'r', encoding='utf-8') as f:
                loaded = json.load(f)
                if isinstance(loaded, list):
                    return loaded
        except Exception as e:
            print(f'Arquivo de movimentos invalido ({MOVIMENTOS_RELATORIOS_FILE}): {e}')
    return []


def save_movimentos_relatorios(movimentos):
    os.makedirs(os.path.dirname(MOVIMENTOS_RELATORIOS_FILE) or '.', exist_ok=True)
    with open(MOVIMENTOS_RELATORIOS_FILE, 'w', encoding='utf-8') as f:
        json.dump(movimentos, f, indent=2, ensure_ascii=False)


def registrar_movimentos_relatorios(items):
    if not items:
        return 0

    existentes = load_movimentos_relatorios()
    chaves = {
        (
            str(m.get('token', '') or ''),
            str(m.get('fornecedor', '') or ''),
            str(m.get('loja', '') or ''),
            str(m.get('numero_doc', '') or ''),
            str(m.get('data_pagamento', '') or ''),
        )
        for m in existentes if isinstance(m, dict)
    }

    adicionados = 0
    for item in items:
        if not isinstance(item, dict):
            continue
        chave = (
            str(item.get('token', '') or ''),
            str(item.get('fornecedor', '') or ''),
            str(item.get('loja', '') or ''),
            str(item.get('numero_doc', '') or ''),
            str(item.get('data_pagamento', '') or ''),
        )
        if chave in chaves:
            continue
        chaves.add(chave)
        existentes.append(item)
        adicionados += 1

    if adicionados:
        save_movimentos_relatorios(existentes)
    return adicionados


def limpar_movimentos_sem_aceite_definitivo():
    propostas = load_propostas()
    tokens_aceitos = {str(t) for t, p in propostas.items() if p.get('status') == 'aceito'}
    movimentos = load_movimentos_relatorios()

    antes = len(movimentos)
    mantidos = []
    removidos_sem_token = 0
    removidos_nao_aceitos = 0

    for mov in movimentos:
        if not isinstance(mov, dict):
            continue
        token = str(mov.get('token', '') or '').strip()
        if not token:
            removidos_sem_token += 1
            continue
        if token not in tokens_aceitos:
            removidos_nao_aceitos += 1
            continue
        mantidos.append(mov)

    removidos_total = removidos_sem_token + removidos_nao_aceitos
    if removidos_total:
        save_movimentos_relatorios(mantidos)

    return {
        'movimentos_antes': int(antes),
        'movimentos_mantidos': int(len(mantidos)),
        'movimentos_removidos': int(removidos_total),
        'removidos_sem_token': int(removidos_sem_token),
        'removidos_token_nao_aceito': int(removidos_nao_aceitos),
    }


def _data_pagamento_para_mes(data_pagamento):
    txt = str(data_pagamento or '').strip()
    if not txt:
        return ''
    for fmt in ('%d/%m/%Y', '%d/%m/%Y %H:%M:%S', '%d/%m/%Y %H:%M'):
        try:
            return datetime.strptime(txt, fmt).strftime('%Y-%m')
        except Exception:
            pass
    return ''


def _rows_to_html_table(colunas, linhas):
    head = ''.join(f'<th>{html.escape(str(c))}</th>' for c in colunas)
    body_rows = []
    for row in linhas:
        tds = ''.join(f'<td>{html.escape(str(row.get(c, "")))}</td>' for c in colunas)
        body_rows.append(f'<tr>{tds}</tr>')
    body = '\n'.join(body_rows) if body_rows else f"<tr><td class='empty' colspan='{len(colunas)}'>Sem dados no período.</td></tr>"
    return (
        "<div class='table-wrap'><table class='report-table'>"
        f"<thead><tr>{head}</tr></thead>"
        f"<tbody>{body}</tbody>"
        "</table></div>"
    )


def _formatar_numero_documento_relatorio(valor):
    txt = str(valor or '').strip()
    if not txt:
        return ''
    if txt == '-':
        return txt

    # Normaliza casos vindos do Excel/Pandas como 397517.0 para inteiro.
    if re.fullmatch(r'\d+\.0+', txt):
        txt = txt.split('.', 1)[0]

    if txt.isdigit():
        return f"{int(txt):,}".replace(',', '.')
    return txt


def _moeda_br_para_float(valor):
    txt = str(valor or '').strip()
    if not txt:
        return 0.0
    txt = txt.replace('R$', '').replace(' ', '')
    txt = txt.replace('.', '').replace(',', '.')
    try:
        return float(txt)
    except Exception:
        return 0.0


def _totais_relatorio_mensal(colunas, linhas):
    col_total_fornecedor = 'total fornecedor' if 'total fornecedor' in colunas else ('valor R$' if 'valor R$' in colunas else '')
    col_total_desc = 'total de desc.' if 'total de desc.' in colunas else ('desc R$' if 'desc R$' in colunas else '')
    col_total_pagar = 'total a pagar' if 'total a pagar' in colunas else ('pagar R$' if 'pagar R$' in colunas else '')

    total_fornecedor = 0.0
    total_desc = 0.0
    total_pagar = 0.0
    for row in linhas:
        if col_total_fornecedor:
            total_fornecedor += _moeda_br_para_float(row.get(col_total_fornecedor, ''))
        if col_total_desc:
            total_desc += _moeda_br_para_float(row.get(col_total_desc, ''))
        if col_total_pagar:
            total_pagar += _moeda_br_para_float(row.get(col_total_pagar, ''))

    return total_fornecedor, total_desc, total_pagar


def _linha_total_relatorio_mensal(colunas, total_fornecedor, total_desc, total_pagar):
    linha = {c: '' for c in colunas}

    if 'data de pagamento' in linha:
        linha['data de pagamento'] = 'TOTAL GERAL'
    elif 'Lojas' in linha:
        linha['Lojas'] = 'TOTAL GERAL'
    elif 'fornecedor' in linha:
        linha['fornecedor'] = 'TOTAL GERAL'

    if 'loja' in linha and not linha.get('loja'):
        linha['loja'] = '-'
    if 'fornecedor' in linha and not linha.get('fornecedor'):
        linha['fornecedor'] = '-'
    if 'n doc' in linha:
        linha['n doc'] = '-'

    if 'total fornecedor' in linha:
        linha['total fornecedor'] = _fmt_moeda_br(total_fornecedor)
    if 'total de desc.' in linha:
        linha['total de desc.'] = _fmt_moeda_br(total_desc)
    if 'total a pagar' in linha:
        linha['total a pagar'] = _fmt_moeda_br(total_pagar)

    if 'valor R$' in linha:
        linha['valor R$'] = _fmt_moeda_br(total_fornecedor)
    if 'desc R$' in linha:
        linha['desc R$'] = _fmt_moeda_br(total_desc)
    if 'pagar R$' in linha:
        linha['pagar R$'] = _fmt_moeda_br(total_pagar)

    return linha


def _proximo_dia_util(base_dt):
    dt = base_dt + timedelta(days=1)
    while dt.weekday() >= 5:
        dt += timedelta(days=1)
    return dt


def gerar_relatorios_mensais_fechamento(output_dir=RELATORIOS_MENSAIS_DIR):
    propostas = load_propostas()
    movimentos = load_movimentos_relatorios()
    tokens_aceitos = {t for t, p in propostas.items() if p.get('status') == 'aceito'}

    meses = set()
    for p in propostas.values():
        if p.get('status') != 'aceito':
            continue
        m = _data_pagamento_para_mes(p.get('data_pagamento', ''))
        if m:
            meses.add(m)
    for m in movimentos:
        token_mov = str(m.get('token', '') or '')
        if token_mov not in tokens_aceitos:
            continue
        mes_mov = _data_pagamento_para_mes(m.get('data_pagamento', ''))
        if mes_mov:
            meses.add(mes_mov)

    if not meses:
        return {'meses': 0, 'arquivos': 0}

    arquivos = 0
    os.makedirs(output_dir, exist_ok=True)

    for mes in sorted(meses):
        pasta_mes = os.path.join(output_dir, mes)
        os.makedirs(pasta_mes, exist_ok=True)

        # Base de movimentos aceitos do mes para relatorios 2 e 3.
        movimentos_aceitos_mes = []
        for mov in movimentos:
            if _data_pagamento_para_mes(mov.get('data_pagamento', '')) != mes:
                continue
            token = str(mov.get('token', '') or '')
            prop = propostas.get(token, {}) if token else {}
            if not prop or prop.get('status') != 'aceito':
                continue
            movimentos_aceitos_mes.append(mov)

        stats_por_token = {}
        for mov in movimentos_aceitos_mes:
            token = str(mov.get('token', '') or '')
            acc = stats_por_token.setdefault(token, {'valor': 0.0, 'desc': 0.0})
            acc['valor'] += float(mov.get('valor_liquido', 0) or 0)
            acc['desc'] += float(mov.get('desconto', 0) or 0)

        def _valores_movimento_ajustados(mov):
            token = str(mov.get('token', '') or '')
            prop = propostas.get(token, {}) if token else {}
            valor = float(mov.get('valor_liquido', 0) or 0)
            desc = float(mov.get('desconto', 0) or 0)
            pagar = float(mov.get('valor_pagar', valor - desc) or (valor - desc))

            stats = stats_por_token.get(token, {})
            total_valor_mov = float(stats.get('valor', 0) or 0)
            total_desc_mov = float(stats.get('desc', 0) or 0)
            desc_prop = float(prop.get('desconto', 0) or 0)

            if total_desc_mov <= 0 and desc_prop > 0 and total_valor_mov > 0:
                fator = valor / total_valor_mov
                desc = desc_prop * fator
                pagar = valor - desc

            return valor, desc, pagar

        # Relatorio 1: fechamento mensal por fornecedor/data de pagamento
        fechamento = {}
        for p in propostas.values():
            if p.get('status') != 'aceito':
                continue
            if _data_pagamento_para_mes(p.get('data_pagamento', '')) != mes:
                continue
            chave = (str(p.get('data_pagamento', '') or ''), str(p.get('fornecedor', '') or ''))
            acc = fechamento.setdefault(chave, {
                'data de pagamento': chave[0],
                'fornecedor': chave[1],
                'total fornecedor': 0.0,
                'total de desc.': 0.0,
                'total a pagar': 0.0,
            })
            acc['total fornecedor'] += float(p.get('valor_total', 0) or 0)
            acc['total de desc.'] += float(p.get('desconto', 0) or 0)
            acc['total a pagar'] += float(p.get('valor_pagar', 0) or 0)

        rel1_rows = sorted(list(fechamento.values()), key=lambda r: (r['data de pagamento'], r['fornecedor']))
        for r in rel1_rows:
            r['total fornecedor'] = _fmt_moeda_br(r['total fornecedor'])
            r['total de desc.'] = _fmt_moeda_br(r['total de desc.'])
            r['total a pagar'] = _fmt_moeda_br(r['total a pagar'])

        # Relatorio 2: fechamento de desconto detalhado
        rel2_rows = []
        for mov in movimentos_aceitos_mes:
            valor_aj, desc_aj, pagar_aj = _valores_movimento_ajustados(mov)
            rel2_rows.append({
                'data de pagamento': str(mov.get('data_pagamento', '') or ''),
                'loja': str(mov.get('loja', '') or ''),
                'fornecedor': str(mov.get('fornecedor', '') or ''),
                'n doc': _formatar_numero_documento_relatorio(mov.get('numero_doc', '')),
                'valor R$': _fmt_moeda_br(valor_aj),
                'desc R$': _fmt_moeda_br(desc_aj),
                'pagar R$': _fmt_moeda_br(pagar_aj),
            })

        # Fallback: se nao houver base detalhada de movimentos, usa as propostas aceitas do mes.
        # Isso garante fechamento de desconto/contabil com visao consolidada minima.
        if not rel2_rows:
            for p in propostas.values():
                if p.get('status') != 'aceito':
                    continue
                if _data_pagamento_para_mes(p.get('data_pagamento', '')) != mes:
                    continue
                rel2_rows.append({
                    'data de pagamento': str(p.get('data_pagamento', '') or ''),
                    'loja': 'SEM_LOJA',
                    'fornecedor': str(p.get('fornecedor', '') or ''),
                    'n doc': '-',
                    'valor R$': _fmt_moeda_br(float(p.get('valor_total', 0) or 0)),
                    'desc R$': _fmt_moeda_br(float(p.get('desconto', 0) or 0)),
                    'pagar R$': _fmt_moeda_br(float(p.get('valor_pagar', 0) or 0)),
                })

        rel2_rows.sort(key=lambda r: (r['data de pagamento'], r['loja'], r['fornecedor'], r['n doc']))

        # Relatorio 3: resumo contabil (por loja)
        resumo = {}
        if movimentos_aceitos_mes:
            for mov in movimentos_aceitos_mes:
                valor_aj, desc_aj, pagar_aj = _valores_movimento_ajustados(mov)
                loja = str(mov.get('loja', '') or 'SEM LOJA')
                acc = resumo.setdefault(loja, {'Lojas': loja, 'valor R$': 0.0, 'desc R$': 0.0, 'pagar R$': 0.0})
                acc['valor R$'] += valor_aj
                acc['desc R$'] += desc_aj
                acc['pagar R$'] += pagar_aj
        else:
            for p in propostas.values():
                if p.get('status') != 'aceito':
                    continue
                if _data_pagamento_para_mes(p.get('data_pagamento', '')) != mes:
                    continue
                loja = 'SEM_LOJA'
                acc = resumo.setdefault(loja, {'Lojas': loja, 'valor R$': 0.0, 'desc R$': 0.0, 'pagar R$': 0.0})
                acc['valor R$'] += float(p.get('valor_total', 0) or 0)
                acc['desc R$'] += float(p.get('desconto', 0) or 0)
                acc['pagar R$'] += float(p.get('valor_pagar', 0) or 0)

        rel3_rows = sorted(list(resumo.values()), key=lambda r: r['Lojas'])
        for r in rel3_rows:
            r['valor R$'] = _fmt_moeda_br(r['valor R$'])
            r['desc R$'] = _fmt_moeda_br(r['desc R$'])
            r['pagar R$'] = _fmt_moeda_br(r['pagar R$'])

        relatorios = {
            'fechamento_mensal': {
                'colunas': ['data de pagamento', 'fornecedor', 'total fornecedor', 'total de desc.', 'total a pagar'],
                'linhas': rel1_rows,
            },
            'fechamento_desconto': {
                'colunas': ['data de pagamento', 'loja', 'fornecedor', 'n doc', 'valor R$', 'desc R$', 'pagar R$'],
                'linhas': rel2_rows,
            },
            'antecipacao_pagamento_contabil': {
                'colunas': ['Lojas', 'valor R$', 'desc R$', 'pagar R$'],
                'linhas': rel3_rows,
            },
        }

        for nome, payload in relatorios.items():
            csv_path = os.path.join(pasta_mes, f'{nome}_{mes.replace("-", "_")}.csv')
            html_path = os.path.join(pasta_mes, f'{nome}_{mes.replace("-", "_")}.html')
            stamp = datetime.now().strftime('%H%M%S')

            total_fornecedor, total_desc, total_pagar = _totais_relatorio_mensal(payload['colunas'], payload['linhas'])
            linha_total = _linha_total_relatorio_mensal(payload['colunas'], total_fornecedor, total_desc, total_pagar)
            linhas_export = list(payload['linhas']) + [linha_total]

            csv_target = csv_path
            try:
                with open(csv_target, 'w', encoding='utf-8-sig', newline='') as f_csv:
                    writer = csv.DictWriter(
                        f_csv,
                        fieldnames=payload['colunas'],
                        delimiter=';',
                        quoting=csv.QUOTE_MINIMAL,
                    )
                    writer.writeheader()
                    for row in linhas_export:
                        writer.writerow({col: row.get(col, '') for col in payload['colunas']})
            except PermissionError:
                csv_target = os.path.join(pasta_mes, f'{nome}_{mes.replace("-", "_")}_{stamp}.csv')
                with open(csv_target, 'w', encoding='utf-8-sig', newline='') as f_csv:
                    writer = csv.DictWriter(
                        f_csv,
                        fieldnames=payload['colunas'],
                        delimiter=';',
                        quoting=csv.QUOTE_MINIMAL,
                    )
                    writer.writeheader()
                    for row in linhas_export:
                        writer.writerow({col: row.get(col, '') for col in payload['colunas']})

            html_body = (
                "<!DOCTYPE html><html lang='pt-BR'><head><meta charset='UTF-8'>"
                "<meta name='viewport' content='width=device-width, initial-scale=1'>"
                f"<title>{nome} {mes}</title>"
                "<style>"
                ":root{--bg:#f5f7fb;--card:#ffffff;--ink:#1e2a3a;--muted:#5d6b7a;--line:#dfe6ef;--head:#e9f1fb;--accent:#1f6fb2;}"
                "*{box-sizing:border-box}"
                "body{margin:0;font-family:'Segoe UI',Tahoma,Arial,sans-serif;color:var(--ink);"
                "background:radial-gradient(circle at 0 0,#e7f0fb 0,#f7f9fc 45%,#f2f5fa 100%);}"
                ".shell{max-width:1200px;margin:28px auto;padding:0 16px}"
                ".card{background:var(--card);border:1px solid var(--line);border-radius:14px;"
                "box-shadow:0 8px 24px rgba(24,39,75,.08);overflow:hidden}"
                ".header{padding:18px 20px;border-bottom:1px solid var(--line)}"
                ".title{margin:0;font-size:22px;font-weight:700;letter-spacing:.2px}"
                ".meta{margin-top:6px;color:var(--muted);font-size:13px}"
                ".totals{display:grid;grid-template-columns:repeat(3,minmax(180px,1fr));gap:10px;padding:12px 20px;border-bottom:1px solid var(--line)}"
                ".total-card{background:#f7fbff;border:1px solid #d7e7f8;border-radius:10px;padding:10px 12px}"
                ".total-label{font-size:12px;color:var(--muted);margin-bottom:4px}"
                ".total-value{font-size:19px;font-weight:700;color:#1c4f7a}"
                ".table-wrap{overflow:auto;padding:8px 12px 14px}"
                ".report-table{width:100%;border-collapse:separate;border-spacing:0;min-width:760px;font-size:13px}"
                ".report-table thead th{position:sticky;top:0;background:var(--head);color:var(--ink);"
                "text-align:left;padding:10px 12px;font-weight:700;border-bottom:1px solid var(--line)}"
                ".report-table tbody td{padding:9px 12px;border-bottom:1px solid #edf2f7}"
                ".report-table tbody tr:nth-child(even){background:#fbfdff}"
                ".report-table tbody tr:hover{background:#f1f7ff}"
                ".empty{text-align:center;color:var(--muted);padding:20px 12px !important}"
                "@media (max-width:720px){.title{font-size:18px}.shell{margin:16px auto}.totals{grid-template-columns:1fr}}"
                "</style></head><body><main class='shell'><section class='card'>"
                "<header class='header'>"
                f"<h2 class='title'>{nome.replace('_', ' ').title()}</h2>"
                f"<div class='meta'>Competência: {mes}</div>"
                "</header>"
                "<section class='totals'>"
                f"<article class='total-card'><div class='total-label'>Valor total do fornecedor</div><div class='total-value'>{_fmt_moeda_br(total_fornecedor)}</div></article>"
                f"<article class='total-card'><div class='total-label'>Total de desc.</div><div class='total-value'>{_fmt_moeda_br(total_desc)}</div></article>"
                f"<article class='total-card'><div class='total-label'>Total a pagar</div><div class='total-value'>{_fmt_moeda_br(total_pagar)}</div></article>"
                "</section>"
                + _rows_to_html_table(payload['colunas'], linhas_export)
                + "</section></main></body></html>"
            )
            html_target = html_path
            try:
                with open(html_target, 'w', encoding='utf-8') as f_html:
                    f_html.write(html_body)
            except PermissionError:
                html_target = os.path.join(pasta_mes, f'{nome}_{mes.replace("-", "_")}_{stamp}.html')
                with open(html_target, 'w', encoding='utf-8') as f_html:
                    f_html.write(html_body)

            arquivos += 2

    return {'meses': len(meses), 'arquivos': arquivos}


def _normalizar_fornecedor_relatorio(valor):
    return re.sub(r'\s+', ' ', str(valor or '').strip().upper())


def backfill_movimentos_por_excel(caminho_excel, data_pagamento_str, taxa_fixa_str=''):
    motor = AntecipacaoPagamentos()
    df = motor.processar_arquivo(caminho_excel, data_pagamento_str, taxa_fixa_str)
    if df.empty:
        return {'linhas_excel': 0, 'movimentos_adicionados': 0, 'linhas_vinculadas': 0}

    propostas = load_propostas()
    aceitas_por_chave = {}
    for token, p in propostas.items():
        if p.get('status') != 'aceito':
            continue
        if str(p.get('data_pagamento', '') or '').strip() != str(data_pagamento_str or '').strip():
            continue
        chave = (
            _normalizar_fornecedor_relatorio(p.get('fornecedor', '')),
            normalizar_cnpj(p.get('cnpj', '')),
        )
        aceitas_por_chave.setdefault(chave, []).append(token)

    itens = []
    vinculadas = 0
    ignoradas_sem_aceite = 0
    for _, row in df.iterrows():
        fornecedor = str(row.get('Fornecedor', '') or '')
        cnpj = normalizar_cnpj(row.get('CNPJ', ''))
        chave = (_normalizar_fornecedor_relatorio(fornecedor), cnpj)
        token = ''
        if chave in aceitas_por_chave and aceitas_por_chave[chave]:
            token = aceitas_por_chave[chave][0]
            vinculadas += 1
        else:
            ignoradas_sem_aceite += 1
            continue

        numero_doc = row.get(motor.col_numero_doc, '') if motor.col_numero_doc in df.columns else ''
        itens.append({
            'token': token,
            'fornecedor': fornecedor,
            'cnpj': cnpj,
            'data_pagamento': str(data_pagamento_str or ''),
            'loja': str(row.get('Loja', '') or ''),
            'numero_doc': str(numero_doc or ''),
            'valor_liquido': float(motor._sf(row.get(motor.col_valor_liquido, 0))),
            'desconto': float(motor._sf(row.get(motor.col_desconto_antecipacao, 0))),
            'valor_pagar': float(motor._sf(row.get('Valor a pagar', 0))),
            'data_registro': datetime.now().strftime('%d/%m/%Y %H:%M:%S'),
        })

    adicionados = registrar_movimentos_relatorios(itens)
    return {
        'linhas_excel': int(len(df)),
        'movimentos_adicionados': int(adicionados),
        'linhas_vinculadas': int(vinculadas),
        'linhas_ignoradas_sem_aceite': int(ignoradas_sem_aceite),
    }

def _fazer_backup_mensal(mes_ref):
    """Salva copia das propostas do mes_ref (YYYY-MM) em Backups_Mensais/propostas_backup_YYYY_MM.json."""
    propostas = load_propostas()
    propostas_mes = {
        token: p for token, p in propostas.items()
        if _mes_ref(_parse_datetime_br(p.get('data_envio', ''))) == mes_ref
    }
    if not propostas_mes:
        return False
    os.makedirs(BACKUPS_MENSAIS_DIR, exist_ok=True)
    nome = 'propostas_backup_' + mes_ref.replace('-', '_') + '.json'
    backup_file = os.path.join(BACKUPS_MENSAIS_DIR, nome)
    with open(backup_file, 'w', encoding='utf-8') as f:
        json.dump(propostas_mes, f, indent=4, ensure_ascii=False)
    return True


def _auto_backup_meses_anteriores():
    """Cria automaticamente backups mensais para todos os meses anteriores sem backup."""
    try:
        propostas = load_propostas()
        mes_atual = datetime.now().strftime('%Y-%m')
        meses = set()
        for p in propostas.values():
            dt = _parse_datetime_br(p.get('data_envio', ''))
            if dt:
                mref = _mes_ref(dt)
                if mref and mref != mes_atual:
                    meses.add(mref)
        for mref in meses:
            nome = 'propostas_backup_' + mref.replace('-', '_') + '.json'
            backup_file = os.path.join(BACKUPS_MENSAIS_DIR, nome)
            if not os.path.exists(backup_file):
                _fazer_backup_mensal(mref)
    except Exception as e:
        print(f'Erro no backup automatico: {e}')


def registrar_proposta(token, fornecedor, cnpj, email, valor_total, desconto, valor_pagar, pdf_path, data_pagamento,
                       assunto='', ai_chat_url='', ai_id_proposta=None, ai_token='',
                       taxa_percentual=None, taxa_display='', ai_base_url='', itens_detalhados=None):
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
        'taxa_percentual': float(taxa_percentual) if taxa_percentual is not None else None,
        'taxa_display': str(taxa_display or ''),
        'ai_base_url': str(ai_base_url or '').strip(),
        'itens_detalhados': itens_detalhados or [],
        'email_enviado': False,
        'erro_envio_email': 'pendente_envio',
        'data_envio_email': None,
    }
    save_propostas(propostas)


def _atualizar_metadados_envio_proposta(token, email_enviado=None, erro_envio_email=None):
    try:
        propostas = load_propostas()
        if token not in propostas:
            return
        proposta = propostas[token]

        if email_enviado is not None:
            proposta['email_enviado'] = bool(email_enviado)
            if email_enviado:
                proposta['data_envio_email'] = datetime.now().strftime('%d/%m/%Y %H:%M:%S')

        if erro_envio_email is not None:
            proposta['erro_envio_email'] = str(erro_envio_email)

        propostas[token] = proposta
        save_propostas(propostas)
    except Exception as e:
        print(f'Falha ao atualizar metadados de envio da proposta {token}: {e}')


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


def _inferir_origem_resposta(mensagem_texto):
    texto = str(mensagem_texto or '').strip().lower()
    if not texto:
        return '-'
    if texto in ('aceito', 'nao aceito', 'não aceito', 'recuso', 'quero negociar'):
        return 'Email'
    return 'Chat'


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

            origem_resp = _inferir_origem_resposta(msg_resp)
            if proposta.get('origem_resposta', '') != origem_resp:
                proposta['origem_resposta'] = origem_resp
                mudou = True

            if mudou:
                alteradas += 1
                if status_atual != 'aceito' and novo_status == 'aceito':
                    _copiar_para_aceitas(proposta)

        if alteradas:
            save_propostas(propostas)
        return alteradas
    except Exception as e:
        print   (f'Erro ao sincronizar respostas IA: {e}')
        return 0

def _enviar_notificacao_resposta(proposta, status):
    """Envia email de notificacao ao remetente SMTP quando o fornecedor responde."""
    try:
        ss, sp, su, spw = get_smtp_credentials()
        if not all([ss, sp, su, spw]):
            return
        ss, sp, su, spw = str(ss), str(sp), str(su), str(spw)

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

        _m = re.search(r'(\d+)', str(sp))
        p = int(_m.group(1)) if _m else 587
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
            propostas[token]['origem_resposta'] = 'Email'
            
            # Salva ANTES de tentar outras operações
            save_propostas(propostas)
            print(f"✅ Proposta {token} atualizada para status '{status}'")

            # O envio de email ao remetente e feito na rota de resposta (/resposta/<token>/<acao>)
            # para manter o assunto com prefixo (Aceito / Quero Negociar / Nao Aceito)
            # e evitar notificacao duplicada.

            # Copia para pasta de aceitas se foi aceita
            if status == 'aceito':
                _copiar_para_aceitas(propostas[token])
        else:
            print(f"⚠️ Token {token} não encontrado nas propostas")
    except Exception as e:
        print(f"❌ Erro ao atualizar status da proposta: {e}")
        traceback.print_exc()

def _copiar_para_aceitas(proposta):
    try:
        os.makedirs(PROPOSTAS_ACEITAS_DIR, exist_ok=True)
        pdf_src = proposta.get('pdf_path', '')
        if pdf_src and os.path.exists(pdf_src):
            nome = os.path.basename(pdf_src)
            dst = os.path.join(PROPOSTAS_ACEITAS_DIR, nome)
            shutil.copy2(pdf_src, dst)
            print(f"✅ PDF copiado para aceitas: {dst}")
            _gerar_relatorio_aceite(proposta, dst)
        else:
            print(f"⚠️ PDF não encontrado: {pdf_src}")
    except Exception as e:
        print(f"❌ Erro ao copiar para Propostas Aceitas: {e}")
        traceback.print_exc()

def _gerar_relatorio_aceite(proposta, pdf_original):
    """Gera um relatório resumido de aceite para o financeiro."""
    if FPDF is None:
        print(f"⚠️ Relatório de aceite não gerado: biblioteca PDF indisponível ({_FPDF_IMPORT_ERROR})")
        return

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
        print(f"✅ Relatório de aceite gerado: {caminho_saida}")
    except Exception as e:
        print(f"❌ Erro ao gerar relatório de aceite: {e}")
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
        ss, sp, su, spw = str(ss), str(sp), str(su), str(spw)

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
        _m = re.search(r'(\d+)', str(sp))
        p = int(_m.group(1)) if _m else 587
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


def _enviar_email_refazer_proposta(proposta, regras_negociacao, whatsapp_contato=''):
    """Notifica o remetente SMTP para refazer e reenviar proposta apos negociar."""
    try:
        ss, sp, su, spw = get_smtp_credentials()
        if not all([ss, sp, su, spw]):
            return False

        fornecedor = proposta.get('fornecedor', '')
        cnpj = proposta.get('cnpj', '')
        assunto = f"[Refazer Proposta] {fornecedor} ({cnpj})"
        texto_whats = f"WhatsApp para contato: {whatsapp_contato}" if whatsapp_contato else 'WhatsApp para contato: (nao informado)'

        corpo = (
            "Solicitacao de negociacao recebida.\n\n"
            "Favor refazer a proposta e encaminhar ao fornecedor, conforme regra automatica:\n"
            f"- Taxa original: {regras_negociacao['taxa_base_pct']}%\n"
            f"- 1a contraproposta: {regras_negociacao['taxa_primeira_pct']}%\n"
            f"- 2a contraproposta (maximo): {regras_negociacao['taxa_segunda_pct']}%\n"
            "- Se ainda recusar e quiser negociar: orientar contato via WhatsApp.\n\n"
            f"Fornecedor: {fornecedor}\n"
            f"CNPJ: {cnpj}\n"
            f"Email fornecedor: {proposta.get('email', '')}\n"
            f"Data pagamento: {proposta.get('data_pagamento', '')}\n"
            f"{texto_whats}\n"
        )

        msg = MIMEMultipart('alternative')
        msg['From'] = str(su)
        msg['To'] = str(su)
        msg['Subject'] = assunto
        msg.attach(MIMEText(corpo, 'plain', 'utf-8'))

        _m = re.search(r'(\d+)', str(sp))
        p = int(_m.group(1)) if _m else 587
        with smtplib.SMTP(str(ss), p) as server:
            server.starttls()
            server.login(str(su), str(spw))
            server.send_message(msg)
        return True
    except Exception as e:
        print(f'Erro ao enviar email de refazer proposta: {e}')
        traceback.print_exc()
        return False

def criar_flask_app():
    app = Flask(__name__)

    @app.route('/resposta-email/<token>/<acao>')
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
            whatsapp_contato = get_whatsapp_contato_negociacao()
            regras_negociacao = _get_regras_negociacao(p)

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
                corpo_msg = (
                    "Prezados,\n\n"
                    "Gostariamos de NEGOCIAR as condicoes da proposta abaixo:\n\n"
                    f"{corpo_base}"
                    "Regra de negociacao automatica solicitada:\n"
                    f"- Taxa original: {regras_negociacao['taxa_base_pct']}%\n"
                    f"- 1a contraproposta: {regras_negociacao['taxa_primeira_pct']}%\n"
                    f"- 2a contraproposta (maximo): {regras_negociacao['taxa_segunda_pct']}%\n"
                    "- Se persistir apos o maximo, orientar contato via WhatsApp.\n\n"
                    f"Atenciosamente,\n{fornecedor}"
                )
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

            if acao == 'negociar':
                _enviar_email_refazer_proposta(p, regras_negociacao, whatsapp_contato)

                # Regera o link do chat no clique de negociar para evitar link expirado/invalido.
                cfg = load_server_config()
                ai_base_url = str(
                    p.get('ai_base_url', '')
                    or cfg.get('ai_base_url', '')
                    or os.getenv('FORNECEDOR_AI_BASE_URL', '')
                ).strip()
                # Fallback: se ai_base_url nao estiver preenchida, usa base_url publica configurada.
                if not ai_base_url:
                    base_publica = str(cfg.get('base_url', '') or '').strip()
                    if base_publica and not _is_local_base_url(base_publica):
                        ai_base_url = base_publica
                if ai_base_url:
                    cnpj_norm = normalizar_cnpj(p.get('cnpj', '')) or 'SEM_CNPJ'
                    numero_proposta = f"{cnpj_norm}-{token[:8]}-{datetime.now().strftime('%Y%m%d%H%M%S')}"
                    novo_ai_chat_url = _criar_link_resposta_ia(
                        ai_base_url,
                        numero_proposta,
                        fornecedor,
                        float(p.get('valor_pagar', 0) or 0),
                        str(p.get('data_pagamento', '') or datetime.now().strftime('%d/%m/%Y')),
                        regras_negociacao['taxa_base_pct'],
                        fornecedor_email,
                        str(p.get('pdf_path', '') or ''),
                        cnpj=cnpj_norm,
                        data_pagamento=str(p.get('data_pagamento', '') or ''),
                        valor_total=float(p.get('valor_total', 0) or 0),
                        desconto_total=float(p.get('desconto', 0) or 0),
                        valor_pagar=float(p.get('valor_pagar', 0) or 0),
                        itens_detalhados=p.get('itens_detalhados') or [],
                    )
                    if novo_ai_chat_url:
                        p['ai_chat_url'] = novo_ai_chat_url
                        ai_id_proposta, ai_token = _parse_ai_link_data(novo_ai_chat_url)
                        p['ai_id_proposta'] = ai_id_proposta
                        p['ai_token'] = ai_token
                        p['ai_base_url'] = ai_base_url
                        propostas[token] = p
                        save_propostas(propostas)

            html = HTML_RESPOSTA.format(
                icon=icon, titulo=titulo,
                mensagem=msg_html,
                classe=classe, badge=badge,
                assunto=assunto_resposta,
                status_bg=status_bg, status_color=status_color, status_text=status_text,
                data=datetime.now().strftime('%d/%m/%Y %H:%M')
            )

            if acao == 'negociar':
                chat_url = _montar_link_chat_negociacao(p.get('ai_chat_url', ''), p, whatsapp_contato)
                if chat_url and _validar_link_chat_ia(chat_url):
                    html = corrigir_texto_exibicao(f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta http-equiv="refresh" content="2;url={chat_url}">
    <title>Negociacao</title>
</head>
<body style="font-family:Arial,sans-serif;background:#f0f2f5;padding:32px;">
    <div style="max-width:620px;margin:0 auto;background:#fff;border-radius:12px;padding:24px;box-shadow:0 4px 16px rgba(0,0,0,.12);text-align:center;">
        <h2 style="margin:0 0 12px;color:#1e3a5f;">Solicitacao de negociacao registrada</h2>
        <p style="color:#4a5568;line-height:1.6;">Voce sera redirecionado para o chat da proposta em instantes.</p>
        <p style="color:#4a5568;line-height:1.6;">Se o redirecionamento nao acontecer, use o botao abaixo.</p>
        <a href="{chat_url}" style="display:inline-block;background:#f6a623;color:#fff;padding:12px 18px;border-radius:8px;font-weight:bold;text-decoration:none;">Abrir Chat da Proposta</a>
    </div>
</body>
</html>""")
                elif chat_url:
                    html = corrigir_texto_exibicao(f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <title>Negociacao Registrada</title>
</head>
<body style="font-family:Arial,sans-serif;background:#f0f2f5;padding:32px;">
    <div style="max-width:620px;margin:0 auto;background:#fff;border-radius:12px;padding:24px;box-shadow:0 4px 16px rgba(0,0,0,.12);text-align:center;">
        <h2 style="margin:0 0 12px;color:#1e3a5f;">Solicitacao de negociacao registrada</h2>
        <p style="color:#4a5568;line-height:1.6;">Nao foi possivel validar o chat automaticamente agora.</p>
        <p style="color:#4a5568;line-height:1.6;">Voce pode abrir manualmente pelo botao abaixo.</p>
        <a href="{chat_url}" style="display:inline-block;background:#f6a623;color:#fff;padding:12px 18px;border-radius:8px;font-weight:bold;text-decoration:none;">Abrir Chat da Proposta</a>
    </div>
</body>
</html>""")
                else:
                    html = corrigir_texto_exibicao("""<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <title>Negociacao Registrada</title>
</head>
<body style="font-family:Arial,sans-serif;background:#f0f2f5;padding:32px;">
    <div style="max-width:620px;margin:0 auto;background:#fff;border-radius:12px;padding:24px;box-shadow:0 4px 16px rgba(0,0,0,.12);text-align:center;">
        <h2 style="margin:0 0 12px;color:#1e3a5f;">Solicitacao de negociacao registrada</h2>
        <p style="color:#4a5568;line-height:1.6;">Nao foi possivel abrir o chat automaticamente agora.</p>
        <p style="color:#4a5568;line-height:1.6;">Sua solicitacao foi registrada e nossa equipe fara o contato.</p>
    </div>
</body>
</html>""")

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
    
    Em Railway, detecta porta automaticamente via variável PORT.
    Em desenvolvimento, usa porta padrão 5001.
    """
    global _flask_app, _flask_thread, _flask_running
    if not FLASK_AVAILABLE:
        print("⚠️ Flask não instalado. Servidor de respostas desativado.")
        return False
    if _flask_running:
        return True
    
    try:
        # Detecta porta: Railway > argumento > padrão
        if port is None:
            port = int(os.getenv('PORT', 5001))
        
        is_production = bool(os.getenv('RAILWAY_URL'))
        env_label = "PRODUÇÃO (Railway)" if is_production else "DESENVOLVIMENTO"
        
        _flask_app = criar_flask_app()
        if _flask_app is None:
            return False

        _app_ref = _flask_app

        def run():
            import logging
            log = logging.getLogger('werkzeug')
            log.setLevel(logging.ERROR)
            _app_ref.run(host='0.0.0.0', port=port, use_reloader=False, threaded=True)

        _flask_thread = threading.Thread(target=run, daemon=True)
        _flask_thread.start()
        _flask_running = True
        
        cfg = load_server_config()
        base_url = cfg.get('base_url', 'http://localhost:5001')
        
        print(f"✅ Servidor de respostas iniciado ({env_label})")
        print(f"   Porta: {port}")
        print(f"   URL Base: {base_url}")
        return True
    except Exception as e:
        print(f"❌ Erro ao iniciar servidor: {e}")
        traceback.print_exc()
        return False

# ==============================================
# Template de Email HTML com Botões
# ==============================================
def get_email_html(fornecedor, cnpj, data_base, data_pagamento, taxa_display,
                   total_valor, total_desconto, total_pagar, base_url, token, ai_chat_url=''):
    def fmt(v):
        return f"R$ {v:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')

    # Fallback sem dependencia do link web: resposta por email em 1 clique.
    _, _, smtp_user, _ = get_smtp_credentials()
    destinatario_fallback = str(smtp_user or 'jonas@mercadaoatacadista.com.br').strip()

    def _mailto_resposta(acao_label):
        subject = urllib.parse.quote(f"Resposta proposta {token[:8]} - {acao_label}")
        body = urllib.parse.quote(
            "Solicito registrar minha resposta para a proposta.\n"
            f"Token: {token}\n"
            f"Acao: {acao_label}\n"
            f"Fornecedor: {fornecedor}\n"
            f"CNPJ: {cnpj}\n"
        )
        return f"mailto:{destinatario_fallback}?subject={subject}&body={body}"

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
    url_mail_aceito = _mailto_resposta('ACEITO')
    url_mail_negociar = _mailto_resposta('NEGOCIAR')
    url_mail_recusar = _mailto_resposta('RECUSAR')

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
                        Ao clicar em "Quero Negociar", o chat da proposta sera aberto automaticamente apos o registro da resposta.
                    </p>

                    <div style="margin-top:16px; background:#fff8e1; border:1px solid #f6a623; border-radius:8px; padding:12px; text-align:left;">
                        <p style="margin:0 0 8px; color:#7a4b00; font-size:12px; font-weight:bold;">
                            Se o link web nao abrir, use os atalhos por e-mail:
                        </p>
                        <p style="margin:0; font-size:12px; line-height:1.7;">
                            <a href="{url_mail_aceito}" style="color:#276749; text-decoration:underline;">Responder ACEITO por e-mail</a><br>
                            <a href="{url_mail_negociar}" style="color:#8a6d3b; text-decoration:underline;">Responder NEGOCIAR por e-mail</a><br>
                            <a href="{url_mail_recusar}" style="color:#9b1c1c; text-decoration:underline;">Responder RECUSAR por e-mail</a>
                        </p>
                    </div>
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

    _, _, smtp_user, _ = get_smtp_credentials()
    destinatario_fallback = str(smtp_user or 'jonas@mercadaoatacadista.com.br').strip()

    def _mailto_resposta(acao_label):
        subject = urllib.parse.quote(f"Resposta proposta {token[:8]} - {acao_label}")
        body = urllib.parse.quote(
            "Solicito registrar minha resposta para a proposta.\n"
            f"Token: {token}\n"
            f"Acao: {acao_label}\n"
            f"Fornecedor: {fornecedor}\n"
            f"CNPJ: {cnpj}\n"
        )
        return f"mailto:{destinatario_fallback}?subject={subject}&body={body}"
    is_ngrok_link = 'ngrok-free.dev' in str(base_url or '').lower() or 'ngrok.io' in str(base_url or '').lower()
    aviso_ngrok = ''
    if is_ngrok_link:
        aviso_ngrok = (
            '\nATENCAO: se abrir uma tela de seguranca do ngrok, clique em "Visite o site" para continuar.\n'
        )
    bloco_resposta = (
        'RESPONDA CLICANDO EM UM DOS LINKS ABAIXO:\n\n'
        'ACEITO:\n'
        f'{base_url}/resposta/{token}/aceito\n\n'
        'QUERO NEGOCIAR:\n'
        f'{base_url}/resposta/{token}/negociar\n\n'
        'NAO ACEITO:\n'
        f'{base_url}/resposta/{token}/recusar\n\n'
        'Obs.: ao clicar em QUERO NEGOCIAR, o chat da proposta sera aberto automaticamente apos o registro.\n'
    )

    bloco_fallback_email = (
        'SE O LINK WEB NAO ABRIR, USE O FALLBACK POR E-MAIL:\n\n'
        'ACEITO (email):\n'
        f'{_mailto_resposta("ACEITO")}\n\n'
        'NEGOCIAR (email):\n'
        f'{_mailto_resposta("NEGOCIAR")}\n\n'
        'RECUSAR (email):\n'
        f'{_mailto_resposta("RECUSAR")}\n\n'
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
{bloco_fallback_email}
------------------------------------------------------------

MERCADAO ATACADISTA - MESA DE ANTECIPACAO
jonas@mercadaoatacadista.com.br | (11) 3791-1130 Ramal 2016
""")


def get_email_html_proposta_atualizada(fornecedor, cnpj, data_base, data_pagamento, taxa_display,
                                                                             total_valor, total_desconto, total_pagar):
        def fmt(v):
                return f"R$ {v:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')

        return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Proposta Atualizada – Mercadão Atacadista</title>
    <style>
        body {{margin:0; padding:0; font-family:'Segoe UI', Arial, sans-serif; background:#f0f2f5;}}
        table {{border-collapse:collapse;}}
    </style>
</head>
<body>
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f0f2f5; padding:32px 0;">
    <tr><td align="center">
        <table width="620" cellpadding="0" cellspacing="0" style="background:#ffffff; border-radius:12px; overflow:hidden; box-shadow:0 4px 16px rgba(0,0,0,0.12);">
            <tr><td style="background:#1e3a5f; padding:32px; text-align:center;">
                <h1 style="color:#ffffff; margin:0; font-size:24px; font-weight:bold;">MERCADÃO ATACADISTA</h1>
                <p style="color:#a0c4e4; margin:6px 0 0; font-size:14px;">Mesa de Antecipação de Pagamentos</p>
            </td></tr>
            <tr><td style="padding:32px 40px;">
                <p style="color:#2d3748; font-size:15px; margin:0 0 6px; line-height:1.4;">
                    <strong>Prezado(a)</strong> {fornecedor},
                </p>
                <p style="color:#2d3748; font-size:14px; margin:0 0 24px; line-height:1.5;">
                    Conforme o aceite da proposta pelo chat, segue em anexo a <strong>proposta atualizada</strong>
                    referente ao CNPJ <strong>{cnpj}</strong>.
                </p>
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
                <p style="color:#718096; font-size:13px; text-align:center; margin:0;">
                    A proposta atualizada completa está em anexo a este email.
                </p>
            </td></tr>
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


def get_email_plaintext_proposta_atualizada(fornecedor, cnpj, data_base, data_pagamento, taxa_display,
                                                                                        total_valor, total_desconto, total_pagar):
        def fmt(v):
                return f"R$ {v:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')

        return corrigir_texto_exibicao(f"""
Prezado(a) {fornecedor},

Conforme o aceite da proposta pelo chat, segue em anexo a proposta atualizada referente ao CNPJ {cnpj}.

Data Base: {data_base}
Data de Pagamento: {data_pagamento}
Taxa Aplicada: {taxa_display}

Valor Liquido Total:      {fmt(total_valor)}
Desconto de Antecipacao:  {fmt(total_desconto)}
Valor a Receber:          {fmt(total_pagar)}

A proposta atualizada completa esta em anexo a este email.

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

        # BCC: destinatários ocultos (não aparecem no cabeçalho)
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
                print(f"  (cópia BCC enviada para: {', '.join(bcc_emails)})")
            return True
        except smtplib.SMTPAuthenticationError:
            print(f"Erro de autenticação para {to_email}")
            return False
        except Exception as e:
            print(f"Erro ao enviar para {to_email}: {e}")
            traceback.print_exc()
            return False

# ==============================================
# Geração de PDF
# ==============================================
_UNICODE_REPLACE = {
    '\u2013': '-',   # en dash â€“
    '\u2014': '-',   # em dash â€”
    '\u2018': "'",   # ' aspa esquerda
    '\u2019': "'",   # ' aspa direita
    '\u201c': '"',   # " aspas duplas esquerda
    '\u201d': '"',   # " aspas duplas direita
    '\u2026': '...', # reticências
    '\u00b0': 'o',  # Â° grau
    '\u2022': '-',   # â€¢ bullet
    '\u20ac': 'EUR', # â‚¬ euro
    '\u00a0': ' ',   # espaço não quebrável
}

def _safe_pdf_text(text):
    """Remove/substitui caracteres fora do Latin-1 para compatibilidade com FPDF."""
    if not text:
        return ''
    text = str(text)
    for char, repl in _UNICODE_REPLACE.items():
        text = text.replace(char, repl)
    # Codifica para latin-1 substituindo o que não couber
    return text.encode('latin-1', errors='replace').decode('latin-1')


class AntecipacaoPDF:
    def __init__(self, logo_path=None):
        self.logo_path = logo_path

    def criar_documento(self):
        pdf = FPDF()  # type: ignore[operator]
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
                img = img.resize((max_w, int(img.size[1] * ratio)), Image.Resampling.LANCZOS)
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
# Lógica de Antecipação
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

    def _registrar_movimentos_fornecedor(self, token, fornecedor, cnpj, data_pagamento_str, df_fornecedor):
        itens = []
        if df_fornecedor is None or df_fornecedor.empty:
            return 0

        for _, row in df_fornecedor.iterrows():
            numero_doc = row.get(self.col_numero_doc, '') if self.col_numero_doc in df_fornecedor.columns else ''
            itens.append({
                'token': str(token or ''),
                'fornecedor': str(fornecedor or ''),
                'cnpj': str(cnpj or ''),
                'data_pagamento': str(data_pagamento_str or ''),
                'loja': str(row.get('Loja', '') or ''),
                'numero_doc': str(numero_doc or ''),
                'valor_liquido': float(self._sf(row.get(self.col_valor_liquido, 0))),
                'desconto': float(self._sf(row.get(self.col_desconto_antecipacao, 0))),
                'valor_pagar': float(self._sf(row.get('Valor a pagar', 0))),
                'data_registro': datetime.now().strftime('%d/%m/%Y %H:%M:%S'),
            })

        return registrar_movimentos_relatorios(itens)

    def _serializar_itens_detalhados_fornecedor(self, df_fornecedor):
        itens = []
        if df_fornecedor is None or df_fornecedor.empty:
            return itens

        for _, row in df_fornecedor.iterrows():
            numero_doc = row.get(self.col_numero_doc, '') if self.col_numero_doc in df_fornecedor.columns else ''
            data_vencimento = row.get('Data de vencimento', '')
            if hasattr(data_vencimento, 'strftime'):
                data_vencimento = data_vencimento.strftime('%d/%m/%Y')
            prazo_dias = row.get('Dias de antecipacao', '')
            try:
                if pd.notna(prazo_dias):
                    prazo_dias = int(float(prazo_dias))
                else:
                    prazo_dias = ''
            except Exception:
                prazo_dias = ''

            itens.append({
                'loja': str(row.get('Loja', '') or ''),
                'numero_doc': str(numero_doc or ''),
                'data_vencimento': str(data_vencimento or ''),
                'prazo_dias': prazo_dias,
                'valor_liquido': float(self._sf(row.get(self.col_valor_liquido, 0))),
            })
        return itens

    def processar_arquivo(self, caminho, data_pagamento_str, taxa_fixa_str=None):
        try:
            df = pd.read_excel(caminho)
            df.columns = [corrigir_texto_exibicao(str(col)).strip() for col in df.columns]
            cols = list(df.columns)

            # Detectar colunas automaticamente pelo conteúdo do nome
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

            # Verificar colunas obrigatórias
            obrigatorias = ['CNPJ', 'Fornecedor', 'Data de vencimento', self.col_valor_liquido]
            faltando = [c for c in obrigatorias if c not in df.columns]
            if faltando:
                messagebox.showerror('Colunas não encontradas',
                    f'As seguintes colunas não foram identificadas na planilha:\n\n'
                    f'{chr(10).join(faltando)}\n\n'
                    f'Colunas encontradas no arquivo:\n{chr(10).join(cols[:20])}')
                return pd.DataFrame()

            # Criar coluna Loja se não existir
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
            messagebox.showerror('Erro', f'Arquivo não encontrado: {caminho}')
            return pd.DataFrame()
        except Exception as e:
            messagebox.showerror('Erro ao processar Excel', str(e))
            traceback.print_exc()
            return pd.DataFrame()

    def gerar_pdfs(self, diretorio_saida, logo_path, data_base, data_pagamento, taxa_unica, enviar_email, base_url=''):
        if self.df_processado.empty:
            messagebox.showwarning('Dados Ausentes', 'Nenhum dado processado.')
            return False

        if FPDF is None:
            detalhe = f'\n\nDetalhe tÃ©cnico: {_FPDF_IMPORT_ERROR}' if _FPDF_IMPORT_ERROR else ''
            messagebox.showerror(
                'Biblioteca PDF indisponivel',
                'Nao foi possivel carregar a biblioteca de PDF (fpdf).\n'
                'A geracao de relatorios foi bloqueada pelo ambiente do Windows.'
                f'{detalhe}'
            )
            return False

        os.makedirs(diretorio_saida, exist_ok=True)
        pdf_gen = AntecipacaoPDF(logo_path)
        email_sender = None

        if enviar_email:
            ss, sp, su, spw = get_smtp_credentials()
            if not all([ss, sp, su, spw]):
                messagebox.showwarning('SMTP', 'Configurações SMTP incompletas. Email desativado.')
                enviar_email = False
            else:
                try:
                    ss, sp, su, spw = str(ss), str(sp), str(su), str(spw)
                    email_sender = EmailSender(ss, sp, su, spw)
                    _m = re.search(r'(\d+)', str(sp))
                    p = int(_m.group(1)) if _m else 587
                    with smtplib.SMTP(ss, p) as srv:
                        srv.starttls(); srv.login(su, spw)
                except Exception as e:
                    messagebox.showerror('SMTP', f'Erro na conexão SMTP: {e}')
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
                itens_detalhados = self._serializar_itens_detalhados_fornecedor(df_f)
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
                    token = str(uuid.uuid4())
                    # Tenta várias combinações para encontrar o email
                    to_email = (
                        get_email_fornecedor(f'{fornecedor} - {cnpj_fmt}') or
                        get_email_fornecedor(cnpj_fmt) or
                        get_email_fornecedor(fornecedor) or
                        get_email_fornecedor(f'{cnpj_fmt} - {fornecedor}')
                    )
                    if to_email:
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
                            pdf_path,
                            cnpj=cnpj_fmt,
                            data_pagamento=data_pagamento.strftime('%d/%m/%Y'),
                            valor_total=total_f['valor'],
                            desconto_total=total_f['desconto'],
                            valor_pagar=total_f['pagar'],
                            itens_detalhados=itens_detalhados,
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
                            taxa_percentual=df_f['Taxa Aplicada (%)'].iloc[0] if 'Taxa Aplicada (%)' in df_f.columns else None,
                            taxa_display=taxa_display,
                            ai_base_url=ai_base_url,
                            itens_detalhados=itens_detalhados,
                        )

                        self._registrar_movimentos_fornecedor(
                            token=token,
                            fornecedor=fornecedor,
                            cnpj=cnpj_fmt,
                            data_pagamento_str=data_pagamento.strftime('%d/%m/%Y'),
                            df_fornecedor=df_f,
                        )

                        # Em producao (URL nao-local), registra no servidor remoto de respostas
                        # antes de enviar o email, para evitar links sem token cadastrado.
                        if not _is_local_base_url(base_url):
                            payload_remoto = {
                                'token': token,
                                # Campos de compatibilidade com o endpoint VPS
                                # (evita exibir "Proposta: None" na pagina de resposta).
                                'proposta_id': numero_proposta,
                                'cliente_email': to_email,
                                'cliente_nome': fornecedor,
                                'valor': float(total_f['pagar']),
                                'fornecedor': fornecedor,
                                'cnpj': cnpj_fmt,
                                'email': to_email,
                                'valor_total': float(total_f['valor']),
                                'desconto': float(total_f['desconto']),
                                'valor_pagar': float(total_f['pagar']),
                                'pdf_path': pdf_path,
                                'data_pagamento': data_pagamento.strftime('%d/%m/%Y'),
                                'assunto': subj,
                                'ai_chat_url': ai_chat_url,
                                'ai_id_proposta': ai_id_proposta,
                                'ai_token': ai_token,
                                'taxa_percentual': df_f['Taxa Aplicada (%)'].iloc[0] if 'Taxa Aplicada (%)' in df_f.columns else None,
                                'taxa_display': taxa_display,
                                'ai_base_url': ai_base_url,
                            }
                            remoto_ok = _registrar_proposta_resposta_remota(base_url, payload_remoto)
                            if not remoto_ok:
                                print(f'Falha no registro remoto da proposta {token}. Seguiremos com o envio de email para nao interromper o processo.')

                        html_b  = get_email_html(fornecedor, cnpj, db_str, dp_str, taxa_display,
                                                  total_f['valor'], total_f['desconto'], total_f['pagar'],
                                                  base_url, token, ai_chat_url=ai_chat_url)
                        plain_b = get_email_plaintext(fornecedor, cnpj, db_str, dp_str, taxa_display,
                                                       total_f['valor'], total_f['desconto'], total_f['pagar'],
                                                       base_url, token, ai_chat_url=ai_chat_url)

                        ok = email_sender.send_email(to_email, subj, html_b, plain_b, [pdf_path])
                        if ok:
                            enviados += 1
                            _atualizar_metadados_envio_proposta(token, email_enviado=True, erro_envio_email='')
                        else:
                            falhos += 1
                            _atualizar_metadados_envio_proposta(token, email_enviado=False, erro_envio_email='falha_smtp')
                    else:
                        sem_email += 1
                        _atualizar_metadados_envio_proposta(token, email_enviado=False, erro_envio_email='sem_email')
                        print(f'⚠ Sem email: {fornecedor} CNPJ:{cnpj_fmt}')
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
            messagebox.showinfo('Concluído',
                f'PDFs gerados com sucesso!\nTotal de fornecedores: {pdfs_gerados}\nPasta: {diretorio_saida}')
        return True

# ==============================================
# Dashboard – agregação de dados
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
# GUI – Classe Principal
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
        self._auto_envio_after_id = None
        self._iniciar_agendamento_envio_automatico()
        self.root.after_idle(_auto_backup_meses_anteriores)

    # -----------------------------------------------
    # Inicialização do servidor de respostas
    # -----------------------------------------------
    def _init_server(self):
        cfg = load_server_config()
        try:
            port = int(str(cfg.get('port', 5001) or 5001).strip())
        except Exception:
            port = 5001
        if FLASK_AVAILABLE:
            iniciar_servidor(port)
        else:
            print('Flask nao instalado. pip install flask para ativar respostas interativas.')

    # -----------------------------------------------
    # Layout raiz: sidebar + área principal
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

        # Área de conteúdo
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
        # Topo – Logo / Avatar
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

        # Itens de navegação
        nav_items = [
            ('dashboard',    'P', 'Painel'),
            ('relatorios',   'R', 'Gerar Propostas'),
            ('fornecedores', 'F', 'Fornecedores'),
            ('propostas',    'E', 'Propostas'),
            ('configuracoes','C', 'Configuracoes'),
        ]

        self._nav_buttons = {}
        for key, icon, label in nav_items:
            btn = self._create_nav_button(key, icon, label)
            self._nav_buttons[key] = btn

        # Rodapé sidebar
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

        # Mostrar a página
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
    # Construção de todas as páginas
    # -----------------------------------------------
    def _build_all_pages(self):
        for key, fn in [
            ('dashboard',    self._build_page_dashboard),
            ('relatorios',   self._build_page_gerar_propostas),
            ('fornecedores', self._build_page_fornecedores),
            ('propostas',    self._build_page_propostas),
            ('configuracoes',self._build_page_configuracoes),
        ]:
            frame = tk.Frame(self.content_area, bg=MAIN_BG)
            self._pages[key] = frame
            fn(frame)

    # -----------------------------------------------
    # Helpers de construção de UI
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
    # Página: Dashboard
    # -----------------------------------------------
    def _build_page_dashboard(self, parent):
        self._dash_parent = parent
        self._page_title(parent, 'Painel Mensal', 'Consolidado diário e mensal de propostas')

        filtro_frame = tk.Frame(parent, bg=MAIN_BG)
        filtro_frame.pack(fill='x', padx=28, pady=(0, 8))
        tk.Label(filtro_frame, text='Período:', font=self.ui_fonts['body_bold'],
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

        # Área de gráficos
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
                    messagebox.showwarning('Período inválido', 'Informe Data Inicial e Data Final no formato DD/MM/AAAA.')
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
            ('Em Negociação', stats['negociando'], ACCENT_ORANGE),
            ('Recusadas', stats['recusados'], DANGER_COLOR),
            ('Taxa Aprovação', f"{stats['taxa_aprovacao']:.1f}%", '#2f855a'),
        ]
        for i, (title, value, color) in enumerate(cards_info):
            c = self._card(self._dash_cards_frame, title, value, accent=color)
            c.grid(row=i // 4, column=i % 4, padx=8, pady=4, sticky='ew')
        for i in range(4):
            self._dash_cards_frame.columnconfigure(i, weight=1)

        # Limpar gráficos anteriores
        for w in self._dash_charts_frame.winfo_children():
            w.destroy()

        # Criar figura matplotlib
        fig = Figure(figsize=(12, 4.5), dpi=90, facecolor=MAIN_BG)

        # Gráfico 1: Evolução diária de propostas no mês
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
            ax1.set_title(f"Evolução Diária ({stats['periodo_label']})", fontsize=10, fontweight='bold', color=TEXT_DARK)
            ax1.tick_params(labelsize=7, colors=TEXT_GRAY)
            ax1.spines[['top', 'right']].set_visible(False)
        else:
            ax1.text(0.5, 0.5, 'Sem registros\nno período selecionado',
                     ha='center', va='center', transform=ax1.transAxes,
                     fontsize=9, color=TEXT_GRAY)
            ax1.set_title('Evolução Diária', fontsize=10, fontweight='bold', color=TEXT_DARK)

        # Gráfico 2: Barras – Top Empresas por volume no mês
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
            ax2.text(0.5, 0.5, 'Nenhuma proposta\nenviada no período',
                     ha='center', va='center', transform=ax2.transAxes,
                     fontsize=9, color=TEXT_GRAY)
            ax2.set_title('Rank de Empresas', fontsize=10, fontweight='bold', color=TEXT_DARK)

        # Gráfico 3: Pizza – Status das Propostas
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
            wedges, texts, autotexts = ax3.pie(  # type: ignore[misc]
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
    # Página: Gerar Propostas
    # -----------------------------------------------
    def _build_page_gerar_propostas(self, parent):
        self._page_title(parent, 'Gerar Propostas', 'Processe e envie propostas de antecipacao')

        card = tk.Frame(parent, bg=CARD_BG, relief='flat', padx=32, pady=24)
        card.config(highlightbackground='#e2e8f0', highlightthickness=1)
        card.pack(fill='both', expand=True, padx=28, pady=8)
        card.columnconfigure(1, weight=1)

        self._v_logo = tk.StringVar()
        self._v_arquivo = tk.StringVar()
        self._v_data_pgto = tk.StringVar(value=datetime.now().strftime('%d/%m/%Y'))
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
                            ('Taxa Fixa % (opcional, ex: 2,5):', self._v_taxa)]:
            tk.Label(card, text=label, font=self.ui_fonts['body'], fg=TEXT_DARK, bg=CARD_BG).grid(
                row=r, column=0, sticky='w', pady=8)
            extra_args = {}
            e = ttk.Entry(card, textvariable=var, width=50, **extra_args)
            e.grid(row=r, column=1, sticky='ew', padx=8, pady=8)
            r += 1

        # Checkbox email + botão processar
        chk_frame = tk.Frame(card, bg=CARD_BG)
        chk_frame.grid(row=r, column=0, columnspan=3, sticky='w', pady=8)
        ttk.Checkbutton(chk_frame, text='Enviar emails automaticamente', variable=self._v_enviar_email).pack(side='left')
        r += 1

        btn_frame = tk.Frame(card, bg=CARD_BG)
        btn_frame.grid(row=r, column=0, columnspan=3, pady=16)
        self._btn(btn_frame, 'Gerar Propostas', self.processar,
              color=ACCENT_BLUE, padx=28, pady=10).pack(side='left', padx=8)
        r += 1

        self._prog = ttk.Progressbar(card, mode='indeterminate')
        self._prog.grid(row=r, column=0, columnspan=3, sticky='ew', pady=8)
        r += 1
        self._status_lbl = tk.Label(card, text='Pronto para processar',
                                     font=self.ui_fonts['body'], fg=SUCCESS_COLOR, bg=CARD_BG)
        self._status_lbl.grid(row=r, column=0, columnspan=3, pady=4)

    # -----------------------------------------------
    # Página: Fornecedores / Emails
    # -----------------------------------------------
    def _build_page_fornecedores(self, parent):
        self._page_title(parent, 'Fornecedores & Emails', 'Gerencie emails e importe da planilha Excel')

        paned = tk.Frame(parent, bg=MAIN_BG)
        paned.pack(fill='both', expand=True, padx=28)
        paned.columnconfigure(0, weight=1)
        paned.columnconfigure(1, weight=1)

        # Card Esquerdo – Cadastro manual
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

        # Card Direito – Importar Excel
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
    # Página: Propostas
    # -----------------------------------------------
    def _build_page_propostas(self, parent):
        self._page_title(parent, 'Propostas Enviadas', 'Acompanhe respostas dos fornecedores')

        topo = tk.Frame(parent, bg=MAIN_BG)
        topo.pack(fill='x', padx=28, pady=(0, 8))
        self._btn(topo, 'Atualizar', self._refresh_propostas, color=ACCENT_BLUE, padx=14, pady=6).pack(side='left', padx=(0, 8))
        self._btn(topo, 'Enviar Proposta Atualizada', self.enviar_proposta_atualizada_selecionada, color='#2f855a', padx=14, pady=6).pack(side='left', padx=(0, 8))
        self._btn(topo, 'Reenviar Falhas de Email', self.reenviar_emails_falhos, color='#4a5568', padx=14, pady=6).pack(side='left', padx=(0, 8))
        self._btn(topo, 'Backfill Lojas (Excel)', self.backfill_lojas_por_excel, color='#2f855a', padx=14, pady=6).pack(side='left', padx=(0, 8))
        self._btn(topo, 'Limpar Movimentos sem Aceite', self.limpar_movimentos_sem_aceite, color='#975a16', padx=14, pady=6).pack(side='left', padx=(0, 8))
        self._btn(topo, 'Exportar Relatorios Mensais', self.exportar_relatorios_mensais, color='#2b6cb0', padx=14, pady=6).pack(side='left', padx=(0, 8))
        self._btn(topo, 'Enviar Aceitas do Dia', self.enviar_aceitas_do_dia, color=ACCENT_ORANGE, padx=14, pady=6).pack(side='left', padx=(0, 8))
        self._btn(topo, 'Abrir Pasta de Aceitas', self.abrir_propostas_aceitas, color=SUCCESS_COLOR, padx=14, pady=6).pack(side='left')

        # Filtro de mes + botao de backup
        filtro_frame = tk.Frame(parent, bg=MAIN_BG)
        filtro_frame.pack(fill='x', padx=28, pady=(0, 4))
        tk.Label(filtro_frame, text='Mes:', font=self.ui_fonts['body_small'],
                 fg=TEXT_DARK, bg=MAIN_BG).pack(side='left', padx=(0, 6))
        self._v_prop_mes_filtro = tk.StringVar(value='Mes Vigente')
        self._prop_mes_combo = ttk.Combobox(
            filtro_frame, textvariable=self._v_prop_mes_filtro,
            state='readonly', width=16, values=['Mes Vigente', 'Todos']
        )
        self._prop_mes_combo.pack(side='left', padx=(0, 8))
        self._prop_mes_combo.bind('<<ComboboxSelected>>', lambda _e: self._refresh_propostas())
        self._btn(filtro_frame, 'Fazer Backup do Mes', self._backup_mes_vigente,
                  color='#4a5568', padx=12, pady=4).pack(side='left', padx=(0, 8))
        tk.Label(filtro_frame, text='(salva em Backups_Mensais/)',
                 font=self.ui_fonts['body_small'], fg=TEXT_GRAY, bg=MAIN_BG).pack(side='left')

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

        auto_frame = tk.Frame(parent, bg=MAIN_BG)
        auto_frame.pack(fill='x', padx=28, pady=(0, 8))
        self._v_envio_aceitas_automatico = tk.BooleanVar(
            value=pref_envio.get('envio_aceitas_automatico_ativo', True)
        )
        ttk.Checkbutton(
            auto_frame,
            text='Enviar automaticamente aceitas do dia para pagamento no proximo dia util',
            variable=self._v_envio_aceitas_automatico,
            command=self._on_toggle_envio_auto_aceitas
        ).pack(side='left', padx=(0, 8))

        tk.Label(auto_frame, text='Horario (HH:MM):', font=self.ui_fonts['body_small'], fg=TEXT_DARK, bg=MAIN_BG).pack(side='left', padx=(8, 6))
        self._v_horario_envio_auto = tk.StringVar(value=pref_envio.get('envio_aceitas_automatico_hora', '18:00'))
        horario_entry = ttk.Entry(auto_frame, textvariable=self._v_horario_envio_auto, width=8)
        horario_entry.pack(side='left')
        horario_entry.bind('<FocusOut>', lambda _e: self._on_toggle_envio_auto_aceitas())

        cols = ('Fornecedor', 'CNPJ', 'Email', 'Valor a Pagar', 'Data Envio', 'Status', 'Origem', 'Data Resposta')
        frame = tk.Frame(parent, bg=MAIN_BG)
        frame.pack(fill='both', expand=True, padx=28)

        self._prop_tree = ttk.Treeview(frame, columns=cols, show='headings', height=20)
        widths = {'Fornecedor': 165, 'CNPJ': 110, 'Email': 170, 'Valor a Pagar': 110,
              'Data Envio': 105, 'Status': 90, 'Origem': 80, 'Data Resposta': 110}
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
            ('Fornecedor', 0.19, 165),
            ('CNPJ', 0.12, 110),
            ('Email', 0.21, 170),
            ('Valor a Pagar', 0.12, 120),
            ('Data Envio', 0.11, 110),
            ('Status', 0.10, 100),
            ('Origem', 0.07, 80),
            ('Data Resposta', 0.08, 110),
        ]
        self._bind_treeview_resize(frame, self._prop_tree, self._prop_tree_columns)

    def _backup_mes_vigente(self):
        mes_ref = datetime.now().strftime('%Y-%m')
        ok = _fazer_backup_mensal(mes_ref)
        if ok:
            nome = 'propostas_backup_' + mes_ref.replace('-', '_') + '.json'
            messagebox.showinfo('Backup', f'Backup do mes vigente salvo em:\nBackups_Mensais/{nome}')
        else:
            messagebox.showwarning('Backup', 'Nenhuma proposta encontrada para o mes vigente.')

    def _refresh_propostas(self):
        sincronizar_respostas_ia()
        # Atualizar opcoes do filtro de mes
        if hasattr(self, '_prop_mes_combo'):
            meses = get_dashboard_month_refs()
            atual_lbl = datetime.now().strftime('%m/%Y')
            labels = ['Mes Vigente', 'Todos']
            for mref in meses:
                lbl = _mes_label(mref)
                if lbl and lbl != atual_lbl:
                    labels.append(lbl)
            self._prop_mes_combo['values'] = labels
            if self._v_prop_mes_filtro.get() not in labels:
                self._v_prop_mes_filtro.set('Mes Vigente')

        filtro = self._v_prop_mes_filtro.get() if hasattr(self, '_v_prop_mes_filtro') else 'Todos'
        mes_atual = datetime.now().strftime('%Y-%m')

        for row in self._prop_tree.get_children():
            self._prop_tree.delete(row)
        propostas = load_propostas()

        def fmt_val(v):
            try:
                return f"R$ {float(v):,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
            except Exception:
                return str(v)

        def _sort_dt(item):
            dt = _parse_datetime_br(item[1].get('data_envio', ''))
            return dt if dt else datetime.min

        status_labels = {'aceito': 'Aceito', 'negociando': 'Negociando', 'recusado': 'Recusado', 'pendente': 'Pendente'}
        for token, p in sorted(propostas.items(), key=_sort_dt, reverse=True):
            dt_envio = _parse_datetime_br(p.get('data_envio', ''))
            if filtro == 'Mes Vigente':
                if not dt_envio or _mes_ref(dt_envio) != mes_atual:
                    continue
            elif filtro not in ('Todos', ''):
                mref_filtro = _mes_ref_from_label(filtro)
                if not dt_envio or _mes_ref(dt_envio) != mref_filtro:
                    continue
            st = p.get('status', 'pendente')
            self._prop_tree.insert('', 'end', iid=token, values=(
                p.get('fornecedor', ''),
                p.get('cnpj', ''),
                p.get('email', ''),
                fmt_val(p.get('valor_pagar', 0)),
                p.get('data_envio', ''),
                status_labels.get(st, st),
                p.get('origem_resposta', '-') or '-',
                p.get('data_resposta', '') or '-',
            ), tags=(st,))

    def _get_selected_proposta_token(self):
        selecionados = self._prop_tree.selection()
        if not selecionados:
            return None
        return str(selecionados[0])

    def _montar_df_proposta_atualizada(self, proposta, taxa_percentual_final):
        itens = proposta.get('itens_detalhados') or []
        if not isinstance(itens, list) or not itens:
            return pd.DataFrame()

        taxa_decimal = float(taxa_percentual_final) / 100.0
        linhas = []
        for item in itens:
            if not isinstance(item, dict):
                continue
            valor_liquido = self.antecipacao._sf(item.get('valor_liquido', 0))
            prazo_dias = self.antecipacao._si(item.get('prazo_dias', 0))
            desconto = self.antecipacao.calcular_desconto(valor_liquido, prazo_dias, taxa_decimal)
            valor_pagar = valor_liquido - desconto
            data_vencimento = item.get('data_vencimento', '')
            try:
                data_vencimento = datetime.strptime(str(data_vencimento), '%d/%m/%Y') if data_vencimento else None
            except Exception:
                data_vencimento = None
            linhas.append({
                'Loja': str(item.get('loja', '') or ''),
                'Numero doc.': str(item.get('numero_doc', '') or ''),
                'Data de vencimento': data_vencimento,
                'Dias de antecipacao': prazo_dias,
                'Valor liquido': valor_liquido,
                'Desconto de antecipacao': desconto,
                'Valor a pagar': valor_pagar,
            })
        return pd.DataFrame(linhas)

    def _gerar_pdf_proposta_atualizada_manual(self, proposta, taxa_percentual_final):
        df_atualizado = self._montar_df_proposta_atualizada(proposta, taxa_percentual_final)
        if df_atualizado.empty:
            raise ValueError('A proposta selecionada nao possui itens detalhados suficientes para regenerar o relatorio atualizado.')

        fornecedor = str(proposta.get('fornecedor', '') or '')
        cnpj = str(proposta.get('cnpj', '') or '')
        data_pagamento_str = str(proposta.get('data_pagamento', '') or '')
        try:
            data_pagamento = datetime.strptime(data_pagamento_str, '%d/%m/%Y')
        except Exception:
            data_pagamento = datetime.now()

        data_base_str = str(proposta.get('data_envio', '') or '')
        try:
            data_base = datetime.strptime(data_base_str.split(' ')[0], '%d/%m/%Y') if data_base_str else datetime.now()
        except Exception:
            data_base = datetime.now()

        taxa_display = f'{float(taxa_percentual_final):.2f}%'
        pdf_gen = AntecipacaoPDF(self.logo_path)
        pdf = pdf_gen.criar_documento()
        pdf_gen.adicionar_cabecalho(pdf, fornecedor, cnpj, data_base, data_pagamento, taxa_display)

        total_f = {'valor': 0.0, 'desconto': 0.0, 'pagar': 0.0}
        for loja in df_atualizado['Loja'].fillna('').unique():
            dl = df_atualizado[df_atualizado['Loja'] == loja].copy()
            pdf_gen.adicionar_secao_loja(pdf, dl, loja)
            total_loja = {
                'valor': float(dl['Valor liquido'].sum()),
                'desconto': float(dl['Desconto de antecipacao'].sum()),
                'pagar': float(dl['Valor a pagar'].sum()),
            }
            total_f['valor'] += total_loja['valor']
            total_f['desconto'] += total_loja['desconto']
            total_f['pagar'] += total_loja['pagar']
            pdf_gen.adicionar_subtotal(pdf, total_loja)

        pdf_gen.adicionar_total_fornecedor(pdf, total_f)
        pdf_gen.adicionar_secao_boletos(pdf)
        pdf_gen.adicionar_rodape(pdf)

        os.makedirs(PROPOSTAS_ACEITAS_DIR, exist_ok=True)
        nome_pdf = f'Proposta_Atualizada_{normalizar_cnpj(cnpj) or "SEM_CNPJ"}.pdf'
        pdf_path = os.path.join(PROPOSTAS_ACEITAS_DIR, nome_pdf)
        pdf.output(pdf_path)
        return pdf_path, total_f, taxa_display, data_base.strftime('%d/%m/%Y'), data_pagamento.strftime('%d/%m/%Y')

    def enviar_proposta_atualizada_selecionada(self):
        token = self._get_selected_proposta_token()
        if not token:
            messagebox.showwarning('Proposta', 'Selecione uma proposta na lista para enviar a proposta atualizada.')
            return

        propostas = load_propostas()
        proposta = propostas.get(token)
        if not proposta:
            messagebox.showerror('Proposta', 'Proposta selecionada nao encontrada no arquivo local.')
            return

        if str(proposta.get('status', '') or '') != 'aceito':
            messagebox.showwarning('Proposta', 'A proposta precisa estar com status Aceito para enviar a proposta atualizada.')
            return

        fornecedor_email = str(proposta.get('email', '') or '').strip()
        if not fornecedor_email:
            messagebox.showwarning('Email', 'A proposta selecionada nao possui email do fornecedor.')
            return

        taxa_final_percentual = _resolver_taxa_final_aceita_percentual(proposta)
        if taxa_final_percentual is None:
            messagebox.showwarning('Taxa', 'Nao foi possivel identificar a taxa final aceita desta proposta.')
            return

        try:
            pdf_path, total_f, taxa_display, data_base_str, data_pagamento_str = self._gerar_pdf_proposta_atualizada_manual(
                proposta,
                taxa_final_percentual,
            )
        except Exception as e:
            messagebox.showerror('Proposta Atualizada', str(e))
            return

        ss, sp, su, spw = get_smtp_credentials()
        if not all([ss, sp, su, spw]):
            messagebox.showwarning('SMTP', 'Configuracoes SMTP incompletas.')
            return

        email_sender = EmailSender(str(ss), str(sp), str(su), str(spw))
        fornecedor = str(proposta.get('fornecedor', '') or '')
        cnpj = str(proposta.get('cnpj', '') or '')
        assunto = f'Proposta Atualizada de Antecipação de Pagamentos - {fornecedor} ({cnpj})'
        html_b = get_email_html_proposta_atualizada(
            fornecedor,
            cnpj,
            data_base_str,
            data_pagamento_str,
            taxa_display,
            total_f['valor'],
            total_f['desconto'],
            total_f['pagar'],
        )
        plain_b = get_email_plaintext_proposta_atualizada(
            fornecedor,
            cnpj,
            data_base_str,
            data_pagamento_str,
            taxa_display,
            total_f['valor'],
            total_f['desconto'],
            total_f['pagar'],
        )

        ok = email_sender.send_email(fornecedor_email, assunto, html_b, plain_b, [pdf_path])
        if not ok:
            messagebox.showerror('Email', 'Falha ao enviar a proposta atualizada por email.')
            return

        proposta['pdf_path'] = pdf_path
        proposta['valor_total'] = float(total_f['valor'])
        proposta['desconto'] = float(total_f['desconto'])
        proposta['valor_pagar'] = float(total_f['pagar'])
        propostas[token] = proposta
        save_propostas(propostas)
        self._refresh_propostas()
        messagebox.showinfo('Sucesso', f'Proposta atualizada enviada para {fornecedor_email}.')

    # -----------------------------------------------
    # PÃ¡gina: Configurações
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

        tk.Label(
            frame,
            text='WhatsApp para Negociacao (opcional):',
            font=self.ui_fonts['body'],
            fg=TEXT_DARK,
            bg=CARD_BG,
        ).grid(row=5, column=0, sticky='w', pady=8)
        self._v_whatsapp_contato = tk.StringVar(value=str(cfg.get('whatsapp_contato', '') or ''))
        ttk.Entry(frame, textvariable=self._v_whatsapp_contato, width=45).grid(row=5, column=1, sticky='ew', padx=8, pady=8)

        flask_status = 'Flask instalado' if FLASK_AVAILABLE else 'Flask NAO instalado - execute: pip install flask'
        tk.Label(
            frame,
            text=flask_status,
            font=self.ui_fonts['body'],
            fg=SUCCESS_COLOR if FLASK_AVAILABLE else DANGER_COLOR,
            bg=CARD_BG,
        ).grid(row=6, column=0, columnspan=2, sticky='w', pady=8)

        ngrok_status = 'pyngrok instalado (URL publica automatica disponivel)' if NGROK_AVAILABLE else 'pyngrok nao instalado - execute: pip install pyngrok'
        tk.Label(
            frame,
            text=ngrok_status,
            font=self.ui_fonts['body_small'],
            fg=SUCCESS_COLOR if NGROK_AVAILABLE else WARN_COLOR,
            bg=CARD_BG,
        ).grid(row=7, column=0, columnspan=2, sticky='w', pady=(0, 8))

        btns = tk.Frame(frame, bg=CARD_BG)
        btns.grid(row=8, column=0, columnspan=2, pady=16)
        self._btn(btns, 'Salvar Configuracao', self.salvar_server_config, color=ACCENT_BLUE).pack(side='left', padx=8)
        if FLASK_AVAILABLE:
            self._btn(btns, 'Testar Servidor', self.testar_servidor, color='#4a5568').pack(side='left', padx=8)

    # -----------------------------------------------
    # Ações dos botões
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

    def sel_excel_import(self):
        p = filedialog.askopenfilename(filetypes=[('Excel', '*.xlsx *.xls')])
        if p:
            self._v_excel_import.set(p)


    def abrir_propostas_aceitas(self):
        os.makedirs(PROPOSTAS_ACEITAS_DIR, exist_ok=True)
        os.startfile(PROPOSTAS_ACEITAS_DIR)

    def reenviar_emails_falhos(self):
        propostas = load_propostas()
        candidatas = []
        for token, p in propostas.items():
            email = str(p.get('email', '') or '').strip()
            if not email:
                continue
            erro_envio = str(p.get('erro_envio_email', '') or '').strip()
            email_enviado = bool(p.get('email_enviado', False))
            if (not email_enviado) and erro_envio in ('pendente_envio', 'falha_registro_remoto', 'falha_smtp'):
                candidatas.append((token, p))

        if not candidatas:
            messagebox.showinfo('Reenvio', 'Nao ha propostas com falha de envio para reenviar.')
            return

        ss, sp, su, spw = get_smtp_credentials()
        if not all([ss, sp, su, spw]):
            messagebox.showerror('SMTP', 'Configuracoes SMTP incompletas para reenviar emails.')
            return

        try:
            email_sender = EmailSender(str(ss), str(sp), str(su), str(spw))
        except Exception as e:
            messagebox.showerror('SMTP', f'Falha ao inicializar SMTP: {e}')
            return

        cfg = load_server_config()
        base_url = str(cfg.get('base_url', 'http://localhost:5001') or 'http://localhost:5001').strip()

        reenviados = falhas = 0
        for token, p in candidatas:
            try:
                fornecedor = str(p.get('fornecedor', '') or '')
                cnpj = str(p.get('cnpj', '') or '')
                to_email = str(p.get('email', '') or '').strip()
                assunto = str(p.get('assunto', '') or f'Proposta de Antecipacao de Pagamentos - {fornecedor} ({cnpj})')
                pdf_path = str(p.get('pdf_path', '') or '')

                # Em producao, revalida/recadastra token antes de reenviar para evitar link quebrado.
                if not _is_local_base_url(base_url):
                    numero_proposta = f"{normalizar_cnpj(cnpj) or 'SEM_CNPJ'}-{token[:8]}-REENVIO"
                    payload_remoto = {
                        'token': token,
                        'proposta_id': numero_proposta,
                        'cliente_email': to_email,
                        'cliente_nome': fornecedor,
                        'valor': float(p.get('valor_pagar', 0) or 0),
                        'fornecedor': fornecedor,
                        'cnpj': cnpj,
                        'email': to_email,
                        'valor_total': float(p.get('valor_total', 0) or 0),
                        'desconto': float(p.get('desconto', 0) or 0),
                        'valor_pagar': float(p.get('valor_pagar', 0) or 0),
                        'pdf_path': pdf_path,
                        'data_pagamento': str(p.get('data_pagamento', '') or ''),
                        'assunto': assunto,
                        'ai_chat_url': str(p.get('ai_chat_url', '') or ''),
                        'ai_id_proposta': p.get('ai_id_proposta'),
                        'ai_token': str(p.get('ai_token', '') or ''),
                        'taxa_percentual': p.get('taxa_percentual'),
                        'taxa_display': str(p.get('taxa_display', '') or ''),
                        'ai_base_url': str(p.get('ai_base_url', '') or ''),
                    }
                    remoto_ok = _registrar_proposta_resposta_remota(base_url, payload_remoto)
                    if not remoto_ok:
                        print(f'Falha no registro remoto da proposta {token} no reenvio. Seguiremos com o envio de email.')

                dt_base = _parse_datetime_br(p.get('data_envio', ''))
                data_base = dt_base.strftime('%d/%m/%Y') if dt_base else datetime.now().strftime('%d/%m/%Y')
                data_pagamento = str(p.get('data_pagamento', '') or '')
                taxa_display = str(p.get('taxa_display', '') or '')

                html_b = get_email_html(
                    fornecedor,
                    cnpj,
                    data_base,
                    data_pagamento,
                    taxa_display,
                    float(p.get('valor_total', 0) or 0),
                    float(p.get('desconto', 0) or 0),
                    float(p.get('valor_pagar', 0) or 0),
                    base_url,
                    token,
                    ai_chat_url=str(p.get('ai_chat_url', '') or ''),
                )
                plain_b = get_email_plaintext(
                    fornecedor,
                    cnpj,
                    data_base,
                    data_pagamento,
                    taxa_display,
                    float(p.get('valor_total', 0) or 0),
                    float(p.get('desconto', 0) or 0),
                    float(p.get('valor_pagar', 0) or 0),
                    base_url,
                    token,
                    ai_chat_url=str(p.get('ai_chat_url', '') or ''),
                )

                anexos = [pdf_path] if (pdf_path and os.path.exists(pdf_path)) else []
                ok = email_sender.send_email(to_email, assunto, html_b, plain_b, anexos)
                if ok:
                    reenviados += 1
                    _atualizar_metadados_envio_proposta(token, email_enviado=True, erro_envio_email='')
                else:
                    falhas += 1
                    _atualizar_metadados_envio_proposta(token, email_enviado=False, erro_envio_email='falha_smtp')
            except Exception as e:
                falhas += 1
                _atualizar_metadados_envio_proposta(token, email_enviado=False, erro_envio_email='falha_smtp')
                print(f'Falha ao reenviar email da proposta {token}: {e}')

        self._refresh_propostas()
        messagebox.showinfo(
            'Reenvio concluido',
            f'Propostas com falha identificadas: {len(candidatas)}\n'
            f'Reenviadas com sucesso: {reenviados}\n'
            f'Falhas restantes: {falhas}'
        )

    def importar_excel_emails(self):
        path = self._v_excel_import.get().strip()
        if not path:
            messagebox.showwarning('Arquivo', 'Selecione um arquivo Excel primeiro.')
            return
        count, err = importar_emails_excel(path)
        if err:
            messagebox.showerror('Erro', f'Erro ao importar:\n{err}')
        else:
            messagebox.showinfo('Importação', f'{count} email(s) importado(s) com sucesso!')
            self._refresh_email_list()

    def add_email_forn(self):
        key   = self._v_forn_key.get().strip()
        email = self._v_forn_email.get().strip()
        if not key or not email:
            messagebox.showwarning('Campos', 'Preencha o Fornecedor e o Email.')
            return
        if '@' not in email:
            messagebox.showwarning('Email', 'Email inválido.')
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
            messagebox.showwarning('Campos', 'Preencha servidor, porta e usuário.')
            return
        if not spw:
            _, _, _, spw = get_smtp_credentials()
            spw = spw or ''
        try:
            set_smtp_credentials(ss, sp, su, spw)
            messagebox.showinfo('Salvo', 'Configurações SMTP salvas!')
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
            _m = re.search(r'(\d+)', sp)
            p = int(_m.group(1)) if _m else 587
            with smtplib.SMTP(ss, p) as srv:
                srv.starttls()
                srv.login(su, spw)
            messagebox.showinfo('Sucesso', 'Conexão SMTP OK!')
        except Exception as e:
            messagebox.showerror('Erro', str(e))

    def salvar_server_config(self):
        cfg = {
            'base_url': self._v_base_url.get().strip(),
            'port': int(self._v_srv_port.get().strip() or 5001),
            'ngrok_authtoken': self._v_ngrok_token.get().strip(),
            'whatsapp_contato': self._v_whatsapp_contato.get().strip() if hasattr(self, '_v_whatsapp_contato') else '',
        }
        save_server_config(cfg)
        messagebox.showinfo('Salvo', 'Configuração do servidor salva!')

    def testar_servidor(self):
        import urllib.request
        try:
            port = self._v_srv_port.get().strip() or '5001'
            urllib.request.urlopen(f'http://localhost:{port}/status', timeout=3)
            messagebox.showinfo('Servidor', f'Servidor respondendo na porta {port}!')
        except Exception:
            messagebox.showwarning('Servidor', 'Servidor não respondeu. Verifique se está rodando.')

    def _selecionar_destinatarios(self, sugestoes=None):
        sugestoes = sorted(set(s for s in (sugestoes or []) if s and '@' in s), key=lambda x: x.lower())
        resultado: dict = {'emails': None}

        win = tk.Toplevel(self.root)
        win.title(corrigir_texto_exibicao('Selecionar Destinatários'))
        win.configure(bg=CARD_BG)
        dialog_width = _clamp(int(self.display_metrics['screen_width'] * 0.32), self._scale(520), self._scale(760))
        dialog_height = _clamp(int(self.display_metrics['screen_height'] * 0.42), self._scale(430), self._scale(620))
        win.geometry(f'{dialog_width}x{dialog_height}')
        win.transient(self.root)
        win.grab_set()

        tk.Label(win, text='Selecione um ou mais destinatários:',
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
                messagebox.showwarning('Destinatários', 'Selecione ou informe ao menos um email.', parent=win)
                return

            invalidos = [e for e in emails if not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', e)]
            if invalidos:
                messagebox.showwarning('Email inválido', f'Email(s) inválido(s):\n' + '\n'.join(invalidos), parent=win)
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
            raise ValueError('Email(s) inválido(s):\n' + '\n'.join(invalidos))
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
            salvar_emails_aceitas_automaticamente=habilitado,
            envio_aceitas_automatico_ativo=bool(getattr(self, '_v_envio_aceitas_automatico', tk.BooleanVar(value=True)).get()),
            envio_aceitas_automatico_hora=str(getattr(self, '_v_horario_envio_auto', tk.StringVar(value='18:00')).get()).strip() or '18:00',
        )

    def _persistir_emails_aceitas_se_habilitado(self, texto_forcado=None):
        if not getattr(self, '_v_salvar_emails_aceitas_auto', None):
            return
        if not self._v_salvar_emails_aceitas_auto.get():
            return
        texto = self._v_emails_aceitas_dia.get().strip() if texto_forcado is None else str(texto_forcado).strip()
        save_envio_aceitas_pref(
            emails_aceitas_dia=texto,
            salvar_emails_aceitas_automaticamente=True,
            envio_aceitas_automatico_ativo=bool(getattr(self, '_v_envio_aceitas_automatico', tk.BooleanVar(value=True)).get()),
            envio_aceitas_automatico_hora=str(getattr(self, '_v_horario_envio_auto', tk.StringVar(value='18:00')).get()).strip() or '18:00',
        )

    def _on_toggle_envio_auto_aceitas(self):
        save_envio_aceitas_pref(
            emails_aceitas_dia=self._v_emails_aceitas_dia.get().strip() if hasattr(self, '_v_emails_aceitas_dia') else '',
            salvar_emails_aceitas_automaticamente=bool(getattr(self, '_v_salvar_emails_aceitas_auto', tk.BooleanVar(value=True)).get()),
            envio_aceitas_automatico_ativo=bool(self._v_envio_aceitas_automatico.get()) if hasattr(self, '_v_envio_aceitas_automatico') else True,
            envio_aceitas_automatico_hora=str(self._v_horario_envio_auto.get()).strip() if hasattr(self, '_v_horario_envio_auto') else '18:00',
        )

    def _coletar_aceitas_do_dia(self, data_ref=None):
        data_base = data_ref if isinstance(data_ref, datetime) else datetime.now()
        dia_ref = data_base.strftime('%d/%m/%Y')
        propostas = load_propostas()
        return [
            p for p in propostas.values()
            if p.get('status') == 'aceito' and str(p.get('data_resposta', '')).startswith(dia_ref)
        ]

    def _parse_horario_envio_auto(self, horario_txt):
        txt = str(horario_txt or '').strip() or '18:00'
        m = re.fullmatch(r'(\d{1,2}):(\d{2})', txt)
        if not m:
            return 18, 0
        h = max(0, min(23, int(m.group(1))))
        mn = max(0, min(59, int(m.group(2))))
        return h, mn

    def _enviar_pagamento_proximo_dia_automatico(self, data_ref=None):
        data_base = data_ref if isinstance(data_ref, datetime) else datetime.now()
        pref = get_envio_aceitas_pref()
        if not pref.get('envio_aceitas_automatico_ativo', True):
            return False

        ult_envio = str(pref.get('ultima_data_envio_auto_aceitas', '') or '').strip()
        dia_ref = data_base.strftime('%d/%m/%Y')
        if ult_envio == dia_ref:
            return False

        aceitas_hoje = self._coletar_aceitas_do_dia(data_base)
        if not aceitas_hoje:
            return False

        destinatarios = []
        try:
            destinatarios = self._parse_emails_texto(pref.get('emails_aceitas_dia', ''))
        except Exception:
            destinatarios = []
        if not destinatarios:
            return False

        ss, sp, su, spw = get_smtp_credentials()
        if not all([ss, sp, su, spw]):
            return False

        pagto_dt = _proximo_dia_util(data_base)
        data_pagamento_auto = pagto_dt.strftime('%d/%m/%Y')
        assunto = f"[Pagamento Proximo Dia] Propostas aprovadas em {dia_ref}"

        linhas_html = []
        linhas_txt = []
        for p in aceitas_hoje:
            fornecedor = str(p.get('fornecedor', '') or '')
            valor = _fmt_moeda_br(float(p.get('valor_pagar', 0) or 0))
            linhas_html.append(
                f"<tr><td style='padding:6px 8px'>{html.escape(fornecedor)}</td><td style='padding:6px 8px'>{data_pagamento_auto}</td><td style='padding:6px 8px;text-align:right'>{valor}</td></tr>"
            )
            linhas_txt.append(f"Fornecedor: {fornecedor} | Data pagamento: {data_pagamento_auto} | Pagar R$: {valor}")

        html_body = (
            "<!DOCTYPE html><html lang='pt-BR'><head><meta charset='UTF-8'></head><body style='font-family:Arial,sans-serif'>"
            f"<h3>Propostas aprovadas no dia {dia_ref} para pagamento em {data_pagamento_auto}</h3>"
            "<table border='1' cellspacing='0' cellpadding='0' style='border-collapse:collapse'>"
            "<thead><tr style='background:#f0f2f5'><th style='padding:6px 8px'>Fornecedor</th><th style='padding:6px 8px'>Data pagamento</th><th style='padding:6px 8px'>Pagar R$</th></tr></thead>"
            f"<tbody>{''.join(linhas_html)}</tbody></table></body></html>"
        )
        txt_body = "Propostas aprovadas para pagamento no próximo dia útil:\n\n" + "\n".join(linhas_txt)

        sender = EmailSender(str(ss), str(sp), str(su), str(spw))
        enviados = 0
        for dest in destinatarios:
            if sender.send_email(dest, assunto, html_body, txt_body):
                enviados += 1

        if enviados:
            save_envio_aceitas_pref(ultima_data_envio_auto_aceitas=dia_ref)
            return True
        return False

    def _verificar_envio_automatico_aceitas(self):
        pref = get_envio_aceitas_pref()
        if not pref.get('envio_aceitas_automatico_ativo', True):
            return
        hora, minuto = self._parse_horario_envio_auto(pref.get('envio_aceitas_automatico_hora', '18:00'))
        agora = datetime.now()
        if (agora.hour, agora.minute) >= (hora, minuto):
            try:
                self._enviar_pagamento_proximo_dia_automatico(agora)
            except Exception as e:
                print(f'Falha no envio automatico de aceitas: {e}')

    def _iniciar_agendamento_envio_automatico(self):
        self._stop_envio_automatico()

        def _tick():
            self._auto_envio_after_id = None
            self._verificar_envio_automatico_aceitas()
            self._auto_envio_after_id = self.root.after(5 * 60 * 1000, _tick)

        self._auto_envio_after_id = self.root.after(20 * 1000, _tick)

    def _stop_envio_automatico(self):
        if getattr(self, '_auto_envio_after_id', None):
            try:
                self.root.after_cancel(self._auto_envio_after_id)
            except Exception:
                pass
        self._auto_envio_after_id = None

    def exportar_relatorios_mensais(self):
        try:
            resultado = gerar_relatorios_mensais_fechamento(RELATORIOS_MENSAIS_DIR)
            meses = int(resultado.get('meses', 0) or 0)
            arquivos = int(resultado.get('arquivos', 0) or 0)
            if meses == 0:
                messagebox.showwarning('Relatorios', 'Nao ha dados suficientes para gerar os relatorios mensais.')
                return
            messagebox.showinfo(
                'Relatorios Mensais',
                f'Relatorios gerados com sucesso!\nMeses processados: {meses}\nArquivos exportados: {arquivos}\nPasta: {RELATORIOS_MENSAIS_DIR}'
            )
        except Exception as e:
            messagebox.showerror('Relatorios', f'Falha ao exportar relatorios mensais:\n{e}')

    def backfill_lojas_por_excel(self):
        caminho = filedialog.askopenfilename(
            title='Selecione a planilha para backfill de lojas',
            filetypes=[('Excel', '*.xlsx *.xls')]
        )
        if not caminho:
            return

        data_pagamento = simpledialog.askstring(
            'Backfill de Lojas',
            'Informe a data de pagamento da planilha (DD/MM/AAAA):',
            parent=self.root,
        )
        if data_pagamento is None:
            return
        data_pagamento = str(data_pagamento).strip()

        try:
            datetime.strptime(data_pagamento, '%d/%m/%Y')
        except Exception:
            messagebox.showwarning('Backfill', 'Data invalida. Use DD/MM/AAAA.')
            return

        taxa_fixa = simpledialog.askstring(
            'Backfill de Lojas',
            'Taxa fixa % (opcional, deixe vazio para dinamica):',
            parent=self.root,
        )
        taxa_fixa = str(taxa_fixa or '').strip()

        try:
            resultado = backfill_movimentos_por_excel(caminho, data_pagamento, taxa_fixa)
            rel = gerar_relatorios_mensais_fechamento(RELATORIOS_MENSAIS_DIR)
            messagebox.showinfo(
                'Backfill concluido',
                f"Linhas lidas da planilha: {resultado.get('linhas_excel', 0)}\n"
                f"Movimentos adicionados: {resultado.get('movimentos_adicionados', 0)}\n"
                f"Linhas vinculadas a propostas aceitas: {resultado.get('linhas_vinculadas', 0)}\n"
                f"Linhas ignoradas (sem proposta aceita): {resultado.get('linhas_ignoradas_sem_aceite', 0)}\n"
                f"Relatorios atualizados: {rel.get('arquivos', 0)} arquivos"
            )
        except Exception as e:
            messagebox.showerror('Backfill', f'Falha ao processar backfill por Excel:\n{e}')

    def limpar_movimentos_sem_aceite(self):
        ok = messagebox.askyesno(
            'Limpeza de Movimentos',
            'Isso vai remover definitivamente do historico os movimentos sem proposta aceita. Deseja continuar?'
        )
        if not ok:
            return

        try:
            resultado = limpar_movimentos_sem_aceite_definitivo()
            rel = gerar_relatorios_mensais_fechamento(RELATORIOS_MENSAIS_DIR)
            messagebox.showinfo(
                'Limpeza concluida',
                f"Movimentos antes: {resultado.get('movimentos_antes', 0)}\n"
                f"Movimentos mantidos: {resultado.get('movimentos_mantidos', 0)}\n"
                f"Movimentos removidos: {resultado.get('movimentos_removidos', 0)}\n"
                f" - sem token: {resultado.get('removidos_sem_token', 0)}\n"
                f" - token nao aceito: {resultado.get('removidos_token_nao_aceito', 0)}\n"
                f"Relatorios atualizados: {rel.get('arquivos', 0)} arquivos"
            )
        except Exception as e:
            messagebox.showerror('Limpeza', f'Falha ao limpar movimentos sem aceite:\n{e}')

    def _enviar_aceitas_em_thread(self, ss, sp, su, spw, aceitas_hoje, destinatarios):
        """Executa o envio de emails em uma thread separada para não bloquear a UI."""
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
            <tr><td style='padding:6px 0;color:#718096;'>Data Aprovação</td><td style='padding:6px 0;color:#2d3748;'>{data_resp}</td></tr>
    </table>
        <p style='margin:12px 0 0;color:#718096;font-size:12px;'>Anexo: relatório PDF da proposta aprovada.</p>
  </div>
</body></html>"""
                plain = (
                    'Proposta aprovada no dia\n\n'
                    f'Fornecedor: {fornecedor}\n'
                    f'CNPJ: {cnpj}\n'
                    f'Valor a Pagar: {valor}\n'
                    f'Data Pagamento: {data_pgto}\n'
                    f'Data Aprovação: {data_resp}\n'
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
                f'Destinatários: {len(destinatarios)}\n'
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

        # Se houver emails preenchidos no campo da tela de Propostas, usa esses destinatários direto.
        destinatarios_campo = []
        try:
            destinatarios_campo = self._parse_emails_texto(self._v_emails_aceitas_dia.get())
        except ValueError as e:
            messagebox.showwarning('Emails inválidos', str(e))
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
        """Executa o processamento em uma thread separada para não bloquear a UI."""
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
                        text='✅ Geração de propostas concluída com sucesso!', fg=SUCCESS_COLOR))
                    self.root.after(0, lambda: messagebox.showinfo(
                        'Sucesso', f'Propostas geradas em:\n{diretorio}'))
                else:
                    self.root.after(0, lambda: self._status_lbl.config(
                        text='Erro ao gerar propostas.', fg=DANGER_COLOR))
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
        diretorio    = PROPOSTAS_GERADAS_DIR
        taxa_fixa    = self._v_taxa.get().strip()
        enviar_email = self._v_enviar_email.get()

        if not arquivo or not data_pgto:
            messagebox.showwarning('Campos', 'Preencha Arquivo e Data de Pagamento.')
            return
        try:
            datetime.strptime(data_pgto, '%d/%m/%Y')
        except ValueError:
            messagebox.showwarning('Data', 'Data inválida. Use DD/MM/AAAA.')
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
                        'A URL Base atual está em localhost/127.0.0.1.\n\n'
                        'Fornecedores fora da sua máquina NÃO conseguirão responder os botões.\n\n'
                        'Dica: em Configuracoes > Servidor de Respostas, preencha o campo "ngrok Authtoken".\n\n'
                        'URL atual: ' + str(base_url) + msg_tunel + '\n\n'
                        'Deseja continuar mesmo assim?'
                    )
                    if not continuar:
                        return

            # Protecao: evita gerar links de email para dominio que nao eh este servidor de respostas.
            cfg_pos = load_server_config()
            base_url_validar = str(cfg_pos.get('base_url', base_url) or base_url).strip()
            if not _url_respostas_ativa(base_url_validar):
                messagebox.showerror(
                    'URL Base invalida para respostas',
                    'A URL Base configurada nao respondeu no endpoint /status do servidor de respostas.\n\n'
                    'Isso gera botoes de email que abrem em outro servico e retornam erro de proposta nao encontrada.\n\n'
                    f'URL atual: {base_url_validar}\n\n'
                    'Ajuste em Configuracoes > Servidor de Respostas para uma URL que aponte para este app '
                    '(ou mantenha localhost com ngrok ativo) e gere os emails novamente.'
                )
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
        self._stop_envio_automatico()
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

        # DPI fixo e fonte global (aplicados uma única vez no startup)
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

        # Avisar se Flask não instalado
        if not FLASK_AVAILABLE:
            messagebox.showwarning(
                'Flask não instalado',
                'Para ativar os botões de resposta no email, instale o Flask:\n\n'
                'pip install flask\n\n'
                'Sem o Flask, os emails ainda serão enviados com links de texto.'
            )

        # Avisar configuração SMTP
        ss, sp, su, spw = get_smtp_credentials()
        if not all([ss, sp, su, spw]):
            messagebox.showinfo(
                'Configuração SMTP',
                'Acesse "Configurações > SMTP" para configurar o envio de emails.'
            )

        root.mainloop()
    except Exception as e:
        print(f'Erro: {e}')
        traceback.print_exc()
        try:
            messagebox.showerror('Erro Fatal', f'O sistema encontrou um erro inesperado:\n\n{e}')
        except Exception:
            pass

if __name__ == '__main__':
    main()


