from pathlib import Path
path = Path('Antecipacao_v2.py')
text = path.read_text(encoding='utf-8')
markers = ('Ã', 'â', 'ð', 'ï', 'œ', 'š')
changed = []
for i, line in enumerate(text.splitlines(), 1):
    if any(m in line for m in markers):
        try:
            fixed = line.encode('latin1').decode('utf-8')
        except Exception:
            continue
        if fixed != line:
            changed.append((i, fixed))
print('changed_lines=', len(changed))
for i, fixed in changed[:60]:
    print(f'{i}: {fixed}')
