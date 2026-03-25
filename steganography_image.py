import os
import json
import base64
import time
from getpass import getpass
from PIL import Image
from PIL import PngImagePlugin
from Crypto.Cipher import AES
from Crypto.Protocol.KDF import PBKDF2
from Crypto.Hash import SHA256
from Crypto.Random import get_random_bytes
from Crypto.Util.Padding import pad, unpad

DELIMITER = '11111111111111101010101010101010'  
METADATA_KEY = "SteganoAuthData"  # Khóa để lưu metadata trong PNG
PBKDF2_ITERATIONS = 100000
AES_KEY_SIZE = 32  # AES-256
HASH_SIZE = 32 # SHA-256


def bytes_to_bits(data_bytes):
    return ''.join(format(byte, '08b') for byte in data_bytes)

def bits_to_bytes(bit_string):
    return int(bit_string, 2).to_bytes((len(bit_string) + 7) // 8, 'big')

        
def _internal_embed_bits_in_image(image, bit_stream):
    width, height = image.size
    pixels = image.load()
    data_index = 0
    data_len = len(bit_stream)

    for y in range(height):
        for x in range(width):
            # Lấy giá trị của cả 4 kênh RGBA
            r, g, b, a = pixels[x, y]
            if data_index < data_len:
                r = (r & 254) | int(bit_stream[data_index]); data_index += 1
            if data_index < data_len:
                g = (g & 254) | int(bit_stream[data_index]); data_index += 1
            if data_index < data_len:
                b = (b & 254) | int(bit_stream[data_index]); data_index += 1
            if data_index < data_len:
                a = (a & 254) | int(bit_stream[data_index]); data_index += 1
            pixels[x, y] = (r, g, b, a)
            if data_index >= data_len:
                return image
    return image

def _internal_extract_bits_from_image(image):
    width, height = image.size
    pixels = image.load()
    binary_data = ""
    for y in range(height):
        for x in range(width):
            r, g, b, a = pixels[x, y]
            binary_data += str(r & 1)
            if binary_data.endswith(DELIMITER): return binary_data[:-len(DELIMITER)]
            binary_data += str(g & 1)
            if binary_data.endswith(DELIMITER): return binary_data[:-len(DELIMITER)]
            binary_data += str(b & 1)
            if binary_data.endswith(DELIMITER): return binary_data[:-len(DELIMITER)]
            binary_data += str(a & 1)
            if binary_data.endswith(DELIMITER): return binary_data[:-len(DELIMITER)]
            
    return None 
def hide_securely_in_image(cover_path, output_path, password, secret_data_source, data_type):
    """
    Quy trình hoàn chỉnh: Chuẩn bị dữ liệu, mã hóa, giấu vào ảnh và đính kèm metadata.
    """
    print(f"\n{'='*20} BẮT ĐẦU QUY TRÌNH GIẤU TIN ({data_type.upper()}) {'='*20}")
    
    print("1. Đang xử lý dữ liệu bí mật...")
    original_filename = None
    secret_data_bytes = None
    if data_type == 'text':
        secret_data_bytes = secret_data_source.encode('utf-8')
    elif data_type == 'file':
        try:
            with open(secret_data_source, 'rb') as f:
                secret_data_bytes = f.read()
            original_filename = os.path.basename(secret_data_source)
        except FileNotFoundError:
            print(f"   - Lỗi: Không tìm thấy tệp bí mật '{secret_data_source}'.")
            return False
    else:
        print(f"   - Lỗi: Loại dữ liệu '{data_type}' không được hỗ trợ.")
        return False
    print(f"   - Kích thước dữ liệu gốc: {len(secret_data_bytes)} bytes.")

    print("2. Đang tạo khóa và mã hóa dữ liệu...")
    auth_salt = get_random_bytes(16)
    key_salt = get_random_bytes(16)
    auth_hash = PBKDF2(password, auth_salt, dkLen=HASH_SIZE, count=PBKDF2_ITERATIONS, hmac_hash_module=SHA256)
    aes_key = PBKDF2(password, key_salt, dkLen=AES_KEY_SIZE, count=PBKDF2_ITERATIONS, hmac_hash_module=SHA256)
    iv = get_random_bytes(AES.block_size)
    cipher = AES.new(aes_key, AES.MODE_CBC, iv)
    padded_data = pad(secret_data_bytes, AES.block_size)
    ciphertext = cipher.encrypt(padded_data)
    print(f"   - Kích thước dữ liệu sau mã hóa: {len(ciphertext)} bytes.")

    print("3. Đang giấu dữ liệu vào ảnh và đính kèm metadata...")
    try:
        cover_image = Image.open(cover_path).convert("RGBA")
        
        bits_to_hide = len(ciphertext) * 8 + len(DELIMITER)
        # Giấu vào 3 kênh RGB nên nhân 3
        cover_capacity = cover_image.width * cover_image.height * 3 
        if bits_to_hide > cover_capacity:
            print(f"   - LỖI: Dữ liệu quá lớn ({bits_to_hide} bits) để giấu trong ảnh (dung lượng: {cover_capacity} bits).")
            return False
        
        bit_stream = bytes_to_bits(ciphertext) + DELIMITER
        stego_image = _internal_embed_bits_in_image(cover_image, bit_stream)
        
        metadata_payload = {
            'auth_salt': base64.b64encode(auth_salt).decode('utf-8'),
            'key_salt': base64.b64encode(key_salt).decode('utf-8'),
            'auth_hash': base64.b64encode(auth_hash).decode('utf-8'),
            'iv': base64.b64encode(iv).decode('utf-8'),
            'data_type': data_type,
            'filename': original_filename
        }
        
        png_info = PngImagePlugin.PngInfo()
        png_info.add_text(METADATA_KEY, json.dumps(metadata_payload))
        
        stego_image.save(output_path, "PNG", pnginfo=png_info)
        return True
    except FileNotFoundError:
        print(f"   - Lỗi: Không tìm thấy tệp ảnh bìa '{cover_path}'.")
        return False
    except Exception as e:
        print(f"   - Lỗi không xác định trong quá trình giấu tin: {e}")
        return False

def extract_securely_from_image(stego_path, password, output_folder=None):  
    print("1. Đang trích xuất và phân tích metadata...")
    try:
        stego_image = Image.open(stego_path).convert("RGBA")
        metadata_str = stego_image.info.get(METADATA_KEY)
        if not metadata_str:
            print("Lỗi: Không tìm thấy metadata giấu tin trong ảnh.")
            return None
        metadata = json.loads(metadata_str)
        
        auth_salt = base64.b64decode(metadata['auth_salt'])
        key_salt = base64.b64decode(metadata['key_salt'])
        auth_hash_original = base64.b64decode(metadata['auth_hash'])
        iv = base64.b64decode(metadata['iv'])
        data_type = metadata['data_type']
        filename = metadata.get('filename')
    except FileNotFoundError:
        print(f"Lỗi: Không tìm thấy tệp ảnh '{stego_path}'.")
        return None
    except (KeyError, json.JSONDecodeError, TypeError):
        print("Lỗi: Metadata không hợp lệ hoặc bị hỏng.")
        return None

    print("2. Đang xác thực mật khẩu")
    auth_hash_attempt = PBKDF2(password, auth_salt, dkLen=HASH_SIZE, count=PBKDF2_ITERATIONS, hmac_hash_module=SHA256)
    if auth_hash_attempt != auth_hash_original:
        print("SAI MẬT KHẨU!")
        return "SAI_MAT_KHAU"
    print("Xác thực mật khẩu thành công.")
    
    print("3. Đang trích xuất và giải mã dữ liệu")
    aes_key = PBKDF2(password, key_salt, dkLen=AES_KEY_SIZE, count=PBKDF2_ITERATIONS, hmac_hash_module=SHA256)
    extracted_bits = _internal_extract_bits_from_image(stego_image)
    if extracted_bits is None:
        print("Lỗi: Không tìm thấy dữ liệu hoặc dữ liệu bị hỏng (không có delimiter).")
        return None
        
    ciphertext = bits_to_bytes(extracted_bits)
    try:
        cipher = AES.new(aes_key, AES.MODE_CBC, iv)
        decrypted_padded_data = cipher.decrypt(ciphertext)
        decrypted_data = unpad(decrypted_padded_data, AES.block_size)
    except (ValueError, KeyError) as e:
        print(f"Lỗi khi giải mã: {e}. Nguyên nhân có thể do mật khẩu sai hoặc dữ liệu bị hỏng.")
        return None

    print("4. Đang xử lý dữ liệu đã giải mã...")
    if data_type == 'text':
        return decrypted_data.decode('utf-8')
    elif data_type == 'file':
        if not output_folder or not filename:
            print("Lỗi: Cần cung cấp thư mục đầu ra và tên file gốc trong metadata.")
            return None
        output_path = os.path.join(output_folder, f"extracted_{filename}")
        with open(output_path, 'wb') as f:
            f.write(decrypted_data)
        return output_path
    else:
        print(f"Lỗi: Loại dữ liệu '{data_type}' không xác định.")
        return None

if __name__ == '__main__':
    pass
