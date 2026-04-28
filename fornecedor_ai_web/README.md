# Sistema Web de Respostas com IA

Modulo web para coletar resposta de fornecedores por URL publica, classificar com IA e salvar no SQLite.

## Stack

- FastAPI
- SQLite
- Frontend chat (HTML/CSS/JS)
- OpenAI (opcional) + fallback local

## Endpoints

- GET /resposta?id=<id_proposta>&token=<token>
- POST /resposta
- POST /propostas (gera proposta e link)
- GET /admin/respostas
- GET /health

## Requisitos

- Python 3.10+
- OPENAI_API_KEY (opcional, recomendado)

## Rodar local

```bash
cd fornecedor_ai_web
pip install -r ..\requirements.txt
uvicorn app:app --host 0.0.0.0 --port 8000 --reload
```

## Criar proposta e gerar link unico

```bash
curl -X POST http://localhost:8000/propostas \
  -H "Content-Type: application/json" \
  -d "{\"numero_proposta\":\"PC-2026-001\",\"fornecedor\":\"Fornecedor XPTO\",\"valor\":12500.90,\"data_proposta\":\"28/04/2026\"}"
```

Retorno inclui link no formato:

https://sistema.onrender.com/resposta?id=123&token=abc456

## Deploy Render

Build command:

```bash
pip install -r requirements.txt
```

Start command:

```bash
uvicorn fornecedor_ai_web.app:app --host 0.0.0.0 --port $PORT
```

Variaveis sugeridas:

- OPENAI_API_KEY=...
- OPENAI_MODEL=gpt-4o-mini
- PUBLIC_BASE_URL=https://seu-app.onrender.com

## Seguranca aplicada

- Token unico por proposta
- Validacao de token no GET e POST
- Bloqueio de multiplas respostas (responded=1)
