# ✅ Checklist de Teste Antes do Deploy

## 1️⃣ Teste Local

- [ ] Aplicação inicia sem erros
- [ ] Interface Tkinter carrega normalmente
- [ ] Botão "Iniciar Servidor" funciona
- [ ] Mensagem "Servidor de respostas iniciado" aparece

## 2️⃣ Configuração

- [ ] Credenciais SMTP configuradas
- [ ] URL base definida (localhost para teste)
- [ ] Arquivo `email_config.json` foi criado

## 3️⃣ Geração de Proposta

- [ ] Carregou arquivo Excel com fornecedores
- [ ] Selecionou fornecedor e configurações
- [ ] PDFs foram gerados
- [ ] Email foi enviado para você (teste)
- [ ] Email contém os 3 botões de resposta

## 4️⃣ Teste de Respostas (Local)

- [ ] Clicou no botão verde (Aceito)
  - [ ] Página apareceu confirmando
  - [ ] Email retornou com prefixo "Aceito"
  
- [ ] Clicou no botão amarelo (Quero Negociar)
  - [ ] Página apareceu confirmando
  - [ ] Email retornou com prefixo "Quero Negociar"
  
- [ ] Clicou no botão vermelho (Não Aceito)
  - [ ] Página apareceu confirmando
  - [ ] Email retornou com prefixo "Não Aceito"

## 5️⃣ Antes de Fazer Deploy

- [ ] Removeu dados sensíveis do Git
  - [ ] `email_config.json` no `.gitignore`
  - [ ] `server_config.json` no `.gitignore`
  - [ ] `propostas.json` no `.gitignore`
  
- [ ] Criou repositório no GitHub
- [ ] `requirements.txt` contém todas as dependências
- [ ] `Procfile` está presente e correto
- [ ] `.gitignore` está configurado
- [ ] Fez commit inicial

## 6️⃣ Após Deploy no Railway

- [ ] Copiou URL pública do Railway
- [ ] Atualizou `server_config.json` com nova URL
- [ ] Enviou nova proposta teste
- [ ] Links no email apontam para Railway (não localhost)
- [ ] Teste dos 3 botões novamente (agora de outro dispositivo)

## 7️⃣ Em Produção

- [ ] Dashboard do Railway mostra "Running"
- [ ] Logs não mostram erros críticos
- [ ] Fornecedores conseguem clicar nos links
- [ ] Emails chegam com prefixos corretos
- [ ] Status das propostas fica "aceito/negociando/recusado"

---

## 🆘 Se Algo Deu Errado

**Erro: Port already in use**
→ Feche outras aplicações usando a porta ou mude em `server_config.json`

**Erro: Module not found**
→ Instale: `pip install -r requirements.txt`

**Email não envia**
→ Valide SMTP em Configurações > Servidor e Emails

**Links não funcionam**
→ Verifique se URL em `server_config.json` está correta

**Railway mostra erro**
→ Acesse Dashboard > Logs para ver mensagens de erro

---

**Tudo passou? 🎉 Seu sistema está pronto para produção!**
