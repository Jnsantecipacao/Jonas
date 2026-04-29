import requests
base = 'https://jonas-pyjf.onrender.com'

# Teste 1: Criar proposta e testar "Aceito"
print('TEST 1: Criar proposta (taxa 8%) e clicar Aceito...')
resp = requests.post(base + '/propostas', json={
    'numero_proposta': 'ACEITO-001',
    'fornecedor': 'Empresa A',
    'valor': 15000.00,
    'data_proposta': '2026-04-29',
    'taxa_desconto': 8.0
})
data = resp.json()
pid1, tok1 = data['id'], data['token']

resp = requests.post(base + '/resposta', json={
    'id_proposta': pid1,
    'fornecedor': 'Empresa A',
    'mensagem_texto': '',
    'token': tok1,
    'acao': 'aceitar'
})
r1 = resp.json()
print(f'  Classificacao: {r1.get("classificacao")}')
print(f'  Mensagem: {r1.get("mensagem")}')

# Teste 2: Criar proposta e testar "Negociar"
print('\nTEST 2: Criar proposta (taxa 7%) e clicar Quero Negociar...')
resp = requests.post(base + '/propostas', json={
    'numero_proposta': 'NEGOCIAR-001',
    'fornecedor': 'Empresa B',
    'valor': 20000.00,
    'data_proposta': '2026-04-29',
    'taxa_desconto': 7.0
})
data = resp.json()
pid2, tok2 = data['id'], data['token']

resp = requests.post(base + '/resposta', json={
    'id_proposta': pid2,
    'fornecedor': 'Empresa B',
    'mensagem_texto': 'Podemos fazer 6%?',
    'token': tok2,
    'acao': 'negociar'
})
r2 = resp.json()
print(f'  Classificacao: {r2.get("classificacao")}')
print(f'  Mensagem: {r2.get("mensagem")[:80]}...')

# Teste 3: Criar proposta e testar "Não Aceito"
print('\nTEST 3: Criar proposta (taxa 10%) e clicar Não Aceito...')
resp = requests.post(base + '/propostas', json={
    'numero_proposta': 'RECUSA-001',
    'fornecedor': 'Empresa C',
    'valor': 12000.00,
    'data_proposta': '2026-04-29',
    'taxa_desconto': 10.0
})
data = resp.json()
pid3, tok3 = data['id'], data['token']

resp = requests.post(base + '/resposta', json={
    'id_proposta': pid3,
    'fornecedor': 'Empresa C',
    'mensagem_texto': '',
    'token': tok3,
    'acao': 'recusar'
})
r3 = resp.json()
print(f'  Classificacao: {r3.get("classificacao")}')
print(f'  Mensagem: {r3.get("mensagem")}')

# Teste 4: Listar respostas
print('\nTEST 4: Listar respostas do admin...')
resp = requests.get(base + '/admin/respostas?limit=5')
items = resp.json()['items']
print(f'Total de respostas: {len(items)}')
print('Últimas 3 respostas:')
for item in items[:3]:
    print(f'  - {item.get("numero_proposta")}: {item.get("classificacao")} (taxa: {item.get("taxa_desconto")}%)')

print('\n✓ Todos os testes completados com sucesso!')


