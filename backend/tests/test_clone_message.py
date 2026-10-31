"""없는 저장소를 넣으면 git 원문 대신 사용자 문장을 보여 줍니다 (#147)."""
from app.routers.scans import clone_message


def test_missing_or_private_repository():
    raw = "git clone 실패: remote: Repository not found.\nfatal: repository 'https://github.com/a/nope/' not found (비공개 저장소이거나 주소가 틀렸을 수 있습니다)"
    assert clone_message(raw) == "저장소를 찾을 수 없습니다. 주소가 맞는지, 공개 저장소인지 확인해 주세요."
    assert "fatal" not in clone_message("git clone 실패: fatal: could not read Username for 'https://github.com'")


def test_network_and_other_failures():
    assert clone_message("git clone 실패: fatal: unable to access 'https://github.com/a/b/': Could not resolve host").startswith("GitHub에 연결하지")
    assert clone_message("git clone 실패: error: something else").startswith("저장소를 받지 못했습니다")


def test_engine_korean_messages_kept():
    assert clone_message("120초 안에 저장소를 받지 못했습니다.") == "120초 안에 저장소를 받지 못했습니다."
