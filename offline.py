"""Restringe o processo antes de carregar o assinador ou um driver PKCS#11."""
import ctypes
import resource
import sys


def _activate():
    if sys.platform != "darwin":
        raise SystemExit("Esta edição offline requer macOS.")
    try:
        lib = ctypes.CDLL("/usr/lib/libsandbox.dylib")
        lib.sandbox_init.argtypes = [ctypes.c_char_p, ctypes.c_uint64,
                                     ctypes.POINTER(ctypes.c_char_p)]
        lib.sandbox_init.restype = ctypes.c_int
        lib.sandbox_free_error.argtypes = [ctypes.c_char_p]
        lib.sandbox_free_error.restype = None
        error = ctypes.c_char_p()
        profile = (
            b'(version 1)(allow default)(deny network*)'
            b'(deny mach-lookup (global-name "com.apple.mDNSResponder")'
            b' (global-name "com.apple.dnssd.service"))'
        )
        status = lib.sandbox_init(profile, 0, ctypes.byref(error))
        if error:
            lib.sandbox_free_error(error)
        if status:
            raise SystemExit("O macOS recusou o bloqueio de rede. Assinatura cancelada.")
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    except (OSError, AttributeError, ValueError) as exc:
        raise SystemExit("Falha ao ativar as proteções locais. Assinatura cancelada.") from exc


# O cache de imports do Python garante uma única ativação por processo.
_activate()
