#!/usr/bin/env python
from passlib.context import CryptContext
from getpass import getpass

crypto_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
password = getpass()
print(crypto_context.hash(password))
