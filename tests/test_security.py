"""Quick test that bcrypt direct usage works."""
from app.core.security import hash_password, verify_password

h = hash_password("test1234")
print("hash OK:", h[:20] + "...")

ok = verify_password("test1234", h)
print("verify correct:", ok)

wrong = verify_password("wrongval", h)
print("verify wrong:", wrong)

assert ok is True
assert wrong is False
print("All checks passed ✅")
