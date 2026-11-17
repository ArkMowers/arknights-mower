"""Verify packaged cryptographic capabilities without loading user configuration."""


def check_credential_crypto():
    from cryptography.exceptions import InvalidTag
    from cryptography.hazmat.decrepit.ciphers.algorithms import TripleDES
    from cryptography.hazmat.primitives import hpke
    from cryptography.hazmat.primitives.asymmetric import mlkem, padding, rsa, x25519
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    mlkem_key = mlkem.MLKEM768PrivateKey.generate()
    seed = mlkem_key.private_bytes_raw()
    assert len(seed) == 64
    restored = mlkem.MLKEM768PrivateKey.from_seed_bytes(seed)
    assert (
        restored.public_key().public_bytes_raw()
        == mlkem_key.public_key().public_bytes_raw()
    )
    classical_key = x25519.X25519PrivateKey.generate()
    private_bytes = seed + classical_key.private_bytes_raw()
    assert len(private_bytes) == 96
    recipient = hpke.MLKEM768X25519PrivateKey(
        mlkem.MLKEM768PrivateKey.from_seed_bytes(private_bytes[:64]),
        x25519.X25519PrivateKey.from_private_bytes(private_bytes[64:]),
    )
    suite = hpke.Suite(
        hpke.KEM.MLKEM768_X25519, hpke.KDF.HKDF_SHA256, hpke.AEAD.AES_256_GCM
    )
    plaintext = b"synthetic-build-credential"
    context = b"arknights-mower-credential-build-check"
    ciphertext = suite.encrypt(plaintext, recipient.public_key(), info=context)
    assert suite.decrypt(ciphertext, recipient, info=context) == plaintext
    next_ciphertext = suite.encrypt(plaintext, recipient.public_key(), info=context)
    assert next_ciphertext != ciphertext
    assert suite.decrypt(next_ciphertext, recipient, info=context) == plaintext
    for position in (0, len(ciphertext) - 1):
        damaged = bytearray(ciphertext)
        damaged[position] ^= 1
        try:
            suite.decrypt(bytes(damaged), recipient, info=context)
        except InvalidTag:
            pass
        else:
            raise AssertionError("Credential ciphertext modification was accepted")
    try:
        suite.decrypt(ciphertext, recipient, info=b"incorrect-context")
    except InvalidTag:
        pass
    else:
        raise AssertionError("Credential ciphertext context was not authenticated")

    # SecuritySm's upstream protocol still uses these primitives.
    block = b"synthetic-block!"
    for cipher in (
        Cipher(TripleDES(b"test-key" * 3), modes.ECB()),
        Cipher(algorithms.AES(b"test-key-for-aes"), modes.CBC(b"0123456789abcdef")),
    ):
        encryptor = cipher.encryptor()
        encrypted = encryptor.update(block) + encryptor.finalize()
        decryptor = cipher.decryptor()
        assert decryptor.update(encrypted) + decryptor.finalize() == block
    rsa_key = rsa.generate_private_key(public_exponent=65537, key_size=1024)
    encrypted = rsa_key.public_key().encrypt(b"synthetic-device-id", padding.PKCS1v15())
    assert rsa_key.decrypt(encrypted, padding.PKCS1v15()) == b"synthetic-device-id"
    print("Credential crypto check passed: X-Wing / HKDF-SHA256 / AES-256-GCM")


if __name__ == "__main__":
    check_credential_crypto()
