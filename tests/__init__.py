import os
from pathlib import Path

# 운영자 전용 패턴 대신 테스트용 예시 패턴을 쓴다(collector.privacy가 import 때 읽음).
os.environ["GONGMO_PRIVATE_DIR"] = str(Path(__file__).resolve().parent / "fixtures" / "operator-example")
