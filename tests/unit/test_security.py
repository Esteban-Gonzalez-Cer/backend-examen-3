from app.core.security import TokenCipher, hash_token, new_refresh_token


def test_cipher_roundtrip_and_wrong_key():
    token = "eyJhbGciOi.payload.signature"
    encrypted = TokenCipher("server-secret").encrypt(token)
    assert token not in encrypted
    assert TokenCipher("server-secret").decrypt(encrypted) == token
    assert TokenCipher("another-secret").decrypt(encrypted) is None
    assert TokenCipher("server-secret").decrypt("garbage") is None


def test_refresh_tokens_are_random_and_hashed():
    a, b = new_refresh_token(), new_refresh_token()
    assert a != b and len(a) >= 40
    assert hash_token(a) != a and len(hash_token(a)) == 64
