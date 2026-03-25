import os
import subprocess
import json
import base64
import cv2
import numpy as np
import time
import traceback
from PIL import Image
from Crypto.Hash import SHA256
from Crypto.Cipher import AES
from Crypto.Protocol.KDF import PBKDF2
from Crypto.Random import get_random_bytes
from Crypto.Util.Padding import pad, unpad

FFMPEG_PATH = r"C:\Program Files\ffmpeg\bin\ffmpeg.exe"
MKVEXTRACT_PATH = r"C:\Program Files\MKVToolNix\mkvextract.exe"

# Kiểm tra xem các file có tồn tại không
if not os.path.exists(FFMPEG_PATH):
    user_profile = os.environ.get("USERPROFILE", "")
    alt_ffmpeg_path = os.path.join(user_profile, r"AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-7.1.1-full_build\bin\ffmpeg.exe")
    if os.path.exists(alt_ffmpeg_path):
        FFMPEG_PATH = alt_ffmpeg_path
    else:
        print(f"Không tìm thấy 'ffmpeg.exe' tại '{FFMPEG_PATH}' hoặc đường dẫn thay thế. Vui lòng kiểm tra lại nơi cài đặt.")

if not os.path.exists(MKVEXTRACT_PATH):
    print(f"Không tìm thấy 'mkvextract.exe' tại '{MKVEXTRACT_PATH}'. Vui lòng kiểm tra lại nơi cài đặt MKVToolNix.")
# ================================================

def resize_image_for_embedding(input_path, temp_dir="temp_processing"):
    try:
        os.makedirs(temp_dir, exist_ok=True)
        image = Image.open(input_path).convert("RGBA")
        image.thumbnail((512, 512), Image.Resampling.LANCZOS)
        timestamp = int(time.time() * 1000)
        base_name = os.path.basename(input_path)
        output_image_path = os.path.join(temp_dir, f'resized_{timestamp}_{base_name}.png')
        image.save(output_image_path, format='PNG')
        return output_image_path
    except Exception as e:
        print(f"Lỗi khi xử lý ảnh: {e}"); traceback.print_exc(); return None

def attach_metadata_to_mkv(video_path, metadata_dict, output_path):
    metadata_filename = "metadata.json"
    temp_video_path = "temp_with_data_" + os.path.basename(video_path)
    try:
        os.rename(video_path, temp_video_path)
    except FileNotFoundError:
        print(f"Lỗi: Không tìm thấy tệp tạm '{video_path}'."); return False
    try:
        with open(metadata_filename, 'w', encoding='utf-8') as f:
            json.dump(metadata_dict, f, ensure_ascii=False, indent=4)
        
        ffmpeg_command = [
            FFMPEG_PATH, '-y', '-i', temp_video_path,
            '-attach', metadata_filename,
            '-metadata:s:t:0', 'mimetype=application/json',
            '-c', 'copy', output_path
        ]
        
        subprocess.run(ffmpeg_command, check=True, capture_output=True, text=True, encoding='utf-8')
        print("Đính kèm metadata thành công."); return True
    except subprocess.CalledProcessError as e:
        print("\nLỗi khi đính kèm metadata bằng FFmpeg:", e.stderr); os.rename(temp_video_path, video_path); return False
    finally:
        if os.path.exists(metadata_filename): os.remove(metadata_filename)
        if os.path.exists(temp_video_path): os.remove(temp_video_path)

def extract_metadata_from_mkv(video_path):
    metadata_filename = f"extracted_metadata_{int(time.time()*1000)}.json"
    try:
        mkvextract_command = [MKVEXTRACT_PATH, 'attachments', video_path, f'1:{metadata_filename}']
        result = subprocess.run(mkvextract_command, check=False, capture_output=True, text=True, encoding='utf-8')
        if result.returncode != 0 or not os.path.exists(metadata_filename):
            print(f"\nLỗi mkvextract hoặc không tìm thấy attachment."); print("STDERR:", result.stderr); return None
        with open(metadata_filename, 'r', encoding='utf-8') as f: metadata = json.load(f)
        print("Trích xuất metadata thành công."); return metadata
    except Exception as e:
        print(f"\nLỗi khi trích xuất metadata: {e}"); traceback.print_exc(); return None
    finally:
        if os.path.exists(metadata_filename): os.remove(metadata_filename)

def _embed_binary_to_video(input_video_path, binary_data, output_video_path):
    cap = cv2.VideoCapture(input_video_path)
    if not cap.isOpened():
        print(f"Lỗi: Không thể mở video đầu vào {input_video_path}"); return False
    fps = cap.get(cv2.CAP_PROP_FPS); width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)); height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)); total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    delimiter = '11111111111111101010101010101010'
    binary_data_with_delimiter = binary_data + delimiter
    data_len = len(binary_data_with_delimiter)
    max_capacity_bits = (width * height * 3) * (total_frames // 2)
    print(f"Dữ liệu cần giấu (đã mã hóa + delimiter): {data_len} bits."); print(f"Dung lượng tối đa của video: {max_capacity_bits} bits.")
    if data_len > max_capacity_bits:
        print("Lỗi: Dữ liệu quá lớn so với dung lượng của video."); cap.release(); return False

    ffmpeg_command = [
        FFMPEG_PATH, '-y', '-f', 'rawvideo', '-vcodec', 'rawvideo', 
        '-s', f'{width}x{height}', '-pix_fmt', 'bgr24', '-r', str(fps), 
        '-i', '-', '-c:v', 'ffv1', '-level', '3', '-g', '1', output_video_path
    ]
    
    ffmpeg_process = subprocess.Popen(ffmpeg_command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    try:
        data_index = 0
        for frame_count in range(total_frames):
            ret, frame = cap.read()
            if not ret: break
            if frame_count % 2 == 0 and data_index < data_len:
                flat_frame = frame.ravel()
                for i in range(len(flat_frame)):
                    if data_index >= data_len: break
                    bit_to_embed = int(binary_data_with_delimiter[data_index])
                    flat_frame[i] = (flat_frame[i] & 254) | bit_to_embed
                    data_index += 1
                frame = flat_frame.reshape(frame.shape)
            ffmpeg_process.stdin.write(frame.tobytes())
            print(f"\rĐã xử lý {frame_count + 1}/{total_frames} frame - Nhúng {data_index}/{data_len} bit", end="")
        print("\nHoàn tất xử lý frame, đang chờ FFmpeg...")
    except Exception as e:
        print(f"\nLỗi nghiêm trọng trong vòng lặp xử lý video: {e}"); traceback.print_exc(); return False
    finally:
        cap.release()
        if ffmpeg_process:
            stdout_data, stderr_data = ffmpeg_process.communicate()
            if ffmpeg_process.returncode != 0:
                print("\nLỗi từ FFmpeg:", stderr_data.decode('utf-8', errors='ignore')); return False
    return True

def _extract_binary_from_video(stego_video_path):
    cap = cv2.VideoCapture(stego_video_path)
    if not cap.isOpened():
        print(f"Lỗi: Không thể mở video {stego_video_path}"); return None
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)); delimiter = '11111111111111101010101010101010'; delimiter_len = len(delimiter)
    extracted_bits = []; data_complete = False
    try:
        for frame_idx in range(total_frames):
            ret, frame = cap.read()
            if not ret: break
            if frame_idx % 2 == 0:
                for row in frame:
                    for pixel in row:
                        for channel_val in pixel:
                            extracted_bits.append(str(channel_val & 1))
                            if len(extracted_bits) >= delimiter_len and ''.join(extracted_bits[-delimiter_len:]) == delimiter:
                                data_complete = True; break
                        if data_complete: break
                    if data_complete: break
            print(f"\rĐang trích xuất: Frame {frame_idx + 1}/{total_frames}", end="")
            if data_complete: break
    finally:
        cap.release()
    if not data_complete:
        print("\nKhông tìm thấy dấu kết thúc. Dữ liệu có thể bị hỏng."); return None
    print("\nĐã tìm thấy dấu kết thúc dữ liệu!")
    return ''.join(extracted_bits[:-delimiter_len])

def embed_securely(input_video, output_video, password, secret_data, data_type='text'):
    try:
        start_time = time.time()
        original_filename = None
        if data_type == 'text':
            data_bytes = secret_data.encode('utf-8'); print(f"Đã chuyển đổi văn bản thành {len(data_bytes)} bytes.")
        elif data_type == 'image':
            if not os.path.exists(secret_data): print(f"Lỗi: Không tìm thấy tệp ảnh '{secret_data}'"); return False
            resized_path = resize_image_for_embedding(secret_data)
            if not resized_path: return False
            with open(resized_path, 'rb') as f: data_bytes = f.read()
            if os.path.exists(resized_path): os.remove(resized_path)
            original_filename = os.path.basename(secret_data); print(f"Đã xử lý và đọc {len(data_bytes)} bytes từ ảnh '{original_filename}'.")
        elif data_type == 'file':
            if not os.path.exists(secret_data): print(f"Lỗi: Không tìm thấy tệp bí mật '{secret_data}'"); return False
            with open(secret_data, 'rb') as f: data_bytes = f.read()
            original_filename = os.path.basename(secret_data); print(f"Đã đọc {len(data_bytes)} bytes từ tệp '{original_filename}'.")
        else:
            print(f"Lỗi: Loại dữ liệu '{data_type}' không được hỗ trợ."); return False
        print("Đang tạo khóa và mã hóa dữ liệu")
        auth_salt = get_random_bytes(16); key_salt = get_random_bytes(16)
        auth_hash = PBKDF2(password, auth_salt, dkLen=32, count=100000, hmac_hash_module=SHA256)
        aes_key = PBKDF2(password, key_salt, dkLen=32, count=100000, hmac_hash_module=SHA256)
        iv = get_random_bytes(AES.block_size); cipher = AES.new(aes_key, AES.MODE_CBC, iv)
        padded_data = pad(data_bytes, AES.block_size); ciphertext = cipher.encrypt(padded_data)
        print("Đang giấu dữ liệu đã mã hóa vào video")
        binary_string_to_embed = ''.join(format(byte, '08b') for byte in ciphertext)
        temp_output_video = "temp_video_with_data.mkv"
        success = _embed_binary_to_video(input_video, binary_string_to_embed, temp_output_video)
        if not success: print("Quá trình giấu dữ liệu vào frame thất bại."); return False
        print("\nĐang đính kèm metadata bảo mật")
        metadata = {
            'data_type': data_type, 'original_filename': original_filename,
            'auth_salt': base64.b64encode(auth_salt).decode('utf-8'), 'key_salt': base64.b64encode(key_salt).decode('utf-8'),
            'auth_hash': base64.b64encode(auth_hash).decode('utf-8'), 'iv': base64.b64encode(iv).decode('utf-8')
        }
        success_attach = attach_metadata_to_mkv(temp_output_video, metadata, output_video)
        if not success_attach: print("Quá trình đính kèm metadata thất bại."); return False
        end_time = time.time()
        print(f"\nĐã giấu tin và mã hóa thành công vào file: {output_video}"); print(f"Thời gian thực thi: {end_time - start_time:.2f} giây."); return True
    except Exception as e:
        print(f"Lỗi không xác định trong quá trình giấu tin: {e}"); traceback.print_exc(); return False

def extract_securely(stego_video_path, password, output_dir=None):
    try:
        start_time = time.time()
        metadata = extract_metadata_from_mkv(stego_video_path)
        if not metadata: return None
        try:
            data_type = metadata['data_type']; original_filename = metadata.get('original_filename')
            auth_salt = base64.b64decode(metadata['auth_salt']); key_salt = base64.b64decode(metadata['key_salt'])
            auth_hash_original = base64.b64decode(metadata['auth_hash']); iv = base64.b64decode(metadata['iv'])
        except (KeyError, TypeError) as e:
            print(f"Lỗi: Metadata không hợp lệ hoặc thiếu trường. {e}"); return None
        print("Đang xác thực mật khẩu")
        auth_hash_attempt = PBKDF2(password, auth_salt, dkLen=32, count=100000, hmac_hash_module=SHA256)
        if auth_hash_attempt != auth_hash_original:
            print("SAI MẬT KHẨU"); 
            return "SAI_MAT_KHAU"
        print("Xác thực mật khẩu thành công.")
        print("Đang trích xuất và giải mã dữ liệu")
        aes_key = PBKDF2(password, key_salt, dkLen=32, count=100000, hmac_hash_module=SHA256)
        binary_data = _extract_binary_from_video(stego_video_path)
        if binary_data is None: return None
        ciphertext = bytearray(int(binary_data[i:i+8], 2) for i in range(0, len(binary_data), 8))
        try:
            cipher = AES.new(aes_key, AES.MODE_CBC, iv)
            decrypted_padded_data = cipher.decrypt(bytes(ciphertext))
            decrypted_data = unpad(decrypted_padded_data, AES.block_size)
        except (ValueError, KeyError) as e:
            print(f"\nLỗi khi giải mã: {e}. Dữ liệu có thể đã bị hỏng."); return None
        end_time = time.time(); print(f"Thời gian thực thi: {end_time - start_time:.2f} giây.")
        if data_type == 'text':
            print(f"Trích xuất văn bản thành công."); return decrypted_data.decode('utf-8')
        elif data_type in ['image', 'file']:
            if not output_dir or not original_filename:
                print("Lỗi: Cần cung cấp thư mục đầu ra (output_dir) và tên file gốc trong metadata."); return None
            os.makedirs(output_dir, exist_ok=True)
            output_path = os.path.join(output_dir, f"extracted_{original_filename}")
            with open(output_path, 'wb') as f: f.write(decrypted_data)
            print(f"Trích xuất và lưu tệp thành công tại: {output_path}"); return output_path
        else:
            print(f"Lỗi: Loại dữ liệu '{data_type}' trong metadata không xác định."); return None
    except Exception as e:
        print(f"Lỗi không xác định trong quá trình trích xuất: {e}"); traceback.print_exc(); return False

if __name__ == "__main__":
    pass