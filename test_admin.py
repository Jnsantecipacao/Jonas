import requests

# Criar nova proposta
print('Criando nova proposta...')
resp = requests.post('https://jonas-pyjf.onrender.com/propostas', json={
    'numero_proposta': 'FINAL-TEST-001',
    'fornecedor': 'Empresa Final',
    'valor': 25000,
    'data_proposta': '2026-04-29',
    'taxa_desconto': 9.5
})
data = resp.json()
pid, tok = data['id'], data['token']
print(f'Proposta criada: ID={pid}')

# Responder com negociar
print('Respondendo com negociar...')
resp = requests.post('https://jonas-pyjf.onrender.com/resposta', json={
    'id_proposta': pid,
    'fornecedor': 'Empresa Final',
    'mensagem_texto': 'Podemos negociar',
    'token': tok,
    'acao': 'negociar'
})
print(f'Resposta registrada')

# Listar admin
print('\nListando respostas admin (últimas 3)...')
resp = requests.get('https://jonas-pyjf.onrender.com/admin/respostas?limit=3')
if resp.status_code == 200:
    items = resp.json()['items']
    for i, item in enumerate(items):
        num = item.get("numero_proposta")
        class_ = item.get("classificacao")
        taxa = item.get("taxa_desconto")
        print(f'{i+1}. {num}: {class_} (Taxa: {taxa}%)')

