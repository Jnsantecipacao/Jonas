# 🚀 Quick Start – Deploy em 5 Minutos

## Pré-requisitos
- [ ] Conta GitHub
- [ ] Conta Railway (railway.app)
- [ ] Repositório Git iniciado localmente

---

## ⚡ Passo 1: Preparar Repositório (2 min)

```bash
cd Desktop/Projetinho
git add .
git commit -m "Pronto para produção"
git push origin main
```

---

## ⚡ Passo 2: Criar Repo no GitHub (1 min)

1. Acesse https://github.com/new
2. Nome: `mercadao-antecipacao`
3. Privado ou público (sua escolha)
4. Copie a URL do repositório

```bash
git remote add origin https://github.com/SEU_USER/mercadao-antecipacao.git
git branch -M main
git push -u origin main
```

---

## ⚡ Passo 3: Deploy no Railway (2 min)

1. Acesse https://railway.app
2. Login com GitHub
3. Clique **"+ New"** > **"GitHub Repo"**
4. Selecione `mercadao-antecipacao`
5. Clique **"Deploy"**
6. Aguarde 2-3 minutos

**Pronto! Você receberá uma URL como:**
```
https://mercadao-antecipacao-prod-xyz.railway.app
```

---

## ⚡ Passo 4: Configurar Variáveis (1 min)

No dashboard do Railway:

1. Clique no seu projeto
2. Vá para **"Variables"**
3. Adicione:
   ```
   RAILWAY_URL = https://mercadao-antecipacao-prod-xyz.railway.app
   ANTECIPACAO_SMTP_PASSWORD = sua_senha_aqui
   ```

---

## ⚡ Passo 5: Atualizar URL Local

Atualize `server_config.json` com a URL do Railway:

```json
{
  "base_url": "https://mercadao-antecipacao-prod-xyz.railway.app",
  "port": 5000
}
```

Faça commit:
```bash
git add server_config.json
git commit -m "Atualizar URL de produção"
git push
```

Railway fará **redeploy automático!**

---

## ✅ Teste Agora!

1. Gere uma proposta
2. Fornecedor recebe email
3. Clique em qualquer botão
4. Página deve carregar normalmente
5. Email deve retornar com prefixo

---

## 📊 Monitorar

- Dashboard do Railway: https://railway.app/dashboard
- Logs em tempo real: Project > Deployments > Logs
- Status do servidor: https://seu-url/status

---

## 💾 Fazer Update do Código

Sempre que fizer mudanças locais:

```bash
git add .
git commit -m "Descrição das mudanças"
git push origin main
```

Railway fará redeploy automaticamente em 1-2 minutos!

---

## 🆘 Dúvidas Comuns

**P: Por quanto tempo posso manter rodando?**
R: Railway oferece 500 horas/mês grátis. Seu app roda ~40 dias contínuos.

**P: Vai cobrar depois?**
R: Só depois de gastar $5/mês em recursos (você terá aviso).

**P: Preciso deixar meu PC ligado?**
R: Não! Railway roda 24/7 mesmo que seu PC esteja desligado.

**P: E se der erro?**
R: Verifique Logs no Railway dashboard.

---

**🎉 Pronto! Seus fornecedores já podem responder de qualquer lugar!**
