"""Red–Blue 실검증: 샌드박스에서 수정 전/후 공격을 실제로 실행해 '정말 고쳐졌는지' 확인."""
from .schemas import AttackSpec, Patch, VerifyRequest, VerifyResult
from .verifier import verify

__all__ = ["AttackSpec", "Patch", "VerifyRequest", "VerifyResult", "verify"]
