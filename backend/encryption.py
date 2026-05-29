from cryptography.fernet import Fernet
from dotenv import load_dotenv
import os

load_dotenv()

_fernet = Fernet(os.environ["FERNET_KEY"].encode())


def encrypt(plaintext: str) -> str:
    return _fernet.encrypt(plaintext.encode()).decode()


def decrypt(token: str) -> str:
    return _fernet.decrypt(token.encode()).decode()
