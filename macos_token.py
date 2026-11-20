"""Identidades de tokens expostas pelo Chaves do macOS (CryptoTokenKit)."""
from __future__ import annotations

import offline
from contextlib import contextmanager
from dataclasses import dataclass
from hashlib import sha256

import Security as sec
from LocalAuthentication import LAContext, LACredentialTypeSmartCardPIN
from asn1crypto import x509
from pyhanko.sign.signers import Signer
from pyhanko_certvalidator.registry import SimpleCertificateStore

from signer_core import SigningError, display_name


@dataclass(frozen=True)
class TokenCertificate:
    token_id: str
    der: bytes

    @property
    def short_id(self):
        return sha256(self.der + self.token_id.encode()).hexdigest()[:10].upper()

    @property
    def title(self):
        cert = x509.Certificate.load(self.der)
        name = display_name(cert) or "Titular sem nome"
        return f"{name} · vence em {cert.not_valid_after:%d/%m/%Y}"


def _items(item_class, context, token_id=None):
    query = {
        sec.kSecClass: item_class,
        sec.kSecAttrAccessGroup: sec.kSecAttrAccessGroupToken,
        sec.kSecUseAuthenticationContext: context,
        sec.kSecMatchLimit: sec.kSecMatchLimitAll,
        sec.kSecReturnRef: True,
        sec.kSecReturnAttributes: True,
    }
    if token_id is not None:
        query[sec.kSecAttrTokenID] = token_id
    status, rows = sec.SecItemCopyMatching(query, None)
    if status == sec.errSecItemNotFound:
        return []
    if status != sec.errSecSuccess:
        raise SigningError("O macOS não conseguiu consultar os certificados do token.")
    return rows


def _identities(context, token_id=None):
    for row in _items(sec.kSecClassIdentity, context, token_id):
        token = row.get(sec.kSecAttrTokenID)
        if not token or not row.get(sec.kSecAttrCanSign, True):
            continue
        identity = row[sec.kSecValueRef]
        status, ref = sec.SecIdentityCopyCertificate(identity, None)
        if status != sec.errSecSuccess:
            continue
        der = bytes(sec.SecCertificateCopyData(ref))
        cert = x509.Certificate.load(der)
        usage = cert.key_usage_value
        if cert.ca or (usage is not None and not usage.native.intersection(
            {"digital_signature", "non_repudiation"}
        )):
            continue
        if cert.public_key.algorithm in ("rsa", "ec"):
            yield TokenCertificate(str(token), der), identity


def discover_tokens():
    context = LAContext.new()
    context.setInteractionNotAllowed_(True)
    try:
        return sorted({item for item, _ in _identities(context)}, key=lambda c: (c.title, c.der, c.token_id))
    finally:
        context.invalidate()


class MacTokenSigner(Signer):
    def __init__(self, cert, key, chain):
        super().__init__(signing_cert=cert, cert_registry=SimpleCertificateStore.from_certs(chain))
        self._key = key
        self._failed = False

    async def async_sign_raw(self, data, digest_algorithm, dry_run=False):
        if digest_algorithm.lower() != "sha256":
            raise SigningError("O assinador de token requer SHA-256.")
        if dry_run:
            size = self.signing_cert.public_key.byte_size
            return bytes(size if self.signing_cert.public_key.algorithm == "rsa" else 2 * size + 10)
        if self._failed:
            raise SigningError("Autorização do token interrompida neste lote.")
        # Uma falha do dispositivo deve interromper novas tentativas de PIN no lote.
        self._failed = True
        algorithm = (sec.kSecKeyAlgorithmRSASignatureMessagePKCS1v15SHA256
                     if self.signing_cert.public_key.algorithm == "rsa"
                     else sec.kSecKeyAlgorithmECDSASignatureMessageX962SHA256)
        signature, _ = sec.SecKeyCreateSignature(self._key, algorithm, data, None)
        if signature is None:
            raise SigningError("O token não autorizou a assinatura. Confira a conexão e o estado do PIN no programa do fabricante.")
        self._failed = False
        return bytes(signature)


@contextmanager
def open_mac_token(selected: TokenCertificate, pin: str):
    if not pin:
        raise SigningError("Digite o PIN do token selecionado.")
    context = LAContext.new()
    context.setInteractionNotAllowed_(True)
    try:
        # A consulta pública reconfirma o cartão e o certificado antes de usar o PIN.
        for item, identity in _identities(context, selected.token_id):
            if item == selected:
                break
        else:
            raise SigningError("O certificado selecionado saiu do Mac. Atualize a lista de tokens.")
        if not context.setCredential_type_(pin.encode("utf-8"), LACredentialTypeSmartCardPIN):
            raise SigningError("O macOS não conseguiu receber o PIN do token.")
        status, key = sec.SecIdentityCopyPrivateKey(identity, None)
        if status != sec.errSecSuccess:
            raise SigningError("O macOS não liberou a chave do token selecionado.")
        chain = []
        for row in _items(sec.kSecClassCertificate, context, selected.token_id):
            cert = x509.Certificate.load(bytes(sec.SecCertificateCopyData(row[sec.kSecValueRef])))
            if cert.ca:
                chain.append(cert)
        yield MacTokenSigner(x509.Certificate.load(selected.der), key, chain)
    finally:
        context.invalidate()
