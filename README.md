# 🛒 Mercadão Atacadista – Mesa de Antecipação

Sistema de antecipação de pagamentos com interface Tkinter, geração de PDFs e servidor Flask para processamento de respostas via email.

## 📋 Funcionalidades

- ✅ **Geração de Propostas**: Cria PDFs com dados de fornecedores
- ✅ **Email Automático**: Envia propostas com links de resposta
- ✅ **Sistema de Respostas**: Fornecedores clicam verde/amarelo/vermelho
- ✅ **Rastreamento**: Registra status de cada proposta
- ✅ **Relatórios**: Gera aceites e resumos

## 🚀 Deployment

### Local (Desenvolvimento)
```bash
python Antecipacao_v2.py
```

### Produção (Railway)
Ver [DEPLOY_RAILWAY.md](DEPLOY_RAILWAY.md) para instruções completas.

**URL de Produção:** `https://seu-projeto.railway.app`

## 📦 Instalação

```bash
pip install -r requirements.txt
```

### Dependências
- pandas: Manipulação de dados
- openpyxl: Leitura de Excel
- fpdf2: Geração de PDFs
- Pillow: Manipulação de imagens
- matplotlib: Gráficos
- flask: Servidor web para respostas

## ⚙️ Configuração

### Email SMTP
1. Abra a aplicação
2. Vá para **Configurações > Servidor e Emails**
3. Preencha:
   - Servidor SMTP
   - Porta SMTP
   - Usuário
   - Senha

### URL Base do Servidor
- **Desenvolvimento**: `http://localhost:5001`
- **Produção**: Detectada automaticamente do Railway

## 📧 Fluxo de Email

```
1. Você gera proposta → PDF + Email enviado
2. Fornecedor recebe email com 3 botões
3. Clica em um dos botões → Link para seu servidor
4. Servidor processa resposta → Email retorna para você
5. Status atualizado no sistema
```

## 🔗 Endpoints

- `GET /resposta/<token>/aceito` - Fornecedor aceita proposta
- `GET /resposta/<token>/negociar` - Fornecedor quer negociar
- `GET /resposta/<token>/recusar` - Fornecedor recusa proposta
- `GET /status` - Verifica saúde do servidor

## 📁 Estrutura de Arquivos

```
Antecipacao_v2.py           # Aplicação principal
requirements.txt            # Dependências Python
Procfile                    # Configuração Railway
DEPLOY_RAILWAY.md           # Guia de deployment
email_config.json           # Credenciais SMTP (não commitar)
server_config.json          # Configuração servidor (não commitar)
propostas.json              # Registro de propostas (não commitar)
Propostas_Aceitas/          # PDFs de aceites
```

## 🔐 Variáveis de Ambiente

Em produção (Railway), configure:
- `RAILWAY_URL`: URL pública da aplicação (automática)
- `PORT`: Porta do servidor (automática, padrão 5000)
- `ANTECIPACAO_SMTP_PASSWORD`: Senha SMTP

## 🧪 Teste Local

1. Inicie a aplicação
2. Configure SMTP
3. Crie uma proposta teste
4. Clique nos links de resposta em `http://localhost:5001`

## 📞 Troubleshooting

### Email não envia
- Verifique credenciais SMTP
- Confira `email_config.json`
- Alguns servidores SMTP precisam de app-specific password

### Links não funcionam
- Em produção, confira URL em `server_config.json`
- Certifique-se que servidor está rodando

### Porta já em uso
- Desenvolviimento: Mude `port` em `server_config.json`
- Produção: Railway atribui automaticamente

## 📝 Licença

Interno - Mercadão Atacadista

---

**Precisa hospedar?** Ver [DEPLOY_RAILWAY.md](DEPLOY_RAILWAY.md)
