# 🚀 Guia de Deploy – Railway.app

## Passo 1: Criar Conta no Railway

1. Acesse [railway.app](https://railway.app)
2. Clique em **"Start Project"**
3. Faça login com GitHub, Google ou Email
4. Crie uma nova conta se necessário

---

## Passo 2: Preparar Repositório Git

### 2.1 – Inicializar Git (se ainda não fez)
```bash
cd C:\Users\Jonas Financeiro\Desktop\Projetinho
git init
git add .
git commit -m "Initial commit - Mercadão Atacadista"
```

### 2.2 – Criar repositório no GitHub
1. Acesse [github.com/new](https://github.com/new)
2. Crie um repositório chamado `mercadao-antecipacao`
3. Não inicialize com README (vamos usar o nosso)
4. Copie o código do repositório

### 2.3 – Fazer Push para GitHub
```bash
git remote add origin https://github.com/SEU_USUARIO/mercadao-antecipacao.git
git branch -M main
git push -u origin main
```

---

## Passo 3: Deploy no Railway

### 3.1 – Conectar GitHub ao Railway
1. No dashboard do Railway, clique em **"+ New"**
2. Selecione **"GitHub Repo"**
3. Authorize Railway a acessar seu GitHub
4. Selecione `mercadao-antecipacao`
5. Clique em **Deploy**

### 3.2 – Aguardar Build
- Railway irá:
  - Instalar Python
  - Rodar `pip install -r requirements.txt`
  - Iniciar o servidor conforme `Procfile`

### 3.3 – Configurar Variáveis de Ambiente
1. No dashboard, clique no seu projeto
2. Vá para a aba **"Variables"**
3. Adicione as variáveis de ambiente:

```
RAILWAY_ENVIRONMENT=production
ANTECIPACAO_SMTP_PASSWORD=SUA_SENHA_AQUI
```

---

## Passo 4: Obter URL Pública

1. No dashboard do Railway, acesse seu projeto
2. Vá para aba **"Deployments"**
3. Clique no deployment ativo
4. Procure por **"Service URL"** ou similar
5. Você terá uma URL como: `https://seu-projeto-randomid.railway.app`

---

## Passo 5: Atualizar a URL Base no Código

### 5.1 – Modificar `server_config.json` manualmente OU

Copie a URL do Railway e atualize:

```json
{
  "base_url": "https://seu-projeto-randomid.railway.app",
  "port": 5000
}
```

### 5.2 – OU deixar automático via variável de ambiente

O código agora detecta automaticamente a URL:
```python
base_url = os.getenv('RAILWAY_URL', 'http://localhost:5001')
```

---

## Passo 6: Testar os Links de Resposta

1. Gere uma proposta normalmente (verde, amarelo, vermelho)
2. Copie um dos links de resposta
3. Substitua `http://localhost:5001` pela sua URL do Railway
4. Teste em outro dispositivo ou navegador incógnito

**Exemplo:**
- Antes: `http://localhost:5001/resposta/abc123/aceito`
- Depois: `https://seu-projeto-randomid.railway.app/resposta/abc123/aceito`

---

## Passo 7: Verificar Logs

Se algo der errado:
1. No Railway, acesse **"Deployments"**
2. Clique no deployment
3. Vá para **"Logs"**
4. Procure por mensagens de erro

---

## 🔑 Checklist Final

- [ ] Repositório Git criado no GitHub
- [ ] Arquivos: `requirements.txt` e `Procfile` presentes
- [ ] Repository conectado ao Railway
- [ ] Build concluído com sucesso
- [ ] URL pública obtida
- [ ] `server_config.json` atualizado com URL do Railway
- [ ] Teste de email funcionando
- [ ] Links de resposta (verde/amarelo/vermelho) funcionam

---

## 📞 Troubleshooting

### ❌ "Port already in use"
- Railway atribui porta automaticamente via `PORT` env var
- O código já lida com isso

### ❌ "Module not found"
- Verifique se `requirements.txt` está na pasta raiz
- Certifique-se que todos os pacotes estão listados

### ❌ "Email não enviado"
- Verifique credenciais SMTP em `email_config.json`
- Confira variável `ANTECIPACAO_SMTP_PASSWORD`

### ❌ "Fornecedor recebe erro 404"
- URL no email ainda aponta para `localhost`
- Atualize `server_config.json` com URL do Railway

---

## 💡 Dicas

1. **Versão gratuita Railway**: 500 horas/mês de execução (suficiente!)
2. **SSL automático**: Railway oferece HTTPS gratuitamente
3. **Monitoramento**: Dashboard mostra CPU, memória, requisições
4. **Rollback fácil**: Pode fazer deploy antigoas versões instantaneamente
5. **Variáveis secretas**: Nunca coloque senhas no Git, use Railway Variables

---

**Pronto! Sua aplicação estará online 24/7** 🎉
