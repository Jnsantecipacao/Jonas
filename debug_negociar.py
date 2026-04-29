import requests
import traceback

base = 'https://jonas-pyjf.onrender.com'

try:
    # Criar proposta
    print('Criando proposta...')
    resp = requests.post(base + '/propostas', json={
        'numero_proposta': 'DEBUG-001',
        'fornecedor': 'Debug',
        'valor': 5000,
        'data_proposta': '2026-04-29',
        'taxa_desconto': 10.0
    })
    print(f'POST /propostas: {resp.status_code}')
    
    if resp.status_code != 200:
        print(f'Erro: {resp.text}')
        exit(1)
    
    data = resp.json()
    pid = data['id']
    tok = data['token']
    print(f'Proposta: ID={pid}, Token={tok[:10]}')
    
    # Testar negociar
    print('\nTestando negociar...')
    payload = {
        'id_proposta': pid,
        'fornecedor': 'Debug',
        'mensagem_texto': 'Teste',
        'token': tok,
        'acao': 'negociar'
    }
    print(f'Payload: {payload}')
    
    resp = requests.post(base + '/resposta', json=payload)
    print(f'POST /resposta: {resp.status_code}')
    print(f'Headers: {dict(resp.headers)}')
    print(f'Body (first 500 chars): {resp.text[:500]}')
    
    if resp.status_code == 200:
        result = resp.json()
        print(f'Success: {result}')
    else:
        print(f'Error: {resp.text}')
        
except Exception as e:
    print(f'Exception: {e}')
    traceback.print_exc()
