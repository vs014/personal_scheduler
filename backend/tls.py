"""HTTPS verification using Windows' native certificate-chain validation."""
import ssl
import sys

import truststore

WINDOWS = sys.platform == 'win32'


def client_context():
    # Loading a snapshot of Windows roots into OpenSSL does not use CryptoAPI's
    # chain building (including retrieval of missing intermediate certificates).
    # Use an explicit context, without globally replacing ssl or retrying insecurely.
    if WINDOWS:
        context = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    else:
        context = ssl.create_default_context()
    context.verify_mode = ssl.CERT_REQUIRED
    context.check_hostname = True
    return context
