import random
import string

def generate_id(length=8):
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))