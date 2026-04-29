import re
import requests

base = 'https://jonas-pyjf.onrender.com'
resp = requests.post(base + '/propostas', json={
    'numero_proposta': 'VALIDA-CHAT-003',
    'fornecedor': 'Fornecedor Teste',
    'valor': 10000.0,
    'data_proposta': '29/04/2026',
    'taxa_desconto': 9.0,
})
resp.raise_for_status()
url = resp.json()['link']
html = requests.get(url, timeout=20).text

checks = {
    'tem saudacao nova': 'Sou o assistente virtual responsável pela negociação desta proposta' in html,
    'tem atributo sugestao': 'data-negotiation-suggestion=' in html,
    'tem taxa atual 9': '9.0%' in html or '9%' in html,
    'tem taxa sugerida 7': '7.0%' in html or '7%' in html,
    'tem botao negociar': 'Quero Negociar' in html,
}

print('URL:', url)
for chave, valor in checks.items():
    print(f'{chave}: {valor}')

match = re.search(r'data-negotiation-suggestion="([^"]+)"', html)
print('sugestao extraida:', match.group(1) if match else 'NAO_ENCONTRADA')
