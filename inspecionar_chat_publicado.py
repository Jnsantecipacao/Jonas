import requests

base = 'https://jonas-pyjf.onrender.com'
resp = requests.post(base + '/propostas', json={
    'numero_proposta': 'CHECK-CHAT-002',
    'fornecedor': 'Fornecedor Teste',
    'valor': 10000.0,
    'data_proposta': '29/04/2026',
    'taxa_desconto': 9.0,
})
resp.raise_for_status()
url = resp.json()['link']
html = requests.get(url, timeout=20).text

for line in html.splitlines()[:120]:
    if 'chatBox' in line or 'bubble bot' in line or 'Quero Negociar' in line or 'data-negotiation' in line or 'textarea' in line:
        print(line)
