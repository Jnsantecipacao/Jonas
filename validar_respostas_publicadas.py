import requests

base = 'https://jonas-pyjf.onrender.com'

def criar_proposta(numero, taxa):
    resp = requests.post(base + '/propostas', json={
        'numero_proposta': numero,
        'fornecedor': 'Fornecedor Teste',
        'valor': 10000.0,
        'data_proposta': '29/04/2026',
        'taxa_desconto': taxa,
    }, timeout=20)
    resp.raise_for_status()
    return resp.json()

# aceitar
aceite = criar_proposta('VAL-ACEITE-001', 8.0)
resp_aceite = requests.post(base + '/resposta', json={
    'id_proposta': aceite['id'],
    'fornecedor': 'Fornecedor Teste',
    'mensagem_texto': '',
    'token': aceite['token'],
    'acao': 'aceitar',
}, timeout=20)
resp_aceite.raise_for_status()

# recusar
recusa = criar_proposta('VAL-RECUSA-001', 10.0)
resp_recusa = requests.post(base + '/resposta', json={
    'id_proposta': recusa['id'],
    'fornecedor': 'Fornecedor Teste',
    'mensagem_texto': '',
    'token': recusa['token'],
    'acao': 'recusar',
}, timeout=20)
resp_recusa.raise_for_status()

# html chat
neg = criar_proposta('VAL-CHAT-001', 9.0)
html = requests.get(neg['link'], timeout=20).text

print('mensagem aceite:', resp_aceite.json().get('mensagem'))
print('mensagem recusa:', resp_recusa.json().get('mensagem'))
print('tem saudacao nova:', 'Sou o assistente virtual responsável pela negociação desta proposta' in html)
print('tem atributo sugestao:', 'data-negotiation-suggestion=' in html)
print('tem sugestao 7%:', '7.0%' in html or '7%' in html)
