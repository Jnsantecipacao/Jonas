import re
import requests

base = 'https://jonas-pyjf.onrender.com'

resp = requests.post(base + '/propostas', json={
    'numero_proposta': 'CHECK-CHAT-001',
    'fornecedor': 'Fornecedor Teste',
    'valor': 10000.0,
    'data_proposta': '29/04/2026',
    'taxa_desconto': 9.0,
})
resp.raise_for_status()
data = resp.json()
url = data['link']

page = requests.get(url, timeout=20)
page.raise_for_status()
html = page.text

print('URL:', url)
print('Tem taxa 9%:', '9.0%' in html or '9%' in html)
print('Tem taxa sugerida 7%:', '7.0%' in html or '7%' in html)
print('Tem data-negotiation-suggestion:', 'data-negotiation-suggestion=' in html)
print('Tem texto Quero Negociar:', 'Quero Negociar' in html)
match = re.search(r'data-negotiation-suggestion="([^"]+)"', html)
print('Sugestao:', match.group(1) if match else 'NAO_ENCONTRADA')
