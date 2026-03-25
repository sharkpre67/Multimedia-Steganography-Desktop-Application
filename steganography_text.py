import os
import json
import base64
from getpass import getpass
from typing import Union
from Crypto.Cipher import AES
from Crypto.Protocol.KDF import PBKDF2
from Crypto.Hash import SHA256
from Crypto.Random import get_random_bytes
from Crypto.Util.Padding import pad, unpad


ZERO_WIDTH_SPACE = '\u200b'     
ZERO_WIDTH_NON_JOINER = '\u200c' 
DELIMITER_BINARY = '1111111111111110' 
HEADER_LEN = 10 


def get_password():
    while True:
        p1 = getpass("Nhập mật khẩu: ")
        p2 = getpass("Xác nhận mật khẩu: ")
        if p1 == p2 and p1:
            return p1
        print("Sai mật khẩu. Thử lại.")

def embed_securely_in_text(cover_text: str, secret_message: str, password: str) -> Union[str, None]: 
    secret_data_bytes = secret_message.encode('utf-8')
    print(f"1. Đã chuẩn bị dữ liệu bí mật (kích thước: {len(secret_data_bytes)} bytes).")

    auth_salt = get_random_bytes(16)
    key_salt = get_random_bytes(16)
    auth_hash = PBKDF2(password, auth_salt, dkLen=32, count=100000, hmac_hash_module=SHA256)
    aes_key = PBKDF2(password, key_salt, dkLen=16, count=100000, hmac_hash_module=SHA256) # AES-128
    print("2. Đã tạo Auth Hash và Key AES-128 từ mật khẩu và salt.")

    iv = get_random_bytes(AES.block_size)
    cipher = AES.new(aes_key, AES.MODE_CBC, iv)
    padded_data = pad(secret_data_bytes, AES.block_size)
    ciphertext = cipher.encrypt(padded_data)
    print(f"3. Đã mã hóa dữ liệu (kích thước mã hóa: {len(ciphertext)} bytes).")

    print("4. Đang đóng gói metadata và dữ liệu đã mã hóa")
    metadata = {
        'auth_salt': base64.b64encode(auth_salt).decode('utf-8'),
        'key_salt': base64.b64encode(key_salt).decode('utf-8'),
        'auth_hash': base64.b64encode(auth_hash).decode('utf-8'),
        'iv': base64.b64encode(iv).decode('utf-8')
    }
    json_metadata_bytes = json.dumps(metadata).encode('utf-8')
    header = f"{len(json_metadata_bytes):0{HEADER_LEN}d}".encode('utf-8')
    payload_to_hide = header + json_metadata_bytes + ciphertext
    print(f"Kích thước payload tổng: {len(payload_to_hide)} bytes.")

    print("5. Bắt đầu giấu payload vào văn bản bìa...")
    binary_to_hide = ''.join(format(byte, '08b') for byte in payload_to_hide) + DELIMITER_BINARY
    
    chunks = [binary_to_hide[i:i + 8] for i in range(0, len(binary_to_hide), 8)]
    if len(chunks) > len(cover_text) - 1:
        print(f"Lỗi: Văn bản bìa quá ngắn. Cần ít nhất {len(chunks) + 1} ký tự để giấu thông điệp này.")
        return None
        
    stego_text_list = []
    for i in range(len(chunks)):
        stego_text_list.append(cover_text[i])
        invisible_sequence = chunks[i].replace('1', ZERO_WIDTH_SPACE).replace('0', ZERO_WIDTH_NON_JOINER)
        stego_text_list.append(invisible_sequence)
        
    stego_text_list.append(cover_text[len(chunks):])
    
    print("Giấu tin thành công!")
    return "".join(stego_text_list)


# Trích xuất bảo mật
def extract_securely_from_text(stego_text: str, password: str) -> Union[str, None]:
    print("1. Đang trích xuất payload từ các ký tự ẩn...")
    extracted_binary = ""
    for char in stego_text:
        if char == ZERO_WIDTH_SPACE:
            extracted_binary += '1'
        elif char == ZERO_WIDTH_NON_JOINER:
            extracted_binary += '0'
            
    delimiter_pos = extracted_binary.find(DELIMITER_BINARY)
    if delimiter_pos == -1:
        print("Không tìm thấy dấu kết thúc dữ liệu.")
        return None
        
    payload_binary = extracted_binary[:delimiter_pos]
    payload_bytes = int(payload_binary, 2).to_bytes((len(payload_binary) + 7) // 8, 'big')
    print(f"Đã trích xuất payload có kích thước {len(payload_bytes)} bytes.")

    print("2. Đang phân tích metadata")
    try:
        header = payload_bytes[:HEADER_LEN]
        json_len = int(header.decode('utf-8'))
        
        json_end = HEADER_LEN + json_len
        json_metadata_bytes = payload_bytes[HEADER_LEN:json_end]
        ciphertext = payload_bytes[json_end:]
        
        metadata = json.loads(json_metadata_bytes.decode('utf-8'))
        
        auth_salt = base64.b64decode(metadata['auth_salt'])
        key_salt = base64.b64decode(metadata['key_salt'])
        auth_hash_original = base64.b64decode(metadata['auth_hash'])
        iv = base64.b64decode(metadata['iv'])
    except Exception as e:
        print(f"Lỗi: Cấu trúc payload không hợp lệ hoặc metadata bị hỏng. {e}")
        return None

    print("3. Đang xác thực mật khẩu")
    auth_hash_attempt = PBKDF2(password, auth_salt, dkLen=32, count=100000, hmac_hash_module=SHA256)
    
    if auth_hash_attempt != auth_hash_original:
        print("Sai mật khẩu!")
        return "SAI_MAT_KHAU"
    print("Xác thực mật khẩu thành công.")

    print("4. Đang tái tạo khóa giải mã AES")
    aes_key = PBKDF2(password, key_salt, dkLen=16, count=100000, hmac_hash_module=SHA256)
    
    print("5. Đang giải mã dữ liệu")
    try:
        cipher = AES.new(aes_key, AES.MODE_CBC, iv)
        decrypted_padded_data = cipher.decrypt(ciphertext)
        decrypted_data = unpad(decrypted_padded_data, AES.block_size)
        
        revealed_message = decrypted_data.decode('utf-8')
        print("Giải mã thành công!")
        return revealed_message
    except (ValueError, KeyError) as e:
        print(f"Lỗi khi giải mã: {e}. Nguyên nhân có thể do mật khẩu sai hoặc dữ liệu bị hỏng.")
        return None
    except UnicodeDecodeError:
        print("Lỗi: Dữ liệu giải mã không phải là văn bản UTF-8 hợp lệ.")
        return None

if __name__ == "__main__":
    pass
