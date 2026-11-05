"""Offline MCP registration check: does not call the gateway or sign payment."""
import ast, os

SERVER = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'neurodynamic_mcp', 'server.py')

EXPECTED = {'catalogue','quote','purchase_json','transcribe_file','transcript_package_file','extract_pdf_file','ocr_image_file','payment_status','budget_status'}

def main():
    tree = ast.parse(open(SERVER, encoding='utf-8').read())
    names = {n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and any(isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute) and d.func.attr == 'tool' for d in n.decorator_list)}
    assert names == EXPECTED, (names, EXPECTED)
    print('offline tools/list OK:', ','.join(sorted(names)))

if __name__ == '__main__': main()
