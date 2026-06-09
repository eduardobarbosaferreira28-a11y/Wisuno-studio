import sys, os, json, re
from pathlib import Path
sys.path.insert(0, '.')
from config import ANTHROPIC_API_KEY, ANTHROPIC_MODEL
import anthropic

try:
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    response = client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=300,
        temperature=0.7,
        system='Test system',
        messages=[{'role': 'user', 'content': 'Test output json format: {"title":"test","caption":"test","hashtags":["test"]}'}]
    )
    Path('anthropic_out.txt').write_text(response.content[0].text, encoding='utf-8')
    print('SUCCESS')
except Exception as e:
    print('ERROR:', e.__class__.__name__, str(e))
