"""Exercise real HTTPS handshakes with a test-only CA, never a user's trust store."""
import ssl
import threading
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
import truststore
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
from fastapi import HTTPException

from backend import tls
from backend.ai import ChatGPT


def certificate(key, subject, issuer, issuer_key, start, end, ca=False, host='localhost'):
    builder=(x509.CertificateBuilder().subject_name(subject).issuer_name(issuer)
        .public_key(key.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(start).not_valid_after(end)
        .add_extension(x509.BasicConstraints(ca=ca,path_length=None),critical=True)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()),critical=False)
        .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(issuer_key.public_key()),critical=False)
        .add_extension(x509.KeyUsage(digital_signature=True,content_commitment=False,
            key_encipherment=not ca,data_encipherment=False,key_agreement=False,
            key_cert_sign=ca,crl_sign=ca,encipher_only=False,decipher_only=False),critical=True))
    if not ca:
        builder=(builder.add_extension(x509.SubjectAlternativeName([x509.DNSName(host)]),critical=False)
            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]),critical=False))
    return builder.sign(issuer_key,hashes.SHA256())


@pytest.mark.parametrize('native',[False,True],ids=['stdlib','truststore'])
@pytest.mark.parametrize('case',['trusted','untrusted','wrong-host','expired'])
def test_https_verification_accepts_only_trusted_current_matching_certificate(tmp_path,monkeypatch,native,case):
    # This selects the production Windows factory branch, but truststore itself
    # uses the host OS backend. Linux results do not verify Windows CryptoAPI.
    monkeypatch.setattr(tls,'WINDOWS',native)
    context=tls.client_context()
    assert context.verify_mode==ssl.CERT_REQUIRED and context.check_hostname
    if native:assert isinstance(context,truststore.SSLContext)
    now=datetime.now(timezone.utc)
    ca_key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    ca_name=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'Ephemeral test CA')])
    ca=certificate(ca_key,ca_name,ca_name,ca_key,now-timedelta(days=2),now+timedelta(days=1),ca=True)
    key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    name=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'Local test server')])
    cert=certificate(key,name,ca_name,ca_key,now-timedelta(days=2),
        now+timedelta(days=-1 if case=='expired' else 1),
        host='wrong.example.invalid' if case=='wrong-host' else 'localhost')
    certfile=tmp_path/'cert.pem';keyfile=tmp_path/'key.pem'
    certfile.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    keyfile.write_bytes(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
    if case!='untrusted':
        context.load_verify_locations(cadata=ca.public_bytes(serialization.Encoding.PEM).decode())
    monkeypatch.setattr('backend.ai.client_context',lambda:context)

    class Handler(BaseHTTPRequestHandler):
        calls=0
        def do_GET(self):
            Handler.calls+=1
            self.send_response(200);self.end_headers();self.wfile.write(b'{"ok":true}')
        def log_message(self,*args):pass

    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    server_context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_context.load_cert_chain(certfile,keyfile)
    server.socket=server_context.wrap_socket(server.socket,server_side=True)
    worker=threading.Thread(target=lambda:server.serve_forever(poll_interval=0.05),daemon=True)
    worker.start()
    try:
        # Transport methods do not need a database or a real ChatGPT account.
        engine=ChatGPT.__new__(ChatGPT)
        url=f'https://localhost:{server.server_port}/test'
        if case=='trusted':
            assert engine.json_request(url)=={'ok':True}
            assert Handler.calls==1
        else:
            with pytest.raises(HTTPException,match='TLS-CERT'):
                engine.json_request(url)
            assert Handler.calls==0  # No HTTP data sent after a rejected certificate.
    finally:
        server.shutdown();server.server_close();worker.join(timeout=2)


def test_certificate_error_exposes_only_numeric_reason(monkeypatch):
    from urllib.error import URLError
    error=ssl.SSLCertVerificationError(1,'private-provider-message')
    error.verify_code=2148204809
    def failed(*args,**kwargs):raise URLError(error)
    monkeypatch.setattr('backend.ai.urlopen',failed)
    engine=ChatGPT.__new__(ChatGPT)
    with pytest.raises(HTTPException) as caught:
        engine.request('https://auth.openai.com/api/accounts/oauth/token')
    assert '인증서 코드 2148204809' in caught.value.detail
    assert 'private-provider-message' not in caught.value.detail
