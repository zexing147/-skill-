import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "scripts" / "scan_xianyu.py"

def run(text):
    out = subprocess.check_output([sys.executable, str(SCRIPT), "--text", text], text=True)
    return json.loads(out)

def test_does_not_match_single_character_inside_operation():
    assert run("按步骤操作即可")['matched'] is False

def test_matches_copyright_term():
    result = run("提供PDF电子书")
    assert any(hit['word'] == '电子书' and hit['category'] == '平台盗版违规词' for hit in result['hits'])
