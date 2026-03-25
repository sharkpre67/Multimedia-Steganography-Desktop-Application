import os
import wave
import numpy as np
import time
import json
import base64
from getpass import getpass
from Crypto.Cipher import AES
from Crypto.Protocol.KDF import PBKDF2
from Crypto.Hash import SHA256
from Crypto.Random import get_random_bytes
from Crypto.Util.Padding import pad, unpad

CHUNK_SIZE = 4096
DELIMITER_BITS = '11111111111111101010101010101010' 
HEADER_LEN = 10  
PBKDF2_ITERATIONS = 100000 
AES_KEY_SIZE = 32  # AES-256
HASH_SIZE = 32 # SHA-256

def get_payload_bits_generator(payload_bytes, delimiter_bits=DELIMITER_BITS):
    """Tạo một generator để cung cấp từng bit của payload và delimiter."""
    for byte in payload_bytes:
        bits = format(byte, '08b')
        for bit in bits:
            yield int(bit)
    for bit in delimiter_bits:
        yield int(bit)

def _internal_hide_bytes_in_audio(cover_audio_path, payload_bytes, output_audio_path):
    """Giấu một chuỗi bytes vào các bit cuối cùng (LSB) của tệp âm thanh."""
    try:
        n_bits_to_hide = len(payload_bytes) * 8 + len(DELIMITER_BITS)
        with wave.open(cover_audio_path, 'rb') as cover_audio:
            params = cover_audio.getparams()
            n_channels, sampwidth, _, n_frames = params[:4]
            
            if sampwidth != 2:
                print("Lỗi: Chỉ hỗ trợ tệp âm thanh 16-bit (WAV).")
                return False
                
            max_bits_can_hide = n_frames * n_channels
            if n_bits_to_hide > max_bits_can_hide:
                print(f"Lỗi: Dữ liệu quá lớn ({n_bits_to_hide} bits) so với dung lượng có thể giấu của tệp ({max_bits_can_hide} bits).")
                return False
            
            with wave.open(output_audio_path, 'wb') as stego_audio:
                stego_audio.setparams(params)
                bit_generator = get_payload_bits_generator(payload_bytes)
                bits_hidden = 0
                
                while True:
                    frames = cover_audio.readframes(CHUNK_SIZE)
                    if not frames: break
                    
                    samples = np.frombuffer(frames, dtype=np.int16)
                    new_samples = samples.copy()
                    
                    if bits_hidden < n_bits_to_hide:
                        num_bits_to_embed = min(len(samples), n_bits_to_hide - bits_hidden)
                        bits_array = np.array([next(bit_generator) for _ in range(num_bits_to_embed)], dtype=np.int16)
                        
                        samples_to_modify = new_samples[:num_bits_to_embed]
                        cleared_samples = samples_to_modify - (samples_to_modify & 1)
                        modified_part = cleared_samples + bits_array
                        
                        new_samples[:num_bits_to_embed] = modified_part
                        bits_hidden += num_bits_to_embed
                        
                    stego_audio.writeframes(new_samples.tobytes())
        return True
    except FileNotFoundError:
        print(f"Lỗi: Không tìm thấy tệp âm thanh bìa tại '{cover_audio_path}'")
        return False
    except Exception as e:
        print(f"Lỗi trong quá trình giấu tin cấp thấp (_internal_hide_bytes_in_audio): {e}")
        return False

def _internal_extract_bytes_from_audio(stego_audio_path):
    try:
        with wave.open(stego_audio_path, 'rb') as stego_audio:
            if stego_audio.getsampwidth() != 2: 
                print("Lỗi: Chỉ hỗ trợ tệp âm thanh 16-bit.")
                return None
                
            bit_buffer = ""
            found_delimiter = False
            all_bits = []
            
            while True:
                frames = stego_audio.readframes(CHUNK_SIZE)
                if not frames: break
                
                samples = np.frombuffer(frames, dtype=np.int16)
                bit_buffer += "".join(map(str, (samples & 1)))
                
                delimiter_index = bit_buffer.find(DELIMITER_BITS)
                if delimiter_index != -1:
                    all_bits.append(bit_buffer[:delimiter_index])
                    found_delimiter = True
                    break
                else:
                    cutoff = max(0, len(bit_buffer) - len(DELIMITER_BITS))
                    all_bits.append(bit_buffer[:cutoff])
                    bit_buffer = bit_buffer[cutoff:]
                    
        if not found_delimiter: 
            print("Lỗi: Không tìm thấy delimiter. Tệp có thể không chứa dữ liệu hoặc bị hỏng.")
            return None
            
        final_bit_string = "".join(all_bits)
        return int(final_bit_string, 2).to_bytes((len(final_bit_string) + 7) // 8, 'big')
    except FileNotFoundError:
        print(f"Lỗi: Không tìm thấy tệp đã giấu tin tại '{stego_audio_path}'")
        return None
    except Exception as e:
        print(f"Lỗi trong quá trình trích xuất cấp thấp (_internal_extract_bytes_from_audio): {e}")
        return None

def hide_securely_in_audio(cover_audio_path, output_audio_path, password, secret_data_source, data_type):
    print("1. Đang xử lý dữ liệu bí mật")
    original_filename = None
    data_bytes = None

    if data_type == 'text':
        data_bytes = secret_data_source.encode('utf-8')
        print(f"Đã chuyển đổi văn bản thành {len(data_bytes)} bytes.")
    elif data_type == 'file':
        if not os.path.exists(secret_data_source):
            print(f"Lỗi: Không tìm thấy tệp bí mật '{secret_data_source}'")
            return False
        try:
            with open(secret_data_source, 'rb') as f:
                data_bytes = f.read()
            original_filename = os.path.basename(secret_data_source)
            print(f"Đã đọc {len(data_bytes)} bytes từ tệp '{original_filename}'.")
        except Exception as e:
            print(f"Lỗi khi đọc tệp bí mật: {e}")
            return False
    else:
        print(f"Lỗi: Loại dữ liệu '{data_type}' không được hỗ trợ.")
        return False

    print("2. Đang tạo các thành phần mã hóa và mã hóa dữ liệu")
    auth_salt = get_random_bytes(16)
    key_salt = get_random_bytes(16)
    auth_hash = PBKDF2(password, auth_salt, dkLen=HASH_SIZE, count=PBKDF2_ITERATIONS, hmac_hash_module=SHA256)
    aes_key = PBKDF2(password, key_salt, dkLen=AES_KEY_SIZE, count=PBKDF2_ITERATIONS, hmac_hash_module=SHA256)
    iv = get_random_bytes(AES.block_size)
    cipher = AES.new(aes_key, AES.MODE_CBC, iv)
    padded_data = pad(data_bytes, AES.block_size)
    ciphertext = cipher.encrypt(padded_data)
    print(f"Kích thước dữ liệu sau mã hóa: {len(ciphertext)} bytes.")

    print("3. Đang đóng gói metadata và ciphertext")
    metadata = {
        'auth_salt': base64.b64encode(auth_salt).decode('utf-8'),
        'key_salt': base64.b64encode(key_salt).decode('utf-8'),
        'auth_hash': base64.b64encode(auth_hash).decode('utf-8'),
        'iv': base64.b64encode(iv).decode('utf-8'),
        'data_type': data_type,
        'filename': original_filename
    }
    json_metadata = json.dumps(metadata).encode('utf-8')
    header = f"{len(json_metadata):0{HEADER_LEN}d}".encode('utf-8')
    payload_to_hide = header + json_metadata + ciphertext
    print(f"   - Kích thước payload tổng cộng cần giấu: {len(payload_to_hide)} bytes.")

    print("4. Đang tiến hành giấu payload vào tệp âm thanh")
    return _internal_hide_bytes_in_audio(cover_audio_path, payload_to_hide, output_audio_path)


def extract_securely_from_audio(stego_audio_path, password, output_folder=None):
    print("1. Đang trích xuất payload từ tệp âm thanh")
    payload = _internal_extract_bytes_from_audio(stego_audio_path)
    if payload is None:
        print("\nKhông thể trích xuất payload.")
        return None

    print("2. Đang phân tích metadata")
    try:
        header = payload[:HEADER_LEN]
        json_len = int(header.decode('utf-8'))
        
        json_end = HEADER_LEN + json_len
        json_metadata_bytes = payload[HEADER_LEN:json_end]
        ciphertext = payload[json_end:]
        
        metadata = json.loads(json_metadata_bytes.decode('utf-8'))
        
        auth_salt = base64.b64decode(metadata['auth_salt'])
        key_salt = base64.b64decode(metadata['key_salt'])
        auth_hash_original = base64.b64decode(metadata['auth_hash'])
        iv = base64.b64decode(metadata['iv'])
        data_type = metadata.get('data_type', 'file') 
        filename = metadata.get('filename')
    except Exception as e:
        print(f"Lỗi: Cấu trúc payload không hợp lệ hoặc metadata bị hỏng. {e}")
        return None
    print("3. Đang xác thực mật khẩu")
    auth_hash_attempt = PBKDF2(password, auth_salt, dkLen=HASH_SIZE, count=PBKDF2_ITERATIONS, hmac_hash_module=SHA256)
    if auth_hash_attempt != auth_hash_original:
        print("SAI MẬT KHẨU!")
        return "SAI_MAT_KHAU"
    print("Xác thực mật khẩu thành công.")

    print("4. Đang tái tạo khóa và giải mã dữ liệu")
    try:
        aes_key = PBKDF2(password, key_salt, dkLen=AES_KEY_SIZE, count=PBKDF2_ITERATIONS, hmac_hash_module=SHA256)
        cipher = AES.new(aes_key, AES.MODE_CBC, iv)
        decrypted_padded_data = cipher.decrypt(ciphertext)
        decrypted_data = unpad(decrypted_padded_data, AES.block_size)
    except (ValueError, KeyError) as e:
        print(f"Lỗi khi giải mã: {e}. Dữ liệu có thể đã bị hỏng (padding không chính xác).")
        return None
    print("5. Đang xử lý dữ liệu đã giải mã")
    if data_type == 'text':
        try:
            return decrypted_data.decode('utf-8')
        except UnicodeDecodeError:
            print("Lỗi giải mã UTF-8, trả về dữ liệu thô.")
            return decrypted_data
    else: 
        if not output_folder:
            print("Lỗi: Cần cung cấp thư mục đầu ra (output_folder) để lưu tệp.")
            return None
            
        output_filename = filename or f"extracted_file_{int(time.time())}.bin"
        output_path = os.path.join(output_folder, output_filename)
        
        try:
            with open(output_path, 'wb') as f:
                f.write(decrypted_data)
            print(f"   - Đã lưu vào: '{output_path}'")
            print(f"   - Kích thước tệp: {len(decrypted_data)} bytes")
            return output_path
        except Exception as e:
            print(f"   - Lỗi khi ghi tệp đầu ra: {e}")
            return None

if __name__ == '__main__':
    pass
